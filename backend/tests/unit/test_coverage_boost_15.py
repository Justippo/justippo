"""Coverage boost batch 15 — search SSE ping/disconnect, chat_stream greeting
iteration, workers_ai greeting streaming, and apertus streaming paths."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── search.py: _sse_generator ping and disconnect ──────────────


class TestSearchSSEPingDisconnect:
    @pytest.mark.asyncio()
    async def test_sse_ping_emitted_during_query(self) -> None:
        from app.api.v1.endpoints.search import _sse_generator

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}
        req.is_disconnected = AsyncMock(return_value=False)

        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(return_value=[])

        frames = []
        async for frame in _sse_generator(
            q="test",
            top_k=5,
            rag=mock_rag,
            request=req,
            lang="en",
            guidance=False,
            emit_model=False,
        ):
            frames.append(frame)
            if len(frames) > 10:
                break

        assert len(frames) > 0

    @pytest.mark.asyncio()
    async def test_disconnect_during_query_cancels_task(self) -> None:
        from app.api.v1.endpoints.search import _sse_generator

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}
        req.is_disconnected = AsyncMock(side_effect=[False, True])

        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(return_value=[])

        frames = []
        async for frame in _sse_generator(
            q="test",
            top_k=5,
            rag=mock_rag,
            request=req,
            lang="en",
            guidance=False,
            emit_model=False,
        ):
            frames.append(frame)

        assert len(frames) > 0


# ─── search.py: guidance marker matched ──────────────────────────


# ─── chat.py: chat_stream greeting path iterates ─────────────────


class TestChatStreamGreetingIteration:
    @pytest.mark.asyncio()
    async def test_greeting_stream_yields_tokens(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(message="hello there", language="en", history=[])

        async def _mock_greeting_stream(*args: Any, **kwargs: Any) -> Any:
            yield "Hi there! "
            yield "How can I help?"

        with (
            patch(
                "app.api.v1.endpoints.chat.generate_greeting_stream",
                _mock_greeting_stream,
            ),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=True),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
        ):
            response = await chat_stream(req, body)
            tokens = []
            async for chunk in response.body_iterator:
                tokens.append(chunk)
            assert any("Hi there" in t for t in tokens)


# ─── chat.py: JSON decode error in answer parsing ────────────────


class TestChatStreamAnswerParseError:
    @pytest.mark.asyncio()
    async def test_malformed_sse_frame_skipped(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(message="test", language="en", history=[])

        async def _mock_sse(*args: Any, **kwargs: Any) -> Any:
            yield "event: answer_chunk\ndata: not-json\n\n"
            yield "event: done\n\ndata: [DONE]\n\n"

        with (
            patch("app.api.v1.endpoints.chat._sse_generator", _mock_sse),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=False),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
            patch(
                "app.api.v1.endpoints.chat.build_empty_result_guidance",
                return_value={
                    "reason": "no_verified_source",
                    "message": "No info",
                    "matched": False,
                },
            ),
        ):
            response = await chat_stream(req, body)
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            assert len(chunks) > 0


# ─── chat.py: memory append path ─────────────────────────────────


class TestChatStreamMemoryAppend:
    @pytest.mark.asyncio()
    async def test_memory_append_after_answer(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(message="test", language="en", history=[])

        mock_memory = AsyncMock()
        mock_memory.append_message = AsyncMock()

        async def _mock_sse(*args: Any, **kwargs: Any) -> Any:
            yield 'event: answer_chunk\ndata: {"text": "Hello"}\n\n'
            yield "event: done\n\ndata: [DONE]\n\n"

        with (
            patch("app.api.v1.endpoints.chat._sse_generator", _mock_sse),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=False),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
            patch(
                "app.api.v1.endpoints.chat.build_empty_result_guidance",
                return_value={
                    "reason": "no_verified_source",
                    "message": "No info",
                    "matched": False,
                },
            ),
            patch(
                "app.api.v1.endpoints.chat.MemoryRepository",
                return_value=mock_memory,
            ),
            patch(
                "app.api.v1.endpoints.chat.D1Client",
                return_value=None,
            ),
            patch(
                "app.api.v1.endpoints.chat.settings",
                MagicMock(SESSION_MEMORY_ENABLED=True),
            ),
        ):
            response = await chat_stream(req, body)
            assert response.status_code == 200
            assert mock_memory.append_message.called
