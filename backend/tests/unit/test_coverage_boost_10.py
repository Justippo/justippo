# SPDX-License-Identifier: MIT
"""Coverage batch 10: high-ROI gaps across workers_ai, apertus, translation,
rag, matrix client, search, pdf_reference_translation, and document_explanation."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as _httpx
import pytest

from app.core.config import Settings
from app.integrations.matrix.client import MatrixClient, MatrixClientError, MatrixTimeoutError


def _mock_settings(**overrides: Any) -> MagicMock:
    s = MagicMock(spec=Settings)
    s.CF_WORKERS_AI_API_TOKEN = overrides.get("CF_WORKERS_AI_API_TOKEN", "test-token")
    s.CF_ACCOUNT_ID = overrides.get("CF_ACCOUNT_ID", "acct123")
    s.CF_AI_GATEWAY_ID = overrides.get("CF_AI_GATEWAY_ID", "gw")
    s.CF_AI_GATEWAY_AUTH_HEADER = overrides.get("CF_AI_GATEWAY_AUTH_HEADER", "")
    s.CF_AI_GATEWAY_AUTH_VALUE = overrides.get("CF_AI_GATEWAY_AUTH_VALUE", "")
    s.RAG_LLM_MODEL = overrides.get("RAG_LLM_MODEL", "@cf/meta/llama-3.1-8b-instruct")
    s.RAG_LLM_MAX_TOKENS = overrides.get("RAG_LLM_MAX_TOKENS", 256)
    s.RAG_LLM_TIMEOUT_S = overrides.get("RAG_LLM_TIMEOUT_S", 30)
    s.NOT_DIAMOND_ENABLED = overrides.get("NOT_DIAMOND_ENABLED", False)
    return s


def _make_stream_response(
    lines: list[str],
    *,
    status_code: int = 200,
    error_body: bytes = b"",
) -> MagicMock:
    """Build a mock that works as `async with client.stream(...) as resp:`."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.aread = AsyncMock(return_value=error_body)

    async def _aiter():
        for line in lines:
            yield line

    resp.aiter_lines = MagicMock(return_value=_aiter())
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_httpx_client(resp: MagicMock | None = None) -> MagicMock:
    """Build a mock httpx.AsyncClient that yields resp on .stream(...).

    Also works for the non-streaming .post() path when resp is None
    (use client.post = AsyncMock(return_value=...).
    """
    client = MagicMock()
    if resp is not None:
        client.stream = MagicMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ─── workers_ai_adapter: _extract_answer edge cases ────────────────────────


class TestExtractAnswerEdgeCases:
    def test_native_result_response(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"result": {"response": "  hello  "}}
        assert _extract_answer(data) == "hello"

    def test_native_result_translated_text(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"result": {"translated_text": "bonjour"}}
        assert _extract_answer(data) == "bonjour"

    def test_bare_response_field(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"response": "  bare  "}
        assert _extract_answer(data) == "bare"

    def test_strip_false_preserves_whitespace(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"message": {"content": "  token  "}}]}
        result = _extract_answer(data, strip=False)
        assert result == "  token  "

    def test_delta_content_path(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"delta": {"content": "delta_text"}}]}
        assert _extract_answer(data) == "delta_text"

    def test_delta_content_empty_string_not_returned(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"delta": {"content": ""}}]}
        assert _extract_answer(data) == ""

    def test_empty_choices_list(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        assert _extract_answer({"choices": []}) == ""

    def test_result_with_empty_response(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"result": {"response": ""}}
        assert _extract_answer(data) == ""

    def test_none_message_content(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"message": {"content": None}}]}
        assert _extract_answer(data) == ""

    def test_non_dict_message(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"message": "string"}]}
        assert _extract_answer(data) == ""

    def test_non_dict_delta(self) -> None:
        from app.integrations.llm.workers_ai_adapter import _extract_answer

        data = {"choices": [{"delta": "string"}]}
        assert _extract_answer(data) == ""


# ─── workers_ai_adapter: generate_answer non-JSON + empty answer ──────────


class TestGenerateAnswerEdgeCases:
    @pytest.mark.asyncio()
    async def test_non_json_response_raises(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("no json")
        mock_resp.text = "not json"

        mock_client = _make_httpx_client()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(RuntimeError, match="non-JSON"),
        ):
            mock_s.return_value = _mock_settings()
            await generate_answer("test")

    @pytest.mark.asyncio()
    async def test_empty_answer_logs_warning(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"response": ""}}

        mock_client = _make_httpx_client()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            mock_s.return_value = _mock_settings()
            result = await generate_answer("test")
            assert result.answer == ""


# ─── workers_ai_adapter: generate_answer_stream error paths ───────────────


class TestAnswerStreamErrors:
    @pytest.mark.asyncio()
    async def test_stream_non_200_raises(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        resp = _make_stream_response([], status_code=500, error_body=b"err")
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
            pytest.raises(RuntimeError, match="streaming generation failed"),
        ):
            mock_s.return_value = _mock_settings()
            async for _ in generate_answer_stream("test"):
                pass

    @pytest.mark.asyncio()
    async def test_stream_http_error_raises(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=_httpx.HTTPError("conn"))
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        client = _make_httpx_client()
        client.stream = MagicMock(return_value=mock_resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
            pytest.raises(RuntimeError, match="HTTP error"),
        ):
            mock_s.return_value = _mock_settings()
            async for _ in generate_answer_stream("test"):
                pass

    @pytest.mark.asyncio()
    async def test_stream_neuron_budget_exhausted(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="999999")

        with patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s:
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test", neuron_budget_kv=mock_kv):
                tokens.append(t)
            assert any("budget" in t.lower() for t in tokens)

    @pytest.mark.asyncio()
    async def test_stream_empty_answer_yields_nothing(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        resp = _make_stream_response(
            [
                'data: {"result":{"response":""}}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test"):
                tokens.append(t)
            assert tokens == []


# ─── workers_ai_adapter: streaming happy path + SSE line skipping ──────────


class TestWorkersAIStreamHappyPath:
    @pytest.mark.asyncio()
    async def test_stream_yields_tokens(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        resp = _make_stream_response(
            [
                'data: {"choices":[{"delta":{"content":"hello"}}]}',
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test"):
                tokens.append(t)
            assert tokens == ["hello", " world"]

    @pytest.mark.asyncio()
    async def test_stream_skips_non_data_lines(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        resp = _make_stream_response(
            [
                "",
                "event: ping",
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test"):
                tokens.append(t)
            assert tokens == ["ok"]

    @pytest.mark.asyncio()
    async def test_stream_skips_invalid_json(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        resp = _make_stream_response(
            [
                "data: {bad json",
                'data: {"choices":[{"delta":{"content":"recovered"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test"):
                tokens.append(t)
            assert tokens == ["recovered"]

    @pytest.mark.asyncio()
    async def test_stream_budget_downgrade(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="7000")
        resp = _make_stream_response(
            [
                'data: {"choices":[{"delta":{"content":"answer"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._payload", return_value={}),
            patch("app.integrations.llm.workers_ai_adapter._select_model", return_value="m"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test", neuron_budget_kv=mock_kv):
                tokens.append(t)
            assert tokens == ["answer"]


# ─── greeting stream: happy path + errors ──────────────────────────────────


class TestGreetingStreamHappyPath:
    @pytest.mark.asyncio()
    async def test_greeting_stream_yields_tokens(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_greeting_stream

        resp = _make_stream_response(
            [
                'data: {"choices":[{"delta":{"content":"Hi!"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_greeting_stream("hello"):
                tokens.append(t)
            assert tokens == ["Hi!"]

    @pytest.mark.asyncio()
    async def test_greeting_skips_non_data_lines(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_greeting_stream

        resp = _make_stream_response(
            [
                "",
                "event: ping",
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_greeting_stream("hi"):
                tokens.append(t)
            assert tokens == ["ok"]

    @pytest.mark.asyncio()
    async def test_greeting_stream_non_200_returns_empty(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_greeting_stream

        resp = _make_stream_response([], status_code=500, error_body=b"err")
        client = _make_httpx_client(resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("app.integrations.llm.workers_ai_adapter._build_url", return_value="http://t"),
            patch("app.integrations.llm.workers_ai_adapter._build_headers", return_value={}),
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_greeting_stream("hi"):
                tokens.append(t)
            assert tokens == []


# ─── apertus_adapter: streaming errors + happy path ────────────────────────


class TestApertusStreamEdges:
    @pytest.mark.asyncio()
    async def test_stream_non_200_raises(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer_stream

        resp = _make_stream_response([], status_code=500, error_body=b"err")
        client = _make_httpx_client(resp)
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=client),
            pytest.raises(RuntimeError, match="streaming generation failed"),
        ):
            mock_s.return_value = _mock_settings()
            async for _ in generate_answer_stream("test"):
                pass

    @pytest.mark.asyncio()
    async def test_stream_timeout_raises(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer_stream

        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        client = _make_httpx_client()
        client.stream = MagicMock(return_value=mock_resp)
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=client),
            pytest.raises(RuntimeError, match="timed out"),
        ):
            mock_s.return_value = _mock_settings()
            async for _ in generate_answer_stream("test"):
                pass

    @pytest.mark.asyncio()
    async def test_stream_connect_error_raises(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer_stream

        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=_httpx.ConnectError("refused"))
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        client = _make_httpx_client()
        client.stream = MagicMock(return_value=mock_resp)
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=client),
            pytest.raises(RuntimeError, match="Cannot connect"),
        ):
            mock_s.return_value = _mock_settings()
            async for _ in generate_answer_stream("test"):
                pass

    @pytest.mark.asyncio()
    async def test_stream_yields_tokens(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer_stream

        resp = _make_stream_response(
            [
                'data: {"choices":[{"delta":{"content":"hello"}}]}',
                'data: {"choices":[{"delta":{"content":"world"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test"):
                tokens.append(t)
            assert tokens == ["hello", "world"]

    @pytest.mark.asyncio()
    async def test_stream_skips_invalid_json(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer_stream

        resp = _make_stream_response(
            [
                "data: {bad json",
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                "data: [DONE]",
            ]
        )
        client = _make_httpx_client(resp)
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=client),
        ):
            mock_s.return_value = _mock_settings()
            tokens = []
            async for t in generate_answer_stream("test"):
                tokens.append(t)
            assert tokens == ["ok"]


# ─── apertus_adapter: generate_answer errors ───────────────────────────────


class TestApertusGenerateAnswerErrors:
    @pytest.mark.asyncio()
    async def test_non_json_response(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        mock_resp.text = "html"
        mock_client = _make_httpx_client()
        mock_client.post = AsyncMock(return_value=mock_resp)
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(RuntimeError, match="non-JSON"),
        ):
            mock_s.return_value = _mock_settings()
            await generate_answer("test")

    @pytest.mark.asyncio()
    async def test_timeout_error(self) -> None:
        from app.integrations.llm.apertus_adapter import generate_answer

        mock_client = _make_httpx_client()
        mock_client.post = AsyncMock(side_effect=_httpx.TimeoutException("t"))
        route = MagicMock(name="public", url="https://a.test", headers={}, model="m")

        with (
            patch("app.integrations.llm.apertus_adapter._resolve_route", return_value=route),
            patch("app.integrations.llm.apertus_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(RuntimeError, match="timed out"),
        ):
            mock_s.return_value = _mock_settings()
            await generate_answer("test")


# ─── apertus_adapter: _parse_stream_delta ──────────────────────────────────


class TestApertusStreamDelta:
    def test_valid_delta(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        data = {"choices": [{"delta": {"content": "hello"}}]}
        assert _parse_stream_delta(data) == "hello"

    def test_non_dict_returns_empty(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta("not a dict") == ""

    def test_no_choices_returns_empty(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta({}) == ""

    def test_choices_empty_list(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta({"choices": []}) == ""

    def test_delta_no_content(self) -> None:
        from app.integrations.llm.apertus_adapter import _parse_stream_delta

        assert _parse_stream_delta({"choices": [{"delta": {"role": "assistant"}}]}) == ""


# ─── translation_service: _apply_glossary_enforcement_result ───────────────


class TestGlossaryEnforcementEdgeCases:
    def test_unsupported_source_lang_returns_early(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        pages = [{"page": 1, "text": "hello", "sections": []}]
        result = svc._apply_glossary_enforcement_result(pages, pages, "xx", "de")
        assert result.terms_applied == 0

    def test_unsupported_target_lang_returns_early(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        pages = [{"page": 1, "text": "hello", "sections": []}]
        result = svc._apply_glossary_enforcement_result(pages, pages, "en", "zz")
        assert result.terms_applied == 0

    def test_auto_source_lang_resolves_to_en(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        pages = [{"page": 1, "text": "hello", "sections": []}]
        with patch("app.services.translation_service.extract_terms", return_value=[]):
            result = svc._apply_glossary_enforcement_result(pages, pages, "auto", "de")
        assert result.terms_applied == 0


# ─── translation_service: _translate_section_content table cell paths ──────


class TestTranslateSectionTableCells:
    @pytest.mark.asyncio()
    async def test_canonical_form_cell_returns_canonical(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        with (
            patch("app.services.translation_service._table_cells", return_value=None),
            patch("app.services.translation_service._canonical_form_cell", return_value="München"),
        ):
            result = await svc._translate_section_content(
                text="München", source_lang="de", target_lang="en"
            )
            assert result == "München"

    @pytest.mark.asyncio()
    async def test_canonical_form_cell_none_calls_m2m(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        with (
            patch("app.services.translation_service._table_cells", return_value=None),
            patch("app.services.translation_service._canonical_form_cell", return_value=None),
            patch.object(svc, "_call_m2m100", new_callable=AsyncMock, return_value="translated"),
        ):
            result = await svc._translate_section_content(
                text="some text", source_lang="en", target_lang="de"
            )
            assert result == "translated"

    @pytest.mark.asyncio()
    async def test_empty_table_cells_preserved(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        with (
            patch(
                "app.services.translation_service._table_cells", return_value=["hello", "", "world"]
            ),
            patch("app.services.translation_service._canonical_form_cell", return_value=None),
            patch.object(svc, "_call_m2m100", new_callable=AsyncMock, return_value="t"),
        ):
            result = await svc._translate_section_content(
                text="table", source_lang="en", target_lang="de"
            )
            assert "t" in result


# ─── translation_service: _call_m2m100 non-@cf/ model path ────────────────


class TestCallM2m100FallbackModel:
    @pytest.mark.asyncio()
    async def test_non_cf_model_falls_back(self) -> None:
        from app.services.translation_service import TranslationService

        svc = TranslationService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"translated_text": "Hallo"}}

        mock_client = _make_httpx_client()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.services.translation_service.settings") as mock_s,
            patch("app.integrations.routing.not_diamond.NotDiamondRouter") as MockRouter,
            patch(
                "app.services.translation_service.get_gateway_url",
                return_value="https://gw.test.com",
            ),
            patch("app.services.translation_service.get_gateway_auth_headers", return_value={}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            mock_s.CF_WORKERS_AI_API_TOKEN = "test-token"
            MockRouter.return_value.route = AsyncMock(return_value="some-weird-model")
            result = await svc._call_m2m100("hello", "en", "de")
            assert result == "Hallo"


# ─── rag_service: RAGService.search ────────────────────────────────────────


class TestRAGServiceSearch:
    @pytest.mark.asyncio()
    async def test_search_with_results(self) -> None:
        from app.services.rag_service import RAGService

        svc = RAGService()
        with patch.object(svc, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = MagicMock(
                answer="doc text",
                sources=[{"title": "title", "url": "u", "excerpt": "doc text", "language": "en"}],
            )
            result = await svc.search("test query", language="en", top_k=1)
            assert result.answer == "doc text"

    @pytest.mark.asyncio()
    async def test_search_empty_results(self) -> None:
        from app.services.rag_service import RAGService

        svc = RAGService()
        with patch.object(svc, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = MagicMock(answer="", sources=[])
            result = await svc.search("test query")
            assert result.answer == ""


# ─── rag_service: HindsightRAGService.query CancelledError ─────────────────


class TestHindsightQueryCancelled:
    @pytest.mark.asyncio()
    async def test_query_cancelled_error_propagates(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        svc._bank_id = "b1"
        svc._hindsight_url = "https://h.test.com"
        svc._hindsight_api_key = "hk"
        svc._glossary_repo = None
        svc._client = AsyncMock()
        svc._client.arecall = AsyncMock(side_effect=asyncio.CancelledError)

        with pytest.raises(asyncio.CancelledError):
            await svc.query(q="test", top_k=5, lang="en")


# ─── matrix/client.py: check_health + _matrix_error ────────────────────────


class TestMatrixClientEdgeCases:
    def test_matrix_error_non_json_response(self) -> None:
        from app.integrations.matrix.client import _matrix_error

        resp = MagicMock()
        resp.status_code = 400
        resp.json.side_effect = ValueError("no json")
        err = _matrix_error(resp, operation="test_op", label="Test failed")
        assert err.status_code == 400
        assert err.errcode is None

    def test_matrix_error_with_errcode(self) -> None:
        from app.integrations.matrix.client import _matrix_error

        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {"errcode": "M_FORBIDDEN", "retry_after_ms": 1000}
        err = _matrix_error(resp, operation="invite", label="Invite failed")
        assert err.errcode == "M_FORBIDDEN"
        assert err.retry_after_ms == 1000

    def test_matrix_error_non_int_retry_after(self) -> None:
        from app.integrations.matrix.client import _matrix_error

        resp = MagicMock()
        resp.status_code = 429
        resp.json.return_value = {"errcode": "M_LIMIT_EXCEEDED", "retry_after_ms": "bad"}
        err = _matrix_error(resp, operation="send", label="Rate limited")
        assert err.retry_after_ms is None

    @pytest.mark.asyncio()
    async def test_check_health_timeout(self) -> None:
        with patch("app.integrations.matrix.client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http
            client = MatrixClient(access_token="tok", base_url="https://matrix.test.com")
            with pytest.raises(MatrixTimeoutError, match="timed out"):
                await client.check_health()

    @pytest.mark.asyncio()
    async def test_check_health_transport_error(self) -> None:
        with patch("app.integrations.matrix.client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=_httpx.HTTPError("conn"))
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http
            client = MatrixClient(access_token="tok", base_url="https://matrix.test.com")
            with pytest.raises(MatrixClientError, match="transport error"):
                await client.check_health()

    @pytest.mark.asyncio()
    async def test_check_health_non_200(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("app.integrations.matrix.client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http
            client = MatrixClient(access_token="tok", base_url="https://matrix.test.com")
            with pytest.raises(MatrixClientError, match="failed"):
                await client.check_health()

    @pytest.mark.asyncio()
    async def test_send_document_missing_content_uri(self) -> None:
        upload_resp = MagicMock()
        upload_resp.status_code = 200
        upload_resp.json.return_value = {}  # no content_uri

        client = MatrixClient(access_token="tok", base_url="https://matrix.test.com")
        with (
            patch.object(client, "_with_retry", new_callable=AsyncMock, return_value=upload_resp),
            patch("app.integrations.matrix.client.httpx.AsyncClient") as mock_cls,
        ):
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http
            with pytest.raises(MatrixClientError, match="missing content_uri"):
                await client.send_document("!room:test", "doc.pdf", b"data", "application/pdf")


# ─── pdf_reference_translation_service: _polygon_height dict points ────────


class TestPolygonHeightEdgeCases:
    def test_dict_point_format(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        polygon = [{"x": 0, "y": 0}, {"x": 1, "y": 10}]
        assert _polygon_height(polygon) == 10.0

    def test_dict_point_one_missing_y(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        polygon = [{"x": 0}, {"x": 1, "y": 5}]
        assert _polygon_height(polygon) is None

    def test_single_dict_point(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        polygon = [{"x": 0, "y": 5}]
        assert _polygon_height(polygon) is None

    def test_flat_polygon(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        polygon = [0, 5, 10, 5, 20, 5]
        assert _polygon_height(polygon) is None


# ─── pdf_reference_translation_service: _validate_translated_analysis ──────


class TestValidateTranslatedAnalysisEdgeCases:
    def test_form_label_leakage_detected(self) -> None:
        from app.services.ocr_service import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_analysis,
        )

        source = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="Vorname: Max\nFamilienname: Müller",
        )
        translated = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="Vorname: Max\nFamilienname: Müller",
        )
        with pytest.raises(PDFReferenceTranslationError) as exc_info:
            _validate_translated_analysis(source, translated, "de", "en", 1)
        assert exc_info.value.detail.code == "TRANSLATION_QUALITY_FAILED"


# ─── document_explanation_service: unsupported language fallback ────────────


class TestDocumentExplanationFallback:
    @pytest.mark.asyncio()
    async def test_unsupported_language_falls_back_to_en(self) -> None:
        from app.services.document_explanation_service import (
            DocumentClassification,
            explain_document,
        )
        from app.services.ocr_service import AzureDocumentAnalysis

        analysis = AzureDocumentAnalysis(
            model_id="test",
            api_version="v1",
            content="test content here",
        )
        classification = DocumentClassification(
            document_type="form",
            confidence=0.9,
            language_code="xx",
            form_type="application",
            geographic_relevance=[],
            keywords=[],
            document_type_raw="form",
        )
        mock_rag = AsyncMock()
        mock_rag.query = AsyncMock(return_value=[])

        result = await explain_document(
            analysis=analysis,
            classification=classification,
            language="xx",
            rag_service=mock_rag,
        )
        assert result.language == "en"


# ─── search.py: SSE ping keepalive ─────────────────────────────────────────


class TestSearchSSEPing:
    @pytest.mark.asyncio()
    async def test_sse_generator_imports_and_runs(self) -> None:
        from app.api.v1.endpoints.search import _sse_generator

        mock_rag = AsyncMock()
        mock_rag.query = AsyncMock(return_value=[])

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        frames = []
        async for frame in _sse_generator(
            q="test",
            top_k=5,
            rag=mock_rag,
            request=mock_request,
            lang="en",
        ):
            frames.append(frame)
            if len(frames) > 5:
                break
        assert isinstance(frames, list)
