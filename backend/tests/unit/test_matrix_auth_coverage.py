# SPDX-License-Identifier: AGPL-3.0-or-later
"""Targeted coverage for Matrix OAuth error/edge branches.

Reuses the autouse ``matrix_settings`` shape from the main matrix_auth test
module via a local fixture, and mocks all network (httpx/D1/cookies).
"""

from __future__ import annotations

import asyncio
import sys
import time
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.api.v1.endpoints import matrix_auth
from tests.unit.d1_fakes import InMemoryD1Binding

METADATA = {
    "authorization_endpoint": "https://account.example/oauth2/auth",
    "token_endpoint": "https://account.example/oauth2/token",
    "revocation_endpoint": "https://account.example/oauth2/revoke",
    "registration_endpoint": "https://account.example/oauth2/register",
    "code_challenge_methods_supported": ["S256"],
}


@pytest.fixture(autouse=True)
def _matrix_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix_auth.settings, "ENABLE_MATRIX_AUTH", True)
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_CLIENT_ID", "client-123")
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_HOMESERVER_URL", "https://matrix.example")
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "")
    monkeypatch.setattr(
        matrix_auth.settings,
        "MATRIX_OAUTH_CALLBACK_URL",
        "https://api.example/api/v1/auth/matrix/callback",
    )
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_OAUTH_POST_LOGIN_URL", "https://app.example/")
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "test")
    matrix_auth._oauth_states.clear()
    matrix_auth._oauth_sessions.clear()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(matrix_auth.router, prefix="/auth")
    return TestClient(app)


# ── _fetch_metadata_with_workers (JS FFI path) 143-144 ─────────────────────────


@pytest.mark.asyncio
async def test_fetch_metadata_with_workers_js_path(caplog: pytest.LogCaptureFixture) -> None:
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(return_value=MagicMock(status=200))  # type: ignore[attr-defined]
    js_resp = workers_module.fetch.return_value  # type: ignore[attr-defined]
    js_resp.json = AsyncMock(return_value=METADATA)
    with patch.dict(sys.modules, {"workers": workers_module}), caplog.at_level("DEBUG"):
        result = await matrix_auth._fetch_metadata_with_workers("https://matrix.example")
    assert result == (200, METADATA)


@pytest.mark.asyncio
async def test_fetch_metadata_with_workers_js_non_200() -> None:
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(return_value=MagicMock(status=404))  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"workers": workers_module}):
        result = await matrix_auth._fetch_metadata_with_workers("https://matrix.example")
    assert result == (404, {})


# ── _provider_request_with_workers (JS FFI path) 163, 176 ──────────────────────


@pytest.mark.asyncio
async def test_provider_request_with_workers_js_path() -> None:
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(return_value=MagicMock(status=200))  # type: ignore[attr-defined]
    js_resp = workers_module.fetch.return_value  # type: ignore[attr-defined]
    js_resp.json = AsyncMock(return_value=METADATA)
    with patch.dict(sys.modules, {"workers": workers_module}):
        status, payload = await matrix_auth._provider_request_with_workers(
            "https://matrix.example/token",
            method="POST",
            form={"grant_type": "code"},
        )
    assert status == 200
    assert payload == METADATA
    # form encoding was sent as body
    call_kwargs = workers_module.fetch.await_args_list[0].kwargs  # type: ignore[attr-defined]
    assert call_kwargs["method"] == "POST"
    assert "grant_type=code" in call_kwargs["body"]


@pytest.mark.asyncio
async def test_provider_request_with_workers_js_exception() -> None:
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(side_effect=RuntimeError("ffi failure"))  # type: ignore[attr-defined]
    with (
        patch.dict(sys.modules, {"workers": workers_module}),
        pytest.raises(matrix_auth.MatrixProviderTransportError),
    ):
        await matrix_auth._provider_request_with_workers(
            "https://matrix.example/token",
            method="POST",
        )


# ── auth_status with non-Discovery HTTPException (538-540) ─────────────────────


def test_status_returns_available_false_on_transport_exception(client: TestClient) -> None:
    with (
        patch.object(matrix_auth, "_has_env_token", return_value=False),
        patch.object(
            matrix_auth, "_discover_metadata", AsyncMock(side_effect=HTTPException(status_code=503))
        ),
    ):
        response = client.get("/auth/matrix/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "transport_error"


# ── require_authenticated_matrix_session error paths (449-491) ─────────────────


def _cookie_request(cookie_val: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    f"{matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME}={cookie_val}".encode(),
                )
            ],
        }
    )


@pytest.mark.asyncio
async def test_require_session_get_lookup_fails_returns_401() -> None:
    matrix_auth._oauth_sessions["broken"] = {
        "session_id": "broken",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_at": int(time.time()) + 300,
    }
    request = _cookie_request("broken")
    with (
        patch.object(
            matrix_auth, "_get_session", AsyncMock(side_effect=RuntimeError("D1 lookup boom"))
        ),
        pytest.raises(HTTPException) as raised,
    ):
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401
    assert "session lookup failed" in raised.value.detail


@pytest.mark.asyncio
async def test_require_session_invalid_or_expired_returns_401() -> None:
    # record found but expired AND refresh returns None -> delete + 401 (476-478).
    matrix_auth._oauth_sessions["expired"] = {
        "session_id": "expired",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "access_token": "old",
        "refresh_token": None,
        "expires_at": int(time.time()) - 1,
    }
    request = _cookie_request("expired")
    with (
        patch.object(matrix_auth, "_refresh_session", AsyncMock(return_value=None)),
        patch.object(matrix_auth, "_delete_session", new=AsyncMock()),
        pytest.raises(HTTPException) as raised,
    ):
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401
    assert "invalid or expired" in raised.value.detail


@pytest.mark.asyncio
async def test_require_session_refresh_failure_records_none_473() -> None:
    matrix_auth._oauth_sessions["exp2"] = {
        "session_id": "exp2",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "access_token": "old",
        "refresh_token": "ref",
        "expires_at": int(time.time()) - 1,
    }
    request = _cookie_request("exp2")
    with (
        patch.object(
            matrix_auth, "_refresh_session", AsyncMock(side_effect=RuntimeError("refresh boom"))
        ),
        patch.object(matrix_auth, "_delete_session", new=AsyncMock()),
        pytest.raises(HTTPException) as raised,
    ):
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401


@pytest.mark.asyncio
async def test_require_session_corrupt_expires_at_raises_464() -> None:
    matrix_auth._oauth_sessions["corrupt"] = {
        "session_id": "corrupt",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "access_token": "tok",
        "refresh_token": None,
        "expires_at": "not-an-int",
    }
    request = _cookie_request("corrupt")
    with pytest.raises(HTTPException) as raised:
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401
    assert "invalid or expired" in raised.value.detail


@pytest.mark.asyncio
async def test_require_session_record_missing_access_token_487() -> None:
    matrix_auth._oauth_sessions["badstruct"] = {
        "session_id": "badstruct",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "access_token": None,  # will str(None) -> still a string, but let's omit keys
        "refresh_token": None,
        "expires_at": int(time.time()) + 300,
    }
    # Force expires_at to be valid so we reach the structure build (480-486).
    request = _cookie_request("badstruct")
    # Override _get_session to return a record missing required keys.
    broken_record = {
        "session_id": "badstruct",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "expires_at": int(time.time()) + 300,
        # access_token intentionally absent
    }
    with (
        patch.object(matrix_auth, "_get_session", AsyncMock(return_value=broken_record)),
        pytest.raises(HTTPException) as raised,
    ):
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401


# ── matrix_callback: error param + token exchange failures (608, 631, 636) ──────


def test_callback_rejects_error_param(client: TestClient) -> None:
    response = client.get(
        "/auth/matrix/callback",
        params={"error": "access_denied", "state": "s"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_callback_token_exchange_non_200(client: TestClient) -> None:
    state = "state-xyz"
    matrix_auth._oauth_states[matrix_auth._state_hash(state)] = {
        "code_verifier": "v" * 64,
        "redirect_uri": matrix_auth.settings.MATRIX_OAUTH_CALLBACK_URL,
        "device_id": "DEV1234",
        "expires_at": int(time.time()) + 300,
        "created_at": int(time.time()),
    }
    provider = AsyncMock(
        side_effect=[
            (401, {"err": "bad code"}),
            (200, {"user_id": "@a:matrix.example", "device_id": "DEV1234"}),
        ]
    )
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        response = client.get(
            "/auth/matrix/callback",
            params={"code": "code-1", "state": state},
            follow_redirects=False,
        )
    assert response.status_code == 401


def test_callback_provider_transport_error_503(client: TestClient) -> None:
    state = "state-xyz"
    matrix_auth._oauth_states[matrix_auth._state_hash(state)] = {
        "code_verifier": "v" * 64,
        "redirect_uri": matrix_auth.settings.MATRIX_OAUTH_CALLBACK_URL,
        "device_id": "DEV1234",
        "expires_at": int(time.time()) + 300,
        "created_at": int(time.time()),
    }
    provider = AsyncMock(side_effect=matrix_auth.MatrixProviderTransportError("down"))
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        response = client.get(
            "/auth/matrix/callback",
            params={"code": "code-1", "state": state},
            follow_redirects=False,
        )
    assert response.status_code == 503


# ── logout: no session cookie + OAuth path (728, 746-747) ──────────────────────


def test_logout_no_session_cookie_oauth_path(client: TestClient) -> None:
    # No cookie at all -> skips session lookup, hits _clear_session_cookie (OAuth path).
    matrix_auth._oauth_sessions.clear()
    response = client.post("/auth/matrix/logout", headers={"origin": "https://app.example"})
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=0" in cookie
    assert "SameSite=lax" in cookie  # test env


def test_logout_csrf_origin_blocked(client: TestClient) -> None:
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "session-1")
    response = client.post("/auth/matrix/logout", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_logout_oauth_path_transport_error_swallowed(client: TestClient) -> None:
    # OAuth-path logout: _get_session returns a live session, _discover_metadata
    # succeeds, but the revocation _provider_request raises MatrixProviderTransportError
    # which is swallowed at 746; _delete_session (748) still runs and the cookie
    # is cleared. Patching _get_session directly avoids TestClient cookie-jar
    # plumbing so we deterministically reach the revocation try-block.
    record = {
        "session_id": "session-1",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEV",
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_at": int(time.time()) + 300,
    }
    provider = AsyncMock(side_effect=matrix_auth.MatrixProviderTransportError("revocation down"))
    get_session = AsyncMock(return_value=record)
    delete_session = AsyncMock()
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
        patch.object(matrix_auth, "_get_session", get_session),
        patch.object(matrix_auth, "_delete_session", delete_session),
    ):
        client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "session-1")
        response = client.post("/auth/matrix/logout", headers={"origin": "https://app.example"})
    assert response.status_code == 200
    get_session.assert_awaited_once()
    assert provider.await_count == 1  # revocation attempted, then swallowed at 746
    delete_session.assert_awaited_once()  # session still deleted (748)
    cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=0" in cookie


# ── session_status: expired+refresh+record-None (701-705) ─────────────────────


def test_session_status_refresh_failure_then_none(client: TestClient) -> None:
    matrix_auth._oauth_sessions["sess"] = {
        "session_id": "sess",
        "matrix_user_id": "@a:evidence.eu",
        "device_id": "DEV",
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_at": int(time.time()) - 1,
    }
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "sess")
    with (
        patch.object(matrix_auth, "_refresh_session", AsyncMock(side_effect=RuntimeError("boom"))),
        patch.object(matrix_auth, "_delete_session", new=AsyncMock()),
    ):
        response = client.get("/auth/matrix/session")
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is False


def test_session_status_record_structure_error_712(client: TestClient) -> None:
    matrix_auth._oauth_sessions["struct"] = {
        "session_id": "struct",
        "matrix_user_id": "@a:evidence.eu",
        # device_id intentionally absent -> KeyError at 710
        "access_token": "tok",
        "refresh_token": None,
        "expires_at": int(time.time()) + 300,
    }
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "struct")
    response = client.get("/auth/matrix/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


# ── matrix_callback error + redirect branches (606, 616, 631, 640-641) ─────────


def test_callback_redirects_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    with patch.object(matrix_auth, "_discover_metadata") as mock_discover:
        response = client.get("/auth/matrix/callback", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == matrix_auth.settings.MATRIX_OAUTH_POST_LOGIN_URL
    mock_discover.assert_not_called()


def test_callback_redirects_when_state_not_found(client: TestClient) -> None:
    # _consume_state returns None -> redirect to post-login (616).
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", AsyncMock()),
    ):
        response = client.get(
            "/auth/matrix/callback",
            params={"code": "c", "state": "unknown"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert response.headers["location"] == matrix_auth.settings.MATRIX_OAUTH_POST_LOGIN_URL


# ── _json_object_to_python TypeError (103) ─────────────────────────────────────


def test_json_object_to_python_rejects_non_dict() -> None:
    with pytest.raises(TypeError, match="not an object"):
        matrix_auth._json_object_to_python("not-a-dict-string")


def test_callback_whoami_non_200(client: TestClient) -> None:
    state = "state-whoami"
    matrix_auth._oauth_states[matrix_auth._state_hash(state)] = {
        "code_verifier": "v" * 64,
        "redirect_uri": matrix_auth.settings.MATRIX_OAUTH_CALLBACK_URL,
        "device_id": "DEV1234",
        "expires_at": int(time.time()) + 300,
        "created_at": int(time.time()),
    }
    provider = AsyncMock(
        side_effect=[
            (
                200,
                {
                    "access_token": "a",
                    "refresh_token": "r",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            ),
            (403, {"err": "forbidden"}),
        ]
    )
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        response = client.get(
            "/auth/matrix/callback",
            params={"code": "code-1", "state": state},
            follow_redirects=False,
        )
    assert response.status_code == 401


# ── _require_enabled / MatrixDiscoveryError constructor (55-56, 81) ───────────


def test_matrix_discovery_error_carries_reason() -> None:
    exc = matrix_auth.MatrixDiscoveryError("incomplete_metadata", "incomplete")
    assert exc.reason == "incomplete_metadata"
    assert exc.detail == "incomplete"
    assert exc.status_code == 503


def test_require_enabled_raises_403_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix_auth.settings, "ENABLE_MATRIX_AUTH", False)
    with pytest.raises(HTTPException) as raised:
        matrix_auth._require_enabled()
    assert raised.value.status_code == 403


# ── _fetch_metadata_with_httpx transport error (132-144) ──────────────────────


@pytest.mark.asyncio
async def test_fetch_metadata_with_httpx_transport_error_raises_discovery() -> None:
    import httpx

    transport_error = httpx.ConnectError("refused")
    with (
        patch("app.api.v1.endpoints.matrix_auth.httpx.AsyncClient", side_effect=transport_error),
        pytest.raises(matrix_auth.MatrixDiscoveryError) as raised,
    ):
        await matrix_auth._fetch_metadata_with_httpx("https://matrix.example")
    assert raised.value.status_code == 503


# ── D1-backed state/session storage paths (288-302, 316-321, 407-421) ──────────


def _d1_scope(db: InMemoryD1Binding) -> dict:
    return {"type": "http", "env": SimpleNamespace(DB=db)}


def test_store_state_persists_to_d1_via_inmemory() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    asyncio.run(
        matrix_auth._store_state(
            request,
            "state-abc",
            {
                "code_verifier": "v",
                "redirect_uri": "https://cb",
                "device_id": "D",
                "expires_at": 9999999999,
                "created_at": 1,
            },
        )
    )
    assert matrix_auth._state_hash("state-abc") in db._tables["matrix_oauth_states"]


def test_store_state_503_when_d1_write_fails() -> None:
    import asyncio

    # from_scope wraps the binding in a D1Client; patch from_scope to return a
    # fake whose execute() reports failure (ok=False branch at 302).
    fake_db = MagicMock(spec=matrix_auth.D1Client)
    fake_db.execute = AsyncMock(return_value=False)
    request = Request(_d1_scope(fake_db))
    with (
        patch.object(matrix_auth.D1Client, "from_scope", classmethod(lambda cls, scope: fake_db)),
        pytest.raises(HTTPException) as raised,
    ):
        asyncio.run(
            matrix_auth._store_state(
                request,
                "state-x",
                {
                    "code_verifier": "v",
                    "redirect_uri": "u",
                    "device_id": "D",
                    "expires_at": 9999999999,
                    "created_at": 1,
                },
            )
        )
    assert raised.value.status_code == 503


def test_consume_state_d1_path_returns_and_deletes() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    key = matrix_auth._state_hash("fresh-state")
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_states (state_hash, code_verifier, redirect_uri, "
            "device_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [key, "v", "https://cb", "D", int(time.time()) + 300, 1],
        )
    )
    record = asyncio.run(matrix_auth._consume_state(request, "fresh-state"))
    assert record is not None
    assert record["code_verifier"] == "v"
    assert asyncio.run(matrix_auth._consume_state(request, "fresh-state")) is None


def test_consume_state_returns_none_when_expired() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    key = matrix_auth._state_hash("expired-state")
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_states (state_hash, code_verifier, redirect_uri, "
            "device_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [key, "v", "https://cb", "D", int(time.time()) - 1, 1],
        )
    )
    assert asyncio.run(matrix_auth._consume_state(request, "expired-state")) is None


def test_refresh_session_d1_update_path() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
            "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["sess-1", "@a:e", "D", "old", "ref", "Bearer", int(time.time()) - 1, 1, 1],
        )
    )
    record = {
        "session_id": "sess-1",
        "access_token": "old",
        "refresh_token": "ref",
        "expires_at": int(time.time()) - 1,
        "device_id": "D",
        "matrix_user_id": "@a:e",
        "created_at": 1,
        "updated_at": 1,
    }
    provider_ok = AsyncMock(return_value=(200, {"access_token": "new", "expires_in": 3600}))
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider_ok),
    ):
        refreshed = asyncio.run(matrix_auth._refresh_session(request, record))
    assert refreshed is not None
    assert refreshed["access_token"] == "new"


# ── D1-backed _store_session / _get_session / _delete_session (336-371) ────────


def _patch_from_scope_to(db: Any) -> patch:
    return patch.object(matrix_auth.D1Client, "from_scope", classmethod(lambda cls, scope: db))


def test_store_session_persists_to_d1() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    with _patch_from_scope_to(db):
        asyncio.run(
            matrix_auth._store_session(
                request,
                "sess-d1",
                {
                    "session_id": "sess-d1",
                    "matrix_user_id": "@a:e",
                    "device_id": "D",
                    "access_token": "tok",
                    "refresh_token": "ref",
                    "token_type": "Bearer",
                    "expires_at": int(time.time()) + 3600,
                    "created_at": 1,
                    "updated_at": 1,
                },
            )
        )
    assert "sess-d1" in db._tables["matrix_oauth_sessions"]


def test_get_session_reads_from_d1() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
            "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["sess-g", "@a:e", "D", "tok", "ref", "Bearer", int(time.time()) + 300, 1, 1],
        )
    )
    with _patch_from_scope_to(db):
        record = asyncio.run(matrix_auth._get_session(request, "sess-g"))
    assert record is not None
    assert record["access_token"] == "tok"


def test_delete_session_d1_path() -> None:
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
            "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["sess-d", "@a:e", "D", "tok", "ref", "Bearer", int(time.time()) + 300, 1, 1],
        )
    )
    with _patch_from_scope_to(db):
        asyncio.run(matrix_auth._delete_session(request, "sess-d"))
    assert "sess-d" not in db._tables["matrix_oauth_sessions"]


def test_refresh_session_d1_none_path_returns_none() -> None:
    # No refresh_token in record -> early return None at 376-377 (405 variant).
    import asyncio

    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    record = {"session_id": "sess-noref", "refresh_token": None}
    with _patch_from_scope_to(db):
        result = asyncio.run(matrix_auth._refresh_session(request, record))
    assert result is None


def test_session_status_d1_path_authenticated(client: TestClient) -> None:
    db = InMemoryD1Binding()
    now = int(time.time())
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
            "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["sess-s", "@a:e", "D", "tok", None, "Bearer", now + 300, 1, 1],
        )
    )
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "sess-s")
    with _patch_from_scope_to(db):
        response = client.get("/auth/matrix/session")
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user_id"] == "@a:e"
    assert body["device_id"] == "D"


def test_session_status_d1_path_get_lookup_fails_690(client: TestClient) -> None:
    db = InMemoryD1Binding()
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "sess-err")
    # _get_session raises inside session_status -> caught at 690 -> authenticated False.
    with (
        _patch_from_scope_to(db),
        patch.object(matrix_auth, "_get_session", AsyncMock(side_effect=RuntimeError("D1 boom"))),
    ):
        response = client.get("/auth/matrix/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


def test_logout_d1_path_no_refresh_token_skips_revoke_687(client: TestClient) -> None:
    db = InMemoryD1Binding()
    asyncio.run(
        db.execute(
            "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
            "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["sess-noref", "@a:e", "D", "tok", None, "Bearer", int(time.time()) + 300, 1, 1],
        )
    )
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "sess-noref")
    provider = AsyncMock(return_value=(200, {}))
    with (
        _patch_from_scope_to(db),
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        response = client.post("/auth/matrix/logout", headers={"origin": "https://app.example"})
    # No refresh_token -> only access_token ("tok") is revoked.
    assert response.status_code == 200
    assert provider.await_count == 1


# ── require_session / session_status edge branches (440-442, 460) ──────────────


@pytest.mark.asyncio
async def test_require_session_invalid_record_returns_401_460() -> None:
    matrix_auth._oauth_sessions["bad"] = {
        "session_id": "bad",
        "matrix_user_id": "@a:e",
        "device_id": "D",
        "access_token": "tok",
        "refresh_token": None,
        "expires_at": int(time.time()) + 300,
    }
    # Make _get_session return None (simulating a consumed/invalid session).
    with patch.object(matrix_auth, "_get_session", AsyncMock(return_value=None)):
        request = _cookie_request("bad")
        with pytest.raises(HTTPException) as raised:
            await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401


@pytest.mark.asyncio
async def test_require_session_no_cookie_440() -> None:
    request = Request({"type": "http", "headers": []})  # no cookie
    with pytest.raises(HTTPException) as raised:
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 401
    assert "authentication required" in raised.value.detail.lower()


# ── login without client_id (565) ──────────────────────────────────────────────


def test_login_returns_503_when_client_id_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_CLIENT_ID", "")
    with patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)):
        response = client.get("/auth/matrix/login", follow_redirects=False)
    assert response.status_code == 503


# ── logout without session cookie (OAuth path, _clear_session_cookie) ───────────


def test_logout_without_session_cookie_clears_nothing(client: TestClient) -> None:
    # No session cookie -> session_id None -> skips lookup; cookie still set (cleared).
    response = client.post("/auth/matrix/logout", headers={"origin": "https://app.example"})
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers.get("set-cookie", "")


# ── Workers FFI discovery ImportError fallback (115-116) ─────────────────────


@pytest.mark.asyncio
async def test_fetch_metadata_with_workers_returns_none_without_workers_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "workers", raising=False)
    assert await matrix_auth._fetch_metadata_with_workers("https://matrix.example") is None


@pytest.mark.asyncio
async def test_provider_request_with_workers_returns_none_without_workers_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "workers", raising=False)
    assert await matrix_auth._provider_request_with_workers("https://x.example") is None


# ── _provider_request_with_httpx (184-214) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_request_with_httpx_bearer_header_and_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status_code=401)
    response.json = MagicMock(return_value={})
    client = MagicMock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(matrix_auth.httpx, "AsyncClient", lambda **kw: client)
    status, payload = await matrix_auth._provider_request_with_httpx(
        "https://x.example", method="GET", bearer_token="secret", expect_json=True
    )
    assert status == 401
    assert payload == {}
    # Bearer header was set on the outbound request.
    sent_headers = client.request.await_args.kwargs["headers"]
    assert sent_headers["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_provider_request_with_httpx_transport_error_raises_636() -> None:
    transport_error = httpx.ConnectError("refused")
    with (
        patch("app.api.v1.endpoints.matrix_auth.httpx.AsyncClient", side_effect=transport_error),
        pytest.raises(matrix_auth.MatrixProviderTransportError),
    ):
        await matrix_auth._provider_request_with_httpx(
            "https://x.example", method="POST", form={"a": "b"}
        )


# ── _provider_request dispatch: workers None -> httpx fallback ─────────────────


@pytest.mark.asyncio
async def test_provider_request_falls_back_to_httpx_when_workers_none() -> None:
    # workers path unavailable (dev) -> _provider_request_with_httpx is used.
    with (
        patch.object(matrix_auth, "_provider_request_with_workers", AsyncMock(return_value=None)),
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(
            matrix_auth, "_provider_request_with_httpx", AsyncMock(return_value=(200, {"ok": True}))
        ) as httpx_spy,
    ):
        status, payload = await matrix_auth._provider_request(
            METADATA["token_endpoint"], method="POST", form={"code": "c"}, bearer_token="rt"
        )
    assert status == 200
    assert payload == {"ok": True}
    httpx_spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_request_uses_workers_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    with (
        patch.object(
            matrix_auth,
            "_provider_request_with_workers",
            AsyncMock(return_value=(200, {"from": "workers"})),
        ),
        patch.object(
            matrix_auth,
            "_provider_request_with_httpx",
            AsyncMock(return_value=(200, {"from": "httpx"})),
        ) as httpx_spy,
    ):
        status, payload = await matrix_auth._provider_request(
            METADATA["token_endpoint"], method="POST", form={"code": "c"}, bearer_token="rt"
        )
    assert status == 200
    assert payload == {"from": "workers"}
    httpx_spy.assert_not_called()


# ── _refresh_session failure branches (389-390 transport error, 392 non-200) ────


@pytest.mark.asyncio
async def test_refresh_session_transport_error_returns_none() -> None:
    request = Request(_d1_scope(InMemoryD1Binding()))
    record = {
        "session_id": "s",
        "refresh_token": "ref",
        "access_token": "old",
        "expires_at": int(time.time()) - 1,
        "device_id": "D",
        "matrix_user_id": "@a:e",
        "created_at": 1,
        "updated_at": 1,
    }
    provider = AsyncMock(side_effect=matrix_auth.MatrixProviderTransportError("gone"))
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        result = await matrix_auth._refresh_session(request, record)
    assert result is None
    provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_session_non_200_returns_none() -> None:
    db = InMemoryD1Binding()
    request = Request(_d1_scope(db))
    record = {
        "session_id": "s",
        "refresh_token": "ref",
        "access_token": "old",
        "expires_at": int(time.time()) - 1,
        "device_id": "D",
        "matrix_user_id": "@a:e",
        "created_at": 1,
        "updated_at": 1,
    }
    provider = AsyncMock(return_value=(500, {"err": "server"}))
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        result = await matrix_auth._refresh_session(request, record)
    assert result is None


# ── _refresh_session in-memory store when db is None (405) ──────────────────────


@pytest.mark.asyncio
async def test_refresh_session_updates_in_memory_when_db_none() -> None:
    # _get_session returns the db-None path: _refresh_session writes to _oauth_sessions.
    request = Request({"type": "http", "headers": []})  # no env -> from_scope None
    record = {
        "session_id": "mem-sess",
        "refresh_token": "ref",
        "access_token": "old",
        "expires_at": int(time.time()) - 1,
        "device_id": "D",
        "matrix_user_id": "@a:e",
        "created_at": 1,
        "updated_at": 1,
    }
    matrix_auth._oauth_sessions["mem-sess"] = dict(record)
    provider_ok = AsyncMock(return_value=(200, {"access_token": "new", "expires_in": 3600}))
    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider_ok),
    ):
        result = await matrix_auth._refresh_session(request, record)
    assert result is not None
    assert matrix_auth._oauth_sessions["mem-sess"]["access_token"] == "new"


# ── session_status: bad expires_at (696-697) + expired refresh-failure (703->706) ─


@pytest.mark.asyncio
async def test_session_status_bad_expires_at_returns_unauthenticated() -> None:
    # D1-backed record with non-int expires_at -> int() raises -> 696-697.
    db = InMemoryD1Binding()
    await db.execute(
        "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
        "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["sess-badexp", "@a:e", "D", "tok", "ref", "Bearer", "not-an-int", 1, 1],
    )
    headers = [(b"cookie", f"{matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME}=sess-badexp".encode())]
    d1_request = Request({"type": "http", "headers": headers, "env": SimpleNamespace(DB=db)})
    with _patch_from_scope_to(db):
        status = await matrix_auth.session_status(d1_request)
    assert status.authenticated is False


@pytest.mark.asyncio
async def test_session_status_expired_refresh_failure_deletes_session_703() -> None:
    db = InMemoryD1Binding()
    expired = int(time.time()) - 1
    await db.execute(
        "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
        "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["sess-exp", "@a:e", "D", "tok", None, "Bearer", expired, 1, 1],
    )
    headers = [(b"cookie", f"{matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME}=sess-exp".encode())]
    d1_request = Request({"type": "http", "headers": headers, "env": SimpleNamespace(DB=db)})
    # _refresh_session will call _provider_request; without refresh_token it returns None (376).
    with _patch_from_scope_to(db):
        status = await matrix_auth.session_status(d1_request)
    assert status.authenticated is False
    # Session was deleted (704) because refresh returned None.
    assert "sess-exp" not in db._tables["matrix_oauth_sessions"]


# ── _discover_metadata non-200 (143-144) ─────────────────────────────────______


@pytest.mark.asyncio
async def test_discover_metadata_404_raises_unsupported() -> None:
    with (
        patch.object(matrix_auth, "_fetch_metadata_with_workers", AsyncMock(return_value=None)),
        patch.object(
            matrix_auth,
            "_fetch_metadata_with_httpx",
            AsyncMock(return_value=(404, {})),
        ),
        pytest.raises(matrix_auth.MatrixDiscoveryError) as raised,
    ):
        await matrix_auth._discover_metadata()
    assert raised.value.reason == "unsupported"


@pytest.mark.asyncio
async def test_discover_metadata_non_200_raises_unavailable() -> None:
    with (
        patch.object(matrix_auth, "_fetch_metadata_with_workers", AsyncMock(return_value=None)),
        patch.object(
            matrix_auth,
            "_fetch_metadata_with_httpx",
            AsyncMock(return_value=(500, {})),
        ),
        pytest.raises(matrix_auth.MatrixDiscoveryError) as raised,
    ):
        await matrix_auth._discover_metadata()
    assert raised.value.reason == "unexpected_status"


# ── _provider_request_with_workers bearer header (163) ─────────────────_______


@pytest.mark.asyncio
async def test_provider_request_with_workers_sets_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    workers_module = ModuleType("workers")
    js_resp = MagicMock(status=200)
    js_resp.json = AsyncMock(return_value={"access_token": "a"})
    workers_module.fetch = AsyncMock(return_value=js_resp)  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"workers": workers_module}):
        await matrix_auth._provider_request_with_workers(
            "https://x.example", bearer_token="secret", method="GET"
        )
    sent_headers = workers_module.fetch.await_args.kwargs["headers"]  # type: ignore[attr-defined]
    assert sent_headers["Authorization"] == "Bearer secret"


# ── _store_state in-memory path when db is None (283) ──────────────────────────


@pytest.mark.asyncio
async def test_store_state_in_memory_when_db_none() -> None:
    request = Request({"type": "http", "headers": []})  # no env -> from_scope None
    matrix_auth._oauth_states.clear()
    await matrix_auth._store_state(
        request,
        "state-mem",
        {
            "code_verifier": "v",
            "redirect_uri": "u",
            "device_id": "D",
            "expires_at": 9999999999,
            "created_at": 1,
        },
    )
    assert matrix_auth._state_hash("state-mem") in matrix_auth._oauth_states


# ── _store_state production-no-D1 (283) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_store_state_production_no_d1_raises_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    request = Request({"type": "http", "headers": []})  # no env -> from_scope None
    with pytest.raises(HTTPException) as raised:
        await matrix_auth._store_state(
            request,
            "state-prod",
            {
                "code_verifier": "v",
                "redirect_uri": "u",
                "device_id": "D",
                "expires_at": 9999999999,
                "created_at": 1,
            },
        )
    assert raised.value.status_code == 503


# ── _store_session D1 write failure (354) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_store_session_503_when_d1_write_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "test")  # dev -> D1 path
    fake_db = MagicMock(spec=matrix_auth.D1Client)
    fake_db.execute = AsyncMock(return_value=False)
    request = Request(_d1_scope(fake_db))
    with (
        patch.object(matrix_auth.D1Client, "from_scope", classmethod(lambda cls, scope: fake_db)),
        pytest.raises(HTTPException) as raised,
    ):
        await matrix_auth._store_session(
            request,
            "sess-fail",
            {
                "matrix_user_id": "@a:e",
                "device_id": "D",
                "access_token": "t",
                "refresh_token": "r",
                "token_type": "Bearer",
                "expires_at": 1,
                "created_at": 1,
                "updated_at": 1,
            },
        )
    assert raised.value.status_code == 503


# ── _fetch_metadata_with_httpx: .get raises (134) ─────────────────────────────


@pytest.mark.asyncio
async def test_fetch_metadata_with_httpx_get_raises_transport_error() -> None:
    # AsyncClient constructs fine, but client.get raises httpx.HTTPError (134).
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("app.api.v1.endpoints.matrix_auth.httpx.AsyncClient", return_value=client),
        pytest.raises(matrix_auth.MatrixDiscoveryError) as raised,
    ):
        await matrix_auth._fetch_metadata_with_httpx("https://matrix.example")
    assert raised.value.reason == "transport_error"


# ── _fetch_metadata_with_httpx: 200 with JS metadata (143-144 + 272-273) ────────


@pytest.mark.asyncio
async def test_fetch_metadata_with_httpx_200_converts_js_metadata() -> None:
    class JavaScriptMetadata:
        def to_py(self) -> dict[str, object]:
            return METADATA

    response = MagicMock(status_code=200)
    response.json = MagicMock(return_value=JavaScriptMetadata())
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.api.v1.endpoints.matrix_auth.httpx.AsyncClient", return_value=client):
        status, payload = await matrix_auth._fetch_metadata_with_httpx("https://matrix.example")
    assert status == 200
    assert payload == METADATA


# ── require_authenticated_matrix_session disabled (437) ───────────────────────


@pytest.mark.asyncio
async def test_require_authenticated_disabled_raises_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix_auth.settings, "ENABLE_MATRIX_AUTH", False)
    request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as raised:
        await matrix_auth.require_authenticated_matrix_session(request)
    assert raised.value.status_code == 403


# ── auth_status: discovery success -> final return (540) ──────────────────────


@pytest.mark.asyncio
async def test_auth_status_available_when_discovery_succeeds() -> None:
    with patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)):
        status = await matrix_auth.auth_status()
    assert status.enabled is True
    assert status.available is True


# ── session_status: no cookie (687) + record-None (693) ───────────────────────


@pytest.mark.asyncio
async def test_session_status_no_cookie_returns_unauthenticated_687() -> None:
    request = Request({"type": "http", "headers": []})  # no cookie
    status = await matrix_auth.session_status(request)
    assert status.authenticated is False


@pytest.mark.asyncio
async def test_session_status_record_none_returns_unauthenticated_693(client: TestClient) -> None:
    db = InMemoryD1Binding()
    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "missing-sess")
    with (
        _patch_from_scope_to(db),
        patch.object(matrix_auth, "_get_session", AsyncMock(return_value=None)),
    ):
        response = client.get("/auth/matrix/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


# ── session_status disabled endpoint (676) ─────────────────────────────────


def test_session_status_disabled_returns_unauthenticated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "ENABLE_MATRIX_AUTH", False)
    response = client.get("/auth/matrix/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


# ── session_status: successful refresh path (703->706 False branch) ─────────


@pytest.mark.asyncio
async def test_session_status_refreshes_then_returns_authenticated() -> None:
    db = InMemoryD1Binding()
    now = int(time.time()) + 10  # not yet expired
    await db.execute(
        "INSERT INTO matrix_oauth_sessions (session_id, matrix_user_id, device_id, "
        "access_token, refresh_token, token_type, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["sess-ok", "@user:e", "DEV1", "tok", "ref", "Bearer", now, 1, 1],
    )
    headers = [(b"cookie", f"{matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME}=sess-ok".encode())]
    d1_request = Request({"type": "http", "headers": headers, "env": SimpleNamespace(DB=db)})
    with _patch_from_scope_to(db):
        status = await matrix_auth.session_status(d1_request)
    assert status.authenticated is True
    assert status.user_id == "@user:e"
    assert status.device_id == "DEV1"


# ── _json_object_to_python callable to_py (272-273) ─────────────────────────


def test_json_object_to_python_uses_callable_to_py() -> None:
    class JsWithToPy:
        def to_py(self) -> dict[str, object]:
            return {"converted": "metadata"}

    result = matrix_auth._json_object_to_python(JsWithToPy())
    assert result == {"converted": "metadata"}


def test_json_object_to_python_falls_back_for_plain_dict() -> None:
    result = matrix_auth._json_object_to_python({"plain": "dict"})
    assert result == {"plain": "dict"}
