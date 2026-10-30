# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for the Langfuse Basic Auth OTLP dispatch (langfuse.py).

Verifies the no-op contract, PII stripping, Basic Auth header, and the
observe_generation decorator following the same pattern as test_laminar.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations import langfuse


@pytest.fixture(autouse=True)
def _reset_langfuse_state() -> None:
    langfuse.configure(None, None, enabled=False)
    yield
    langfuse.configure(None, None, enabled=False)


class TestConfigure:
    def test_configure_noop_when_disabled(self) -> None:
        langfuse.configure("pk", "sk", enabled=False)
        assert langfuse._enabled is False

    def test_configure_noop_when_keys_empty(self) -> None:
        langfuse.configure("", "", enabled=True)
        assert langfuse._enabled is False

    def test_configure_noop_when_public_key_missing(self) -> None:
        langfuse.configure(None, "sk", enabled=True)
        assert langfuse._enabled is False

    def test_configure_enables_when_keys_and_flag_set(self) -> None:
        langfuse.configure("pk-test", "sk-test", enabled=True)
        assert langfuse._enabled is True
        assert langfuse._public_key == "pk-test"
        assert langfuse._secret_key == "sk-test"


class TestBasicAuth:
    def test_build_basic_auth_produces_correct_header(self) -> None:
        langfuse.configure("pk-test", "sk-test", enabled=True)
        header = langfuse._build_basic_auth()
        assert header.startswith("Basic ")


class TestStripPiiLangfuse:
    def test_strip_pii_removes_gen_ai_prompt_and_completion(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=False)
        attrs = {
            "gen_ai.prompt": "leaked prompt",
            "gen_ai.completion": "leaked completion",
            "gen_ai.request.model": "m2m100-1.2b",
            "gen_ai.usage.input_tokens": 50,
        }
        result = langfuse._strip_pii_langfuse(attrs)
        assert "gen_ai.prompt" not in result
        assert "gen_ai.completion" not in result
        assert result["gen_ai.request.model"] == "m2m100-1.2b"
        assert result["gen_ai.usage.input_tokens"] == 50

    def test_strip_pii_removes_dot_content_substring(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=False)
        attrs = {"gen_ai.prompt.0.content": "leaked"}
        result = langfuse._strip_pii_langfuse(attrs)
        assert "gen_ai.prompt.0.content" not in result

    def test_strip_pii_passes_through_when_send_prompt_content_true(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=True)
        attrs = {"gen_ai.prompt": "visible", "gen_ai.completion": "also visible"}
        result = langfuse._strip_pii_langfuse(attrs)
        assert result["gen_ai.prompt"] == "visible"
        assert result["gen_ai.completion"] == "also visible"


class TestObserveGeneration:
    @pytest.mark.asyncio
    async def test_noop_when_disabled(self) -> None:
        langfuse.configure(None, None, enabled=False)

        @langfuse.observe_generation(name="test.gen", model="test-model")
        async def sample_fn(x: int) -> int:
            return x * 2

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            result = await sample_fn(21)

        assert result == 42
        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sends_generation_span_with_correct_attributes(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=False)

        @langfuse.observe_generation(name="translate.llm", model="m2m100-1.2b")
        async def sample_translate() -> str:
            return "translated"

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            result = await sample_translate()

        assert result == "translated"
        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "translate.llm"
        assert span["kind"] == 1  # INTERNAL
        attrs = {a["key"]: a["value"] for a in span["attributes"]}
        assert attrs["langfuse.observation.type"]["stringValue"] == "generation"
        assert attrs["gen_ai.request.model"]["stringValue"] == "m2m100-1.2b"

    @pytest.mark.asyncio
    async def test_send_to_langfuse_failure_does_not_raise(self) -> None:
        """Transport failure must never propagate — fire_and_forget + try/except."""
        langfuse.configure("pk", "sk", enabled=True, sample_rate=1.0)

        # Build a real span so _send_to_langfuse doesn't short-circuit on empty list
        test_span = langfuse.build_span(
            name="test.span",
            kind=1,
            start_ns=1,
            end_ns=2,
            attributes={},
            trace_id=langfuse._new_trace_id(),
            span_id=langfuse._new_span_id(),
        )

        with patch(
            "app.integrations.langfuse.fire_and_forget",
            new=AsyncMock(side_effect=RuntimeError("network down")),
        ):
            # Must not raise despite transport failure
            await langfuse._send_to_langfuse([test_span])


class TestTraceContextManager:
    @pytest.mark.asyncio
    async def test_trace_noop_when_disabled(self) -> None:
        langfuse.configure(None, None, enabled=False)

        async with langfuse.trace("test.trace") as trace_id:
            assert trace_id == ""

    @pytest.mark.asyncio
    async def test_trace_creates_span_and_yields_trace_id(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=False)

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            async with langfuse.trace("test.trace") as trace_id:
                assert len(trace_id) == 32

        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "test.trace"
        attrs = {a["key"]: a["value"] for a in span["attributes"]}
        assert attrs["langfuse.observation.type"]["stringValue"] == "span"

    @pytest.mark.asyncio
    async def test_trace_marks_error_on_exception(self) -> None:
        langfuse.configure("pk", "sk", enabled=True)

        with (
            patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post,
            pytest.raises(ValueError, match="boom"),
        ):
            async with langfuse.trace("failing.trace"):
                raise ValueError("boom")

        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["status"]["code"] == 2  # ERROR


class TestLogGeneration:
    @pytest.mark.asyncio
    async def test_log_generation_noop_when_disabled(self) -> None:
        langfuse.configure(None, None, enabled=False)

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            await langfuse.log_generation("trace-id", model="m2m100")

        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_generation_sends_generation_span(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=False)

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            await langfuse.log_generation(
                "a" * 32,
                model="m2m100-1.2b",
                input_meta={"source_lang": "en", "char_count": 11},
                output_meta={"target_lang": "de"},
                latency_ms=150.0,
                usage={"input_tokens": 5, "output_tokens": 3},
            )

        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "generation.m2m100-1.2b"
        attrs = {a["key"]: a["value"] for a in span["attributes"]}
        assert attrs["langfuse.observation.type"]["stringValue"] == "generation"
        assert attrs["gen_ai.request.model"]["stringValue"] == "m2m100-1.2b"
        assert attrs["gen_ai.usage.input_tokens"]["intValue"] == "5"
        assert attrs["gen_ai.usage.output_tokens"]["intValue"] == "3"
        assert attrs["latency_ms"]["doubleValue"] == 150.0

    @pytest.mark.asyncio
    async def test_log_generation_strips_prompt_content_when_disabled(self) -> None:
        langfuse.configure("pk", "sk", enabled=True, send_prompt_content=False)

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            await langfuse.log_generation(
                "a" * 32,
                model="m2m100",
                input_meta={"prompt": "sensitive text"},
            )

        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        attrs = {a["key"] for a in span["attributes"]}
        # "gen_ai.input.prompt" should be stripped (contains "prompt" key)
        assert "gen_ai.input.prompt" not in attrs


class TestLogScore:
    @pytest.mark.asyncio
    async def test_log_score_noop_when_disabled(self) -> None:
        langfuse.configure(None, None, enabled=False)

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            await langfuse.log_score("trace-id", "accuracy", 0.95)

        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_score_sends_score_span(self) -> None:
        langfuse.configure("pk", "sk", enabled=True)

        with patch("app.integrations.langfuse.fire_and_forget", new=AsyncMock()) as post:
            await langfuse.log_score("a" * 32, "translation_accuracy", 0.92, comment="good")

        post.assert_awaited_once()
        payload = post.await_args.args[2]
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "score.translation_accuracy"
        attrs = {a["key"]: a["value"] for a in span["attributes"]}
        assert attrs["langfuse.score.name"]["stringValue"] == "translation_accuracy"
        assert attrs["langfuse.score.value"]["doubleValue"] == 0.92
        assert attrs["langfuse.score.comment"]["stringValue"] == "good"
