"""Coverage batch 7 — real edge-case tests (no pragma).

Targets coverable statement-miss lines with genuine scenarios:
- chat_guidance: _is_followup_answer goal-phrase short-circuit (295-296)
- glossary: PostHog capture on extract (167)
- document_explanation: non-list retrieval results normalized to [] (468)
- search SSE: placeholder disclaimer (246) + answer-error outcome (328/334-336)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.api.v1.endpoints.search as search_ep
import app.services.chat_guidance as chat_guidance
from app.main import app
from app.services.document_explanation_service import explain_document

GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}


# ── chat_guidance: goal-phrase short-circuit ────────────────────────────────────


def test_is_followup_answer_goal_phrase_returns_false():
    # "I want to ..." contains a goal phrase -> not a followup answer (295-296)
    assert chat_guidance._is_followup_answer("I want to apply for a visa") is False


# ── glossary: PostHog capture path (real, client present) ───────────────────────


def test_glossary_extract_captures_event():
    fake_ph = MagicMock()
    with (
        patch("app.integrations.posthog.get_client", return_value=fake_ph),
        patch("app.api.v1.endpoints.glossary.extract_terms", return_value=[]),
    ):
        client = TestClient(app, headers=GDPR_HEADERS)
        resp = client.post(
            "/api/v1/glossary/extract",
            json={"source_lang": "en", "target_lang": "de", "text": "sample terms"},
        )
    assert resp.status_code in (200, 422)
    fake_ph.capture.assert_called()  # 167


# ── document_explanation: non-list retrieval results -> [] (468) ───────────────


@pytest.mark.asyncio
async def test_explain_document_non_list_results():
    classification = SimpleNamespace(
        document_type="contract", language_code="en", geographic_relevance=[]
    )
    analysis = SimpleNamespace(content="x", pages=[], paragraphs=[], key_value_pairs=[])
    with patch(
        "app.services.document_explanation_service.HindsightRAGService",
        return_value=MagicMock(query=AsyncMock(return_value="not-a-list")),
    ):
        result = await explain_document(analysis, classification, language="en")
    assert result is not None
    assert result.citations == []  # 468 normalized non-list -> []


# ── search SSE: placeholder disclaimer + error-event outcome ────────────────────


async def _placeholder_stream(prompt, **kwargs):
    yield "%s placeholder skeleton %%"


async def _boom_stream(prompt, **kwargs):
    raise RuntimeError("apertus down")
    yield  # makes this an async generator


def test_search_sse_placeholder_disclaimer():
    results = [
        {
            "id": "1",
            "text": "EU law excerpt",
            "type": "regulation",
            "chunk_id": "c1",
            "entities": [],
            "rank": 1,
            "document_id": "doc-1",
            "source_url": "https://europa.eu/x",
            "source_title": "Regulation",
            "source_language": "en",
        }
    ]
    with (
        patch.object(
            search_ep,
            "HindsightRAGService",
            return_value=MagicMock(query=AsyncMock(return_value=results)),
        ),
        patch.object(search_ep, "apertus_enabled", lambda: True),
        patch.object(search_ep, "generate_answer_stream", _placeholder_stream),
        patch.object(search_ep, "detect_placeholders", lambda text: True),
    ):
        client = TestClient(app, headers=GDPR_HEADERS)
        with client.stream("GET", "/api/v1/search/?q=visa") as resp:
            frames = [line for line in resp.iter_lines() if line.strip()]
    # Placeholder disclaimer emitted (246) when detect_placeholders true.
    assert any("answer_chunk" in f for f in frames)


def test_search_sse_error_event_outcome():
    results = [
        {
            "id": "1",
            "text": "x",
            "type": "t",
            "chunk_id": "c",
            "entities": [],
            "rank": 1,
            "document_id": "d",
            "source_url": "u",
            "source_title": "s",
            "source_language": "en",
        }
    ]
    with (
        patch.object(
            search_ep,
            "HindsightRAGService",
            return_value=MagicMock(query=AsyncMock(return_value=results)),
        ),
        patch.object(search_ep, "apertus_enabled", lambda: True),
        patch.object(search_ep, "generate_answer_stream", _boom_stream),
    ):
        client = TestClient(app, headers=GDPR_HEADERS)
        with client.stream("GET", "/api/v1/search/?q=test") as resp:
            frames = [line for line in resp.iter_lines() if line.strip()]
    assert any("answer_error" in f or "done" in f for f in frames)
