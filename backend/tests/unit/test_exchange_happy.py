# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Tests — Exchange Endpoint Happy Paths (GDPR Article 30 + Audit Logging)

Covers:
- send_document happy path (lines 70-100)
- create_room happy path (lines 119-137)
- get_room_events happy path (lines 150-168)
- MatrixClient error handling (502 responses)
- Audit logging integration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ─── Fixtures ─────────────────────────────────────────────────────────────────


GDPR_HEADERS = {"X-GDPR-Consent": "test-consent-token"}


@pytest.fixture
def client_with_matrix(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Test client with ENABLE_MATRIX_EXCHANGE=true."""
    monkeypatch.setattr("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True)
    monkeypatch.setattr("app.core.config.settings.ENABLE_MATRIX_AUTH", True)
    monkeypatch.setattr("app.core.config.settings.MATRIX_HOMESERVER_URL", "https://matrix.test.org")
    monkeypatch.setattr("app.core.config.settings.MATRIX_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr("app.core.config.settings.MATRIX_DEVICE_ID", "TESTDEVICE")
    monkeypatch.setattr("app.core.config.settings.DATA_RESIDENCY_REGION", "EU")

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


# ─── send_document Happy Path ─────────────────────────────────────────────────


class TestSendDocumentHappyPath:
    def test_send_document_success(self, client_with_matrix: TestClient) -> None:
        """send_document returns event_id and room_id on success."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.send_document = AsyncMock(return_value="$event_ok")
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/send",
                data={"room_id": "!room:matrix.org"},
                files={"file": ("test.pdf", b"PDF content", "application/pdf")},
            )

            assert response.status_code == 200
            body = response.json()
            assert body["event_id"] == "$event_ok"
            assert body["room_id"] == "!room:matrix.org"
            assert body["ephemeral"] is True
            MockClient.assert_called_once_with(
                access_token="user-access-token",
                device_id="TESTDEVICE",
            )
            instance.send_document.assert_called_once()
            instance.close.assert_called_once()

    def test_send_document_matrix_error(self, client_with_matrix: TestClient) -> None:
        """send_document returns 502 on MatrixClientError."""
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.send_document = AsyncMock(side_effect=MatrixClientError("upload failed"))
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/send",
                data={"room_id": "!room:matrix.org"},
                files={"file": ("test.pdf", b"PDF content", "application/pdf")},
            )

            assert response.status_code == 502
            assert response.json()["detail"]["code"] == "matrix_send_failed"
            assert "upload failed" not in response.text

    def test_send_document_generic_error(self, client_with_matrix: TestClient) -> None:
        """send_document returns 502 on generic Exception (no internals leaked)."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.send_document = AsyncMock(side_effect=RuntimeError("something broke"))
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/send",
                data={"room_id": "!room:matrix.org"},
                files={"file": ("test.pdf", b"PDF content", "application/pdf")},
            )

            assert response.status_code == 502
            assert response.json()["detail"]["code"] == "matrix_upstream_error"
            assert "something broke" not in response.text


# ─── create_room Happy Path ──────────────────────────────────────────────────


class TestCreateRoomHappyPath:
    def test_create_room_success(self, client_with_matrix: TestClient) -> None:
        """create_room returns room_id on success."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(return_value="!newroom:matrix.org")
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org", "@bob:matrix.org"]},
            )

            assert response.status_code == 200
            assert response.json()["room_id"] == "!newroom:matrix.org"
            instance.create_secure_room.assert_called_once_with(
                ["@alice:matrix.org", "@bob:matrix.org"]
            )
            instance.close.assert_called_once()

    def test_create_room_requires_authenticated_matrix_session(
        self,
        client_with_matrix: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Room creation fails closed when the Matrix session cookie is missing."""
        from app.api.v1.endpoints.matrix_auth import require_authenticated_matrix_session
        from app.main import app

        monkeypatch.setattr("app.core.config.settings.MATRIX_ACCESS_TOKEN", "")
        app.dependency_overrides.pop(require_authenticated_matrix_session, None)
        with TestClient(app, headers=GDPR_HEADERS) as unauthenticated_client:
            response = unauthenticated_client.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org"]},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Matrix authentication required"

    def test_create_room_matrix_error(self, client_with_matrix: TestClient) -> None:
        """create_room returns 502 on MatrixClientError."""
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(
                side_effect=MatrixClientError("room creation failed")
            )
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org"]},
            )

            assert response.status_code == 502
            assert response.json()["detail"]["code"] == "matrix_room_creation_failed"
            assert "room creation failed" not in response.text

    @pytest.mark.parametrize(
        ("matrix_error", "status_code", "public_code"),
        [
            (
                {"operation": "invite", "status_code": 403, "errcode": "M_FORBIDDEN"},
                502,
                "matrix_invitation_forbidden",
            ),
            (
                {"operation": "invite", "status_code": 404, "errcode": "M_NOT_FOUND"},
                502,
                "matrix_participant_not_found",
            ),
            (
                {"operation": "create_room", "status_code": 403, "errcode": "M_FORBIDDEN"},
                403,
                "matrix_room_forbidden",
            ),
            (
                {
                    "operation": "create_room",
                    "status_code": 429,
                    "errcode": "M_LIMIT_EXCEEDED",
                    "retry_after_ms": 1000,
                },
                429,
                "matrix_rate_limited",
            ),
            (
                {"operation": "create_room", "status_code": 401, "errcode": "M_UNKNOWN_TOKEN"},
                401,
                "matrix_authentication_required",
            ),
        ],
    )
    def test_create_room_classifies_matrix_error(
        self,
        client_with_matrix: TestClient,
        matrix_error: dict[str, object],
        status_code: int,
        public_code: str,
    ) -> None:
        """Room creation returns actionable errors without upstream details."""
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(
                side_effect=MatrixClientError("private upstream detail", **matrix_error)
            )
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org"]},
            )

        assert response.status_code == status_code
        assert response.json()["detail"]["code"] == public_code
        assert "private upstream detail" not in response.text

    def test_create_room_passes_retry_after_ms_uncapped(
        self, client_with_matrix: TestClient
    ) -> None:
        """retry_after_ms is passed through without being capped at 30s."""
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(
                side_effect=MatrixClientError(
                    "rate limited",
                    operation="create_room",
                    status_code=429,
                    errcode="M_LIMIT_EXCEEDED",
                    retry_after_ms=1_800_000,  # 30 min
                )
            )
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org"]},
            )

        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "matrix_rate_limited"
        assert response.json()["detail"]["retry_after_ms"] == 1_800_000

    def test_create_room_generic_error(self, client_with_matrix: TestClient) -> None:
        """create_room returns 502 on generic Exception."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(side_effect=RuntimeError("unexpected"))
            instance.close = AsyncMock()

            response = client_with_matrix.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@alice:matrix.org"]},
            )

            assert response.status_code == 502
            assert response.json()["detail"]["code"] == "matrix_upstream_error"
            assert "unexpected" not in response.text


# ─── get_room_events Happy Path ──────────────────────────────────────────────


class TestGetRoomEventsHappyPath:
    def test_get_events_success(self, client_with_matrix: TestClient) -> None:
        """get_room_events returns event list on success."""
        mock_events = [
            {"event_id": "$evt1", "sender": "@alice:matrix.org"},
            {"event_id": "$evt2", "sender": "@bob:matrix.org"},
        ]
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(return_value=mock_events)
            instance.close = AsyncMock()

            response = client_with_matrix.get(
                "/api/v1/exchange/rooms/!room:matrix.org/events?limit=10"
            )

            assert response.status_code == 200
            assert len(response.json()) == 2
            instance.get_room_events.assert_called_once_with(room_id="!room:matrix.org", limit=10)
            instance.close.assert_called_once()

    def test_get_events_limit_capping(self, client_with_matrix: TestClient) -> None:
        """get_room_events caps limit at 100."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(return_value=[])
            instance.close = AsyncMock()

            response = client_with_matrix.get(
                "/api/v1/exchange/rooms/!room:matrix.org/events?limit=999"
            )

            assert response.status_code == 200
            instance.get_room_events.assert_called_once_with(room_id="!room:matrix.org", limit=100)

    def test_get_events_limit_minimum(self, client_with_matrix: TestClient) -> None:
        """get_room_events caps limit at minimum 1."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(return_value=[])
            instance.close = AsyncMock()

            response = client_with_matrix.get(
                "/api/v1/exchange/rooms/!room:matrix.org/events?limit=-5"
            )

            assert response.status_code == 200
            instance.get_room_events.assert_called_once_with(room_id="!room:matrix.org", limit=1)

    def test_get_events_matrix_error(self, client_with_matrix: TestClient) -> None:
        """get_room_events returns 502 on MatrixClientError."""
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(side_effect=MatrixClientError("retrieval failed"))
            instance.close = AsyncMock()

            response = client_with_matrix.get("/api/v1/exchange/rooms/!room:matrix.org/events")

            assert response.status_code == 502
            assert response.json()["detail"]["code"] == "matrix_events_failed"
            assert "retrieval failed" not in response.text

    def test_get_events_generic_error(self, client_with_matrix: TestClient) -> None:
        """get_room_events returns 502 on generic Exception."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(side_effect=RuntimeError("boom"))
            instance.close = AsyncMock()

            response = client_with_matrix.get("/api/v1/exchange/rooms/!room:matrix.org/events")

            assert response.status_code == 502
            assert response.json()["detail"]["code"] == "matrix_upstream_error"
            assert "boom" not in response.text
