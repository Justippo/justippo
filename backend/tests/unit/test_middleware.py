"""
Unit Tests — GDPRConsentMiddleware (Sprint 1)

Coverage:
- Requests without X-GDPR-Consent header to protected endpoints → HTTP 451
- Requests with X-GDPR-Consent header → pass through (200)
- Exempt paths (/health, /api/v1/health/*, /api/docs, /api/redoc, /api/openapi.json)
  are always accessible without a consent header
- GDPR_CONSENT_REQUIRED=False disables the gate entirely (dev / CI shortcut)
- Response body on 451 is valid JSON with a "detail" key
- Existing health endpoint tests are not broken by middleware activation

All isolated-app tests use a minimal FastAPI instance — not app.main — so they are
independent of other middleware and router wiring.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.core.config as _config_module
from app.core.middleware import GDPRConsentMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> TestClient:
    """
    Minimal FastAPI app with GDPRConsentMiddleware and two routes:
      GET /protected  — must require consent
      GET /health     — exempt from consent check
    """
    application = FastAPI()
    application.add_middleware(GDPRConsentMiddleware)

    @application.get("/protected")
    async def _protected() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @application.get("/health")
    async def _health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @application.get("/api/v1/health/ready")
    async def _ready() -> JSONResponse:
        return JSONResponse({"status": "ready", "dependencies": {}})

    @application.get("/api/docs")
    async def _docs() -> JSONResponse:
        return JSONResponse({"docs": True})

    return TestClient(application, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# 451 — missing consent header on protected endpoint
# ---------------------------------------------------------------------------


class TestMissingConsentHeader:
    def test_protected_endpoint_returns_451_without_header(self) -> None:
        """Any non-exempt endpoint without X-GDPR-Consent must return 451."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/protected")
        assert resp.status_code == 451

    def test_451_body_is_valid_json_with_detail(self) -> None:
        """Response body must be JSON with a non-empty 'detail' key."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/protected")
        data = resp.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)
        assert len(data["detail"]) > 0

    def test_451_content_type_is_json(self) -> None:
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/protected")
        assert "application/json" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 200 — consent header present
# ---------------------------------------------------------------------------


class TestConsentHeaderPresent:
    def test_protected_endpoint_passes_with_consent_header(self) -> None:
        """Any non-empty X-GDPR-Consent value must pass through."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/protected", headers={"X-GDPR-Consent": "accepted"})
        assert resp.status_code == 200

    def test_sprint1_accepts_any_non_empty_token(self) -> None:
        """Sprint 1 only checks presence, not content — any non-empty value passes."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get(
                "/protected", headers={"X-GDPR-Consent": "some-opaque-token-123"}
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Exempt paths — always pass without consent header
# ---------------------------------------------------------------------------


class TestExemptPaths:
    def test_root_health_exempt(self) -> None:
        """/health must be reachable without consent (Cloudflare liveness probe)."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/health")
        assert resp.status_code == 200

    def test_api_v1_health_ready_exempt(self) -> None:
        """/api/v1/health/ready must be reachable without consent."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/api/v1/health/ready")
        assert resp.status_code == 200

    def test_api_docs_exempt(self) -> None:
        """/api/docs must be reachable without consent."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/api/docs")
        assert resp.status_code == 200

    def test_matrix_oauth_flow_exempt(self) -> None:
        """OAuth redirects must pass the consent layer without a custom header."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", True):
            resp = _make_client().get("/api/v1/auth/matrix/callback")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GDPR_CONSENT_REQUIRED=False — gate disabled entirely
# ---------------------------------------------------------------------------


class TestConsentGateDisabled:
    def test_protected_passes_when_consent_not_required(self) -> None:
        """When GDPR_CONSENT_REQUIRED=False, all requests pass through regardless."""
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", False):
            resp = _make_client().get("/protected")
        assert resp.status_code == 200

    def test_no_451_when_gate_off(self) -> None:
        with patch.object(_config_module.settings, "GDPR_CONSENT_REQUIRED", False):
            resp = _make_client().get("/protected")
        assert resp.status_code != 451


# ---------------------------------------------------------------------------
# Regression — existing health tests must still pass with middleware active
# ---------------------------------------------------------------------------


class TestMainAppHealthRegression:
    """
    Verify that activating GDPRConsentMiddleware in main.py does NOT break
    the existing /health and /api/v1/health/ready endpoints.
    """

    def test_root_health_still_200_on_main_app(self) -> None:
        """GET /health on the real main app must return 200 without consent header."""
        from app.main import app

        resp = TestClient(app).get("/health")
        assert resp.status_code == 200

    def test_v1_health_ready_still_200_on_main_app(self) -> None:
        """GET /api/v1/health/ready on the real main app must return 200 without consent header."""
        from app.main import app

        resp = TestClient(app).get("/api/v1/health/ready")
        assert resp.status_code == 200
