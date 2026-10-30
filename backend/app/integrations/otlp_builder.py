# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Shared OTLP/HTTP/json Span Builder (No opentelemetry-sdk)

Pure OTLP payload construction — no backend-specific logic, no HTTP calls,
no gRPC, no threading, no C extensions. Both laminar.py and langfuse.py
import from this module so the OTLP JSON shape is defined in exactly one
place (DRY). Adding a third OTLP backend requires only a thin dispatch
module, not a 300-line rewrite.

Confirmed protocol details (see docs/adal/laminar-instrumentation-research.md
section 3):
    - traceId is 32 hex chars, spanId is 16 hex chars (secrets.token_hex)
    - Keys are lowerCamelCase; enum values are integers; timestamps are
      decimal-string nanoseconds (time.time_ns())
    - kind: 1=INTERNAL, 2=SERVER, 3=CLIENT
"""

from __future__ import annotations

import secrets
from contextvars import ContextVar
from typing import Any

# OTLP span kind constants
SPAN_KIND_INTERNAL = 1
SPAN_KIND_SERVER = 2
SPAN_KIND_CLIENT = 3

# Shared trace context — written by LaminarMiddleware, read by both
# laminar.py and langfuse.py so both dashboards show the same trace ID.
# Uses contextvars (NOT threading.local) because Pyodide has no threading
# module. contextvars propagate correctly across asyncio tasks.
_current_trace_id: ContextVar[str | None] = ContextVar("_current_trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("_current_span_id", default=None)


def _encode_attribute_value(value: Any) -> dict[str, Any]:
    """Encode one Python value as an OTLP AnyValue JSON object."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _encode_attributes(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """Encode a flat attrs dict as an OTLP attributes array."""
    encoded: list[dict[str, Any]] = []
    for key, value in attrs.items():
        encoded.append({"key": key, "value": _encode_attribute_value(value)})
    return encoded


def _new_trace_id() -> str:
    """Generate a 32 hex char OTLP traceId (16 random bytes)."""
    return secrets.token_hex(16)


def _new_span_id() -> str:
    """Generate a 16 hex char OTLP spanId (8 random bytes)."""
    return secrets.token_hex(8)


def build_span(
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
    """Build a single OTLP span dict, JSON Protobuf encoding.

    Attributes MUST already be PII-stripped by the caller before
    reaching this function — the caller (laminar.py or langfuse.py)
    applies its own content-key filter, then passes clean metadata here.
    This keeps the builder backend-agnostic (no module-level flags).

    status_code follows OTLP Status.code: 1 is OK, 2 is ERROR.
    """
    span: dict[str, Any] = {}
    span["traceId"] = trace_id
    span["spanId"] = span_id
    span["name"] = name
    span["kind"] = kind
    span["startTimeUnixNano"] = str(start_ns)
    span["endTimeUnixNano"] = str(end_ns)
    span["attributes"] = _encode_attributes(attributes)
    span["status"] = {"code": status_code}
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return span


def build_resource_spans(
    spans: list[dict[str, Any]],
    *,
    service_name: str,
    scope_name: str = "evidence-eu.otlp-forwarder",
) -> dict[str, Any]:
    """Wrap built spans in the OTLP resourceSpans/scopeSpans/spans shape."""
    resource_attrs = [{"key": "service.name", "value": {"stringValue": service_name}}]
    resource = {"attributes": resource_attrs}
    scope = {"name": scope_name}
    scope_spans_entry = {"scope": scope, "spans": spans}
    resource_spans_entry = {"resource": resource, "scopeSpans": [scope_spans_entry]}
    return {"resourceSpans": [resource_spans_entry]}
