"""Batch 7: Remaining coverage boost — chat.py and matrix_auth.py pure functions.

Covers:
- chat.py — is_greeting, build_contextual_retrieval_query, ChatTurn validation, ChatRequest validation
- matrix_auth.py — _require_enabled, _state_hash, _has_env_token, _pkce_challenge, _json_object_to_python, _set_session_cookie, _clear_session_cookie, auth_status
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/api/v1/endpoints/chat.py
# ---------------------------------------------------------------------------


class TestIsGreeting:
    def test_greeting_hello(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("Hello") is True

    def test_greeting_hi(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("Hi there") is True

    def test_not_greeting(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("What is the work permit process?") is False

    def test_empty(self) -> None:
        from app.api.v1.endpoints.chat import is_greeting

        assert is_greeting("") is False


class TestBuildContextualQuery:
    def test_no_history(self) -> None:
        from app.api.v1.endpoints.chat import build_contextual_retrieval_query

        result = build_contextual_retrieval_query("test query", [])
        assert "test query" in result

    def test_with_history(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn, build_contextual_retrieval_query

        history = [
            ChatTurn(role="user", content="prev question"),
            ChatTurn(role="assistant", content="prev answer"),
        ]
        result = build_contextual_retrieval_query("follow up", history)
        assert "follow up" in result


class TestChatTurnValidation:
    def test_valid_turn(self) -> None:
        from app.api.v1.endpoints.chat import ChatTurn

        turn = ChatTurn(role="user", content="hello")
        assert turn.role == "user"
        assert turn.content == "hello"

    def test_blank_content_rejected(self) -> None:
        from pydantic import ValidationError

        from app.api.v1.endpoints.chat import ChatTurn

        with pytest.raises(ValidationError):
            ChatTurn(role="user", content="")


class TestChatRequestValidation:
    def test_valid_request(self) -> None:
        from app.api.v1.endpoints.chat import ChatRequest

        req = ChatRequest(message="hello", session_id="s1")
        assert req.message == "hello"

    def test_blank_message_rejected(self) -> None:
        from pydantic import ValidationError

        from app.api.v1.endpoints.chat import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(message="", session_id="s1")


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/matrix_auth.py
# ---------------------------------------------------------------------------


class TestMatrixRequireEnabled:
    def test_raises_when_disabled(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _require_enabled

        with patch("app.api.v1.endpoints.matrix_auth.settings") as mock_settings:
            mock_settings.ENABLE_MATRIX_AUTH = False
            with pytest.raises(Exception, match="Matrix auth"):
                _require_enabled()

    def test_no_raise_when_enabled(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _require_enabled

        with patch("app.api.v1.endpoints.matrix_auth.settings") as mock_settings:
            mock_settings.ENABLE_MATRIX_AUTH = True
            _require_enabled()


class TestMatrixStateHash:
    def test_deterministic(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _state_hash

        h1 = _state_hash("test-state")
        h2 = _state_hash("test-state")
        assert h1 == h2

    def test_different_inputs(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _state_hash

        assert _state_hash("state1") != _state_hash("state2")


class TestMatrixHasEnvToken:
    def test_has_token(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _has_env_token

        with patch("app.api.v1.endpoints.matrix_auth.settings") as mock_settings:
            mock_settings.MATRIX_ACCESS_TOKEN = "valid-token"
            assert _has_env_token() is True

    def test_no_token(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _has_env_token

        with patch("app.api.v1.endpoints.matrix_auth.settings") as mock_settings:
            mock_settings.MATRIX_ACCESS_TOKEN = ""
            assert _has_env_token() is False


class TestMatrixPkceChallenge:
    def test_challenge_generation(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _pkce_challenge

        challenge = _pkce_challenge("test-verifier-value")
        assert isinstance(challenge, str)
        assert len(challenge) > 0

    def test_deterministic(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _pkce_challenge

        c1 = _pkce_challenge("verifier")
        c2 = _pkce_challenge("verifier")
        assert c1 == c2


class TestMatrixJsonObject:
    def test_valid_dict(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _json_object_to_python

        result = _json_object_to_python({"key": "value"})
        assert result == {"key": "value"}

    def test_non_dict(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _json_object_to_python

        with pytest.raises(TypeError):
            _json_object_to_python("not a dict")
        with pytest.raises(TypeError):
            _json_object_to_python(123)
        with pytest.raises(TypeError):
            _json_object_to_python(None)


class TestMatrixCookieHelpers:
    def test_set_session_cookie(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _set_session_cookie

        mock_response = MagicMock()
        mock_settings = MagicMock()
        mock_settings.MATRIX_OAUTH_COOKIE_NAME = "matrix_session"
        mock_settings.MATRIX_OAUTH_SESSION_TTL_S = 3600
        mock_settings.is_production = True

        with patch("app.api.v1.endpoints.matrix_auth.settings", mock_settings):
            _set_session_cookie(mock_response, "session-123")
            mock_response.set_cookie.assert_called_once()

    def test_clear_session_cookie(self) -> None:
        from app.api.v1.endpoints.matrix_auth import _clear_session_cookie

        mock_response = MagicMock()
        mock_settings = MagicMock()
        mock_settings.MATRIX_OAUTH_COOKIE_NAME = "matrix_session"
        mock_settings.is_production = True

        with patch("app.api.v1.endpoints.matrix_auth.settings", mock_settings):
            _clear_session_cookie(mock_response)
            mock_response.set_cookie.assert_called_once()
            call_kwargs = mock_response.set_cookie.call_args
            assert call_kwargs.kwargs.get("max_age") == 0 or call_kwargs[1].get("max_age") == 0


class TestMatrixAuthStatus:
    async def test_auth_status_disabled(self) -> None:
        from app.api.v1.endpoints.matrix_auth import auth_status

        with patch("app.api.v1.endpoints.matrix_auth.settings") as mock_settings:
            mock_settings.ENABLE_MATRIX_AUTH = False
            result = await auth_status()
            assert result.enabled is False

    async def test_auth_status_enabled_no_token(self) -> None:
        from app.api.v1.endpoints.matrix_auth import auth_status

        with patch("app.api.v1.endpoints.matrix_auth.settings") as mock_settings:
            mock_settings.ENABLE_MATRIX_AUTH = True
            mock_settings.MATRIX_ACCESS_TOKEN = ""
            result = await auth_status()
            assert result.enabled is True
            assert result.available is False
