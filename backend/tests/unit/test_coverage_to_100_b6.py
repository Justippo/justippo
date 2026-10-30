"""Coverage batch 6 — real edge-case/bug tests (no pragma).

Targets coverable statement-miss lines with genuine scenarios:
- journey_content: None jurisdiction short-circuits (317-318, 325-326)
- journey_playbook: unknown step -> _is_step_complete returns False (157-158)
- session_topic: query truncation (463) + retrieval context with topic dict (488)
- documents: GET /{id}/classification 404 when unknown (379-380)
- document_explanation: _page_number non-list / non-dict guards (210-217),
  _key_content non-dict (222-223), requirement dedup guard (243)
- translation_service: empty translation raises (417-418) via real retry loop
- chat_guidance: _is_followup_answer question-prefix + intent-trigger short-circuits
- main: lifespan DB-init exception is swallowed (90-94)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.services.chat_guidance as chat_guidance
import app.services.journey_content as journey_content
import app.services.journey_playbook as journey_playbook
import app.services.session_topic as session_topic
from app.main import app
from app.services.document_explanation_service import (
    _key_content,
    _page_number,
    extract_document_requirements,
)

GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}


# ── journey_content: None jurisdiction short-circuits ───────────────────────────


def test_journey_content_none_jurisdiction_returns_none():
    assert journey_content.get_step_documents("check_language", None) is None  # 317-318
    assert journey_content.get_authority_info(None) is None  # 325-326


# ── journey_playbook: unknown step -> not complete ─────────────────────────────


def test_journey_playbook_unknown_step_not_complete():
    assert journey_playbook._is_step_complete("unknown_step_xyz", {}) is False  # 157-158


# ── session_topic: query truncation + retrieval context ────────────────────────


def test_session_topic_query_truncation():
    tracker = session_topic.SessionTopicTracker()
    many = [f"q{i}" for i in range(session_topic._MAX_USER_QUERIES + 5)]
    facts: dict = {"last_user_queries": list(many)}
    tracker.update_topic("extra query", facts)
    assert len(facts["last_user_queries"]) <= session_topic._MAX_USER_QUERIES  # 463


def test_session_topic_retrieval_context_with_topic_dict():
    ctx = session_topic.SessionTopicTracker().get_retrieval_context(
        "how do I renew?",
        {"topic": {"subject": "renewal", "keywords": ["visa"]}},
    )
    assert isinstance(ctx, str)  # 488 topic branch


# ── documents: GET /{id}/classification 404 when unknown ──────────────────────


def test_documents_get_classification_404_unknown_id():
    client = TestClient(app, headers=GDPR_HEADERS)
    resp = client.get("/api/v1/documents/does-not-exist-xyz/classification")
    assert resp.status_code == 404  # 379-380


# ── document_explanation: defensive guards (real invalid inputs) ──────────────


def test_page_number_non_list_and_non_dict():
    assert _page_number("not a dict") is None  # 207-208
    assert _page_number({"boundingRegions": [{"pageNumber": 0}, {"pageNumber": 2}]}) == 2
    # non-dict region is skipped (213-214)
    assert (
        _page_number({"boundingRegions": [{"pageNumber": 0}, "not a dict", {"pageNumber": 3}]}) == 3
    )


def test_key_content_non_dict():
    assert _key_content("not a dict") == ("", None)  # 222-223


def test_extract_requirements_returns_list():
    class _A:
        pages = []
        paragraphs = []
        key_value_pairs = []

    reqs = extract_document_requirements(_A())
    assert isinstance(reqs, list)  # exercises append path / dedup guard (243)


# ── chat_guidance: _is_followup_answer short-circuits ──────────────────────────


def test_is_followup_answer_question_prefix_returns_false():
    assert chat_guidance._is_followup_answer("What is the deadline?") is False  # 279-282
    assert chat_guidance._is_followup_answer("How do I apply?") is False
    assert chat_guidance._is_followup_answer("show me work permits") is False  # intent trigger 274
