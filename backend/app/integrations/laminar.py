# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Laminar Integration - Custom OTLP HTTP JSON Forwarder (No lmnr SDK)

The Python lmnr SDK depends on grpcio (C extension, socket, threading),
opentelemetry-sdk (BatchSpanProcessor uses threading.Thread),
opentelemetry-instrumentation-threading (monkey-patches the threading
module), and blake3 (C extension) - all non-functional in Pyodide/WASM
(Cloudflare Python Workers).

This module now delegates OTLP payload construction to
app/integrations/otlp_builder.py (DRY - shared with langfuse.py).
Only Laminar-specific auth, PII stripping, endpoint, and sampling
logic lives here.

Architecture:
    app/main.py lifespan calls laminar.configure(api_key, endpoint, ...)
    LaminarMiddleware creates a root SERVER span per request
    The @observe decorator wraps service functions and creates child spans
    Both funnel into _send_spans() which builds the OTLP payload via
    otlp_builder.build_span/build_resource_spans, then POSTs to Laminar
    via fire_and_forget() with Bearer auth.

No-op contract:
    If LMNR_ENABLED is False OR LMNR_PROJECT_API_KEY is empty, all public
    functions (configure, observe, LaminarMiddleware) return immediately
    without raising.

GDPR contract:
    _strip_pii() runs on every attribute dict before it reaches
    _send_spans(). When LMNR_SEND_PROMPT_CONTENT is False (default), any
    key that could carry document/translation/query content is dropped.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from app.integrations.http_forwarder import fire_and_forget
from app.integrations.otlp_builder import (
    SPAN_KIND_INTERNAL,
    SPAN_KIND_SERVER,
    _current_span_id,
    _current_trace_id,
    _new_span_id,
    _new_trace_id,
    build_resource_spans,
    build_span,
)

logger = logging.getLogger(__name__)

# ParamSpec + TypeVar for the @observe decorator typing
_P = ParamSpec("_P")
_R = TypeVar("_R")

# Module-level state (mirrors sentry.py / datadog.py pattern)
_api_key: str | None = None
_endpoint: str | None = None
_service_name: str = "evidence-eu-backend"
_send_prompt_content: bool = False
_sample_rate: float = 1.0
_enabled: bool = False

# PII content keys (GDPR Art. 5(1)(c) - data minimisation)
_CONTENT_KEYS: frozenset[str] = frozenset(
    [
        "content",
        "text",
        "document",
        "document_content",
        "prompt",
        "query",
        "source_text",
        "translated_text",
        "input_text",
        "output_text",
        "ocr_text",
        "raw_text",
        "answer",
        "chunk_text",
    ]
)
_CONTENT_KEY_SUBSTRING = ".content"


def configure(
    api_key: str | None,
    endpoint: str = "https://api.lmnr.ai:443/v1/traces",
    *,
    enabled: bool = False,
    service_name: str = "evidence-eu-backend",
    send_prompt_content: bool = False,
    sample_rate: float = 1.0,
) -> None:
    """Configure the Laminar OTLP HTTP JSON forwarder.

    Must be called at app startup, in the lifespan handler, before any
    middleware runs. If enabled is False or api_key is empty, the
    forwarder becomes a no-op. Same graceful-degradation contract as
    Sentry, Datadog, and D1Client.
    """
    global _api_key, _endpoint, _service_name, _send_prompt_content
    global _sample_rate, _enabled

    if not enabled or not api_key:
        logger.debug(
            "LMNR_ENABLED=%s or LMNR_PROJECT_API_KEY unset - Laminar disabled (no-op)",
            enabled,
        )
        _api_key = None
        _endpoint = None
        _enabled = False
        return

    _api_key = api_key
    _endpoint = endpoint
    _service_name = service_name
    _send_prompt_content = send_prompt_content
    _sample_rate = sample_rate
    _enabled = True
    logger.info("Laminar configured - service=%s endpoint=%s", service_name, endpoint)


def _strip_pii(attrs: dict[str, Any]) -> dict[str, Any]:
    """Strip document/prompt/query content from span attributes.

    When LMNR_SEND_PROMPT_CONTENT is False (default), removes any key
    that is a known content key or contains the substring ".content".
    Metadata (model, token counts, latency, language codes, status
    codes, route paths) always passes through unchanged.
    """
    if _send_prompt_content:
        return attrs

    stripped: dict[str, Any] = {}
    for key, value in attrs.items():
        lowered = key.lower()
        if lowered in _CONTENT_KEYS:
            continue
        if _CONTENT_KEY_SUBSTRING in lowered:
            continue
        stripped[key] = value
    return stripped


def _build_span(
    *,
    name: str,
    kind: int,
    start_ns: int,
    end_ns: int,
    attributes: dict[str, Any],
    trace_id: str,
    span_id: str,
    parent_span_id: str | None = None,
    status_code: int = 1,
) -> dict[str, Any]:
    """Thin wrapper — strips PII then delegates to shared builder.

    Re-exported as _build_span for backward compatibility with tests.
    """
    return build_span(
        name=name,
        kind=kind,
        start_ns=start_ns,
        end_ns=end_ns,
        attributes=_strip_pii(attributes),
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        status_code=status_code,
    )


def _build_resource_spans(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """Thin wrapper — delegates to shared builder.

    Re-exported for backward compatibility with tests.
    """
    return build_resource_spans(
        spans,
        service_name=_service_name,
        scope_name="evidence-eu.laminar-forwarder",
    )


async def _send_spans(spans: list[dict[str, Any]]) -> None:
    """Ship spans to Laminar via OTLP over HTTP JSON.

    Single HTTP call site for Laminar. fire_and_forget() guarantees
    no blocking and no raising — the try/except is defense in depth.
    """
    if not _enabled or not spans:
        return

    if _sample_rate < 1.0 and random.random() > _sample_rate:
        return

    try:
        payload = _build_resource_spans(spans)
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {_api_key}"}
        await fire_and_forget(_endpoint or "", headers, payload, timeout=5.0)
    except Exception:  # noqa: BLE001 - best effort, never raise
        logger.debug("Failed to build or ship Laminar spans", exc_info=True)


def observe(
    name: str | None = None, span_type: str = "DEFAULT"
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Decorator that wraps an async function in a Laminar span.

    Captures duration and exception status. Service functions may
    attach extra metadata via _lmnr_attrs on the returned object.

    No-op contract: checks _enabled at call time (not decoration time).
    """

    def decorator(func: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            if not _enabled:
                return await func(*args, **kwargs)

            trace_id = _current_trace_id.get() or _new_trace_id()
            parent_span_id = _current_span_id.get()
            span_id = _new_span_id()

            trace_token = _current_trace_id.set(trace_id)
            span_token = _current_span_id.set(span_id)

            start_ns = time.time_ns()
            status_code = 1
            attributes: dict[str, Any] = {"lmnr.span.type": span_type}
            try:
                result = await func(*args, **kwargs)
                extra = getattr(result, "_lmnr_attrs", None)
                if isinstance(extra, dict):
                    attributes.update(extra)
                return result
            except Exception:
                status_code = 2
                raise
            finally:
                try:
                    end_ns = time.time_ns()
                    span = _build_span(
                        name=span_name,
                        kind=SPAN_KIND_INTERNAL,
                        start_ns=start_ns,
                        end_ns=end_ns,
                        attributes=attributes,
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        status_code=status_code,
                    )
                    await _send_spans([span])
                    _current_trace_id.reset(trace_token)
                    _current_span_id.reset(span_token)
                except Exception:  # noqa: BLE001
                    pass  # Monitoring must never mask the response

        return wrapper

    return decorator


class LaminarMiddleware:
    """Pure ASGI middleware creating a root SERVER span per request.

    Implemented as raw ASGI (not BaseHTTPMiddleware) to avoid buffering.
    Propagates the generated traceId via a contextvar so any
    @observe-wrapped service call becomes a child span of this root.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not _enabled or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path.startswith("/health") or path.startswith("/api/v1/health"):
            await self.app(scope, receive, send)
            return

        trace_id = _new_trace_id()
        span_id = _new_span_id()
        trace_token = _current_trace_id.set(trace_id)
        span_token = _current_span_id.set(span_id)

        method = scope.get("method", "GET")
        start_ns = time.time_ns()
        status_holder: dict[str, int] = {"status": 200}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status_holder["status"] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                end_ns = time.time_ns()
                http_status = status_holder["status"]
                span_attrs = {
                    "http.method": method,
                    "http.route": path,
                    "http.status_code": http_status,
                }
                span_status = 1 if http_status < 500 else 2
                span = _build_span(
                    name=method + " " + path,
                    kind=SPAN_KIND_SERVER,
                    start_ns=start_ns,
                    end_ns=end_ns,
                    attributes=span_attrs,
                    trace_id=trace_id,
                    span_id=span_id,
                    status_code=span_status,
                )
                await _send_spans([span])
                _current_trace_id.reset(trace_token)
                _current_span_id.reset(span_token)
            except Exception:  # noqa: BLE001
                pass  # Monitoring must never mask the response
