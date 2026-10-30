"""Eurostat snapshot repository — D1 cache for migration statistics.

Follows the same D1Client pattern as GlossaryRepo: graceful degradation
when D1 is unavailable (returns None / empty, never raises).

# DRY: D1 pattern — mirrors glossary_repo.py's D1Client usage.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite

    from app.db.d1_client import D1Client

logger = logging.getLogger(__name__)

_DEFAULT_DATASET = "migr_pop1ctz"
_DEFAULT_TTL = 86400  # 24 hours — dataset updates annually


class EurostatRepo:
    """Data-access layer for eurostat_snapshots (D1 / SQLite)."""

    def __init__(self, db: D1Client | aiosqlite.Connection | None = None) -> None:
        self._db = db

    async def get_fresh_snapshot(
        self,
        dataset_code: str = _DEFAULT_DATASET,
    ) -> dict[str, Any] | None:
        """Return the latest cached snapshot if still within TTL, else None.

        # DRY: D1 pattern — same fetch_one + graceful degradation as GlossaryRepo.
        """
        if self._db is None:
            return None

        now = int(time.time())
        sql = (
            "SELECT data_json, fetched_at, ttl_seconds FROM eurostat_snapshots "
            "WHERE dataset_code = ? ORDER BY fetched_at DESC LIMIT 1"
        )
        try:
            row = await self._db.fetch_one(sql, [dataset_code])  # type: ignore[union-attr]
        except Exception:
            logger.warning("D1 fetch failed for eurostat_snapshots", exc_info=False)
            return None

        if not row:
            return None

        fetched_at = int(row.get("fetched_at", 0))
        ttl = int(row.get("ttl_seconds", _DEFAULT_TTL))
        if now - fetched_at > ttl:
            logger.info("Eurostat snapshot expired (age=%ds, ttl=%ds)", now - fetched_at, ttl)
            return None

        try:
            parsed = dict(json.loads(row["data_json"]))
            # Validity check: skip cached responses with empty value dicts
            # (caused by previous broken geo param format)
            if not parsed.get("value"):
                logger.info("Cached Eurostat snapshot has empty value dict — treating as stale")
                return None
            return parsed
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Failed to parse cached Eurostat JSON", exc_info=False)
            return None

    async def get_last_snapshot(
        self,
        dataset_code: str = _DEFAULT_DATASET,
    ) -> dict[str, Any] | None:
        """Return the latest cached snapshot regardless of TTL (graceful fallback)."""
        if self._db is None:
            return None

        sql = (
            "SELECT data_json FROM eurostat_snapshots "
            "WHERE dataset_code = ? ORDER BY fetched_at DESC LIMIT 1"
        )
        try:
            row = await self._db.fetch_one(sql, [dataset_code])  # type: ignore[union-attr]
        except Exception:
            return None

        if not row:
            return None

        try:
            parsed = dict(json.loads(row["data_json"]))
            if not parsed.get("value"):
                logger.info("Cached Eurostat fallback snapshot has empty value dict — skipping")
                return None
            return parsed
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    async def save_snapshot(
        self,
        data: dict[str, Any],
        dataset_code: str = _DEFAULT_DATASET,
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> bool:
        """Persist a fresh Eurostat API response to D1.

        # DRY: D1 pattern — same execute + graceful degradation as GlossaryRepo.
        """
        if self._db is None:
            return False

        now = int(time.time())
        sql = (
            "INSERT INTO eurostat_snapshots (dataset_code, data_json, fetched_at, ttl_seconds) "
            "VALUES (?, ?, ?, ?)"
        )
        try:
            return bool(
                await self._db.execute(sql, [dataset_code, json.dumps(data), now, ttl_seconds])
            )
        except Exception:
            logger.warning("Failed to save Eurostat snapshot to D1", exc_info=False)
            return False
