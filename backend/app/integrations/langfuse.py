# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Langfuse Integration - Custom Basic Auth OTLP Dispatch (No langfuse SDK)

The Langfuse Python SDK v4 requires opentelemetry-sdk (BatchSpanProcessor
uses threading.Thread) - non-functional in Pyodide/WASM. Instead, we
send OTLP/HTTP/json payloads directly via httpx + http_forwarder.py,
using the exact same shared builder (otlp_builder.py) as laminar.py.

Architecture:
    app/main.py lifespan calls langfuse.configure(public_key, secret_key, ...)
    The trace() context manager and observe_generation decorator both read
    the _current_trace_id contextvar (set by LaminarMiddleware in
    otlp_builder.py) so Langfuse and Laminar traces share IDs.
    The observe_generation decorator wraps LLM call functions and creates
    GENERATION-type spans with gen_ai.usage attributes.

No-op contract:
    If LANGFUSE_ENABLED is False OR either LANGFUSE_PUBLIC_KEY or
    LANGFUSE_SECRET_KEY is empty, the forwarder is a transparent no-op.

GDPR contract:
    When LANGFUSE_SEND_PROMPT_CONTENT is False (default), span attributes
    never include raw prompt/completion text - only metadata (model name,
    token counts, latency, language codes).
"""

from __future__ import annotations

import base64
import functools
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from app.integrations.http_forwarder import fire_and_forget
from app.integrations.otlp_builder import (
    SPAN_KIND_INTERNAL,
    _current_span_id,
    _current_trace_id,
    _new_span_id,
    _new_trace_id,
    build_resource_spans,
    build_span,
)

logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")

# Module-level state
_public_key: str | None = None
_secret_key: str | None = None
_endpoint: str | None = None
_service_name: str = "evidence-eu-backend"
_send_prompt_content: bool = False
_sample_rate: float = 1.0
_enabled: bool = False

# Langfuse-specific PII content keys — extends the standard set with
# Langfuse-native attribute prefixes that carry prompt/completion text.
_LANGFUSE_CONTENT_KEYS: frozenset[str] = frozenset(
    [
        "gen_ai.prompt",
        "gen_ai.completion",
        "langfuse.observation.input",
        "langfuse.observation.output",
    ]
)
_CONTENT_KEY_SUBSTRINGS: tuple[str, ...] = (".content", ".prompt", ".completion")


def configure(
    public_key: str | None,
    secret_key: str | None,
    endpoint: str = "https://cloud.langfuse.com/api/public/otel/v1/traces",
    *,
    enabled: bool = False,
    service_name: str = "evidence-eu-backend",
    send_prompt_content: bool = False,
    sample_rate: float = 1.0,
) -> None:
    """Configure the Langfuse Basic Auth OTLP dispatch.

    Called at app startup via lifespan. If enabled is False or either
    key is empty, becomes a no-op.
    """
    global _public_key, _secret_key, _endpoint, _service_name
    global _send_prompt_content, _sample_rate, _enabled

    if not enabled or not public_key or not secret_key:
        logger.debug(
            "LANGFUSE_ENABLED=%s or keys unset - Langfuse disabled (no-op)",
            enabled,
        )
        _public_key = None
        _secret_key = None
        _endpoint = None
        _enabled = False
        return

    _public_key = public_key
    _secret_key = secret_key
    _endpoint = endpoint
    _service_name = service_name
    _send_prompt_content = send_prompt_content
    _sample_rate = sample_rate
    _enabled = True
    logger.info("Langfuse configured - service=%s endpoint=%s", service_name, endpoint)


def _build_basic_auth() -> str:
    """Return Basic auth header value from public/secret key pair."""
    credentials = f"{_public_key}:{_secret_key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _strip_pii_langfuse(attrs: dict[str, Any]) -> dict[str, Any]:
    """Strip prompt/completion content from Langfuse span attributes.

    When LANGFUSE_SEND_PROMPT_CONTENT is False (default), removes
    gen_ai.prompt, gen_ai.completion, langfuse.observation.input,
    langfuse.observation.output, and any key containing ".content".
    """
    if _send_prompt_content:
        return attrs

    stripped: dict[str, Any] = {}
    for key, value in attrs.items():
        lowered = key.lower()
        if lowered in _LANGFUSE_CONTENT_KEYS:
            continue
        if any(sub in lowered for sub in _CONTENT_KEY_SUBSTRINGS):
            continue
        stripped[key] = value
    return stripped


async def _send_to_langfuse(spans: list[dict[str, Any]]) -> None:
    """Ship spans to Langfuse via OTLP over HTTP JSON with Basic Auth.

    Single HTTP call site for Langfuse. fire_and_forget() ensures
    no blocking and no raising.
    """
    if not _enabled or not spans:
        return

    if _sample_rate < 1.0 and random.random() > _sample_rate:
        return

    try:
        payload = build_resource_spans(
            spans,
            service_name=_service_name,
            scope_name="evidence-eu.langfuse-forwarder",
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": _build_basic_auth(),
        }
        await fire_and_forget(_endpoint or "", headers, payload, timeout=5.0)
    except Exception:  # noqa: BLE001 - best effort, never raise
        logger.debug("Failed to build or ship Langfuse spans", exc_info=True)


def observe_generation(
    name: str | None = None,
    model: str | None = None,
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Decorator that wraps an LLM call in a Langfuse GENERATION span.

    Sets langfuse.observation.type=generation and gen_ai.request.model
    so Langfuse auto-classifies the span as an LLM generation and
    renders token counts/prompt/completion in its UI.

    No-op contract: checks _enabled at call time.
    """

    def decorator(func: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        span_name = name or func.__qualname__
        resolved_model = model or "unknown"

        @functools.wraps(func)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            if not _enabled:
                return await func(*args, **kwargs)

            trace_id = _current_trace_id.get() or _new_trace_id()
            parent_span_id = _current_span_id.get()
            span_id = _new_span_id()

            start_ns = time.time_ns()
            status_code = 1
            attributes: dict[str, Any] = {
                "langfuse.observation.type": "generation",
                "gen_ai.request.model": resolved_model,
            }
            try:
                result = await func(*args, **kwargs)
                extra = getattr(result, "_langfuse_attrs", None)
                if isinstance(extra, dict):
                    attributes.update(extra)
                return result
            except Exception:
                status_code = 2
                raise
            finally:
                end_ns = time.time_ns()
                span = build_span(
                    name=span_name,
                    kind=SPAN_KIND_INTERNAL,
                    start_ns=start_ns,
                    end_ns=end_ns,
                    attributes=_strip_pii_langfuse(attributes),
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    status_code=status_code,
                )
                await _send_to_langfuse([span])

        return wrapper

    return decorator


class trace:
    """Async context manager that creates a parent Langfuse trace span.

    Yields the trace_id so callers can pass it to log_generation() or
    log_score() for child events. Reads the shared _current_trace_id
    contextvar from otlp_builder if set by LaminarMiddleware, so both
    dashboards show the same trace ID.

    Usage:
        async with trace("translate.request") as trace_id:
            await log_generation(trace_id, model="m2m100-1.2b", ...)
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None) -> None:
        self._name = name
        self._metadata = metadata or {}
        self._trace_id: str | None = None
        self._span_id: str | None = None
        self._start_ns: int = 0
        self._trace_token: Any = None
        self._span_token: Any = None

    async def __aenter__(self) -> str:
        if not _enabled:
            return ""

        self._trace_id = _current_trace_id.get() or _new_trace_id()
        self._span_id = _new_span_id()
        self._trace_token = _current_trace_id.set(self._trace_id)
        self._span_token = _current_span_id.set(self._span_id)
        self._start_ns = time.time_ns()
        return self._trace_id

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not _enabled or not self._trace_id:
            return

        end_ns = time.time_ns()
        status_code = 2 if exc_type else 1
        attrs: dict[str, Any] = {
            "langfuse.observation.type": "span",
        }
        attrs.update(self._metadata)
        span = build_span(
            name=self._name,
            kind=SPAN_KIND_INTERNAL,
            start_ns=self._start_ns,
            end_ns=end_ns,
            attributes=_strip_pii_langfuse(attrs),
            trace_id=self._trace_id,
            span_id=self._span_id or _new_span_id(),
            status_code=status_code,
        )
        await _send_to_langfuse([span])
        if self._trace_token is not None:
            _current_trace_id.reset(self._trace_token)
        if self._span_token is not None:
            _current_span_id.reset(self._span_token)


async def log_generation(
    trace_id: str,
    model: str,
    input_meta: dict[str, Any] | None = None,
    output_meta: dict[str, Any] | None = None,
    latency_ms: float | None = None,
    usage: dict[str, int] | None = None,
) -> None:
    """Log a generation event under a parent trace.

    Creates a GENERATION-type span with gen_ai.usage attributes so
    Langfuse auto-classifies it as an LLM call with token tracking.

    Args:
        trace_id: Parent trace ID (from trace() context manager).
        model: Model name (e.g. "m2m100-1.2b").
        input_meta: Metadata about the input (language, char_count).
        output_meta: Metadata about the output (language, char_count).
        latency_ms: Call latency in milliseconds.
        usage: Token usage dict with input_tokens, output_tokens keys.
    """
    if not _enabled or not trace_id:
        return

    attrs: dict[str, Any] = {
        "langfuse.observation.type": "generation",
        "gen_ai.request.model": model,
    }
    if input_meta:
        attrs.update({f"gen_ai.input.{k}": v for k, v in input_meta.items()})
    if output_meta:
        attrs.update({f"gen_ai.output.{k}": v for k, v in output_meta.items()})
    if latency_ms is not None:
        attrs["latency_ms"] = latency_ms
    if usage:
        if "input_tokens" in usage:
            attrs["gen_ai.usage.input_tokens"] = usage["input_tokens"]
        if "output_tokens" in usage:
            attrs["gen_ai.usage.output_tokens"] = usage["output_tokens"]

    parent_span_id = _current_span_id.get()
    span = build_span(
        name=f"generation.{model}",
        kind=SPAN_KIND_INTERNAL,
        start_ns=time.time_ns(),
        end_ns=time.time_ns(),
        attributes=_strip_pii_langfuse(attrs),
        trace_id=trace_id,
        span_id=_new_span_id(),
        parent_span_id=parent_span_id,
    )
    await _send_to_langfuse([span])


async def log_score(
    trace_id: str,
    name: str,
    value: float,
    comment: str | None = None,
) -> None:
    """Attach a numeric score to a trace for evaluation pipelines.

    Creates a span with langfuse.score attributes so Langfuse renders
    it as a score in the evaluation UI.

    Args:
        trace_id: Trace ID to attach the score to.
        name: Score name (e.g. "translation_accuracy").
        value: Numeric score value.
        comment: Optional comment.
    """
    if not _enabled or not trace_id:
        return

    attrs: dict[str, Any] = {
        "langfuse.score.name": name,
        "langfuse.score.value": value,
        "langfuse.score.datatype": "numeric",
    }
    if comment:
        attrs["langfuse.score.comment"] = comment

    span = build_span(
        name=f"score.{name}",
        kind=SPAN_KIND_INTERNAL,
        start_ns=time.time_ns(),
        end_ns=time.time_ns(),
        attributes=_strip_pii_langfuse(attrs),
        trace_id=trace_id,
        span_id=_new_span_id(),
    )
    await _send_to_langfuse([span])
