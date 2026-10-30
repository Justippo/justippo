"""
Unit tests for the Pyodide-safe Sentry Envelope forwarder.

Coverage focus:
- DSN configure/no-op behavior
- Envelope format: envelope header, item header, event payload
- Matching event_id in envelope header and event payload
- Sensitive header filtering
- ship_to_sentry graceful no-op and create_task/fallback behavior
- SentryMiddleware re-raises after shipping (does not swallow 500s)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.middleware import SentryMiddleware
from app.integrations import sentry


def _parse_envelope(envelope: bytes) -> tuple[dict, dict, dict]:
    """Parse our single-item Sentry envelope into header, item header, payload."""
    header_raw, item_raw, payload_raw, _ = envelope.split(b"\n", 3)
    return (
        json.loads(header_raw.decode()),
        json.loads(item_raw.decode()),
        json.loads(payload_raw.decode()),
    )


@pytest.fixture(autouse=True)
def _reset_sentry_state() -> None:
    sentry.configure(None)


class TestConfigure:
    def test_configure_none_disables_sentry(self) -> None:
        sentry.configure(None)
        assert sentry._enabled is False
        assert sentry._dsn is None
        assert sentry._ingest_url is None

    def test_configure_empty_string_disables_sentry(self) -> None:
        sentry.configure("")
        assert sentry._enabled is False

    def test_configure_valid_dsn_sets_ingest_url(self) -> None:
        dsn = "https://abc123@o4510903400529920.ingest.de.sentry.io/4511587249094736"
        sentry.configure(dsn)
        assert sentry._enabled is True
        assert sentry._project_id == "4511587249094736"
        assert (
            sentry._ingest_url
            == "https://o4510903400529920.ingest.de.sentry.io/api/4511587249094736/envelope/"
        )


class TestBuildEnvelope:
    def test_build_envelope_contains_matching_event_ids(self) -> None:
        dsn = "https://abc123@o4510903400529920.ingest.de.sentry.io/4511587249094736"
        sentry.configure(dsn)

        try:
            raise ValueError("boom")
        except ValueError as exc:
            envelope = sentry.build_envelope(
                exc,
                {
                    "method": "POST",
                    "url": "https://api.example.test/api/v1/documents/",
                    "headers": {"content-type": "application/json"},
                    "query_string": "x=1",
                },
            )

        header, item, payload = _parse_envelope(envelope)

        assert header["dsn"] == dsn
        assert header["event_id"] == payload["event_id"]
        assert header["sdk"]["name"] == "evidence-eu.pyodide-sentry-forwarder"
        assert item["type"] == "event"
        assert item["content_type"] == "application/json"
        assert item["length"] == len(
            json.dumps(payload, separators=(",", ":"), default=str).encode()
        )
        assert payload["platform"] == "python"
        assert payload["level"] == "error"
        assert payload["exception"]["values"][0]["type"] == "ValueError"
        assert payload["exception"]["values"][0]["value"] == "boom"
        assert payload["request"]["method"] == "POST"

    def test_build_envelope_filters_sensitive_headers(self) -> None:
        sentry.configure("https://abc123@o4510903400529920.ingest.de.sentry.io/42")

        exc = RuntimeError("sensitive")
        envelope = sentry.build_envelope(
            exc,
            {
                "method": "GET",
                "url": "https://api.example.test",
                "headers": {
                    "Authorization": "Bearer secret",
                    "Cookie": "session=secret",
                    "X-GDPR-Consent": "accepted",
                    "CF-AIG-Authorization": "Bearer cf",
                    "X-Request-ID": "safe",
                },
            },
        )

        _, _, payload = _parse_envelope(envelope)
        headers = payload["request"]["headers"]
        assert headers["Authorization"] == "[Filtered]"
        assert headers["Cookie"] == "[Filtered]"
        assert headers["X-GDPR-Consent"] == "[Filtered]"
        assert headers["CF-AIG-Authorization"] == "[Filtered]"
        assert headers["X-Request-ID"] == "safe"


class TestShipToSentry:
    @pytest.mark.asyncio
    async def test_ship_to_sentry_noop_when_disabled(self) -> None:
        sentry.configure(None)
        with patch("app.integrations.sentry.fire_and_forget", new=AsyncMock()) as post:
            await sentry.ship_to_sentry(RuntimeError("ignored"))
        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ship_to_sentry_ships_when_enabled(self) -> None:
        sentry.configure("https://abc123@o4510903400529920.ingest.de.sentry.io/42")

        with patch("app.integrations.sentry.fire_and_forget", new=AsyncMock()) as post:
            await sentry.ship_to_sentry(RuntimeError("scheduled"))

        post.assert_awaited_once()
        # Verify it posted to the correct ingest URL
        call_args = post.await_args
        assert "ingest" in call_args.args[0] and "sentry.io" in call_args.args[0]
        assert call_args.args[1]["Content-Type"] == "application/x-sentry-envelope"


class TestSentryMiddleware:
    @pytest.mark.asyncio
    async def test_middleware_ships_and_reraises_unhandled_exception(self) -> None:
        middleware = SentryMiddleware(app=lambda scope, receive, send: None)

        request = SimpleNamespace(
            method="GET",
            url="https://api.example.test/api/v1/documents/",
            headers={"x-request-id": "abc"},
            query_params={"q": "test"},
        )

        async def _call_next(_request):
            raise RuntimeError("middleware boom")

        with (
            patch("app.integrations.sentry.ship_to_sentry", new=AsyncMock()) as ship,
            pytest.raises(RuntimeError, match="middleware boom"),
        ):
            await middleware.dispatch(request, _call_next)

        ship.assert_awaited_once()
        exc_arg, request_ctx = ship.await_args.args
        assert isinstance(exc_arg, RuntimeError)
        assert request_ctx["method"] == "GET"
        assert request_ctx["query_string"] == "{'q': 'test'}"
