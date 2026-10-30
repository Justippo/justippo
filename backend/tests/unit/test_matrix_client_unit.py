"""
Unit tests for MatrixClient — fully mocked httpx.

Coverage:
- create_secure_room(): success, failure (non-200), transport error
- send_document(): success, upload failure, send failure, transport error
- get_room_events(): success, binary body redaction, failure, transport error
- close(): no-op (httpx clients are per-request)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.matrix.client import MatrixClient, MatrixClientError


def _mock_response(status: int, json_data: dict[str, Any] | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = "" if json_data is None else str(json_data)
    resp.json.return_value = json_data or {}
    return resp


@pytest.fixture
def mock_settings():
    with patch("app.integrations.matrix.client.settings") as mock:
        mock.MATRIX_HOMESERVER_URL = "https://matrix.test.org"
        mock.MATRIX_ACCESS_TOKEN = "test-token"
        mock.MATRIX_DEVICE_ID = "DEV123"
        mock.MATRIX_ROOM_PREFIX = "evidence-eu"
        yield mock


class TestMatrixClientInit:
    def test_init_sets_config(self, mock_settings) -> None:
        client = MatrixClient()
        assert client._base_url == "https://matrix.test.org"
        assert client._token == "test-token"

    def test_init_prefers_explicit_session_credentials(self, mock_settings) -> None:
        client = MatrixClient(
            access_token="user-token",
            base_url="https://matrix.user.example/",
            device_id="USERDEVICE",
        )

        assert client._base_url == "https://matrix.user.example"
        assert client._token == "user-token"
        assert client._device_id == "USERDEVICE"

    def test_headers_include_bearer_token(self, mock_settings) -> None:
        client = MatrixClient()
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"


class TestMatrixClientClose:
    @pytest.mark.asyncio
    async def test_close_is_noop(self, mock_settings) -> None:
        client = MatrixClient()
        await client.close()


class TestCreateSecureRoom:
    @pytest.mark.asyncio
    async def test_success_returns_room_id(self, mock_settings) -> None:
        client = MatrixClient()
        room_resp = _mock_response(200, {"room_id": "!abc:matrix.org"})
        invite_resp = _mock_response(200, {})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(side_effect=[room_resp, invite_resp])

            room_id = await client.create_secure_room(["@alice:matrix.org"])

        assert room_id == "!abc:matrix.org"
        calls = mock_ac.return_value.post.await_args_list
        assert calls[0].kwargs["json"].get("invite") is None
        assert calls[0].kwargs["json"]["initial_state"][0]["type"] == "m.room.encryption"
        assert calls[1].args[0].endswith("/rooms/!abc:matrix.org/invite")
        assert calls[1].kwargs["json"] == {"user_id": "@alice:matrix.org"}

    @pytest.mark.asyncio
    async def test_invitation_failure_preserves_sanitized_diagnostics(self, mock_settings) -> None:
        client = MatrixClient()
        invite_resp = _mock_response(
            403,
            {"errcode": "M_FORBIDDEN", "error": "sensitive homeserver explanation"},
        )

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=invite_resp)

            with pytest.raises(MatrixClientError) as exc_info:
                await client._invite_user(
                    mock_ac.return_value, "!abc:matrix.org", "@alice:matrix.org"
                )

        assert exc_info.value.operation == "invite"
        assert exc_info.value.status_code == 403
        assert exc_info.value.errcode == "M_FORBIDDEN"
        assert "sensitive" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_preserves_retry_delay(self, mock_settings) -> None:
        client = MatrixClient()
        mock_resp = _mock_response(
            429,
            {"errcode": "M_LIMIT_EXCEEDED", "retry_after_ms": 1500},
        )

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=mock_resp)

            with pytest.raises(MatrixClientError) as exc_info:
                await client.create_secure_room(["@alice:matrix.org"])

        assert exc_info.value.operation == "create_room"
        assert exc_info.value.retry_after_ms == 1500

    @pytest.mark.asyncio
    async def test_failure_raises_matrix_client_error(self, mock_settings) -> None:
        client = MatrixClient()
        mock_resp = _mock_response(400, {"error": "bad request"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=mock_resp)

            with pytest.raises(MatrixClientError, match="Room creation failed"):
                await client.create_secure_room(["@bob:matrix.org"])

    @pytest.mark.asyncio
    async def test_transport_error_raises(self, mock_settings) -> None:
        client = MatrixClient()

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

            with pytest.raises(MatrixClientError, match="transport error"):
                await client.create_secure_room(["@alice:matrix.org"])

    @pytest.mark.asyncio
    async def test_missing_room_id_raises(self, mock_settings) -> None:
        client = MatrixClient()
        mock_resp = _mock_response(200, {})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=mock_resp)

            with pytest.raises(MatrixClientError, match="missing room_id"):
                await client.create_secure_room(["@alice:matrix.org"])


class TestSendDocument:
    @pytest.mark.asyncio
    async def test_success_returns_event_id(self, mock_settings) -> None:
        client = MatrixClient()
        upload_resp = _mock_response(200, {"content_uri": "mxc://matrix.org/abc"})
        send_resp = _mock_response(200, {"event_id": "$evt123"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=upload_resp)
            mock_ac.return_value.put = AsyncMock(return_value=send_resp)

            event_id = await client.send_document(
                room_id="!room:matrix.org",
                doc_bytes=b"PDF content",
                filename="contract.pdf",
                mime_type="application/pdf",
            )

        assert event_id == "$evt123"

    @pytest.mark.asyncio
    async def test_upload_failure_raises_error(self, mock_settings) -> None:
        client = MatrixClient()
        upload_resp = _mock_response(413, {"error": "too large"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=upload_resp)

            with pytest.raises(MatrixClientError, match="Upload failed"):
                await client.send_document(
                    room_id="!room:matrix.org",
                    doc_bytes=b"bytes",
                    filename="doc.pdf",
                    mime_type="application/pdf",
                )

    @pytest.mark.asyncio
    async def test_send_failure_raises_error(self, mock_settings) -> None:
        client = MatrixClient()
        upload_resp = _mock_response(200, {"content_uri": "mxc://matrix.org/abc"})
        send_resp = _mock_response(403, {"error": "forbidden"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=upload_resp)
            mock_ac.return_value.put = AsyncMock(return_value=send_resp)

            with pytest.raises(MatrixClientError, match="Send failed"):
                await client.send_document(
                    room_id="!room:matrix.org",
                    doc_bytes=b"bytes",
                    filename="doc.pdf",
                    mime_type="application/pdf",
                )

    @pytest.mark.asyncio
    async def test_missing_content_uri_raises(self, mock_settings) -> None:
        client = MatrixClient()
        upload_resp = _mock_response(200, {})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=upload_resp)

            with pytest.raises(MatrixClientError, match="missing content_uri"):
                await client.send_document(
                    room_id="!room:matrix.org",
                    doc_bytes=b"bytes",
                    filename="doc.pdf",
                    mime_type="application/pdf",
                )


class TestGetRoomEvents:
    @pytest.mark.asyncio
    async def test_success_returns_event_list(self, mock_settings) -> None:
        client = MatrixClient()
        events_data = {
            "chunk": [
                {
                    "event_id": "$evt1",
                    "sender": "@alice:matrix.org",
                    "type": "m.room.message",
                    "origin_server_ts": 1717600000000,
                    "content": {"msgtype": "m.file", "body": "doc.pdf"},
                }
            ]
        }
        mock_resp = _mock_response(200, events_data)

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            events = await client.get_room_events("!room:matrix.org", limit=10)

        assert len(events) == 1
        assert events[0]["event_id"] == "$evt1"
        assert events[0]["content"]["msgtype"] == "m.file"

    @pytest.mark.asyncio
    async def test_binary_body_is_redacted(self, mock_settings) -> None:
        client = MatrixClient()
        events_data = {
            "chunk": [
                {
                    "event_id": "$evt2",
                    "sender": "@bob:matrix.org",
                    "type": "m.room.message",
                    "origin_server_ts": 0,
                    "content": {"msgtype": "m.file", "body": b"\x89PDF binary data"},
                }
            ]
        }
        mock_resp = _mock_response(200, events_data)

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            events = await client.get_room_events("!room:matrix.org")

        assert "REDACTED" in events[0]["content"]["body"]

    @pytest.mark.asyncio
    async def test_failure_raises_matrix_client_error(self, mock_settings) -> None:
        client = MatrixClient()
        mock_resp = _mock_response(403, {"error": "forbidden"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            with pytest.raises(MatrixClientError, match="Event retrieval failed"):
                await client.get_room_events("!room:matrix.org")

    @pytest.mark.asyncio
    async def test_transport_error_raises(self, mock_settings) -> None:
        client = MatrixClient()

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

            with pytest.raises(MatrixClientError, match="transport error"):
                await client.get_room_events("!room:matrix.org")


class TestMatrixConfigurationError:
    """Tests for placeholder token validation (4.3s crash prevention)."""

    def test_empty_token_raises_configuration_error(self, mock_settings) -> None:
        mock_settings.MATRIX_ACCESS_TOKEN = ""
        with pytest.raises(MatrixClientError, match="placeholder"):
            MatrixClient()

    def test_placeholder_token_raises_configuration_error(self, mock_settings) -> None:
        mock_settings.MATRIX_ACCESS_TOKEN = "your-matrix-token"
        with pytest.raises(MatrixClientError, match="placeholder"):
            MatrixClient()

    def test_real_token_does_not_raise(self, mock_settings) -> None:
        mock_settings.MATRIX_ACCESS_TOKEN = "syt_real_token_abc123"
        client = MatrixClient()
        assert client._token == "syt_real_token_abc123"

    def test_explicit_token_bypasses_validation(self, mock_settings) -> None:
        mock_settings.MATRIX_ACCESS_TOKEN = ""
        client = MatrixClient(access_token="user-explicit-token")
        assert client._token == "user-explicit-token"


class TestMatrixTimeoutError:
    """Tests for timeout error handling (11.8s crash prevention)."""

    @pytest.mark.asyncio
    async def test_create_room_timeout_raises_timeout_error(self, mock_settings) -> None:
        from app.integrations.matrix.client import MatrixTimeoutError

        client = MatrixClient()

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

            with pytest.raises(MatrixTimeoutError, match="timed out"):
                await client.create_secure_room(["@user:test.org"])

    @pytest.mark.asyncio
    async def test_send_document_upload_timeout_raises_timeout_error(self, mock_settings) -> None:
        from app.integrations.matrix.client import MatrixTimeoutError

        client = MatrixClient()

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("upload timeout")
            )

            with pytest.raises(MatrixTimeoutError, match="timed out"):
                await client.send_document(
                    "!room:matrix.org",
                    b"test content",
                    "test.pdf",
                    "application/pdf",
                )

    @pytest.mark.asyncio
    async def test_get_room_events_timeout_raises_timeout_error(self, mock_settings) -> None:
        from app.integrations.matrix.client import MatrixTimeoutError

        client = MatrixClient()

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

            with pytest.raises(MatrixTimeoutError, match="timed out"):
                await client.get_room_events("!room:matrix.org")


class TestMatrixHealthCheck:
    """Tests for Matrix health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_settings) -> None:
        client = MatrixClient()
        mock_resp = _mock_response(200, {"unstable_features": {"org.matrix.msc3504": "v1.0"}})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            health = await client.check_health()
            assert health["status"] == "healthy"
            assert health["server_version"] == "v1.0"
            assert health["connectivity"] == "ok"

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, mock_settings) -> None:
        from app.integrations.matrix.client import MatrixTimeoutError

        client = MatrixClient()

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("health timeout")
            )

            with pytest.raises(MatrixTimeoutError, match="Health check timed out"):
                await client.check_health()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_settings) -> None:
        client = MatrixClient()
        mock_resp = _mock_response(503, {"error": "service unavailable"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            with pytest.raises(MatrixClientError, match="Health check failed"):
                await client.check_health()


class TestMatrixRetryPattern:
    """Tests for exponential backoff retry pattern."""

    @pytest.mark.asyncio
    async def test_create_room_retries_on_transient_errors(self, mock_settings) -> None:
        client = MatrixClient()
        # Test that room creation retries on 503 errors
        # Mock only the room creation call, not the invite calls

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)

            # First two room creation attempts fail with 503, third succeeds
            room_attempts = 0

            async def mock_post(*args, **kwargs):
                nonlocal room_attempts
                url = args[0] if args else kwargs.get("url", "")

                # Only mock room creation calls, not invite calls
                if "/createRoom" in url:
                    room_attempts += 1
                    if room_attempts <= 2:
                        # First two attempts fail
                        resp = _mock_response(503, {"error": "temporarily unavailable"})
                        return resp
                    else:
                        # Third attempt succeeds
                        resp = _mock_response(200, {"room_id": "!retry:matrix.org"})
                        return resp
                else:
                    # For invite calls, return success
                    return _mock_response(200, {})

            mock_ac.return_value.post = mock_post

            room_id = await client.create_secure_room(["@user:test.org"])
            assert room_id == "!retry:matrix.org"
            # Should have attempted room creation 3 times (2 retries + 1 success)
            assert room_attempts == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_error(self, mock_settings) -> None:
        client = MatrixClient()
        # All three attempts fail
        responses = [
            _mock_response(503, {"error": "temporarily unavailable"}),
            _mock_response(503, {"error": "temporarily unavailable"}),
            _mock_response(503, {"error": "temporarily unavailable"}),
        ]

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(side_effect=responses)

            with pytest.raises(MatrixClientError, match="failed after 3 attempts"):
                await client.create_secure_room(["@user:test.org"])
