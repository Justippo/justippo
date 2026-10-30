# SPDX-License-Identifier: AGPL-3.0-or-later
"""
D1 Client — Thin async wrapper for Cloudflare D1 binding.

The D1 binding is a JS object available via request.scope["env"].DB in the
Cloudflare ASGI bridge. This module provides a small helper so the rest of the
application doesn't need to know about scope internals.

Usage in middleware:
    db = D1Client.from_scope(request.scope)
    if db:
        await db.execute("INSERT INTO audit_log ...")

Usage in tests:
    db = D1Client(mock_d1_binding)
    # or pass None to simulate unavailable binding
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

logger = logging.getLogger(__name__)


class D1Client:
    """Wraps a Cloudflare D1 binding (JS object) for use from Python async code."""

    def __init__(self, binding: Any) -> None:
        self._db = binding

    @classmethod
    def from_scope(cls, scope: MutableMapping[str, Any]) -> D1Client | None:
        """
        Extract the D1 binding from an ASGI scope dict.

        Cloudflare's Python Workers ASGI bridge exposes the Worker env
        (including bindings) via scope["env"]. Returns None when running
        locally or in tests without a real D1 binding.
        """
        env = scope.get("env")
        if env is None:
            return None
        db = getattr(env, "DB", None)
        if db is None:
            return None
        return cls(db)

    async def execute(self, sql: str, params: list[Any] | None = None) -> bool:
        """
        Execute a write statement (INSERT / UPDATE / DELETE).

        Returns True on success, False on any error.
        Errors are logged but never raised — callers must not depend on D1
        availability for correctness (graceful degradation).
        """
        try:
            stmt = self._db.prepare(sql)
            if params:
                stmt = stmt.bind(*params)
            await stmt.run()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("D1 write failed (%s): %s", type(exc).__name__, exc)
            return False

    async def fetch_one(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        """
        Execute a SELECT and return the first row as a dict, or None.
        """
        try:
            stmt = self._db.prepare(sql)
            if params:
                stmt = stmt.bind(*params)
            result = await stmt.first()
            return dict(result) if result else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("D1 read failed (%s): %s", type(exc).__name__, exc)
            return None

    async def fetch_all(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute a SELECT and return all matching rows as a list of dicts.

        Uses D1PreparedStatement.all() which returns a D1Result object with:
            result.results — list of row dicts
            result.success — boolean

        Returns an empty list on no results or any error.
        Errors are logged but never raised — callers must not depend on D1
        availability for correctness (graceful degradation).

        This is the primitive the GlossaryRepo.search_terms() and
        get_all_terms() depend on.
        """
        try:
            stmt = self._db.prepare(sql)
            if params:
                stmt = stmt.bind(*params)
            result = await stmt.all()
            if result is None:
                return []
            # D1Result exposes .results as a list of row objects.
            # Handle both attribute-access (JS proxy) and dict-access shapes.
            rows: Any = getattr(result, "results", None)
            if rows is None and isinstance(result, dict):
                rows = result.get("results", [])
            if not rows:
                return []
            return [dict(row) for row in rows if row is not None]
        except Exception as exc:  # noqa: BLE001
            logger.warning("D1 fetch_all failed (%s): %s", type(exc).__name__, exc)
            return []
