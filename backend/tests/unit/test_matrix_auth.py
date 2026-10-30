# SPDX-License-Identifier: AGPL-3.0-or-later
"""ADR-019 Matrix OAuth 2.0 + PKCE endpoint tests."""

from __future__ import annotations

import sys
import time
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient

from app.api.v1.endpoints import matrix_auth

METADATA = {
    "authorization_endpoint": "https://account.example/oauth2/auth",
    "token_endpoint": "https://account.example/oauth2/token",
    "revocation_endpoint": "https://account.example/oauth2/revoke",
    "registration_endpoint": "https://account.example/oauth2/register",
    "code_challenge_methods_supported": ["S256"],
}


@pytest.fixture(autouse=True)
def matrix_settings(monkeypatch: pytest.MonkeyPatch):
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


def test_status_is_transparent_noop_when_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "ENABLE_MATRIX_AUTH", False)

    response = client.get("/auth/matrix/status")

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "available": False}


def test_status_returns_public_safe_discovery_reason(client: TestClient) -> None:
    error = matrix_auth.MatrixDiscoveryError(
        "incomplete_metadata", "Matrix OAuth metadata is incomplete"
    )
    with patch.object(matrix_auth, "_discover_metadata", AsyncMock(side_effect=error)):
        response = client.get("/auth/matrix/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "available": False,
        "reason": "incomplete_metadata",
    }
    assert "Matrix OAuth metadata is incomplete" not in response.text


@pytest.mark.asyncio
async def test_production_discovery_prefers_native_workers_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    native = AsyncMock(return_value=(200, METADATA))
    fallback = AsyncMock()

    with (
        patch.object(matrix_auth, "_fetch_metadata_with_workers", native),
        patch.object(matrix_auth, "_fetch_metadata_with_httpx", fallback),
    ):
        metadata = await matrix_auth._discover_metadata()

    assert metadata == METADATA
    native.assert_awaited_once()
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_discovery_falls_back_to_httpx_when_native_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    native = AsyncMock(return_value=None)
    fallback = AsyncMock(return_value=(200, METADATA))

    with (
        patch.object(matrix_auth, "_fetch_metadata_with_workers", native),
        patch.object(matrix_auth, "_fetch_metadata_with_httpx", fallback),
    ):
        metadata = await matrix_auth._discover_metadata()

    assert metadata == METADATA
    fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_discovery_log_excludes_exception_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("sensitive-value")
    )
    with (
        patch.dict(sys.modules, {"workers": workers_module}),
        caplog.at_level("WARNING"),
    ):
        result = await matrix_auth._fetch_metadata_with_workers("https://matrix.example")

    assert result is None
    assert "RuntimeError" in caplog.text
    assert "sensitive-value" not in caplog.text


@pytest.mark.asyncio
async def test_native_discovery_converts_javascript_metadata_to_python() -> None:
    class JavaScriptMetadata:
        def to_py(self) -> dict[str, object]:
            return METADATA

    response = MagicMock(status=200)
    response.json = AsyncMock(return_value=JavaScriptMetadata())
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(return_value=response)  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"workers": workers_module}):
        result = await matrix_auth._fetch_metadata_with_workers("https://matrix.example")

    assert result == (200, METADATA)


@pytest.mark.asyncio
async def test_native_provider_request_encodes_form_without_logging_secrets() -> None:
    class JavaScriptPayload:
        def to_py(self) -> dict[str, object]:
            return {"access_token": "matrix-secret"}

    response = MagicMock(status=200)
    response.json = AsyncMock(return_value=JavaScriptPayload())
    workers_module = ModuleType("workers")
    workers_module.fetch = AsyncMock(return_value=response)  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"workers": workers_module}):
        result = await matrix_auth._provider_request_with_workers(
            "https://account.example/oauth2/token",
            method="POST",
            form={"code": "one-time-code", "code_verifier": "pkce-secret"},
        )

    assert result == (200, {"access_token": "matrix-secret"})
    request = workers_module.fetch.await_args  # type: ignore[attr-defined]
    assert request.kwargs["method"] == "POST"
    assert request.kwargs["headers"]["Content-Type"] == ("application/x-www-form-urlencoded")
    assert request.kwargs["body"] == "code=one-time-code&code_verifier=pkce-secret"


@pytest.mark.asyncio
async def test_production_provider_request_does_not_fall_back_to_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    native = AsyncMock(return_value=None)
    fallback = AsyncMock()

    with (
        patch.object(matrix_auth, "_provider_request_with_workers", native),
        patch.object(matrix_auth, "_provider_request_with_httpx", fallback),
        pytest.raises(matrix_auth.MatrixProviderTransportError),
    ):
        await matrix_auth._provider_request("https://account.example/oauth2/token")

    fallback.assert_not_awaited()


def test_login_discovers_endpoints_and_builds_pkce_request(client: TestClient) -> None:
    with patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)):
        response = client.get("/auth/matrix/login", follow_redirects=False)

    assert response.status_code == 302
    redirect = urlparse(response.headers["location"])
    query = parse_qs(redirect.query)
    assert (
        f"{redirect.scheme}://{redirect.netloc}{redirect.path}"
        == METADATA["authorization_endpoint"]
    )
    assert query["code_challenge_method"] == ["S256"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [matrix_auth.settings.MATRIX_OAUTH_CALLBACK_URL]
    assert "urn:matrix:client:api:*" in query["scope"][0]
    assert "urn:matrix:client:device:" in query["scope"][0]
    assert len(matrix_auth._oauth_states) == 1
    stored = next(iter(matrix_auth._oauth_states.values()))
    assert stored["code_verifier"] not in response.headers["location"]


def test_callback_rejects_missing_or_replayed_state(client: TestClient) -> None:
    # When state is unknown (already consumed or never created), the
    # callback redirects to the post-login URL instead of erroring.
    # This prevents "Authorization grant already used" errors when the
    # browser sends concurrent requests to the callback URL.
    response = client.get(
        "/auth/matrix/callback",
        params={"code": "code-1", "state": "unknown"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == matrix_auth.settings.MATRIX_OAUTH_POST_LOGIN_URL


def test_callback_exchanges_code_verifies_identity_and_sets_opaque_cookie(
    client: TestClient,
) -> None:
    state = "state-123"
    matrix_auth._oauth_states[matrix_auth._state_hash(state)] = {
        "code_verifier": "v" * 64,
        "redirect_uri": matrix_auth.settings.MATRIX_OAUTH_CALLBACK_URL,
        "device_id": "DEVICE1234",
        "expires_at": int(time.time()) + 300,
        "created_at": int(time.time()),
    }
    provider = AsyncMock(
        side_effect=[
            (
                200,
                {
                    "access_token": "matrix-access-secret",
                    "refresh_token": "matrix-refresh-secret",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            ),
            (200, {"user_id": "@alice:matrix.example", "device_id": "DEVICE1234"}),
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

    assert response.status_code == 302
    assert response.headers["location"] == "https://app.example/"
    cookie = response.headers["set-cookie"]
    assert "evidenceeu_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "matrix-access-secret" not in cookie
    assert matrix_auth._state_hash(state) not in matrix_auth._oauth_states
    assert len(matrix_auth._oauth_sessions) == 1
    token_call = provider.await_args_list[0]
    assert token_call.kwargs["form"]["code_verifier"] == "v" * 64
    assert "Authorization" not in str(token_call.kwargs["form"])
    whoami_call = provider.await_args_list[1]
    assert whoami_call.kwargs["bearer_token"] == "matrix-access-secret"


def test_production_cookie_is_secure_and_cross_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    response = Response()

    matrix_auth._set_session_cookie(response, "opaque-session")

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=none" in cookie


def test_session_returns_only_identity_not_matrix_tokens(client: TestClient) -> None:
    matrix_auth._oauth_sessions["session-1"] = {
        "session_id": "session-1",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
        "access_token": "secret",
        "refresh_token": "refresh",
        "expires_at": int(time.time()) + 300,
    }

    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "session-1")
    response = client.get("/auth/matrix/session")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
    }
    assert "secret" not in response.text


def test_expired_session_without_refresh_token_fails_closed(client: TestClient) -> None:
    matrix_auth._oauth_sessions["expired"] = {
        "session_id": "expired",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
        "access_token": "secret",
        "refresh_token": None,
        "expires_at": int(time.time()) - 1,
    }

    client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "expired")
    response = client.get("/auth/matrix/session")

    assert response.json() == {"authenticated": False, "user_id": None, "device_id": None}
    assert "expired" not in matrix_auth._oauth_sessions


@pytest.mark.asyncio
async def test_authenticated_session_dependency_returns_server_only_credentials() -> None:
    matrix_auth._oauth_sessions["session-1"] = {
        "session_id": "session-1",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
        "access_token": "matrix-access-secret",
        "refresh_token": "matrix-refresh-secret",
        "expires_at": int(time.time()) + 300,
    }
    request = Request(
        {
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    f"{matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME}=session-1".encode(),
                )
            ],
        }
    )

    session = await matrix_auth.require_authenticated_matrix_session(request)

    assert session.user_id == "@alice:matrix.example"
    assert session.device_id == "DEVICE1234"
    assert session.access_token == "matrix-access-secret"
    assert session.session_id == "session-1"
    assert "matrix-access-secret" not in repr(session)


@pytest.mark.asyncio
async def test_authenticated_session_dependency_requires_cookie() -> None:
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as raised:
        await matrix_auth.require_authenticated_matrix_session(request)

    assert raised.value.status_code == 401
    assert raised.value.detail == "Matrix authentication required"


@pytest.mark.asyncio
async def test_authenticated_session_dependency_refreshes_expired_token() -> None:
    matrix_auth._oauth_sessions["expired"] = {
        "session_id": "expired",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
        "access_token": "old-access",
        "refresh_token": "refresh-secret",
        "expires_at": int(time.time()) - 1,
    }
    request = Request(
        {
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    f"{matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME}=expired".encode(),
                )
            ],
        }
    )
    refreshed = {
        **matrix_auth._oauth_sessions["expired"],
        "access_token": "new-access",
        "expires_at": int(time.time()) + 300,
    }

    with patch.object(
        matrix_auth,
        "_refresh_session",
        AsyncMock(return_value=refreshed),
    ) as refresh:
        session = await matrix_auth.require_authenticated_matrix_session(request)

    refresh.assert_awaited_once()
    assert session.access_token == "new-access"


def test_logout_revokes_tokens_deletes_session_and_cookie(client: TestClient) -> None:
    matrix_auth._oauth_sessions["session-1"] = {
        "session_id": "session-1",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_at": int(time.time()) + 300,
    }
    provider = AsyncMock(return_value=(200, {}))

    with (
        patch.object(matrix_auth, "_discover_metadata", AsyncMock(return_value=METADATA)),
        patch.object(matrix_auth, "_provider_request", provider),
    ):
        client.cookies.set(matrix_auth.settings.MATRIX_OAUTH_COOKIE_NAME, "session-1")
        response = client.post("/auth/matrix/logout")

    assert response.status_code == 200
    assert "session-1" not in matrix_auth._oauth_sessions
    assert provider.await_count == 2
    assert all(call.kwargs["expect_json"] is False for call in provider.await_args_list)
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_production_session_storage_requires_d1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as raised:
        await matrix_auth._store_session(request, "session-1", {})

    assert raised.value.status_code == 503
    assert "Authentication session storage unavailable" in str(raised.value.detail)


def test_status_returns_available_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    with patch.object(matrix_auth, "_discover_metadata") as mock_discover:
        response = client.get("/auth/matrix/status")

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "available": True}
    mock_discover.assert_not_called()


def test_login_redirects_to_dashboard_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    with patch.object(matrix_auth, "_discover_metadata") as mock_discover:
        response = client.get("/auth/matrix/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == matrix_auth.settings.MATRIX_OAUTH_POST_LOGIN_URL
    mock_discover.assert_not_called()


def test_session_returns_demo_user_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")

    response = client.get("/auth/matrix/session")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "user_id": "@demo_bot:evidenceeu.eu.mihai.codes",
        "device_id": "DEMO",
    }


@pytest.mark.asyncio
async def test_require_auth_session_returns_demo_session_when_env_token_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    request = Request({"type": "http", "headers": []})

    session = await matrix_auth.require_authenticated_matrix_session(request)

    assert session.user_id == "@demo_bot:evidenceeu.eu.mihai.codes"
    assert session.device_id == "DEMO"
    assert session.access_token == "demo-token"
    assert session.session_id == "demo-session"


def test_logout_sets_demo_logout_cookie_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")

    response = client.post("/auth/matrix/logout")

    assert response.status_code == 200
    assert "matrix_demo_logout=1;" in response.headers.get("set-cookie", "")
    # 1 hour expiry
    assert "Max-Age=3600" in response.headers["set-cookie"]


def test_logout_cookie_uses_samesite_none_secure_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")

    response = client.post("/auth/matrix/logout")

    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert "SameSite=none" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie


def test_session_returns_not_authenticated_when_demo_logout_cookie_present(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    client.cookies.set("matrix_demo_logout", "1")

    response = client.get("/auth/matrix/session")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user_id": None, "device_id": None}


def test_login_clears_demo_logout_cookie_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")

    with patch.object(matrix_auth, "_discover_metadata") as mock_discover:
        response = client.get("/auth/matrix/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == matrix_auth.settings.MATRIX_OAUTH_POST_LOGIN_URL
    cookie = response.headers.get("set-cookie", "")
    assert 'matrix_demo_logout=""' in cookie
    assert "Max-Age=0" in cookie
    assert "Secure" not in cookie  # test env, not production
    mock_discover.assert_not_called()


def test_login_clears_demo_logout_with_samesite_none_secure_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    # Set a production-like post-login URL (pages.dev)
    monkeypatch.setattr(
        matrix_auth.settings,
        "MATRIX_OAUTH_POST_LOGIN_URL",
        "https://evidence-eu-frontend.pages.dev/dashboard",
    )

    with patch.object(matrix_auth, "_discover_metadata") as mock_discover:
        response = client.get("/auth/matrix/login", follow_redirects=False)

    assert response.status_code == 302
    cookie = response.headers.get("set-cookie", "")
    assert 'matrix_demo_logout=""' in cookie
    assert "SameSite=none" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    mock_discover.assert_not_called()


@pytest.mark.asyncio
async def test_require_auth_session_raises_401_when_demo_logout_cookie_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", b"matrix_demo_logout=1")],
        }
    )

    with pytest.raises(HTTPException) as raised:
        await matrix_auth.require_authenticated_matrix_session(request)

    assert raised.value.status_code == 401
    assert raised.value.detail == "Matrix authentication required"


def test_callback_redirects_when_env_token_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "demo-token")

    with patch.object(matrix_auth, "_discover_metadata") as mock_discover:
        response = client.get(
            "/auth/matrix/callback",
            params={"code": "code-1", "state": "state-123"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == matrix_auth.settings.MATRIX_OAUTH_POST_LOGIN_URL
    mock_discover.assert_not_called()


def test_logout_oauth_path_deletes_cookie_with_matching_attributes_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OAuth-path logout must delete the session cookie with SameSite=None; Secure.

    Safari/WebKit refuses to delete a cookie whose deletion attributes don't
    match the original.  _clear_session_cookie uses set_cookie(max_age=0) with
    matching SameSite/Secure instead of Starlette's delete_cookie (which
    defaults to SameSite=Lax).
    """
    monkeypatch.setattr(matrix_auth.settings, "APP_ENV", "production")
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_ACCESS_TOKEN", "")
    monkeypatch.setattr(matrix_auth.settings, "MATRIX_OAUTH_COOKIE_NAME", "evidenceeu_session")
    # Simulate an existing OAuth session cookie so the logout endpoint enters
    # the OAuth path (not the demo-token path).
    client.cookies.set("evidenceeu_session", "session-abc")

    with patch.object(matrix_auth, "_get_session", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None  # session already invalid
        response = client.post("/auth/matrix/logout")

    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert 'evidenceeu_session=""' in cookie
    assert "Max-Age=0" in cookie
    assert "SameSite=none" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
