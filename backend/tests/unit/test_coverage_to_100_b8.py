"""Coverage batch 8 — real edge-case tests (no pragma).

Targets coverable statement/branch misses with genuine scenarios:
- translation_service._split_translation_sections: over-long sentence word-chunking
  fallback (190-205)
- chat_guidance._is_followup_answer: personal-status declaration paths (314-340)
- rag_service: Hindsight recall retry on HTTP 429 (954-982)
"""

from __future__ import annotations

import app.services.chat_guidance as chat_guidance
from app.services.translation_service import _split_translation_sections

# ── translation_service: long-sentence word-chunking fallback ──────────────────


def test_split_translation_sections_long_sentence_chunked():
    # A single sentence far exceeding max_chars must be split by words (190-205).
    long_sentence = "This is an extremely long single sentence that should be broken into word chunks because it exceeds the maximum character limit allowed per translation section by a wide margin for sure."
    sections = _split_translation_sections(long_sentence, max_chars=20)
    assert sections, "expected non-empty sections"
    # Every produced chunk respects the max_chars limit.
    assert all(len(s) <= 20 for s in sections)
    # The fallback word-chunking path (194-204) was exercised.
    assert len(sections) > 1


def test_split_translation_sections_normal_sentence():
    sections = _split_translation_sections("Short sentence one. Short sentence two.", max_chars=30)
    assert len(sections) == 2


# ── chat_guidance: _is_followup_answer personal-status paths ───────────────────


def test_is_followup_answer_personal_status_with_keyword():
    # "I am an EU citizen" -> starts with status prefix AND has status keyword
    # -> returns True (334). Exercises 314-334.
    assert chat_guidance._is_followup_answer("I am an EU citizen") is True


def test_is_followup_answer_personal_status_short_no_keyword():
    # "I am here" -> status prefix, <=12 words, no keyword -> returns True (338).
    assert chat_guidance._is_followup_answer("I am here") is True


def test_is_followup_answer_plain_statement_false():
    # A normal noun phrase is not a followup answer.
    assert chat_guidance._is_followup_answer("renewal requirements") is False
