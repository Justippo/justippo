"""Unit tests for the stateless conversational RAG endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.chat import ChatTurn, build_contextual_retrieval_query, router
from app.integrations.llm.answer_generation import AnswerModelInfo
from app.services.chat_guidance import build_empty_result_guidance


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    return app


def test_contextual_query_uses_latest_user_turn_for_follow_up() -> None:
    history = [
        ChatTurn(role="user", content="How do I extend a residence permit in Germany?"),
        ChatTurn(role="assistant", content="The relevant EU rules depend on your status."),
    ]

    query = build_contextual_retrieval_query("What documents do I need?", history)

    assert "extend a residence permit in Germany" in query
    assert query.endswith("User answer or follow-up: What documents do I need?")


def test_contextual_query_uses_declarative_answer_to_assistant_question() -> None:
    history = [
        ChatTurn(role="user", content="How do I obtain a residence permit in Germany?"),
        ChatTurn(
            role="assistant",
            content="Are you an EU citizen or a family member of an EU citizen?",
        ),
    ]

    query = build_contextual_retrieval_query(
        "I am a non-EU citizen and would like to work in Germany",
        history,
    )

    assert "obtain a residence permit in Germany" in query
    assert "Assistant clarification: Are you an EU citizen" in query
    assert query.endswith(
        "User answer or follow-up: I am a non-EU citizen and would like to work in Germany"
    )


def test_contextual_query_preserves_goal_for_short_status_answer() -> None:
    history = [
        ChatTurn(role="user", content="How do I get an EU Blue Card for IT work in Germany?"),
        ChatTurn(
            role="assistant",
            content=(
                "You will need proof of qualifications. "
                "Are your IT qualifications recognized in your home country or another EU Member State?"
            ),
        ),
    ]

    query = build_contextual_retrieval_query(
        "yes it is recognized in my home country",
        history,
    )

    assert query.startswith("Original user goal: How do I get an EU Blue Card")
    assert "Assistant clarification: Are your IT qualifications recognized" in query
    assert query.endswith("User answer or follow-up: yes it is recognized in my home country")


def test_contextual_query_keeps_new_topic_independent() -> None:
    history = [ChatTurn(role="user", content="How do I extend a German residence permit?")]

    query = build_contextual_retrieval_query("Explain Spanish remote-work tax rules", history)

    assert query == "Explain Spanish remote-work tax rules"


def test_spain_tax_guidance_is_relevant_and_uses_curated_authority() -> None:
    guidance = build_empty_result_guidance("What are the tax rules in Spain?")

    assert guidance["reason"] == "national_law"
    assert "Spanish tax obligations" in guidance["message"]
    assert "Germany" not in str(guidance)
    assert [option["label"] for option in guidance["options"]] == [
        "Tax residency",
        "Remote employment",
        "Self-employment",
    ]
    assert all(option["action"] == "submit" for option in guidance["options"])
    assert guidance["references"][0]["url"].startswith("https://sede.agenciatributaria.gob.es/")


def test_generic_guidance_preserves_topic_without_unrelated_examples() -> None:
    guidance = build_empty_result_guidance("Recognition of a Romanian diploma")

    assert guidance["reason"] == "no_verified_source"
    assert "Germany" not in str(guidance)
    assert guidance["options"][0]["action"] == "compose"
    assert "query" not in guidance["options"][0]
    assert all("Romanian diploma" in option["query"] for option in guidance["options"][1:])


def test_german_work_permit_guidance_collects_real_status() -> None:
    guidance = build_empty_result_guidance("How do I get a work permit in Germany?")

    assert guidance["reason"] == "national_law"
    assert guidance["options"][0] == {
        "label": "Add my status",
        "action": "compose",
        "prompt": (
            "Describe your citizenship, where you currently live, whether you have "
            "a German job offer, and the type of work or stay you plan."
        ),
    }
    assert guidance["options"][1]["query"].startswith("I am an EU")
    assert guidance["options"][2]["query"].startswith("I am a non-EU")


def test_chat_rejects_more_than_six_history_turns() -> None:
    history = [{"role": "user", "content": f"Question {index}"} for index in range(7)]

    with TestClient(_app()) as client:
        response = client.post(
            "/api/v1/chat/",
            json={"message": "What next?", "history": history},
        )

    assert response.status_code == 422


def test_chat_streams_grounded_answer_model_and_citations() -> None:
    results = [
        {
            "id": "result-1",
            "text": "Directive 2004/38/EC governs residence rights.",
            "rank": 1,
            "source_title": "Directive 2004/38/EC",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32004L0038",
        }
    ]

    async def answer_stream(_prompt: str):
        yield "Next steps:\n"
        yield "1. Confirm your residence category."

    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=results)
    model = AnswerModelInfo(
        provider="public-ai",
        provider_display="Public AI",
        model="swiss-ai/apertus-8b-instruct",
        display_name="Apertus 8B",
    )

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.generate_answer_stream",
            new_callable=MagicMock,
            return_value=answer_stream(""),
        ) as generate,
        patch("app.api.v1.endpoints.search.active_model_info", return_value=model),
        patch(
            "app.api.v1.endpoints.search.record_search_stage",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.v1.endpoints.search.build_search_stage_series",
            return_value={"series": []},
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        settings.APP_ENV = "test"
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "What documents do I need?",
                    "language": "en",
                    "history": [
                        {
                            "role": "user",
                            "content": "How do I extend a residence permit in Germany?",
                        },
                        {
                            "role": "assistant",
                            "content": "First confirm the permit category.",
                        },
                    ],
                },
            )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: result" in response.text
    assert "event: answer_model" in response.text
    assert '"display_name": "Apertus 8B"' in response.text
    assert "event: answer_chunk" in response.text
    assert response.text.endswith("event: done\ndata: [DONE]\n\n")

    retrieval_query = fake_rag.query.await_args.kwargs["q"]
    assert "extend a residence permit in Germany" in retrieval_query
    prompt = generate.call_args.args[0]
    assert "[CONVERSATION_HISTORY_START]" in prompt
    assert "provide concise next steps" in prompt
    assert "[SOURCE 1: Directive 2004/38/EC]" in prompt


def test_chat_streams_journey_state_update_on_first_turn() -> None:
    """Verify NO journey_state_update is emitted (removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={"message": "I want to work in Germany", "language": "en"},
            )

    assert response.status_code == 200
    # No journey events should be emitted per user request
    assert "event: journey_state_update" not in response.text
    # But guidance should fire for Germany work permit
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text
    assert response.text.endswith("event: done\ndata: [DONE]\n\n")


def test_chat_emits_journey_state_on_subsequent_turns() -> None:
    """Verify NO journey_state_update is emitted on subsequent turns (removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "How do I get a residence permit in Germany?",
                    "language": "en",
                    "journey_state": {
                        "journey_type": "work",
                        "jurisdiction": "DE",
                        "citizenship_group": "eu_citizen",
                        "facts": {"has_job_offer": True},
                        "current_step": None,
                        "completed_steps": [],
                        "offered_actions": [],
                        "asked_questions": [],
                        "confirmed_facts": [],
                        "shown_sources": [],
                        "turn_count": 1,
                    },
                },
            )

    assert response.status_code == 200
    # No journey events should be emitted per user request
    assert "event: journey_state_update" not in response.text
    # But guidance should fire for Germany residence permit
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text
    assert response.text.endswith("event: done\ndata: [DONE]\n\n")


def test_chat_streams_guidance_when_retrieval_is_empty() -> None:
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={"message": "What are the tax rules in Spain?", "language": "en"},
            )

    assert response.status_code == 200
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text
    assert "Spanish Tax Agency" in response.text
    assert "Germany" not in response.text
    assert response.text.endswith("event: done\ndata: [DONE]\n\n")


def test_chat_topic_tracking_in_facts() -> None:
    """Verify topic tracking is internal (no journey events emitted per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "How do I get a work permit in Germany?",
                    "language": "en",
                },
            )

    assert response.status_code == 200
    # Topic tracking is internal now (no journey events emitted)
    assert "event: journey_state_update" not in response.text
    # Guidance should fire for Germany work permit
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text


def test_chat_emits_next_step_on_first_turn() -> None:
    """Verify NO next_step event is emitted (journey events removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "How do I work in Germany?",
                    "language": "en",
                },
            )

    assert response.status_code == 200
    assert "event: next_step" not in response.text
    # But guidance should fire
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text


def test_chat_emits_clarification_question_with_options() -> None:
    """Verify NO clarification_question event is emitted (journey events removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "How do I work in Germany?",
                    "language": "en",
                },
            )

    assert response.status_code == 200
    assert "event: clarification_question" not in response.text
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text


def test_chat_emits_document_checklist_for_relevant_step() -> None:
    """Verify NO document_checklist event is emitted (journey events removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "How do I work in Germany?",
                    "language": "en",
                },
            )

    assert response.status_code == 200
    assert "event: document_checklist" not in response.text
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text


def test_chat_emits_action_plan_with_all_steps() -> None:
    """Verify NO action_plan event is emitted (journey events removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "How do I work in Germany?",
                    "language": "en",
                },
            )

    assert response.status_code == 200
    assert "event: action_plan" not in response.text
    assert "event: guidance" in response.text
    assert '"reason": "national_law"' in response.text


def test_chat_structured_events_not_emitted_without_journey_type() -> None:
    """Verify structured events are NOT emitted (journey events removed per user request)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "What is the weather in Paris?",
                    "language": "en",
                },
            )

    assert response.status_code == 200
    assert "event: next_step" not in response.text
    assert "event: clarification_question" not in response.text
    assert "event: document_checklist" not in response.text
    assert "event: action_plan" not in response.text
    assert "event: journey_state_update" not in response.text


def test_chat_topic_persists_on_subsequent_turn() -> None:
    """Verify topic tracking persists with existing journey_state (no journey events)."""
    fake_rag = MagicMock()
    fake_rag.query = AsyncMock(return_value=[])

    with (
        patch("app.api.v1.endpoints.chat.HindsightRAGService", return_value=fake_rag),
        patch("app.api.v1.endpoints.search.apertus_enabled", return_value=True),
        patch(
            "app.api.v1.endpoints.search.flush_search_stage_batch",
            new_callable=AsyncMock,
        ),
        patch("app.api.v1.endpoints.search.settings") as settings,
    ):
        settings.SSE_CHUNK_DELAY_MS = 0
        with TestClient(_app()) as client:
            response = client.post(
                "/api/v1/chat/",
                json={
                    "message": "What about studying in France?",
                    "language": "en",
                    "journey_state": {
                        "journey_type": None,
                        "jurisdiction": None,
                        "citizenship_group": None,
                        "facts": {
                            "topic": {
                                "subject": "work permit germany",
                                "keywords": ["work", "permit", "germany"],
                                "since_turn": 1,
                            },
                            "topics_history": [],
                            "last_user_queries": ["How do I get a work permit in Germany?"],
                            "_last_topic_shift": False,
                        },
                        "current_step": None,
                        "completed_steps": [],
                        "offered_actions": [],
                        "asked_questions": [],
                        "confirmed_facts": [],
                        "shown_sources": [],
                        "turn_count": 2,
                    },
                },
            )

    assert response.status_code == 200
    assert '"topic"' not in response.text  # No journey_state_update events
