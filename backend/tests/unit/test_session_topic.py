"""Unit tests for the SessionTopicTracker."""

from __future__ import annotations

from copy import deepcopy

from app.services.session_topic import (
    SessionTopicTracker,
    _extract_content_words,
    _infer_topic_subject,
    _jaccard_similarity,
)


def _tracker() -> SessionTopicTracker:
    return SessionTopicTracker()


# ── Content word extraction ───────────────────────────────────────────────────


def test_extract_content_words_removes_stopwords() -> None:
    words = _extract_content_words("I want to work in Germany as an engineer")
    assert "germany" in words
    assert "engineer" in words
    assert "i" not in words
    assert "want" not in words
    assert "to" not in words


def test_extract_content_words_german() -> None:
    words = _extract_content_words("Ich mochte in Deutschland als Ingenieur arbeiten")
    assert "deutschland" in words
    assert "ingenieur" in words
    assert "ich" not in words


def test_extract_content_words_french() -> None:
    words = _extract_content_words("Je veux travailler en France comme ingénieur")
    assert "france" in words
    assert "ingénieur" in words
    assert "je" not in words


def test_extract_content_words_empty() -> None:
    assert _extract_content_words("") == []


def test_extract_content_words_only_stopwords() -> None:
    # All words are stopwords
    words = _extract_content_words("the and or of to in on")
    assert words == []


def test_extract_content_words_removes_numeric() -> None:
    words = _extract_content_words("Section 5 of Article 8 regulation")
    assert "section" in words
    assert "regulation" in words
    for w in words:
        assert not w.isnumeric()


# ── Jaccard similarity ────────────────────────────────────────────────────────


def test_jaccard_identical_sets() -> None:
    sim = _jaccard_similarity({"work", "germany"}, {"work", "germany"})
    assert sim == 1.0


def test_jaccard_disjoint_sets() -> None:
    sim = _jaccard_similarity({"work", "germany"}, {"study", "france"})
    assert sim == 0.0


def test_jaccard_partial_overlap() -> None:
    sim = _jaccard_similarity({"work", "germany", "engineer"}, {"work", "germany", "blue", "card"})
    assert 0.2 < sim < 0.5  # 2/5 = 0.4


def test_jaccard_empty() -> None:
    sim = _jaccard_similarity(set(), set())
    assert sim == 1.0


# ── Topic subject inference ───────────────────────────────────────────────────


def test_infer_subject_from_words() -> None:
    subject = _infer_topic_subject(["work", "germany", "engineer"])
    assert subject == "work germany engineer"


def test_infer_subject_truncated() -> None:
    words = [str(i) for i in range(20)]
    subject = _infer_topic_subject(words, max_words=3)
    assert subject == "0 1 2"


def test_infer_subject_empty() -> None:
    assert _infer_topic_subject([]) == ""


# ── First turn ────────────────────────────────────────────────────────────────


def test_first_turn_sets_initial_topic() -> None:
    facts = _tracker().update_topic(
        "How do I get a work permit in Germany?", {}, "en", is_first_turn=True
    )
    topic = facts.get("topic")
    assert isinstance(topic, dict)
    assert (
        "germany" in topic.get("subject", "").lower() or "work" in topic.get("subject", "").lower()
    )
    assert len(topic.get("keywords", [])) > 0
    assert topic.get("since_turn") == 1
    assert "last_user_queries" in facts
    assert len(facts["last_user_queries"]) == 1


def test_first_turn_german() -> None:
    facts = _tracker().update_topic(
        "Wie bekomme ich eine Arbeitserlaubnis in Deutschland?",
        {},
        "de",
        is_first_turn=True,
    )
    topic = facts.get("topic")
    assert isinstance(topic, dict)
    assert any(
        "arbeitserlaubnis" in w or "deutschland" in w for w in topic.get("subject", "").split()
    )


def test_first_turn_sets_last_queries() -> None:
    facts = _tracker().update_topic("First message", {}, "en", is_first_turn=True)
    assert facts.get("last_user_queries") == ["First message"]


# ── Same topic (no shift) ─────────────────────────────────────────────────────


def test_same_topic_no_shift() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "work in germany",
            "keywords": ["work", "germany", "permit"],
            "since_turn": 1,
        },
        "topics_history": [],
        "last_user_queries": ["How to get a work permit in Germany"],
    }
    facts = _tracker().update_topic(
        "What documents do I need for the work permit?",
        deepcopy(facts),
        "en",
    )
    assert facts.get("_last_topic_shift") is False
    topic = facts.get("topic")
    assert isinstance(topic, dict)
    assert "germany" in topic.get("subject", "").lower() or "work" in topic.get("keywords", [])


# ── Topic shift ───────────────────────────────────────────────────────────────


def test_topic_shift_detected() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "work in germany",
            "keywords": ["work", "germany", "permit", "blue", "card"],
            "since_turn": 1,
        },
        "topics_history": [],
        "last_user_queries": ["How to get a Blue Card in Germany"],
    }
    facts = _tracker().update_topic(
        "Tell me about family reunification in France",
        deepcopy(facts),
        "en",
    )
    assert facts.get("_last_topic_shift") is True
    topic = facts.get("topic")
    assert isinstance(topic, dict)
    assert (
        "france" in topic.get("subject", "").lower() or "family" in topic.get("subject", "").lower()
    )


def test_topic_history_appended_on_shift() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "work in germany",
            "keywords": ["work", "germany", "permit"],
            "since_turn": 1,
        },
        "topics_history": [],
        "last_user_queries": ["How to get a work permit in Germany"],
    }
    facts = _tracker().update_topic(
        "What about studying in France?",
        deepcopy(facts),
        "en",
    )
    history = facts.get("topics_history")
    assert isinstance(history, list)
    assert len(history) == 1
    assert history[0]["subject"] == "work in germany"


def test_topic_history_multiple_shifts() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "work germany",
            "keywords": ["work", "germany"],
            "since_turn": 1,
        },
        "topics_history": [],
        "last_user_queries": ["message 1"],
    }
    # Shift 1
    facts = _tracker().update_topic("Now about studying in France", deepcopy(facts), "en")
    assert len(facts.get("topics_history", [])) == 1
    # Shift 2
    facts = _tracker().update_topic("I need health insurance in Spain", deepcopy(facts), "en")
    assert len(facts.get("topics_history", [])) == 2


# ── Short messages (too few content words) ────────────────────────────────────


def test_short_message_keeps_topic() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "work in germany",
            "keywords": ["work", "germany"],
            "since_turn": 1,
        },
        "topics_history": [],
        "last_user_queries": ["How to get a work permit in Germany"],
    }
    facts = _tracker().update_topic("Yes please", deepcopy(facts), "en")
    # Too few content words — no shift detected
    assert facts.get("_last_topic_shift") is False
    topic = facts.get("topic")
    assert isinstance(topic, dict)
    assert topic.get("subject") == "work in germany"


def test_short_message_updates_queries() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "test",
            "keywords": ["test"],
            "since_turn": 1,
        },
        "topics_history": [],
        "last_user_queries": ["Initial query"],
    }
    facts = _tracker().update_topic("yes", deepcopy(facts), "en")
    queries = facts.get("last_user_queries", [])
    assert "yes" in queries


# ── Retrieval context building ────────────────────────────────────────────────


def test_retrieval_context_no_topic() -> None:
    result = _tracker().get_retrieval_context("What are the rules?", None)
    assert result == "What are the rules?"


def test_retrieval_context_no_facts() -> None:
    result = _tracker().get_retrieval_context("What are the rules?", {})
    assert result == "What are the rules?"


def test_retrieval_context_with_topic() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "work in germany",
            "keywords": ["work", "germany"],
            "since_turn": 1,
        },
        "_last_topic_shift": False,
    }
    result = _tracker().get_retrieval_context("What documents do I need?", facts)
    assert "Current topic:" in result
    assert "work in germany" in result
    assert "What documents do I need?" in result


def test_retrieval_context_on_shift() -> None:
    facts: dict[str, object] = {
        "topic": {
            "subject": "family reunification france",
            "keywords": ["family", "france"],
            "since_turn": 3,
        },
        "_last_topic_shift": True,
    }
    result = _tracker().get_retrieval_context("What documents for family visa?", facts)
    assert "New topic:" in result
    assert "family reunification france" in result


# ── Clear topic ───────────────────────────────────────────────────────────────


def test_clear_topic_removes_fields() -> None:
    facts: dict[str, object] = {
        "topic": {"subject": "work"},
        "topics_history": [{"subject": "old"}],
        "last_user_queries": ["old query"],
    }
    facts = _tracker().clear_topic(facts)
    assert "topic" not in facts
    assert "topics_history" not in facts
    assert "last_user_queries" not in facts


def test_clear_topic_none_facts() -> None:
    facts = _tracker().clear_topic(None)
    assert facts == {}


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_update_topic_none_facts() -> None:
    facts = _tracker().update_topic("Hello", None, "en", is_first_turn=False)
    assert isinstance(facts, dict)
    # With no existing topic and not first turn, still sets a topic
    topic = facts.get("topic")
    assert isinstance(topic, dict)


def test_get_current_topic_no_facts() -> None:
    assert _tracker().get_current_topic(None) == ""


def test_get_current_topic_with_subject() -> None:
    facts: dict[str, object] = {
        "topic": {"subject": "work permit germany", "keywords": ["work", "germany"]}
    }
    assert _tracker().get_current_topic(facts) == "work permit germany"


def test_get_current_topic_no_subject() -> None:
    facts: dict[str, object] = {"topic": {"keywords": ["work"]}}
    assert _tracker().get_current_topic(facts) == ""
