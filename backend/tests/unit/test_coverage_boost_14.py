"""Coverage boost batch 14 — workers_ai greeting/answer streaming error responses."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── workers_ai_adapter: greeting streaming HTTP error response ──────


class TestWorkersAIGreetingHTTPErrorResponse:
    @pytest.mark.asyncio()
    async def test_greeting_non_200_response_returns_empty(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_greeting_stream

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.aread = AsyncMock(return_value=b"Internal Server Error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.aiter_lines = AsyncMock(return_value=AsyncIterator([]))

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.integrations.llm.workers_ai_adapter.is_enabled", return_value=True),
        ):
            mock_s.return_value = MagicMock()
            mock_s.return_value.CF_ACCOUNT_ID = "acc1"
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30

            tokens = []
            async for token in generate_greeting_stream("Hello"):
                tokens.append(token)
            assert len(tokens) == 0


# ─── workers_ai_adapter: answer streaming HTTP error response ────────


class TestWorkersAIAnswerHTTPErrorResponse:
    @pytest.mark.asyncio()
    async def test_answer_non_200_response_raises(self) -> None:
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.aread = AsyncMock(return_value=b"Internal Server Error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_resp)

        with (
            patch("app.integrations.llm.workers_ai_adapter._get_settings") as mock_s,
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.integrations.llm.workers_ai_adapter.is_enabled", return_value=True),
        ):
            mock_s.return_value = MagicMock()
            mock_s.return_value.CF_ACCOUNT_ID = "acc1"
            mock_s.return_value.CF_WORKERS_AI_API_TOKEN = "tok"
            mock_s.return_value.NOT_DIAMOND_ENABLED = False
            mock_s.return_value.RAG_LLM_TIMEOUT_S = 30

            with pytest.raises(RuntimeError, match="failed"):
                async for _ in generate_answer_stream("prompt"):
                    pass


class AsyncIterator:
    def __init__(self, items: list[str]) -> None:
        self._items = items
        self._index = 0

    def __aiter__(self) -> Any:
        return self

    async def __anext__(self) -> str:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item
