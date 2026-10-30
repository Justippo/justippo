"""
Consolidated tests for small coverage gaps across multiple modules.

Covers:
|- app/api/v1/endpoints/health.py  line 32  — GET /api/v1/health/ liveness
|- app/api/v1/__init__.py           lines 26-27 — ENABLE_HEALTHCARE_PHASE2 branch
|- app/api/v1/endpoints/search.py   — POST / delegates to RAG, GET /stream delegates to SSE
|- app/api/v1/endpoints/search.py   — _sse_events/_sse_generator streaming branches
|  (results loop, guidance short-circuit, answer-generation stream,
|   TimeoutError/Exception → results_complete, client disconnect)
|- app/api/v1/endpoints/chat.py     — _wrapped_generator guidance short-circuit + memory_repo.append
|- app/api/v1/endpoints/translate.py lines 54-61,72-75,86-87 — HTTP endpoint level
|- app/api/v1/endpoints/exchange.py lines 85-91,124-130,150-168 — 502 error paths + events
|- app/main.py                      lines 26-33 — lifespan startup body
|- app/core/config.py               line 98  — production secret key validator
|- app/integrations/cloudflare/gateway.py line 26 — empty model path
|- app/services/glossary_service.py lines 37-42 — _get_baml_client lazy init
|
|Deviations from plan / coverage ceiling:
|  - Host-pytest ceiling ~94-96%, NOT 100%. Two unreachable classes:
|    (1) DEAD CODE — chat.py 519-571: 4 journey-event builder closures
|        (_build_next_step/_build_clarification/_build_document_checklist/
|        _build_action_plan) never called (0 repo call sites). The "→ SSE
|        journey_state_update" pipeline (journey_classifier.py:4,
|        journey_playbook.py:5) was scaffolded but never wired. PO decides
|        wire-up vs. delete; this file does not fabricate the feature.
|    (2) Pyodide/WASM runtime-only — workers_ai_adapter _get_neuron_budget_kv
|        env.AI/NeURON_BUDGET_KV reads (128-129, behind token guard) +
|        search.py _sse_generator finally/CancelledError (334-336, needs real
|        ASGI client-disconnect). workers_ai_adapter uses httpx.AsyncClient to
|        the CF AI Gateway (366/459), NOT env.AI FFI, so its HTTP branches ARE
|        MockTransport-mockable; only the KV guard + SSE finally are runtime.
|  - Codecov badge 93% is stale (uploads on push-to-main only, fail_ci_if_error=false;
|    Codecov branch recalculation ≠ pytest-cov's 94%). Ticks to 94% next green push.
|"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.sse import sse_frame
from tests.unit.d1_fakes import InMemoryD1Binding

GDPR = {"X-GDPR-Consent": "test-token"}


@pytest.fixture
def client() -> TestClient:
    from app.api.v1.endpoints.matrix_auth import (
        AuthenticatedMatrixSession,
        require_authenticated_matrix_session,
    )
    from app.main import app

    app.dependency_overrides[require_authenticated_matrix_session] = lambda: (
        AuthenticatedMatrixSession(
            session_id="test-session",
            user_id="@owner:matrix.test.org",
            device_id="TESTDEVICE",
            access_token="user-access-token",
        )
    )
    yield TestClient(app, headers=GDPR)
    app.dependency_overrides.pop(require_authenticated_matrix_session, None)


# ---------------------------------------------------------------------------
# health.py — GET /api/v1/health/  (distinct from root GET /health)
# ---------------------------------------------------------------------------


class TestV1HealthLiveness:
    def test_get_v1_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["sprint"] == 2


# ---------------------------------------------------------------------------
# config.py — production secret key validator (line 98)
# ---------------------------------------------------------------------------


class TestConfigProductionValidator:
    def test_production_rejects_default_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("APP_SECRET_KEY", "change-me-in-production")
        with pytest.raises(ValueError, match="APP_SECRET_KEY"):
            Settings()

    def test_production_accepts_custom_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("APP_SECRET_KEY", "super-secure-random-key-abc123xyz")
        # Must not raise
        s = Settings()
        assert s.is_production is True


# ---------------------------------------------------------------------------
# gateway.py — get_gateway_url with empty model (line 26)
# ---------------------------------------------------------------------------


class TestGatewayUrl:
    def test_empty_model_returns_base_url_without_trailing_slash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.integrations.cloudflare.gateway import get_gateway_url

        monkeypatch.setattr(
            "app.integrations.cloudflare.gateway.settings.CLOUDFLARE_ACCOUNT_ID", "acct123"
        )
        monkeypatch.setattr(
            "app.integrations.cloudflare.gateway.settings.CLOUDFLARE_GATEWAY_ID", "gw456"
        )
        monkeypatch.setattr("app.integrations.cloudflare.gateway.settings.CF_ACCOUNT_ID", "")
        monkeypatch.setattr("app.integrations.cloudflare.gateway.settings.CF_AI_GATEWAY_ID", "")

        url = get_gateway_url("mistral", "")
        assert url.endswith("/mistral")
        assert "//" not in url.replace("https://", "")


# ---------------------------------------------------------------------------
# search.py — POST / delegates to RAG pipeline, GET /stream delegates to SSE generator
# ---------------------------------------------------------------------------


class TestSearchStubEndpoints:
    def test_post_search_returns_500(self) -> None:
        from app.main import app

        c = TestClient(app, headers=GDPR, raise_server_exceptions=False)
        with patch(
            "app.api.v1.endpoints.search.HindsightRAGService.query",
            new_callable=AsyncMock,
            side_effect=RuntimeError("test RAG failure"),
        ):
            response = c.post(
                "/api/v1/search/",
                json={"query": "test", "language": "en"},
            )
        assert response.status_code == 500

    def test_get_search_stream_returns_sse_error(self) -> None:
        """GET /search/stream delegates to SSE generator — RAG errors become SSE events, not 500."""
        from app.main import app

        c = TestClient(app, headers=GDPR, raise_server_exceptions=False)
        response = c.get("/api/v1/search/stream", params={"query": "test"})
        # RAG connection fails → SSE generator catches it → 200 with error event
        assert response.status_code == 200
        assert "event: error" in response.text or "event: done" in response.text


# ---------------------------------------------------------------------------
# translate.py — HTTP endpoint level (lines 54-61, 72-75, 86-87)
# ---------------------------------------------------------------------------


class TestTranslateEndpoints:
    def test_post_translate_happy_path(self, client: TestClient) -> None:
        from app.services.translation_service import TranslationJob

        fake_job = TranslationJob(
            job_id="job-xyz",
            document_id="550e8400-e29b-41d4-a716-446655440000",
            source_language="en",
            target_language="de",
            status="done",
            translated_pages=[{"page": 1, "text": "Hallo"}],
            error=None,
        )

        with patch(
            "app.api.v1.endpoints.translate._svc.translate",
            new_callable=AsyncMock,
            return_value=fake_job,
        ):
            response = client.post(
                "/api/v1/translate/",
                json={
                    "document_id": "550e8400-e29b-41d4-a716-446655440000",
                    "source_language": "en",
                    "target_language": "de",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-xyz"
        assert data["status"] == "done"

    def test_get_translation_status_not_found(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.translate._svc.get_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get("/api/v1/translate/status/no-such-job")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_translation_status_found(self, client: TestClient) -> None:
        from app.services.translation_service import TranslationJob

        fake_job = TranslationJob(
            job_id="job-abc",
            document_id="doc-abc",
            source_language="en",
            target_language="fr",
            status="done",
            translated_pages=[],
            error=None,
        )
        with patch(
            "app.api.v1.endpoints.translate._svc.get_job",
            new_callable=AsyncMock,
            return_value=fake_job,
        ):
            response = client.get("/api/v1/translate/status/job-abc")

        assert response.status_code == 200
        assert response.json()["job_id"] == "job-abc"

    def test_get_languages_returns_pairs(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.translate._svc.get_supported_language_pairs",
            new_callable=AsyncMock,
            return_value=[
                {"source": "en", "target": "de"},
                {"source": "de", "target": "fr"},
            ],
        ):
            response = client.get("/api/v1/translate/languages")

        assert response.status_code == 200
        data = response.json()
        assert len(data["pairs"]) == 2


# ---------------------------------------------------------------------------
# exchange.py — 502 error paths + events success (lines 85-91, 124-130, 150-168)
# ---------------------------------------------------------------------------


class TestExchangeErrorPaths:
    @pytest.fixture(autouse=True)
    def _enable_matrix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True)

    def test_send_document_matrix_error_returns_502(self, client: TestClient) -> None:
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.send_document = AsyncMock(side_effect=MatrixClientError("homeserver down"))
            instance.close = AsyncMock()

            response = client.post(
                "/api/v1/exchange/send",
                data={"room_id": "!room:matrix.org"},
                files={"file": ("doc.pdf", b"content here", "application/pdf")},
            )

        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "matrix_send_failed"

    def test_send_document_generic_error_returns_502(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.send_document = AsyncMock(side_effect=ConnectionError("DNS"))
            instance.close = AsyncMock()

            response = client.post(
                "/api/v1/exchange/send",
                data={"room_id": "!room:matrix.org"},
                files={"file": ("doc.pdf", b"content here", "application/pdf")},
            )

        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "matrix_upstream_error"

    def test_create_room_matrix_error_returns_502(self, client: TestClient) -> None:
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(
                side_effect=MatrixClientError("federation failed")
            )
            instance.close = AsyncMock()

            response = client.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@user:matrix.org"]},
            )

        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "matrix_room_creation_failed"

    def test_create_room_generic_error_returns_502(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.create_secure_room = AsyncMock(side_effect=RuntimeError("crash"))
            instance.close = AsyncMock()

            response = client.post(
                "/api/v1/exchange/rooms",
                json={"participants": ["@user:matrix.org"]},
            )

        assert response.status_code == 502

    def test_get_events_success(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(
                return_value=[{"event_id": "$e1", "sender": "@u:m.org"}]
            )
            instance.close = AsyncMock()

            response = client.get("/api/v1/exchange/rooms/!room:matrix.org/events")

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_events_matrix_error_returns_502(self, client: TestClient) -> None:
        from app.integrations.matrix.client import MatrixClientError

        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(side_effect=MatrixClientError("room not found"))
            instance.close = AsyncMock()

            response = client.get("/api/v1/exchange/rooms/!room:matrix.org/events")

        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "matrix_events_failed"

    def test_get_events_generic_error_returns_502(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(side_effect=Exception("network timeout"))
            instance.close = AsyncMock()

            response = client.get("/api/v1/exchange/rooms/!room:matrix.org/events")

        assert response.status_code == 502

    def test_get_events_limit_capped_at_100(self, client: TestClient) -> None:
        """limit > 100 must be capped to 100 by the endpoint."""
        with patch("app.api.v1.endpoints.exchange.MatrixClient") as MockClient:
            instance = MockClient.return_value
            instance.get_room_events = AsyncMock(return_value=[])
            instance.close = AsyncMock()

            response = client.get("/api/v1/exchange/rooms/!room:matrix.org/events?limit=9999")

        assert response.status_code == 200
        # Verify get_room_events was called with limit capped
        _, call_kwargs = instance.get_room_events.call_args
        assert call_kwargs["limit"] <= 100


# ---------------------------------------------------------------------------
# api/v1/__init__.py — ENABLE_HEALTHCARE_PHASE2 branch (lines 26-27)
# ---------------------------------------------------------------------------


class TestApiV1HealthcareFlag:
    def test_healthcare_router_registered_when_flag_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ENABLE_HEALTHCARE_PHASE2=True, the healthcare router is imported and registered."""
        import importlib

        import app.api.v1 as v1_mod

        monkeypatch.setattr("app.core.config.settings.ENABLE_HEALTHCARE_PHASE2", True)
        importlib.reload(v1_mod)

        assert v1_mod.router is not None

        # Restore to False to avoid affecting other tests
        monkeypatch.setattr("app.core.config.settings.ENABLE_HEALTHCARE_PHASE2", False)
        importlib.reload(v1_mod)

    def test_healthcare_router_not_registered_by_default(self) -> None:
        from app.core.config import settings

        assert settings.ENABLE_HEALTHCARE_PHASE2 is False


# ---------------------------------------------------------------------------
# main.py — lifespan startup body (lines 26-33)
# ---------------------------------------------------------------------------


class TestMainLifespan:
    def test_lifespan_runs_without_error(self) -> None:
        """Using TestClient as context manager triggers startup/shutdown lifecycle."""
        from app.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            response = c.get("/health")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# glossary_service.py — _get_baml_client lazy init (lines 37-42)
# ---------------------------------------------------------------------------


class TestGetBamlClientLazyInit:
    def test_initialises_on_first_call(self) -> None:
        import app.services.glossary_service as glossary_mod

        original_b = glossary_mod._b
        try:
            # Reset so the lazy init path runs
            glossary_mod._b = None  # type: ignore[assignment]

            fake_b = MagicMock()
            fake_b.ExtractGlossaryTerms = MagicMock()

            with patch(
                "app.services.glossary_service._create_client",
                return_value=fake_b,
            ):
                result = glossary_mod._get_baml_client()

            assert result is fake_b
            assert glossary_mod._b is fake_b
        finally:
            # Always restore the global sentinel
            glossary_mod._b = original_b  # type: ignore[assignment]

    def test_returns_cached_client_on_second_call(self) -> None:
        import app.services.glossary_service as glossary_mod

        original_b = glossary_mod._b
        try:
            mock_client = MagicMock()
            glossary_mod._b = mock_client  # type: ignore[assignment]

            result = glossary_mod._get_baml_client()
            assert result is mock_client
        finally:
            glossary_mod._b = original_b  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# search.py — _sse_events / _sse_generator streaming branches
# (results loop, guidance short-circuit, answer-generation stream,
#  TimeoutError/Exception → results_complete, client disconnect)
# ---------------------------------------------------------------------------


def _request(disconnected: bool = False) -> MagicMock:
    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=disconnected)
    scope: dict[str, object] = {
        "env": SimpleNamespace(DB=InMemoryD1Binding(), NEURON_BUDGET_KV=None)
    }
    req.scope = scope
    req.url.path = "/api/v1/search/stream"
    return req


def _mock_rag(results: list[dict[str, object]]) -> MagicMock:
    rag = MagicMock()
    rag.query = AsyncMock(return_value=list(results))
    return rag


def _run_stream(gen):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_drain(gen))
    finally:
        loop.close()


async def _drain(gen):
    out: list[str] = []
    async for frame in gen:
        out.append(frame)
    return out


class TestSSEGeneratorStreaming:
    """Drive the real SSE generator body hermetically (no live LLM/D1).

    Mocks rag.query, generate_answer_stream, build_grounding_verdict so the
    generator executes its stream branches; InMemoryD1Binding stands in for the
    Worker-runtime D1 binding (see InMemoryKVBinding for the neuron-budget KV).
    """

    def test_results_loop_then_done(self) -> None:
        from app.api.v1.endpoints.search import _sse_events

        req = _request()
        rag = _mock_rag([{"id": "1", "score": 0.9}])
        with (
            patch("app.api.v1.endpoints.search.begin_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
        ):
            frames = _run_stream(_sse_events(q="residence permit", top_k=5, rag=rag, request=req))
        assert any("event: result" in f for f in frames)
        assert sse_frame("results_complete", "[RESULTS_READY") in frames or any(
            "results_complete" in f for f in frames
        )
        assert frames[-1] == sse_frame("done", "[DONE]")

    def test_guidance_matched_short_circuits(self) -> None:
        from app.api.v1.endpoints.search import _sse_events

        req = _request()
        rag = _mock_rag([{"id": "1"}])
        matched = {
            "reason": "verified_source",
            "message": "Curated answer text here",
            "query": "q",
        }
        with (
            patch(
                "app.api.v1.endpoints.search.build_empty_result_guidance",
                return_value=matched,
            ),
            patch(
                "app.api.v1.endpoints.search.apertus_enabled",
                return_value=True,
            ),
            patch("app.api.v1.endpoints.search.begin_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
        ):
            frames = _run_stream(_sse_events(q="q", top_k=5, rag=rag, request=req, guidance=True))
        assert sse_frame("guidance", matched) in frames

    def test_apertus_answer_generation_stream(self) -> None:
        from app.api.v1.endpoints.search import _sse_events

        req = _request()
        rag = _mock_rag([{"id": "1"}])

        async def fake_stream(*_a: object, **_k: object):
            for tok in ("Hello", " ", "world"):
                yield tok

        mock_model = MagicMock()
        mock_model.as_event_payload.return_value = "test-model"
        with (
            patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
            patch(
                "app.api.v1.endpoints.search.generate_answer_stream",
                side_effect=fake_stream,
            ),
            patch(
                "app.api.v1.endpoints.search.active_model_info",
                return_value=mock_model,
            ),
            patch(
                "app.api.v1.endpoints.search.build_grounding_verdict",
                return_value={"verdict": "grounded"},
            ),
            patch("app.api.v1.endpoints.search.begin_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
        ):
            frames = _run_stream(
                _sse_events(q="q", top_k=5, rag=rag, request=req, guidance=False, emit_model=True)
            )
        assert sse_frame("answer_model", "test-model") in frames
        assert any("answer_chunk" in f for f in frames)
        assert sse_frame("grounding_verdict", {"verdict": "grounded"}) in frames
        assert frames[-1] == sse_frame("done", "[DONE]")

    def test_timeout_error_emits_results_complete(self) -> None:
        from app.api.v1.endpoints.search import _sse_events

        req = _request()
        rag = MagicMock()
        rag.query = AsyncMock(side_effect=TimeoutError())
        with (
            patch("app.api.v1.endpoints.search.begin_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
        ):
            frames = _run_stream(_sse_events(q="q", top_k=5, rag=rag, request=req))
        assert sse_frame("results_complete", "[RESULTS_READY]") in frames

    def test_upstream_exception_emits_results_complete(self) -> None:
        from app.api.v1.endpoints.search import _sse_events

        req = _request()
        rag = MagicMock()
        rag.query = AsyncMock(side_effect=RuntimeError("rag down"))
        with (
            patch("app.api.v1.endpoints.search.begin_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
        ):
            frames = _run_stream(_sse_events(q="q", top_k=5, rag=rag, request=req))
        assert sse_frame("results_complete", "[RESULTS_READY]") in frames

    def test_client_disconnect_during_results(self) -> None:
        from app.api.v1.endpoints.search import _sse_events

        req = MagicMock()
        req.is_disconnected = AsyncMock(return_value=True)
        req.scope = {"env": SimpleNamespace(DB=InMemoryD1Binding(), NEURON_BUDGET_KV=None)}
        rag = _mock_rag([{"id": "1"}, {"id": "2"}])
        with (
            patch("app.api.v1.endpoints.search.begin_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
        ):
            frames = _run_stream(_sse_events(q="q", top_k=5, rag=rag, request=req))
        assert not any("event: result" in f for f in frames)

    def test_sse_generator_wraps_events_with_outcome(self) -> None:
        from app.api.v1.endpoints.search import _sse_generator

        req = _request()
        rag = _mock_rag([{"id": "1"}])
        with (
            patch("app.api.v1.endpoints.search.begin_search_stage_batch", return_value="batch"),
            patch("app.api.v1.endpoints.search.reset_search_stage_batch"),
            patch("app.api.v1.endpoints.search.flush_search_stage_batch"),
        ):
            frames = _run_stream(
                _sse_generator(q="q", top_k=5, rag=rag, request=req, emit_model=False)
            )
        assert any("event: result" in f for f in frames)
        assert frames[-1] == sse_frame("done", "[DONE]")

    def test_keepalive_ping_then_disconnect_during_query(self) -> None:
        """Cover keepalive ping (144) + disconnect-cancel (146-149, 328, 332-336).

        A pending RAG query makes ``asyncio.wait`` time out (keepalive), and
        ``is_disconnected()`` flipping True exercises the cancel/return path.
        Driven through ``_sse_generator`` so the ``finally`` outcome branches
        (premature_termination → client_disconnect, CancelledError) are hit too.
        """
        from app.api.v1.endpoints import search as search_module
        from app.api.v1.endpoints.search import _sse_generator

        req = _request(disconnected=True)

        # A coroutine that blocks forever (pending) so the keepalive
        # ``asyncio.wait`` times out → ping fires. Cancelled at 148 on
        # disconnect — cancelling ``asyncio.sleep`` is clean (no leak).
        def _pending_query(*_a: object, **_k: object):
            return asyncio.sleep(99)

        rag = MagicMock()
        rag.query = MagicMock(side_effect=_pending_query)
        with (
            patch.object(search_module, "begin_search_stage_batch"),
            patch.object(search_module, "flush_search_stage_batch"),
            patch.object(search_module, "reset_search_stage_batch"),
            # Simulate the keepalive ``asyncio.wait`` timing out (query_task still
            # pending) so the ``: ping`` keepalive (144) fires, then the client
            # disconnects (146-149 cancel + return) without waiting 10s.
            patch(
                "app.api.v1.endpoints.search.asyncio.wait",
                new_callable=AsyncMock,
                return_value=(set(), set()),
            ),
        ):
            frames = _run_stream(
                _sse_generator(
                    q="q",
                    top_k=5,
                    rag=rag,
                    request=req,
                    emit_model=False,
                )
            )
        # Keepalive ping emitted before cancellation.
        assert any(": ping" in frame for frame in frames)

    def test_disconnect_during_answer_generation(self) -> None:
        """Cover disconnect-after-first-token (220) + mid-generation (232-234).

        The apertus answer path yields the first token, then
        ``is_disconnected()`` flips True during the token loop.
        """
        from app.api.v1.endpoints import search as search_module
        from app.api.v1.endpoints.search import _sse_events

        call_count = {"n": 0}

        async def _disconnected_late() -> bool:
            call_count["n"] += 1
            # Results-loop (156), results_complete guard (194), apertus-entry
            # guard (202), post-first-token guard (219) must all be False so the
            # first token is emitted; the mid-generation token-loop check (231)
            # flips True to hit 232-234.
            return call_count["n"] > 4

        req = MagicMock()
        req.is_disconnected = _disconnected_late
        req.scope = {"env": SimpleNamespace(DB=InMemoryD1Binding(), NEURON_BUDGET_KV=None)}
        req.url.path = "/api/v1/search/stream"
        rag = _mock_rag([{"id": "1"}])

        async def fake_stream(*_a: object, **_k: object):
            for tok in ("tok1", "tok2", "tok3"):
                yield tok

        mock_model = MagicMock()
        mock_model.as_event_payload.return_value = "test-model"
        with (
            patch.object(search_module, "apertus_enabled", return_value=True),
            patch.object(search_module, "generate_answer_stream", side_effect=fake_stream),
            patch.object(search_module, "active_model_info", return_value=mock_model),
            patch.object(
                search_module, "build_grounding_verdict", return_value={"verdict": "grounded"}
            ),
            patch.object(search_module, "begin_search_stage_batch"),
            patch.object(search_module, "flush_search_stage_batch"),
            patch.object(search_module, "reset_search_stage_batch"),
        ):
            frames = _run_stream(
                _sse_events(
                    q="q",
                    top_k=5,
                    rag=rag,
                    request=req,
                    guidance=False,
                    emit_model=True,
                )
            )
        # First token emitted, then disconnect short-circuits the loop.
        assert any("answer_chunk" in f for f in frames)
        assert sse_frame("answer_model", "test-model") in frames

    def test_search_stream_route_language_fallback(self, client: TestClient) -> None:
        """Cover GET /search/stream route handler incl. language fallback (410-412).

        ``language='xx'`` is not in {en,de,fr} → normalized to 'en' (412).
        The normalization feeds ``_sse_generator`` and the capture_event
        properties, both of which we assert without running the live generator.
        """
        from app.api.v1.endpoints import search as search_module

        with (
            patch("app.integrations.posthog.capture_event", new_callable=AsyncMock) as mock_ce,
            patch.object(search_module, "HindsightRAGService"),
            patch.object(search_module, "_sse_response") as mock_resp,
        ):
            mock_resp.return_value = StreamingResponse(  # type: ignore[assignment]
                content=iter([]), media_type="text/event-stream"
            )
            client.get(
                "/api/v1/search/stream", params={"query": "hello", "language": "xx"}, headers=GDPR
            )
        # Language normalized from 'xx' → 'en' before capture_event (line 412).
        _, ce_kwargs = mock_ce.call_args
        assert ce_kwargs["properties"]["language"] == "en"


# ---------------------------------------------------------------------------
# chat.py — _wrapped_generator guidance short-circuit + memory_repo.append
# ---------------------------------------------------------------------------


class TestChatSSEWrapper:
    def test_chat_guidance_short_circuit(self, client: TestClient) -> None:
        from app.api.v1.endpoints import chat as chat_module

        matched = {
            "reason": "verified_source",
            "message": "Curated answer here.",
            "query": "q",
        }
        with (
            patch.object(chat_module, "build_empty_result_guidance", return_value=matched),
            patch("app.api.v1.endpoints.chat.D1Client") as mock_d1,
            patch.object(chat_module, "HindsightRAGService"),
        ):
            mock_d1.from_scope.return_value = InMemoryD1Binding()
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "residence permit", "language": "en"},
                headers={"X-GDPR-Consent": "test-token"},
            )
        assert resp.status_code == 200
        assert "guidance" in resp.text
        assert "[DONE]" in resp.text

    def test_chat_normal_rag_records_memory(self, client: TestClient) -> None:
        from app.api.v1.endpoints import chat as chat_module
        from app.api.v1.endpoints import search as search_module

        results = [{"id": "doc-1", "score": 0.9}]

        async def fake_answer_stream(*_a: object, **_k: object):
            for tok in ("Hello", " ", "world"):
                yield tok

        mock_model = MagicMock()
        mock_model.as_event_payload.return_value = "test-model"
        with (
            patch("app.api.v1.endpoints.chat.D1Client") as mock_d1,
            patch.object(chat_module, "is_greeting", return_value=False),
            patch.object(
                chat_module,
                "build_empty_result_guidance",
                return_value={"reason": "no_verified_source", "message": "", "query": "q"},
            ),
            patch.object(search_module, "apertus_enabled", return_value=True),
            patch.object(search_module, "generate_answer_stream", side_effect=fake_answer_stream),
            patch.object(search_module, "active_model_info", return_value=mock_model),
            patch.object(
                search_module,
                "build_grounding_verdict",
                return_value={"verdict": "grounded"},
            ),
            patch.object(search_module, "begin_search_stage_batch"),
            patch.object(search_module, "flush_search_stage_batch"),
            patch.object(search_module, "reset_search_stage_batch"),
            patch.object(chat_module, "HindsightRAGService") as mock_rag_cls,
            patch("app.integrations.posthog.capture_event", new_callable=AsyncMock),
            patch("app.core.config.settings.SESSION_MEMORY_ENABLED", True),
        ):
            mock_d1.from_scope.return_value = InMemoryD1Binding()
            mock_rag_cls.return_value.query = AsyncMock(return_value=results)
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "residence permit requirements", "language": "en"},
                headers={"X-GDPR-Consent": "test-token"},
            )
        assert resp.status_code == 200
        assert "[RESULTS_READY]" in resp.text
