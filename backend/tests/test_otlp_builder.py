# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for the shared OTLP/HTTP/json span builder (otlp_builder.py).

Verifies that the builder produces valid OTLP JSON payloads — backend-
agnostic, no auth, no HTTP. Both laminar.py and langfuse.py delegate
payload construction to this module.
"""

from app.integrations.otlp_builder import (
    SPAN_KIND_INTERNAL,
    SPAN_KIND_SERVER,
    _new_span_id,
    _new_trace_id,
    build_resource_spans,
    build_span,
)


class TestBuildSpan:
    def test_build_span_produces_valid_otlp_shape(self) -> None:
        trace_id = _new_trace_id()
        span_id = _new_span_id()
        span = build_span(
            name="test.span",
            kind=SPAN_KIND_INTERNAL,
            start_ns=1000000000,
            end_ns=2000000000,
            attributes={"key": "value"},
            trace_id=trace_id,
            span_id=span_id,
        )
        assert span["traceId"] == trace_id
        assert span["spanId"] == span_id
        assert span["name"] == "test.span"
        assert span["kind"] == SPAN_KIND_INTERNAL
        assert span["startTimeUnixNano"] == "1000000000"
        assert span["endTimeUnixNano"] == "2000000000"
        assert span["status"] == {"code": 1}
        assert len(span["attributes"]) == 1
        assert "parentSpanId" not in span

    def test_build_span_includes_parent_span_id_when_provided(self) -> None:
        span = build_span(
            name="child",
            kind=SPAN_KIND_INTERNAL,
            start_ns=1,
            end_ns=2,
            attributes={},
            trace_id=_new_trace_id(),
            span_id=_new_span_id(),
            parent_span_id="deadbeefdeadbeef",
        )
        assert span["parentSpanId"] == "deadbeefdeadbeef"

    def test_build_span_encodes_bool_int_float_string(self) -> None:
        span = build_span(
            name="types",
            kind=SPAN_KIND_SERVER,
            start_ns=1,
            end_ns=2,
            attributes={
                "bool_attr": True,
                "int_attr": 42,
                "float_attr": 3.14,
                "str_attr": "hello",
            },
            trace_id=_new_trace_id(),
            span_id=_new_span_id(),
        )
        attrs = {a["key"]: a["value"] for a in span["attributes"]}
        assert attrs["bool_attr"] == {"boolValue": True}
        assert attrs["int_attr"] == {"intValue": "42"}
        assert attrs["float_attr"] == {"doubleValue": 3.14}
        assert attrs["str_attr"] == {"stringValue": "hello"}


class TestBuildResourceSpans:
    def test_build_resource_spans_wraps_spans_correctly(self) -> None:
        span = build_span(
            name="s",
            kind=SPAN_KIND_INTERNAL,
            start_ns=1,
            end_ns=2,
            attributes={},
            trace_id=_new_trace_id(),
            span_id=_new_span_id(),
        )
        payload = build_resource_spans(
            [span],
            service_name="test-svc",
            scope_name="test-scope",
        )
        rs = payload["resourceSpans"][0]
        assert rs["resource"]["attributes"][0]["key"] == "service.name"
        assert rs["resource"]["attributes"][0]["value"]["stringValue"] == "test-svc"
        assert rs["scopeSpans"][0]["scope"]["name"] == "test-scope"
        assert rs["scopeSpans"][0]["spans"][0]["name"] == "s"


class TestIdGeneration:
    def test_new_trace_id_is_32_hex_chars(self) -> None:
        assert len(_new_trace_id()) == 32

    def test_new_span_id_is_16_hex_chars(self) -> None:
        assert len(_new_span_id()) == 16

    def test_ids_are_unique(self) -> None:
        t1 = _new_trace_id()
        t2 = _new_trace_id()
        assert t1 != t2
