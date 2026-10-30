# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for NotDiamondRouter.

Tests verify:
- Successful routing returns a model id from the Not Diamond response
- API timeout triggers silent fallback (no exception, no caller crash)
- API 5xx triggers silent fallback
- GDPR guard raises ValueError in development when forbidden keys appear
- GDPR guard logs + skips (does not raise) in production when forbidden keys appear
- Long-string metadata is rejected by the GDPR guard
- NOT_DIAMOND_ENABLED=False bypasses routing entirely (no HTTP call)
- Empty NOT_DIAMOND_API_KEY bypasses routing entirely
- OCR_POST task type returns default without an HTTP call
- Unrecognized response shape returns default
- All httpx contact goes through _call_api (DRY: single private method)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.routing import not_diamond as nd_module
from app.integrations.routing.not_diamond import NotDiamondRouter, TaskType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings_enabled(monkeypatch):
    """Settings with NOT_DIAMOND enabled + token + 800ms timeout."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "test-key-123")
    monkeypatch.setattr(ms, "NOT_DIAMOND_BASE_URL", "https://api.notdiamond.ai/v2")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "@cf/meta/m2m100-1.2b")
    monkeypatch.setattr(ms, "NOT_DIAMOND_TIMEOUT_MS", 800)
    return ms


@pytest.fixture
def mock_settings_disabled(monkeypatch):
    """Settings with NOT_DIAMOND disabled (the default state)."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", False)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "@cf/meta/m2m100-1.2b")
    return ms


def _ok_response(model_id: str) -> dict:
    """Build a Not Diamond success-shaped response."""
    return {"providers": [{"provider": "cloudflare", "model": model_id}], "session_id": "sess_abc"}


def _ok_httpx_response(body: dict) -> MagicMock:
    """Build a mocked httpx response with .status_code and .json()."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_routing_returns_model_id(mock_settings_enabled):
    """Happy path: ND returns a model id and the router maps it to internal."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "de-fr", "doc_type": "legal_contract", "complexity_score": 0.8}

    mock_response = _ok_httpx_response(_ok_response("mistral-small-latest"))
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, metadata)

    # mistral-small-latest maps to @cf/meta/m2m100-1.2b per MODEL_MAP
    assert result == "@cf/meta/m2m100-1.2b"


@pytest.mark.asyncio
async def test_successful_rag_routing(mock_settings_enabled):
    """RAG_QUERY task routes between Apertus (via mistral-small proxy) and frontier."""
    router = NotDiamondRouter()
    metadata = {"language_count": 3, "complexity_score": 0.9}

    mock_response = _ok_httpx_response(_ok_response("mistral-small-latest"))
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.RAG_QUERY, metadata)

    # mistral-small-latest maps to @cf/meta/m2m100-1.2b per MODEL_MAP
    # (for RAG, this would map to Apertus in a real deployment — but the
    # MODEL_MAP currently uses the same mapping for both tasks)
    assert result == "@cf/meta/m2m100-1.2b"


# ---------------------------------------------------------------------------
# Fallback paths — must never raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_triggers_fallback_no_exception(mock_settings_enabled, caplog):
    """httpx timeout → default model, no exception propagated to caller."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "en-de"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.side_effect = httpx.TimeoutException("simulated")

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, metadata)

    assert result == router.DEFAULT_MODEL
    # The fallback was logged (without leaking payload contents).
    assert any("Not Diamond routing failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_5xx_triggers_fallback(mock_settings_enabled):
    """HTTP 500 → default model silently."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "en-de"}

    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, metadata)

    assert result == router.DEFAULT_MODEL


@pytest.mark.asyncio
async def test_malformed_response_returns_default(mock_settings_enabled):
    """ND returns garbage shape → default model, no crash."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "en-de"}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"unexpected": "shape"}
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, metadata)

    assert result == router.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Feature flag / token short-circuits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_flag_bypasses_routing(mock_settings_disabled):
    """NOT_DIAMOND_ENABLED=False → no HTTP call, returns default immediately."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "en-de"}

    # If httpx.AsyncClient is patched, the call would raise because the mock
    # is never wired in. We assert it is NEVER reached by patching to a MagicMock
    # whose .post call would raise if called.
    sentinel = MagicMock()
    sentinel.__aenter__.return_value.post.side_effect = AssertionError(
        "routing should not have made an HTTP call when NOT_DIAMOND_ENABLED=False"
    )

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=sentinel):
        result = await router.route(TaskType.TRANSLATION, metadata)

    assert result == router.DEFAULT_MODEL


@pytest.mark.asyncio
async def test_empty_api_token_bypasses_routing(monkeypatch):
    """NOT_DIAMOND_API_KEY="" + flag=True → no-op (defensive)."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "@cf/meta/m2m100-1.2b")

    router = NotDiamondRouter()
    result = await router.route(TaskType.TRANSLATION, {"language_pair": "en-de"})
    assert result == router.DEFAULT_MODEL


@pytest.mark.asyncio
async def test_ocr_post_never_routes(mock_settings_enabled):
    """OCR_POST short-circuits to default — no HTTP call, no routing decision."""
    router = NotDiamondRouter()
    sentinel = MagicMock()
    sentinel.__aenter__.return_value.post.side_effect = AssertionError(
        "OCR_POST must not route via Not Diamond"
    )

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=sentinel):
        result = await router.route(TaskType.OCR_POST, {})

    assert result == router.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# GDPR guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gdpr_guard_raises_in_dev_on_forbidden_key(monkeypatch):
    """In development, a forbidden content key raises ValueError."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "APP_ENV", "development")
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "test-key")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "@cf/meta/m2m100-1.2b")

    router = NotDiamondRouter()
    bad_metadata = {"language_pair": "en-de", "content": "actual document text here"}

    with pytest.raises(ValueError, match="forbidden content keys"):
        await router.route(TaskType.TRANSLATION, bad_metadata)


@pytest.mark.asyncio
async def test_gdpr_guard_skips_in_prod_on_forbidden_key(monkeypatch, caplog):
    """In production, a forbidden content key is logged and default returned (no raise)."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "APP_ENV", "production")
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "test-key")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "@cf/meta/m2m100-1.2b")

    router = NotDiamondRouter()
    bad_metadata = {"language_pair": "en-de", "text": "some content"}

    result = await router.route(TaskType.TRANSLATION, bad_metadata)

    assert result == router.DEFAULT_MODEL
    assert any("GDPR guard rejected" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_gdpr_guard_rejects_long_string(monkeypatch):
    """A string value over 5000 chars in metadata is treated as content."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "APP_ENV", "development")
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "test-key")

    router = NotDiamondRouter()
    too_long = "x" * 6000
    with pytest.raises(ValueError, match="routing signals must be short metadata"):
        await router.route(TaskType.TRANSLATION, {"language_pair": too_long})


# ---------------------------------------------------------------------------
# DRY / structure
# ---------------------------------------------------------------------------


def test_single_httpx_contact_point():
    """All HTTP calls in the module go through _call_api — DRY."""
    import inspect

    source = inspect.getsource(NotDiamondRouter)
    # Only _call_api should reference AsyncClient or .post — verify by grepping
    # for "AsyncClient" / ".post" outside _call_api.
    tree_lines = source.splitlines()
    in_call_api = False
    offenders = []
    for line in tree_lines:
        if "async def _call_api" in line:
            in_call_api = True
            continue
        if (
            in_call_api
            and line.strip().startswith(("def ", "async def ", "@"))
            and "_call_api" not in line
        ):
            # Next method boundary — leave _call_api
            in_call_api = False
        if not in_call_api and ("AsyncClient" in line or ".post(" in line):
            offenders.append(line.strip())
    assert offenders == [], f"httpx contact leaked outside _call_api: {offenders}"


def test_get_router_returns_singleton():
    """get_router() returns a stable singleton."""
    r1 = nd_module.get_router()
    r2 = nd_module.get_router()
    assert r1 is r2


# ---------------------------------------------------------------------------
# Config-driven DEFAULT_MODEL (bug fix: was hardcoded, ignoring config)
# ---------------------------------------------------------------------------


def test_default_model_reads_from_settings(monkeypatch):
    """DEFAULT_MODEL must read from settings.NOT_DIAMOND_DEFAULT_MODEL, not
    a hardcoded class constant. This was a real bug — config was dead."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "custom/fallback-model")

    router = NotDiamondRouter()
    assert router.DEFAULT_MODEL == "custom/fallback-model"


def test_default_model_falls_back_to_hardcoded_when_settings_empty(monkeypatch):
    """When NOT_DIAMOND_DEFAULT_MODEL is empty, use the hardcoded fallback."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "")

    router = NotDiamondRouter()
    assert router.DEFAULT_MODEL == NotDiamondRouter._HARDCODED_FALLBACK


# ---------------------------------------------------------------------------
# _parse_model_id defensive branches (lines 280, 283 — previously uncovered)
# ---------------------------------------------------------------------------


def test_parse_model_id_providers_not_list():
    """providers is not a list → default."""
    router = NotDiamondRouter()
    assert router._parse_model_id({"providers": "not-a-list"}) == router.DEFAULT_MODEL


def test_parse_model_id_providers_empty_list():
    """providers is empty list → default."""
    router = NotDiamondRouter()
    assert router._parse_model_id({"providers": []}) == router.DEFAULT_MODEL


def test_parse_model_id_first_provider_not_dict():
    """first provider is not a dict → default."""
    router = NotDiamondRouter()
    assert router._parse_model_id({"providers": ["not-a-dict"]}) == router.DEFAULT_MODEL


def test_parse_model_id_model_not_string():
    """model field is not a string → default."""
    router = NotDiamondRouter()
    assert router._parse_model_id({"providers": [{"model": 123}]}) == router.DEFAULT_MODEL


def test_parse_model_id_model_empty_string():
    """model field is empty string → default."""
    router = NotDiamondRouter()
    assert router._parse_model_id({"providers": [{"model": ""}]}) == router.DEFAULT_MODEL


def test_parse_model_id_providers_missing():
    """providers key entirely missing → default."""
    router = NotDiamondRouter()
    assert router._parse_model_id({"session_id": "abc"}) == router.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Config-driven default model used in fallback paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_default_model_used_on_timeout(monkeypatch):
    """When routing fails, the fallback uses the config-driven default, not
    a hardcoded value."""
    ms = nd_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "test-key")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "custom/fallback-model")
    monkeypatch.setattr(ms, "NOT_DIAMOND_TIMEOUT_MS", 800)

    router = NotDiamondRouter()
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.side_effect = httpx.TimeoutException("simulated")

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, {"language_pair": "en-de"})

    assert result == "custom/fallback-model"  # NOT the hardcoded fallback


# ---------------------------------------------------------------------------
# MODEL_MAP integration (bug fix: candidate lists were invalid providers)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_frontier_translation_maps_to_mistral_large(mock_settings_enabled):
    """When ND picks mistral-large-latest (frontier), router returns mistral-large-translation sentinel."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "de-fr", "doc_type": "legal_contract", "complexity_score": 0.95}

    mock_response = _ok_httpx_response(_ok_response("mistral-large-latest"))
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, metadata)

    assert result == "mistral-large-translation"


@pytest.mark.asyncio
async def test_unmapped_model_falls_back_to_default(mock_settings_enabled, caplog):
    """When ND returns a model not in MODEL_MAP, router falls back to default."""
    router = NotDiamondRouter()
    metadata = {"language_pair": "en-de"}

    # mistral-open-mistral-nemo is a valid ND model but NOT in MODEL_MAP
    mock_response = _ok_httpx_response(_ok_response("mistral/open-mistral-nemo"))
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, metadata)

    assert result == router.DEFAULT_MODEL
    assert any("unmapped model" in r.message for r in caplog.records)
