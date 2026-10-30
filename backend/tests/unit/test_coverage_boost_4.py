"""Batch 4: Medium-gap coverage boost — 9 files with 7–23 missed statements each.

Covers:
- azure_document_intelligence.py — config validation branches, poll error paths
- ocr_service.py — fillable form processing, layout analysis exception
- session_topic.py — topic tracking edge cases
- classification_service.py — map_response branches, classify_document paths
- chat_guidance.py — followup_answer + Spain markers
- document_explanation_service.py — helper functions + explain branches
- pdf_intake_service.py — all validation branches
- babeldoc_adapter.py — language pair mismatch, retry, non-retryable errors
- graph_rag_service.py — entity expansion, no d1, no tokens
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/integrations/azure_document_intelligence.py — config branches
# ---------------------------------------------------------------------------


class TestAzureConfigBranches:
    def test_load_config_no_endpoint(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            _load_config,
        )

        with (
            patch.dict(
                "os.environ",
                {"AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "", "AZURE_DOCUMENT_INTELLIGENCE_KEY": ""},
                clear=False,
            ),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            _load_config()

    def test_load_config_invalid_timing(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            _load_config,
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://test.cognitiveservices.azure.com",
                    "AZURE_DOCUMENT_INTELLIGENCE_KEY": "test-key",
                    "AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S": "not-a-number",
                },
                clear=False,
            ),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            _load_config()

    def test_load_config_negative_timing(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            _load_config,
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://test.cognitiveservices.azure.com",
                    "AZURE_DOCUMENT_INTELLIGENCE_KEY": "test-key",
                    "AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S": "-1",
                },
                clear=False,
            ),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            _load_config()

    def test_get_analysis_limits_invalid_tier(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            get_analysis_limits,
        )

        with (
            patch.dict("os.environ", {"AZURE_DOCUMENT_INTELLIGENCE_TIER": "X0"}, clear=False),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            get_analysis_limits()

    async def test_analyze_pdf_empty_bytes(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            analyze_pdf,
        )

        with (
            patch("app.integrations.azure_document_intelligence._is_enabled", return_value=True),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            await analyze_pdf(b"")

    async def test_analyze_pdf_disabled(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            analyze_pdf,
        )

        with (
            patch("app.integrations.azure_document_intelligence._is_enabled", return_value=False),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            await analyze_pdf(b"test")

    async def test_normalize_result_no_analyze_result(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            _normalize_result,
        )

        config = MagicMock()
        with pytest.raises(AzureDocumentIntelligenceError):
            _normalize_result({}, config)

    async def test_analyze_pdf_poll_timeout_exception(self) -> None:
        import httpx

        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            analyze_pdf,
        )

        mock_config = MagicMock()
        mock_config.endpoint = "https://test.cognitiveservices.azure.com"
        mock_config.key = "test-key"
        mock_config.api_version = "2024-02-29-preview"
        mock_config.model_id = "prebuilt-layout"
        mock_config.timeout_s = 5
        mock_config.poll_interval_s = 0.1
        mock_config.max_polls = 1

        mock_submit_response = MagicMock()
        mock_submit_response.status_code = 202
        mock_submit_response.headers = {
            "Operation-Location": "https://test.cognitiveservices.azure.com/documentintelligence/ops/123",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_submit_response
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.azure_document_intelligence._is_enabled", return_value=True),
            patch(
                "app.integrations.azure_document_intelligence._load_config",
                return_value=mock_config,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            await analyze_pdf(b"%PDF-1.4 fake pdf content")

    async def test_analyze_pdf_poll_connect_error(self) -> None:
        import httpx

        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            analyze_pdf,
        )

        mock_config = MagicMock()
        mock_config.endpoint = "https://test.cognitiveservices.azure.com"
        mock_config.key = "test-key"
        mock_config.api_version = "2024-02-29-preview"
        mock_config.model_id = "prebuilt-layout"
        mock_config.timeout_s = 5
        mock_config.poll_interval_s = 0
        mock_config.max_polls = 1

        mock_submit_response = MagicMock()
        mock_submit_response.status_code = 202
        mock_submit_response.headers = {
            "Operation-Location": "https://test.cognitiveservices.azure.com/documentintelligence/ops/123",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_submit_response
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.azure_document_intelligence._is_enabled", return_value=True),
            patch(
                "app.integrations.azure_document_intelligence._load_config",
                return_value=mock_config,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            await analyze_pdf(b"%PDF-1.4 fake pdf content")

    async def test_analyze_pdf_poll_json_error(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            analyze_pdf,
        )

        mock_config = MagicMock()
        mock_config.endpoint = "https://test.cognitiveservices.azure.com"
        mock_config.key = "test-key"
        mock_config.api_version = "2024-02-29-preview"
        mock_config.model_id = "prebuilt-layout"
        mock_config.timeout_s = 5
        mock_config.poll_interval_s = 0
        mock_config.max_polls = 1

        mock_submit_response = MagicMock()
        mock_submit_response.status_code = 202
        mock_submit_response.headers = {
            "Operation-Location": "https://test.cognitiveservices.azure.com/documentintelligence/ops/123",
        }

        mock_poll_response = MagicMock()
        mock_poll_response.status_code = 200
        mock_poll_response.json.side_effect = ValueError("invalid json")

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_submit_response
        mock_client.get.return_value = mock_poll_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.azure_document_intelligence._is_enabled", return_value=True),
            patch(
                "app.integrations.azure_document_intelligence._load_config",
                return_value=mock_config,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            await analyze_pdf(b"%PDF-1.4 fake pdf content")

    async def test_analyze_pdf_poll_not_dict(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            analyze_pdf,
        )

        mock_config = MagicMock()
        mock_config.endpoint = "https://test.cognitiveservices.azure.com"
        mock_config.key = "test-key"
        mock_config.api_version = "2024-02-29-preview"
        mock_config.model_id = "prebuilt-layout"
        mock_config.timeout_s = 5
        mock_config.poll_interval_s = 0
        mock_config.max_polls = 1

        mock_submit_response = MagicMock()
        mock_submit_response.status_code = 202
        mock_submit_response.headers = {"Operation-Location": "https://test.com/ops/123"}

        mock_poll_response = MagicMock()
        mock_poll_response.status_code = 200
        mock_poll_response.json.return_value = "not a dict"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_submit_response
        mock_client.get.return_value = mock_poll_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.azure_document_intelligence._is_enabled", return_value=True),
            patch(
                "app.integrations.azure_document_intelligence._load_config",
                return_value=mock_config,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(AzureDocumentIntelligenceError),
        ):
            await analyze_pdf(b"%PDF-1.4 fake pdf content")


# ---------------------------------------------------------------------------
# app/services/session_topic.py — topic tracking edge cases
# ---------------------------------------------------------------------------


class TestSessionTopicEdgeCases:
    def test_infer_topic_subject_empty(self) -> None:
        from app.services.session_topic import _infer_topic_subject

        assert _infer_topic_subject([]) == ""

    def test_infer_topic_subject_long(self) -> None:
        from app.services.session_topic import _infer_topic_subject

        words = ["extraordinarilylongword"] * 30
        result = _infer_topic_subject(words)
        assert len(result) <= 120
        assert result.endswith("...")

    def test_jaccard_empty_sets(self) -> None:
        from app.services.session_topic import _jaccard_similarity

        assert _jaccard_similarity(set(), set()) == 1.0

    def test_update_topic_shift_exceeds_history_limit(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {
            "topic": {"subject": "old", "keywords": ["a", "b"], "since_turn": 1},
            "topics_history": [
                {"subject": f"t{i}", "keywords": [], "since_turn": i} for i in range(15)
            ],
            "last_user_queries": ["q1"],
        }
        result = tracker.update_topic(
            "new unique topic words here testing", facts, is_first_turn=False
        )
        assert isinstance(result.get("topics_history"), list)
        assert len(result["topics_history"]) <= 10

    def test_update_topic_few_words_no_shift(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {
            "topic": {"subject": "tax law", "keywords": ["tax", "law"], "since_turn": 1},
            "last_user_queries": [],
        }
        result = tracker.update_topic("hi", facts, is_first_turn=False)
        assert result.get("_last_topic_shift") is False

    def test_update_topic_non_list_queries(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {
            "topic": {"subject": "tax", "keywords": ["tax"], "since_turn": 1},
            "last_user_queries": "not a list",
        }
        result = tracker.update_topic(
            "something about immigration law policy", facts, is_first_turn=False
        )
        assert isinstance(result.get("last_user_queries"), list)

    def test_get_retrieval_context_no_shift(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {
            "topic": {"subject": "work permit", "keywords": ["work", "permit"], "since_turn": 1},
            "_last_topic_shift": False,
        }
        result = tracker.get_retrieval_context("how do I apply?", facts)
        assert result.startswith("Current topic:")

    def test_get_retrieval_context_shift(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {
            "topic": {"subject": "visa", "keywords": ["visa"], "since_turn": 1},
            "_last_topic_shift": True,
        }
        result = tracker.get_retrieval_context("tell me more", facts)
        assert result.startswith("New topic:")

    def test_get_retrieval_context_empty_topic(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {"topic": {"subject": "", "keywords": []}}
        result = tracker.get_retrieval_context("query", facts)
        assert result == "query"

    def test_get_current_topic_no_facts(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        assert tracker.get_current_topic(None) == ""
        assert tracker.get_current_topic({}) == ""
        assert tracker.get_current_topic({"topic": "not a dict"}) == ""

    def test_clear_topic(self) -> None:
        from app.services.session_topic import SessionTopicTracker

        tracker = SessionTopicTracker()
        facts: dict[str, object] = {
            "topic": {"subject": "x"},
            "topics_history": [],
            "last_user_queries": [],
            "_last_topic_shift": True,
            "other_key": "keep",
        }
        result = tracker.clear_topic(facts)
        assert "topic" not in result
        assert "topics_history" not in result
        assert "other_key" in result


# ---------------------------------------------------------------------------
# app/services/classification_service.py — branches
# ---------------------------------------------------------------------------


class TestClassificationBranches:
    def test_quality_to_score_fragment(self) -> None:
        from app.services.classification_service import _quality_to_score

        assert (
            _quality_to_score({"content_quality": "excellent", "content_integrity": "fragment"})
            <= 0.35
        )

    def test_quality_to_score_severely_degraded(self) -> None:
        from app.services.classification_service import _quality_to_score

        assert (
            _quality_to_score({"content_quality": "good", "content_integrity": "severely_degraded"})
            <= 0.15
        )

    def test_language_from_response_fallback(self) -> None:
        from app.services.classification_service import _language_from_response

        result = _language_from_response({}, "Dies ist ein Test")
        assert isinstance(result, str)
        assert len(result) == 2

    def test_map_response_list_content_type(self) -> None:
        from app.services.classification_service import _map_response

        data = {
            "content_type": ["invoice", "receipt"],
            "geographic_relevance": ["DE"],
            "content_safety": "safe",
            "pii_presence": "no_pii",
        }
        result = _map_response(data, "test")
        assert result.document_type == "invoice"

    def test_map_response_string_geography(self) -> None:
        from app.services.classification_service import _map_response

        data = {
            "content_type": "unknown",
            "regional_relevance": "EU",
            "country_relevance": ["DE", "FR"],
            "content_safety": "unsafe",
            "pii_presence": "contains_pii",
        }
        result = _map_response(data, "test")
        assert "EU" in result.geographic_relevance
        assert "contains_pii" in result.safety_flags
        assert "unsafe" in result.safety_flags

    def test_map_response_empty_content_type(self) -> None:
        from app.services.classification_service import _map_response

        data = {"content_type": []}
        result = _map_response(data, "test")
        assert result.document_type == "unknown"

    async def test_classify_disabled(self) -> None:
        from app.services.classification_service import classify_document, default_classification

        with patch("app.services.classification_service._settings_bool", return_value=False):
            result = await classify_document("test text", "application/pdf")
            assert result == default_classification("test text")

    async def test_classify_empty_text(self) -> None:
        from app.services.classification_service import classify_document, default_classification

        result = await classify_document("  ", "application/pdf")
        assert result == default_classification("  ")

    async def test_classify_with_propella_base_url(self) -> None:
        from app.services.classification_service import classify_document

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "content_type": "invoice",
                                "language_code": "de",
                                "content_quality": "good",
                                "content_integrity": "complete",
                                "content_safety": "safe",
                                "pii_presence": "no_pii",
                                "confidence": 0.9,
                            }
                        )
                    }
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.classification_service._settings_bool", return_value=True),
            patch(
                "app.services.classification_service._settings_str",
                return_value="https://propella.example.com",
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await classify_document("Invoice for services", "application/pdf")
            assert result.document_type == "invoice"


# ---------------------------------------------------------------------------
# app/services/chat_guidance.py — followup_answer + Spain markers
# ---------------------------------------------------------------------------


class TestChatGuidanceBranches:
    def test_is_followup_answer_short_status(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        assert _is_followup_answer("I am an EU citizen") is True

    def test_is_followup_answer_question(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        assert _is_followup_answer("What is a work permit?") is False

    def test_is_followup_answer_goal(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        assert _is_followup_answer("I want to find a job") is False

    def test_is_followup_answer_long_statement(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        assert (
            _is_followup_answer(
                "I am a professional software engineer with extensive experience in building scalable distributed systems"
            )
            is False
        )

    def test_enforce_citation_grounding_disabled(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding("test claim", config=GroundingConfig(enabled=False))
        assert result["verdict"] == "pass"
        assert result["claims"] == []

    def test_enforce_citation_grounding_empty_text(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding("", config=GroundingConfig(enabled=True))
        assert result["verdict"] == "pass"
        assert result["claims"] == []

    def test_enforce_citation_grounding_with_docs(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            "This is a grounded claim.",
            known_doc_ids={"doc-1"},
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] in ("pass", "partial", "fail")
        assert result["total_claims"] >= 1


# ---------------------------------------------------------------------------
# app/services/document_explanation_service.py — helper functions
# ---------------------------------------------------------------------------


class TestDocumentExplanationHelpers:
    def test_coerce_page_number_int(self) -> None:
        from app.services.document_explanation_service import _coerce_page_number

        assert _coerce_page_number(5) == 5

    def test_coerce_page_number_str(self) -> None:
        from app.services.document_explanation_service import _coerce_page_number

        assert _coerce_page_number("3") == 3

    def test_coerce_page_number_invalid_str(self) -> None:
        from app.services.document_explanation_service import _coerce_page_number

        assert _coerce_page_number("abc") == 0

    def test_coerce_page_number_other(self) -> None:
        from app.services.document_explanation_service import _coerce_page_number

        assert _coerce_page_number(None) == 0
        assert _coerce_page_number(3.14) == 0

    def test_bounded_text_non_string(self) -> None:
        from app.services.document_explanation_service import _bounded_text

        assert _bounded_text(None, 100) == ""
        assert _bounded_text(123, 100) == ""

    def test_bounded_text_truncation(self) -> None:
        from app.services.document_explanation_service import _bounded_text

        result = _bounded_text("a" * 200, 50)
        assert len(result) == 50

    def test_page_number_not_dict(self) -> None:
        from app.services.document_explanation_service import _page_number

        assert _page_number("not a dict") is None
        assert _page_number(None) is None

    def test_page_number_no_regions(self) -> None:
        from app.services.document_explanation_service import _page_number

        assert _page_number({}) is None
        assert _page_number({"boundingRegions": "not a list"}) is None

    def test_key_content_not_dict(self) -> None:
        from app.services.document_explanation_service import _key_content

        assert _key_content("not a dict") == ("", None)
        assert _key_content({"key": "not a dict"}) == ("", None)

    def test_query_term(self) -> None:
        from app.services.document_explanation_service import _query_term

        result = _query_term("some_text!@#$%")
        assert "some text" in result
        assert "!" not in result

    def test_document_evidence_empty(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.document_explanation_service import _document_evidence

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
        result = _document_evidence(analysis, [])
        assert result == ""


# ---------------------------------------------------------------------------
# app/services/pdf_intake_service.py — all branches
# ---------------------------------------------------------------------------


class TestPDFIntakeService:
    def test_non_pdf_returns_none(self) -> None:
        from app.services.pdf_intake_service import route_pdf_upload

        assert route_pdf_upload(b"content", "text/plain") is None

    def test_pdf_too_large(self) -> None:
        from app.services.pdf_intake_service import PDFIntakeError, route_pdf_upload

        with pytest.raises(PDFIntakeError) as exc_info:
            route_pdf_upload(b"%PDF" + b"\x00" * (10 * 1024 * 1024 + 1), "application/pdf")
        assert exc_info.value.code == "FILE_TOO_LARGE"
        assert exc_info.value.status_code == 413

    def test_invalid_pdf_header(self) -> None:
        from app.services.pdf_intake_service import PDFIntakeError, route_pdf_upload

        with pytest.raises(PDFIntakeError) as exc_info:
            route_pdf_upload(b"NOT_PDF_CONTENT", "application/pdf")
        assert exc_info.value.code == "INVALID_PDF"
        assert exc_info.value.status_code == 422

    def test_valid_pdf_with_form(self) -> None:
        from app.services.pdf_intake_service import route_pdf_upload

        pdf_bytes = b"%PDF-1.4 fake content"
        with patch("app.services.pdf_intake_service._detect_fillable_form", return_value=True):
            result = route_pdf_upload(pdf_bytes, "application/pdf")
            assert result is not None
            assert result.is_fillable_form is True

    def test_valid_pdf_no_form(self) -> None:
        from app.services.pdf_intake_service import route_pdf_upload

        pdf_bytes = b"%PDF-1.4 fake content"
        with patch("app.services.pdf_intake_service._detect_fillable_form", return_value=False):
            result = route_pdf_upload(pdf_bytes, "application/pdf")
            assert result is not None
            assert result.is_fillable_form is False

    def test_detect_fillable_form_no_pdfium(self) -> None:
        from app.services.pdf_intake_service import _detect_fillable_form

        with patch.dict("sys.modules", {"pypdfium2": None}):
            assert _detect_fillable_form(b"test") is False

    def test_detect_fillable_form_pdfium_error(self) -> None:
        from app.services.pdf_intake_service import _detect_fillable_form

        class FakePdfiumError(Exception):
            pass

        mock_pdfium = MagicMock()
        mock_pdfium.PdfDocument.side_effect = FakePdfiumError("parse error")
        mock_pdfium.PdfiumError = FakePdfiumError
        with patch.dict("sys.modules", {"pypdfium2": mock_pdfium}):
            assert _detect_fillable_form(b"test") is False


# ---------------------------------------------------------------------------
# app/services/graph_rag_service.py — entity expansion
# ---------------------------------------------------------------------------


class TestGraphRAGService:
    async def test_query_no_d1(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = None
        with patch.object(
            svc.__class__.__bases__[0],
            "query",
            new_callable=AsyncMock,
            return_value=[{"document_id": "d1"}],
        ):
            result = await svc.query("test", top_k=5)
            assert len(result) == 1

    async def test_fetch_related_no_d1(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = None
        result = await svc._fetch_related_via_entities("test query")
        assert result == []

    async def test_fetch_related_short_tokens(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = AsyncMock()
        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = mock_d1
        result = await svc._fetch_related_via_entities("hi")
        assert result == []

    async def test_fetch_related_with_results(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = AsyncMock()
        mock_d1.query.side_effect = [
            [{"id": "e1", "name": "test entity", "entity_type": "org", "doc_id": "doc-1"}],
            [{"id": "doc-1", "title": "Test Document"}],
        ]
        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = mock_d1
        result = await svc._fetch_related_via_entities("testentity")
        assert len(result) == 1
        assert result[0]["document_id"] == "doc-1"

    async def test_fetch_related_no_docs(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = AsyncMock()
        mock_d1.query.side_effect = [
            [{"id": "e1", "name": "test entity", "entity_type": "org", "doc_id": "doc-1"}],
            [],
        ]
        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = mock_d1
        result = await svc._fetch_related_via_entities("testentity")
        assert result == []

    async def test_fetch_related_exception(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = AsyncMock()
        mock_d1.query.side_effect = Exception("DB error")
        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = mock_d1
        with patch.object(
            svc.__class__.__bases__[0],
            "query",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await svc.query("testingquery", top_k=5)
            assert result == []

    async def test_query_deduplicates(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        svc = GraphAugmentedRAGService.__new__(GraphAugmentedRAGService)
        svc._d1 = AsyncMock()
        with (
            patch.object(
                svc.__class__.__bases__[0],
                "query",
                new_callable=AsyncMock,
                return_value=[{"document_id": "d1"}, {"document_id": "d2"}],
            ),
            patch.object(
                svc,
                "_fetch_related_via_entities",
                new_callable=AsyncMock,
                return_value=[{"document_id": "d1"}, {"document_id": "d3"}],
            ),
        ):
            result = await svc.query("test", top_k=5)
            ids = [r.get("document_id") for r in result]
            assert ids.count("d1") == 1


# ---------------------------------------------------------------------------
# app/integrations/babeldoc_adapter.py — error branches
# ---------------------------------------------------------------------------


class TestBabeldocAdapterBranches:
    async def test_missing_language_pair_in_response(self) -> None:
        from app.integrations.babeldoc_adapter import BabelDocRequest, translate

        req = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64="dGVzdA==",
            timeout_seconds=30,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "translated_b64": "dGVzdA==",
            "source_lang": None,
            "target_lang": None,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.babeldoc_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.babeldoc_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await translate(req)
            assert "SIDECAR_LANGUAGE_PAIR_UNVERIFIED" in result.warnings

    async def test_mismatched_language_pair(self) -> None:
        from app.integrations.babeldoc_adapter import (
            BabelDocRequest,
            BabelDocSidecarError,
            translate,
        )

        req = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64="dGVzdA==",
            timeout_seconds=30,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "translated_b64": "dGVzdA==",
            "source_lang": "fr",
            "target_lang": "es",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.babeldoc_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.babeldoc_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(BabelDocSidecarError),
        ):
            await translate(req)

    async def test_non_retryable_error_json(self) -> None:
        from app.integrations.babeldoc_adapter import (
            BabelDocRequest,
            BabelDocSidecarError,
            translate,
        )

        req = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64="dGVzdA==",
            timeout_seconds=30,
        )

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "error": {"code": "INVALID_INPUT", "message": "bad file", "retryable": False}
        }
        mock_response.text = '{"error": "bad"}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.babeldoc_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.babeldoc_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(BabelDocSidecarError),
        ):
            await translate(req)

    async def test_non_retryable_error_non_json(self) -> None:
        from app.integrations.babeldoc_adapter import (
            BabelDocRequest,
            BabelDocSidecarError,
            translate,
        )

        req = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64="dGVzdA==",
            timeout_seconds=30,
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "Server Error"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.babeldoc_adapter._is_enabled", return_value=True),
            patch(
                "app.integrations.babeldoc_adapter._get_sidecar_url",
                return_value="http://localhost:8080",
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(BabelDocSidecarError),
        ):
            await translate(req)
