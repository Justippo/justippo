# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Custom Middleware

Responsibilities:
- GDPRConsentMiddleware: block requests lacking a valid GDPR consent token
- AuditLogMiddleware: write structured audit entries for all document operations
- SentryMiddleware: capture unhandled 500 errors via Pyodide-safe Sentry forwarder
"""

import re
from datetime import timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# PII Log Sanitizer (GDPR Art. 5(1)(c) — data minimisation)
# ---------------------------------------------------------------------------
# Redacts query string values while preserving parameter names for debugging.
# Example: "q=John+Doe&lang=en" → "q=[REDACTED]&lang=[REDACTED]"
# Health endpoints are exempt (no PII in health probe params).

_REDACT_QS_PATTERN = re.compile(r"=[^&\s]*")
_HEALTH_PREFIXES = ("/health", "/api/v1/health")


def redact_query_string(qs: str) -> str:
    """Redact all query string values, keeping parameter names.

    Args:
        qs: Raw query string (e.g. from request.url.query or str(request.query_params)).

    Returns:
        Sanitized query string with values replaced by [REDACTED].
    """
    if not qs:
        return ""
    return _REDACT_QS_PATTERN.sub("=[REDACTED]", qs)


def sanitize_request_url_for_logging(url_str: str) -> str:
    """Sanitize a full URL string by redacting its query string portion.

    Args:
        url_str: Full URL string (e.g. str(request.url)).

    Returns:
        URL with query values redacted. If no query string, returns unchanged.
    """
    if "?" not in url_str:
        return url_str
    base, qs = url_str.split("?", 1)
    return f"{base}?{redact_query_string(qs)}"


# Paths that must always be reachable without a consent token.
# Health probes must work for Cloudflare to detect liveness; API docs are
# unauthenticated by design.
_CONSENT_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health",  # root liveness probe (GET /health)
    "/api/v1/health",  # v1 liveness + readiness probes
    "/api/docs",  # Swagger UI
    "/api/redoc",  # ReDoc UI
    "/api/openapi.json",  # OpenAPI schema download
    # OAuth redirects and callbacks cannot attach the application consent
    # header. Matrix obtains its own explicit authorization at the provider.
    "/api/v1/auth/matrix",
    # Exchange endpoints use Matrix OAuth cookies, not the GDPR consent header.
    # Matrix obtains its own explicit authorization at the identity provider.
    "/api/v1/exchange",
)


class GDPRConsentMiddleware(BaseHTTPMiddleware):
    """
    Verifies that the requesting user has provided valid GDPR consent
    before allowing access to document processing endpoints (GDPR Article 7).

    Expected header: ``X-GDPR-Consent: <token>``

    Returns HTTP 451 Unavailable For Legal Reasons when the header is
    absent and ``GDPR_CONSENT_REQUIRED=true`` in settings.

    Exempt paths (always pass through without a consent header):
        /health, /api/v1/health/*, /api/v1/auth/matrix/*, /api/docs,
        /api/redoc, /api/openapi.json

    Sprint 2+: validate token signature / expiry in addition to presence.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.core.config import settings  # local import — avoids circular deps at module load

        # Consent checking can be disabled globally (e.g., local dev, unit tests).
        if not settings.GDPR_CONSENT_REQUIRED:
            return await call_next(request)

        # Health probes and API documentation are always exempt.
        path: str = request.url.path
        if any(path.startswith(prefix) for prefix in _CONSENT_EXEMPT_PREFIXES):
            return await call_next(request)

        # CORS Preflight requests don't send custom headers, so they must be exempt
        if request.method == "OPTIONS":
            return await call_next(request)

        # All other endpoints require the consent header or query parameter (for SSE EventSource)
        consent = request.headers.get("X-GDPR-Consent") or request.query_params.get("gdpr_consent")
        if not consent:
            return Response(
                content='{"detail": "GDPR consent required. Provide X-GDPR-Consent header."}',
                status_code=451,
                media_type="application/json",
            )

        # Token is present — pass through.
        # Sprint 2: add signature / expiry validation here before call_next.
        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Writes a structured audit log entry for every request (GDPR Article 30).

    Log schema (metadata only — no document content, no PII):
        timestamp, method, path, status_code, duration_ms,
        request_id_hash, mime_type, target_lang

    D1 binding is accessed via request.scope["env"].DB (Cloudflare ASGI bridge).
    When DB is unavailable (local dev, CI), the middleware logs a debug warning
    and passes the request through — audit logging must never break functionality.

    Paths audited: /api/v1/documents/*, /api/v1/translate/*
    Paths exempt:  /health/*, /api/docs, /api/redoc, /api/openapi.json
    """

    _AUDIT_PATHS: tuple[str, ...] = (
        "/api/v1/documents",
        "/api/v1/translate",
        "/api/v1/search",
        "/api/v1/chat",
    )
    _EXEMPT_PREFIXES: tuple[str, ...] = (
        "/health",
        "/api/v1/health",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        import hashlib
        import time
        from datetime import datetime

        from app.db.d1_client import D1Client

        path: str = request.url.path

        # Pass through exempt paths without any audit overhead
        if any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            return await call_next(request)

        # Only audit document/translation operations
        should_audit = any(path.startswith(p) for p in self._AUDIT_PATHS)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        if not should_audit:
            return response

        # Extract metadata — never log document content
        mime_type: str | None = (
            request.headers.get("content-type", "").split(";")[0].strip() or None
        )
        # target_lang is a form field — only available via parsed body on POST,
        # so we read it from query params as fallback (GET /search uses it too)
        target_lang: str | None = request.query_params.get("target_lang")

        # SHA256[:8] of a per-request nonce — provides traceability without PII
        nonce = request.headers.get("x-request-id", str(time.monotonic_ns()))
        request_id_hash = hashlib.sha256(nonce.encode()).hexdigest()[:8]

        timestamp = datetime.now(timezone.utc).isoformat()  # noqa: UP017

        # Write to D1 — gracefully skip when binding unavailable (dev/CI)
        db = D1Client.from_scope(request.scope)
        if db is None:
            import logging

            logging.getLogger(__name__).debug(
                "AuditLogMiddleware: D1 binding unavailable — skipping write "
                "(expected in local dev and CI)"
            )
        else:
            # NT-3: Read injection detection fields from request.state.
            # Services/endpoints set these via:
            #   request.state.injection_detected = True
            #   request.state.injection_patterns = ["pattern_name", ...]
            # Falls back to False/None when not set (backwards-compatible).
            injection_detected: bool = getattr(request.state, "injection_detected", False)
            injection_patterns_raw: list[str] = getattr(request.state, "injection_patterns", [])
            injection_patterns_json: str | None = (
                __import__("json").dumps(injection_patterns_raw) if injection_patterns_raw else None
            )

            await db.execute(
                """
                INSERT INTO audit_log
                    (timestamp, method, path, status_code, duration_ms,
                     request_id_hash, mime_type, target_lang,
                     injection_detected, injection_patterns)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    timestamp,
                    request.method,
                    path,
                    response.status_code,
                    duration_ms,
                    request_id_hash,
                    mime_type,
                    target_lang,
                    1 if injection_detected else 0,
                    injection_patterns_json,
                ],
            )

        return response


class SentryMiddleware(BaseHTTPMiddleware):
    """
    Captures unhandled 500 errors and ships them to Sentry.

    This middleware wraps the entire request cycle. If any downstream middleware
    or endpoint raises an unhandled exception, it ships the error to Sentry via
    the custom Envelope forwarder (app/integrations/sentry.py) and then re-raises
    the exception so FastAPI/Starlette can generate the standard 500 response.

    Pyodide constraint:
        Do NOT use sentry-sdk in the backend. The Python SDK uses threading,
        sockets, and ssl; those are not functional in Cloudflare Python Workers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            from app.integrations.sentry import ship_to_sentry  # noqa: PLC0415

            request_ctx = {
                "method": request.method,
                "url": sanitize_request_url_for_logging(str(request.url)),
                "headers": dict(request.headers),
                "query_string": redact_query_string(str(request.query_params)),
            }
            await ship_to_sentry(exc, request_ctx)
            # Re-raise — let Starlette/FastAPI generate the 500 response.
            raise


class DatadogMetricsMiddleware(BaseHTTPMiddleware):
    """
    Records request duration + status code and ships to Datadog as custom metrics.

    Uses time.perf_counter() for high-resolution duration measurement.
    Route paths are normalized (UUIDs → {id}) to avoid high-cardinality tags.
    All query params are stripped from metric tags to prevent PII leakage.

    NFR Traceability:
        - NFR-01: p95 latency (metric: evidence_eu.request.duration)
        - NFR-02: error rate (metric: evidence_eu.request.count, tag: status:5xx)

    Must run AFTER SentryMiddleware so Sentry captures errors before Datadog
    records the status code. In FastAPI middleware stack, later-added middleware
    runs first on the way in — so DatadogMetricsMiddleware (added after Sentry)
    wraps SentryMiddleware, measuring total duration including Sentry's handling.

    Pyodide constraint:
        Do NOT use ddtrace in the backend. The Python agent uses socket,
        threading, and native C extensions; none functional in Pyodide/WASM.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        import time as _time

        from app.core.config import settings  # noqa: PLC0415

        start = _time.perf_counter()
        status = 500

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            raise
        finally:
            try:
                from app.integrations.datadog import (  # noqa: PLC0415
                    build_metric_series,
                    ship_metrics,
                )

                duration_ms = (_time.perf_counter() - start) * 1000
                series = build_metric_series(
                    route=request.url.path,
                    method=request.method,
                    status=status,
                    duration_ms=duration_ms,
                    env=settings.APP_ENV,
                )
                await ship_metrics(series)
            except Exception:  # noqa: BLE001
                pass  # Metrics must never mask the response

        return response


class DemoWarmupMiddleware(BaseHTTPMiddleware):
    """Detects cold starts and annotates responses for demo observability.

    Activated only when DEMO_MODE=true. On the first request after Worker
    cold start, adds X-Cold-Start: true header and logs the cold-start
    latency separately so it does not pollute p95 metrics.

    No-op when DEMO_MODE is false (default).
    """

    _warmed_up: bool = False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        import logging as _logging
        import time as _time

        from app.core.config import settings  # noqa: PLC0415

        # No-op if demo mode is disabled
        if not getattr(settings, "DEMO_MODE", False):
            return await call_next(request)

        is_cold = not DemoWarmupMiddleware._warmed_up
        start = _time.perf_counter()
        response = await call_next(request)
        duration_ms = (_time.perf_counter() - start) * 1000

        if is_cold:
            DemoWarmupMiddleware._warmed_up = True
            response.headers["X-Cold-Start"] = "true"
            response.headers["X-Cold-Start-Ms"] = str(int(duration_ms))
            _logging.getLogger(__name__).info(
                "DEMO cold start detected: %.0fms on %s %s",
                duration_ms,
                request.method,
                request.url.path,
            )

        return response


class PostHogMiddleware(BaseHTTPMiddleware):
    """Extracts PostHog session context from request headers for event correlation.

    Reads X-POSTHOG-DISTINCT-ID and X-POSTHOG-SESSION-ID headers (set by the
    PostHog JS SDK on the frontend) to correlate backend events with frontend
    user sessions. The middleware does NOT capture events directly — it stores
    the context in request.state so endpoint handlers can pass it to
    capture_event().

    GDPR gate: PostHog is completely silent when X-GDPR-Consent header is
    absent. The middleware returns 451 (via GDPRConsentMiddleware) for
    non-exempt routes before any PostHog processing occurs.

    No-op when the PostHog client is not configured.
    """

    _EXEMPT_PREFIXES: tuple[str, ...] = (
        "/health",
        "/api/v1/health",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.integrations.posthog import get_client  # noqa: PLC0415

        if get_client() is None:
            return await call_next(request)

        path: str = request.url.path
        if any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            return await call_next(request)

        # GDPR gate: skip PostHog context extraction when consent is absent.
        # GDPRConsentMiddleware returns 451 for non-exempt routes, but we
        # check here too for defense-in-depth (middleware ordering race).
        gdpr_consent = request.headers.get("X-GDPR-Consent", "")
        if not gdpr_consent:
            return await call_next(request)

        # Store PostHog context in request.state for endpoint handlers
        request.state.posthog_distinct_id = request.headers.get("X-POSTHOG-DISTINCT-ID")
        request.state.posthog_session_id = request.headers.get("X-POSTHOG-SESSION-ID")

        return await call_next(request)
