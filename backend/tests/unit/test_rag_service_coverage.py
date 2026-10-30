"""Coverage for Hindsight recall retry + RAG stream error handlers.

DRY: ``_HindsightHttpClient.arecall`` funnels through ``httpx.AsyncClient``.
A single ``MockTransport`` returns 429 (rate-limited) then 200 to exercise the
retry/backoff path (both ``Retry-After`` parse branches) and the happy path.
The streaming search error handlers are exercised by making ``generate_answer_stream``
raise (RuntimeError / generic Exception) while answer generation is enabled.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import rag_service
from app.services.rag_service import RAGService, _HindsightHttpClient, _RecallResponse

# Capture the REAL httpx.AsyncClient before any test patches it.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_for(handler, base_url: str = "https://hindsight.example.com") -> httpx.AsyncClient:
    return _REAL_ASYNC_CLIENT(base_url=base_url, transport=httpx.MockTransport(handler))


@pytest.fixture
def patch_httpx(monkeypatch: pytest.MonkeyPatch):
    store = {}

    def _apply(factory) -> None:
        store["factory"] = factory
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: factory())

    return _apply


@pytest.mark.asyncio
async def test_arecall_success(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"text": "x"}]})

    patch_httpx(lambda: _client_for(handler))
    client = _HindsightHttpClient(base_url="https://hindsight.example.com", api_key="k")
    resp = await client.arecall(bank_id="b1", query="q")
    assert isinstance(resp, _RecallResponse)


@pytest.mark.asyncio
async def test_arecall_429_retry_invalid_retry_after(
    patch_httpx, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "not-a-float"})
        return httpx.Response(200, json={"results": [{"text": "x"}]})

    patch_httpx(lambda: _client_for(handler))
    client = _HindsightHttpClient(base_url="https://hindsight.example.com", api_key="k")
    resp = await client.arecall(bank_id="b1", query="q")
    assert calls["n"] == 2
    assert isinstance(resp, _RecallResponse)


@pytest.mark.asyncio
async def test_arecall_429_retry_valid_retry_after(
    patch_httpx, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"results": [{"text": "x"}]})

    patch_httpx(lambda: _client_for(handler))
    client = _HindsightHttpClient(base_url="https://hindsight.example.com", api_key="k")
    resp = await client.arecall(bank_id="b1", query="q")
    assert calls["n"] == 2
    assert isinstance(resp, _RecallResponse)


@pytest.mark.asyncio
async def test_search_stream_runtime_error_handler(monkeypatch) -> None:
    # Force answer generation enabled and make the stream raise RuntimeError.
    monkeypatch.setattr("app.integrations.llm.answer_generation.is_enabled", lambda: True)

    async def _boom(prompt: str):
        raise RuntimeError("apertus down")
        yield  # pragma: no cover - unreachable, makes this an async generator

    monkeypatch.setattr("app.integrations.llm.answer_generation.generate_answer_stream", _boom)
    # Avoid a real Hindsight call; return one fake result.
    monkeypatch.setattr(
        rag_service.HindsightRAGService,
        "query",
        AsyncMock(return_value=[{"text": "x"}]),
    )

    svc = RAGService()
    frames = [f async for f in svc.stream_search("query", language="en")]
    # Expect at least a result frame, an answer_error frame, and a done frame.
    events = [f for f in frames if f.startswith("event:")]
    assert any("answer_error" in e for e in events)
    assert any("done" in e for e in events)


@pytest.mark.asyncio
async def test_search_stream_generic_error_handler(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.llm.answer_generation.is_enabled", lambda: True)

    async def _boom(prompt: str):
        raise ValueError("weird")
        yield  # pragma: no cover - unreachable, makes this an async generator

    monkeypatch.setattr("app.integrations.llm.answer_generation.generate_answer_stream", _boom)
    monkeypatch.setattr(
        rag_service.HindsightRAGService,
        "query",
        AsyncMock(return_value=[{"text": "x"}]),
    )

    svc = RAGService()
    frames = [f async for f in svc.stream_search("query", language="en")]
    events = [f for f in frames if f.startswith("event:")]
    assert any("error" in e for e in events)
    assert any("done" in e for e in events)
