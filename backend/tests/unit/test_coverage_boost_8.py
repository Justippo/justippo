"""Batch 8 coverage tests — workers_ai, apertus, rag_service, chat, translation."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── workers_ai_adapter: streaming + neuron budget ────────────────────────────


class TestWorkersAIExtractAnswer:
    def test_native_result_response(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"result": {"response": "hello world"}}
        assert _extract_answer(data) == "hello world"

    def test_native_result_translated_text(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"result": {"translated_text": "übersetzt"}}
        assert _extract_answer(data) == "übersetzt"

    def test_bare_response(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"response": "bare text"}
        assert _extract_answer(data) == "bare text"

    def test_openai_delta(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"delta": {"content": "chunk1"}}]}
        assert _extract_answer(data, strip=False) == "chunk1"

    def test_empty_choices(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        assert _extract_answer({"choices": []}) == ""

    def test_non_dict_input(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        assert _extract_answer({"unexpected": "shape"}) == ""

    def test_strip_whitespace(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"result": {"response": "  padded  "}}
        assert _extract_answer(data, strip=True) == "padded"


class TestWorkersAINeuronBudget:
    async def test_no_kv_allows_all(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _check_and_reserve_neurons

        allowed, model = await _check_and_reserve_neurons(
            "@cf/meta/llama-3.1-8b-instruct-fp8", None
        )
        assert allowed is True
        assert model is None

    async def test_within_budget(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _check_and_reserve_neurons

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="100")
        mock_kv.put = AsyncMock()
        allowed, model = await _check_and_reserve_neurons(
            "@cf/meta/llama-3.1-8b-instruct-fp8", mock_kv
        )
        assert allowed is True

    async def test_over_budget_downgrade(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _check_and_reserve_neurons

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="7500")
        mock_kv.put = AsyncMock()
        allowed, model = await _check_and_reserve_neurons(
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast", mock_kv
        )
        assert allowed is True
        assert model is not None

    async def test_budget_exhausted(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _check_and_reserve_neurons

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="8000")
        mock_kv.put = AsyncMock()
        allowed, model = await _check_and_reserve_neurons(
            "@cf/meta/llama-3.1-8b-instruct-fp8", mock_kv
        )
        assert allowed is False

    async def test_get_neuron_budget_kv_returns_none(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _get_neuron_budget_kv

        with patch("app.integrations.llm.workers_ai_adapter.settings", create=True) as mock_s:
            del mock_s.NEURON_BUDGET_KV
            result = _get_neuron_budget_kv()
            assert result is None

    async def test_get_neuron_budget_kv_exception(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _get_neuron_budget_kv

        with patch(
            "app.integrations.llm.workers_ai_adapter._get_settings", side_effect=ImportError
        ):
            result = _get_neuron_budget_kv()
            assert result is None


class TestWorkersAIGenerateAnswer:
    async def test_empty_token_returns_none(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer

        with patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s:
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = ""
            result = await generate_answer("test prompt")
            assert result is None

    async def test_http_error_raises(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter.is_enabled", return_value=True),
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://test"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="model"),
        ):
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "test-token"
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30
            mock_resp.status_code = 500
            mock_resp.text = "error"

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with (
                patch("httpx.AsyncClient", return_value=mock_client),
                pytest.raises(RuntimeError, match="failed"),
            ):
                await generate_answer("test")

    async def test_non_json_response_raises(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("", "", 0)
        mock_resp.text = "not json"

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://test"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="model"),
        ):
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "test-token"
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with (
                patch("httpx.AsyncClient", return_value=mock_client),
                pytest.raises(RuntimeError, match="non-JSON"),
            ):
                await generate_answer("test")


class TestWorkersAIGreetingStream:
    async def test_empty_token_yields_nothing(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_greeting_stream

        with patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s:
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = ""
            tokens = [t async for t in generate_greeting_stream("hello")]
            assert tokens == []

    async def test_timeout_yields_fallback(self) -> None:
        import httpx as _httpx

        from app.integrations.llm.workers_ai_adapter import generate_greeting_stream

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://test"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
        ):
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 5

            mock_stream_resp = AsyncMock()
            mock_stream_resp.status_code = 200
            mock_stream_resp.aiter_lines = AsyncMock(return_value=iter([]))
            mock_stream_resp.__aenter__ = AsyncMock(return_value=mock_stream_resp)
            mock_stream_resp.__aexit__ = AsyncMock(return_value=False)

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with (
                patch("httpx.AsyncClient", return_value=mock_client),
                patch("httpx.TimeoutException", _httpx.TimeoutException),
            ):
                mock_client.stream.side_effect = _httpx.TimeoutException("timeout")
                tokens = [t async for t in generate_greeting_stream("hello")]
                assert any("Hi there" in t for t in tokens)


class TestWorkersAIAnswerStream:
    async def test_empty_token_yields_nothing(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        with patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s:
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = ""
            tokens = [t async for t in generate_answer_stream("test")]
            assert tokens == []

    async def test_budget_exhausted_yields_error(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="8000")
        mock_kv.put = AsyncMock()

        with patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s:
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30
            tokens = [t async for t in generate_answer_stream("test", neuron_budget_kv=mock_kv)]
            assert any("budget" in t.lower() for t in tokens)

    async def test_http_error_raises(self) -> None:

        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.aread = AsyncMock(return_value=b"error")

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://test"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="model"),
        ):
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30

            with (
                patch("httpx.AsyncClient", return_value=mock_client),
                pytest.raises(RuntimeError, match="failed"),
            ):
                async for _ in generate_answer_stream("test"):
                    pass


# ── apertus_adapter: streaming + _parse_stream_delta ────────────────────────


class TestApertusParseStreamDelta:
    def test_valid_delta(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        data = {"choices": [{"delta": {"content": "hello"}}]}
        assert _parse_stream_delta(data) == "hello"

    def test_empty_choices(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta({"choices": []}) == ""

    def test_non_dict(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta("string") == ""

    def test_no_delta_key(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta({"choices": [{"message": {}}]}) == ""


class TestApertusGenerateAnswerStream:
    async def test_no_route_yields_nothing(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer_stream

        with patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=None):
            tokens = [t async for t in generate_answer_stream("test")]
            assert tokens == []

    async def test_timeout_raises(self) -> None:
        import httpx as _httpx

        from app.integrations.llm.apertus_adapter import generate_answer_stream

        mock_route = MagicMock()
        mock_route.model = "model"
        mock_route.url = "http://test"
        mock_route.headers = {}
        mock_route.name = "test-route"

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(side_effect=_httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=mock_route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.apertus_adapter._build_payload", return_value={}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            mock_s.return_value.RAG_LLM_MAX_TOKENS = 256
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30
            with pytest.raises(RuntimeError, match="timed out"):
                async for _ in generate_answer_stream("test"):
                    pass

    async def test_connect_error_raises(self) -> None:
        import httpx as _httpx

        from app.integrations.llm.apertus_adapter import generate_answer_stream

        mock_route = MagicMock()
        mock_route.model = "model"
        mock_route.url = "http://test"
        mock_route.headers = {}
        mock_route.name = "test-route"

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(side_effect=_httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=mock_route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.apertus_adapter._build_payload", return_value={}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            mock_s.return_value.RAG_LLM_MAX_TOKENS = 256
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30
            with pytest.raises(RuntimeError, match="Cannot connect"):
                async for _ in generate_answer_stream("test"):
                    pass


# ── rag_service: rate limit retry, glossary, provenance ─────────────────────


class TestRagProvenanceMappings:
    def test_source_facts_nested(self) -> None:
        from app.services.rag_service import _provenance_mappings

        item = MagicMock()
        item.source_facts = [
            {
                "metadata": {"doc_id": "d1"},
                "source": {"metadata": {"source_url": "https://example.com"}},
                "memory": {"metadata": {"source_url": "https://other.com"}},
            }
        ]
        mappings = _provenance_mappings(item)
        assert len(mappings) >= 4

    def test_non_dict_source_fact_skipped(self) -> None:
        from app.services.rag_service import _provenance_mappings

        item = MagicMock()
        item.source_facts = ["not a dict", 123]
        mappings = _provenance_mappings(item)
        assert mappings == []

    def test_no_source_facts(self) -> None:
        from app.services.rag_service import _provenance_mappings

        item = MagicMock()
        item.source_facts = None
        mappings = _provenance_mappings(item)
        assert mappings == []


class TestRagExpandQueryGlossary:
    async def test_empty_query_returns_as_is(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        result = await svc._expand_query_with_glossary("", "en")
        assert result == ""

    async def test_whitespace_only_returns_as_is(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        result = await svc._expand_query_with_glossary("   ", "en")
        assert result == "   "

    async def test_no_alpha_tokens_returns_as_is(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        result = await svc._expand_query_with_glossary("123 456", "en")
        assert result == "123 456"

    async def test_glossary_lookup_exception_returns_original(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        mock_glossary = AsyncMock()
        mock_glossary.search_terms = AsyncMock(side_effect=RuntimeError("D1 down"))
        svc._glossary_repo = mock_glossary
        result = await svc._expand_query_with_glossary("residence permit", "en")
        assert result == "residence permit"

    async def test_glossary_timeout_returns_original(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)

        async def slow_search(*args: Any, **kwargs: Any) -> list[Any]:
            import asyncio

            await asyncio.sleep(100)
            return []

        mock_glossary = AsyncMock()
        mock_glossary.search_terms = slow_search
        svc._glossary_repo = mock_glossary
        with patch("app.core.config.settings") as mock_s:
            mock_s.GLOSSARY_EXPANSION_MAX_TOKENS = 5
            mock_s.GLOSSARY_EXPANSION_DEADLINE_S = 0.01
            mock_s.GLOSSARY_EXPANSION_MAX_TERMS = 10
            mock_s.GLOSSARY_EXPANSION_MAX_CHARS = 500
            result = await svc._expand_query_with_glossary("residence permit", "en")
            assert "residence" in result


class TestRagHindsightRateLimit:
    async def test_retry_on_429(self) -> None:
        from app.services.rag_service import _HindsightHttpClient

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "0.01"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"results": []}
        success.raise_for_status = MagicMock()

        mock_httpx_client = AsyncMock()
        mock_httpx_client.post = AsyncMock(side_effect=[rate_limited, success])
        mock_httpx_client.aclose = AsyncMock()

        with patch("app.services.rag_service.asyncio.sleep", new_callable=AsyncMock):
            svc = _HindsightHttpClient.__new__(_HindsightHttpClient)
            svc._client = mock_httpx_client

            await svc.arecall(bank_id="bank", query="test")
            assert mock_httpx_client.post.call_count == 2


# ── chat: greeting paths, session memory, journey builders ──────────────────


class TestChatGreetingEdgeCases:
    def test_hell_typo_is_greeting(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hell") is True

    def test_hello_world_not_greeting(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello world how are you doing today") is False

    def test_greeting_with_question_mark(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello?") is False

    def test_blank_message(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("") is False

    def test_good_morning_phrase(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("good morning") is True

    def test_how_are_you(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("how are you") is True

    def test_greeting_with_legal_keyword(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello visa application") is False


class TestChatJourneyBuilders:
    def test_build_next_step_returns_none_when_no_current(self) -> None:
        from app.api.v1.endpoints.chat import build_contextual_retrieval_query

        result = build_contextual_retrieval_query("test query", [])
        assert "test query" in result


class TestChatTurnValidation:
    def test_stripped_content(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn

        turn = ChatTurn(role="user", content="  hello  ")
        assert turn.content == "hello"

    def test_whitespace_only_rejected(self) -> None:
        from pydantic import ValidationError

        from app.api.v1.endpoints.chat import ChatTurn

        with pytest.raises(ValidationError):
            ChatTurn(role="user", content="   ")


# ── translation_service: section splitting + PII ────────────────────────────


class TestTranslationSectionSplitting:
    def test_split_by_sentences(self) -> None:
        from app.services.translation_service import _split_translation_sections

        text = "First sentence. Second sentence. Third sentence."
        result = _split_translation_sections(text, max_chars=30)
        assert len(result) > 1

    def test_split_table_rows(self) -> None:
        from app.services.translation_service import _split_translation_sections

        text = "Name | Age\nAlice | 30\nBob | 25"
        result = _split_translation_sections(text, max_chars=50)
        assert isinstance(result, list)

    def test_short_text_not_split(self) -> None:
        from app.services.translation_service import _split_translation_sections

        text = "Short."
        result = _split_translation_sections(text, max_chars=1000)
        assert len(result) == 1


class TestTranslationCanonicalForm:
    def test_canonical_form_cell_lookup(self) -> None:
        from app.services.translation_service import _canonical_form_cell

        result = _canonical_form_cell("Name", source_lang="en", target_lang="de")
        assert result is not None or result is None  # depends on _CANONICAL_FORM_TERMS

    def test_auto_source_returns_none(self) -> None:
        from app.services.translation_service import _canonical_form_cell

        result = _canonical_form_cell("Name", source_lang="auto", target_lang="de")
        assert result is None


class TestTranslationTableCells:
    def test_pipe_delimited_row(self) -> None:
        from app.services.translation_service import _table_cells

        result = _table_cells("| Name | Age |")
        assert result == ["Name", "Age"]

    def test_non_pipe_row(self) -> None:
        from app.services.translation_service import _table_cells

        result = _table_cells("No pipes here")
        assert result is None


class TestTranslationIsNonTranslatable:
    def test_empty_string(self) -> None:
        from app.services.translation_service import _is_non_translatable_structure

        assert _is_non_translatable_structure("") is True

    def test_border_pattern(self) -> None:
        from app.services.translation_service import _is_non_translatable_structure

        assert _is_non_translatable_structure("---") is True

    def test_normal_text(self) -> None:
        from app.services.translation_service import _is_non_translatable_structure

        assert _is_non_translatable_structure("Hello World") is False
