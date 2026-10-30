import pytest

from app.core.config import settings
from app.core.hash_utils import sha256_digest
from app.integrations.trace_recorder import TraceRecorder, get_recorder


@pytest.fixture(autouse=True)
def _reset_recorder():
    recorder = get_recorder()
    recorder._traces = []
    yield


@pytest.fixture
def recorder(monkeypatch) -> TraceRecorder:
    monkeypatch.setattr(settings, "ENABLE_LLM_TRACING", True)
    r = TraceRecorder()
    r._traces = []
    return r


@pytest.fixture
def recorder_evict(monkeypatch) -> TraceRecorder:
    monkeypatch.setattr(settings, "ENABLE_LLM_TRACING", True)
    return TraceRecorder(max_entries=3)


@pytest.fixture
def recorder_disabled(monkeypatch) -> TraceRecorder:
    monkeypatch.setattr(settings, "ENABLE_LLM_TRACING", False)
    return TraceRecorder()


@pytest.fixture
def sample_prompt() -> str:
    return "What is the meaning of life?"


@pytest.fixture
def sample_response() -> str:
    return "42. That is the answer to the ultimate question."


# ── record() ──────────────────────────────────────────────────────────────────


async def test_record_creates_trace_with_hash_and_preview(recorder, sample_prompt, sample_response):
    trace = await recorder.record(
        model="test-model",
        prompt=sample_prompt,
        response=sample_response,
        latency_ms=150.0,
        token_count=42,
    )
    assert trace is not None
    assert trace.model == "test-model"
    assert trace.prompt_hash == sha256_digest(sample_prompt)
    assert trace.response_hash == sha256_digest(sample_response)
    assert trace.response_preview is not None
    assert len(trace.response_preview) == len(sample_response)
    assert trace.latency_ms == 150.0
    assert trace.token_count == 42
    assert trace.error is None
    assert trace.trace_id != ""


async def test_record_truncates_long_response_preview(recorder):
    long_response = "x" * 500
    trace = await recorder.record(model="m", prompt="p", response=long_response)
    assert trace is not None
    assert trace.response_preview == "x" * 200 + "..."
    assert len(trace.response_preview) == 203


async def test_record_with_empty_response(recorder):
    trace = await recorder.record(model="m", prompt="p", response="")
    assert trace is not None
    assert trace.response_preview == ""
    assert trace.response_hash == sha256_digest("")


async def test_record_no_response(recorder):
    trace = await recorder.record(model="m", prompt="p")
    assert trace is not None
    assert trace.response_hash is None
    assert trace.response_preview is None


async def test_record_with_error(recorder):
    trace = await recorder.record(model="m", prompt="p", error="Connection timeout")
    assert trace is not None
    assert trace.error == "Connection timeout"
    assert trace.response_hash is None


async def test_record_eviction(recorder_evict):
    for i in range(5):
        await recorder_evict.record(model="m", prompt=str(i))
    assert len(recorder_evict._traces) == 3
    assert recorder_evict._traces[0].prompt_hash == sha256_digest("2")
    assert recorder_evict._traces[-1].prompt_hash == sha256_digest("4")


async def test_record_disabled(recorder_disabled):
    trace = await recorder_disabled.record(model="m", prompt="p")
    assert trace is None
    assert len(recorder_disabled._traces) == 0


async def test_trace_timestamp_is_recent(recorder):
    import time

    before = time.time()
    trace = await recorder.record(model="m", prompt="p")
    after = time.time()
    assert trace is not None
    assert before <= trace.timestamp <= after


async def test_trace_trace_id_is_unique(recorder):
    ids = set()
    for i in range(10):
        t = await recorder.record(model="m", prompt=str(i))
        assert t is not None
        ids.add(t.trace_id)
    assert len(ids) == 10


# ── search() ──────────────────────────────────────────────────────────────────


async def test_search_all(recorder):
    for i in range(5):
        await recorder.record(model="m", prompt=str(i))
    results = await recorder.search()
    assert len(results) == 5


async def test_search_filter_model(recorder):
    await recorder.record(model="a", prompt="x")
    await recorder.record(model="b", prompt="y")
    await recorder.record(model="a", prompt="z")
    results = await recorder.search(model="a")
    assert len(results) == 2
    assert all(t.model == "a" for t in results)


async def test_search_filter_prompt_hash(recorder):
    await recorder.record(model="a", prompt="hello")
    await recorder.record(model="b", prompt="world")
    h = sha256_digest("hello")
    results = await recorder.search(prompt_hash=h)
    assert len(results) == 1
    assert results[0].prompt_hash == h


async def test_search_limit(recorder):
    for i in range(10):
        await recorder.record(model="m", prompt=str(i))
    results = await recorder.search(limit=3)
    assert len(results) == 3


async def test_search_model_and_hash(recorder):
    h = sha256_digest("x")
    await recorder.record(model="a", prompt="x")
    await recorder.record(model="b", prompt="x")
    await recorder.record(model="a", prompt="y")
    results = await recorder.search(model="a", prompt_hash=h)
    assert len(results) == 1


async def test_search_disabled(recorder_disabled):
    results = await recorder_disabled.search()
    assert results == []


async def test_search_empty(recorder):
    results = await recorder.search()
    assert results == []


# ── stats() ───────────────────────────────────────────────────────────────────


async def test_stats_empty(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LLM_TRACING", True)
    r = TraceRecorder()
    s = await r.stats()
    assert s == {"count": 0}


async def test_stats_aggregation(recorder):
    await recorder.record(model="a", prompt="p1", response="r1", latency_ms=100.0, token_count=10)
    await recorder.record(model="a", prompt="p2", response="r2", latency_ms=200.0, token_count=20)
    await recorder.record(model="b", prompt="p3", error="timeout")
    s = await recorder.stats()
    assert s["count"] == 3
    assert set(s["models"]) == {"a", "b"}
    assert s["error_count"] == 1
    assert s["error_rate"] == pytest.approx(1 / 3, rel=1e-4)
    assert s["avg_latency_ms"] == 150.0
    assert s["p95_latency_ms"] == 195.0


async def test_stats_disabled(recorder_disabled):
    s = await recorder_disabled.stats()
    assert s == {"count": 0}


# ── singleton ─────────────────────────────────────────────────────────────────


async def test_get_recorder_singleton():
    r1 = get_recorder()
    r2 = get_recorder()
    assert r1 is r2


async def test_get_recorder_creates_when_none(monkeypatch):
    from app.integrations.trace_recorder import TraceRecorder

    monkeypatch.setattr(settings, "ENABLE_LLM_TRACING", True)
    import app.integrations.trace_recorder as tr

    tr._recorder = None
    r = tr.get_recorder()
    assert r is not None
    assert isinstance(r, TraceRecorder)


async def test_stats_with_latency_edge_cases(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LLM_TRACING", True)
    r = TraceRecorder()
    s = await r.stats()
    assert s == {"count": 0}

    await r.record(model="m", prompt="x", latency_ms=500.0)
    s = await r.stats()
    assert s["count"] == 1
    assert s["avg_latency_ms"] == 500.0
    assert s["p95_latency_ms"] == 500.0
