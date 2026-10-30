# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Glossary Repository — D1 / SQLite data access for glossary_terms.

This module provides the data-access contract that the RAG engine and
translation service depend on.  The full D1 async implementation;
the stubs below return safe defaults so the integration points are wired
and the system degrades gracefully when D1 is unavailable.

Architecture:
    GlossaryRepo
      ├── upsert_terms()   → INSERT OR REPLACE via D1Client.execute()
      ├── search_terms()   → fuzzy search via D1Client (LIKE / prefix)
      └── get_all_terms()  → SELECT * with optional lang filter

All methods are async and must work in both environments:
    Docker (uvicorn)  → aiosqlite (SQLite file)
    Cloudflare Workers → D1 binding (Pyodide)

Pyodide constraints:
    - No threading, no create_engine, no SQLAlchemy sessions
    - All DB access goes through D1Client (app.db.d1_client)
    - D1Client primitives: .execute() (writes), .fetch_one() (single row),
      .fetch_all() (multi-row SELECT — required for search_terms / get_all_terms)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    import aiosqlite

    from app.db.d1_client import D1Client

logger = logging.getLogger(__name__)


class GlossaryRepo:
    """Data-access layer for glossary_terms (D1 / SQLite).


    See D1Client in app.db.d1_client for available primitives:
      .execute(sql, params)    → bool        (INSERT/UPDATE/DELETE)
      .fetch_one(sql, params)  → dict|None   (SELECT single row)
      .fetch_all(sql, params)  → list[dict]  (SELECT multiple rows)
    All primitives degrade gracefully — they log + return False/None/[] on error, never raise.
    """

    def __init__(self, db: D1Client | aiosqlite.Connection | None = None) -> None:
        """*db* will be a D1Client (Workers) or aiosqlite connection (Docker).

        For now, None is accepted so the RAG expansion wiring works
        without any DB at all (returns empty results → passes original query).
        """
        self._db = db

    # ── Write ──────────────────────────────────────────────────────────────

    async def upsert_terms(
        self,
        terms: list[dict[str, Any]],
        doc_id: str,
        lang: str,
    ) -> list[dict[str, Any]]:
        """Insert or replace glossary terms extracted from a document.

        Uses INSERT OR REPLACE (D1 SQLite) with the UNIQUE(term_en, term_de,
        term_fr) constraint to deduplicate.  Fire-and-forget — errors are
        logged but never raised (don't fail document extraction on D1 write).

        Args:
            terms:  List of dicts with keys: term_en, term_de, term_fr,
                    definition, confidence.
            doc_id: Source document UUID.
            lang:   ISO 639-1 language of the source document.

        Returns:
            List of GlossaryTermRecord that were inserted/updated.
        """
        if self._db is None or not terms:
            logger.info(
                "upsert_terms skipped — db unavailable or no terms (%d terms for doc=%s, lang=%s)",
                len(terms),
                doc_id,
                lang,
            )
            return []

        now = datetime.now(timezone.utc).isoformat()  # noqa: UP017
        inserted: list[dict[str, Any]] = []
        tasks = []
        records = []

        for term in terms:
            record = {
                "id": str(uuid4()),
                "term_en": str(term.get("term_en", "")).strip(),
                "term_de": str(term.get("term_de", "")).strip(),
                "term_fr": str(term.get("term_fr", "")).strip(),
                "mistranslations": None,
                "definition": str(term.get("definition", "")).strip(),
                "source_doc_id": str(term.get("source_doc_id", doc_id) or doc_id),
                "source_lang": str(term.get("source_lang", lang) or lang),
                "confidence": float(term.get("confidence") or 1.0),
                "created_at": now,
                "updated_at": now,
            }

            if not record["term_en"] and not record["term_de"] and not record["term_fr"]:
                continue

            mistranslations = term.get("mistranslations")
            if isinstance(mistranslations, list):
                record["mistranslations"] = json.dumps([str(item) for item in mistranslations])
            elif isinstance(mistranslations, str) and mistranslations.strip():
                record["mistranslations"] = mistranslations

            sql = (
                "INSERT OR REPLACE INTO glossary_terms "
                "(id, term_en, term_de, term_fr, mistranslations, definition, source_doc_id, source_lang, confidence, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            params = [
                record["id"],
                record["term_en"],
                record["term_de"],
                record["term_fr"],
                record["mistranslations"],
                record["definition"],
                record["source_doc_id"],
                record["source_lang"],
                record["confidence"],
                record["created_at"],
                record["updated_at"],
            ]

            tasks.append(self._db.execute(sql, params))
            records.append(record)

        if tasks:
            results = await asyncio.gather(*tasks)
            for ok, record in zip(results, records, strict=True):
                if ok:
                    inserted.append(record)

        logger.info(
            "upsert_terms stored %d/%d terms for doc=%s (lang=%s)",
            len(inserted),
            len(terms),
            doc_id,
            lang,
        )
        return inserted

    # ── Read ───────────────────────────────────────────────────────────────

    async def search_terms(
        self,
        query: str,
        lang: str | None = None,
    ) -> list:  # type: ignore[type-arg]  # returns list[GlossaryTermRecord]
        """Fuzzy-search glossary terms.

        Args:
            query:  Search string (a word or short phrase in any language).
            lang:   Optional ISO 639-1 filter (e.g., only match against
                    term_de column).  None = search all three columns.

        Returns:
            Matching GlossaryTermRecord list, or empty list if no matches
            or DB unavailable.
        """
        if self._db is None or not query or not query.strip():
            logger.debug(
                "search_terms skipped — db unavailable or empty query (%r, lang=%s)", query, lang
            )
            return []

        needle = f"%{query.strip().lower()}%"
        if lang:
            normalized_lang = lang.lower().strip()
            if normalized_lang not in {"en", "de", "fr"}:
                logger.warning("search_terms skipped — unsupported language filter: %s", lang)
                return []
            column = f"term_{normalized_lang}"
            sql = (
                "SELECT * FROM glossary_terms "
                f"WHERE LOWER({column}) LIKE ? "
                "ORDER BY updated_at DESC LIMIT 5"
            )
            rows = await self._db.fetch_all(sql, [needle])  # type: ignore[union-attr]
        else:
            sql = (
                "SELECT * FROM glossary_terms "
                "WHERE LOWER(term_en) LIKE ? OR LOWER(term_de) LIKE ? OR LOWER(term_fr) LIKE ? "
                "ORDER BY updated_at DESC LIMIT 5"
            )
            rows = await self._db.fetch_all(sql, [needle, needle, needle])  # type: ignore[union-attr]

        return [self._row_to_record(row) for row in rows]

    async def get_all_terms(
        self,
        lang: str | None = None,
    ) -> list:  # type: ignore[type-arg]  # returns list[GlossaryTermRecord]
        """Return all glossary terms, optionally filtered by source language.

        Args:
            lang: ISO 639-1 filter on source_lang column. None = all languages.

        Returns:
            List of GlossaryTermRecord, or empty list if DB unavailable.
        """
        if self._db is None:
            logger.debug("get_all_terms skipped — db unavailable (lang=%s)", lang)
            return []

        if lang:
            sql = "SELECT * FROM glossary_terms WHERE source_lang = ? ORDER BY updated_at DESC"
            rows = await self._db.fetch_all(sql, [lang.lower().strip()])  # type: ignore[union-attr]
        else:
            sql = "SELECT * FROM glossary_terms ORDER BY updated_at DESC"
            rows = await self._db.fetch_all(sql)  # type: ignore[union-attr]

        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> object:
        from app.models.glossary import GlossaryTermRecord  # noqa: PLC0415

        return GlossaryTermRecord(**dict(row))
