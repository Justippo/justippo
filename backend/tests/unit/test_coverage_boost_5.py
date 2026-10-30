"""Batch 5: Medium-gap coverage boost — langfuse, laminar, matrix client, pdf ref translation, search.

Covers:
- langfuse.py — configure no-op, _strip_pii_langfuse, trace context manager, log_generation, log_score
- laminar.py — configure no-op, _strip_pii, observe decorator, LaminarMiddleware
- matrix/client.py — __init__ validation, _with_retry, check_health, create_secure_room
- pdf_reference_translation_service.py — validation helpers, error mapping
- search.py — _request_id, SearchRequest validation
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/integrations/langfuse.py
# ---------------------------------------------------------------------------


class TestLangfuseConfigure:
    def test_configure_disabled(self) -> None:
        import app.integrations.langfuse as mod

        mod.configure("pk", "sk", "http://localhost", enabled=False)
        assert mod._enabled is False

    def test_configure_no_public_key(self) -> None:
        import app.integrations.langfuse as mod

        mod.configure("", "sk", "http://localhost", enabled=True)
        assert mod._enabled is False

    def test_configure_no_secret_key(self) -> None:
        import app.integrations.langfuse as mod

        mod.configure("pk", "", "http://localhost", enabled=True)
        assert mod._enabled is False

    def test_configure_enabled(self) -> None:
        import app.integrations.langfuse as mod

        mod.configure("pk", "sk", "http://localhost", enabled=True, service_name="test")
        assert mod._enabled is True
        assert mod._service_name == "test"
        mod._enabled = False


class TestLangfuseStripPII:
    def test_strip_pii_passthrough_when_enabled(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import _strip_pii_langfuse

        mod._send_prompt_content = True
        attrs = {"gen_ai.prompt": "secret", "gen_ai.completion": "result"}
        result = _strip_pii_langfuse(attrs)
        assert result == attrs
        mod._send_prompt_content = False

    def test_strip_pii_removes_content_keys(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import _strip_pii_langfuse

        mod._send_prompt_content = False
        attrs = {
            "gen_ai.prompt": "secret",
            "langfuse.observation.input": "data",
            "other": "keep",
        }
        result = _strip_pii_langfuse(attrs)
        assert "gen_ai.prompt" not in result
        assert "langfuse.observation.input" not in result
        assert result["other"] == "keep"


class TestLangfuseTrace:
    async def test_trace_disabled(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import trace as langfuse_trace

        mod._enabled = False
        async with langfuse_trace("test") as tid:
            assert tid == ""
        mod._enabled = False

    async def test_trace_enabled(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import trace as langfuse_trace

        mod._enabled = True
        mod._send_spans = AsyncMock()
        async with langfuse_trace("test-op") as tid:
            assert isinstance(tid, str)
            assert len(tid) > 0
        mod._enabled = False


class TestLangfuseLogGeneration:
    async def test_log_generation_disabled(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import log_generation

        mod._enabled = False
        await log_generation("trace-123", "model", {}, {}, 100.0)

    async def test_log_generation_no_trace(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import log_generation

        mod._enabled = True
        await log_generation("", "model", {}, {}, 100.0)
        mod._enabled = False

    async def test_log_generation_with_usage(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import log_generation

        mod._enabled = True
        mod._send_to_langfuse = AsyncMock()
        await log_generation(
            "trace-123",
            "model",
            {"text": "input"},
            {"text": "output"},
            100.0,
            usage={"input_tokens": 10, "output_tokens": 20},
        )
        mod._send_to_langfuse.assert_called_once()
        mod._enabled = False


class TestLangfuseLogScore:
    async def test_log_score_disabled(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import log_score

        mod._enabled = False
        await log_score("trace-123", "quality", 0.9)

    async def test_log_score_no_trace(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import log_score

        mod._enabled = True
        await log_score("", "quality", 0.9)
        mod._enabled = False

    async def test_log_score_with_comment(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import log_score

        mod._enabled = True
        mod._send_to_langfuse = AsyncMock()
        await log_score("trace-123", "quality", 0.9, comment="good")
        mod._send_to_langfuse.assert_called_once()
        mod._enabled = False


class TestLangfuseBasicAuth:
    def test_build_basic_auth(self) -> None:
        import app.integrations.langfuse as mod
        from app.integrations.langfuse import _build_basic_auth

        mod._public_key = "pk"
        mod._secret_key = "sk"
        result = _build_basic_auth()
        assert result.startswith("Basic ")
        decoded = base64.b64decode(result[6:]).decode()
        assert "pk:sk" in decoded


# ---------------------------------------------------------------------------
# app/integrations/laminar.py
# ---------------------------------------------------------------------------


class TestLaminarConfigure:
    def test_configure_disabled(self) -> None:
        import app.integrations.laminar as mod

        mod.configure("key", "http://localhost", enabled=False)
        assert mod._enabled is False

    def test_configure_no_key(self) -> None:
        import app.integrations.laminar as mod

        mod.configure("", "http://localhost", enabled=True)
        assert mod._enabled is False

    def test_configure_enabled(self) -> None:
        import app.integrations.laminar as mod

        mod.configure("key", "http://localhost", enabled=True, service_name="test-svc")
        assert mod._enabled is True
        assert mod._service_name == "test-svc"
        mod._enabled = False


class TestLaminarStripPII:
    def test_strip_pii_passthrough(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import _strip_pii

        mod._send_prompt_content = True
        attrs = {"content": "secret", "other": "keep"}
        result = _strip_pii(attrs)
        assert result == attrs
        mod._send_prompt_content = False

    def test_strip_pii_removes_content(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import _strip_pii

        mod._send_prompt_content = False
        attrs = {
            "content": "secret",
            "text": "data",
            "llm.input.messages": [{"role": "user", "content": "hi"}],
            "other": "keep",
        }
        result = _strip_pii(attrs)
        assert "content" not in result
        assert "text" not in result
        assert "other" in result


class TestLaminarSendSpans:
    async def test_send_spans_disabled(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import _send_spans

        mod._enabled = False
        await _send_spans([{"name": "test"}])

    async def test_send_spans_empty(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import _send_spans

        mod._enabled = True
        await _send_spans([])
        mod._enabled = False

    async def test_send_spans_sample_rate(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import _send_spans

        mod._enabled = True
        mod._sample_rate = 0.0
        with patch("app.integrations.laminar.fire_and_forget", new_callable=AsyncMock):
            await _send_spans([{"name": "test"}])
        mod._enabled = False
        mod._sample_rate = 1.0


class TestLaminarObserve:
    async def test_observe_disabled(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import observe

        mod._enabled = False

        @observe("test-span")
        async def my_func() -> str:
            return "hello"

        result = await my_func()
        assert result == "hello"

    async def test_observe_enabled(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import observe

        mod._enabled = True
        mod._send_spans = AsyncMock()

        @observe("test-span")
        async def my_func() -> str:
            return "hello"

        result = await my_func()
        assert result == "hello"
        mod._send_spans.assert_called_once()
        mod._enabled = False

    async def test_observe_exception(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import observe

        mod._enabled = True
        mod._send_spans = AsyncMock()

        @observe("test-span")
        async def my_func() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await my_func()
        mod._send_spans.assert_called_once()
        mod._enabled = False


class TestLaminarMiddleware:
    async def test_middleware_disabled(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import LaminarMiddleware

        mod._enabled = False
        mock_app = AsyncMock()
        middleware = LaminarMiddleware(mock_app)
        send = AsyncMock()
        await middleware({"type": "http", "path": "/api/test"}, MagicMock(), send)
        mock_app.assert_called_once()

    async def test_middleware_health_path(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import LaminarMiddleware

        mod._enabled = True
        mock_app = AsyncMock()
        middleware = LaminarMiddleware(mock_app)
        send = AsyncMock()
        await middleware({"type": "http", "path": "/api/v1/health/"}, MagicMock(), send)
        mock_app.assert_called_once()
        mod._enabled = False

    async def test_middleware_non_http(self) -> None:
        import app.integrations.laminar as mod
        from app.integrations.laminar import LaminarMiddleware

        mod._enabled = True
        mock_app = AsyncMock()
        middleware = LaminarMiddleware(mock_app)
        send = AsyncMock()
        await middleware({"type": "websocket"}, MagicMock(), send)
        mock_app.assert_called_once()
        mod._enabled = False


# ---------------------------------------------------------------------------
# app/integrations/matrix/client.py
# ---------------------------------------------------------------------------


class TestMatrixClientInit:
    def test_placeholder_token(self) -> None:
        from app.integrations.matrix.client import MatrixClient, MatrixConfigurationError

        with pytest.raises(MatrixConfigurationError):
            MatrixClient(
                access_token="YOUR_ACCESS_TOKEN",
                base_url="https://matrix.example.com",
                device_id="D1",
            )

    def test_non_https_url(self) -> None:
        from app.integrations.matrix.client import MatrixClient, MatrixConfigurationError

        with pytest.raises(MatrixConfigurationError):
            MatrixClient(
                access_token="valid-token",
                base_url="http://matrix.example.com",
                device_id="D1",
            )

    def test_valid_init(self) -> None:
        from app.integrations.matrix.client import MatrixClient

        client = MatrixClient(
            access_token="valid-token",
            base_url="https://matrix.example.com",
            device_id="D1",
        )
        assert client._token == "valid-token"
        assert client._base_url == "https://matrix.example.com"


class TestMatrixClientHealth:
    async def test_check_health_timeout(self) -> None:
        import httpx

        from app.integrations.matrix.client import MatrixClient, MatrixTimeoutError

        client = MatrixClient(
            access_token="tok",
            base_url="https://matrix.example.com",
            device_id="D1",
        )
        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.TimeoutException("timeout")
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_http),
            pytest.raises(MatrixTimeoutError),
        ):
            await client.check_health()

    async def test_check_health_success(self) -> None:
        from app.integrations.matrix.client import MatrixClient

        client = MatrixClient(
            access_token="tok",
            base_url="https://matrix.example.com",
            device_id="D1",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "versions": ["v1.1"],
            "unstable_features": {"org.matrix.msc3504": True},
        }

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await client.check_health()
            assert result["status"] == "healthy"
            assert result["connectivity"] == "ok"


class TestMatrixClientRetry:
    async def test_retry_on_5xx(self) -> None:
        from app.integrations.matrix.client import MatrixClient

        client = MatrixClient(
            access_token="tok",
            base_url="https://matrix.example.com",
            device_id="D1",
        )

        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        error_response.headers = {}

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {
            "room_id": "!test:example.com",
            "unstable_features": {},
        }

        call_count = 0

        async def mock_post(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return error_response
            return ok_response

        mock_http = AsyncMock()
        mock_http.post = mock_post
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_http),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.create_secure_room(["@user:example.com"])
            assert result == "!test:example.com"
            assert call_count >= 2


# ---------------------------------------------------------------------------
# app/services/pdf_reference_translation_service.py
# ---------------------------------------------------------------------------


class TestPDFRefTranslationValidate:
    def test_validate_languages_same(self) -> None:
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_languages,
        )

        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_languages("en", "en")
        assert exc_info.value.detail.code == "INVALID_LANGUAGE_PAIR"

    def test_validate_languages_unsupported(self) -> None:
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_languages,
        )

        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_languages("en", "zz")
        assert exc_info.value.detail.code == "UNSUPPORTED_LANGUAGE"

    def test_validate_languages_valid(self) -> None:
        from app.services.pdf_reference_translation_service import _validate_languages

        src, tgt = _validate_languages("en", "de")
        assert src == "en"
        assert tgt == "de"


class TestPDFRefTranslationHelpers:
    def test_page_count(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import _page_count

        analysis = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="",
            pages=[{"pageNumber": 1}, {"pageNumber": 2}],
            paragraphs=[],
            tables=[],
            key_value_pairs=[],
            languages=[],
            styles=[],
        )
        assert _page_count(analysis) == 2

    def test_alphabetic_count(self) -> None:
        from app.services.pdf_reference_translation_service import _alphabetic_count

        assert _alphabetic_count("abc123def") == 6
        assert _alphabetic_count("12345") == 0
        assert _alphabetic_count("") == 0

    def test_validate_translated_pdf_good(self) -> None:
        from app.services.pdf_reference_translation_service import _validate_translated_pdf

        pdf_bytes = b"%PDF-1.4 valid"
        b64 = base64.b64encode(pdf_bytes).decode()
        result = _validate_translated_pdf(b64)
        assert result == pdf_bytes

    def test_validate_translated_pdf_not_pdf(self) -> None:
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_pdf,
        )

        b64 = base64.b64encode(b"NOT_PDF").decode()
        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_translated_pdf(b64)
        assert exc_info.value.detail.code == "BABELDOC_TRANSLATION_FAILED"

    def test_validate_translated_pdf_bad_base64(self) -> None:
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_pdf,
        )

        with pytest.raises(PDFReferenceTranslationError):
            _validate_translated_pdf("!!!not-base64!!!")


class TestPDFRefTranslationErrorMapping:
    def test_map_azure_error_timeout(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )
        from app.services.pdf_reference_translation_service import _map_azure_error

        exc = AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="PROCESSING_TIMEOUT",
                message="timeout",
                retryable=True,
            )
        )
        result = _map_azure_error(exc)
        assert result.status_code == 504

    def test_map_azure_error_unavailable(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )
        from app.services.pdf_reference_translation_service import _map_azure_error

        exc = AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="unavailable",
                retryable=True,
            )
        )
        result = _map_azure_error(exc)
        assert result.status_code == 503

    def test_map_babeldoc_not_implemented(self) -> None:
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        result = _map_babeldoc_error(NotImplementedError("disabled"))
        assert result.status_code == 503

    def test_map_babeldoc_runtime(self) -> None:
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        result = _map_babeldoc_error(RuntimeError("not configured"))
        assert result.status_code == 503


class TestPDFRefTranslationFormLabelLeakage:
    def test_no_leakage(self) -> None:
        from app.services.pdf_reference_translation_service import (
            _contains_source_form_label_leakage,
        )

        assert _contains_source_form_label_leakage("Name:", "Name:", "en") is False

    def test_with_leakage(self) -> None:
        from app.services.pdf_reference_translation_service import (
            _contains_source_form_label_leakage,
        )

        assert _contains_source_form_label_leakage("Vorname:", "Vorname: Max", "de") is True


class TestPDFRefTranslationAnalysisHelpers:
    def test_dominant_language_none(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import (
            _dominant_analysis_language,
        )

        analysis = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="",
            pages=[],
            paragraphs=[],
            tables=[],
            key_value_pairs=[],
            languages=[],
            styles=[],
        )
        assert _dominant_analysis_language(analysis) is None

    def test_dominant_language_with_langs(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import (
            _dominant_analysis_language,
        )

        analysis = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="",
            pages=[],
            paragraphs=[],
            tables=[],
            key_value_pairs=[],
            languages=[
                {"locale": "de", "confidence": 0.9},
                {"locale": "de", "confidence": 0.8},
                {"locale": "en", "confidence": 0.7},
            ],
            styles=[],
        )
        result = _dominant_analysis_language(analysis)
        assert result == "de"

    def test_polygon_height(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        polygon = [
            {"x": 0, "y": 0},
            {"x": 10, "y": 0},
            {"x": 10, "y": 20},
            {"x": 0, "y": 20},
        ]
        assert _polygon_height(polygon) == 20.0

    def test_polygon_height_none(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        assert _polygon_height([]) is None
        assert _polygon_height("not a list") is None

    def test_median_word_height_empty(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import _median_word_height

        analysis = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="",
            pages=[],
            paragraphs=[],
            tables=[],
            key_value_pairs=[],
            languages=[],
            styles=[],
        )
        assert _median_word_height(analysis) is None


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/search.py
# ---------------------------------------------------------------------------


class TestSearchRequestId:
    def test_request_id_from_x_request_id(self) -> None:
        from app.api.v1.endpoints.search import _request_id

        request = MagicMock()
        request.headers = {"x-request-id": "req-123"}
        assert _request_id(request) == "req-123"

    def test_request_id_from_cf_ray(self) -> None:
        from app.api.v1.endpoints.search import _request_id

        request = MagicMock()
        request.headers = {"cf-ray": "ray-456"}
        assert _request_id(request) == "ray-456"

    def test_request_id_unavailable(self) -> None:
        from app.api.v1.endpoints.search import _request_id

        request = MagicMock()
        request.headers = {}
        assert _request_id(request) == "unavailable"


class TestSearchRequest:
    def test_default_values(self) -> None:
        from app.api.v1.endpoints.search import SearchRequest

        req = SearchRequest(query="test query")
        assert req.query == "test query"
        assert req.language == "en"
        assert req.document_types == []
        assert req.max_results == 10
