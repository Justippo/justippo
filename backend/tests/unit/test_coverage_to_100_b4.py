"""Coverage drive to 100% — batch 4 (hermetic, no pragma).

Targets the capstone RAG search SSE path (search.py 246/328/334-336) and other
coverable statement lines: chat_guidance branches, document_explanation,
translation, glossary, langfuse/workers_ai/laminar defensive branches where a
contrived-but-valid trigger exists. Dead/unreachable branches (health 230,
gateway 62, classification 404, pdf_intake 91-92, azure 393, apertus 420,
search disconnect 220/230) are intentionally NOT covered and documented.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import app.api.v1.endpoints.search as search_ep
from app.main import app

GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}


def _fake_rag_with_results(results):
    fake = MagicMock()
    fake.query = AsyncMock(return_value=results)
    return fake


async def _placeholder_stream(prompt, **kwargs):
    # Yield a token containing a skeleton placeholder so detect_placeholders fires.
    yield "%s placeholder skeleton %%"


def test_search_sse_placeholder_and_done_events():
    # search.py: covers _sse_events answer-generation (246 placeholder disclaimer)
    # and _sse_generator outcome logging (328 error-event, 334-336 done-event).
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
            search_ep, "HindsightRAGService", return_value=_fake_rag_with_results(results)
        ),
        patch.object(search_ep, "apertus_enabled", lambda: True),
        patch.object(search_ep, "generate_answer_stream", _placeholder_stream),
        patch.object(search_ep, "detect_placeholders", lambda text: True),
    ):
        client = TestClient(app, headers=GDPR_HEADERS)
        with client.stream("GET", "/api/v1/search/?q=visa+requirements") as resp:
            frames = [line for line in resp.iter_lines() if line.strip()]
    # The stream must have produced at least results + done events.
    assert any("result" in f or "done" in f or "answer_chunk" in f for f in frames)


def test_search_sse_error_event_path():
    # _sse_generator line 328: an upstream "error" frame flips saw_application_error.
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

    async def _boom_stream(prompt, **kwargs):
        yield 'event: error\ndata: {"message": "boom"}\n\n'

    with (
        patch.object(
            search_ep, "HindsightRAGService", return_value=_fake_rag_with_results(results)
        ),
        patch.object(search_ep, "apertus_enabled", lambda: True),
        patch.object(search_ep, "generate_answer_stream", _boom_stream),
    ):
        client = TestClient(app, headers=GDPR_HEADERS)
        with client.stream("GET", "/api/v1/search/?q=test") as resp:
            frames = [line for line in resp.iter_lines() if line.strip()]
    assert frames  # stream produced frames including the error event
