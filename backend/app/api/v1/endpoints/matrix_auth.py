# SPDX-License-Identifier: AGPL-3.0-or-later
"""Feature-flagged Matrix OAuth 2.0 Authorization Code + PKCE endpoints.

ADR-019 keeps Matrix credentials and OAuth tokens outside browser JavaScript.
The browser receives only an opaque HttpOnly EvidenceEU session cookie.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.core.config import settings
from app.db.d1_client import D1Client

router = APIRouter(prefix="/matrix")

_SCOPE_API = "urn:matrix:client:api:*"
_SCOPE_DEVICE_PREFIX = "urn:matrix:client:device:"
logger = logging.getLogger(__name__)
MatrixDiscoveryReason = Literal[
    "transport_error",
    "unsupported",
    "unexpected_status",
    "incomplete_metadata",
]

# Local/test fallback only. Production requires D1 so OAuth state and sessions
# survive isolate recycling without writing to disk.
_oauth_states: dict[str, dict[str, Any]] = {}
_oauth_sessions: dict[str, dict[str, Any]] = {}


class MatrixAuthStatus(BaseModel):
    enabled: bool
    available: bool
    reason: MatrixDiscoveryReason | None = None


class MatrixDiscoveryError(HTTPException):
    """A public-safe discovery failure with no provider response data."""

    def __init__(self, reason: MatrixDiscoveryReason, detail: str) -> None:
        super().__init__(status_code=503, detail=detail)
        self.reason = reason


class MatrixProviderTransportError(Exception):
    """Internal provider transport failure with no sensitive response detail."""


class MatrixSessionStatus(BaseModel):
    authenticated: bool
    user_id: str | None = None
    device_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuthenticatedMatrixSession:
    """Server-only Matrix identity and credentials for authenticated operations."""

    session_id: str
    user_id: str
    device_id: str
    access_token: str = field(repr=False)


def _require_enabled() -> None:
    if not settings.ENABLE_MATRIX_AUTH:
        raise HTTPException(status_code=403, detail="Matrix authentication is disabled")


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _has_env_token() -> bool:
    return bool(settings.MATRIX_ACCESS_TOKEN)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _json_object_to_python(payload: Any) -> dict[str, Any]:
    """Normalize a Workers JavaScript JSON object at the Pyodide FFI boundary."""
    to_py = getattr(payload, "to_py", None)
    if callable(to_py):
        payload = to_py()
    if not isinstance(payload, dict):
        raise TypeError("Matrix provider payload is not an object")
    return cast(dict[str, Any], payload)


async def _fetch_metadata_with_workers(url: str) -> tuple[int, dict[str, Any]] | None:
    """Use the native Workers Fetch API when running inside Pyodide.

    Returning ``None`` means the runtime API is unavailable and lets local
    development and tests continue through httpx.
    """
    try:
        from workers import fetch as workers_fetch  # noqa: PLC0415
    except ImportError:
        return None

    try:
        response = await workers_fetch(url, headers={"Accept": "application/json"})
        status = int(response.status)
        payload = _json_object_to_python(await response.json()) if status == 200 else {}
        return status, payload
    except Exception as exc:  # JS FFI exceptions do not inherit from httpx.HTTPError
        logger.warning(
            "matrix_oauth_discovery transport=workers_fetch outcome=error error_type=%s",
            type(exc).__name__,
        )
        return None


async def _fetch_metadata_with_httpx(url: str) -> tuple[int, dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        logger.warning(
            "matrix_oauth_discovery transport=httpx outcome=error error_type=%s",
            type(exc).__name__,
        )
        raise MatrixDiscoveryError(
            "transport_error", "Matrix authentication is unavailable"
        ) from exc
    payload = _json_object_to_python(response.json()) if response.status_code == 200 else {}
    return response.status_code, payload


async def _provider_request_with_workers(
    url: str,
    *,
    method: str = "GET",
    form: dict[str, str] | None = None,
    bearer_token: str | None = None,
    expect_json: bool = True,
) -> tuple[int, dict[str, Any]] | None:
    """Call a Matrix OAuth endpoint through the native Workers Fetch API."""
    try:
        from workers import fetch as workers_fetch  # noqa: PLC0415
    except ImportError:  # pragma: no cover - Workers-only; never imported under pytest
        return None

    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    kwargs: dict[str, Any] = {"method": method, "headers": headers}
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        kwargs["body"] = urlencode(form)

    try:
        response = await workers_fetch(url, **kwargs)
        status = int(response.status)
        payload = (
            _json_object_to_python(await response.json()) if expect_json and status == 200 else {}
        )
        return status, payload
    except Exception as exc:  # pragma: no cover - Workers-only JS FFI path; never runs under pytest
        logger.warning(
            "matrix_oauth_provider transport=workers_fetch outcome=error error_type=%s",
            type(exc).__name__,
        )
        raise MatrixProviderTransportError from exc


async def _provider_request_with_httpx(
    url: str,
    *,
    method: str = "GET",
    form: dict[str, str] | None = None,
    bearer_token: str | None = None,
    expect_json: bool = True,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method,
                url,
                data=form,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "matrix_oauth_provider transport=httpx outcome=error error_type=%s",
            type(exc).__name__,
        )
        raise MatrixProviderTransportError from exc
    payload = (
        _json_object_to_python(response.json())
        if expect_json and response.status_code == 200
        else {}
    )
    return response.status_code, payload


async def _provider_request(
    url: str,
    *,
    method: str = "GET",
    form: dict[str, str] | None = None,
    bearer_token: str | None = None,
    expect_json: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Use native fetch in production and httpx only outside Workers."""
    if settings.is_production:
        result = await _provider_request_with_workers(
            url,
            method=method,
            form=form,
            bearer_token=bearer_token,
            expect_json=expect_json,
        )
        if result is None:
            logger.warning("matrix_oauth_provider transport=workers_fetch outcome=unavailable")
            raise MatrixProviderTransportError
        return result
    return await _provider_request_with_httpx(
        url,
        method=method,
        form=form,
        bearer_token=bearer_token,
        expect_json=expect_json,
    )


async def _discover_metadata() -> dict[str, Any]:
    url = f"{settings.MATRIX_HOMESERVER_URL.rstrip('/')}/_matrix/client/v1/auth_metadata"
    result = await _fetch_metadata_with_workers(url) if settings.is_production else None
    if result is None:
        result = await _fetch_metadata_with_httpx(url)
    status_code, metadata = result

    if status_code == 404:
        logger.warning("matrix_oauth_discovery outcome=unsupported status_code=404")
        raise MatrixDiscoveryError("unsupported", "Matrix OAuth is not supported")
    if status_code != 200:
        logger.warning(
            "matrix_oauth_discovery outcome=unexpected_status status_code=%s", status_code
        )
        raise MatrixDiscoveryError("unexpected_status", "Matrix authentication is unavailable")

    required = {
        "authorization_endpoint",
        "token_endpoint",
        "revocation_endpoint",
        "registration_endpoint",
    }
    if not required.issubset(metadata) or "S256" not in metadata.get(
        "code_challenge_methods_supported", []
    ):
        logger.warning("matrix_oauth_discovery outcome=incomplete_metadata")
        raise MatrixDiscoveryError("incomplete_metadata", "Matrix OAuth metadata is incomplete")
    logger.info("matrix_oauth_discovery outcome=available pkce=S256")
    return metadata


async def _store_state(request: Request, state: str, record: dict[str, Any]) -> None:
    key = _state_hash(state)
    db = D1Client.from_scope(request.scope)
    if db is None:
        if settings.is_production:
            raise HTTPException(
                status_code=503, detail="Authentication session storage unavailable"
            )
        _oauth_states[key] = record
        return
    ok = await db.execute(
        """INSERT INTO matrix_oauth_states
        (state_hash, code_verifier, redirect_uri, device_id, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        [
            key,
            record["code_verifier"],
            record["redirect_uri"],
            record["device_id"],
            record["expires_at"],
            record["created_at"],
        ],
    )
    if not ok:
        raise HTTPException(status_code=503, detail="Authentication session storage unavailable")


async def _consume_state(request: Request, state: str) -> dict[str, Any] | None:
    key = _state_hash(state)
    db = D1Client.from_scope(request.scope)
    if db is None:
        record = _oauth_states.pop(key, None)
    else:
        # D1's .first() doesn't work with DELETE...RETURNING (treats DELETE
        # as a write op, returns None even with RETURNING clause). Use
        # SELECT then DELETE — the race window is acceptable because the
        # callback now redirects to dashboard instead of erroring when
        # state is already consumed.
        record = await db.fetch_one("SELECT * FROM matrix_oauth_states WHERE state_hash = ?", [key])
        if record is not None:
            await db.execute("DELETE FROM matrix_oauth_states WHERE state_hash = ?", [key])
    if record is None or int(record["expires_at"]) < int(time.time()):
        return None
    return record


async def _store_session(request: Request, session_id: str, record: dict[str, Any]) -> None:
    # D1 is the server-only session boundary and provides provider-managed
    # encryption at rest. Matrix tokens are never returned to browser code,
    # URLs, logs, or telemetry.
    db = D1Client.from_scope(request.scope)
    if db is None:
        if settings.is_production:
            raise HTTPException(
                status_code=503, detail="Authentication session storage unavailable"
            )
        _oauth_sessions[session_id] = record
        return
    ok = await db.execute(
        """INSERT INTO matrix_oauth_sessions
        (session_id, matrix_user_id, device_id, access_token, refresh_token,
         token_type, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            session_id,
            record["matrix_user_id"],
            record["device_id"],
            record["access_token"],
            record.get("refresh_token"),
            record["token_type"],
            record["expires_at"],
            record["created_at"],
            record["updated_at"],
        ],
    )
    if not ok:
        raise HTTPException(status_code=503, detail="Authentication session storage unavailable")


async def _get_session(request: Request, session_id: str) -> dict[str, Any] | None:
    db = D1Client.from_scope(request.scope)
    if db is None:
        return _oauth_sessions.get(session_id)
    return await db.fetch_one(
        "SELECT * FROM matrix_oauth_sessions WHERE session_id = ?", [session_id]
    )


async def _delete_session(request: Request, session_id: str) -> None:
    db = D1Client.from_scope(request.scope)
    if db is None:
        _oauth_sessions.pop(session_id, None)
        return
    await db.execute("DELETE FROM matrix_oauth_sessions WHERE session_id = ?", [session_id])


async def _refresh_session(request: Request, record: dict[str, Any]) -> dict[str, Any] | None:
    refresh_token = record.get("refresh_token")
    if not refresh_token:
        return None
    metadata = await _discover_metadata()
    try:
        status_code, payload = await _provider_request(
            metadata["token_endpoint"],
            method="POST",
            form={
                "grant_type": "refresh_token",
                "refresh_token": str(refresh_token),
                "client_id": settings.MATRIX_CLIENT_ID,
            },
        )
    except MatrixProviderTransportError:
        return None
    if status_code != 200:
        return None
    now = int(time.time())
    record.update(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token", refresh_token),
        token_type=payload.get("token_type", "Bearer"),
        expires_at=now + int(payload.get("expires_in", settings.MATRIX_OAUTH_SESSION_TTL_S)),
        updated_at=now,
    )
    # Use UPDATE instead of DELETE+INSERT to avoid race condition
    # when two concurrent requests refresh the same session.
    db = D1Client.from_scope(request.scope)
    if db is None:
        _oauth_sessions[str(record["session_id"])] = record
    else:
        await db.execute(
            """UPDATE matrix_oauth_sessions
            SET access_token = ?, refresh_token = ?, token_type = ?,
                expires_at = ?, updated_at = ?
            WHERE session_id = ?""",
            [
                record["access_token"],
                record.get("refresh_token"),
                record["token_type"],
                record["expires_at"],
                record["updated_at"],
                str(record["session_id"]),
            ],
        )
    return record


async def require_authenticated_matrix_session(request: Request) -> AuthenticatedMatrixSession:
    """Resolve and refresh the current server-side Matrix OAuth session.

    Matrix tokens remain inside the backend and are never serialized to the
    browser. Exchange endpoints can use this as a FastAPI dependency.

    When MATRIX_ACCESS_TOKEN is set in env vars (demo/local mode), returns a
    demo session using that token directly, bypassing the SSO flow.

    Catches any unexpected exception (D1 result parsing, Pyodide JS proxy
    quirks) and converts it to a safe 401 instead of letting it escape as 500.
    """
    if not settings.ENABLE_MATRIX_AUTH:
        raise HTTPException(status_code=403, detail="Matrix authentication is disabled")

    if _has_env_token():
        if request.cookies.get("matrix_demo_logout"):
            raise HTTPException(status_code=401, detail="Matrix authentication required")
        return AuthenticatedMatrixSession(
            session_id="demo-session",
            user_id="@demo_bot:evidenceeu.eu.mihai.codes",
            device_id="DEMO",
            access_token=settings.MATRIX_ACCESS_TOKEN,
        )

    session_id = request.cookies.get(settings.MATRIX_OAUTH_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Matrix authentication required")

    try:
        record = await _get_session(request, session_id)
    except Exception:  # noqa: BLE001
        logger.warning("D1 session lookup failed unexpectedly", exc_info=True)
        raise HTTPException(status_code=401, detail="Matrix session lookup failed") from None

    if record is None:
        raise HTTPException(status_code=401, detail="Matrix session is invalid or expired")

    try:
        expires_at = int(record["expires_at"])
    except (KeyError, TypeError, ValueError):
        logger.warning("D1 session record missing or corrupt expires_at field")
        raise HTTPException(
            status_code=401, detail="Matrix session is invalid or expired"
        ) from None

    if expires_at <= int(time.time()):
        try:
            record = await _refresh_session(request, record)
        except Exception:  # noqa: BLE001
            logger.warning("Matrix session refresh failed unexpectedly", exc_info=True)
            record = None
        if record is None:
            await _delete_session(request, session_id)
            raise HTTPException(status_code=401, detail="Matrix session is invalid or expired")

    try:
        return AuthenticatedMatrixSession(
            session_id=session_id,
            user_id=str(record["matrix_user_id"]),
            device_id=str(record["device_id"]),
            access_token=str(record["access_token"]),
        )
    except Exception:  # noqa: BLE001
        logger.warning("D1 session record missing or has unexpected structure")
        raise HTTPException(
            status_code=401, detail="Matrix session is invalid or expired"
        ) from None


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=settings.MATRIX_OAUTH_COOKIE_NAME,
        value=session_id,
        max_age=settings.MATRIX_OAUTH_SESSION_TTL_S,
        httponly=True,
        secure=settings.is_production,
        # Production UI and API are on pages.dev and workers.dev respectively,
        # so credentialed API fetches require an explicitly cross-site cookie.
        samesite="none" if settings.is_production else "lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    """Delete the session cookie with attributes matching _set_session_cookie.

    Safari/WebKit refuses to delete a cookie when the deletion response's
    attributes (SameSite, Secure) don't match the original.  Starlette's
    delete_cookie() defaults to SameSite=Lax, which silently fails for a
    SameSite=None cookie.  Using set_cookie with max_age=0 and matching
    attributes ensures cross-browser deletion.
    """
    response.set_cookie(
        key=settings.MATRIX_OAUTH_COOKIE_NAME,
        value="",
        max_age=0,
        httponly=True,
        secure=settings.is_production,
        samesite="none" if settings.is_production else "lax",
        path="/",
    )


@router.get("/status", response_model=MatrixAuthStatus, response_model_exclude_none=True)
async def auth_status() -> MatrixAuthStatus:
    if not settings.ENABLE_MATRIX_AUTH:
        return MatrixAuthStatus(enabled=False, available=False)
    if _has_env_token():
        return MatrixAuthStatus(enabled=True, available=True)
    try:
        await _discover_metadata()
    except MatrixDiscoveryError as exc:
        return MatrixAuthStatus(enabled=True, available=False, reason=exc.reason)
    except HTTPException:
        return MatrixAuthStatus(enabled=True, available=False, reason="transport_error")
    return MatrixAuthStatus(enabled=True, available=True)


@router.get("/login")
async def matrix_login(request: Request) -> RedirectResponse:
    _require_enabled()
    if _has_env_token():
        # Demo mode: replace delete_cookie with explicit set_cookie using
        # matching attributes (SameSite=None; Secure in production).
        # Standalone delete_cookie defaults to SameSite=Lax, which Chrome
        # blocks on cross-site responses.  Using set_cookie with matching
        # attributes ensures the cookie is deleted regardless of context.
        # https://github.com/encode/starlette/issues/1207
        response = RedirectResponse(settings.MATRIX_OAUTH_POST_LOGIN_URL, status_code=302)
        response.set_cookie(
            key="matrix_demo_logout",
            value="",
            max_age=0,
            httponly=True,
            secure=settings.is_production,
            samesite="none" if settings.is_production else "lax",
            path="/",
        )
        return response
    if not settings.MATRIX_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Matrix OAuth client is not configured")
    metadata = await _discover_metadata()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    device_id = secrets.token_urlsafe(12)
    now = int(time.time())
    await _store_state(
        request,
        state,
        {
            "code_verifier": verifier,
            "redirect_uri": settings.MATRIX_OAUTH_CALLBACK_URL,
            "device_id": device_id,
            "expires_at": now + settings.MATRIX_OAUTH_STATE_TTL_S,
            "created_at": now,
        },
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.MATRIX_CLIENT_ID,
            "redirect_uri": settings.MATRIX_OAUTH_CALLBACK_URL,
            "scope": f"{_SCOPE_API} {_SCOPE_DEVICE_PREFIX}{device_id}",
            "state": state,
            "response_mode": "query",
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{metadata['authorization_endpoint']}?{query}", status_code=302)


@router.get("/callback")
async def matrix_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    _require_enabled()
    if _has_env_token():
        return RedirectResponse(settings.MATRIX_OAUTH_POST_LOGIN_URL, status_code=302)
    if error or not code or not state:
        raise HTTPException(status_code=400, detail="Matrix authorization was not completed")
    transaction = await _consume_state(request, state)
    if transaction is None:
        # State already consumed by a concurrent callback request (e.g.,
        # browser prefetch or redirect retry). The first request already
        # created the session — redirect to dashboard instead of erroring.
        # The session cookie (if set) will authenticate; if not, the
        # frontend will redirect to login.
        return RedirectResponse(settings.MATRIX_OAUTH_POST_LOGIN_URL, status_code=302)
    metadata = await _discover_metadata()
    try:
        token_status, token = await _provider_request(
            metadata["token_endpoint"],
            method="POST",
            form={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": str(transaction["redirect_uri"]),
                "client_id": settings.MATRIX_CLIENT_ID,
                "code_verifier": str(transaction["code_verifier"]),
            },
        )
        if token_status != 200:
            raise HTTPException(status_code=401, detail="Matrix token exchange failed")
        whoami_status, identity = await _provider_request(
            f"{settings.MATRIX_HOMESERVER_URL.rstrip('/')}/_matrix/client/v3/account/whoami",
            bearer_token=str(token["access_token"]),
        )
    except MatrixProviderTransportError as exc:
        raise HTTPException(
            status_code=503, detail="Matrix authentication provider unavailable"
        ) from exc
    if whoami_status != 200:
        raise HTTPException(status_code=401, detail="Matrix identity verification failed")
    now = int(time.time())
    session_id = secrets.token_urlsafe(32)
    await _store_session(
        request,
        session_id,
        {
            "session_id": session_id,
            "matrix_user_id": identity["user_id"],
            "device_id": identity.get("device_id") or transaction["device_id"],
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "token_type": token.get("token_type", "Bearer"),
            "expires_at": now + int(token.get("expires_in", settings.MATRIX_OAUTH_SESSION_TTL_S)),
            "created_at": now,
            "updated_at": now,
        },
    )
    from app.integrations.posthog import capture_event  # noqa: PLC0415

    await capture_event(
        "matrix_user_logged_in",
        distinct_id=identity["user_id"],
        properties={"login_method": "matrix_oauth"},
        session_id=getattr(request.state, "posthog_session_id", None),
    )

    response = RedirectResponse(settings.MATRIX_OAUTH_POST_LOGIN_URL, status_code=302)
    _set_session_cookie(response, session_id)
    return response


@router.get("/session", response_model=MatrixSessionStatus)
async def session_status(request: Request) -> MatrixSessionStatus:
    if not settings.ENABLE_MATRIX_AUTH:
        return MatrixSessionStatus(authenticated=False)
    if _has_env_token():
        if request.cookies.get("matrix_demo_logout"):
            return MatrixSessionStatus(authenticated=False)
        return MatrixSessionStatus(
            authenticated=True,
            user_id="@demo_bot:evidenceeu.eu.mihai.codes",
            device_id="DEMO",
        )
    session_id = request.cookies.get(settings.MATRIX_OAUTH_COOKIE_NAME)
    if not session_id:
        return MatrixSessionStatus(authenticated=False)
    try:
        record = await _get_session(request, session_id)
    except Exception:  # noqa: BLE001
        return MatrixSessionStatus(authenticated=False)
    if record is None:
        return MatrixSessionStatus(authenticated=False)
    try:
        expires_at = int(record["expires_at"])
    except (KeyError, TypeError, ValueError):
        return MatrixSessionStatus(authenticated=False)
    if expires_at <= int(time.time()):
        try:
            record = await _refresh_session(request, record)
        except Exception:  # noqa: BLE001
            record = None
        if record is None:
            await _delete_session(request, session_id)
            return MatrixSessionStatus(authenticated=False)
    try:
        return MatrixSessionStatus(
            authenticated=True,
            user_id=str(record["matrix_user_id"]),
            device_id=str(record["device_id"]),
        )
    except (KeyError, TypeError):
        return MatrixSessionStatus(authenticated=False)


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    _require_enabled()
    # CSRF protection: verify Origin header matches our API origin.
    # SameSite=None cookies (required for Pages→Worker cross-site fetch)
    # are vulnerable to CSRF — this check prevents cross-site POST attacks.
    origin = request.headers.get("origin", "")
    if origin and origin not in (
        settings.MATRIX_OAUTH_POST_LOGIN_URL.rsplit("/", 1)[0],  # dashboard URL origin
        "https://evidence-eu-frontend.pages.dev",
        "http://localhost:3000",
    ):
        raise HTTPException(status_code=403, detail="Cross-origin request blocked")
    session_id = request.cookies.get(settings.MATRIX_OAUTH_COOKIE_NAME)
    if session_id:
        record = await _get_session(request, session_id)
        if record is not None:
            try:
                metadata = await _discover_metadata()
                for token in (record.get("refresh_token"), record.get("access_token")):
                    if token:
                        await _provider_request(
                            metadata["revocation_endpoint"],
                            method="POST",
                            form={
                                "token": str(token),
                                "client_id": settings.MATRIX_CLIENT_ID,
                            },
                            expect_json=False,
                        )
            except (HTTPException, MatrixProviderTransportError):
                pass
        await _delete_session(request, session_id)

    if session_id and record is not None:
        from app.integrations.posthog import capture_event  # noqa: PLC0415

        await capture_event(
            "matrix_user_logged_out",
            distinct_id=record["matrix_user_id"],
            session_id=getattr(request.state, "posthog_session_id", None),
        )

    response = JSONResponse({"status": "ok"})
    # NOTE: Pyodide's ASGI → Workers Response handler uses
    # Object.fromEntries() which collapses duplicate header keys.
    # Only the last Set-Cookie header survives.  We use an if/else
    # instead of two separate cookie operations to avoid this.
    if _has_env_token():
        response.set_cookie(
            key="matrix_demo_logout",
            value="1",
            max_age=3600,
            httponly=True,
            secure=settings.is_production,
            samesite="none" if settings.is_production else "lax",
            path="/",
        )
    else:
        # Delete the OAuth session cookie with SameSite=None; Secure (matching
        # _set_session_cookie).  Safari/WebKit refuses to delete a cookie
        # whose deletion attributes don't match the original — see
        # _clear_session_cookie docstring.
        _clear_session_cookie(response)
    return response
