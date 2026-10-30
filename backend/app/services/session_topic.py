"""
Session Topic Tracker — Topic detection and coherence for multi-turn chat.

Pipeline position: Chat endpoint (every turn) before retrieval query construction.
Tracks what the conversation is about to ensure the system maintains coherent
context across turns, even when the user switches topics.

The tracker works with any topic — not just the guided journey playbooks.
It is entirely deterministic: stopword stripping, content word extraction,
and Jaccard similarity on word sets.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Maximum number of user queries stored for overlap computation
_MAX_USER_QUERIES = 5

# Jaccard similarity threshold below which a topic shift is detected
_TOPIC_SHIFT_THRESHOLD = 0.25

# Minimum number of content words in the current query to try topic detection
_MIN_CONTENT_WORDS = 3

# Precompiled stopword patterns
_STOPWORDS: set[str] = {
    # English
    "a",
    "an",
    "the",
    "is",
    "it",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "with",
    "for",
    "and",
    "or",
    "but",
    "so",
    "if",
    "not",
    "up",
    "down",
    "no",
    "yes",
    "do",
    "did",
    "does",
    "was",
    "were",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "be",
    "can",
    "could",
    "shall",
    "should",
    "will",
    "would",
    "may",
    "might",
    "i",
    "me",
    "my",
    "we",
    "our",
    "us",
    "you",
    "your",
    "he",
    "she",
    "his",
    "her",
    "its",
    "they",
    "them",
    "their",
    "what",
    "which",
    "who",
    "whom",
    "when",
    "where",
    "why",
    "how",
    "that",
    "this",
    "these",
    "those",
    "am",
    "are",
    "get",
    "got",
    "make",
    "want",
    "like",
    "there",
    "here",
    "just",
    # German
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einen",
    "einer",
    "einem",
    "eines",
    "ist",
    "sind",
    "sein",
    "seine",
    "ihre",
    "ihr",
    "ihres",
    "ihren",
    "ihrem",
    "unser",
    "unsere",
    "euer",
    "eure",
    "auf",
    "aus",
    "bei",
    "mit",
    "nach",
    "von",
    "zu",
    "über",
    "unter",
    "vor",
    "zwischen",
    "und",
    "oder",
    "aber",
    "denn",
    "doch",
    "nicht",
    "ja",
    "nein",
    "mal",
    "auch",
    "noch",
    "schon",
    "erst",
    "nur",
    "sehr",
    "viel",
    "wenig",
    "kann",
    "können",
    "musste",
    "muss",
    "soll",
    "sollen",
    "darf",
    "durfen",
    "wird",
    "werden",
    "wurde",
    "hatte",
    "hätte",
    "hätten",
    "ich",
    "du",
    "er",
    "sie",
    "es",
    "wir",
    "mir",
    "mich",
    "dir",
    "dich",
    "sich",
    "uns",
    "euch",
    "ihnen",
    "als",
    "wie",
    "weil",
    "dass",
    "wenn",
    "ob",
    "zum",
    "zur",
    "beim",
    "vom",
    "ins",
    "ums",
    "durch",
    "gegen",
    "ohne",
    "um",
    "bis",
    # French
    "le",
    "la",
    "les",
    "un",
    "une",
    "de",
    "dans",
    "sur",
    "pour",
    "par",
    "avec",
    "sans",
    "chez",
    "entre",
    "depuis",
    "pendant",
    "avant",
    "après",
    "est",
    "suis",
    "sommes",
    "etez",
    "sont",
    "fait",
    "faire",
    "peut",
    "peuvent",
    "doit",
    "doivent",
    "veut",
    "veulent",
    "sait",
    "savent",
    "il",
    "elle",
    "ils",
    "elles",
    "nous",
    "vous",
    "lui",
    "eux",
    "celles",
    "ceux",
    "cela",
    "cet",
    "cette",
    "ces",
    "qui",
    "que",
    "quoi",
    "dont",
    "ou",
    "donc",
    "ni",
    "car",
    "même",
    "tres",
    "aussi",
    "trop",
    "assez",
    "peu",
    "plein",
    "déjà",
    "encore",
    "toujours",
    "jamais",
    "parfois",
    "alors",
    "puis",
    "si",
    "non",
    "oui",
    "je",
    "tu",
    "te",
    "se",
    "leur",
    "leurs",
    "au",
    "aux",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "mon",
    "ton",
    "son",
    "mes",
    "tes",
    "ses",
    "nos",
    "vos",
    "ce",
    "en",
    "y",
    "ne",
    "pas",
    "plus",
}

# Noisewords that should not form a topic on their own
_NOISEWORDS: set[str] = {
    "question",
    "want",
    "look",
    "regarding",
    "regards",
    "actually",
    "basically",
    "essentially",
    "morally",
    "personally",
    "generally",
    "please",
    "thanks",
    "hello",
    "hi",
}


def _extract_content_words(text: str) -> list[str]:
    """Extract meaningful content words from text, removing stopwords and punctuation."""
    if not text:
        return []

    lowered = text.lower()
    # Remove common punctuation
    lowered = re.sub(r"[^a-z0-9äöüßéèêëàâîïôùûç\s]", " ", lowered)
    # Split into words
    words = lowered.split()

    return [
        w
        for w in words
        if len(w) > 1 and w not in _STOPWORDS and w not in _NOISEWORDS and not w.isnumeric()
    ]


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _infer_topic_subject(content_words: list[str], max_words: int = 6) -> str:
    """Infer a short subject string from content words."""
    if not content_words:
        return ""
    # Take the first few (most significant) words
    subject = " ".join(content_words[:max_words]).strip()
    if len(subject) > 120:
        subject = subject[:117] + "..."
    return subject


class SessionTopicTracker:
    """
    Topic tracker for chat session coherence.

    Tracks the current topic of a multi-turn conversation, detects topic shifts
    by Jaccard similarity on content words, and provides context for RAG retrieval.

    All state is stored in the session's JourneyState facts to survive stateless requests.
    """

    def update_topic(
        self,
        message: str,
        facts: dict[str, object] | None,
        language: str = "en",
        is_first_turn: bool = False,
    ) -> dict[str, object]:
        """
        Process a user message and update topic state.

        Args:
            message: The user's current chat message.
            facts: Current facts dict from JourneyState (or None).
            language: Language code (en/de/fr).
            is_first_turn: Whether this is the first turn of the conversation.

        Returns:
            Updated facts dict with topic fields set.
        """
        if facts is None:
            facts = {}

        content_words = _extract_content_words(message)

        # Decode topic fields from facts
        current_topic_raw = facts.get("topic")
        current_topic = current_topic_raw if isinstance(current_topic_raw, dict) else None
        topics_history_raw = facts.get("topics_history")
        topics_history = topics_history_raw if isinstance(topics_history_raw, list) else []

        # First turn: always set initial topic
        if is_first_turn or current_topic is None:
            current_subject = _infer_topic_subject(content_words)
            new_topic = {
                "subject": current_subject,
                "keywords": content_words[:12],
                "since_turn": 1 if is_first_turn else ((current_topic or {}).get("since_turn", 1)),
            }
            facts["topic"] = new_topic
            facts["topics_history"] = topics_history
            facts["last_user_queries"] = [(message or "")[:500]]
            return facts

        # Normal turn: check for topic shift
        keyword_set = set(content_words)
        topic_keyword_set = set(current_topic.get("keywords", []))

        # Get last queries for additional context
        last_queries = facts.get("last_user_queries", [])
        if not isinstance(last_queries, list):
            last_queries = []

        # Determine if we should process this turn for topic detection:
        # only if there are enough content words
        if len(content_words) >= _MIN_CONTENT_WORDS:
            similarity = _jaccard_similarity(keyword_set, topic_keyword_set)

            is_topic_shift = similarity < _TOPIC_SHIFT_THRESHOLD

            if is_topic_shift:
                # Store old topic in history
                new_history = [*topics_history, current_topic]
                # Limit history to last 10 topics
                if len(new_history) > 10:
                    new_history = new_history[-10:]

                new_subject = _infer_topic_subject(content_words)
                new_topic = {
                    "subject": new_subject,
                    "keywords": content_words[:12],
                    "since_turn": len(last_queries) + 2,  # approximate turn number
                }
                facts["topic"] = new_topic
                facts["topics_history"] = new_history
                facts["_last_topic_shift"] = True
        else:
            # Too few content words — keep current topic, no shift detected
            facts["_last_topic_shift"] = False

        # Update last user queries
        updated_queries = list(last_queries)
        updated_queries.append((message or "")[:500])
        if len(updated_queries) > _MAX_USER_QUERIES:
            updated_queries = updated_queries[-_MAX_USER_QUERIES:]
        facts["last_user_queries"] = updated_queries

        if "_last_topic_shift" not in facts:
            facts["_last_topic_shift"] = False

        return facts

    def get_retrieval_context(self, current_query: str, facts: dict[str, object] | None) -> str:
        """
        Build a retrieval context prefix for the current query.

        This prefix is prepended to the user's message when constructing the
        RAG retrieval query. It ensures that important context (current topic)
        is not lost when the RAG engine processes the query in isolation.
        """
        if not facts:
            return current_query

        topic_raw = facts.get("topic", None)
        topic = topic_raw if isinstance(topic_raw, dict) else None

        last_shift = facts.get("_last_topic_shift", False)

        if topic is None:
            return current_query

        subject = topic.get("subject", "")
        keywords = topic.get("keywords", [])

        if not subject and not keywords:
            return current_query

        if last_shift and isinstance(last_shift, bool) and last_shift:
            return f"New topic: {subject}. User request: {current_query}"

        # No shift — lightly prefix with topic for RAG context
        return f"Current topic: {subject}. User question: {current_query}"

    def clear_topic(self, facts: dict[str, object] | None) -> dict[str, object]:
        """Reset all topic tracking fields."""
        if facts is None:
            facts = {}
        facts.pop("topic", None)
        facts.pop("topics_history", None)
        facts.pop("last_user_queries", None)
        facts.pop("_last_topic_shift", None)
        return facts

    def get_current_topic(self, facts: dict[str, object] | None) -> str:
        """Return the subject of the current tracked topic, empty string if none."""
        if not facts:
            return ""
        topic_raw = facts.get("topic", None)
        if not isinstance(topic_raw, dict):
            return ""
        return topic_raw.get("subject", "") or ""
