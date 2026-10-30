"""Coverage for adapter config-validation and error branches.

DRY: two adapters, one pattern each.
- ``azure_document_intelligence._load_config`` validates env vars and raises
  ``AzureDocumentIntelligenceError`` on missing/invalid config (pure, no network).
- ``apertus_adapter.generate_answer`` is no-op when unconfigured and raises
  ``RuntimeError`` on a non-200 upstream response (MockTransport).
"""

from __future__ import annotations

import httpx
import pytest

from app.integrations.azure_document_intelligence import (
    AzureDocumentIntelligenceError,
    _load_config,
)
from app.integrations.llm import apertus_adapter
from app.integrations.llm.apertus_adapter import ApertusResponse, generate_answer

# ---------------------------------------------------------------------------
# azure_document_intelligence._load_config — pure validation branches
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "AZURE_DOCUMENT_INTELLIGENCE_KEY",
        "AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S",
        "AZURE_DOCUMENT_INTELLIGENCE_POLL_INTERVAL_S",
        "AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_azure_config_missing_raises(clean_azure_env: None) -> None:
    with pytest.raises(AzureDocumentIntelligenceError):
        _load_config()


def test_azure_config_non_https_raises(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "http://bad")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    with pytest.raises(AzureDocumentIntelligenceError):
        _load_config()


def test_azure_config_bad_timing_raises(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://doc-int.example.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S", "not-a-float")
    with pytest.raises(AzureDocumentIntelligenceError):
        _load_config()


def test_azure_config_negative_timing_raises(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://doc-int.example.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S", "-5")
    with pytest.raises(AzureDocumentIntelligenceError):
        _load_config()


def test_azure_config_valid(clean_azure_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://doc-int.example.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    cfg = _load_config()
    assert cfg.endpoint == "https://doc-int.example.com"


# ---------------------------------------------------------------------------
# apertus_adapter.generate_answer — no-op + error branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apertus_noop_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLICAI_API_KEY", raising=False)
    monkeypatch.delenv("HF_API_TOKEN", raising=False)
    # Force route resolution to re-read env.
    monkeypatch.setattr(apertus_adapter, "_resolve_route", lambda: None)
    assert await generate_answer("ignored") is None


@pytest.mark.asyncio
async def test_apertus_runtime_error_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLICAI_API_KEY", raising=False)
    monkeypatch.delenv("HF_API_TOKEN", raising=False)

    route = apertus_adapter._Route(
        name="publicai-direct",
        url="https://api.publicai.co/v1",
        headers={},
        model="swiss-ai/apertus-8b-instruct",
    )
    monkeypatch.setattr(apertus_adapter, "_resolve_route", lambda: route)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    with pytest.raises(RuntimeError):
        # Use a tiny timeout to fail fast if it ever reached the network.
        await generate_answer("prompt")


@pytest.mark.asyncio
async def test_apertus_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLICAI_API_KEY", raising=False)
    monkeypatch.delenv("HF_API_TOKEN", raising=False)

    route = apertus_adapter._Route(
        name="publicai-direct",
        url="https://api.publicai.co/v1",
        headers={},
        model="swiss-ai/apertus-8b-instruct",
    )
    monkeypatch.setattr(apertus_adapter, "_resolve_route", lambda: route)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Hello <|end_of_text|> world"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    resp = await generate_answer("prompt")
    assert isinstance(resp, ApertusResponse)
    assert "world" in resp.answer
