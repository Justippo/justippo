# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coverage batch 13 — close the CI-only statement/branch misses.

Dry diagnostic: extracted the Missing column from CI run 31209411377
(job 92968390590, coverage==7.15.4) and from a local run with the SAME
coverage version (7.15.4 + env -u PYTHONPATH).  `comm`'d the two →
exactly 6 statement + 2 branch gaps.  This batch targets the
genuinely-COVERABLE lines (the rest are provably dead/defensive — see
"Dead lines" below, not faked, no pragma).

Targets (all real, reachable edge cases — not monkeypatch attribution tricks):
- not_diamond.py:230 — NOT_DIAMOND_PREFERENCE_ID set + TRANSLATION task selects
  _CUSTOM_TRANSLATION_CANDIDATES (TRUE branch of the pref_id guard).
- health.py:228 — pipeline_status returns "healthy" when EVERY component is healthy
  (requires every settings key to be truthy).
- laminar.py:246 — @observe-decorated fn whose return object carries _lmnr_attrs
  dict → attributes.update(extra) TRUE branch.
- rag_service.py:313 — RAGService.__init__ sets Authorization header when
  settings.HF_API_TOKEN is non-empty (TRUE branch of `if settings.HF_API_TOKEN:`).

Dead / defensive (intentionally NOT covered — honest ceiling, no pragma):
- health.py:230 — `elif any(s == "unavailable")`: no component in pipeline_status()
  can ever emit "unavailable" (all use healthy/degraded), so this branch is unreachable.
- laminar.py:268-269 — decorator's `except Exception: pass` wrapping _send_spans:
  _send_spans has its OWN try/except around fire_and_forget (laminar.py:205-210),
  so it only escapes on a BaseException-not-Exception (e.g. SystemExit), which no
  realistic code path raises. Intentionally left uncovered.

Attribution-proof by construction: health/not_diamond/rag tests mutate the shared
`app.core.config.settings` singleton directly via monkeypatch.setattr, which
propagates under CI's PYTHONPATH ordering — same mechanism the existing b12 tests use.

The laminar test (laminar.py:246) requires a different attribution-proof approach:
patching `app.integrations.laminar._enabled=True` AND `_send_spans` together via
string-path, then asserting the captured span carries the merged _lmnr_attrs.
Earlier attempts to patch `fire_and_forget` directly failed CI under full-suite
ordering: a prior test's leaked module-global state (sample_rate/_enabled) and
_send_spans's own `except Exception` (laminar.py:209) could swallow a build error
so the mock was 'awaited 0 times'. Patching _send_spans directly bypasses that
swallowing chain while still exercising line 246 (attributes.update(extra) runs in
the @observe wrapper at call time, before _send_spans is invoked).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.integrations.laminar as laminar
import app.integrations.routing.not_diamond as not_diamond_module
from app.integrations.routing.not_diamond import NotDiamondRouter, TaskType
from app.main import app

GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}


@pytest.fixture(autouse=True)
def _reset_laminar_state() -> None:
    """Reset module-level Laminar state before and after every test.

    Mirrors the autouse fixture in tests/test_laminar.py. Without it, a prior
    test in the shared suite can leave ``laminar._enabled``/``_sample_rate``/``_endpoint``
    in an unexpected state, so ``configure(enabled=True)`` here is a no-op on the
    already-gated module and ``fire_and_forget`` is never awaited → intermittent
    'Awaited 0 times' failure under CI's test ordering. Reset guarantees a clean
    slate regardless of which module form (app.* vs backend.app.*) CI loaded first.
    """
    laminar.configure(None, enabled=False)
    yield
    laminar.configure(None, enabled=False)


# ---------------------------------------------------------------------------
# not_diamond:230 — custom translation candidates when NOT_DIAMOND_PREFERENCE_ID set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_diamond_pref_id_uses_custom_translation_candidates(monkeypatch):
    """Line 230: with a preference_id configured, TRANSLATION routing uses
    _CUSTOM_TRANSLATION_CANDIDATES instead of the pre-trained candidate list.

    The pre-trained candidates use proxy models (mistral-small/openai); the custom
    list uses evidence-eu providers.  We assert the routed model differs from
    the mistral-small proxy path, proving the custom branch executed.
    """
    ms = not_diamond_module.settings
    monkeypatch.setattr(ms, "NOT_DIAMOND_ENABLED", True)
    monkeypatch.setattr(ms, "NOT_DIAMOND_API_KEY", "test-key-123")
    monkeypatch.setattr(ms, "NOT_DIAMOND_PREFERENCE_ID", "custom-router-123")
    monkeypatch.setattr(ms, "NOT_DIAMOND_DEFAULT_MODEL", "@cf/meta/m2m100-1.2b")
    monkeypatch.setattr(ms, "NOT_DIAMOND_TIMEOUT_MS", 800)

    router = NotDiamondRouter()
    # Custom candidates include evidence-eu/apertus-8b (line 230 sets the list
    # that _build_payload sends to Not Diamond's modelSelect endpoint).
    mock_response_body = {
        "providers": [{"provider": "evidence-eu", "model": "apertus-8b"}],
        "session_id": "sess_custom",
    }
    mock_response = SimpleNamespace(status_code=200)
    mock_response.json = lambda: mock_response_body
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("app.integrations.routing.not_diamond.httpx.AsyncClient", return_value=mock_client):
        result = await router.route(TaskType.TRANSLATION, {"language_pair": "en-de"})

    # apertus-8b maps to "mistral-large-translation" per MODEL_MAP — NOT the
    # mistral-small proxy.  This proves the _CUSTOM_TRANSLATION_CANDIDATES branch (230) ran.
    assert result == "mistral-large-translation"
    # Assert the payload sent to ND used the custom evidence-eu candidates.
    sent_payload = mock_client.__aenter__.return_value.post.await_args.kwargs["json"]
    sent_models = [c["model"] for c in sent_payload["llm_providers"] if isinstance(c, dict)]
    assert "apertus-8b" in sent_models
    assert all(c.get("provider") == "evidence-eu" for c in sent_payload["llm_providers"])


# ---------------------------------------------------------------------------
# health.py:228 — all components healthy → overall = "healthy"
# ---------------------------------------------------------------------------


def test_pipeline_all_healthy_returns_healthy(monkeypatch):
    """Line 228: overall="healthy" only fires when every component is healthy,
    which requires every settings key to be truthy (ocr + translation keys are
    empty by default → degraded in the existing test, so 228 was skipped by CI).

    We set just MISTRAL_API_KEY + CF_WORKERS_AI_API_TOKEN (the only two that
    default to "") and assert overall="healthy".
    """
    from app.api.v1.endpoints import health as health_module

    ms = health_module.settings
    monkeypatch.setattr(ms, "MISTRAL_API_KEY", "sk-test-mistral")
    monkeypatch.setattr(ms, "CF_WORKERS_AI_API_TOKEN", "cf-token-test")
    # The other keys (chromadb/hindsight/babeldoc/propella/matrix) have non-empty
    # defaults, so they're already "healthy".

    with TestClient(app) as client:
        resp = client.get("/api/v1/health/pipeline", headers=GDPR_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"  # line 227-228 — all-healthy branch
    assert all(c["status"] == "healthy" for c in data["components"].values())


# ---------------------------------------------------------------------------
# laminar.py:246 — @observe merges result._lmnr_attrs into span attributes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observe_merges_lmnr_attrs_into_span() -> None:
    """Line 246: attributes.update(extra) fires when the decorated function
    returns an object carrying a _lmnr_attrs dict (e.g. a service result that
    annotates itself with LLM metadata).  The existing tests return plain str,
    so the `isinstance(extra, dict)` TRUE branch at 246 was never exercised.

    Attribution-proof design: we patch ``app.integrations.laminar._enabled`` to
    True AND ``_send_spans`` together via string-path (same module object the
    ``@observe`` wrapper's closure reads globals from). Patching ``_send_spans``
    directly — rather than ``fire_and_forget`` — sidesteps the flaky chain
    (wrapper -> _send_spans -> _build_resource_spans -> fire_and_forget) where a
    prior test's leaked state or a swallowed _build_resource_spans exception
    (caught by _send_spans's own ``except Exception``) could leave the mock
    un-awaited. The wrapper builds the span (line 246 merges _lmnr_attrs into
    ``attributes`` at call time) and hands it to _send_spans; we assert the
    captured span carries the merged attr, proving line 246 ran.
    """

    class _AnnotatedResult:
        def __init__(self, value: str, attrs: dict) -> None:
            self.value = value
            self._lmnr_attrs = attrs

    @laminar.observe(name="annotated.span", span_type="LLM")
    async def annotated_fn() -> _AnnotatedResult:
        return _AnnotatedResult("ok", {"gen.ai.response.model": "m2m100-1.2b", "custom.tag": "x"})

    send_mock = AsyncMock()
    with (
        patch("app.integrations.laminar._enabled", True),
        patch("app.integrations.laminar._send_spans", new=send_mock),
    ):
        result = await annotated_fn()

    assert result.value == "ok"
    send_mock.assert_awaited_once()
    call_args = send_mock.await_args
    sent_span = call_args.args[0][0]
    attr_map = {a["key"]: a["value"] for a in sent_span["attributes"]}
    # The merged attribute from _lmnr_attrs proves line 246 ran.
    assert attr_map.get("gen.ai.response.model") == {"stringValue": "m2m100-1.2b"}
    assert attr_map.get("custom.tag") == {"stringValue": "x"}
    assert attr_map["lmnr.span.type"] == {"stringValue": "LLM"}


# ---------------------------------------------------------------------------
# rag_service.py:313 — RAGService.__init__ sets Authorization when HF_API_TOKEN set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rag_service_with_hf_api_token_sets_auth_header(monkeypatch):
    """Line 313: `headers["Authorization"] = ...` only runs when
    settings.HF_API_TOKEN is non-empty.  RAGService.__init__ imports settings
    from app.core.config at call-time, so monkeypatch.setattr on the shared
    singleton propagates under CI's PYTHONPATH ordering (no patch.object).
    """
    from app.core.config import settings
    from app.services.rag_service import RAGService

    monkeypatch.setattr(settings, "HF_API_TOKEN", "hf_test_token_123")
    monkeypatch.setattr(settings, "VECTOR_DB_PROVIDER", "cloudflare")

    svc = RAGService()
    # The httpx client was built with the Bearer token in its headers.
    auth = svc._llm_client.headers.get("Authorization")
    assert auth == "Bearer hf_test_token_123"
    # Close the httpx.AsyncClient we instantiated to avoid unclosed-resource warnings.
    await svc._llm_client.aclose()
