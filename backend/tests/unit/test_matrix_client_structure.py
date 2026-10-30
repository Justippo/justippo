# SPDX-License-Identifier: AGPL-3.0-or-later
"""Matrix Client Structure Tests — httpx-based, no nio dependency."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.matrix.client import MatrixClient, MatrixClientError


def test_matrix_client_imports_without_nio():
    """Test that client module imports successfully without matrix-nio."""
    from app.integrations.matrix import client

    assert hasattr(client, "MatrixClient")
    assert hasattr(client, "MatrixClientError")
    assert hasattr(client, "logger")


def test_matrix_client_initialization():
    """Test client initialization sets config values."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "test-token"
        mock_settings.MATRIX_DEVICE_ID = "test-device"

        client = MatrixClient()
        assert client._base_url == "https://matrix.org"
        assert client._token == "test-token"


def test_matrix_client_error_handling():
    """Test MatrixClientError exception handling."""
    with pytest.raises(MatrixClientError) as exc_info:
        raise MatrixClientError("Test error")

    assert str(exc_info.value) == "Test error"
    assert isinstance(exc_info.value, Exception)


@pytest.mark.asyncio
async def test_matrix_client_close_is_noop():
    """Test close is a no-op (httpx clients are per-request)."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "test-token"
        mock_settings.MATRIX_DEVICE_ID = "test-device"

        client = MatrixClient()
        await client.close()


def test_matrix_user_id_regex():
    """Test user ID validation regex pattern."""
    from app.api.v1.endpoints.exchange import _MATRIX_USER_ID_RE

    valid_ids = [
        "@alice:matrix.org",
        "@bob.example:matrix.org",
        "@user_with.underscores:matrix.org",
        "@user-with-dashes:matrix.org",
        "@user123:matrix.org",
    ]

    for user_id in valid_ids:
        assert _MATRIX_USER_ID_RE.match(user_id), f"Should match: {user_id}"

    invalid_ids = [
        "alice:matrix.org",
        "@alice",
        "@alice:localhost",
        "@alice:matrix",
        "@alice:matrix.",
        "@alice:matrix.org:",
        "",
        "@@alice:matrix.org",
        "@alice@@matrix.org",
    ]

    for user_id in invalid_ids:
        assert not _MATRIX_USER_ID_RE.match(user_id), f"Should not match: {user_id}"


def test_validate_matrix_user_ids():
    """Test user ID validation function."""
    from app.api.v1.endpoints.exchange import _validate_matrix_user_ids

    _validate_matrix_user_ids(["@alice:matrix.org", "@bob:matrix.org"])

    with pytest.raises(Exception) as exc_info:
        _validate_matrix_user_ids([])
    assert "must not be empty" in str(exc_info.value)

    with pytest.raises(Exception) as exc_info:
        _validate_matrix_user_ids(["invalid-user-id"])
    assert "Invalid Matrix user ID format" in str(exc_info.value)


def test_matrix_client_logging():
    """Test that client has proper logging configured."""
    from app.integrations.matrix.client import logger

    assert logger.name == "app.integrations.matrix.client"


def test_matrix_client_documentation():
    """Test that client has proper docstrings."""
    from app.integrations.matrix.client import MatrixClient

    assert MatrixClient.__doc__ is not None
    assert "Matrix" in MatrixClient.__doc__

    assert MatrixClient.create_secure_room.__doc__ is not None
    assert "Create" in MatrixClient.create_secure_room.__doc__

    assert MatrixClient.send_document.__doc__ is not None
    assert "Upload" in MatrixClient.send_document.__doc__

    assert MatrixClient.get_room_events.__doc__ is not None
    assert "Retrieve" in MatrixClient.get_room_events.__doc__


def test_matrix_client_error_documentation():
    """Test that custom error has proper documentation."""
    from app.integrations.matrix.client import MatrixClientError

    assert MatrixClientError.__doc__ is not None
    assert "Matrix operation fails" in MatrixClientError.__doc__


def test_matrix_client_gdpr_compliance():
    """Test GDPR-related aspects of client."""
    from app.integrations.matrix.client import MatrixClient

    doc = MatrixClient.send_document.__doc__
    assert "GDPR" in doc or "NEVER log" in doc or "doc_bytes" in doc

    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "test-token"
        mock_settings.MATRIX_DEVICE_ID = "DEV"

        client = MatrixClient()
        assert not hasattr(client, "_documents")
        assert not hasattr(client, "_file_cache")


def _mock_response(status: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = "" if json_data is None else str(json_data)
    resp.json.return_value = json_data or {}
    return resp


@pytest.mark.asyncio
async def test_create_room_success():
    """Cover successful room creation via httpx."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "tok"
        mock_settings.MATRIX_DEVICE_ID = "DEV"
        mock_settings.MATRIX_ROOM_PREFIX = "evidence-eu"

        client = MatrixClient()
        mock_resp = _mock_response(200, {"room_id": "!abc123:matrix.org"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=mock_resp)

            room_id = await client.create_secure_room(["@alice:matrix.org"])

        assert room_id == "!abc123:matrix.org"


@pytest.mark.asyncio
async def test_send_document_success():
    """Cover successful document send via httpx."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "tok"
        mock_settings.MATRIX_DEVICE_ID = "DEV"

        client = MatrixClient()
        upload_resp = _mock_response(200, {"content_uri": "mxc://matrix.org/file123"})
        send_resp = _mock_response(200, {"event_id": "$evt456"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=upload_resp)
            mock_ac.return_value.put = AsyncMock(return_value=send_resp)

            event_id = await client.send_document(
                room_id="!room:matrix.org",
                doc_bytes=b"hello world",
                filename="doc.pdf",
                mime_type="application/pdf",
            )

        assert event_id == "$evt456"


@pytest.mark.asyncio
async def test_get_room_events_success():
    """Cover successful event retrieval via httpx."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "tok"
        mock_settings.MATRIX_DEVICE_ID = "DEV"

        client = MatrixClient()
        mock_resp = _mock_response(
            200,
            {
                "chunk": [
                    {
                        "event_id": "$evt1",
                        "sender": "@alice:matrix.org",
                        "type": "m.room.message",
                        "origin_server_ts": 12345,
                        "content": {"msgtype": "m.text", "body": "hello"},
                    }
                ]
            },
        )

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            events = await client.get_room_events("!room:matrix.org")

        assert len(events) == 1
        assert events[0]["event_id"] == "$evt1"


@pytest.mark.asyncio
async def test_create_room_error():
    """Cover room creation failure via httpx."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "tok"
        mock_settings.MATRIX_DEVICE_ID = "DEV"
        mock_settings.MATRIX_ROOM_PREFIX = "evidence-eu"

        client = MatrixClient()
        mock_resp = _mock_response(500, {"error": "internal"})

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.post = AsyncMock(return_value=mock_resp)

            with pytest.raises(
                MatrixClientError, match="Operation create_room failed after 3 attempts: HTTP 500"
            ):
                await client.create_secure_room(["@alice:matrix.org"])


@pytest.mark.asyncio
async def test_get_room_events_redacts_binary_body():
    """Cover binary content redaction in event body."""
    with patch("app.integrations.matrix.client.settings") as mock_settings:
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "tok"
        mock_settings.MATRIX_DEVICE_ID = "DEV"

        client = MatrixClient()
        mock_resp = _mock_response(
            200,
            {
                "chunk": [
                    {
                        "event_id": "$evt1",
                        "sender": "@alice:matrix.org",
                        "type": "m.room.message",
                        "origin_server_ts": 12345,
                        "content": {"body": b"\x89PNG\r\n\x1a\n", "msgtype": "m.file"},
                    }
                ]
            },
        )

        with patch("httpx.AsyncClient") as mock_ac:
            mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_ac.return_value)
            mock_ac.return_value.get = AsyncMock(return_value=mock_resp)

            events = await client.get_room_events("!room:matrix.org")

        assert len(events) == 1
        assert events[0]["content"]["body"] == "[REDACTED — binary content]"
        assert events[0]["content"]["msgtype"] == "m.file"
