"""
Unit tests for demo pipeline stabilization:
- Pipeline health endpoint
- DemoWarmupMiddleware cold-start detection
- Translation service demo truncation
"""

from unittest.mock import patch

from starlette.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-GDPR-Consent": "test"})


# ---------------------------------------------------------------------------
# B. Pipeline health endpoint
# ---------------------------------------------------------------------------


class TestPipelineHealth:
    def test_pipeline_returns_200(self) -> None:
        resp = client.get("/api/v1/health/pipeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert "components" in data
        assert "version" in data
        assert "environment" in data

    def test_pipeline_has_all_components(self) -> None:
        resp = client.get("/api/v1/health/pipeline")
        data = resp.json()
        components = data["components"]
        assert "ocr" in components
        assert "translation" in components
        assert "hindsight_rag" in components
        assert "chromadb" in components
        assert "babeldoc" in components
        assert "propella_classifier" in components
        assert "matrix_synapse" in components
        assert "glossary" in components
        assert "grounding_gate" in components

    def test_pipeline_component_shape(self) -> None:
        resp = client.get("/api/v1/health/pipeline")
        data = resp.json()
        for name, comp in data["components"].items():
            assert "status" in comp, f"{name} missing status"
            assert "last_check_ms" in comp, f"{name} missing last_check_ms"
            assert comp["status"] in ("healthy", "degraded", "unavailable")


# ---------------------------------------------------------------------------
# C. DemoWarmupMiddleware
# ---------------------------------------------------------------------------


class TestDemoWarmupMiddleware:
    def test_no_cold_start_header_when_demo_mode_off(self) -> None:
        """Default: DEMO_MODE=false → no X-Cold-Start header."""
        resp = client.get("/api/v1/health/")
        assert "X-Cold-Start" not in resp.headers

    def test_cold_start_header_when_demo_mode_on(self) -> None:
        """DEMO_MODE=true → first request gets X-Cold-Start: true."""
        from app.core.middleware import DemoWarmupMiddleware

        # Reset warmed state
        DemoWarmupMiddleware._warmed_up = False

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.DEMO_MODE = True
            mock_settings.GDPR_CONSENT_REQUIRED = False
            mock_settings.APP_VERSION = "0.1.0"
            mock_settings.APP_ENV = "test"
            mock_settings.ALLOWED_ORIGINS = ["*"]
            mock_settings.AUDIT_LOG_ENABLED = False
            mock_settings.DATADOG_API_KEY = ""
            mock_settings.SENTRY_DSN = ""
            mock_settings.MISTRAL_API_KEY = "test"
            mock_settings.CF_WORKERS_AI_API_TOKEN = "test"
            mock_settings.CF_AIG_AUTHORIZATION = ""
            mock_settings.VECTOR_DB_PROVIDER = "chromadb"
            resp = client.get("/api/v1/health/")
            assert resp.status_code == 200
            assert resp.headers.get("X-Cold-Start") == "true"

        # Reset for other tests
        DemoWarmupMiddleware._warmed_up = False

    def test_subsequent_requests_not_cold_start(self) -> None:
        """After warm-up, no X-Cold-Start header."""
        from app.core.middleware import DemoWarmupMiddleware

        DemoWarmupMiddleware._warmed_up = True
        resp = client.get("/api/v1/health/")
        assert "X-Cold-Start" not in resp.headers
        # Reset
        DemoWarmupMiddleware._warmed_up = False


# ---------------------------------------------------------------------------
# D. Translation demo truncation
# ---------------------------------------------------------------------------
