# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for the Pyodide-safe Laminar OTLP/HTTP/json forwarder.

Coverage focus:
- @observe decorator captures span attributes and duration
- LaminarMiddleware creates a root span per request
- _strip_pii removes content when LMNR_SEND_PROMPT_CONTENT=False
- LMNR_ENABLED=False causes a complete no-op (no HTTP calls made)
- _send_spans() failure (httpx timeout) does not raise, request still 200

Note: this codebase does not use the respx library anywhere (verified via
grep across backend/tests). Following the same mocking style already
established in test_sentry_integration.py, we patch
app.integrations.laminar.fire_and_forget directly with AsyncMock — this
achieves the same isolation as respx without adding a new test dependency.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations import laminar


@pytest.fixture(autouse=True)
def _reset_laminar_state() -> None:
    """Reset module-level Laminar state before and after every test."""
    laminar.configure(None, enabled=False)
    yield
    laminar.configure(None, enabled=False)


class TestConfigure:
    def test_configure_disabled_by_default(self) -> None:
        laminar.configure("some-key", enabled=False)
        assert laminar._enabled is False

    def test_configure_noop_when_api_key_empty(self) -> None:
        laminar.configure("", enabled=True)
        assert laminar._enabled is False

    def test_configure_enables_when_key_and_flag_set(self) -> None:
        laminar.configure("test-key", "https://api.lmnr.ai:443/v1/traces", enabled=True)
        assert laminar._enabled is True
        assert laminar._api_key == "test-key"
        assert laminar._endpoint == "https://api.lmnr.ai:443/v1/traces"


class TestStripPii:
    def test_strip_pii_removes_content_keys_by_default(self) -> None:
        laminar.configure("test-key", enabled=True, send_prompt_content=False)
        attrs = {
            "text": "this is document content",
            "query": "sensitive search query",
            "model": "m2m100-1.2b",
            "latency_ms": 120,
        }
        result = laminar._strip_pii(attrs)
        assert "text" not in result
        assert "query" not in result
        assert result["model"] == "m2m100-1.2b"
        assert result["latency_ms"] == 120

    def test_strip_pii_removes_gen_ai_prompt_content_substring(self) -> None:
        laminar.configure("test-key", enabled=True, send_prompt_content=False)
        attrs = {
            "gen_ai.prompt.0.content": "leaked document text",
            "gen_ai.prompt.0.role": "user",
        }
        result = laminar._strip_pii(attrs)
        assert "gen_ai.prompt.0.content" not in result
        assert result["gen_ai.prompt.0.role"] == "user"

    def test_strip_pii_passes_through_when_send_prompt_content_true(self) -> None:
        laminar.configure("test-key", enabled=True, send_prompt_content=True)
        attrs = {"text": "this is document content"}
        result = laminar._strip_pii(attrs)
        assert result["text"] == "this is document content"


class TestObserveDecorator:
    @pytest.mark.asyncio
    async def test_observe_is_noop_when_disabled(self) -> None:
        laminar.configure(None, enabled=False)

        @laminar.observe(name="test.span")
        async def sample_fn(x: int) -> int:
            return x * 2

        with patch("app.integrations.laminar.fire_and_forget", new=AsyncMock()) as post:
            result = await sample_fn(21)

        assert result == 42
        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_observe_captures_span_with_correct_attributes(self) -> None:
        laminar.configure("test-key", enabled=True, send_prompt_content=False)

        @laminar.observe(name="translate.llm", span_type="LLM")
        async def sample_translate() -> str:
            return "translated"

        with patch("app.integrations.laminar.fire_and_forget", new=AsyncMock()) as post:
            result = await sample_translate()

        assert result == "translated"
        post.assert_awaited_once()
        call_args = post.await_args
        url, headers, payload = call_args.args[0], call_args.args[1], call_args.args[2]
        assert url == laminar._endpoint
        assert headers["Authorization"] == "Bearer test-key"
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "translate.llm"
        assert span["kind"] == laminar.SPAN_KIND_INTERNAL
        assert len(span["traceId"]) == 32
        assert len(span["spanId"]) == 16
        attr_keys = {a["key"] for a in span["attributes"]}
        assert "lmnr.span.type" in attr_keys

    @pytest.mark.asyncio
    async def test_observe_marks_error_status_on_exception(self) -> None:
        laminar.configure("test-key", enabled=True)

        @laminar.observe(name="failing.span")
        async def sample_fail() -> None:
            raise ValueError("boom")

        with (
            patch("app.integrations.laminar.fire_and_forget", new=AsyncMock()) as post,
            pytest.raises(ValueError, match="boom"),
        ):
            await sample_fail()

        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["status"]["code"] == 2


class TestLaminarMiddleware:
    @pytest.mark.asyncio
    async def test_middleware_noop_when_disabled(self) -> None:
        laminar.configure(None, enabled=False)

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = laminar.LaminarMiddleware(inner_app)
        scope = {"type": "http", "method": "GET", "path": "/health"}
        sent_messages = []

        async def receive():
            return {"type": "http.request"}

        async def send(message):
            sent_messages.append(message)

        with patch("app.integrations.laminar.fire_and_forget", new=AsyncMock()) as post:
            await middleware(scope, receive, send)

        post.assert_not_awaited()
        assert sent_messages[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_middleware_creates_root_span_per_request(self) -> None:
        laminar.configure("test-key", enabled=True)

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = laminar.LaminarMiddleware(inner_app)
        scope = {"type": "http", "method": "POST", "path": "/api/v1/translate"}

        async def receive():
            return {"type": "http.request"}

        async def send(message):
            pass

        with patch("app.integrations.laminar.fire_and_forget", new=AsyncMock()) as post:
            await middleware(scope, receive, send)

        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "POST /api/v1/translate"
        assert span["kind"] == laminar.SPAN_KIND_SERVER
        attrs = {a["key"]: a["value"] for a in span["attributes"]}
        assert attrs["http.method"]["stringValue"] == "POST"
        assert attrs["http.status_code"]["intValue"] == "200"


class TestSendSpansFailureIsolation:
    @pytest.mark.asyncio
    async def test_send_spans_failure_does_not_raise(self) -> None:
        """A transport-level failure (e.g. httpx timeout) inside fire_and_forget
        must never propagate — the request path must remain unaffected.
        fire_and_forget() already guarantees this contract; here we verify
        _send_spans() does not re-raise even if fire_and_forget itself raises
        unexpectedly (defense in depth via the outer try/except)."""
        laminar.configure("test-key", enabled=True)

        with patch(
            "app.integrations.laminar.fire_and_forget",
            new=AsyncMock(side_effect=RuntimeError("network unreachable")),
        ):
            span = laminar._build_span(
                name="test.span",
                kind=laminar.SPAN_KIND_INTERNAL,
                start_ns=1,
                end_ns=2,
                attributes={},
                trace_id=laminar._new_trace_id(),
                span_id=laminar._new_span_id(),
            )
            # Must not raise despite the underlying transport failing.
            await laminar._send_spans([span])

    @pytest.mark.asyncio
    async def test_middleware_request_still_returns_200_when_shipping_fails(self) -> None:
        laminar.configure("test-key", enabled=True)

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = laminar.LaminarMiddleware(inner_app)
        scope = {"type": "http", "method": "GET", "path": "/api/v1/search"}
        sent_messages = []

        async def receive():
            return {"type": "http.request"}

        async def send(message):
            sent_messages.append(message)

        with patch(
            "app.integrations.laminar.fire_and_forget",
            new=AsyncMock(side_effect=RuntimeError("timeout")),
        ):
            await middleware(scope, receive, send)

        assert sent_messages[0]["type"] == "http.response.start"
        assert sent_messages[0]["status"] == 200
