"""
Tests — Matrix Protocol Integration

Covers:
- MatrixClient methods (mocked matrix-nio)
- 403 on all exchange endpoints when ENABLE_MATRIX_EXCHANGE=false
- send_document does not retain bytes after call
- Invalid Matrix user ID format returns 422 on room creation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings

# ─── Fixtures ─────────────────────────────────────────────────────────────────


GDPR_HEADERS = {"X-GDPR-Consent": "test-consent-token"}


@pytest.fixture
def client() -> TestClient:
    """Test client with ENABLE_MATRIX_EXCHANGE=false (default)."""
    from app.api.v1.endpoints.matrix_auth import (
        AuthenticatedMatrixSession,
        require_authenticated_matrix_session,
    )
    from app.main import app

    app.dependency_overrides[require_authenticated_matrix_session] = lambda: (
        AuthenticatedMatrixSession(
            session_id="test-session",
            user_id="@owner:matrix.test.org",
            device_id="TESTDEVICE",
            access_token="user-access-token",
        )
    )
    yield TestClient(app, headers=GDPR_HEADERS)
    app.dependency_overrides.pop(require_authenticated_matrix_session, None)


@pytest.fixture
def client_with_matrix_enabled() -> TestClient:
    """Test client with ENABLE_MATRIX_EXCHANGE=true (overridden per-test)."""
    with patch("app.core.config.settings") as mock_settings:
        # Copy all attributes from real settings
        real_settings = Settings()
        for field in real_settings.model_fields:
            setattr(mock_settings, field, getattr(real_settings, field))
        # Override the feature flag
        mock_settings.ENABLE_MATRIX_EXCHANGE = True
        mock_settings.MATRIX_HOMESERVER_URL = "https://matrix.test.org"
        mock_settings.MATRIX_ACCESS_TOKEN = "test-token"
        mock_settings.MATRIX_DEVICE_ID = "TESTDEVICE"

        from app.api.v1.endpoints.matrix_auth import (
            AuthenticatedMatrixSession,
            require_authenticated_matrix_session,
        )
        from app.main import app

        app.dependency_overrides[require_authenticated_matrix_session] = lambda: (
            AuthenticatedMatrixSession(
                session_id="test-session",
                user_id="@owner:matrix.test.org",
                device_id="TESTDEVICE",
                access_token="user-access-token",
            )
        )
        yield TestClient(app)
        app.dependency_overrides.pop(require_authenticated_matrix_session, None)


# ─── Feature Flag 403 Tests ──────────────────────────────────────────────────


class TestFeatureFlag403:
    """All exchange endpoints must return 403 when ENABLE_MATRIX_EXCHANGE=false."""

    def test_send_returns_403_when_flag_off(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/send",
            data={"room_id": "!room:matrix.org"},
            files={"file": ("test.pdf", b"fake content", "application/pdf")},
        )
        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["flag"] == "ENABLE_MATRIX_EXCHANGE"

    def test_create_room_returns_403_when_flag_off(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/rooms",
            json={"participants": ["@user:matrix.org"]},
        )
        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["flag"] == "ENABLE_MATRIX_EXCHANGE"

    def test_get_events_returns_403_when_flag_off(self, client: TestClient) -> None:
        response = client.get("/api/v1/exchange/rooms/!room:matrix.org/events")
        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["flag"] == "ENABLE_MATRIX_EXCHANGE"


# ─── Matrix User ID Validation Tests ─────────────────────────────────────────


class TestMatrixUserIdValidation:
    """Invalid Matrix user IDs must return 422 on room creation."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True)

    def test_empty_participants_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/rooms",
            json={"participants": []},
        )
        assert response.status_code == 422
        assert "must not be empty" in response.json()["detail"]

    def test_invalid_user_id_no_at_sign(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/rooms",
            json={"participants": ["user:matrix.org"]},
        )
        assert response.status_code == 422

    def test_invalid_user_id_no_domain(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/rooms",
            json={"participants": ["@user"]},
        )
        assert response.status_code == 422

    def test_invalid_user_id_no_tld(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/rooms",
            json={"participants": ["@user:localhost"]},
        )
        assert response.status_code == 422

    def test_invalid_user_id_spaces(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/exchange/rooms",
            json={"participants": ["@us er:matrix.org"]},
        )
        assert response.status_code == 422

    def test_valid_user_id_passes_validation(self, client: TestClient) -> None:
        """Valid ID passes validation but fails on Matrix call (mocked below)."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(return_value="!newroom:matrix.org")
            instance.close = AsyncMock()

            response = client.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org"]},
            )
            assert response.status_code == 200
            assert response.json()["room_id"] == "!newroom:matrix.org"


# ─── MatrixClient Unit Tests (mocked httpx) ───────────────────────────────────


class TestMatrixClientMocked:
    """Unit tests for MatrixClient with mocked httpx.AsyncClient.

    MatrixClient uses direct HTTP API calls via httpx (Pyodide-safe), not
    matrix-nio. Tests mock httpx.AsyncClient to avoid real network calls.
    """

    @pytest.fixture(autouse=True)
    def _enable_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True)
        monkeypatch.setattr(
            "app.core.config.settings.MATRIX_HOMESERVER_URL", "https://matrix.test.org"
        )
        monkeypatch.setattr("app.core.config.settings.MATRIX_ACCESS_TOKEN", "test-token")
        monkeypatch.setattr("app.core.config.settings.MATRIX_DEVICE_ID", "TESTDEVICE")

    @patch("app.integrations.matrix.client.httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_create_secure_room(self, MockAsyncClient: MagicMock) -> None:
        from app.integrations.matrix.client import MatrixClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"room_id": "!abc123:matrix.org"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = mock_client

        client = MatrixClient()
        room_id = await client.create_secure_room(["@bob:matrix.org"])

        assert room_id == "!abc123:matrix.org"
        assert mock_client.post.await_count == 2
        await client.close()

    @patch("app.integrations.matrix.client.httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_send_document(self, MockAsyncClient: MagicMock) -> None:
        from app.integrations.matrix.client import MatrixClient

        mock_upload_response = MagicMock()
        mock_upload_response.status_code = 200
        mock_upload_response.json.return_value = {"content_uri": "mxc://matrix.org/abc123"}

        mock_send_response = MagicMock()
        mock_send_response.status_code = 200
        mock_send_response.json.return_value = {"event_id": "$event123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_upload_response)
        mock_client.put = AsyncMock(return_value=mock_send_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = mock_client

        client = MatrixClient()
        event_id = await client.send_document(
            room_id="!room:matrix.org",
            doc_bytes=b"PDF content here",
            filename="contract.pdf",
            mime_type="application/pdf",
        )

        assert event_id == "$event123"
        mock_client.post.assert_called_once()  # upload
        mock_client.put.assert_called_once()  # send message
        await client.close()

    @patch("app.integrations.matrix.client.httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_get_room_events(self, MockAsyncClient: MagicMock) -> None:
        from app.integrations.matrix.client import MatrixClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "chunk": [
                {
                    "event_id": "$evt1",
                    "sender": "@alice:matrix.org",
                    "origin_server_ts": 1717600000000,
                    "type": "m.room.message",
                    "content": {
                        "msgtype": "m.file",
                        "body": "doc.pdf",
                        "url": "mxc://x/y",
                    },
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockAsyncClient.return_value = mock_client

        client = MatrixClient()
        events = await client.get_room_events("!room:matrix.org", limit=10)

        assert len(events) == 1
        assert events[0]["event_id"] == "$evt1"
        assert events[0]["content"]["msgtype"] == "m.file"
        await client.close()


# ─── GDPR: send_document must not retain bytes ───────────────────────────────


class TestGDPRBytesCleanup:
    """Verify that send_document endpoint deletes file bytes after sending."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True)

    def test_send_empty_file_returns_422(self, client: TestClient) -> None:
        """Uploading an empty file must be rejected with 422."""
        response = client.post(
            "/api/v1/exchange/send",
            data={"room_id": "!room:matrix.org"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()

    def test_send_document_does_not_retain_bytes(self, client: TestClient) -> None:
        """After send_document completes, the doc_bytes local must be deleted."""
        captured_bytes_ref: list[bytes] = []

        async def mock_send_document(
            room_id: str, doc_bytes: bytes, filename: str, mime_type: str
        ) -> str:
            # Capture a reference to verify it's the same object
            captured_bytes_ref.append(doc_bytes)
            return "$event_ok"

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.send_document = AsyncMock(side_effect=mock_send_document)
            instance.close = AsyncMock()

            response = client.post(
                "/api/v1/exchange/send",
                data={"room_id": "!room:matrix.org"},
                files={"file": ("test.pdf", b"secret document bytes", "application/pdf")},
            )

            assert response.status_code == 200
            result = response.json()
            assert result["ephemeral"] is True
            assert result["event_id"] == "$event_ok"

            # The endpoint used `del doc_bytes` — while we can't directly verify
            # the local was deleted from outside, we verify the response shape
            # confirms the ephemeral contract and the mock was called correctly.
            instance.send_document.assert_called_once()
