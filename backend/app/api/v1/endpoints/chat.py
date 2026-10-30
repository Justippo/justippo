# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stateless conversational RAG over the verified public corpus."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.v1.endpoints.search import _request_id, _sse_generator, _sse_response
from app.core.config import settings
from app.core.sse import sse_frame
from app.db.d1_client import D1Client
from app.integrations.llm.answer_generation import generate_greeting_stream
from app.repositories.glossary_repo import GlossaryRepo
from app.repositories.memory_repository import MemoryRepository
from app.services.chat_guidance import build_empty_result_guidance
from app.services.rag_service import HindsightRAGService
from app.services.session_topic import SessionTopicTracker

router = APIRouter()

_FOLLOW_UP_MARKERS = (
    "what documents",
    "which documents",
    "what do i need",
    "what should i do",
    "what next",
    "how do i",
    "how about",
    "does that",
    "is that",
    "can i",
    "and what",
)

_GREETING_WORDS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "greetings",
        "howdy",
        "sup",
        "yo",
    }
)

_GREETING_PHRASES = (
    "good morning",
    "good afternoon",
    "good evening",
    "good day",
    "what's up",
    "whats up",
    "nice to meet",
    "good to see",
    "just saying hi",
    "just hi",
)

_PROCEDURAL_QUERY_WORDS = frozenset(
    {
        "what",
        "why",
        "when",
        "where",
        "who",
        "which",
        "do",
        "does",
        "can",
        "could",
        "will",
        "would",
        "should",
    }
)

_LEGAL_KEYWORDS = frozenset(
    {
        "visa",
        "permit",
        "residence",
        "citizen",
        "passport",
        "immigration",
        "diploma",
        "degree",
        "tax",
        "insurance",
        "contract",
        "application",
        "registration",
        "certificate",
    }
)


def is_greeting(message: str) -> bool:
    """Detect if the message is purely a greeting or small talk.

    Heuristic: starts with a greeting word (or ``hell``-typo variant),
    ≤5 words, no question marks, no question words, no legal keywords.
    Multi-word greeting phrases bypass the question-word check.
    """
    text = message.strip().lower()
    if not text:
        return False

    words = text.split()
    if len(words) > 5:
        return False

    if "?" in text:
        return False

    # Known greeting phrases bypass further checks
    lowered = text
    for phrase in _GREETING_PHRASES:
        if lowered.startswith(phrase):
            return True

    first = words[0]
    if (
        first not in _GREETING_WORDS
        and not first.startswith("hell")
        and first not in ("how", "how's")
    ):
        return False

    return not (
        any(kw in words for kw in _LEGAL_KEYWORDS)
        or any(w in _PROCEDURAL_QUERY_WORDS for w in words[1:])
    )


class ChatTurn(BaseModel):
    """A bounded prior turn supplied from browser memory."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation content must not be blank")
        return normalized


class JourneyState(BaseModel):
    """Structured ephemeral journey state submitted with each request."""

    journey_type: str | None = None
    jurisdiction: str | None = None
    citizenship_group: str | None = None
    facts: dict[str, object] = Field(default_factory=dict)
    current_step: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    offered_actions: list[str] = Field(default_factory=list)
    asked_questions: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    shown_sources: list[str] = Field(default_factory=list)
    turn_count: int = Field(default=0, ge=0)


class ChatRequest(BaseModel):
    """A stateless chat request; conversation history is never persisted."""

    message: str = Field(min_length=1, max_length=2_000)
    language: Literal["en", "de", "fr"] = "en"
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    top_k: int = Field(default=5, ge=1, le=10)
    journey_state: JourneyState | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


def build_contextual_retrieval_query(message: str, history: list[ChatTurn]) -> str:
    """Resolve follow-ups and clarification answers without an extra LLM call."""
    normalized = message.strip()
    lowered = normalized.lower()
    latest_assistant = next(
        (turn.content for turn in reversed(history) if turn.role == "assistant"),
        "",
    )
    is_follow_up = any(marker in lowered for marker in _FOLLOW_UP_MARKERS) or (
        bool(history) and history[-1].role == "assistant" and "?" in latest_assistant
    )
    if not is_follow_up:
        return normalized

    previous_question = next(
        (turn.content for turn in reversed(history) if turn.role == "user"),
        "",
    )
    if not previous_question:
        return normalized

    assistant_questions = re.findall(r"[^.!?\n]{1,500}\?", latest_assistant)
    clarification_question = assistant_questions[-1].strip() if assistant_questions else ""
    context = [f"Original user goal: {previous_question[:1_500]}"]
    if clarification_question:
        context.append(f"Assistant clarification: {clarification_question}")
    context.append(f"User answer or follow-up: {normalized}")
    return "\n".join(context)


@router.post(
    "/",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """Stream grounded results, runtime model metadata, answer chunks, and `done`."""
    history = [turn.model_dump() for turn in body.history]

    # ── Greeting detection — bypass RAG entirely for greetings ───────────
    if not history and is_greeting(body.message):

        async def _greeting_only() -> AsyncGenerator[str, None]:
            yield sse_frame("results_complete", "[RESULTS_READY]")
            tokens: list[str] = []
            async for token in generate_greeting_stream(body.message):
                tokens.append(token)
                yield sse_frame("answer_chunk", {"text": token})
            if not tokens:
                yield sse_frame(
                    "answer_chunk",
                    {"text": "Hi there! How can I help you with EU documents today?"},
                )
            yield sse_frame("done", "[DONE]")

        return _sse_response(_greeting_only(), _request_id(request))

    # ── Session topic tracking (every turn) ──────────────────────────────
    is_first_turn_topic = body.journey_state is None or not body.journey_state.facts.get("topic")
    topic_tracker = SessionTopicTracker()
    facts = dict(body.journey_state.facts) if body.journey_state is not None else {}
    facts = topic_tracker.update_topic(body.message, facts, body.language, is_first_turn_topic)
    topic_query = topic_tracker.get_retrieval_context(body.message, facts)

    retrieval_query = build_contextual_retrieval_query(topic_query, body.history)
    rag = HindsightRAGService(glossary_repo=GlossaryRepo(D1Client.from_scope(request.scope)))
    request_id = _request_id(request)

    from app.integrations.posthog import capture_event  # noqa: PLC0415

    await capture_event(
        "chat_stream_started",
        distinct_id=getattr(request.state, "posthog_distinct_id", ""),
        properties={
            "language": body.language,
            "top_k": body.top_k,
            "history_length": len(body.history),
            "is_follow_up": bool(body.history),
        },
        session_id=getattr(request.state, "posthog_session_id", None),
    )

    # ── Cross-session memory (Linus five-layer pillar, DEC-0028) ──────────
    # Feature-flagged by SESSION_MEMORY_ENABLED. Creates/opens D1-backed
    # session, appends user message, stores investigation metadata.
    memory_repo: MemoryRepository | None = None
    session_id: str | None = None
    if settings.SESSION_MEMORY_ENABLED:
        memory_repo = MemoryRepository(D1Client.from_scope(request.scope))
        session_record = await memory_repo.create_session(
            language=body.language,
            journey_type=None,
        )
        if session_record is not None:
            session_id = session_record.id
            await memory_repo.append_message(
                session_id=session_id,
                role="user",
                content_summary=body.message[:500],
            )

    # No journey events are emitted (v3.0 spec: "No journey events emitted per
    # user request."). The journey-classification + SSE-builder scaffold that
    # populated them was fully removed; topic tracking above is retained.

    async def _wrapped_generator() -> AsyncGenerator[str, None]:
        # Pre-compute guidance — if a marker matches, we use curated answer
        # and skip RAG/LLM. No journey events emitted per user request.
        guidance_msg = build_empty_result_guidance(body.message)
        guidance_matched = guidance_msg["reason"] not in ("no_verified_source", "followup_answer")

        # If guidance matched, use curated answer — skip RAG + LLM entirely
        if guidance_matched:
            yield sse_frame("results_complete", "[RESULTS_READY]")
            yield sse_frame("guidance", guidance_msg)
            msg = guidance_msg["message"]
            for i in range(0, len(msg), 80):
                yield sse_frame("answer_chunk", {"text": msg[i : i + 80]})
            yield sse_frame("done", "[DONE]")
            return

        # Normal flow: RAG + LLM (no journey events)
        answer_parts: list[str] = []
        async for frame in _sse_generator(
            q=body.message,
            retrieval_q=retrieval_query,
            top_k=body.top_k,
            rag=rag,
            request=request,
            lang=body.language,
            conversation_history=history,
            guidance=True,
            emit_model=True,
            request_id=request_id,
        ):
            if frame.startswith("event: answer_chunk"):
                import json as _json  # noqa: PLC0415

                try:
                    data_line = [line for line in frame.splitlines() if line.startswith("data: ")][
                        0
                    ]
                    payload = _json.loads(data_line[6:])
                    answer_parts.append(str(payload.get("text", "")))
                except (IndexError, _json.JSONDecodeError):
                    pass
            yield frame

        if memory_repo is not None and session_id is not None and answer_parts:
            full_answer = "".join(answer_parts)
            await memory_repo.append_message(
                session_id=session_id,
                role="assistant",
                content_summary=full_answer[:500],
                has_citations=True,
                grounding_verdict=None,
            )

    return _sse_response(_wrapped_generator(), request_id)
