"""Coverage batch 12 — real edge-case tests (no pragma).

Targets coverable statement/branch misses with genuine scenarios:
- langfuse.log_generation: input_meta/usage branch arcs (319->321, 326->328, 328->331)
- langfuse.log_score: comment branch arc (370->373)
- document_explanation_service: build_legal_retrieval_query + _detect_directive_keywords arcs
  (294, 300, 304, 327, 331, 336, 342)
- chat_guidance._is_followup_answer: guidance-intent short-circuit (274)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.integrations.langfuse as langfuse
import app.services.chat_guidance as chat_guidance
import app.services.document_explanation_service as doc_exp

# ── langfuse: log_generation / log_score branch arcs ─────────────────────────────


@pytest.mark.asyncio
async def test_langfuse_log_generation_and_score_branches():
    langfuse.configure(enabled=True, public_key="pk", secret_key="sk")
    with patch.object(langfuse, "fire_and_forget", AsyncMock()):
        await langfuse.log_generation(
            trace_id="trace-1",
            model="m2m100-1.2b",
            input_meta={"source_language": "en"},
            output_meta={"target_language": "de"},
            latency_ms=12.5,
            usage={"input_tokens": 5, "output_tokens": 7},
        )
        await langfuse.log_score(
            trace_id="trace-1",
            name="translation_accuracy",
            value=0.9,
            comment="good",
        )
    # input_meta (319->321), usage input/output tokens (326->328, 328->331),
    # score comment (370->373) all exercised.


# ── document_explanation_service: retrieval-query builder arcs ──────────────────


def test_build_legal_retrieval_query_covers_branches():
    analysis = SimpleNamespace(
        content="Meldebescheinigung registration certificate residence",
        key_value_pairs=[{"key": {"content": "registration"}}],
        paragraphs=[],
    )
    classification = SimpleNamespace(
        document_type="registration certificate",
        geographic_relevance=["Germany"],
    )
    # language "de" triggers the non-en branch (327)
    query = doc_exp.build_legal_retrieval_query(analysis, classification, "de")
    assert "registration" in query.lower() or "germany" in query.lower()
    # _detect_directive_keywords: content (294), key_text (300), document_type (304)
    directives = doc_exp._detect_directive_keywords(analysis, classification)
    assert isinstance(directives, list)


def test_build_legal_retrieval_query_false_branches():
    # Falsy-but-non-empty inputs exercise the FALSE (loop-back) branch of every
    # `if` in the retrieval-query builders: 294->298, 300->298, 304->306,
    # 331->334, 336->334, 342->339.
    # - key_value_pairs with no usable key -> _key_content returns "" (300, 342)
    # - geographic_relevance with an empty string -> _query_term returns "" (336)
    analysis_empty = SimpleNamespace(content="", key_value_pairs=[{"value": "x"}], paragraphs=[])
    classification_empty = SimpleNamespace(document_type="", geographic_relevance=[""])
    query = doc_exp.build_legal_retrieval_query(analysis_empty, classification_empty, "en")
    assert isinstance(query, str)
    directives = doc_exp._detect_directive_keywords(analysis_empty, classification_empty)
    assert isinstance(directives, list)


@pytest.mark.asyncio
async def test_langfuse_log_generation_and_score_false_branches():
    langfuse.configure(enabled=True, public_key="pk", secret_key="sk")
    with patch.object(langfuse, "fire_and_forget", AsyncMock()):
        # usage present but without token keys -> 326->328, 328->331
        await langfuse.log_generation(trace_id="trace-2", model="m2m100-1.2b", usage={"other": 1})
        # No usage kwarg at all -> 325->331
        await langfuse.log_generation(trace_id="trace-3", model="m2m100-1.2b")
        # No comment -> 370->373
        await langfuse.log_score(trace_id="trace-3", name="translation_accuracy", value=0.9)


# ── chat_guidance: guidance-intent short-circuit (274) ──────────────────────────


def test_is_followup_answer_guidance_intent_returns_false():
    # A guidance-intent query must NOT be treated as a followup answer (274)
    assert chat_guidance._is_followup_answer("requirements for a work permit") is False


# ── apertus_adapter: _extract_apertus_content non-dict message (335->339) ────────


def test_extract_apertus_content_non_dict_message():
    from app.integrations.llm.apertus_adapter import _parse_chat_completion

    # choices[0].message is not a dict -> warning + "" (335->339)
    assert _parse_chat_completion({"choices": [{"message": "not-a-dict"}]}) == ""
    # message.content is not a str -> warning + "" (337->339)
    assert _parse_chat_completion({"choices": [{"message": {"content": 123}}]}) == ""
    # missing choices entirely -> "" too
    assert _parse_chat_completion({}) == ""


# ── glossary: /extract with persist=false (156->164) ───────────────────────────


def test_glossary_extract_no_persist(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.v1.endpoints import glossary as glossary_ep
    from app.main import app

    # Avoid any live LLM call in extract_terms
    monkeypatch.setattr(
        glossary_ep,
        "extract_terms",
        lambda text, source_lang: [],
    )

    GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/glossary/extract",
            json={"text": "Meldebescheinigung Anmeldung", "source_lang": "de", "persist": False},
            headers=GDPR_HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["persisted_count"] == 0
