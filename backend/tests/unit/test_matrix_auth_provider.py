"""
Tests — Matrix auth OAuth provider HTTP path (coverage boost).

Covers ``_provider_request_with_httpx`` (the pytest-runnable transport; the
Workers-only ``_provider_request_with_workers`` path is pragmed out) and the
JSON/error branches around it. Uses the single ``httpx.AsyncClient`` MockTransport
chokepoint so no real network calls occur.
"""

from __future__ import annotations

import httpx
import pytest

from app.api.v1.endpoints import matrix_auth

# Capture the REAL httpx.AsyncClient before any test patches it.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_for(handler) -> httpx.AsyncClient:
    return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))


@pytest.fixture
def patch_httpx(monkeypatch: pytest.MonkeyPatch):
    def _apply(factory):
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: factory())

    return _apply


@pytest.mark.asyncio
async def test_provider_request_httpx_success(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})

    patch_httpx(lambda: _client_for(handler))
    status, payload = await matrix_auth._provider_request_with_httpx(
        "https://auth.example.org/token",
        method="POST",
        form={"grant_type": "client_credentials"},
        bearer_token=None,
    )
    assert status == 200
    assert payload["access_token"] == "tok"


@pytest.mark.asyncio
async def test_provider_request_httpx_non_200(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    patch_httpx(lambda: _client_for(handler))
    status, payload = await matrix_auth._provider_request_with_httpx(
        "https://auth.example.org/token"
    )
    assert status == 401
    assert payload == {}  # non-200 responses yield empty payload


@pytest.mark.asyncio
async def test_provider_request_httpx_bearer_header(patch_httpx) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={})

    patch_httpx(lambda: _client_for(handler))
    await matrix_auth._provider_request_with_httpx(
        "https://auth.example.org/me", bearer_token="abc123"
    )
    assert seen["auth"] == "Bearer abc123"


@pytest.mark.asyncio
async def test_provider_request_httpx_transport_error(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    patch_httpx(lambda: _client_for(handler))
    with pytest.raises(matrix_auth.MatrixProviderTransportError):
        await matrix_auth._provider_request_with_httpx("https://auth.example.org/token")
