"""SPDX-License-Identifier: AGPL-3.0-or-later
Minimal in-memory Cloudflare D1 binding fake for pytest.

Why this exists
--------------
The production ``D1Client`` wraps a Cloudflare D1 *binding* (a JS object
exposed via ``request.scope["env"].DB``) reachable only inside the Workers
runtime (workerd / Miniflare). Host ``pytest`` has no real D1 binding, so the
D1-backed branches of endpoints (matrix_auth session/state storage, glossary,
stats, audit) are unreachable without a fake. Per Cloudflare's Testing docs,
D1 state is only assertable inside the Workers runtime; the Workers Vitest
integration (``@cloudflare/vitest-pool-workers``) is JS/TS-only and cannot
import the Python backend. This fake lets us execute the *real*
``D1Client.execute / fetch_one / fetch_all`` code paths against an in-process
key/value store, exercising the production branches faithfully.

Surface modelled on the real D1 binding used by ``app.db.d1_client.D1Client``:
    stmt = binding.prepare(sql)
    stmt = stmt.bind(*params)      # optional
    await stmt.run()                # writes  -> returns None
    await stmt.first()              # reads   -> one row dict or None
    await stmt.all()                # reads   -> D1Result with .results

Supported SQL is deliberately narrow: the INSERT / INSERT OR REPLACE /
SELECT / DELETE / UPDATE shapes emitted by the app's storage helpers. Rows are
keyed by the first column of the INSERT (which is the primary key in every
schema used here: state_hash, session_id, id, dataset_code). WHERE clauses
support exact (``= ?``) and ``LOWER(col) LIKE ?`` substring matching.

Inject via the real ``D1Client.from_scope`` path:
    scope = {"type": "http", "env": SimpleNamespace(DB=InMemoryD1Binding()), ...}
    request = Request(scope)
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

from app.db.d1_client import D1Client

# Tables the fake knows about. Values are keyed dicts: key -> full row dict.
_DEFAULT_TABLES: dict[str, dict[Any, dict[str, Any]]] = {
    "matrix_oauth_states": {},
    "matrix_oauth_sessions": {},
    "glossary_terms": {},
    "eurostat_snapshots": {},
    "chat_sessions": {},
    "session_messages": {},
    "user_investigations": {},
}

_WHERE_RE = re.compile(r"WHERE\s+(?:LOWER\()?(\w+)\)?\s+(LIKE|=)\s*\?", re.IGNORECASE)
_FROM_RE = re.compile(r"FROM\s+(\w+)", re.IGNORECASE)
_INSERT_RE = re.compile(
    r"INSERT\s+(?:OR\s+REPLACE\s+)?INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES\s*\((.+)\)",
    re.IGNORECASE | re.DOTALL,
)
_DELETE_RE = re.compile(r"DELETE\s+FROM\s+(\w+)", re.IGNORECASE)
_UPDATE_RE = re.compile(r"UPDATE\s+(\w+)", re.IGNORECASE)


class _Statement:
    """A prepared statement bound to a fake binding + SQL + params."""

    def __init__(self, binding: InMemoryD1Binding, sql: str) -> None:
        self._binding = binding
        self._sql = sql
        self._params: list[Any] = []

    def bind(self, *params: Any) -> _Statement:
        self._params.extend(params)
        return self

    async def run(self) -> None:
        self._binding._execute_write(self._sql, self._params)

    async def first(self) -> dict[str, Any] | None:
        rows = self._binding._execute_read_all(self._sql, self._params)
        return rows[0] if rows else None

    async def all(self) -> Any:
        rows = self._binding._execute_read_all(self._sql, self._params)
        result = MagicMock()
        result.results = rows
        return result


class InMemoryD1Binding(D1Client):
    """In-memory stand-in for a Cloudflare D1 database binding.

    Subclasses ``D1Client`` so it satisfies the ``D1Client | None`` type hints
    used by repositories, while ``self._db = self`` makes ``D1Client.execute /
    fetch_one / fetch_all`` delegate to this fake's ``prepare`` surface.

    Realistic enough to drive ``D1Client``'s execute/fetch_one/fetch_all paths.
    Set ``fail_writes=True`` to simulate a D1 outage (run() raises) so callers
    exercise their graceful-degradation / 503 paths.
    """

    def __init__(self, *, fail_writes: bool = False) -> None:
        super().__init__(self)
        self._tables: dict[str, dict[Any, dict[str, Any]]] = {name: {} for name in _DEFAULT_TABLES}
        self.fail_writes = fail_writes
        # Observability for assertions in tests.
        self.writes: list[tuple[str, list[Any]]] = []
        self.reads: list[tuple[str, list[Any]]] = []

    # -- D1 binding surface -------------------------------------------------

    def prepare(self, sql: str) -> _Statement:
        return _Statement(self, sql)

    # -- internal execution --------------------------------------------------

    def _execute_write(self, sql: str, params: list[Any]) -> None:
        self.writes.append((sql, list(params)))
        if self.fail_writes:
            raise RuntimeError("simulated D1 outage")
        lowered = sql.strip().upper()
        if lowered.startswith("INSERT"):
            m = _INSERT_RE.search(sql)
            if not m:
                raise ValueError(f"Unsupported INSERT statement: {sql!r}")
            table = m.group(1)
            cols = [c.strip() for c in m.group(2).split(",")]
            # VALUES tokens may mix bound params (``?``) and SQL literals
            # (e.g. ``VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1)``). Bind params
            # consume positionally from ``params``; literals are folded in
            # verbatim so the stored row mirrors what D1 would persist.
            value_tokens = [v.strip() for v in m.group(3).split(",")]
            assert table is not None
            row: dict[Any, Any] = {}
            param_idx = 0
            for col, token in zip(cols, value_tokens, strict=True):
                if token == "?":
                    row[col] = params[param_idx]
                    param_idx += 1
                elif token.upper() == "NULL":
                    row[col] = None
                else:
                    row[col] = token
            pk = cols[0]
            self._tables[table][row[pk]] = row
        elif lowered.startswith("DELETE"):
            m = _DELETE_RE.search(sql)
            assert m is not None
            table = m.group(1)
            where = _WHERE_RE.search(sql)
            assert where is not None
            pk_value = params[0]
            self._tables[table].pop(pk_value, None)
        elif lowered.startswith("UPDATE"):
            m = _UPDATE_RE.search(sql)
            assert m is not None
            table = m.group(1)
            where = _WHERE_RE.search(sql)
            assert where is not None
            pk_value = params[-1]
            existing = self._tables[table].get(pk_value)
            if existing is not None:
                set_cols = re.search(r"SET\s+(.+?)\s+WHERE", sql, re.IGNORECASE | re.DOTALL)
                assert set_cols is not None
                set_names = [s.strip().split("=")[0].strip() for s in set_cols.group(1).split(",")]
                for name, value in zip(set_names, params[:-1], strict=True):
                    existing[name] = value
        else:
            raise ValueError(f"Unsupported write statement: {sql!r}")

    def _execute_read_all(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        self.reads.append((sql, list(params)))
        lowered = sql.strip().upper()
        if not lowered.startswith("SELECT"):
            raise ValueError(f"Unsupported read statement: {sql!r}")
        from_m = _FROM_RE.search(sql)
        assert from_m is not None
        table = from_m.group(1)
        where = _WHERE_RE.search(sql)
        rows = list(self._tables[table].values())
        if where is None:
            return rows
        col = where.group(1)
        op = where.group(2).upper()
        value = params[0]
        if op == "LIKE":
            needle = str(value).strip("%").lower()
            return [r for r in rows if needle in str(r.get(col, "")).lower()]
        return [r for r in rows if r.get(col) == value]


class InMemoryKVBinding:
    """In-memory Cloudflare Workers KV binding fake for pytest.

    Mirrors the KV namespace binding surface used by the workers_ai neuron
    budget tracker (``settings.NEURON_BUDGET_KV``): ``await kv.get(key)``
    returns the stored value or ``None``; ``await kv.put(key, value,
    expiration_ttl=...)`` stores it. No Worker runtime required.
    """

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._store: dict[str, str] = dict(initial or {})
        self.get_calls: list[str] = []
        self.put_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str, /, *, type: str = "text") -> str | None:
        self.get_calls.append(key)
        return self._store.get(key)

    async def put(
        self,
        key: str,
        value: str,
        /,
        *,
        expiration_ttl: int | None = None,
    ) -> None:
        self.put_calls.append((key, value, expiration_ttl))
        self._store[key] = value

    def get_sync(self, key: str) -> str | None:  # convenience for assertions
        return self._store.get(key)
