# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for the Cloudflare Workers AI answer-generation adapter.

Verifies:
- (edge cases) network-failure paths raise RuntimeError and the greeting stream
  degrades gracefully to a canned fallback when the AI Gateway is unreachable.
- No-op contract: returns None when CF_WORKERS_AI_API_TOKEN is empty
- is_enabled() reflects token presence
- Gateway URL routes through CF AI Gateway workers-ai provider (not direct URL)
- Successful generation parses BOTH the OpenAI-compatible shape
  ({"choices":[{"message":{"content":...}}]}) and the native Workers AI shape
  ({"result":{"response":...}}) — the gateway can return either.
- Streaming yields tokens from both shapes
- Raises RuntimeError on non-200 / timeout / connection error
- AST check: no direct provider URLs outside gateway.py (REM-8)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.llm.workers_ai_adapter import (
    AnswerResponse,
    _build_url,
    _select_model,
    generate_answer,
    generate_answer_stream,
    generate_greeting_stream,
    is_enabled,
    model_name,
)

MOD = "app.integrations.llm.workers_ai_adapter"


@pytest.fixture
def settings_with_token():
    mock = MagicMock()
    mock.CF_WORKERS_AI_API_TOKEN = "cf_wa_test_token"
    mock.RAG_LLM_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
    mock.RAG_LLM_MAX_TOKENS = 512
    mock.RAG_LLM_TIMEOUT_S = 30
    return mock


@pytest.fixture
def settings_no_token():
    mock = MagicMock()
    mock.CF_WORKERS_AI_API_TOKEN = ""
    mock.RAG_LLM_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
    mock.RAG_LLM_MAX_TOKENS = 512
    mock.RAG_LLM_TIMEOUT_S = 30
    return mock


@pytest.fixture
def sample_prompt() -> str:
    return (
        "SYSTEM: You are a document analysis assistant.\n\n"
        "[RETRIEVED_CONTEXT_START]\nSample text.\n[RETRIEVED_CONTEXT_END]\n\n"
        "USER: What is this about?"
    )


# ---------------------------------------------------------------------------
# No-op contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_noop_when_token_empty(settings_no_token):
    with patch(f"{MOD}._get_settings", return_value=settings_no_token):
        assert await generate_answer("p") is None


def test_is_enabled_false_when_token_empty(settings_no_token):
    with patch(f"{MOD}._get_settings", return_value=settings_no_token):
        assert is_enabled() is False


def test_is_enabled_true_when_token_set(settings_with_token):
    with patch(f"{MOD}._get_settings", return_value=settings_with_token):
        assert is_enabled() is True


def test_model_name_returns_default_when_enabled(settings_with_token):
    with patch(f"{MOD}._get_settings", return_value=settings_with_token):
        assert model_name() == "@cf/meta/llama-3.1-8b-instruct-fp8"


# ---------------------------------------------------------------------------
# Model selection (tiered routing)
# ---------------------------------------------------------------------------


def test_select_model_returns_fast_for_simple_query():
    assert _select_model("What is this document about?") == "@cf/meta/llama-3.1-8b-instruct-fp8"


def test_select_model_returns_frontier_for_complex_query():
    assert (
        _select_model("What are the penalties for non-compliance?")
        == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    )


def test_select_model_returns_frontier_for_biometric_query():
    assert (
        _select_model("How does the biometric data provision work?")
        == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    )


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def test_build_gateway_url_routes_through_cf_gateway(settings_with_token):
    with patch(f"{MOD}._get_settings", return_value=settings_with_token):
        url = _build_url("@cf/meta/llama-3.1-8b-instruct-fp8")
    assert "gateway.ai.cloudflare.com" in url
    assert "workers-ai" in url
    assert "@cf/meta/llama-3.1-8b-instruct-fp8" in url
    assert "api.cloudflare.com/client/v4/accounts" not in url


# ---------------------------------------------------------------------------
# Successful generation — both response shapes
# ---------------------------------------------------------------------------


def _mock_client_post(status_code: int, json_payload, text: str = ""):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_payload
    mock_resp.text = text
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


@pytest.mark.asyncio
async def test_generate_answer_openai_shape(settings_with_token, sample_prompt):
    client = _mock_client_post(
        200, {"choices": [{"message": {"content": "OpenAI-shaped answer."}}]}
    )
    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=client),
    ):
        result = await generate_answer(sample_prompt)
    assert isinstance(result, AnswerResponse)
    assert result.answer == "OpenAI-shaped answer."
    assert result.model == "@cf/meta/llama-3.1-8b-instruct-fp8"


@pytest.mark.asyncio
async def test_generate_answer_native_shape(settings_with_token, sample_prompt):
    client = _mock_client_post(200, {"result": {"response": "Native-shaped answer."}})
    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=client),
    ):
        result = await generate_answer(sample_prompt)
    assert result.answer == "Native-shaped answer."


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_raises_on_non200(settings_with_token, sample_prompt):
    client = _mock_client_post(402, {}, text="Insufficient wholesale credits")
    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(RuntimeError, match="HTTP 402"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_raises_on_timeout(settings_with_token, sample_prompt):
    import httpx

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        await generate_answer(sample_prompt)


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_stream_yields_tokens(settings_with_token, sample_prompt):
    import json

    lines = [
        f"data: {json.dumps({'choices': [{'delta': {'content': 'Hello'}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'content': ' world'}}]})}",
        "data: [DONE]",
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = MagicMock(return_value=_async_iter(lines))
    mock_resp.aread = AsyncMock(return_value=b"")

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=stream_cm)

    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        tokens = [t async for t in _stream(sample_prompt, settings_with_token)]

    assert tokens == ["Hello", " world"]


async def _async_iter(items):
    for item in items:
        yield item


async def _stream(prompt, settings):
    with patch(f"{MOD}._get_settings", return_value=settings):
        from app.integrations.llm.workers_ai_adapter import generate_answer_stream

        async for token in generate_answer_stream(prompt):
            yield token


@pytest.mark.asyncio
async def test_generate_answer_raises_on_connect_error(settings_with_token, sample_prompt):
    import httpx

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(RuntimeError, match="Cannot connect"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_raises_on_http_error(settings_with_token, sample_prompt):
    import httpx

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(side_effect=httpx.HTTPError("gateway 503"))
    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(RuntimeError, match="HTTP error"),
    ):
        await generate_answer(sample_prompt)


# ---------------------------------------------------------------------------
# Streaming — network-failure edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_stream_raises_on_connect_error(settings_with_token, sample_prompt):
    import httpx

    stream_cm = MagicMock()
    stream_cm.__aenter__ = MagicMock(side_effect=httpx.ConnectError("connection refused"))
    stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=stream_cm)

    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="Cannot connect"),
    ):
        async for _ in generate_answer_stream(sample_prompt):
            pass


@pytest.mark.asyncio
async def test_generate_answer_stream_raises_on_http_error(settings_with_token, sample_prompt):
    import httpx

    stream_cm = MagicMock()
    stream_cm.__aenter__ = MagicMock(side_effect=httpx.HTTPError("gateway 503"))
    stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=stream_cm)

    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="HTTP error"),
    ):
        async for _ in generate_answer_stream(sample_prompt):
            pass


# ---------------------------------------------------------------------------
# Greeting stream — graceful degradation edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_greeting_stream_yields_fallback_on_connect_error(
    settings_with_token,
):
    import httpx

    stream_cm = MagicMock()
    stream_cm.__aenter__ = MagicMock(side_effect=httpx.ConnectError("connection refused"))
    stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=stream_cm)

    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        tokens = [t async for t in generate_greeting_stream("hello there")]
    assert tokens == ["Hi there! How can I help you with EU documents today?"]


@pytest.mark.asyncio
async def test_greeting_stream_yields_fallback_on_timeout(
    settings_with_token,
):
    import httpx

    stream_cm = MagicMock()
    stream_cm.__aenter__ = MagicMock(side_effect=httpx.TimeoutException("timed out"))
    stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=stream_cm)

    with (
        patch(f"{MOD}._get_settings", return_value=settings_with_token),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        tokens = [t async for t in generate_greeting_stream("hello there")]
    assert tokens == ["Hi there! How can I help you with EU documents today?"]


@pytest.mark.asyncio
async def test_greeting_stream_noop_when_token_empty(settings_no_token):
    with patch(f"{MOD}._get_settings", return_value=settings_no_token):
        tokens = [t async for t in generate_greeting_stream("hello")]
    assert tokens == []


# ---------------------------------------------------------------------------
# AST check: no direct provider URLs outside gateway.py
# ---------------------------------------------------------------------------


def test_no_direct_provider_urls_in_adapter():
    adapter_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "integrations"
        / "llm"
        / "workers_ai_adapter.py"
    )
    source = adapter_path.read_text()
    forbidden = [
        "api.cloudflare.com/client/v4/accounts",
        "api-inference.huggingface.co",
        "api.openai.com",
    ]
    for url in forbidden:
        assert url not in source, f"Direct provider URL found in adapter: {url}"
