"""
Unit tests for AuditLogMiddleware (Sprint 2)

Coverage:
- Audited paths (/api/v1/documents, /api/v1/translate) write to D1
- Exempt paths (/health, /api/v1/health, /api/docs) skip D1 write
- Non-audited paths (e.g. /api/v1/search) pass through without write
- D1 unavailable (scope has no env) → no error, request passes through
- request_id_hash is SHA256[:8], never contains raw nonce
- mime_type extracted from Content-Type header (stripped of params)
- response status code is recorded correctly
- duration_ms is a non-negative integer
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from app.core.middleware import AuditLogMiddleware

# ---------------------------------------------------------------------------
# Minimal test app
# ---------------------------------------------------------------------------


def _make_app(scope_env: Any = None) -> FastAPI:
    """Build a minimal FastAPI app with AuditLogMiddleware and configurable env."""
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware)

    @app.post("/api/v1/documents/")
    async def upload(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/translate/")
    async def translate(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/search/")
    async def search() -> dict[str, str]:
        return {"results": []}

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_db() -> MagicMock:
    """Mock D1Client that tracks execute() calls."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_write_on_documents_path() -> None:
    """POST /api/v1/documents/ should trigger a D1 write."""
    mock_db = _make_mock_db()

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        # TestClient is sync — use it directly (Starlette handles async internally)
        client.post("/api/v1/documents/", headers={"X-GDPR-Consent": "test"})

    mock_db.execute.assert_called_once()
    args = mock_db.execute.call_args
    sql: str = args[0][0]
    params: list = args[0][1]
    assert "INSERT INTO audit_log" in sql
    assert params[1] == "POST"  # method
    assert params[2] == "/api/v1/documents/"  # path
    assert params[3] == 200  # status_code
    assert isinstance(params[4], int) and params[4] >= 0  # duration_ms


@pytest.mark.asyncio
async def test_audit_write_on_translate_path() -> None:
    """POST /api/v1/translate/ should trigger a D1 write."""
    mock_db = _make_mock_db()

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        client.post("/api/v1/translate/", headers={"X-GDPR-Consent": "test"})

    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_no_audit_on_health_path() -> None:
    """GET /api/v1/health/ should not trigger any D1 write."""
    mock_db = _make_mock_db()

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/api/v1/health/")

    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_no_audit_on_non_audited_path() -> None:
    """GET /api/v1/other/ is not in AUDIT_PATHS — no D1 write."""
    mock_db = _make_mock_db()

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        # AuditLogMiddleware only handles paths listed in _AUDIT_PATHS
        client.get("/api/v1/other/")

    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_d1_unavailable_does_not_raise() -> None:
    """When D1Client.from_scope returns None, request completes normally."""
    with patch("app.db.d1_client.D1Client.from_scope", return_value=None):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/v1/documents/", headers={"X-GDPR-Consent": "test"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_request_id_hash_is_short() -> None:
    """request_id_hash written to D1 should be 8 hex chars (SHA256[:8])."""
    mock_db = _make_mock_db()

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        client.post(
            "/api/v1/documents/",
            headers={"X-GDPR-Consent": "test", "X-Request-Id": "my-nonce-123"},
        )

    params = mock_db.execute.call_args[0][1]
    request_id_hash: str = params[5]
    assert len(request_id_hash) == 8
    assert all(c in "0123456789abcdef" for c in request_id_hash)
    # Must not be the raw nonce
    assert request_id_hash != "my-nonce-123"


@pytest.mark.asyncio
async def test_mime_type_stripped_of_params() -> None:
    """mime_type stored in D1 should not include charset= or boundary= params."""
    mock_db = _make_mock_db()

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        client.post(
            "/api/v1/documents/",
            headers={
                "X-GDPR-Consent": "test",
                "Content-Type": "multipart/form-data; boundary=----WebKitFormBoundary",
            },
        )

    params = mock_db.execute.call_args[0][1]
    mime_type: str | None = params[6]
    assert mime_type == "multipart/form-data"


@pytest.mark.asyncio
async def test_d1_write_failure_does_not_raise() -> None:
    """If D1 execute() returns False (write failure), the request still completes.

    D1Client.execute() catches all exceptions internally and returns False.
    The middleware must treat a False return as a non-fatal warning, not an error.
    """
    mock_db = _make_mock_db()
    mock_db.execute = AsyncMock(return_value=False)  # D1Client signals failure via False

    with patch("app.db.d1_client.D1Client.from_scope", return_value=mock_db):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/v1/documents/", headers={"X-GDPR-Consent": "test"})

    assert resp.status_code == 200
    mock_db.execute.assert_called_once()
