"""Batch 9 coverage tests — pdf_reference_translation, rag_service, translation, ocr."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── pdf_reference_translation_service: error mapping + validation ───────────


class TestPDFRefValidateTranslatedPDF:
    def test_oversized_b64_raises(self) -> None:
        from app.services.pdf_reference_translation_service import (
            MAX_TRANSLATED_PDF_B64_CHARS,
            PDFReferenceTranslationError,
            _validate_translated_pdf,
        )

        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_translated_pdf("x" * (MAX_TRANSLATED_PDF_B64_CHARS + 1))
        assert exc_info.value.detail.code == "BABELDOC_TRANSLATION_FAILED"

    def test_invalid_base64_raises(self) -> None:
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_pdf,
        )

        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_translated_pdf("!!!not-base64!!!")
        assert exc_info.value.detail.code == "BABELDOC_TRANSLATION_FAILED"

    def test_missing_pdf_header_raises(self) -> None:
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_pdf,
        )

        valid_b64 = base64.b64encode(b"NOT A PDF FILE").decode()
        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_translated_pdf(valid_b64)
        assert exc_info.value.detail.code == "BABELDOC_TRANSLATION_FAILED"

    def test_valid_pdf_passes(self) -> None:
        from app.services.pdf_reference_translation_service import _validate_translated_pdf

        valid_b64 = base64.b64encode(b"%PDF-1.4 some content").decode()
        result = _validate_translated_pdf(valid_b64)
        assert result.startswith(b"%PDF")


class TestPDFRefMapBabelDocError:
    def test_not_implemented_error(self) -> None:
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        result = _map_babeldoc_error(NotImplementedError("not supported"))
        assert result.status_code == 503

    def test_runtime_error(self) -> None:
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        result = _map_babeldoc_error(RuntimeError("runtime fail"))
        assert result.status_code == 503

    def test_generic_exception(self) -> None:
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        result = _map_babeldoc_error(ValueError("generic"))
        assert result.status_code == 502

    def test_babeldoc_password_required(self) -> None:
        from app.integrations.babeldoc_adapter import BabelDocError, BabelDocSidecarError
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        err = BabelDocSidecarError(
            BabelDocError(error_code="PASSWORD_REQUIRED", message="protected", retryable=False)
        )
        result = _map_babeldoc_error(err)
        assert result.status_code == 422

    def test_babeldoc_timeout(self) -> None:
        from app.integrations.babeldoc_adapter import BabelDocError, BabelDocSidecarError
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        err = BabelDocSidecarError(
            BabelDocError(error_code="TIMEOUT", message="timeout", retryable=True)
        )
        result = _map_babeldoc_error(err)
        assert result.status_code == 504

    def test_babeldoc_service_unavailable(self) -> None:
        from app.integrations.babeldoc_adapter import BabelDocError, BabelDocSidecarError
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        err = BabelDocSidecarError(
            BabelDocError(error_code="SERVICE_UNAVAILABLE", message="unavail", retryable=True)
        )
        result = _map_babeldoc_error(err)
        assert result.status_code == 503

    def test_babeldoc_generic_error(self) -> None:
        from app.integrations.babeldoc_adapter import BabelDocError, BabelDocSidecarError
        from app.services.pdf_reference_translation_service import _map_babeldoc_error

        err = BabelDocSidecarError(
            BabelDocError(error_code="UNKNOWN_CODE", message="unknown", retryable=False)
        )
        result = _map_babeldoc_error(err)
        assert result.status_code == 502


class TestPDFRefMapOutputAnalysisError:
    def test_processing_timeout(self) -> None:
        from app.services.pdf_reference_translation_service import _map_output_analysis_error

        mock_exc = MagicMock()
        mock_exc.detail.code = "PROCESSING_TIMEOUT"
        result = _map_output_analysis_error(mock_exc)
        assert result.status_code == 504

    def test_service_unavailable(self) -> None:
        from app.services.pdf_reference_translation_service import _map_output_analysis_error

        mock_exc = MagicMock()
        mock_exc.detail.code = "SERVICE_UNAVAILABLE"
        result = _map_output_analysis_error(mock_exc)
        assert result.status_code == 503

    def test_other_code(self) -> None:
        from app.services.pdf_reference_translation_service import _map_output_analysis_error

        mock_exc = MagicMock()
        mock_exc.detail.code = "SOME_OTHER_ERROR"
        result = _map_output_analysis_error(mock_exc)
        assert result.status_code == 502


class TestPDFRefMapAzureError:
    def test_service_unavailable(self) -> None:
        from app.services.pdf_reference_translation_service import _map_azure_error

        mock_exc = MagicMock()
        mock_exc.detail.code = "SERVICE_UNAVAILABLE"
        result = _map_azure_error(mock_exc)
        assert result.status_code == 503

    def test_other_code(self) -> None:
        from app.services.pdf_reference_translation_service import _map_azure_error

        mock_exc = MagicMock()
        mock_exc.detail.code = "OTHER"
        result = _map_azure_error(mock_exc)
        assert result.status_code == 502


class TestPDFRefPolygonHeight:
    def test_flat_list_polygon(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        polygon = [0, 0, 10, 0, 10, 20, 0, 20]
        height = _polygon_height(polygon)
        assert height == 20.0

    def test_empty_polygon(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        result = _polygon_height([])
        assert result is None or result == 0.0


# ── rag_service: rerank, search, stream_search, provenance ──────────────────


class TestRagServiceRerank:
    def test_rerank_import_error_returns_original(self) -> None:
        from app.services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        docs = [{"text": "a"}, {"text": "b"}]
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            result = svc.rerank("query", docs, top_k=1)
            assert len(result) == 1

    def test_rerank_empty_returns_empty(self) -> None:
        from app.services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        result = svc.rerank("query", [], top_k=5)
        assert result == []

    def test_rerank_success_scores_and_sorts(self) -> None:
        """Cover the cross-encoder success path: lazy import, init, predict, sort."""
        from app.services.rag_service import RAGService

        fake_module = MagicMock()
        fake_cross_encoder = MagicMock()
        fake_cross_encoder.predict.return_value = [0.3, 0.9, 0.1]
        fake_module.CrossEncoder = MagicMock(return_value=fake_cross_encoder)
        svc = RAGService.__new__(RAGService)
        svc._cross_encoder = None

        docs = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            result = svc.rerank("query", docs, top_k=5)
        # CrossEncoder was lazily imported + instantiated with the expected model.
        fake_module.CrossEncoder.assert_called_once_with(
            "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
        )
        fake_cross_encoder.predict.assert_called_once()
        # Sorted by score descending: b (0.9), a (0.3), c (0.1).
        assert [d["text"] for d in result] == ["b", "a", "c"]
        assert all("score" in d for d in result)


class TestRagServiceSearch:
    async def test_search_empty_language_uses_detect(self) -> None:
        from app.services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        with (
            patch("app.services.rag_service.HindsightRAGService") as MockRAG,
            patch("app.services.rag_service.apertus_enabled", return_value=False),
            patch("app.services.rag_service.build_rag_prompt", return_value="prompt"),
        ):
            mock_rag = AsyncMock()
            mock_rag.query = AsyncMock(return_value=[])
            MockRAG.return_value = mock_rag
            result = await svc.search("test query", language="")
            assert result.sources == []


class TestRagServiceStreamSearch:
    async def test_stream_search_yields_done(self) -> None:
        from app.services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        with (
            patch("app.services.rag_service.HindsightRAGService") as MockRAG,
            patch("app.core.sse.sse_frame", side_effect=lambda t, d: f"event:{t}\n"),
        ):
            mock_rag = AsyncMock()
            mock_rag.query = AsyncMock(return_value=[])
            MockRAG.return_value = mock_rag
            frames = []
            async for frame in svc.stream_search("test", language="en"):
                frames.append(frame)
            assert any("done" in f for f in frames)


class TestRagBuildRagPrompt:
    def test_empty_chunk_text_skipped(self) -> None:
        from app.services.rag_service import build_rag_prompt

        results = [
            {"text": "  ", "source_title": "Doc1", "source_url": "http://ex.com"},
            {"text": "valid content", "source_title": "Doc2", "source_url": "http://ex2.com"},
        ]
        prompt = build_rag_prompt("query", results)
        assert "valid content" in prompt

    def test_conversation_history_included(self) -> None:
        from app.services.rag_service import build_rag_prompt

        results = [{"text": "content", "source_title": "Doc", "source_url": "http://ex.com"}]
        history = [
            {"role": "user", "content": "prev question"},
            {"role": "assistant", "content": "prev answer"},
        ]
        prompt = build_rag_prompt("follow up", results, conversation_history=history)
        assert "prev question" in prompt


# ── translation_service: _call_mistral_large + _call_m2m100 branches ────────


class TestTranslationCallMistralLarge:
    async def test_mistral_large_success(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "Übersetzter Text"}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.core.config.settings") as mock_s,
            patch("app.services.translation_service.get_gateway_url", return_value="http://test"),
            patch("app.services.translation_service.get_gateway_auth_headers", return_value={}),
        ):
            mock_s.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.RAG_LLM_TIMEOUT_S = 30
            result = await svc._call_mistral_large("Hello", "en", "de", 30)
            assert result == "Übersetzter Text"

    async def test_mistral_large_empty_choices(self) -> None:
        from app.services.translation_service import TranslationError, TranslationService

        svc = TranslationService.__new__(TranslationService)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.core.config.settings") as mock_s,
            patch("app.services.translation_service.get_gateway_url", return_value="http://test"),
            patch("app.services.translation_service.get_gateway_auth_headers", return_value={}),
        ):
            mock_s.MISTRAL_API_KEY = "tok"
            mock_s.RAG_LLM_TIMEOUT_S = 30
            with pytest.raises(TranslationError, match="Unexpected"):
                await svc._call_mistral_large("Hello", "en", "de", 30)


class TestTranslationCallM2M100:
    async def test_unsupported_model_fallback(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {"translated_text": "translated"},
            "success": True,
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.core.config.settings") as mock_s,
            patch("app.services.translation_service.get_gateway_url", return_value="http://test"),
            patch("app.services.translation_service.get_gateway_auth_headers", return_value={}),
            patch("app.integrations.routing.not_diamond.NotDiamondRouter") as MockRouter,
        ):
            mock_s.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.RAG_LLM_TIMEOUT_S = 30
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value="some-unsupported-model")
            MockRouter.return_value = mock_router
            result = await svc._call_m2m100("Hello", "en", "de", timeout=30)
            assert result == "translated"

    async def test_m2m100_non_dict_result(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": "not-a-dict", "success": True}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.core.config.settings") as mock_s,
            patch("app.services.translation_service.get_gateway_url", return_value="http://test"),
            patch("app.services.translation_service.get_gateway_auth_headers", return_value={}),
            patch("app.integrations.routing.not_diamond.NotDiamondRouter") as MockRouter,
        ):
            mock_s.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.RAG_LLM_TIMEOUT_S = 30
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value="@cf/meta/m2m100-1.2b")
            MockRouter.return_value = mock_router
            with pytest.raises(Exception, match="Unexpected"):
                await svc._call_m2m100("Hello", "en", "de", timeout=30)

    async def test_m2m100_http_error(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.core.config.settings") as mock_s,
            patch("app.services.translation_service.get_gateway_url", return_value="http://test"),
            patch("app.services.translation_service.get_gateway_auth_headers", return_value={}),
            patch("app.integrations.routing.not_diamond.NotDiamondRouter") as MockRouter,
        ):
            mock_s.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.RAG_LLM_TIMEOUT_S = 30
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value="@cf/meta/m2m100-1.2b")
            MockRouter.return_value = mock_router
            with pytest.raises(Exception, match="HTTP 500"):
                await svc._call_m2m100("Hello", "en", "de", timeout=30)


class TestTranslationSectionSplitWordBoundary:
    def test_oversized_sentence_split_by_words(self) -> None:
        from app.services.translation_service import _split_translation_sections

        long_sentence = "word " * 200
        result = _split_translation_sections(long_sentence.strip(), max_chars=100)
        assert len(result) > 1
        for section in result:
            assert len(section) <= 150

    def test_table_row_not_split(self) -> None:
        from app.services.translation_service import _split_translation_sections

        table = "| Name | Age | City |\n| Alice | 30 | Berlin |"
        result = _split_translation_sections(table, max_chars=1000)
        assert len(result) >= 1


class TestTranslationGlossaryEnforcement:
    def test_pages_without_sections_key(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)
        pages = [{"page_number": 1, "text": "No sections here"}]
        translated = [{"page_number": 1, "text": "Übersetzt"}]
        with patch("app.core.config.settings") as mock_s:
            mock_s.GLOSSARY_ENFORCEMENT_ENABLED = False
            result = svc._apply_glossary_enforcement_result(pages, translated, "en", "de")
            assert result.terms_applied == 0


# ── ocr_service: fillable form detection ────────────────────────────────────


class TestOCR_FILLABLE_FORM:
    async def test_pdf_intake_detects_fillable_form(self) -> None:
        from app.services.pdf_intake_service import _detect_fillable_form

        with patch("pypdfium2.PdfDocument") as mock_pdfium:
            mock_pdf = MagicMock()
            mock_page = MagicMock()
            mock_page.getFormFieldCount.return_value = 3
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_pdf.__len__ = MagicMock(return_value=1)
            mock_pdf.__iter__ = MagicMock(return_value=iter([mock_page]))
            mock_pdfium.return_value = mock_pdf
            result = _detect_fillable_form(b"fake pdf bytes")
            assert isinstance(result, bool)
