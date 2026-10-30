# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Unit tests for D1Client — Cloudflare D1 binding wrapper.

Coverage:
- from_scope() returns None when scope has no env
- from_scope() returns None when env has no DB attribute
- from_scope() returns D1Client when env.DB is present
- execute() returns True on success (no params)
- execute() returns True on success (with params)
- execute() returns False on exception (graceful degradation)
- execute() does not call bind() when no params provided
- fetch_one() returns dict on success
- fetch_one() returns None when result is falsy
- fetch_one() returns None on exception (graceful degradation)
- fetch_one() works with params
- fetch_one() does not call bind() when no params provided
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.d1_client import D1Client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_binding(
    *,
    execute_raises: Exception | None = None,
    fetch_result: Any = None,
    fetch_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock D1 binding (JS-like object with prepare/bind/run/first)."""
    binding = MagicMock()
    stmt = MagicMock()

    # prepare().bind(*args) returns the same stmt for chaining
    binding.prepare.return_value = stmt
    stmt.bind.return_value = stmt

    if execute_raises:
        stmt.run = AsyncMock(side_effect=execute_raises)
    else:
        stmt.run = AsyncMock(return_value=None)

    if fetch_raises:
        stmt.first = AsyncMock(side_effect=fetch_raises)
    else:
        stmt.first = AsyncMock(return_value=fetch_result)

    return binding


# ---------------------------------------------------------------------------
# from_scope
# ---------------------------------------------------------------------------


class TestFromScope:
    def test_returns_none_when_no_env_key(self) -> None:
        scope: dict[str, Any] = {}
        assert D1Client.from_scope(scope) is None

    def test_returns_none_when_env_is_none(self) -> None:
        scope: dict[str, Any] = {"env": None}
        assert D1Client.from_scope(scope) is None

    def test_returns_none_when_env_has_no_db(self) -> None:
        env = MagicMock(spec=[])  # no DB attribute
        scope: dict[str, Any] = {"env": env}
        assert D1Client.from_scope(scope) is None

    def test_returns_d1client_when_env_has_db(self) -> None:
        binding = _make_binding()
        env = MagicMock()
        env.DB = binding
        scope: dict[str, Any] = {"env": env}
        client = D1Client.from_scope(scope)
        assert isinstance(client, D1Client)


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_returns_true_on_success_no_params(self) -> None:
        binding = _make_binding()
        client = D1Client(binding)
        result = await client.execute("INSERT INTO audit_log VALUES (?)")
        assert result is True
        binding.prepare.assert_called_once_with("INSERT INTO audit_log VALUES (?)")
        binding.prepare.return_value.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_true_on_success_with_params(self) -> None:
        binding = _make_binding()
        client = D1Client(binding)
        result = await client.execute(
            "INSERT INTO audit_log (id, method) VALUES (?, ?)", ["abc", "POST"]
        )
        assert result is True
        stmt = binding.prepare.return_value
        stmt.bind.assert_called_once_with("abc", "POST")
        stmt.bind.return_value.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        binding = _make_binding(execute_raises=RuntimeError("D1 unavailable"))
        client = D1Client(binding)
        result = await client.execute("INSERT INTO t VALUES (?)")
        assert result is False
        assert "D1 write failed" in caplog.text

    @pytest.mark.asyncio
    async def test_does_not_raise_on_exception(self) -> None:
        """execute() must never propagate exceptions — graceful degradation."""
        binding = _make_binding(execute_raises=Exception("connection reset"))
        client = D1Client(binding)
        result = await client.execute("INSERT INTO t VALUES (?)")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_bind_called_when_no_params(self) -> None:
        binding = _make_binding()
        client = D1Client(binding)
        await client.execute("DELETE FROM t")
        binding.prepare.return_value.bind.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_bind_called_when_params_is_none(self) -> None:
        binding = _make_binding()
        client = D1Client(binding)
        await client.execute("DELETE FROM t", None)
        binding.prepare.return_value.bind.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_one
# ---------------------------------------------------------------------------


class TestFetchOne:
    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self) -> None:
        row = {"id": "abc", "method": "POST", "status_code": 200}
        binding = _make_binding(fetch_result=row)
        client = D1Client(binding)
        result = await client.fetch_one("SELECT * FROM audit_log WHERE id = ?", ["abc"])
        assert result == row

    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self) -> None:
        binding = _make_binding(fetch_result=None)
        client = D1Client(binding)
        result = await client.fetch_one("SELECT * FROM audit_log WHERE id = ?", ["missing"])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        binding = _make_binding(fetch_raises=RuntimeError("D1 gone"))
        client = D1Client(binding)
        result = await client.fetch_one("SELECT * FROM t")
        assert result is None
        assert "D1 read failed" in caplog.text

    @pytest.mark.asyncio
    async def test_does_not_raise_on_exception(self) -> None:
        binding = _make_binding(fetch_raises=Exception("timeout"))
        client = D1Client(binding)
        result = await client.fetch_one("SELECT * FROM t")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_bind_called_when_no_params(self) -> None:
        binding = _make_binding(fetch_result={"count": 5})
        client = D1Client(binding)
        await client.fetch_one("SELECT COUNT(*) FROM t")
        binding.prepare.return_value.bind.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_params_calls_bind(self) -> None:
        row = {"id": "1"}
        binding = _make_binding(fetch_result=row)
        client = D1Client(binding)
        await client.fetch_one("SELECT * FROM t WHERE id = ?", ["1"])
        binding.prepare.return_value.bind.assert_called_once_with("1")

    @pytest.mark.asyncio
    async def test_multiple_params_unpacked(self) -> None:
        row = {"id": "x", "method": "GET"}
        binding = _make_binding(fetch_result=row)
        client = D1Client(binding)
        await client.fetch_one("SELECT * FROM t WHERE id = ? AND method = ?", ["x", "GET"])
        binding.prepare.return_value.bind.assert_called_once_with("x", "GET")


# ---------------------------------------------------------------------------
# fetch_all
# ---------------------------------------------------------------------------


def _make_binding_all(
    *,
    all_result: Any = None,
    all_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock D1 binding with .all() support."""
    binding = MagicMock()
    stmt = MagicMock()
    binding.prepare.return_value = stmt
    stmt.bind.return_value = stmt
    stmt.run = AsyncMock(return_value=None)
    stmt.first = AsyncMock(return_value=None)
    if all_raises:
        stmt.all = AsyncMock(side_effect=all_raises)
    else:
        stmt.all = AsyncMock(return_value=all_result)
    return binding


class TestFetchAll:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts_attribute_results(self) -> None:
        """D1Result with .results attribute (JS proxy shape)."""
        d1_result = MagicMock()
        d1_result.results = [
            {"id": "a", "term_en": "residence permit"},
            {"id": "b", "term_en": "work permit"},
        ]
        binding = _make_binding_all(all_result=d1_result)
        client = D1Client(binding)
        result = await client.fetch_all("SELECT * FROM glossary_terms")
        assert result == [
            {"id": "a", "term_en": "residence permit"},
            {"id": "b", "term_en": "work permit"},
        ]

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts_dict_results(self) -> None:
        """D1Result as plain dict (test/mock shape)."""
        d1_result = {"results": [{"id": "c", "term_en": "visa"}], "success": True}
        binding = _make_binding_all(all_result=d1_result)
        client = D1Client(binding)
        result = await client.fetch_all("SELECT * FROM glossary_terms")
        assert result == [{"id": "c", "term_en": "visa"}]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self) -> None:
        d1_result = MagicMock()
        d1_result.results = []
        binding = _make_binding_all(all_result=d1_result)
        client = D1Client(binding)
        result = await client.fetch_all("SELECT * FROM glossary_terms WHERE 1=0")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_result_is_none(self) -> None:
        binding = _make_binding_all(all_result=None)
        client = D1Client(binding)
        result = await client.fetch_all("SELECT * FROM glossary_terms")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """Graceful degradation — never raises."""
        caplog.set_level(logging.WARNING)
        binding = _make_binding_all(all_raises=RuntimeError("D1 unavailable"))
        client = D1Client(binding)
        result = await client.fetch_all("SELECT * FROM glossary_terms")
        assert result == []
        assert "D1 fetch_all failed" in caplog.text

    @pytest.mark.asyncio
    async def test_does_not_raise_on_any_exception(self) -> None:
        binding = _make_binding_all(all_raises=Exception("timeout"))
        client = D1Client(binding)
        result = await client.fetch_all("SELECT * FROM glossary_terms")
        assert result == []

    @pytest.mark.asyncio
    async def test_binds_params_correctly(self) -> None:
        d1_result = MagicMock()
        d1_result.results = [{"id": "d", "term_en": "passport"}]
        binding = _make_binding_all(all_result=d1_result)
        client = D1Client(binding)
        await client.fetch_all("SELECT * FROM glossary_terms WHERE term_en LIKE ?", ["%passport%"])
        binding.prepare.return_value.bind.assert_called_once_with("%passport%")

    @pytest.mark.asyncio
    async def test_no_bind_when_no_params(self) -> None:
        d1_result = MagicMock()
        d1_result.results = []
        binding = _make_binding_all(all_result=d1_result)
        client = D1Client(binding)
        await client.fetch_all("SELECT * FROM glossary_terms")
        binding.prepare.return_value.bind.assert_not_called()
