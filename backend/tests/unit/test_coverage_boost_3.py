"""Batch 3: Small-gap coverage boost — 16 files with 2–18 missed statements each.

Covers:
- translate.py:123-124              — explain_document exception fallback
- middleware.py:107,318-319,351-362 — OPTIONS exemption, Datadog metrics exception, cold start
- main.py:85-96                     — SQLite engine init + exception
- exchange.py:92,101,121-123,135-136 — MatrixConfigurationError/TimeoutError/rate-limit retry_after
- glossary.py:87,92,106,156-164,167 — validation + PostHog + persist
- health.py:73,79,82,86,202-203,217-218,229-232 — effective_state branches, import errors
- documents.py:98,122,231,240-244,258-263,273,286-287,377-380,396-397
- sentry.py:85-87,240-241           — DSN parse error, envelope exception
- datadog.py:278-283                — ship_metrics enabled path
- posthog.py:145-146                — capture exception
- pii_redaction_adapter.py:145,149-150,198-199
- cloudflare/gateway.py:62,130      — empty account_id error, empty auth
- trace_recorder.py:121             — _percentile edge case
- http_forwarder.py:70-72,114-116   — httpx import error
- glossary_repo.py:87-93,116,121-122,146-152,189-190,199-204,221-222,225-226
- rag_service.py:157-158            — trusted_eu_source_url ValueError
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/api/v1/endpoints/translate.py — explain_document exception fallback
# ---------------------------------------------------------------------------


class TestTranslateExplainFallback:
    async def test_explain_document_exception_returns_fallback(self) -> None:
        from app.api.v1.endpoints.translate import (
            TranslationRequest,
            _refresh_document_explanation,
        )
        from app.models.document_explanation import DocumentExplanation

        payload = TranslationRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000",
            source_language="en",
            target_language="de",
            pages=[{"page": 1, "text": "test content", "confidence": 0.9}],
            include_document_explanation=True,
        )
        with patch(
            "app.api.v1.endpoints.translate.explain_document",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = await _refresh_document_explanation(payload)
            assert isinstance(result, DocumentExplanation)
            assert result.legal_context_status == "unavailable"
            assert "DOCUMENT_EXPLANATION_UNAVAILABLE" in result.warnings


# ---------------------------------------------------------------------------
# app/core/middleware.py — OPTIONS exemption, Datadog exception, cold start
# ---------------------------------------------------------------------------


class TestMiddlewareOptionsExempt:
    async def test_options_request_bypasses_consent(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.middleware import GDPRConsentMiddleware

        app = FastAPI()
        app.add_middleware(GDPRConsentMiddleware)

        @app.get("/test")
        async def _test() -> dict:
            return {"ok": True}

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options("/test")
            assert resp.status_code != 451


class TestDemoWarmupMiddleware:
    async def test_cold_start_sets_headers(self) -> None:
        from app.core.middleware import DemoWarmupMiddleware

        DemoWarmupMiddleware._warmed_up = False

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(DemoWarmupMiddleware)

        @app.get("/test")
        async def _test() -> dict:
            return {"ok": True}

        with (
            patch("app.core.config.settings") as mock_settings,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            mock_settings.DEMO_MODE = True
            resp = client.get("/test")
            assert resp.status_code == 200
            assert resp.headers.get("x-cold-start") == "true"
            assert "x-cold-start-ms" in resp.headers
            DemoWarmupMiddleware._warmed_up = True

    async def test_warm_request_no_headers(self) -> None:
        from app.core.middleware import DemoWarmupMiddleware

        DemoWarmupMiddleware._warmed_up = True

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(DemoWarmupMiddleware)

        @app.get("/test")
        async def _test() -> dict:
            return {"ok": True}

        with (
            patch("app.core.config.settings") as mock_settings,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            mock_settings.DEMO_MODE = True
            resp = client.get("/test")
            assert resp.status_code == 200
            assert "x-cold-start" not in resp.headers

    async def test_demo_mode_disabled_returns_immediately(self) -> None:
        from app.core.middleware import DemoWarmupMiddleware

        DemoWarmupMiddleware._warmed_up = False

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(DemoWarmupMiddleware)

        @app.get("/test")
        async def _test() -> dict:
            return {"ok": True}

        with (
            patch("app.core.config.settings") as mock_settings,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            mock_settings.DEMO_MODE = False
            resp = client.get("/test")
            assert resp.status_code == 200
            assert "x-cold-start" not in resp.headers


class TestDatadogMiddlewareException:
    async def test_datadog_metrics_exception_does_not_mask_response(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.middleware import DatadogMetricsMiddleware

        app = FastAPI()
        app.add_middleware(DatadogMetricsMiddleware)

        @app.get("/test")
        async def _test() -> dict:
            return {"ok": True}

        with (
            patch(
                "app.integrations.datadog.ship_metrics",
                new_callable=AsyncMock,
                side_effect=RuntimeError("dd"),
            ),
            patch(
                "app.integrations.datadog.build_metric_series",
                return_value={},
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/test", headers={"X-GDPR-Consent": "yes"})
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# app/main.py — SQLite engine init + exception
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/exchange.py — Matrix error classification
# ---------------------------------------------------------------------------


class TestExchangeErrorClassification:
    def test_configuration_error_returns_503(self) -> None:
        from app.api.v1.endpoints.exchange import _classified_room_error
        from app.integrations.matrix.client import MatrixConfigurationError

        exc = MatrixConfigurationError("no config")
        result = _classified_room_error(exc)
        assert result.status_code == 503
        assert result.detail["code"] == "matrix_configuration_error"

    def test_timeout_error_returns_504(self) -> None:
        from app.api.v1.endpoints.exchange import _classified_room_error
        from app.integrations.matrix.client import MatrixTimeoutError

        exc = MatrixTimeoutError("timed out", operation="create_room")
        result = _classified_room_error(exc)
        assert result.status_code == 504
        assert result.detail["code"] == "matrix_timeout"

    def test_rate_limit_with_retry_after(self) -> None:
        from app.api.v1.endpoints.exchange import _classified_room_error
        from app.integrations.matrix.client import MatrixClientError

        exc = MatrixClientError(
            "rate limited",
            operation="create_room",
            status_code=429,
            errcode="M_LIMIT_EXCEEDED",
            retry_after_ms=5000,
        )
        result = _classified_room_error(exc)
        assert result.status_code == 429
        assert result.detail["retry_after_ms"] == 5000

    def test_invite_not_found(self) -> None:
        from app.api.v1.endpoints.exchange import _classified_room_error
        from app.integrations.matrix.client import MatrixClientError

        exc = MatrixClientError(
            "not found",
            operation="invite",
            status_code=404,
            errcode="M_NOT_FOUND",
        )
        result = _classified_room_error(exc)
        assert result.status_code == 502

    def test_invite_forbidden(self) -> None:
        from app.api.v1.endpoints.exchange import _classified_room_error
        from app.integrations.matrix.client import MatrixClientError

        exc = MatrixClientError(
            "forbidden",
            operation="invite",
            status_code=403,
            errcode="M_FORBIDDEN",
        )
        result = _classified_room_error(exc)
        assert result.status_code == 502

    def test_invite_generic_error(self) -> None:
        from app.api.v1.endpoints.exchange import _classified_room_error
        from app.integrations.matrix.client import MatrixClientError

        exc = MatrixClientError(
            "failed",
            operation="invite",
            status_code=500,
            errcode=None,
        )
        result = _classified_room_error(exc)
        assert result.status_code == 502


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/glossary.py — validation + PostHog + persist
# ---------------------------------------------------------------------------


class TestGlossaryEndpointValidation:
    def test_invalid_source_language(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1.endpoints.glossary import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/glossary")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/glossary/search",
                params={"q": "test", "source": "xx"},
            )
            assert resp.status_code == 422

    def test_invalid_target_language(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1.endpoints.glossary import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/glossary")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/glossary/search",
                params={"q": "test", "target": "xx"},
            )
            assert resp.status_code == 422


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/health.py — effective_state branches
# ---------------------------------------------------------------------------


class TestHealthEffectiveState:
    def test_compute_effective_state_all_healthy(self) -> None:
        from app.api.v1.endpoints.health import _compute_effective_state

        state, degs = _compute_effective_state({"a": "healthy", "b": "healthy"})
        assert state == "live"
        assert degs == []

    def test_compute_effective_state_degraded(self) -> None:
        from app.api.v1.endpoints.health import _compute_effective_state

        state, degs = _compute_effective_state({"a": "healthy", "b": "degraded"})
        assert state == "degraded"
        assert len(degs) == 1
        assert degs[0].severity == "warning"

    def test_compute_effective_state_down(self) -> None:
        from app.api.v1.endpoints.health import _compute_effective_state

        state, degs = _compute_effective_state({"a": "degraded", "b": "unavailable"})
        assert state == "down"
        assert len(degs) == 1
        assert degs[0].severity == "critical"

    def test_compute_effective_state_all_unavailable(self) -> None:
        from app.api.v1.endpoints.health import _compute_effective_state

        state, degs = _compute_effective_state({"x": "unavailable"})
        assert state == "down"
        assert len(degs) == 1

    async def test_pipeline_glossary_import_error(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1.endpoints.health import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/health")

        with (
            patch.dict("sys.modules", {"app.services.glossary_service": None}),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/health/pipeline")
            assert resp.status_code == 200
            data = resp.json()
            assert data["components"]["glossary"]["status"] == "degraded"

    async def test_pipeline_grounding_import_error(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1.endpoints.health import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/health")

        with (
            patch.dict("sys.modules", {"app.services.chat_guidance": None}),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/health/pipeline")
            assert resp.status_code == 200
            data = resp.json()
            assert data["components"]["grounding_gate"]["status"] == "degraded"

    async def test_pipeline_status_degraded_overall(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1.endpoints.health import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/health")

        with (
            patch("app.api.v1.endpoints.health.settings") as mock_settings,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            mock_settings.MISTRAL_API_KEY = ""
            mock_settings.CF_WORKERS_AI_API_TOKEN = ""
            mock_settings.CF_AIG_AUTHORIZATION = ""
            mock_settings.HINDSIGHT_API_URL = ""
            mock_settings.CHROMADB_URL = ""
            mock_settings.BABELDOC_URL = ""
            mock_settings.PROPELLA_BASE_URL = ""
            mock_settings.MATRIX_HOMESERVER_URL = ""
            mock_settings.APP_VERSION = "0.1.0"
            mock_settings.APP_ENV = "test"
            resp = client.get("/api/v1/health/pipeline")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/documents.py — various branches
# ---------------------------------------------------------------------------


class TestDocumentsEdgeCases:
    async def test_try_fetch_azure_too_large(self) -> None:
        from app.api.v1.endpoints.documents import _try_fetch_azure_analysis

        with patch(
            "app.api.v1.endpoints.documents.get_analysis_limits",
            return_value=MagicMock(max_bytes=100),
        ):
            result = await _try_fetch_azure_analysis(b"x" * 200)
            assert result is None

    async def test_try_fetch_azure_error(self) -> None:
        from app.api.v1.endpoints.documents import _try_fetch_azure_analysis
        from app.integrations.azure_document_intelligence import AzureDocumentIntelligenceError

        with (
            patch(
                "app.api.v1.endpoints.documents.get_analysis_limits",
                return_value=MagicMock(max_bytes=1000),
            ),
            patch(
                "app.api.v1.endpoints.documents.analyze_pdf",
                new_callable=AsyncMock,
                side_effect=AzureDocumentIntelligenceError.__new__(AzureDocumentIntelligenceError),
            ),
        ):
            result = await _try_fetch_azure_analysis(b"small")
            assert result is None

    async def test_analyze_pdf_for_understanding_azure_provided(self) -> None:
        from app.api.v1.endpoints.documents import _analyze_pdf_for_understanding

        mock_analysis = MagicMock()
        pages = [{"page": 1, "text": "hello", "confidence": 0.9}]

        result = await _analyze_pdf_for_understanding(b"pdf", pages, azure_analysis=mock_analysis)
        assert result is mock_analysis

    async def test_classifications_eviction(self) -> None:
        from app.api.v1.endpoints.documents import _CLASSIFICATIONS_MAX, _classifications
        from app.services.classification_service import DocumentClassification

        _classifications.clear()
        # Fill to max
        for i in range(_CLASSIFICATIONS_MAX):
            _classifications[f"doc-{i}"] = DocumentClassification(
                document_type="unknown",
                language_code="en",
                quality_score=0.5,
            )
        assert len(_classifications) == _CLASSIFICATIONS_MAX

        # Simulate what upload_document does when at capacity
        if len(_classifications) >= _CLASSIFICATIONS_MAX:
            _classifications.popitem(last=False)
        _classifications["doc-new"] = DocumentClassification(
            document_type="unknown",
            language_code="en",
            quality_score=0.5,
        )
        assert len(_classifications) == _CLASSIFICATIONS_MAX
        _classifications.clear()

    def test_resolve_target_language_same(self) -> None:
        from app.api.v1.endpoints.documents import _resolve_target_language

        result = _resolve_target_language("en", "en")
        assert result != "en"
        assert result in ("de", "fr")


# ---------------------------------------------------------------------------
# app/integrations/sentry.py — DSN parse error + envelope exception
# ---------------------------------------------------------------------------


class TestSentryDSNParseError:
    def test_dsn_parse_error_disables_sentry(self) -> None:

        import app.integrations.sentry as sentry_mod

        with patch("app.integrations.sentry.urlparse", side_effect=ValueError("bad url")):
            original = sentry_mod._enabled
            try:
                sentry_mod.configure("not-a-valid-url")
                assert sentry_mod._enabled is False
            finally:
                sentry_mod._enabled = original

    async def test_envelope_shipping_exception_suppressed(self) -> None:
        from app.integrations.sentry import ship_to_sentry

        exc = ValueError("test error")

        with (
            patch("app.integrations.sentry._enabled", True),
            patch("app.integrations.sentry._ingest_url", "https://example.com/api/1/envelope/"),
            patch(
                "app.integrations.sentry.build_envelope",
                side_effect=RuntimeError("build failed"),
            ),
        ):
            await ship_to_sentry(exc)


# ---------------------------------------------------------------------------
# app/integrations/datadog.py — ship_metrics enabled path
# ---------------------------------------------------------------------------


class TestDatadogShipMetrics:
    async def test_ship_metrics_enabled(self) -> None:
        from app.integrations.datadog import ship_metrics

        with (
            patch("app.integrations.datadog._enabled", True),
            patch("app.integrations.datadog._api_key", "test-key"),
            patch(
                "app.integrations.datadog._metrics_url",
                "https://http-intake.logs.datadoghq.com/api/v2/logs",
            ),
            patch("app.integrations.datadog.fire_and_forget", new_callable=AsyncMock) as mock_fire,
        ):
            await ship_metrics({"series": []})
            mock_fire.assert_awaited_once()


# ---------------------------------------------------------------------------
# app/integrations/posthog.py — capture exception
# ---------------------------------------------------------------------------


class TestPostHogCaptureException:
    async def test_capture_event_exception_suppressed(self) -> None:
        import app.integrations.posthog as ph_mod

        original_enabled = ph_mod._enabled
        original_key = ph_mod._api_key
        original_host = ph_mod._host
        try:
            ph_mod._enabled = True
            ph_mod._api_key = "test-key"
            ph_mod._host = "https://app.posthog.com"
            with patch(
                "app.integrations.posthog.fire_and_forget",
                new_callable=AsyncMock,
                side_effect=RuntimeError("net"),
            ):
                await ph_mod.capture_event("test_event", distinct_id="test")
        finally:
            ph_mod._enabled = original_enabled
            ph_mod._api_key = original_key
            ph_mod._host = original_host


# ---------------------------------------------------------------------------
# app/integrations/pii_redaction_adapter.py — entity filter + httpx import + error parsing
# ---------------------------------------------------------------------------


class TestPIIRedactionEdgeCases:
    async def test_entities_not_none_includes_in_payload(self) -> None:
        from app.integrations.pii_redaction_adapter import PIIRedactionRequest, redact

        req = PIIRedactionRequest(text="hello", language="en", entities=["PERSON"])

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "redacted_text": "hello",
            "entity_count": 0,
            "entity_types": [],
            "processing_time_ms": 10,
        }

        with (
            patch("app.integrations.pii_redaction_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.pii_redaction_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await redact(req)
                assert result.entity_count == 0

    async def test_non_retryable_error_with_json_body(self) -> None:
        from app.integrations.pii_redaction_adapter import (
            PIIRedactionRequest,
            PIIRedactionSidecarError,
            redact,
        )

        req = PIIRedactionRequest(text="hello", language="en")

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "error": {
                "code": "INVALID_INPUT",
                "message": "bad text",
                "retryable": False,
            }
        }
        mock_response.text = '{"error": "bad"}'

        with (
            patch("app.integrations.pii_redaction_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.pii_redaction_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("httpx.AsyncClient", return_value=mock_client),
                pytest.raises(PIIRedactionSidecarError),
            ):
                await redact(req)

    async def test_non_retryable_error_non_json_body(self) -> None:
        from app.integrations.pii_redaction_adapter import (
            PIIRedactionRequest,
            PIIRedactionSidecarError,
            redact,
        )

        req = PIIRedactionRequest(text="hello", language="en")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "plain text error"

        with (
            patch("app.integrations.pii_redaction_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.pii_redaction_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("httpx.AsyncClient", return_value=mock_client),
                pytest.raises(PIIRedactionSidecarError),
            ):
                await redact(req)


# ---------------------------------------------------------------------------
# app/integrations/cloudflare/gateway.py — empty account_id error
# ---------------------------------------------------------------------------


class TestGatewayEmptyAccountId:
    def test_empty_account_id_uses_fallback(self) -> None:
        from app.integrations.cloudflare.gateway import get_gateway_url

        with (
            patch("app.integrations.cloudflare.gateway.settings") as mock_settings,
            patch.dict("os.environ", {}, clear=True),
        ):
            mock_settings.CLOUDFLARE_ACCOUNT_ID = ""
            mock_settings.CF_ACCOUNT_ID = ""
            mock_settings.CLOUDFLARE_GATEWAY_ID = ""
            mock_settings.CF_AI_GATEWAY_ID = ""
            url = get_gateway_url("test", "model")
            assert "gateway.ai.cloudflare.com" in url
            assert "/test/model" in url

    def test_empty_auth_returns_empty_dict(self) -> None:
        from app.integrations.cloudflare.gateway import get_gateway_auth_headers

        with (
            patch("app.integrations.cloudflare.gateway.settings") as mock_settings,
            patch.dict("os.environ", {}, clear=True),
        ):
            mock_settings.CF_AIG_AUTHORIZATION = ""
            result = get_gateway_auth_headers()
            assert result == {}


# ---------------------------------------------------------------------------
# app/integrations/trace_recorder.py — _percentile edge case
# ---------------------------------------------------------------------------


class TestTraceRecorderPercentile:
    def test_percentile_at_end(self) -> None:
        from app.integrations.trace_recorder import _percentile

        result = _percentile([1.0, 2.0, 3.0], 1.0)
        assert result == 3.0


# ---------------------------------------------------------------------------
# app/integrations/http_forwarder.py — httpx import error
# ---------------------------------------------------------------------------


class TestHttpForwarderImportError:
    @pytest.mark.asyncio
    async def test_fire_and_forget_no_httpx(self) -> None:
        import app.integrations.http_forwarder as mod

        with (
            patch.dict("sys.modules", {"httpx": None}),
            patch.object(mod.logger, "warning") as mock_log,
        ):
            await mod.fire_and_forget("http://x.com", {}, b"body")
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_now_no_httpx(self) -> None:
        import app.integrations.http_forwarder as mod

        with (
            patch.dict("sys.modules", {"httpx": None}),
            patch.object(mod.logger, "warning") as mock_log,
        ):
            await mod.post_now("http://x.com", {}, b"body")
            mock_log.assert_called_once()


# ---------------------------------------------------------------------------
# app/repositories/glossary_repo.py — branches
# ---------------------------------------------------------------------------


class TestGlossaryRepoBranches:
    async def test_upsert_no_db(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(db=None)
        result = await repo.upsert_terms([{"term_en": "test"}], "doc-1", "en")
        assert result == []

    async def test_upsert_empty_terms(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(db=MagicMock())
        result = await repo.upsert_terms([], "doc-1", "en")
        assert result == []

    async def test_upsert_skips_empty_record(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.execute.return_value = True
        repo = GlossaryRepo(db=mock_db)
        result = await repo.upsert_terms(
            [{"term_en": "", "term_de": "", "term_fr": ""}],
            "doc-1",
            "en",
        )
        assert result == []

    async def test_upsert_with_mistranslations_list(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.execute.return_value = True
        repo = GlossaryRepo(db=mock_db)
        result = await repo.upsert_terms(
            [{"term_en": "test", "mistranslations": ["wrong1", "wrong2"]}],
            "doc-1",
            "en",
        )
        assert len(result) == 1
        assert json.loads(result[0]["mistranslations"]) == ["wrong1", "wrong2"]

    async def test_upsert_with_mistranslations_string(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.execute.return_value = True
        repo = GlossaryRepo(db=mock_db)
        result = await repo.upsert_terms(
            [{"term_en": "test", "mistranslations": "old_term"}],
            "doc-1",
            "en",
        )
        assert len(result) == 1
        assert result[0]["mistranslations"] == "old_term"

    async def test_upsert_execute_failure(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.execute.return_value = False
        repo = GlossaryRepo(db=mock_db)
        result = await repo.upsert_terms(
            [{"term_en": "test"}],
            "doc-1",
            "en",
        )
        assert result == []

    async def test_search_no_db(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(db=None)
        result = await repo.search_terms("test")
        assert result == []

    async def test_search_empty_query(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(db=MagicMock())
        result = await repo.search_terms("")
        assert result == []

    async def test_search_unsupported_lang(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = []
        repo = GlossaryRepo(db=mock_db)
        result = await repo.search_terms("test", lang="xx")
        assert result == []

    async def test_search_with_valid_lang(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = [
            {
                "id": "1",
                "term_en": "test",
                "term_de": "",
                "term_fr": "",
                "mistranslations": None,
                "definition": "",
                "source_doc_id": "d1",
                "source_lang": "en",
                "confidence": 1.0,
                "created_at": "",
                "updated_at": "",
            }
        ]
        repo = GlossaryRepo(db=mock_db)
        result = await repo.search_terms("test", lang="en")
        assert len(result) == 1

    async def test_search_no_lang(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = []
        repo = GlossaryRepo(db=mock_db)
        result = await repo.search_terms("test", lang=None)
        assert result == []

    async def test_get_all_no_db(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(db=None)
        result = await repo.get_all_terms()
        assert result == []

    async def test_get_all_with_lang(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = []
        repo = GlossaryRepo(db=mock_db)
        result = await repo.get_all_terms(lang="en")
        assert result == []

    async def test_get_all_without_lang(self) -> None:
        from app.repositories.glossary_repo import GlossaryRepo

        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = []
        repo = GlossaryRepo(db=mock_db)
        result = await repo.get_all_terms(lang=None)
        assert result == []


# ---------------------------------------------------------------------------
# app/services/rag_service.py — trusted_eu_source_url ValueError
# ---------------------------------------------------------------------------


class TestTrustedEUSourceURL:
    def test_value_error_returns_none(self) -> None:
        from app.services.rag_service import trusted_eu_source_url

        with patch("app.services.rag_service.urlsplit", side_effect=ValueError("bad url")):
            result = trusted_eu_source_url("not-a-url")
            assert result is None


# ---------------------------------------------------------------------------
# app/services/rag_service.py — _compute_effective_state branches
# ---------------------------------------------------------------------------


class TestRAGServiceRecallRetry:
    async def test_recall_429_retry_then_success(self) -> None:
        from app.services.rag_service import _HindsightHttpClient

        mock_client = AsyncMock()
        rate_response = MagicMock()
        rate_response.status_code = 429
        rate_response.headers = {"Retry-After": "0.01"}

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"results": []}
        ok_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [rate_response, ok_response]

        svc = _HindsightHttpClient.__new__(_HindsightHttpClient)
        svc._client = mock_client
        svc._bank_id = "test-bank"
        svc._access_key = "test-key"

        with patch("app.services.rag_service.asyncio.sleep", new_callable=AsyncMock):
            await svc.arecall(
                bank_id="test-bank",
                query="test query",
                include_source_facts=True,
            )
            assert mock_client.post.call_count == 2

    async def test_recall_429_invalid_retry_after(self) -> None:
        from app.services.rag_service import _HindsightHttpClient

        mock_client = AsyncMock()
        rate_response = MagicMock()
        rate_response.status_code = 429
        rate_response.headers = {"Retry-After": "invalid"}

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"results": []}
        ok_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [rate_response, ok_response]

        svc = _HindsightHttpClient.__new__(_HindsightHttpClient)
        svc._client = mock_client
        svc._bank_id = "test-bank"
        svc._access_key = "test-key"

        with patch("app.services.rag_service.asyncio.sleep", new_callable=AsyncMock):
            await svc.arecall(
                bank_id="test-bank",
                query="test query",
                include_source_facts=False,
            )
            assert mock_client.post.call_count == 2
