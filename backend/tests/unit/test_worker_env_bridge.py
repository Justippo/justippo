"""
Unit tests for Cloudflare Worker env binding bridge.

The Python Worker receives secrets as Cloudflare env bindings. `worker.py` must
copy each binding into `os.environ` before pydantic-settings is imported.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _WorkerEnv:
    """Mock Cloudflare Worker env object.

    Pyodide's JS-proxied env exposes bindings via getattr().
    This mock supports that pattern.
    """

    def __init__(self, **kwargs: str) -> None:
        self._data = kwargs

    def __getattr__(self, key: str) -> str:
        if key.startswith("_"):
            raise AttributeError(key)
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key) from None


def test_worker_bridges_ai_gateway_authorization(monkeypatch) -> None:
    """CF_AIG_AUTHORIZATION must be available to gateway.py in production."""
    asgi_stub = ModuleType("asgi")
    asgi_stub.fetch = object()
    workers_stub = ModuleType("workers")
    workers_stub.WorkerEntrypoint = object
    monkeypatch.setitem(sys.modules, "asgi", asgi_stub)
    monkeypatch.setitem(sys.modules, "workers", workers_stub)

    from app.worker import _bridge_env

    monkeypatch.delenv("CF_AIG_AUTHORIZATION", raising=False)

    _bridge_env(_WorkerEnv(CF_AIG_AUTHORIZATION="fresh-aig-token"))

    import os

    assert os.environ["CF_AIG_AUTHORIZATION"] == "fresh-aig-token"


def test_bridge_skips_missing_keys(monkeypatch) -> None:
    """Bindings absent from the env object must not be written to os.environ."""
    asgi_stub = ModuleType("asgi")
    asgi_stub.fetch = object()
    workers_stub = ModuleType("workers")
    workers_stub.WorkerEntrypoint = object
    monkeypatch.setitem(sys.modules, "asgi", asgi_stub)
    monkeypatch.setitem(sys.modules, "workers", workers_stub)

    from app.worker import _bridge_env

    monkeypatch.delenv("CF_AIG_AUTHORIZATION", raising=False)

    _bridge_env(_WorkerEnv())  # empty env — no bindings

    import os

    assert "CF_AIG_AUTHORIZATION" not in os.environ


def test_worker_bridges_pdf_reference_provider_configuration(monkeypatch) -> None:
    """Azure secrets and the BabelDOC URL must reach their HTTP adapters."""
    asgi_stub = ModuleType("asgi")
    asgi_stub.fetch = object()
    workers_stub = ModuleType("workers")
    workers_stub.WorkerEntrypoint = object
    monkeypatch.setitem(sys.modules, "asgi", asgi_stub)
    monkeypatch.setitem(sys.modules, "workers", workers_stub)

    from app.worker import _bridge_env

    values = {
        "AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "true",
        "AZURE_DOCUMENT_INTELLIGENCE_TIER": "F0",
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.cognitiveservices.azure.com",
        "AZURE_DOCUMENT_INTELLIGENCE_KEY": "azure-secret",
        "BABELDOC_ENABLED": "true",
        "BABELDOC_SIDECAR_URL": "https://babeldoc.example",
    }
    for key in values:
        monkeypatch.delenv(key, raising=False)

    _bridge_env(_WorkerEnv(**values))

    import os

    assert {key: os.environ[key] for key in values} == values


@pytest.mark.asyncio
async def test_on_fetch_binds_and_resets_worker_wait_until(monkeypatch) -> None:
    """Every ASGI request must expose its own Cloudflare execution context."""
    asgi_stub = ModuleType("asgi")
    asgi_stub.fetch = AsyncMock(return_value="response")
    workers_stub = ModuleType("workers")
    workers_stub.WorkerEntrypoint = object
    monkeypatch.setitem(sys.modules, "asgi", asgi_stub)
    monkeypatch.setitem(sys.modules, "workers", workers_stub)

    from app import worker as worker_module

    monkeypatch.setattr(worker_module.asgi, "fetch", asgi_stub.fetch)
    monkeypatch.setattr(worker_module, "_asgi_app", object())
    entrypoint = worker_module.Default()
    entrypoint.env = _WorkerEnv()
    wait_until = MagicMock()
    entrypoint.ctx = SimpleNamespace(waitUntil=wait_until)
    token = object()

    with (
        patch("app.integrations.http_forwarder.bind_wait_until", return_value=token) as bind,
        patch("app.integrations.http_forwarder.reset_wait_until") as reset,
    ):
        response = await entrypoint.on_fetch(object())

    assert response == "response"
    bind.assert_called_once_with(wait_until)
    reset.assert_called_once_with(token)


@pytest.mark.asyncio
async def test_on_fetch_resets_context_when_asgi_raises(monkeypatch) -> None:
    """A failed request must not leak its waitUntil callback to the next one."""
    asgi_stub = ModuleType("asgi")
    asgi_stub.fetch = AsyncMock(side_effect=RuntimeError("ASGI failed"))
    workers_stub = ModuleType("workers")
    workers_stub.WorkerEntrypoint = object
    monkeypatch.setitem(sys.modules, "asgi", asgi_stub)
    monkeypatch.setitem(sys.modules, "workers", workers_stub)

    from app import worker as worker_module

    monkeypatch.setattr(worker_module.asgi, "fetch", asgi_stub.fetch)
    monkeypatch.setattr(worker_module, "_asgi_app", object())
    entrypoint = worker_module.Default()
    entrypoint.env = _WorkerEnv()
    entrypoint.ctx = SimpleNamespace(waitUntil=MagicMock())
    token = object()

    with (
        patch("app.integrations.http_forwarder.bind_wait_until", return_value=token),
        patch("app.integrations.http_forwarder.reset_wait_until") as reset,
        pytest.raises(RuntimeError, match="ASGI failed"),
    ):
        await entrypoint.on_fetch(object())

    reset.assert_called_once_with(token)
