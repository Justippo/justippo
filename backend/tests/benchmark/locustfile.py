"""
Performance Test: /api/v1/search/ SSE Endpoint — Locust

Loads query fixtures from shared queries.json (DRY).
Tests SSE streaming latency: time-to-first-byte (TTFB), first result,
answer time-to-first-token, answer streaming, full-stream duration, and validates
event structure (result/error/done).

Usage:
    make perf-locust                          # default: 10 users, 60s
    locust -f backend/tests/benchmark/locustfile.py --headless \
        -u 50 -r 10 --run-time 120s --host http://localhost:8000

Environment variables:
    PERF_TARGET_HOST      — Override target (default: http://localhost:8000)
    PERF_USERS            — Number of concurrent users (default: 10)
    PERF_DURATION         — Test duration in seconds (default: 60)
    SSE_STREAM_TIMEOUT_S  — Max seconds to wait for SSE stream (default: 30)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from locust import HttpUser, between, events, task
from locust.runners import MasterRunner

# ── Constants ──────────────────────────────────────────────────────────────────

# Max time to wait for the full SSE stream to complete (seconds).
# Prevents greenlet blocking forever if server hangs mid-stream.
SSE_STREAM_TIMEOUT_S = float(os.environ.get("SSE_STREAM_TIMEOUT_S", "30"))

# ── Load shared query fixtures (DRY) ──────────────────────────────────────────

QUERIES_PATH = Path(__file__).parent / "queries.json"


_REQUIRED_QUERY_FIELDS = {"id", "q", "top_k", "category", "language"}


def _load_queries() -> list[dict[str, Any]]:
    """Load and validate query fixtures from shared JSON file."""
    with QUERIES_PATH.open() as f:
        data = json.load(f)
    queries = data["queries"]
    for i, entry in enumerate(queries):
        missing = _REQUIRED_QUERY_FIELDS - set(entry.keys())
        if missing:
            raise ValueError(f"queries.json entry {i} missing required fields: {missing}")
    return queries


QUERIES = _load_queries()

# ── Metrics collection ─────────────────────────────────────────────────────────

_metrics: dict[str, list[float]] = {
    "ttfb_ms": [],
    "first_result_ms": [],
    "answer_ttft_ms": [],
    "answer_stream_ms": [],
    "post_retrieval_ms": [],
    "full_stream_ms": [],
    "event_counts": [],
    "error_count": [],
}


@events.test_stop.add_listener
def _on_test_stop(environment: Any, **kwargs: Any) -> None:  # noqa: ARG001
    """Print summary metrics at test end."""
    if isinstance(environment.runner, MasterRunner):
        return  # Only print on workers/standalone

    if _metrics["ttfb_ms"]:
        ttfb = sorted(_metrics["ttfb_ms"])
        print("\n" + "=" * 60)
        print("SSE PERFORMANCE SUMMARY")
        print("=" * 60)
        print(f"  Samples:       {len(ttfb)}")
        print(f"  TTFB p50:      {_percentile(ttfb, 50):.1f} ms")
        print(f"  TTFB p95:      {_percentile(ttfb, 95):.1f} ms")
        print(f"  TTFB p99:      {_percentile(ttfb, 99):.1f} ms")
        _print_percentiles("First result", _metrics["first_result_ms"])
        _print_percentiles("Answer TTFT", _metrics["answer_ttft_ms"])
        _print_percentiles("Answer stream", _metrics["answer_stream_ms"])
        _print_percentiles("Post-retrieval", _metrics["post_retrieval_ms"])
        _print_percentiles("Full stream", _metrics["full_stream_ms"])
        print(f"  Errors:        {len(_metrics['error_count'])}")
        print("=" * 60 + "\n")


def _percentile(data: list[float], pct: int) -> float:
    """Calculate percentile from sorted list."""
    if not data:
        return 0.0
    idx = int(len(data) * pct / 100)
    return data[min(idx, len(data) - 1)]


def _print_percentiles(label: str, values: list[float]) -> None:
    """Print p50/p95/p99 for a stage when the stream emitted that stage."""
    if not values:
        return
    ordered = sorted(values)
    print(f"  {label} samples: {len(ordered)}")
    for pct in (50, 95, 99):
        print(f"  {label} p{pct}:     {_percentile(ordered, pct):.1f} ms")


# ── Locust User ───────────────────────────────────────────────────────────────


class SearchSSEUser(HttpUser):
    """Simulates a user making SSE search queries."""

    wait_time = between(0.5, 2.0)
    host = os.environ.get("PERF_TARGET_HOST", "http://localhost:8000")

    def on_start(self) -> None:
        """Initialize per-instance state (avoids class-variable race condition)."""
        self._query_idx = 0

    @task
    def search_sse(self) -> None:
        """Execute an SSE search and measure TTFB + full stream time."""
        if not QUERIES:
            return  # Guard: empty fixture file

        query = QUERIES[self._query_idx % len(QUERIES)]
        self._query_idx += 1

        # Match the browser EventSource contract exactly. EventSource cannot set
        # custom headers, so production SSE consent is carried in the query
        # string; include the fixture language so multilingual runs exercise
        # the same glossary-expansion path as real users.
        params = {
            "q": query["q"],
            "top_k": query["top_k"],
            "language": query["language"],
            "gdpr_consent": "true",
        }
        start = time.perf_counter()
        ttfb: float | None = None
        event_count = 0
        has_error = False
        error_detail = "unknown upstream error"
        has_done = False
        timed_out = False
        current_event_type: str | None = None
        first_result_at: float | None = None
        answer_first_token_at: float | None = None
        done_at: float | None = None

        with self.client.get(
            "/api/v1/search/",
            params=params,
            stream=True,
            catch_response=True,
            timeout=SSE_STREAM_TIMEOUT_S,
            name=f"/api/v1/search/ [{query['category']}]",
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                _metrics["error_count"].append(time.perf_counter() - start)
                return

            # Parse SSE stream with timeout guard
            try:
                for line in response.iter_lines():
                    # Check wall-clock timeout (protects against slow/hung streams)
                    if (time.perf_counter() - start) > SSE_STREAM_TIMEOUT_S:
                        timed_out = True
                        break

                    if ttfb is None:
                        ttfb = (time.perf_counter() - start) * 1000
                        _metrics["ttfb_ms"].append(ttfb)

                    if not line:
                        continue

                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line

                    if decoded.startswith("event: "):
                        current_event_type = decoded[7:].strip()
                        if current_event_type == "error":
                            has_error = True
                        elif current_event_type == "done":
                            has_done = True
                    elif decoded.startswith("data: "):
                        event_at = time.perf_counter()
                        event_count += 1
                        if current_event_type == "result" and first_result_at is None:
                            first_result_at = event_at
                        elif current_event_type == "answer_chunk" and answer_first_token_at is None:
                            answer_first_token_at = event_at
                        elif current_event_type == "done":
                            done_at = event_at
                        elif current_event_type == "error":
                            try:
                                payload = json.loads(decoded[6:])
                                error_detail = str(payload.get("message", error_detail))[:240]
                            except (json.JSONDecodeError, AttributeError):
                                error_detail = decoded[6:][:240]
            except Exception as exc:  # noqa: BLE001
                response.failure(f"Stream read error: {exc}")
                _metrics["error_count"].append(time.perf_counter() - start)
                return

            elapsed_ms = (time.perf_counter() - start) * 1000
            _metrics["full_stream_ms"].append(elapsed_ms)
            _metrics["event_counts"].append(event_count)
            if first_result_at is not None:
                _metrics["first_result_ms"].append((first_result_at - start) * 1000)
            if first_result_at is not None and answer_first_token_at is not None:
                _metrics["answer_ttft_ms"].append((answer_first_token_at - first_result_at) * 1000)
            if answer_first_token_at is not None and done_at is not None:
                _metrics["answer_stream_ms"].append((done_at - answer_first_token_at) * 1000)
            if first_result_at is not None and done_at is not None:
                _metrics["post_retrieval_ms"].append((done_at - first_result_at) * 1000)
            # If no lines were received, TTFB = full elapsed (empty stream edge case)
            if ttfb is None:
                _metrics["ttfb_ms"].append(elapsed_ms)

            # Validate stream structure
            if timed_out:
                response.failure(f"SSE stream timed out after {SSE_STREAM_TIMEOUT_S}s")
                _metrics["error_count"].append(elapsed_ms)
            elif not has_done:
                response.failure("SSE stream missing 'done' sentinel")
                _metrics["error_count"].append(elapsed_ms)
            elif has_error:
                response.failure(f"SSE stream contained error event: {error_detail}")
                _metrics["error_count"].append(elapsed_ms)
            else:
                response.success()
