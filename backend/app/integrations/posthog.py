# SPDX-License-Identifier: AGPL-3.0-or-later
"""
PostHog Integration — Direct HTTP Product Analytics (No posthog-python SDK)

The posthog-python SDK uses threading internally (Consumer daemon thread with
requests). In Cloudflare Workers (Pyodide/WASM), threading is non-functional
— events are enqueued but never flushed. This module bypasses the SDK entirely,
constructing PostHog /capture payloads and handing them to http_forwarder.py
(the same pattern used by sentry.py, datadog.py, laminar.py, langfuse.py).

Architecture:
    app/main.py lifespan → configure(api_key, host)
         │
         ▼
    PostHogMiddleware (middleware.py) — reads X-POSTHOG-DISTINCT-ID / SESSION-ID
    headers, gates on X-GDPR-Consent, extracts request context
         │
         ▼
    capture_event() — fire-and-forget POST to PostHog /capture API
         │
         ▼
    http_forwarder.py — shared httpx + ctx.waitUntil + no-loop fallback

No-op contract:
    If POSTHOG_PROJECT_TOKEN is unset, empty, or POSTHOG_DISABLED=True,
    configure() is a no-op and get_client() returns None. All callers must
    guard with `if ph := get_client()` before calling capture_event().

GDPR guarantee:
    capture_event() returns immediately (no-op) when the X-GDPR-Consent
    header is absent from the request context. This is enforced in
    PostHogMiddleware — not per-endpoint.
"""

from __future__ import annotations

import logging
from typing import Any

from app.integrations.http_forwarder import fire_and_forget

logger = logging.getLogger(__name__)

# ── Module-level state ──────────────────────────────────────────────────────

_api_key: str | None = None
_host: str | None = None
_enabled: bool = False


# ── Configuration ────────────────────────────────────────────────────────────


def configure(api_key: str, host: str, disabled: bool = False) -> None:
    """Configure PostHog at app startup (lifespan).

    If api_key is empty or disabled is True, PostHog is a no-op.
    Follows the same graceful-degradation pattern as sentry.py and datadog.py.
    """
    global _api_key, _host, _enabled

    # Always reset state first — prevents stale config from previous calls
    _api_key = None
    _host = None
    _enabled = False

    if disabled or not api_key or api_key == "<ph_project_token>":
        logger.debug("PostHog not configured — integration disabled (no-op)")
        return

    _api_key = api_key
    _host = host.rstrip("/")
    _enabled = True
    logger.info("PostHog configured — host=%s", _host)


def get_client() -> Any | None:
    """Return a truthy sentinel when configured, None otherwise.

    This matches the no-op singleton contract used by sentry.py and datadog.py.
    Callers use `if ph := get_client():` to gate PostHog calls.
    """
    if not _enabled or not _api_key:
        return None
    return _api_key


# ── Public API ────────────────────────────────────────────────────────────────


async def capture_event(
    event: str,
    distinct_id: str,
    properties: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> None:
    """Capture a PostHog event via direct HTTP POST (fire-and-forget).

    This is the shared DRY helper for all PostHog events. Endpoints call this
    helper — never the PostHog SDK directly. Properties are additive —
    never include document content, filenames, or extracted text.

    Args:
        event:       Event name (e.g. "document_translated", "search_performed").
        distinct_id: User identifier. Must be non-empty and non-IP. For
                     authenticated requests, use the Matrix user ID. For
                     anonymous requests, use a random UUID (not persistent).
        properties:  Event properties — additive only. Allowed: file_type,
                     language_pair, duration_ms, result_count, query_length,
                     status_code, protocol. Never: document content, filenames,
                     extracted text.
        session_id:  PostHog session ID from X-POSTHOG-SESSION-ID header
                     (set by the frontend JS SDK). Used to correlate backend
                     events with frontend user sessions.
    """
    if not _enabled or not _api_key or not _host:
        return

    if not distinct_id or distinct_id.startswith("anonymous-"):
        logger.debug("PostHog capture skipped — invalid distinct_id")
        return

    payload: dict[str, Any] = {
        "api_key": _api_key,
        "event": event,
        "distinct_id": distinct_id,
        "properties": {
            "$session_id": session_id,
            # Anonymous events only — don't create person profiles for
            # backend captures (GDPR data minimisation, Art. 5(1)(c)).
            # PostHog still aggregates events under the distinct_id but
            # doesn't build a person profile with properties.
            "$process_person_profile": False,
            **(properties or {}),
        },
    }

    try:
        await fire_and_forget(
            f"{_host}/capture/",
            {"Content-Type": "application/json"},
            payload,
        )
    except Exception:
        logger.warning("PostHog capture failed for event=%s", event, exc_info=True)
