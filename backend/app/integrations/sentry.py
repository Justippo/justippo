# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Sentry Integration — Custom HTTP Envelope Forwarder (No sentry-sdk)

The Python `sentry-sdk` uses threading.Lock, socket, and ssl — all non-functional
in Pyodide/WASM (Cloudflare Python Workers). This module implements a minimal
Sentry Envelope forwarder that works in both Docker (uvicorn) and Cloudflare
Workers (Pyodide) using only httpx (already a dependency).

Architecture:
    app/main.py lifespan → sentry.configure(dsn)
         │
         ▼
    SentryMiddleware (middleware.py) catches unhandled 500s
         │
         ▼
    ship_to_sentry(exc, request)  →  httpx POST to Sentry Envelope API
         │
         ▼
    build_envelope(exc, request)  →  bytes  (envelope header + item header + event JSON)

No-op contract:
    If SENTRY_DSN is unset or empty, ALL functions return immediately without
    raising. This follows the same graceful-degradation pattern as D1Client.

Reference:
    Envelope format: https://develop.sentry.dev/sdk/foundations/envelopes/
    Ingestion endpoint: POST https://o<id>.ingest.sentry.io/api/<project>/envelope/
"""

from __future__ import annotations

import json
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.integrations.http_forwarder import fire_and_forget

logger = logging.getLogger(__name__)

# ── Module-level state ───────────────────────────────────────────────────────

_dsn: str | None = None
_project_id: str | None = None
_ingest_url: str | None = None
_enabled: bool = False


# ── Configuration ─────────────────────────────────────────────────────────────


def configure(dsn: str | None) -> None:
    """Parse the DSN and configure the Sentry forwarder.

    Must be called at app startup (lifespan) before any middleware runs.
    If `dsn` is empty or None, the forwarder is a no-op — this follows the
    same graceful-degradation contract as D1Client.

    DSN format: https://<key>@o<org_id>.ingest.sentry.io/<project_id>
    """
    global _dsn, _project_id, _ingest_url, _enabled

    if not dsn:
        logger.debug("SENTRY_DSN not set — Sentry integration disabled (no-op)")
        _dsn = None
        _project_id = None
        _ingest_url = None
        _enabled = False
        return

    _dsn = dsn
    try:
        parsed = urlparse(dsn)
        # Path is /<project_id>
        _project_id = parsed.path.strip("/")
        # Build ingest URL: https://o<org_id>.ingest.sentry.io/api/<project>/envelope/
        host = parsed.hostname or ""
        _ingest_url = f"https://{host}/api/{_project_id}/envelope/"
        _enabled = True
        logger.info("Sentry configured — project=%s host=%s", _project_id, host)
    except Exception as exc:
        logger.error("Failed to parse Sentry DSN: %s", exc)
        _enabled = False


# ── Envelope Builder ──────────────────────────────────────────────────────────


def _utcnow() -> str:
    """Return current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017  # datetime.UTC breaks mypy on CI typeshed


def build_envelope(exc: BaseException, request: dict[str, Any] | None = None) -> bytes:
    """Build a Sentry Envelope containing a single error event.

    Format (per https://develop.sentry.dev/sdk/foundations/envelopes/):
        {envelope_header}\n
        {item_header}\n
        {event_payload}\n

    Args:
        exc: The exception to capture.
        request: Optional dict with keys: method, url, headers, query_string.

    Returns:
        Raw bytes ready to POST to the Sentry Envelope endpoint.
    """
    event_id = uuid.uuid4().hex
    envelope_header = json.dumps(
        {
            "event_id": event_id,
            "sent_at": _utcnow(),
            "dsn": _dsn,
            "sdk": {
                "name": "evidence-eu.pyodide-sentry-forwarder",
                "version": "0.1.0",
            },
        },
        separators=(",", ":"),
    )

    event_payload = _build_event_payload(exc, request, event_id)
    event_json = json.dumps(event_payload, separators=(",", ":"), default=str)
    event_bytes = event_json.encode("utf-8")

    item_header = json.dumps(
        {
            "type": "event",
            "length": len(event_bytes),
            "content_type": "application/json",
        },
        separators=(",", ":"),
    )

    return b"".join(
        [
            envelope_header.encode("utf-8"),
            b"\n",
            item_header.encode("utf-8"),
            b"\n",
            event_bytes,
            b"\n",
        ]
    )


def _build_event_payload(
    exc: BaseException,
    request: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Construct the event payload JSON for a captured exception."""
    event_id = event_id or uuid.uuid4().hex
    timestamp = _utcnow()

    payload: dict[str, Any] = {
        "event_id": event_id,
        "timestamp": timestamp,
        "platform": "python",
        "level": "error",
        "exception": {
            "values": [
                {
                    "type": type(exc).__name__,
                    "value": str(exc),
                    "stacktrace": _build_stacktrace(exc),
                }
            ],
        },
        "server_name": "evidence-eu-api-worker",
    }

    if request:
        payload["request"] = {
            "method": request.get("method", "GET"),
            "url": request.get("url", ""),
            "headers": _sanitize_headers(request.get("headers", {})),
            "query_string": request.get("query_string", ""),
        }

    return payload


def _build_stacktrace(exc: BaseException) -> dict[str, Any]:
    """Build a Sentry-compatible stacktrace from an exception."""
    frames: list[dict[str, Any]] = []
    tb = exc.__traceback__
    if tb is not None:
        for frame in traceback.extract_tb(tb):
            frames.append(
                {
                    "filename": frame.filename,
                    "function": frame.name,
                    "lineno": frame.lineno,
                    "context_line": frame.line or "",
                }
            )

    return {"frames": frames}


def _sanitize_headers(headers: dict[str, Any]) -> dict[str, str]:
    """Strip sensitive headers before sending to Sentry."""
    SENSITIVE = {"authorization", "cookie", "x-gdpr-consent", "cf-aig-authorization"}
    return {k: "[Filtered]" if k.lower() in SENSITIVE else str(v) for k, v in headers.items()}


# ── Fire-and-Forget Sender ───────────────────────────────────────────────────


async def ship_to_sentry(
    exc: BaseException,
    request: dict[str, Any] | None = None,
) -> None:
    """Ship an error event to Sentry asynchronously, fire-and-forget.

    This must never block the request path. Uses httpx for the HTTP POST
    and asyncio.create_task() to detach from the main response flow.

    If the envelope cannot be shipped (network error, Sentry down), the
    failure is logged at DEBUG level and never raised — monitoring is a
    best-effort enhancement, never a hard requirement.
    """
    if not _enabled:
        return

    try:
        envelope = build_envelope(exc, request)
        await fire_and_forget(
            _ingest_url or "",
            {"Content-Type": "application/x-sentry-envelope"},
            envelope,
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001 — best-effort, never raise
        logger.debug("Failed to build or ship Sentry envelope", exc_info=True)
