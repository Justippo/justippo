import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.hash_utils import sha256_digest


@dataclass
class LLMTrace:
    model: str
    prompt_hash: str
    response_hash: str | None = None
    response_preview: str | None = None
    latency_ms: float | None = None
    token_count: int | None = None
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    trace_id: str = ""


class TraceRecorder:
    """In-memory ring buffer of LLM call metadata.

    Feature-flagged by ``ENABLE_LLM_TRACING`` (default False). When disabled,
    all methods are transparent no-ops — zero overhead, zero allocations.

    No document content is ever stored. Only hashes and a short preview
    (first 200 chars) of the response are retained for debugging.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._traces: list[LLMTrace] = []
        self._max_entries = max_entries

    @property
    def enabled(self) -> bool:
        return settings.ENABLE_LLM_TRACING

    async def record(
        self,
        model: str,
        prompt: str,
        response: str | None = None,
        latency_ms: float | None = None,
        token_count: int | None = None,
        error: str | None = None,
    ) -> LLMTrace | None:
        """Record an LLM call.

        Stores only metadata — the prompt and response are hashed (SHA-256),
        and a 200-char preview of the response is kept for quick debugging.
        The record is appended to an in-memory ring buffer; old entries are
        evicted when ``max_entries`` is exceeded.
        """
        if not self.enabled:
            return None

        trace = LLMTrace(
            model=model,
            prompt_hash=sha256_digest(prompt),
            response_hash=sha256_digest(response) if response is not None else None,
            response_preview=(response[:200] + "...")
            if response and len(response) > 200
            else response,
            latency_ms=latency_ms,
            token_count=token_count,
            error=error,
            trace_id=uuid.uuid4().hex[:12],
        )
        self._traces.append(trace)
        if len(self._traces) > self._max_entries:
            self._traces.pop(0)
        return trace

    async def search(
        self,
        model: str | None = None,
        prompt_hash: str | None = None,
        limit: int = 50,
    ) -> list[LLMTrace]:
        """Search recorded traces by optional model and/or prompt hash."""
        if not self.enabled:
            return []
        results = self._traces
        if model:
            results = [t for t in results if t.model == model]
        if prompt_hash:
            results = [t for t in results if t.prompt_hash == prompt_hash]
        return results[-limit:]

    async def stats(self) -> dict[str, Any]:
        """Aggregate statistics over all recorded traces."""
        if not self.enabled or not self._traces:
            return {"count": 0}
        latencies = [t.latency_ms for t in self._traces if t.latency_ms is not None]
        errors = [t for t in self._traces if t.error]
        return {
            "count": len(self._traces),
            "models": list({t.model for t in self._traces}),
            "error_count": len(errors),
            "error_rate": round(len(errors) / len(self._traces), 4) if self._traces else 0.0,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p95_latency_ms": _percentile(sorted(latencies), 0.95) if latencies else None,
        }


_recorder: TraceRecorder | None = None


def get_recorder() -> TraceRecorder:
    global _recorder
    if _recorder is None:
        _recorder = TraceRecorder()
    return _recorder


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * percentile
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
