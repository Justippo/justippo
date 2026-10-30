# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Datadog Custom Metrics Forwarder (No ddtrace in Pyodide)

The Python `ddtrace` agent uses socket, threading, and native C extensions —
all non-functional in Pyodide/WASM. This module implements a minimal Datadog
metrics forwarder that works in both Docker (uvicorn) and Cloudflare Workers
(Pyodide) using only httpx (already a dependency) via the shared
http_forwarder module.

Architecture:
    app/main.py lifespan → datadog.configure(api_key)
         │
         ▼
    DatadogMetricsMiddleware (middleware.py) records request duration + status
         │
         ▼
    ship_metrics(series)  →  fire_and_forget() → httpx POST to Datadog API
         │
         ▼
    POST https://api.{site}/api/v1/series
    Body: {"series": [{"metric": "...", "points": [...], "tags": [...]}]}

NFR Traceability:
    This middleware provides evidence for:
    - NFR-01: p95 latency ≤ 5s (metric: evidence_eu.request.duration)
    - NFR-02: error rate < 1% (metric: evidence_eu.request.count, tag: status:5xx)
    - NFR-01 diagnosis: search stage latency
      (metric: evidence_eu.search.stage.duration)

No-op contract:
    If DATADOG_API_KEY is unset or empty, ALL functions return immediately
    without raising. Same graceful-degradation pattern as Sentry + D1Client.
"""

from __future__ import annotations

import logging
import re
import time
from contextvars import ContextVar, Token
from typing import Any

from app.integrations.http_forwarder import fire_and_forget, post_now

logger = logging.getLogger(__name__)

# ── Module-level state ───────────────────────────────────────────────────────

_api_key: str | None = None
_site: str = "us5.datadoghq.com"
_metrics_url: str | None = None
_enabled: bool = False

# A mutable list is deliberately stored per request. asyncio task creation
# copies the ContextVar while retaining the list identity, so Hindsight recall
# running in the SSE child task and answer generation in the stream task append
# to the same privacy-safe batch without any global cross-request state.
_search_stage_batch: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "datadog_search_stage_batch", default=None
)

# Regex for UUID normalization in route paths
# Matches: 550e8400-e29b-41d4-a716-446655440000
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# Also normalize long hex strings (D1 row IDs, etc.)
_HEX_ID_RE = re.compile(r"/([0-9a-f]{16,})(?=/|$)", re.IGNORECASE)


# ── Configuration ────────────────────────────────────────────────────────────


def configure(api_key: str | None, site: str = "us5.datadoghq.com") -> None:
    """Configure the Datadog metrics forwarder.

    Must be called at app startup (lifespan) before any middleware runs.
    If `api_key` is empty or None, the forwarder is a no-op.

    Args:
        api_key: Datadog API key (server-only, never exposed to browser).
        site:    Datadog site (default: datadoghq.com).
    """
    global _api_key, _site, _metrics_url, _enabled

    if not api_key:
        logger.debug("DATADOG_API_KEY not set — Datadog integration disabled (no-op)")
        _api_key = None
        _metrics_url = None
        _enabled = False
        return

    _api_key = api_key
    _site = site
    _metrics_url = f"https://api.{site}/api/v1/series"
    _enabled = True
    logger.info("Datadog configured — site=%s", site)


# ── Route Normalization + PII Stripping ──────────────────────────────────────


def normalize_route(path: str) -> str:
    """Normalize a URL path for metric tags — strips UUIDs and long hex IDs.

    Examples:
        /api/v1/documents/550e8400-e29b-41d4-a716-446655440000
            → /api/v1/documents/{id}
        /api/v1/documents/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
            → /api/v1/documents/{id}
        /api/v1/search?q=passport
            → /api/v1/search  (query params stripped — may contain PII)

    PII stripping rationale:
        Query parameters in /search, /translate, and /documents may contain
        document content, user tokens, or file names. We strip ALL query
        params from metric tags to prevent accidental PII leakage.
    """
    # Strip query string entirely (may contain search terms, file names, tokens)
    path = path.split("?")[0]

    # Replace UUIDs with {id}
    path = _UUID_RE.sub("{id}", path)

    # Replace long hex strings with {id}
    path = _HEX_ID_RE.sub("/{id}", path)

    return path


# ── Metric Builder ───────────────────────────────────────────────────────────


def build_metric_series(
    route: str,
    method: str,
    status: int,
    duration_ms: float,
    env: str,
) -> dict[str, Any]:
    """Build a Datadog MetricSeries payload for request metrics.

    Emits two metrics per request:
    1. evidence_eu.request.duration (gauge) — duration in milliseconds
    2. evidence_eu.request.count (count) — incremented by 1

    Tags (no PII):
        route:<normalized_path>   — e.g. /api/v1/documents/{id}
        method:<HTTP_METHOD>      — GET, POST, etc.
        status:<HTTP_STATUS_CODE> — 200, 404, 500, etc.
        env:<environment>         — production, development, test

    Args:
        route:       Normalized route path (use normalize_route() first).
        method:      HTTP method (GET, POST, etc.).
        status:      HTTP status code.
        duration_ms: Request duration in milliseconds (use time.perf_counter()).
        env:         Environment name (production, development, test).

    Returns:
        Dict ready to POST to /api/v1/series as JSON body.
    """
    normalized = normalize_route(route)
    timestamp = int(time.time())

    tags = [
        f"route:{normalized}",
        f"method:{method}",
        f"status:{status}",
        f"env:{env}",
    ]

    return {
        "series": [
            {
                "metric": "evidence_eu.request.duration",
                # Datadog v1 intake requires [timestamp, value] tuples. The
                # object-shaped point schema belongs to /api/v2/series.
                "points": [[timestamp, duration_ms]],
                "tags": tags,
                "type": "gauge",
            },
            {
                "metric": "evidence_eu.request.count",
                "points": [[timestamp, 1]],
                "tags": tags,
                "type": "count",
            },
        ]
    }


def build_search_stage_series(
    stage: str,
    outcome: str,
    duration_ms: float,
    env: str,
    *,
    fallback: bool = False,
) -> dict[str, Any]:
    """Build a privacy-safe latency metric for one search pipeline stage.

    Only fixed, low-cardinality values supplied by the application are tagged.
    In particular, queries, document identifiers, bank identifiers, and result
    content are intentionally absent from the payload.
    """
    timestamp = int(time.time())
    tags = [
        f"stage:{stage}",
        f"outcome:{outcome}",
        f"env:{env}",
    ]
    if fallback:
        tags.append("fallback:true")

    return {
        "series": [
            {
                "metric": "evidence_eu.search.stage.duration",
                "points": [[timestamp, duration_ms]],
                "tags": tags,
                "type": "gauge",
            }
        ]
    }


def begin_search_stage_batch() -> Token[list[dict[str, Any]] | None]:
    """Start collecting search-stage series for the current SSE request."""
    return _search_stage_batch.set([])


def reset_search_stage_batch(token: Token[list[dict[str, Any]] | None]) -> None:
    """Restore the prior stage batch after an SSE request completes."""
    _search_stage_batch.reset(token)


async def record_search_stage(series: dict[str, Any]) -> None:
    """Collect an SSE stage metric, or use background delivery outside SSE."""
    batch = _search_stage_batch.get()
    if batch is None:
        await ship_metrics(series)
        return

    batch.extend(series.get("series", []))


async def flush_search_stage_batch() -> None:
    """Synchronously flush one combined stage payload before the SSE ``done`` event."""
    batch = _search_stage_batch.get()
    if not _enabled or not batch:
        return

    headers = {
        "Content-Type": "application/json",
        "DD-API-KEY": _api_key or "",
    }
    payload = {"series": list(batch)}
    batch.clear()
    await post_now(_metrics_url or "", headers, payload, timeout=5.0)


# ── Fire-and-Forget Sender ───────────────────────────────────────────────────


async def ship_metrics(series: dict[str, Any]) -> None:
    """Ship a metric series to Datadog asynchronously, fire-and-forget.

    Uses the shared http_forwarder.fire_and_forget() utility (DRY — same
    pattern as Sentry envelope shipping). Never blocks or raises.
    """
    if not _enabled:
        return

    headers = {
        "Content-Type": "application/json",
        "DD-API-KEY": _api_key or "",
    }

    await fire_and_forget(
        _metrics_url or "",
        headers,
        series,
        timeout=5.0,
    )
