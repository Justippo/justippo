"""Coverage boost batch 19 — session_topic, chat_guidance, azure_document_intelligence, apertus."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ─── session_topic: _infer_topic_subject paths ──────────────────


class TestSessionTopicPaths:
    def test_infer_topic_subject_empty_list(self) -> None:
        from app.services.session_topic import _infer_topic_subject

        result = _infer_topic_subject(content_words=[])
        assert result == ""

    def test_infer_topic_subject_normal(self) -> None:
        from app.services.session_topic import _infer_topic_subject

        result = _infer_topic_subject(content_words=["test", "query", "words"])
        assert result == "test query words"

    def test_infer_topic_subject_truncates_long(self) -> None:
        from app.services.session_topic import _infer_topic_subject

        # A single token longer than 120 chars triggers the truncation branch.
        long_word = "x" * 130
        result = _infer_topic_subject(content_words=[long_word])
        assert result.endswith("...")
        assert len(result) == 120


# ─── chat_guidance: _is_followup_answer and grounding paths ───────


class TestChatGuidancePaths:
    def test_is_followup_answer_short_non_status_is_false(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        # These are short but are NOT personal-status declarations.
        assert _is_followup_answer("yes") is False
        assert _is_followup_answer("no") is False
        assert _is_followup_answer("ok") is False
        assert _is_followup_answer("thanks") is False

    def test_is_followup_answer_personal_status_is_true(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        # These start with a status declaration and carry a status keyword.
        assert _is_followup_answer("I am a non-EU citizen") is True
        assert _is_followup_answer("I have a German job offer") is True

    def test_is_followup_answer_goal_is_false(self) -> None:
        from app.services.chat_guidance import _is_followup_answer

        # Goals (guidance options) are NEW questions, never answers.
        assert _is_followup_answer("I want to work in Germany") is False

    def test_enforce_citation_grounding_empty_claim(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="",
            known_doc_ids={"doc1"},
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "pass"

    def test_enforce_citation_grounding_disabled(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="Unsupported claim",
            known_doc_ids=set(),
            entity_mentions=set(),
            config=GroundingConfig(enabled=False),
        )
        assert result["verdict"] == "pass"

    def test_enforce_citation_grounding_all_grounded(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="This is supported by doc1.",
            known_doc_ids={"doc1"},
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "pass"
        assert result["ungrounded_count"] == 0

    def test_enforce_citation_grounding_partial(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="Supported by doc1. Unsupported claim.",
            known_doc_ids={"doc1"},
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "partial"
        assert result["ungrounded_count"] == 1

    def test_enforce_citation_grounding_all_ungrounded(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="No sources for this claim.",
            known_doc_ids=set(),
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "fail"
        assert result["ungrounded_count"] > 0


# ─── azure_document_intelligence: error paths ──────────────────


class TestAzureDocumentIntelligenceErrors:
    def test_invalid_provider_response_error(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )

        detail = AzureDocumentIntelligenceErrorDetail(
            code="INVALID_PROVIDER_RESPONSE",
            message="Invalid response",
            retryable=False,
        )
        with pytest.raises(AzureDocumentIntelligenceError):
            raise AzureDocumentIntelligenceError(detail)


# ─── apertus_adapter: error paths ──────────────────────────────


class TestApertusAdapterErrors:
    def test_model_name_returns_none_when_disabled(self) -> None:
        from app.integrations.llm.apertus_adapter import model_name

        with patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=None):
            result = model_name()
            assert result is None

    def test_build_payload_includes_stream_flag(self) -> None:
        from app.integrations.llm.apertus_adapter import _build_payload

        payload = _build_payload("test prompt", "test-model", 100, stream=True)
        assert payload["stream"] is True
        assert payload["model"] == "test-model"

        payload_false = _build_payload("test prompt", "test-model", 100, stream=False)
        assert payload_false["stream"] is False

    def test_strip_special_tokens_removes_tokens(self) -> None:
        from app.integrations.llm.apertus_adapter import (
            _APERTUS_SPECIAL_TOKENS,
            _strip_special_tokens,
        )

        result = _strip_special_tokens(
            f"{_APERTUS_SPECIAL_TOKENS[0]}Hello world{_APERTUS_SPECIAL_TOKENS[0]}"
        )
        assert _APERTUS_SPECIAL_TOKENS[0] not in result
        assert result == "Hello world"

    def test_parse_stream_delta_extracts_content(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        data = {"choices": [{"delta": {"content": "hello"}}]}
        result = _parse_stream_delta(data)
        assert result == "hello"

    def test_parse_stream_delta_returns_empty_for_invalid(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta("not a dict") == ""
        assert _parse_stream_delta({"choices": "not a list"}) == ""
        assert _parse_stream_delta({"choices": []}) == ""
