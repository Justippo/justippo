from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.memory_repository import MemoryRepository


def _session_row(
    *,
    sid: str = "sess-1",
    language: str = "en",
    journey_type: str | None = "work",
    citizenship_group: str | None = "eu",
    jurisdiction: str | None = "DE",
    message_count: int = 3,
    created_at: str = "2026-01-01T00:00:00+00:00",
    updated_at: str = "2026-01-02T00:00:00+00:00",
    is_active: int = 1,
) -> dict[str, object]:
    return {
        "id": sid,
        "language": language,
        "journey_type": journey_type,
        "citizenship_group": citizenship_group,
        "jurisdiction": jurisdiction,
        "message_count": message_count,
        "created_at": created_at,
        "updated_at": updated_at,
        "is_active": is_active,
    }


def _message_row(
    *,
    mid: str = "msg-1",
    session_id: str = "sess-1",
    role: str = "user",
    content_summary: str = "test query",
    content_length: int = 10,
    has_citations: int = 0,
    grounding_verdict: str | None = None,
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": mid,
        "session_id": session_id,
        "role": role,
        "content_summary": content_summary,
        "content_length": content_length,
        "has_citations": has_citations,
        "grounding_verdict": grounding_verdict,
        "created_at": created_at,
    }


def _investigation_row(
    *,
    iid: str = "inv-1",
    session_id: str | None = "sess-1",
    topic: str = "work permit",
    language: str = "en",
    summary: str = "",
    doc_ids: str = '["doc-1"]',
    entity_mentions: str = '["Germany"]',
    confidence: float | None = 0.85,
    created_at: str = "2026-01-01T00:00:00+00:00",
    updated_at: str = "2026-01-02T00:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": iid,
        "session_id": session_id,
        "topic": topic,
        "language": language,
        "summary": summary,
        "doc_ids": doc_ids,
        "entity_mentions": entity_mentions,
        "confidence": confidence,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# ── No-db path (graceful degradation) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session_no_db_returns_none() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.create_session()
    assert result is None


@pytest.mark.asyncio
async def test_get_session_no_db_returns_none() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.get_session("sess-1")
    assert result is None


@pytest.mark.asyncio
async def test_list_active_sessions_no_db_returns_empty() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.list_active_sessions()
    assert result == []


@pytest.mark.asyncio
async def test_update_session_no_db_returns_false() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.update_session("sess-1")
    assert result is False


@pytest.mark.asyncio
async def test_close_session_no_db_returns_false() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.close_session("sess-1")
    assert result is False


@pytest.mark.asyncio
async def test_append_message_no_db_returns_none() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.append_message(session_id="sess-1", role="user")
    assert result is None


@pytest.mark.asyncio
async def test_get_session_messages_no_db_returns_empty() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.get_session_messages("sess-1")
    assert result == []


@pytest.mark.asyncio
async def test_create_investigation_no_db_returns_none() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.create_investigation(topic="tax")
    assert result is None


@pytest.mark.asyncio
async def test_update_investigation_no_db_returns_false() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.update_investigation("inv-1")
    assert result is False


@pytest.mark.asyncio
async def test_search_investigations_no_db_returns_empty() -> None:
    repo = MemoryRepository(db=None)
    result = await repo.search_investigations(topic="work")
    assert result == []


# ── Session CRUD ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session_inserts_and_returns_record() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.create_session(
        language="de",
        journey_type="work",
        citizenship_group="non-eu",
        jurisdiction="DE",
    )

    assert result is not None
    assert result.language == "de"
    assert result.journey_type == "work"
    assert result.citizenship_group == "non-eu"
    assert result.jurisdiction == "DE"
    assert result.message_count == 0
    assert result.is_active is True
    db.execute.assert_awaited_once()
    sql = db.execute.await_args.args[0]
    assert "INSERT INTO chat_sessions" in sql


@pytest.mark.asyncio
async def test_create_session_fails_returns_none() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=False)
    repo = MemoryRepository(db)

    result = await repo.create_session()
    assert result is None


@pytest.mark.asyncio
async def test_get_session_returns_record() -> None:
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value=_session_row())
    repo = MemoryRepository(db)

    result = await repo.get_session("sess-1")
    assert result is not None
    assert result.id == "sess-1"
    assert result.journey_type == "work"
    assert result.message_count == 3


@pytest.mark.asyncio
async def test_get_session_not_found_returns_none() -> None:
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value=None)
    repo = MemoryRepository(db)

    result = await repo.get_session("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_active_sessions_returns_records() -> None:
    db = MagicMock()
    rows = [
        _session_row(sid="sess-1", message_count=5),
        _session_row(sid="sess-2", message_count=2),
    ]
    db.fetch_all = AsyncMock(return_value=rows)
    repo = MemoryRepository(db)

    results = await repo.list_active_sessions(limit=5)
    assert len(results) == 2
    assert results[0].id == "sess-1"
    assert results[0].message_count == 5
    assert results[1].id == "sess-2"
    db.fetch_all.assert_awaited_once()
    sql = db.fetch_all.await_args.args[0]
    assert "is_active = 1" in sql
    assert "LIMIT ?" in sql


@pytest.mark.asyncio
async def test_update_session_updates_fields() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.update_session(
        "sess-1", journey_type="study", citizenship_group="non-eu", jurisdiction="FR"
    )
    assert result is True
    db.execute.assert_awaited_once()
    sql, params = db.execute.await_args.args
    assert "UPDATE chat_sessions" in sql
    assert "journey_type = ?" in sql
    assert "citizenship_group = ?" in sql
    assert "jurisdiction = ?" in sql
    assert "sess-1" in params


@pytest.mark.asyncio
async def test_update_session_no_changes_only_timestamp() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.update_session("sess-1")
    assert result is True
    sql = db.execute.await_args.args[0]
    assert "updated_at = ?" in sql
    assert "journey_type" not in sql


@pytest.mark.asyncio
async def test_close_session_sets_inactive() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.close_session("sess-1")
    assert result is True
    sql = db.execute.await_args.args[0]
    assert "is_active = 0" in sql
    assert "WHERE id = ?" in sql


# ── Messages ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_message_inserts_and_updates_count() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.append_message(
        session_id="sess-1",
        role="assistant",
        content_summary="This is a test response",
        has_citations=True,
        grounding_verdict='{"verdict": "pass"}',
    )

    assert result is not None
    assert result.session_id == "sess-1"
    assert result.role == "assistant"
    assert result.has_citations is True
    assert result.grounding_verdict == '{"verdict": "pass"}'
    assert result.content_length == len("This is a test response")
    assert db.execute.await_count == 2  # INSERT + UPDATE message_count
    insert_sql = db.execute.await_args_list[0].args[0]
    assert "INSERT INTO session_messages" in insert_sql
    update_sql = db.execute.await_args_list[1].args[0]
    assert "UPDATE chat_sessions SET message_count = message_count + 1" in update_sql


@pytest.mark.asyncio
async def test_append_message_truncates_long_summary() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    long_text = "x" * 1000
    result = await repo.append_message(
        session_id="sess-1",
        role="user",
        content_summary=long_text,
    )

    assert result is not None
    assert len(result.content_summary) == 500
    assert result.content_length == 1000


@pytest.mark.asyncio
async def test_append_message_no_citations() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.append_message(
        session_id="sess-1",
        role="user",
        content_summary="hello",
        has_citations=False,
    )

    assert result is not None
    assert result.has_citations is False
    # Second call params: INSERT sets has_citations=0
    insert_params = db.execute.await_args_list[0].args[1]
    assert insert_params[5] == 0  # has_citations column index


@pytest.mark.asyncio
async def test_append_message_insert_fails_does_not_update_count() -> None:
    db = MagicMock()
    # First call (INSERT) fails, second call should NOT be made
    db.execute = AsyncMock(side_effect=[False])
    repo = MemoryRepository(db)

    result = await repo.append_message(session_id="sess-1", role="user")
    assert result is None
    assert db.execute.await_count == 1  # only the INSERT, no UPDATE


@pytest.mark.asyncio
async def test_get_session_messages_returns_records() -> None:
    db = MagicMock()
    rows = [
        _message_row(mid="msg-1", role="user", created_at="2026-01-01T00:00:00+00:00"),
        _message_row(mid="msg-2", role="assistant", created_at="2026-01-01T00:00:01+00:00"),
    ]
    db.fetch_all = AsyncMock(return_value=rows)
    repo = MemoryRepository(db)

    results = await repo.get_session_messages("sess-1", limit=10)
    assert len(results) == 2
    assert results[0].role == "user"
    assert results[1].role == "assistant"
    sql = db.fetch_all.await_args.args[0]
    assert "ORDER BY created_at ASC" in sql


# ── Investigations ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_investigation_inserts_and_returns() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.create_investigation(
        topic="Work permit requirements in Germany",
        language="en",
        session_id="sess-1",
        doc_ids=["doc-1", "doc-2"],
        entity_mentions=["Germany", "work permit"],
    )

    assert result is not None
    assert result.topic == "Work permit requirements in Germany"
    assert result.session_id == "sess-1"
    assert result.doc_ids == ["doc-1", "doc-2"]
    assert result.entity_mentions == ["Germany", "work permit"]
    assert result.confidence is None  # default
    db.execute.assert_awaited_once()
    sql = db.execute.await_args.args[0]
    assert "INSERT INTO user_investigations" in sql


@pytest.mark.asyncio
async def test_create_investigation_truncates_long_topic() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    long_topic = "x" * 1000
    result = await repo.create_investigation(topic=long_topic)
    assert result is not None
    assert len(result.topic) == 500


@pytest.mark.asyncio
async def test_create_investigation_defaults_empty_lists() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.create_investigation(topic="tax")
    assert result is not None
    assert result.doc_ids == []
    assert result.entity_mentions == []


@pytest.mark.asyncio
async def test_update_investigation_updates_fields() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.update_investigation(
        "inv-1",
        summary="Updated summary",
        doc_ids=["doc-3"],
        entity_mentions=["France"],
        confidence=0.95,
    )
    assert result is True
    sql = db.execute.await_args.args[0]
    assert "UPDATE user_investigations" in sql
    assert "summary = ?" in sql
    assert "doc_ids = ?" in sql
    assert "entity_mentions = ?" in sql
    assert "confidence = ?" in sql


@pytest.mark.asyncio
async def test_update_investigation_partial_summary_only() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.update_investigation("inv-1", summary="Only summary")
    assert result is True
    sql = db.execute.await_args.args[0]
    assert "summary = ?" in sql
    assert "doc_ids" not in sql
    assert "entity_mentions" not in sql
    assert "confidence" not in sql


@pytest.mark.asyncio
async def test_update_investigation_partial_doc_ids_only() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = MemoryRepository(db)

    result = await repo.update_investigation("inv-1", doc_ids=["doc-x"])
    assert result is True
    sql = db.execute.await_args.args[0]
    assert "updated_at = ?" in sql
    assert "doc_ids = ?" in sql
    assert "summary" not in sql
    assert "entity_mentions" not in sql
    assert "confidence" not in sql


@pytest.mark.asyncio
async def test_search_investigations_returns_matches() -> None:
    db = MagicMock()
    rows = [
        _investigation_row(iid="inv-1", topic="work permit"),
        _investigation_row(iid="inv-2", topic="work visa"),
    ]
    db.fetch_all = AsyncMock(return_value=rows)
    repo = MemoryRepository(db)

    results = await repo.search_investigations(topic="work", limit=5)
    assert len(results) == 2
    assert results[0].topic == "work permit"
    sql = db.fetch_all.await_args.args[0]
    assert "LOWER(topic) LIKE ?" in sql


@pytest.mark.asyncio
async def test_search_investigations_empty_results() -> None:
    db = MagicMock()
    db.fetch_all = AsyncMock(return_value=[])
    repo = MemoryRepository(db)

    results = await repo.search_investigations(topic="nonexistent")
    assert results == []


# ── Row mapping edge cases ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_session_handles_nullable_fields_as_none() -> None:
    db = MagicMock()
    row = _session_row(journey_type=None, citizenship_group=None, jurisdiction=None)
    db.fetch_one = AsyncMock(return_value=row)
    repo = MemoryRepository(db)

    result = await repo.get_session("sess-1")
    assert result is not None
    assert result.journey_type is None
    assert result.citizenship_group is None
    assert result.jurisdiction is None


@pytest.mark.asyncio
async def test_get_session_missing_keys_defaults() -> None:
    db = MagicMock()
    # Row that exists (truthy) but has missing keys
    db.fetch_one = AsyncMock(return_value={"id": ""})
    repo = MemoryRepository(db)

    result = await repo.get_session("sess-1")
    assert result is not None
    assert result.id == ""
    assert result.language == "en"
    assert result.is_active is True


@pytest.mark.asyncio
async def test_get_session_messages_handles_grounding_verdict() -> None:
    db = MagicMock()
    row = _message_row(grounding_verdict='{"verdict":"partial"}')
    db.fetch_all = AsyncMock(return_value=[row])
    repo = MemoryRepository(db)

    results = await repo.get_session_messages("sess-1")
    assert len(results) == 1
    assert results[0].grounding_verdict == '{"verdict":"partial"}'


@pytest.mark.asyncio
async def test_investigation_parses_empty_json_arrays() -> None:
    db = MagicMock()
    row = _investigation_row(doc_ids="[]", entity_mentions="[]")
    db.fetch_all = AsyncMock(return_value=[row])
    repo = MemoryRepository(db)

    results = await repo.search_investigations(topic="x")
    assert len(results) == 1
    assert results[0].doc_ids == []
    assert results[0].entity_mentions == []


@pytest.mark.asyncio
async def test_investigation_handles_non_string_json_gracefully() -> None:
    db = MagicMock()
    row = _investigation_row(doc_ids='["doc-1"]', entity_mentions='["ent-1"]')
    db.fetch_all = AsyncMock(return_value=[row])
    repo = MemoryRepository(db)

    results = await repo.search_investigations(topic="x")
    assert len(results) == 1
    assert results[0].doc_ids == ["doc-1"]
    assert results[0].entity_mentions == ["ent-1"]
