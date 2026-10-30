"""Tests for PostHog backend integration (issue #218)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_posthog_state() -> None:
    """Reset PostHog module-level state between tests."""
    from app.integrations import posthog

    posthog._api_key = None
    posthog._host = None
    posthog._enabled = False


from app.integrations.posthog import capture_event, configure, get_client  # noqa: E402


class TestPostHogNoOp:
    """PostHog must be a no-op when token is unset."""

    def test_no_op_when_token_unset(self) -> None:
        configure("", "https://eu.i.posthog.com")
        assert get_client() is None

    def test_no_op_when_disabled(self) -> None:
        configure("phc_test_token", "https://eu.i.posthog.com", disabled=True)
        assert get_client() is None


class TestPostHogCaptureEvent:
    """capture_event must fire-and-forget via http_forwarder."""

    @pytest.mark.asyncio
    async def test_capture_event_helper_with_valid_token(self) -> None:
        configure("phc_test_token", "https://eu.i.posthog.com")
        assert get_client() is not None

        with patch("app.integrations.posthog.fire_and_forget", new_callable=AsyncMock) as mock_ff:
            await capture_event(
                "document_uploaded",
                distinct_id="@alice:matrix.org",
                properties={"page_count": 1, "content_type": "application/pdf"},
                session_id="sess-123",
            )

        mock_ff.assert_called_once()
        args, _ = mock_ff.call_args
        payload = args[2]  # fire_and_forget(url, headers, content) — content is 3rd arg
        assert payload["event"] == "document_uploaded"
        assert payload["distinct_id"] == "@alice:matrix.org"
        assert payload["api_key"] == "phc_test_token"
        assert payload["properties"]["$session_id"] == "sess-123"
        assert payload["properties"]["page_count"] == 1

    @pytest.mark.asyncio
    async def test_capture_event_skips_empty_distinct_id(self) -> None:
        configure("phc_test_token", "https://eu.i.posthog.com")

        with patch("app.integrations.posthog.fire_and_forget", new_callable=AsyncMock) as mock_ff:
            await capture_event("document_uploaded", distinct_id="")

        mock_ff.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_event_skips_anonymous_prefix(self) -> None:
        configure("phc_test_token", "https://eu.i.posthog.com")

        with patch("app.integrations.posthog.fire_and_forget", new_callable=AsyncMock) as mock_ff:
            await capture_event("document_uploaded", distinct_id="anonymous-123")

        mock_ff.assert_not_called()


def _make_scope(path: str, headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    """Build a minimal valid ASGI scope for Starlette Request."""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }


async def _ok_response(request):
    """Async call_next that returns a proper Response."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


class TestPostHogMiddleware:
    """PostHogMiddleware must gate on GDPR consent."""

    @pytest.fixture(autouse=True)
    def _configure_posthog(self) -> None:
        from app.integrations.posthog import configure

        configure("phc_test_token", "https://eu.i.posthog.com")

    @pytest.mark.asyncio
    async def test_middleware_skips_health_endpoint(self) -> None:
        from starlette.requests import Request

        from app.core.middleware import PostHogMiddleware

        middleware = PostHogMiddleware(app=None)
        request = Request(_make_scope("/api/v1/health"))

        response = await middleware.dispatch(request, _ok_response)
        assert response.status_code == 200
        assert not hasattr(request.state, "posthog_distinct_id")

    @pytest.mark.asyncio
    async def test_middleware_blocks_capture_without_gdpr_consent(self) -> None:
        from starlette.requests import Request

        from app.core.middleware import PostHogMiddleware

        middleware = PostHogMiddleware(app=None)
        request = Request(_make_scope("/api/v1/translate"))

        await middleware.dispatch(request, _ok_response)
        assert not hasattr(request.state, "posthog_distinct_id")
        assert not hasattr(request.state, "posthog_session_id")

    @pytest.mark.asyncio
    async def test_middleware_extracts_correct_headers(self) -> None:
        from starlette.requests import Request

        from app.core.middleware import PostHogMiddleware

        middleware = PostHogMiddleware(app=None)
        request = Request(
            _make_scope(
                "/api/v1/translate",
                headers=[
                    (b"x-gdpr-consent", b"token-123"),
                    (b"x-posthog-distinct-id", b"@alice:matrix.org"),
                    (b"x-posthog-session-id", b"sess-456"),
                ],
            )
        )

        await middleware.dispatch(request, _ok_response)
        assert request.state.posthog_distinct_id == "@alice:matrix.org"
        assert request.state.posthog_session_id == "sess-456"


class TestExchangeEvent:
    """exchange_document_shared must exclude room and user IDs."""

    @pytest.mark.asyncio
    async def test_exchange_event_excludes_room_and_user_ids(self) -> None:
        configure("phc_test_token", "https://eu.i.posthog.com")

        with patch("app.integrations.posthog.fire_and_forget", new_callable=AsyncMock) as mock_ff:
            await capture_event(
                "exchange_document_shared",
                distinct_id="@alice:matrix.org",
                properties={"protocol": "matrix", "direction": "send"},
            )

        mock_ff.assert_called_once()
        args, _ = mock_ff.call_args
        payload = args[2]
        props = payload["properties"]
        # No room IDs, user IDs, or message content
        assert "room_id" not in props
        assert "user_id" not in props
        assert "message_content" not in props
        assert "filename" not in props
        # Only allowed properties
        assert props["protocol"] == "matrix"
        assert props["direction"] == "send"
