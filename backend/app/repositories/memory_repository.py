# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Memory Repository — D1 data access for cross-session memory pillar.

Linus five-layer memory adaptation:
    Intra-step  → conversation_history param (generator-in-memory)
    Session     → chat_sessions table (D1)
    Episodic    → session_messages table (D1)
    Investigation → user_investigations table (D1)
    Semantic    → Vectorize via HindsightRAGService (existing)

Pattern follows glossary_repo.py exactly:
    D1Client-based, graceful no-op when unavailable, async,
    all methods return empty on error, no new dependencies.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    import aiosqlite

    from app.db.d1_client import D1Client

logger = logging.getLogger(__name__)


@dataclass
class SessionRecord:
    id: str = ""
    language: str = "en"
    journey_type: str | None = None
    citizenship_group: str | None = None
    jurisdiction: str | None = None
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    is_active: bool = True


@dataclass
class MessageRecord:
    id: str = ""
    session_id: str = ""
    role: str = ""
    content_summary: str = ""
    content_length: int = 0
    has_citations: bool = False
    grounding_verdict: str | None = None
    created_at: str = ""


@dataclass
class InvestigationRecord:
    id: str = ""
    session_id: str | None = None
    topic: str = ""
    language: str = "en"
    summary: str = ""
    doc_ids: list[str] = field(default_factory=list)
    entity_mentions: list[str] = field(default_factory=list)
    confidence: float | None = None
    created_at: str = ""
    updated_at: str = ""


class MemoryRepository:
    """Data-access layer for cross-session memory tables (D1 / SQLite).

    All methods are async, gracefully degrade when DB is unavailable,
    and follow the same pattern as GlossaryRepo.
    """

    def __init__(self, db: D1Client | aiosqlite.Connection | None = None) -> None:
        self._db = db

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(
        self,
        language: str = "en",
        journey_type: str | None = None,
        citizenship_group: str | None = None,
        jurisdiction: str | None = None,
    ) -> SessionRecord | None:
        if self._db is None:
            logger.debug("create_session skipped — db unavailable")
            return None

        now = datetime.now(UTC).isoformat()
        record = SessionRecord(
            id=str(uuid4()),
            language=language,
            journey_type=journey_type,
            citizenship_group=citizenship_group,
            jurisdiction=jurisdiction,
            created_at=now,
            updated_at=now,
        )
        ok = await self._db.execute(
            """INSERT INTO chat_sessions
               (id, language, journey_type, citizenship_group, jurisdiction,
                message_count, created_at, updated_at, is_active)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1)""",
            [
                record.id,
                record.language,
                record.journey_type,
                record.citizenship_group,
                record.jurisdiction,
                record.created_at,
                record.updated_at,
            ],
        )
        return record if ok else None

    async def get_session(self, session_id: str) -> SessionRecord | None:
        if self._db is None:
            return None
        row = await self._db.fetch_one("SELECT * FROM chat_sessions WHERE id = ?", [session_id])  # type: ignore[union-attr]
        if not row:
            return None
        return self._row_to_session(row)

    async def list_active_sessions(self, limit: int = 10) -> list[SessionRecord]:
        if self._db is None:
            return []
        rows = await self._db.fetch_all(  # type: ignore[union-attr]
            "SELECT * FROM chat_sessions WHERE is_active = 1 ORDER BY updated_at DESC LIMIT ?",
            [limit],
        )
        return [self._row_to_session(r) for r in rows]

    async def update_session(
        self,
        session_id: str,
        journey_type: str | None = None,
        citizenship_group: str | None = None,
        jurisdiction: str | None = None,
    ) -> bool:
        if self._db is None:
            return False
        now = datetime.now(UTC).isoformat()
        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]
        if journey_type is not None:
            fields.append("journey_type = ?")
            params.append(journey_type)
        if citizenship_group is not None:
            fields.append("citizenship_group = ?")
            params.append(citizenship_group)
        if jurisdiction is not None:
            fields.append("jurisdiction = ?")
            params.append(jurisdiction)
        params.append(session_id)
        return await self._db.execute(
            f"UPDATE chat_sessions SET {', '.join(fields)} WHERE id = ?", params
        )  # type: ignore[return-value]

    async def close_session(self, session_id: str) -> bool:
        if self._db is None:
            return False
        now = datetime.now(UTC).isoformat()
        return await self._db.execute(
            "UPDATE chat_sessions SET is_active = 0, updated_at = ? WHERE id = ?",
            [now, session_id],
        )  # type: ignore[return-value]

    # ── Messages ─────────────────────────────────────────────────────────────

    async def append_message(
        self,
        session_id: str,
        role: str,
        content_summary: str = "",
        has_citations: bool = False,
        grounding_verdict: str | None = None,
    ) -> MessageRecord | None:
        if self._db is None:
            logger.debug("append_message skipped — db unavailable")
            return None

        now = datetime.now(UTC).isoformat()
        record = MessageRecord(
            id=str(uuid4()),
            session_id=session_id,
            role=role,
            content_summary=content_summary[:500],
            content_length=len(content_summary),
            has_citations=has_citations,
            grounding_verdict=grounding_verdict,
            created_at=now,
        )
        ok = await self._db.execute(
            """INSERT INTO session_messages
               (id, session_id, role, content_summary, content_length,
                has_citations, grounding_verdict, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                record.id,
                record.session_id,
                record.role,
                record.content_summary,
                record.content_length,
                1 if record.has_citations else 0,
                record.grounding_verdict,
                record.created_at,
            ],
        )
        if ok:
            await self._db.execute(
                "UPDATE chat_sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
                [now, session_id],
            )
        return record if ok else None

    async def get_session_messages(self, session_id: str, limit: int = 50) -> list[MessageRecord]:
        if self._db is None:
            return []
        rows = await self._db.fetch_all(  # type: ignore[union-attr]
            "SELECT * FROM session_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
            [session_id, limit],
        )
        return [self._row_to_message(r) for r in rows]

    # ── Investigations ───────────────────────────────────────────────────────

    async def create_investigation(
        self,
        topic: str,
        language: str = "en",
        session_id: str | None = None,
        doc_ids: list[str] | None = None,
        entity_mentions: list[str] | None = None,
    ) -> InvestigationRecord | None:
        if self._db is None:
            logger.debug("create_investigation skipped — db unavailable")
            return None

        now = datetime.now(UTC).isoformat()
        record = InvestigationRecord(
            id=str(uuid4()),
            session_id=session_id,
            topic=topic[:500],
            language=language,
            doc_ids=doc_ids or [],
            entity_mentions=entity_mentions or [],
            created_at=now,
            updated_at=now,
        )
        ok = await self._db.execute(
            """INSERT INTO user_investigations
               (id, session_id, topic, language, summary, doc_ids,
                entity_mentions, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                record.id,
                record.session_id,
                record.topic,
                record.language,
                record.summary,
                json.dumps(record.doc_ids),
                json.dumps(record.entity_mentions),
                record.confidence,
                record.created_at,
                record.updated_at,
            ],
        )
        return record if ok else None

    async def update_investigation(
        self,
        investigation_id: str,
        summary: str | None = None,
        doc_ids: list[str] | None = None,
        entity_mentions: list[str] | None = None,
        confidence: float | None = None,
    ) -> bool:
        if self._db is None:
            return False
        now = datetime.now(UTC).isoformat()
        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]
        if summary is not None:
            fields.append("summary = ?")
            params.append(summary)
        if doc_ids is not None:
            fields.append("doc_ids = ?")
            params.append(json.dumps(doc_ids))
        if entity_mentions is not None:
            fields.append("entity_mentions = ?")
            params.append(json.dumps(entity_mentions))
        if confidence is not None:
            fields.append("confidence = ?")
            params.append(confidence)
        params.append(investigation_id)
        return await self._db.execute(
            f"UPDATE user_investigations SET {', '.join(fields)} WHERE id = ?",
            params,
        )  # type: ignore[return-value]

    async def search_investigations(self, topic: str, limit: int = 5) -> list[InvestigationRecord]:
        if self._db is None:
            return []
        needle = f"%{topic.strip().lower()}%"
        rows = await self._db.fetch_all(  # type: ignore[union-attr]
            "SELECT * FROM user_investigations WHERE LOWER(topic) LIKE ? ORDER BY updated_at DESC LIMIT ?",
            [needle, limit],
        )
        return [self._row_to_investigation(r) for r in rows]

    # ── Row mapping helpers ──────────────────────────────────────────────────

    @staticmethod
    def _row_to_session(row: dict[str, Any]) -> SessionRecord:
        return SessionRecord(
            id=str(row.get("id", "")),
            language=str(row.get("language", "en")),
            journey_type=row.get("journey_type"),
            citizenship_group=row.get("citizenship_group"),
            jurisdiction=row.get("jurisdiction"),
            message_count=int(row.get("message_count", 0)),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
            is_active=bool(row.get("is_active", 1)),
        )

    @staticmethod
    def _row_to_message(row: dict[str, Any]) -> MessageRecord:
        return MessageRecord(
            id=str(row.get("id", "")),
            session_id=str(row.get("session_id", "")),
            role=str(row.get("role", "")),
            content_summary=str(row.get("content_summary", "")),
            content_length=int(row.get("content_length", 0)),
            has_citations=bool(row.get("has_citations", 0)),
            grounding_verdict=row.get("grounding_verdict"),
            created_at=str(row.get("created_at", "")),
        )

    @staticmethod
    def _row_to_investigation(row: dict[str, Any]) -> InvestigationRecord:
        doc_ids_raw = row.get("doc_ids", "[]")
        entity_raw = row.get("entity_mentions", "[]")
        return InvestigationRecord(
            id=str(row.get("id", "")),
            session_id=row.get("session_id"),
            topic=str(row.get("topic", "")),
            language=str(row.get("language", "en")),
            summary=str(row.get("summary", "")),
            doc_ids=json.loads(doc_ids_raw) if isinstance(doc_ids_raw, str) else [],
            entity_mentions=json.loads(entity_raw) if isinstance(entity_raw, str) else [],
            confidence=row.get("confidence"),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )
