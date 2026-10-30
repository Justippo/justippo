"""Coverage boost batch 22 — matrix_auth D1-backed storage branches via fake D1.

DRY: reuses ``tests.unit.d1_fakes.InMemoryD1Binding`` to drive the REAL
``D1Client.execute / fetch_one`` code paths (the production branches that the
in-memory fallback dict never reaches). Cloudflare's Testing docs confirm D1
state is only assertable inside the Workers runtime; this fake lets host
pytest execute those branches without workerd/Miniflare.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request

from app.api.v1.endpoints import matrix_auth as ma
from tests.unit.d1_fakes import InMemoryD1Binding


def _request_with_d1(binding: InMemoryD1Binding) -> Request:
    """Build a FastAPI Request whose scope carries a real D1 binding (env.DB)."""
    scope: dict[str, object] = {
        "type": "http",
        "headers": [],
        "env": SimpleNamespace(DB=binding),
    }
    return Request(scope)


def _state_record() -> dict[str, object]:
    return {
        "code_verifier": "v" * 64,
        "redirect_uri": "https://app.example/callback",
        "device_id": "DEVICE1234",
        "expires_at": int(time.time()) + 300,
        "created_at": int(time.time()),
    }


def _session_record() -> dict[str, object]:
    return {
        "session_id": "session-1",
        "matrix_user_id": "@alice:matrix.example",
        "device_id": "DEVICE1234",
        "access_token": "old-access",
        "refresh_token": "refresh-secret",
        "token_type": "Bearer",
        "expires_at": int(time.time()) + 300,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }


# ─── state storage (matrix_oauth_states) ────────────────────────


class TestMatrixStateStorageD1:
    async def test_store_state_persists_to_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        state = "state-abc"
        await ma._store_state(request, state, _state_record())

        key = ma._state_hash(state)
        assert key in binding._tables["matrix_oauth_states"]
        assert binding._tables["matrix_oauth_states"][key]["code_verifier"] == "v" * 64

    async def test_consume_state_reads_and_deletes_from_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        state = "state-xyz"
        await ma._store_state(request, state, _state_record())

        # Not expired -> returns the record, and removes it from D1.
        record = await ma._consume_state(request, state)
        assert record is not None
        assert record["code_verifier"] == "v" * 64
        key = ma._state_hash(state)
        assert key not in binding._tables["matrix_oauth_states"]

    async def test_consume_state_expired_returns_none(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        state = "state-exp"
        rec = _state_record()
        rec["expires_at"] = int(time.time()) - 10
        await ma._store_state(request, state, rec)

        assert await ma._consume_state(request, state) is None

    async def test_consume_state_missing_returns_none(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        assert await ma._consume_state(request, "never-stored") is None

    async def test_store_state_d1_failure_raises_503(self) -> None:
        binding = InMemoryD1Binding(fail_writes=True)
        request = _request_with_d1(binding)
        with pytest.raises(HTTPException) as exc_info:
            await ma._store_state(request, "state-fail", _state_record())
        assert exc_info.value.status_code == 503
        assert "storage unavailable" in str(exc_info.value.detail)


# ─── session storage (matrix_oauth_sessions) ────────────────────


class TestMatrixSessionStorageD1:
    async def test_store_session_persists_to_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        await ma._store_session(request, "session-1", _session_record())
        assert "session-1" in binding._tables["matrix_oauth_sessions"]
        assert (
            binding._tables["matrix_oauth_sessions"]["session-1"]["matrix_user_id"]
            == "@alice:matrix.example"
        )

    async def test_get_session_reads_from_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        await ma._store_session(request, "session-1", _session_record())
        fetched = await ma._get_session(request, "session-1")
        assert fetched is not None
        assert fetched["access_token"] == "old-access"

    async def test_get_session_missing_returns_none(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        assert await ma._get_session(request, "absent") is None

    async def test_delete_session_removes_from_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        await ma._store_session(request, "session-1", _session_record())
        await ma._delete_session(request, "session-1")
        assert "session-1" not in binding._tables["matrix_oauth_sessions"]

    async def test_store_session_d1_failure_raises_503(self) -> None:
        binding = InMemoryD1Binding(fail_writes=True)
        request = _request_with_d1(binding)
        with pytest.raises(HTTPException) as exc_info:
            await ma._store_session(request, "session-1", _session_record())
        assert exc_info.value.status_code == 503


# ─── refresh session (UPDATE path) ──────────────────────────────


class TestMatrixRefreshSessionD1:
    async def test_refresh_session_updates_token_in_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        await ma._store_session(request, "session-1", _session_record())

        refreshed = {
            **_session_record(),
            "access_token": "new-access",
            "expires_at": int(time.time()) + 300,
            "updated_at": int(time.time()),
        }
        with (
            patch.object(
                ma, "_discover_metadata", AsyncMock(return_value={"token_endpoint": "https://t"})
            ),
            patch.object(
                ma,
                "_provider_request",
                AsyncMock(return_value=(200, {"access_token": "new-access", "expires_in": 3600})),
            ),
        ):
            result = await ma._refresh_session(request, refreshed)

        assert result is not None
        assert result["access_token"] == "new-access"
        stored = binding._tables["matrix_oauth_sessions"]["session-1"]
        assert stored["access_token"] == "new-access"

    async def test_refresh_session_no_refresh_token_returns_none(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        rec = _session_record()
        rec["refresh_token"] = None
        assert await ma._refresh_session(request, rec) is None
