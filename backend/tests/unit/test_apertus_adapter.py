# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for Apertus 8B adapter.

Apertus runs **free** via the Public AI utility over two routes, resolved by
``_resolve_route()`` in priority order:
  1. Direct Public AI platform (api.publicai.co) when PUBLICAI_API_KEY is set.
  2. HF Inference Providers router (:publicai suffix) when only HF_API_TOKEN set.

Tests verify:
- No-op contract: returns None when BOTH credentials are empty
- is_enabled() reflects credential presence correctly
- Route resolution prefers the direct Public AI platform over the HF router
- Direct route uses api.publicai.co, the bare model id, and a User-Agent header
- HF route uses the Inference Providers router and appends the ``:publicai`` suffix
- Successful generation parses OpenAI chat-completion responses
- Raises RuntimeError on non-200 / timeout / connection / non-JSON
- Special-token stripping cleans echoed control tokens
- No direct/legacy HuggingFace API URLs live in the adapter
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.llm.apertus_adapter import (
    _DEFAULT_APERTUS_MODEL,
    _PUBLICAI_DIRECT_MODEL,
    ApertusResponse,
    _parse_chat_completion,
    _resolve_hf_model,
    _resolve_route,
    generate_answer,
    is_enabled,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings_with_token():
    """Settings with only HF_API_TOKEN set → HF router fallback route."""
    mock = MagicMock()
    mock.PUBLICAI_API_KEY = ""
    mock.HF_API_TOKEN = "hf_test_token_123"
    mock.RAG_LLM_MODEL = "swiss-ai/Apertus-8B-Instruct-2509"
    mock.RAG_LLM_MAX_TOKENS = 512
    mock.RAG_LLM_TIMEOUT_S = 30
    return mock


@pytest.fixture
def mock_settings_with_publicai():
    """Settings with PUBLICAI_API_KEY set → preferred direct Public AI route."""
    mock = MagicMock()
    mock.PUBLICAI_API_KEY = "pai_test_key_456"
    mock.HF_API_TOKEN = "hf_test_token_123"  # present but must be ignored
    mock.RAG_LLM_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
    mock.RAG_LLM_MAX_TOKENS = 512
    mock.RAG_LLM_TIMEOUT_S = 30
    return mock


@pytest.fixture
def mock_settings_no_token():
    """Settings with BOTH credentials empty (no-op)."""
    mock = MagicMock()
    mock.PUBLICAI_API_KEY = ""
    mock.HF_API_TOKEN = ""
    mock.RAG_LLM_MODEL = "swiss-ai/Apertus-8B-Instruct-2509"
    mock.RAG_LLM_MAX_TOKENS = 512
    mock.RAG_LLM_TIMEOUT_S = 30
    return mock


@pytest.fixture
def sample_prompt() -> str:
    """A RAG prompt from build_rag_prompt()."""
    return (
        "SYSTEM: You are a document analysis assistant.\n\n"
        "[RETRIEVED_CONTEXT_START]\nSample document text.\n[RETRIEVED_CONTEXT_END]\n\n"
        "USER: What is this document about?"
    )


@pytest.fixture
def mock_chat_completion_response():
    """Mock OpenAI-compatible chat completion response."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "This document is about EU residence permits.",
                }
            }
        ]
    }


# ---------------------------------------------------------------------------
# No-op contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_noop_when_both_credentials_empty(mock_settings_no_token):
    """generate_answer returns None when neither credential is set."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_no_token
    ):
        result = await generate_answer("test prompt")
    assert result is None


def test_is_enabled_false_when_both_credentials_empty(mock_settings_no_token):
    """is_enabled returns False when neither credential is set."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_no_token
    ):
        assert is_enabled() is False


def test_is_enabled_true_when_hf_token_set(mock_settings_with_token):
    """is_enabled returns True when HF_API_TOKEN is set."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_with_token
    ):
        assert is_enabled() is True


def test_is_enabled_true_when_publicai_key_set(mock_settings_with_publicai):
    """is_enabled returns True when PUBLICAI_API_KEY is set."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings",
        return_value=mock_settings_with_publicai,
    ):
        assert is_enabled() is True


# ---------------------------------------------------------------------------
# Route resolution tests
# ---------------------------------------------------------------------------


def test_route_prefers_direct_publicai_when_key_set(mock_settings_with_publicai):
    """When PUBLICAI_API_KEY is set, the direct Public AI route is preferred."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings",
        return_value=mock_settings_with_publicai,
    ):
        route = _resolve_route()
    assert route is not None
    assert route.name == "publicai-direct"
    assert route.url == "https://api.publicai.co/v1/chat/completions"
    assert route.model == _PUBLICAI_DIRECT_MODEL == "swiss-ai/apertus-8b-instruct"
    assert route.headers["Authorization"] == "Bearer pai_test_key_456"
    assert route.headers["Content-Type"] == "application/json"
    # Public AI's platform requires a non-empty User-Agent header.
    assert route.headers["User-Agent"]
    # Critical: the bare model id must NOT carry the HF-router-only suffix.
    assert ":publicai" not in route.model


def test_route_falls_back_to_hf_router_when_only_hf_token(mock_settings_with_token):
    """When only HF_API_TOKEN is set, the HF Inference Providers router is used."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings",
        return_value=mock_settings_with_token,
    ):
        route = _resolve_route()
    assert route is not None
    assert route.name == "hf-router"
    assert route.url == "https://router.huggingface.co/v1/chat/completions"
    # Critical: never the deprecated/paid legacy serverless API.
    assert "api-inference.huggingface.co" not in route.url
    assert route.model == "swiss-ai/Apertus-8B-Instruct-2509:publicai"
    assert route.headers["Authorization"] == "Bearer hf_test_token_123"
    assert "User-Agent" not in route.headers


def test_route_none_when_both_credentials_empty(mock_settings_no_token):
    """_resolve_route returns None when neither credential is set."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_no_token
    ):
        assert _resolve_route() is None


def test_resolve_hf_model_appends_publicai_suffix(mock_settings_with_token):
    """A bare HF model id gets the free ``:publicai`` provider suffix."""
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_with_token
    ):
        model = _resolve_hf_model()
    assert model == "swiss-ai/Apertus-8B-Instruct-2509:publicai"


def test_resolve_hf_model_falls_back_when_cf_default(mock_settings_with_token):
    """When RAG_LLM_MODEL holds a Workers AI @cf/ default, fall back to Apertus."""
    mock_settings_with_token.RAG_LLM_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_with_token
    ):
        model = _resolve_hf_model()
    assert model == _DEFAULT_APERTUS_MODEL
    assert model.endswith(":publicai")


def test_resolve_hf_model_preserves_explicit_provider_suffix(mock_settings_with_token):
    """An explicit provider suffix is preserved as-is."""
    mock_settings_with_token.RAG_LLM_MODEL = "swiss-ai/Apertus-70B-Instruct-2509:publicai"
    with patch(
        "app.integrations.llm.apertus_adapter._get_settings", return_value=mock_settings_with_token
    ):
        model = _resolve_hf_model()
    assert model == "swiss-ai/Apertus-70B-Instruct-2509:publicai"


# ---------------------------------------------------------------------------
# Response parsing tests
# ---------------------------------------------------------------------------


def test_parse_chat_completion_extracts_content(mock_chat_completion_response):
    """_parse_chat_completion pulls choices[0].message.content."""
    assert (
        _parse_chat_completion(mock_chat_completion_response)
        == "This document is about EU residence permits."
    )


def test_parse_chat_completion_empty_on_unexpected_shape():
    """_parse_chat_completion returns empty string for unexpected shapes."""
    assert _parse_chat_completion({"unexpected_key": "value"}) == ""
    assert _parse_chat_completion([]) == ""
    assert _parse_chat_completion({"choices": []}) == ""


# ---------------------------------------------------------------------------
# Successful generation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_success(
    mock_settings_with_token, sample_prompt, mock_chat_completion_response
):
    """generate_answer parses an OpenAI chat-completion response correctly."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_chat_completion_response

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await generate_answer(sample_prompt)

    assert result is not None
    assert isinstance(result, ApertusResponse)
    assert "EU residence permits" in result.answer
    assert result.model == "swiss-ai/Apertus-8B-Instruct-2509:publicai"
    assert result.processing_time_ms > 0


@pytest.mark.asyncio
async def test_generate_answer_success_via_direct_publicai(
    mock_settings_with_publicai, sample_prompt, mock_chat_completion_response
):
    """generate_answer uses the direct Public AI route when PUBLICAI_API_KEY is set."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_chat_completion_response

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_publicai,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await generate_answer(sample_prompt)

    assert result is not None
    assert result.model == "swiss-ai/apertus-8b-instruct"
    # Verify the request went to the direct Public AI endpoint with a User-Agent.
    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer pai_test_key_456"
    assert kwargs["headers"]["User-Agent"]


@pytest.mark.asyncio
async def test_generate_answer_empty_answer_on_unexpected_shape(
    mock_settings_with_token, sample_prompt
):
    """generate_answer returns empty string for unexpected response shape."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"unexpected_key": "value"}

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await generate_answer(sample_prompt)

    assert result is not None
    assert result.answer == ""


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_raises_on_non200(mock_settings_with_token, sample_prompt):
    """generate_answer raises RuntimeError on non-200 HTTP status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="HTTP 503"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_raises_on_timeout(mock_settings_with_token, sample_prompt):
    """generate_answer raises RuntimeError on request timeout."""
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_raises_on_connection_error(mock_settings_with_token, sample_prompt):
    """generate_answer raises RuntimeError on connection failure."""
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="Cannot connect"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_raises_on_non_json_response(mock_settings_with_token, sample_prompt):
    """generate_answer raises RuntimeError when response is not JSON (e.g. HTML error page)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html>Cloudflare error page</html>"
    mock_resp.json.side_effect = ValueError("not JSON")

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="non-JSON"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_raises_on_generic_http_error(
    mock_settings_with_token, sample_prompt
):
    """generate_answer raises RuntimeError on generic httpx HTTPError (not just timeout/connect)."""
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.ReadError("read error"))

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="HTTP error"),
    ):
        await generate_answer(sample_prompt)


@pytest.mark.asyncio
async def test_generate_answer_strips_special_tokens_from_output(
    mock_settings_with_token, sample_prompt
):
    """Generated answer has special tokens stripped before returning."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "<|assistant_end|>Answer here.<|user_start|>"}}]
    }

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch(
            "app.integrations.llm.apertus_adapter._get_settings",
            return_value=mock_settings_with_token,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await generate_answer(sample_prompt)

    assert result is not None
    assert result.answer == "Answer here."
    assert "<|" not in result.answer


# ---------------------------------------------------------------------------
# AST checks: no direct/legacy HuggingFace API URLs, no HF SDK imports
# ---------------------------------------------------------------------------


def test_no_legacy_huggingface_urls_in_adapter():
    """Adapter must not contain the legacy/paid HF Serverless Inference API URL.

    The router URL itself is centralized in gateway.py (REM-8), so no hardcoded
    provider URLs should appear in the adapter at all.
    """
    adapter_path = (
        Path(__file__).resolve().parents[2] / "app" / "integrations" / "llm" / "apertus_adapter.py"
    )
    source = adapter_path.read_text()

    assert "api-inference.huggingface.co" not in source, (
        "Legacy HuggingFace Serverless Inference API URL found in adapter — "
        "Apertus must use the Inference Providers router via gateway.py"
    )


def test_adapter_uses_httpx_not_hf_sdk():
    """Adapter must use httpx (HTTP boundary), not the HuggingFace SDK.

    Same isolation principle as BabelDOC adapter (ADR-012) —
    no SDK imports that could pull in incompatible dependencies.
    """
    adapter_path = (
        Path(__file__).resolve().parents[2] / "app" / "integrations" / "llm" / "apertus_adapter.py"
    )
    source = adapter_path.read_text()

    forbidden_imports = [
        "from huggingface_hub",
        "import huggingface_hub",
        "from transformers",
        "import transformers",
        "@huggingface/inference",
    ]
    for imp in forbidden_imports:
        assert imp not in source, f"Forbidden import found in adapter: {imp}"


# ---------------------------------------------------------------------------
# Special token stripping tests
# ---------------------------------------------------------------------------


def test_strip_special_tokens_removes_role_delimiters():
    """Generated text with echoed special tokens is cleaned."""
    from app.integrations.llm.apertus_adapter import _strip_special_tokens

    raw = "<|assistant_start|>This is a answer.<|assistant_end|>"
    assert _strip_special_tokens(raw) == "This is a answer."


def test_strip_special_tokens_removes_all_known_tokens():
    """All Apertus special tokens are stripped."""
    from app.integrations.llm.apertus_adapter import _strip_special_tokens

    tokens = [
        "<|system_start|>",
        "<|system_end|>",
        "<|developer_start|>",
        "<|developer_end|>",
        "<|user_start|>",
        "<|user_end|>",
        "<|assistant_start|>",
        "<|assistant_end|>",
        "<|begin_of_text|>",
        "<|end_of_text|>",
    ]
    raw = " ".join(tokens) + " clean text"
    assert _strip_special_tokens(raw) == "clean text"


def test_strip_special_tokens_preserves_normal_text():
    """Normal text without special tokens is unchanged."""
    from app.integrations.llm.apertus_adapter import _strip_special_tokens

    text = "This document explains EU residence permits in German."
    assert _strip_special_tokens(text) == text
