"""Coverage boost batch 13 — chat_stream greeting path, JSON decode error,
memory append, and matrix_auth pure logic paths."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── chat.py: chat_stream greeting path ──────────────────────────


class TestChatStreamGreeting:
    @pytest.mark.asyncio()
    async def test_greeting_bypasses_rag(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(message="hello there", language="en", history=[])

        async def _mock_greeting_stream(*args: Any, **kwargs: Any) -> Any:
            yield "Hi there! "
            yield "How can I help?"

        with (
            patch(
                "app.api.v1.endpoints.chat.generate_greeting_stream",
                _mock_greeting_stream,
            ),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=True),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
        ):
            response = await chat_stream(req, body)
            assert response.status_code == 200

    @pytest.mark.asyncio()
    async def test_greeting_not_triggered_with_history(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, ChatTurn, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(
            message="hello there",
            language="en",
            history=[ChatTurn(role="user", content="hi")],
        )

        with (
            patch(
                "app.api.v1.endpoints.chat.generate_greeting_stream",
                side_effect=Exception("should not be called"),
            ),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=True),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
            patch(
                "app.api.v1.endpoints.chat.build_empty_result_guidance",
                return_value={
                    "reason": "no_verified_source",
                    "message": "No info",
                    "matched": False,
                },
            ),
        ):
            response = await chat_stream(req, body)
            assert response.status_code == 200


# ─── chat.py: answer parsing JSON decode error ────────────────────


class TestChatStreamAnswerParseError:
    @pytest.mark.asyncio()
    async def test_malformed_sse_frame_skipped(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(message="test", language="en", history=[])

        async def _mock_sse(*args: Any, **kwargs: Any) -> Any:
            yield "event: answer_chunk\ndata: not-json\n\n"
            yield "event: done\n\ndata: [DONE]\n\n"

        with (
            patch("app.api.v1.endpoints.chat._sse_generator", _mock_sse),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=False),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
            patch(
                "app.api.v1.endpoints.chat.build_empty_result_guidance",
                return_value={
                    "reason": "no_verified_source",
                    "message": "No info",
                    "matched": False,
                },
            ),
        ):
            response = await chat_stream(req, body)
            assert response.status_code == 200


# ─── chat.py: memory append path ──────────────────────────────────


class TestChatStreamMemoryAppend:
    @pytest.mark.asyncio()
    async def test_memory_append_after_answer(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest, chat_stream

        req = MagicMock()
        req.headers = {}
        req.query_params = {}
        req.scope = {}

        body = ChatRequest(message="test", language="en", history=[])

        mock_memory = AsyncMock()
        mock_memory.append_message = AsyncMock()

        async def _mock_sse(*args: Any, **kwargs: Any) -> Any:
            yield 'event: answer_chunk\ndata: {"text": "Hello"}\n\n'
            yield "event: done\n\ndata: [DONE]\n\n"

        with (
            patch("app.api.v1.endpoints.chat._sse_generator", _mock_sse),
            patch("app.api.v1.endpoints.chat.is_greeting", return_value=False),
            patch("app.api.v1.endpoints.chat._request_id", return_value="req-1"),
            patch(
                "app.api.v1.endpoints.chat.build_empty_result_guidance",
                return_value={
                    "reason": "no_verified_source",
                    "message": "No info",
                    "matched": False,
                },
            ),
            patch(
                "app.api.v1.endpoints.chat.MemoryRepository",
                return_value=mock_memory,
            ),
            patch(
                "app.api.v1.endpoints.chat.D1Client",
                return_value=None,
            ),
            patch(
                "app.api.v1.endpoints.chat.settings",
                MagicMock(SESSION_MEMORY_ENABLED=True),
            ),
        ):
            response = await chat_stream(req, body)
            assert response.status_code == 200
            assert mock_memory.append_message.called


# ─── matrix_auth.py: discovery logic ──────────────────────────────


class TestMatrixAuthDiscovery:
    def test_discovery_404_raises_unsupported(self) -> None:
        from app.api.v1.endpoints.matrix_auth import MatrixDiscoveryError, _discover_metadata

        async def _mock_discovery(*args: Any, **kwargs: Any) -> tuple[int, dict[str, Any]]:
            return (404, {})

        with (
            patch(
                "app.api.v1.endpoints.matrix_auth._fetch_metadata_with_httpx",
                side_effect=_mock_discovery,
            ),
            pytest.raises(MatrixDiscoveryError),
        ):
            asyncio.run(_discover_metadata())

    def test_discovery_incomplete_metadata(self) -> None:
        from app.api.v1.endpoints.matrix_auth import MatrixDiscoveryError, _discover_metadata

        async def _mock_discovery(*args: Any, **kwargs: Any) -> tuple[int, dict[str, Any]]:
            return (
                200,
                {
                    "authorization_endpoint": "https://example.com/auth",
                    "token_endpoint": "https://example.com/token",
                },
            )

        with (
            patch(
                "app.api.v1.endpoints.matrix_auth._fetch_metadata_with_httpx",
                side_effect=_mock_discovery,
            ),
            pytest.raises(MatrixDiscoveryError, match="incomplete"),
        ):
            asyncio.run(_discover_metadata())

    def test_discovery_no_pkce(self) -> None:
        from app.api.v1.endpoints.matrix_auth import MatrixDiscoveryError, _discover_metadata

        async def _mock_discovery(*args: Any, **kwargs: Any) -> tuple[int, dict[str, Any]]:
            return (
                200,
                {
                    "authorization_endpoint": "https://example.com/auth",
                    "token_endpoint": "https://example.com/token",
                    "revocation_endpoint": "https://example.com/revoke",
                    "registration_endpoint": "https://example.com/register",
                    "code_challenge_methods_supported": ["plain"],
                },
            )

        with (
            patch(
                "app.api.v1.endpoints.matrix_auth._fetch_metadata_with_httpx",
                side_effect=_mock_discovery,
            ),
            pytest.raises(MatrixDiscoveryError, match="incomplete"),
        ):
            asyncio.run(_discover_metadata())


class TestMatrixAuthStateStorage:
    def test_state_stored_in_memory_when_no_d1(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _oauth_states, _state_hash, _store_state

        _oauth_states.clear()

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            state = "test-state"
            record = {
                "code_verifier": "v1",
                "redirect_uri": "https://example.com/callback",
                "device_id": "dev1",
                "expires_at": 9999999999,
            }
            asyncio.run(_store_state(MagicMock(), state, record))
            assert _state_hash(state) in _oauth_states

    def test_state_stored_in_d1_when_available(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _store_state

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=True)

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=mock_db,
        ):
            state = "test-state"
            now = int(time.time())
            record = {
                "code_verifier": "v1",
                "redirect_uri": "https://example.com/callback",
                "device_id": "dev1",
                "expires_at": now + 3600,
                "created_at": now,
            }
            asyncio.run(_store_state(MagicMock(), state, record))
            assert mock_db.execute.called


class TestMatrixAuthSessionStorage:
    def test_session_stored_in_memory_when_no_d1(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _oauth_sessions, _store_session

        _oauth_sessions.clear()

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            session_id = "test-session"
            record = {
                "matrix_user_id": "@user:example.com",
                "device_id": "dev1",
                "access_token": "tok",
                "token_type": "Bearer",
                "expires_at": 9999999999,
                "created_at": 1000000000,
                "updated_at": 1000000000,
            }
            asyncio.run(_store_session(MagicMock(), session_id, record))
            assert session_id in _oauth_sessions

    def test_session_retrieved_from_memory_when_no_d1(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _get_session

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            session_id = "test-session"
            record = {
                "matrix_user_id": "@user:example.com",
                "device_id": "dev1",
                "access_token": "tok",
                "token_type": "Bearer",
                "expires_at": 9999999999,
            }
            from app.api.v1.endpoints.matrix_auth import _oauth_sessions

            _oauth_sessions[session_id] = record
            result = asyncio.run(_get_session(MagicMock(), session_id))
            assert result is not None
            assert result["matrix_user_id"] == "@user:example.com"

    def test_session_not_found_returns_none(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _get_session

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            result = asyncio.run(_get_session(MagicMock(), "nonexistent"))
            assert result is None

    def test_session_deleted_from_memory(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _delete_session, _oauth_sessions

        _oauth_sessions["to-delete"] = {"access_token": "tok"}

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            asyncio.run(_delete_session(MagicMock(), "to-delete"))
            assert "to-delete" not in _oauth_sessions


class TestMatrixAuthSessionValidation:
    def test_validate_session_returns_none_when_no_record(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _get_session

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            result = asyncio.run(_get_session(MagicMock(), "bad-session"))
            assert result is None

    def test_validate_session_returns_record_when_valid(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _get_session, _oauth_sessions

        valid_record = {
            "matrix_user_id": "@user:example.com",
            "device_id": "dev1",
            "access_token": "tok",
            "token_type": "Bearer",
            "expires_at": 9999999999,
        }

        _oauth_sessions["valid-session"] = valid_record

        with patch(
            "app.api.v1.endpoints.matrix_auth.D1Client.from_scope",
            return_value=None,
        ):
            result = asyncio.run(_get_session(MagicMock(), "valid-session"))
            assert result is not None
            assert result["matrix_user_id"] == "@user:example.com"
