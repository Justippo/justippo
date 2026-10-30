"""
Unit tests for GET /api/v1/search SSE streaming endpoint (Sprint 2)

Coverage:
- _sse_frame() produces valid W3C SSE format for all three event types
- _sse_generator() yields result → done on happy path
- _sse_generator() yields error → done on upstream RAG exception
- _sse_generator() stops cleanly on client disconnect (no exception raised)
- search_stream() returns all required SSE headers
- search_stream() propagates ImportError as HTTP 500
- Backpressure delay is skipped when SSE_CHUNK_DELAY_MS == 0
- Backpressure delay is applied when SSE_CHUNK_DELAY_MS > 0

All external calls (RAG, asyncio.sleep, request.is_disconnected) are mocked.
No real network calls are made.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.search import _sse_generator, router
from app.core.sse import sse_frame as _sse_frame

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_apertus():
    """Disable Apertus answer generation for all tests in this module.

    The search endpoint's answer-generation step calls the real HuggingFace
    API when HF_API_TOKEN is set in .env. Existing tests assert exact frame
    counts (e.g. 2 results + 1 done = 3 frames) and must not be affected
    by the answer feature. Tests that exercise the answer path explicitly
    re-patch ``apertus_enabled`` / ``apertus_generate`` themselves.
    """
    with (
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=False),
        patch("app.api.v1.endpoints.search.generate_answer_stream", new_callable=AsyncMock),
    ):
        yield


def _fake_request(*, disconnected_after: int = 999) -> MagicMock:
    """
    Build a mock fastapi.Request whose is_disconnected() returns True
    after *disconnected_after* calls, allowing us to simulate a mid-stream
    client disconnect.
    """
    call_count: list[int] = [0]

    async def _is_disconnected() -> bool:
        call_count[0] += 1
        return call_count[0] > disconnected_after

    req = MagicMock()
    req.is_disconnected = _is_disconnected
    return req


def _fake_rag(results: list[dict[str, Any]]) -> MagicMock:
    """Return a mock HindsightRAGService whose query() resolves to *results*."""
    rag = MagicMock()
    rag.query = AsyncMock(return_value=results)
    return rag


async def _collect(gen: AsyncGenerator[str, None]) -> list[str]:
    """Drain an async generator into a list of strings."""
    return [frame async for frame in gen]


# ---------------------------------------------------------------------------
# _sse_frame unit tests
# ---------------------------------------------------------------------------


class TestSseFrame:
    def test_result_event_format(self) -> None:
        frame = _sse_frame("result", {"id": "1", "text": "hello"})
        lines = frame.split("\n")
        assert lines[0] == "event: result"
        assert lines[1].startswith("data: ")
        payload = json.loads(lines[1][len("data: ") :])
        assert payload == {"id": "1", "text": "hello"}
        # Must end with blank line (double newline → last element empty)
        assert frame.endswith("\n\n")

    def test_error_event_format(self) -> None:
        frame = _sse_frame("error", {"message": "boom"})
        assert frame.startswith("event: error\n")
        assert '"message": "boom"' in frame
        assert frame.endswith("\n\n")

    def test_done_event_with_string_data(self) -> None:
        frame = _sse_frame("done", "[DONE]")
        assert frame == "event: done\ndata: [DONE]\n\n"

    def test_non_ascii_characters_preserved(self) -> None:
        frame = _sse_frame("result", {"text": "über Straße"})
        assert "über Straße" in frame


# ---------------------------------------------------------------------------
# _sse_generator — happy path
# ---------------------------------------------------------------------------


class TestSseGeneratorHappyPath:
    @pytest.mark.asyncio
    async def test_yields_result_then_done(self) -> None:
        results = [
            {"id": "1", "text": "First result", "rank": 1},
            {"id": "2", "text": "Second result", "rank": 2},
        ]
        rag = _fake_rag(results)
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="test", top_k=5, rag=rag, request=request))

        assert len(frames) == 4  # 2 results + results_complete + done
        assert frames[0].startswith("event: result\n")
        assert frames[1].startswith("event: result\n")
        assert frames[2].startswith("event: results_complete\n")
        assert frames[3] == "event: done\ndata: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_result_payload_matches_rag_output(self) -> None:
        results = [{"id": "42", "text": "Answer", "rank": 1}]
        rag = _fake_rag(results)
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        data_line = frames[0].split("\n")[1]
        payload = json.loads(data_line[len("data: ") :])
        assert payload["id"] == "42"
        assert payload["text"] == "Answer"

    @pytest.mark.asyncio
    async def test_empty_results_yields_only_done(self) -> None:
        rag = _fake_rag([])
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        assert frames == [
            "event: results_complete\ndata: [RESULTS_READY]\n\n",
            "event: done\ndata: [DONE]\n\n",
        ]

    @pytest.mark.asyncio
    async def test_flushes_stage_metrics_before_done(self) -> None:
        rag = _fake_rag([])
        request = _fake_request()
        order: list[str] = []

        async def flush() -> None:
            order.append("flush")

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch(
                "app.api.v1.endpoints.search.flush_search_stage_batch",
                new=AsyncMock(side_effect=flush),
            ) as flush_metric,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            async for frame in _sse_generator(q="q", top_k=5, rag=rag, request=request):
                order.append(frame.splitlines()[0])

        flush_metric.assert_awaited_once()
        # results_complete is emitted by the inner generator; stage metrics are
        # flushed by the wrapping generator just before the terminal done.
        assert order == ["event: results_complete", "flush", "event: done"]

    @pytest.mark.asyncio
    async def test_logs_correlated_done_outcome(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        rag = _fake_rag([])
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            await _collect(
                _sse_generator(
                    q="q",
                    top_k=5,
                    rag=rag,
                    request=request,
                    request_id="request-123",
                    emit_model=True,
                )
            )

        record = next(record for record in caplog.records if "sse_stream_outcome" in record.message)
        assert json.loads(record.message) == {
            "event": "sse_stream_outcome",
            "request_id": "request-123",
            "outcome": "done",
            "endpoint": "chat",
        }


# ---------------------------------------------------------------------------
# _sse_generator — upstream error propagation
# ---------------------------------------------------------------------------


class TestSseGeneratorUpstreamError:
    @pytest.mark.asyncio
    async def test_rag_exception_yields_results_complete_then_done(self) -> None:
        rag = MagicMock()
        rag.query = AsyncMock(side_effect=RuntimeError("Hindsight unreachable"))
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        assert len(frames) == 2
        assert frames[0].startswith("event: results_complete\n")
        assert frames[1] == "event: done\ndata: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_rag_exception_does_not_raise(self) -> None:
        """Generator must not propagate any exception to the caller."""
        rag = MagicMock()
        rag.query = AsyncMock(side_effect=Exception("unexpected"))
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            # Should complete without raising
            frames = await _collect(_sse_generator(q="q", top_k=3, rag=rag, request=request))

        # Confirm we got results_complete and not an exception
        assert any("event: results_complete" in f for f in frames)

    @pytest.mark.asyncio
    async def test_no_result_frames_emitted_on_rag_error(self) -> None:
        rag = MagicMock()
        rag.query = AsyncMock(side_effect=ValueError("bad query"))
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        result_frames = [f for f in frames if f.startswith("event: result\n")]
        assert result_frames == []

    @pytest.mark.asyncio
    async def test_logs_done_outcome_on_rag_error(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        rag = MagicMock()
        rag.query = AsyncMock(side_effect=RuntimeError("unavailable"))
        request = _fake_request()

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            await _collect(
                _sse_generator(q="q", top_k=5, rag=rag, request=request, request_id="request-error")
            )

        record = next(record for record in caplog.records if "sse_stream_outcome" in record.message)
        assert json.loads(record.message)["outcome"] == "done"


# ---------------------------------------------------------------------------
# _sse_generator — client disconnect
# ---------------------------------------------------------------------------


class TestSseGeneratorClientDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_stops_generator_without_raising(self) -> None:
        """
        Simulate a client that disconnects after the first result.
        Generator must stop cleanly — no exception, no done sentinel.
        """
        results = [{"id": str(i), "rank": i} for i in range(5)]
        rag = _fake_rag(results)
        # is_disconnected returns True starting from call 2 (after 1st result checked)
        request = _fake_request(disconnected_after=1)

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        # No exception raised — test passes if we get here
        # done sentinel should NOT be emitted after disconnect
        assert all("event: done" not in f for f in frames)

    @pytest.mark.asyncio
    async def test_disconnect_at_start_yields_nothing(self) -> None:
        """Client disconnects before any result is checked."""
        results = [{"id": "1"}]
        rag = _fake_rag(results)
        # Disconnected from the very first check
        request = _fake_request(disconnected_after=0)

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        assert frames == []

    @pytest.mark.asyncio
    async def test_logs_client_disconnect_outcome(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        rag = _fake_rag([{"id": "1"}])
        request = _fake_request(disconnected_after=0)

        with patch("app.api.v1.endpoints.search.settings") as mock_settings:
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            await _collect(
                _sse_generator(
                    q="q", top_k=5, rag=rag, request=request, request_id="request-disconnect"
                )
            )

        record = next(record for record in caplog.records if "sse_stream_outcome" in record.message)
        assert json.loads(record.message)["outcome"] == "client_disconnect"


class TestSseGeneratorPrematureTermination:
    @pytest.mark.asyncio
    async def test_logs_missing_done_as_premature_termination(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        request = _fake_request()

        async def incomplete_events(**_kwargs: Any) -> AsyncGenerator[str, None]:
            yield _sse_frame("result", {"id": "1"})

        with patch("app.api.v1.endpoints.search._sse_events", side_effect=incomplete_events):
            frames = await _collect(
                _sse_generator(
                    q="q",
                    top_k=5,
                    rag=_fake_rag([]),
                    request=request,
                    request_id="request-incomplete",
                )
            )

        assert len(frames) == 1
        record = next(record for record in caplog.records if "sse_stream_outcome" in record.message)
        assert json.loads(record.message)["outcome"] == "premature_termination"


# ---------------------------------------------------------------------------
# _sse_generator — backpressure delay
# ---------------------------------------------------------------------------


class TestSseGeneratorBackpressure:
    @pytest.mark.asyncio
    async def test_no_sleep_when_delay_is_zero(self) -> None:
        rag = _fake_rag([{"id": "1"}])
        request = _fake_request()

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch(
                "app.api.v1.endpoints.search.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_sleep_called_when_delay_set(self) -> None:
        rag = _fake_rag([{"id": "1"}, {"id": "2"}])
        request = _fake_request()

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch(
                "app.api.v1.endpoints.search.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 50
            await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        # Called once per yielded result (2 results → 2 sleeps)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.05)


# ---------------------------------------------------------------------------
# search_stream endpoint — headers and integration
# ---------------------------------------------------------------------------


class TestSearchStreamEndpoint:
    """
    Integration-level tests using FastAPI TestClient.
    HindsightRAGService is always mocked so no real network calls occur.
    """

    def _make_app(self) -> Any:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/search")
        return app

    def test_response_has_required_sse_headers(self) -> None:
        app = self._make_app()

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(return_value=[])
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app, raise_server_exceptions=True) as client:
                resp = client.get("/api/v1/search/?q=test")

        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"
        assert "text/event-stream" in resp.headers["content-type"]
        assert "charset=utf-8" in resp.headers["content-type"]
        # Connection: keep-alive is intentionally NOT set — it is prohibited
        # in HTTP/2 (Cloudflare Workers default, Safari refuses responses).
        # The SSE stream is kept alive by periodic :ping comment frames
        # emitted by the generator, not the HTTP header.
        assert "connection" not in resp.headers

    def test_import_error_propagates_as_500(self) -> None:
        """When HindsightRAGService raises ImportError, it propagates as HTTP 500."""
        app = self._make_app()

        with (
            patch(
                "app.api.v1.endpoints.search.HindsightRAGService",
                side_effect=ImportError("no hindsight"),
            ),
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/search/?q=test")

        assert resp.status_code == 500

    def test_rag_exception_does_not_return_500(self) -> None:
        """Upstream RAG exceptions must be absorbed as SSE error events, not HTTP 500."""
        app = self._make_app()

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(side_effect=RuntimeError("db gone"))
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/search/?q=test")

        # Must be 200 (SSE stream opened) — error carried in body, not status code
        assert resp.status_code == 200
        assert "event: results_complete" in resp.text
        assert "event: done" in resp.text

    def test_all_three_event_types_in_correct_order(self) -> None:
        """Verify result → (optional more results) → done ordering on happy path."""
        app = self._make_app()
        fake_results = [
            {"id": "a", "text": "first", "rank": 1},
            {"id": "b", "text": "second", "rank": 2},
        ]

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(return_value=fake_results)
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app) as client:
                resp = client.get("/api/v1/search/?q=docs&top_k=2")

        body = resp.text
        # Collect event types in order
        event_types = [
            line[len("event: ") :].strip()
            for line in body.splitlines()
            if line.startswith("event: ")
        ]
        assert event_types == ["result", "result", "results_complete", "done"]

    def test_search_stream_wires_glossary_repo_and_language(self) -> None:
        app = self._make_app()

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(return_value=[])
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app) as client:
                resp = client.get("/api/v1/search/?q=Aufenthaltstitel&language=de")

        assert resp.status_code == 200
        _, constructor_kwargs = mock_rag_cls.call_args
        assert constructor_kwargs["glossary_repo"] is not None
        mock_rag_instance.query.assert_awaited_once_with(
            q="Aufenthaltstitel",
            top_k=5,
            lang="de",
        )


# ---------------------------------------------------------------------------
# Apertus answer generation (Sprint 3 — ADR-014 candidate)
# ---------------------------------------------------------------------------


class TestApertusAnswerGeneration:
    """Tests for the grounded-answer SSE event from Apertus 8B."""

    @pytest.mark.asyncio
    async def test_records_answer_generation_stage_metric(self) -> None:
        results = [{"id": "1", "text": "Residence permit info", "rank": 1}]
        rag = _fake_rag(results)
        request = _fake_request()

        async def mock_stream(*args, **kwargs):
            yield "answer"

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
            patch(
                "app.api.v1.endpoints.search.generate_answer_stream",
                new_callable=MagicMock,
            ) as mock_gen,
            patch("app.api.v1.endpoints.search.build_search_stage_series") as build_metric,
            patch(
                "app.api.v1.endpoints.search.record_search_stage", new_callable=AsyncMock
            ) as record_metric,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            mock_settings.APP_ENV = "test"
            mock_gen.return_value = mock_stream()
            build_metric.return_value = {"series": []}
            await _collect(_sse_generator(q="private query", top_k=5, rag=rag, request=request))

        metric_kwargs = build_metric.call_args.kwargs
        assert metric_kwargs["stage"] == "answer_generation"
        assert metric_kwargs["outcome"] == "success"
        assert metric_kwargs["env"] == "test"
        assert "private query" not in repr(metric_kwargs)
        record_metric.assert_awaited_once_with({"series": []})

    @pytest.mark.asyncio
    async def test_answer_event_emitted_when_enabled(self) -> None:
        """When Apertus is enabled, an 'answer_chunk' event follows result events."""
        from unittest.mock import MagicMock

        results = [{"id": "1", "text": "Residence permit info", "rank": 1}]
        rag = _fake_rag(results)
        request = _fake_request()

        async def mock_stream(*args, **kwargs):
            yield "token1"
            yield "token2"

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
            patch(
                "app.api.v1.endpoints.search.generate_answer_stream",
                new_callable=MagicMock,
            ) as mock_gen,
        ):
            mock_gen.return_value = mock_stream()
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="permit", top_k=5, rag=rag, request=request))

        # 1 result + results_complete + 2 chunks + 1 grounding_verdict + 1 done = 6 frames
        assert len(frames) == 6
        assert frames[0].startswith("event: result\n")
        assert frames[1].startswith("event: results_complete\n")
        assert frames[2].startswith("event: answer_chunk\n")
        assert frames[3].startswith("event: answer_chunk\n")
        assert frames[4].startswith("event: grounding_verdict\n")
        assert frames[5] == "event: done\ndata: [DONE]\n\n"

        # Verify build_rag_prompt was used (prompt passed to generate)
        mock_gen.assert_called_once()
        prompt_arg = mock_gen.call_args.args[0]
        assert "permit" in prompt_arg
        assert "[RETRIEVED_CONTEXT_START]" in prompt_arg

    @pytest.mark.asyncio
    async def test_answer_error_event_on_failure(self) -> None:
        """When Apertus raises, an 'answer_error' event is emitted (non-fatal)."""
        from unittest.mock import MagicMock

        results = [{"id": "1", "text": "Some text", "rank": 1}]
        rag = _fake_rag(results)
        request = _fake_request()

        async def mock_stream_error(*args, **kwargs):
            raise RuntimeError("Apertus timed out")
            yield

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
            patch(
                "app.api.v1.endpoints.search.generate_answer_stream",
                new_callable=MagicMock,
            ) as mock_gen,
        ):
            mock_gen.return_value = mock_stream_error()
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        # result + answer_error + done
        event_types = [f.split("\n")[0] for f in frames]
        assert "event: result" in event_types
        assert "event: answer_error" in event_types
        assert frames[-1] == "event: done\ndata: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_answer_skipped_when_disabled(self) -> None:
        """When Apertus is disabled, no answer event is emitted (no-op contract)."""
        results = [{"id": "1", "text": "text", "rank": 1}]
        rag = _fake_rag(results)
        request = _fake_request()

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=False),
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            frames = await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        # 1 result + results_complete + 1 done = 3 frames (no answer event)
        assert len(frames) == 3
        assert frames[0].startswith("event: result\n")
        assert frames[1].startswith("event: results_complete\n")
        assert frames[2] == "event: done\ndata: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_answer_skipped_on_empty_results(self) -> None:
        """No answer generation when no chunks were retrieved."""
        rag = _fake_rag([])
        request = _fake_request()

        with (
            patch("app.api.v1.endpoints.search.settings") as mock_settings,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
            patch(
                "app.api.v1.endpoints.search.generate_answer_stream",
                new_callable=AsyncMock,
            ) as mock_gen,
        ):
            mock_settings.SSE_CHUNK_DELAY_MS = 0
            await _collect(_sse_generator(q="q", top_k=5, rag=rag, request=request))

        # generate_answer should not be called when results is empty
        mock_gen.assert_not_called()


class TestSearchDocumentsEndpoint:
    """Tests for the non-streaming POST /search/ endpoint."""

    def _make_app(self) -> Any:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/search")
        return app

    @pytest.mark.asyncio
    async def test_search_documents_success(self) -> None:
        from app.integrations.llm.apertus_adapter import ApertusResponse

        app = self._make_app()
        fake_results = [
            {"id": "doc1", "text": "First chunk", "rank": 1},
            {"id": "doc2", "text": "Second chunk", "rank": 2},
        ]

        mock_response = ApertusResponse(
            answer="This is a generated answer based on docs.",
            model="swiss-ai/Apertus-8B-Instruct-2509",
            processing_time_ms=500.0,
        )

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
            patch(
                "app.api.v1.endpoints.search.apertus_generate",
                new_callable=AsyncMock,
                return_value=mock_response,
            ) as mock_gen,
        ):
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(return_value=fake_results)
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/search/",
                    json={
                        "query": "test query",
                        "language": "en",
                        "max_results": 5,
                    },
                )

            mock_gen.assert_awaited_once()

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "This is a generated answer based on docs."
        assert len(data["sources"]) == 2
        assert data["sources"][0]["title"] == "doc1"
        assert data["sources"][0]["excerpt"] == "First chunk"
        assert data["sources"][1]["title"] == "doc2"
        assert data["sources"][1]["excerpt"] == "Second chunk"
        assert data["query_language"] == "en"

    @pytest.mark.asyncio
    async def test_search_documents_fallback_answer(self) -> None:
        """When Apertus is disabled, it falls back to returning the first chunk's text."""
        app = self._make_app()
        fake_results = [
            {"id": "doc1", "text": "First chunk", "rank": 1},
        ]

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=False),
        ):
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(return_value=fake_results)
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/search/",
                    json={
                        "query": "test query",
                        "language": "fr",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "First chunk"
        assert len(data["sources"]) == 1
        assert data["query_language"] == "fr"

    @pytest.mark.asyncio
    async def test_search_documents_empty_results(self) -> None:
        app = self._make_app()

        with (
            patch("app.api.v1.endpoints.search.HindsightRAGService") as mock_rag_cls,
        ):
            mock_rag_instance = MagicMock()
            mock_rag_instance.query = AsyncMock(return_value=[])
            mock_rag_cls.return_value = mock_rag_instance

            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/search/",
                    json={
                        "query": "test query",
                        "language": "de",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == ""
        assert data["sources"] == []
        assert data["query_language"] == "de"
