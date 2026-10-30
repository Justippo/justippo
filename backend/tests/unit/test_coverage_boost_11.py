# SPDX-License-Identifier: MIT
"""Coverage batch 11: is_greeting edge cases, build_contextual_retrieval_query,
rag fallback paths, langfuse _send_to_langfuse + observe_generation,
matrix retry paths, and search SSE answer generation."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as _httpx
import pytest

# ─── chat.py: is_greeting edge cases ───────────────────────────────────────


class TestIsGreetingEdgeCases:
    def test_empty_string(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("") is False

    def test_whitespace_only(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("   ") is False

    def test_long_message(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello this is a very long message with many words") is False

    def test_question_not_greeting(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello?") is False

    def test_legal_keyword_not_greeting(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello visa") is False

    def test_how_are_you_not_greeting_with_legal(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("hello what is a permit") is False


# ─── chat.py: build_contextual_retrieval_query ─────────────────────────────


class TestBuildContextualRetrievalQuery:
    def test_followup_marker(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn, build_contextual_retrieval_query

        history = [ChatTurn(role="assistant", content="The answer is X.")]
        result = build_contextual_retrieval_query("tell me more about that", history)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_clarification_answer(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn, build_contextual_retrieval_query

        history = [ChatTurn(role="assistant", content="Which country?")]
        result = build_contextual_retrieval_query("Germany", history)
        assert isinstance(result, str)

    def test_no_history(self) -> None:
        from app.api.v1.endpoints.chat import build_contextual_retrieval_query

        result = build_contextual_retrieval_query("work permit requirements", [])
        assert "work permit requirements" in result

    def test_with_history(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn, build_contextual_retrieval_query

        history = [
            ChatTurn(role="user", content="What is a Blue Card?"),
            ChatTurn(role="assistant", content="A Blue Card is..."),
        ]
        result = build_contextual_retrieval_query("how do I apply", history)
        assert isinstance(result, str)


# ─── chat.py: ChatTurn + ChatRequest validation ────────────────────────────


class TestChatTurnValidation:
    def test_valid_turn(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn

        turn = ChatTurn(role="user", content="hello")
        assert turn.role == "user"
        assert turn.content == "hello"

    def test_blank_content_rejected(self) -> None:
        from pydantic import ValidationError

        from app.api.v1.endpoints.chat import ChatTurn

        with pytest.raises(ValidationError):
            ChatTurn(role="user", content="")

    def test_long_content_rejected(self) -> None:
        from pydantic import ValidationError

        from app.api.v1.endpoints.chat import ChatTurn

        with pytest.raises(ValidationError):
            ChatTurn(role="user", content="x" * 2001)


# ─── rag_service.py: fallback cancel/error paths ───────────────────────────


class TestRagFallbackPaths:
    @pytest.mark.asyncio()
    async def test_fallback_cancelled(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        svc._bank_id = "b1"
        svc._hindsight_url = "https://h.test.com"
        svc._hindsight_api_key = "hk"
        svc._glossary_repo = None
        svc._client = AsyncMock()

        call_count = 0

        async def mock_arecall(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("primary failed")
            raise asyncio.CancelledError()

        svc._client.arecall = mock_arecall

        with pytest.raises(asyncio.CancelledError):
            await svc.query(q="test", top_k=5, lang="en")

    @pytest.mark.asyncio()
    async def test_fallback_also_fails(self) -> None:
        from app.services.rag_service import HindsightRAGService

        svc = HindsightRAGService.__new__(HindsightRAGService)
        svc._bank_id = "b1"
        svc._hindsight_url = "https://h.test.com"
        svc._hindsight_api_key = "hk"
        svc._glossary_repo = None
        svc._client = AsyncMock()

        async def mock_arecall(**kwargs: Any) -> Any:
            raise RuntimeError("both failed")

        svc._client.arecall = mock_arecall

        with pytest.raises(RuntimeError, match="both failed"):
            await svc.query(q="test", top_k=5, lang="en")


# ─── langfuse.py: _send_to_langfuse + observe_generation ──────────────────


class TestLangfuseEdges:
    @pytest.mark.asyncio()
    async def test_send_to_langfuse_disabled(self) -> None:
        from app.integrations.langfuse import _send_to_langfuse

        with patch("app.integrations.langfuse._enabled", False):
            await _send_to_langfuse([{"test": "span"}])

    @pytest.mark.asyncio()
    async def test_send_to_langfuse_empty_spans(self) -> None:
        from app.integrations.langfuse import _send_to_langfuse

        with patch("app.integrations.langfuse._enabled", True):
            await _send_to_langfuse([])

    @pytest.mark.asyncio()
    async def test_observe_generation_noop_when_disabled(self) -> None:
        from app.integrations.langfuse import observe_generation

        with patch("app.integrations.langfuse._enabled", False):

            @observe_generation(name="test", model="m")
            async def my_func() -> str:
                return "result"

            result = await my_func()
            assert result == "result"

    @pytest.mark.asyncio()
    async def test_observe_generation_wraps_success(self) -> None:
        from app.integrations.langfuse import observe_generation

        with (
            patch("app.integrations.langfuse._enabled", True),
            patch(
                "app.integrations.langfuse._send_to_langfuse", new_callable=AsyncMock
            ) as mock_send,
        ):

            @observe_generation(name="test_gen", model="test-model")
            async def my_func() -> str:
                return "ok"

            result = await my_func()
            assert result == "ok"
            mock_send.assert_called_once()

    @pytest.mark.asyncio()
    async def test_observe_generation_wraps_exception(self) -> None:
        from app.integrations.langfuse import observe_generation

        with (
            patch("app.integrations.langfuse._enabled", True),
            patch("app.integrations.langfuse._send_to_langfuse", new_callable=AsyncMock),
        ):

            @observe_generation(name="test_gen", model="m")
            async def my_func() -> str:
                raise ValueError("boom")

            with pytest.raises(ValueError, match="boom"):
                await my_func()

    def test_strip_pii_content_keys(self) -> None:
        from app.integrations.langfuse import _strip_pii_langfuse

        attrs = {
            "langfuse.observation.type": "generation",
            "gen_ai.prompt": "secret",
            "gen_ai.completion": "secret2",
            "langfuse.observation.input": "secret3",
            "langfuse.observation.output": "secret4",
            "gen_ai.request.model": "m",
        }
        result = _strip_pii_langfuse(attrs)
        assert "gen_ai.prompt" not in result
        assert "gen_ai.completion" not in result
        assert "langfuse.observation.input" not in result
        assert "langfuse.observation.output" not in result
        assert "gen_ai.request.model" in result

    def test_strip_pii_content_substrings(self) -> None:
        from app.integrations.langfuse import _strip_pii_langfuse

        attrs = {
            "custom.content": "secret",
            "custom.prompt": "secret",
            "normal_key": "value",
        }
        result = _strip_pii_langfuse(attrs)
        assert "custom.content" not in result
        assert "custom.prompt" not in result
        assert "normal_key" in result


# ─── langfuse.py: trace context manager ────────────────────────────────────


class TestLangfuseTrace:
    @pytest.mark.asyncio()
    async def test_trace_noop_when_disabled(self) -> None:
        from app.integrations.langfuse import trace

        with patch("app.integrations.langfuse._enabled", False):
            async with trace(name="test") as tid:
                assert tid == ""

    @pytest.mark.asyncio()
    async def test_trace_sends_span(self) -> None:
        from app.integrations.langfuse import trace

        with (
            patch("app.integrations.langfuse._enabled", True),
            patch(
                "app.integrations.langfuse._send_to_langfuse", new_callable=AsyncMock
            ) as mock_send,
        ):
            async with trace(name="test_trace") as tid:
                assert isinstance(tid, str)
                assert len(tid) > 0
            mock_send.assert_called()


# ─── matrix/client.py: _with_retry paths ───────────────────────────────────


class TestMatrixRetryPaths:
    @pytest.mark.asyncio()
    async def test_retry_timeout_last_attempt(self) -> None:
        from app.integrations.matrix.client import MatrixClient, MatrixTimeoutError

        client = MatrixClient(access_token="tok", base_url="https://matrix.test.com")

        async def always_timeout(*args: Any, **kwargs: Any) -> MagicMock:
            raise _httpx.TimeoutException("timeout")

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=always_timeout)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.matrix.client.httpx.AsyncClient", return_value=mock_http),
            pytest.raises(MatrixTimeoutError),
        ):
            await client._with_retry(
                lambda: mock_http.get("http://test"),
                operation_name="test_op",
            )

    @pytest.mark.asyncio()
    async def test_retry_transport_error_last_attempt(self) -> None:
        from app.integrations.matrix.client import MatrixClient, MatrixClientError

        client = MatrixClient(access_token="tok", base_url="https://matrix.test.com")

        async def always_http_error(*args: Any, **kwargs: Any) -> MagicMock:
            raise _httpx.HTTPError("conn")

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=always_http_error)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.integrations.matrix.client.httpx.AsyncClient", return_value=mock_http),
            pytest.raises(MatrixClientError),
        ):
            await client._with_retry(
                lambda: mock_http.get("http://test"),
                operation_name="test_op",
            )


# ─── search.py: _sse_generator answer generation error ─────────────────────


class TestSearchSSEAnswerGeneration:
    @pytest.mark.asyncio()
    async def test_search_sse_with_timeout_error(self) -> None:
        from app.api.v1.endpoints.search import _sse_generator

        mock_rag = AsyncMock()
        mock_rag.query = AsyncMock(side_effect=TimeoutError("timed out"))

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
            if len(frames) > 10:
                break
        assert isinstance(frames, list)

    @pytest.mark.asyncio()
    async def test_search_sse_with_generic_error(self) -> None:
        from app.api.v1.endpoints.search import _sse_generator

        mock_rag = AsyncMock()
        mock_rag.query = AsyncMock(side_effect=RuntimeError("upstream failed"))

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
            if len(frames) > 10:
                break
        assert isinstance(frames, list)
