"""Coverage for the Matrix client retry/error branches.

DRY: every Matrix HTTP call funnels through ``httpx.AsyncClient`` ->
``_with_retry``. A single ``httpx.MockTransport`` (injected by patching
``httpx.AsyncClient``) drives every error branch: 5xx/429 retry, last-attempt
``MatrixClientError`` (with/without parseable JSON), ``httpx.TimeoutException``
-> ``MatrixTimeoutError``, transport ``httpx.HTTPError`` -> ``MatrixClientError``,
and the ``create_secure_room`` / ``check_health`` response-shape guards.

The public methods (``create_secure_room``/``check_health``) call ``_with_retry``
internally, so exercising them covers the retry core too.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.integrations.matrix.client import (
    MatrixClient,
    MatrixClientError,
    MatrixConfigurationError,
    MatrixTimeoutError,
)

# Capture the REAL httpx.AsyncClient before any test patches it so the mock
# client factory can build genuine clients backed by MockTransport without
# recursing into the patched symbol.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_for(
    *,
    status: int = 200,
    json_body: object | None = None,
    raise_exc: type[Exception] | Exception | None = None,
    text_body: str | None = None,
    handler: object | None = None,
) -> httpx.AsyncClient:
    """Build a real httpx client whose single transport returns/raises as told.

    If ``handler`` (a callable) is supplied it is used directly; otherwise a
    default handler is built from status/json_body/raise_exc/text_body.
    """

    def _default(request: httpx.Request) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        if text_body is not None:
            return httpx.Response(status, content=text_body.encode())
        return httpx.Response(status, json=json_body if json_body is not None else {})

    _handler = handler if handler is not None else _default
    return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(_handler))


def _make_client(
    *,
    status: int = 200,
    json_body: object | None = None,
    raise_exc: type[Exception] | Exception | None = None,
    text_body: str | None = None,
) -> MatrixClient:
    client = MatrixClient(base_url="https://matrix.example.org", access_token="s3cr3t")
    client._RETRY_CONFIG = {"attempts": 3, "exponential_base": 2, "exponential_max": 0.0}
    return client


@pytest.fixture
def patch_httpx(monkeypatch: pytest.MonkeyPatch):
    """Patch httpx.AsyncClient to a factory producing our MockTransport client."""

    def _apply(factory) -> None:
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: factory())

    return _apply


@pytest.mark.asyncio
async def test_create_secure_room_success(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=200, json_body={"room_id": "!abc:example.org"}))
    room_id = await _make_client().create_secure_room(participants=["@a:example.org"])
    assert room_id == "!abc:example.org"


@pytest.mark.asyncio
async def test_create_secure_room_4xx_matrix_client_error(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=403, json_body={"errcode": "M_FORBIDDEN"}))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().create_secure_room(participants=["@a:example.org"])
    assert exc.value.status_code == 403
    assert exc.value.errcode == "M_FORBIDDEN"


@pytest.mark.asyncio
async def test_create_secure_room_5xx_retries_then_errors(
    patch_httpx, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    patch_httpx(lambda: _client_for(status=500, json_body={"errcode": "M_UNKNOWN"}))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().create_secure_room(participants=["@a:example.org"])
    assert exc.value.status_code == 500
    # Three attempts -> two backoff sleeps between them.
    assert len(sleeps) == 2


@pytest.mark.asyncio
async def test_create_secure_room_5xx_unparseable_json(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=502, text_body="<html>bad</html>"))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().create_secure_room(participants=["@a:example.org"])
    assert exc.value.status_code == 502
    assert exc.value.errcode is None


@pytest.mark.asyncio
async def test_create_secure_room_timeout(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.TimeoutException("boom")))
    with pytest.raises(MatrixTimeoutError):
        await _make_client().create_secure_room(participants=["@a:example.org"])


@pytest.mark.asyncio
async def test_create_secure_room_connect_error(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.ConnectError("nope")))
    with pytest.raises(MatrixClientError):
        await _make_client().create_secure_room(participants=["@a:example.org"])


@pytest.mark.asyncio
async def test_create_secure_room_connect_error_retries_then_fails(
    patch_httpx, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    patch_httpx(lambda: _client_for(raise_exc=httpx.ConnectError("nope")))
    with pytest.raises(MatrixClientError):
        await _make_client().create_secure_room(participants=["@a:example.org"])
    assert len(sleeps) == 2


@pytest.mark.asyncio
async def test_check_health_success(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=200, json_body={"unstable_features": {}}))
    health = await _make_client().check_health()
    assert health["status"] == "healthy"


@pytest.mark.asyncio
async def test_check_health_transport_error(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.ConnectError("nope")))
    with pytest.raises(MatrixClientError):
        await _make_client().check_health()


@pytest.mark.asyncio
async def test_check_health_non_200(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=500, json_body={"errcode": "X"}))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().check_health()
    assert "500" in str(exc.value)


@pytest.mark.asyncio
async def test_check_health_timeout(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.TimeoutException("boom")))
    with pytest.raises(MatrixTimeoutError):
        await _make_client().check_health()


@pytest.mark.asyncio
async def test_create_secure_room_non_dict_response(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=200, json_body=["not", "a", "dict"]))
    with pytest.raises(MatrixClientError):
        await _make_client().create_secure_room(participants=["@a:example.org"])


@pytest.mark.asyncio
async def test_create_secure_room_missing_room_id(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=200, json_body={"foo": "bar"}))
    with pytest.raises(MatrixClientError):
        await _make_client().create_secure_room(participants=["@a:example.org"])


# ---------------------------------------------------------------------------
# send_document (2-step upload + send) and get_room_events — httpx chokepoint
# ---------------------------------------------------------------------------


def _matrix_client_for_send(patch_httpx, *, upload_status=200, send_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/upload"):
            if upload_status != 200:
                return httpx.Response(upload_status, json={"errcode": "M_FORBIDDEN"})
            return httpx.Response(200, json={"content_uri": "mxc://example.org/abc"})
        if send_status != 200:
            return httpx.Response(send_status, json={"errcode": "M_FORBIDDEN"})
        return httpx.Response(200, json={"event_id": "$evt:example.org"})

    patch_httpx(lambda: _client_for(handler=handler))


@pytest.mark.asyncio
async def test_send_document_success(patch_httpx) -> None:
    _matrix_client_for_send(patch_httpx)
    event_id = await _make_client().send_document(
        room_id="!r:example.org",
        doc_bytes=b"%PDF-1.4",
        filename="doc.pdf",
        mime_type="application/pdf",
    )
    assert event_id == "$evt:example.org"


@pytest.mark.asyncio
async def test_send_document_upload_error(patch_httpx) -> None:
    _matrix_client_for_send(patch_httpx, upload_status=403)
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )
    assert "403" in str(exc.value)


@pytest.mark.asyncio
async def test_send_document_send_error(patch_httpx) -> None:
    _matrix_client_for_send(patch_httpx, send_status=403)
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )
    assert "403" in str(exc.value)


@pytest.mark.asyncio
async def test_send_document_missing_content_uri(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/upload"):
            return httpx.Response(200, json={})  # no content_uri
        return httpx.Response(200, json={"event_id": "$evt:example.org"})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError):
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_send_document_missing_event_id(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/upload"):
            return httpx.Response(200, json={"content_uri": "mxc://x/y"})
        return httpx.Response(200, json={})  # no event_id

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError):
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_get_room_events_success(patch_httpx, monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a MagicMock response so a real bytes body survives JSON (httpx can't
    # carry bytes in json=). The redaction branch keys on bytes/bytearray type.
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    def _json():
        return {
            "chunk": [
                {
                    "event_id": "$1:example.org",
                    "sender": "@a:example.org",
                    "type": "m.room.message",
                    "origin_server_ts": 123,
                    "content": {"body": b"\x00binary", "msgtype": "m.file"},
                }
            ]
        }

    mock_resp.json.side_effect = _json

    client = _REAL_ASYNC_CLIENT()
    monkeypatch.setattr(client, "get", AsyncMock(return_value=mock_resp))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    events = await _make_client().get_room_events("!r:example.org")
    assert len(events) == 1
    assert events[0]["content"]["body"] == "[REDACTED — binary content]"
    assert events[0]["content"]["msgtype"] == "m.file"


@pytest.mark.asyncio
async def test_get_room_events_error(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=403, json_body={"errcode": "M_FORBIDDEN"}))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().get_room_events("!r:example.org")
    assert "403" in str(exc.value)


# ---------------------------------------------------------------------------
# Constructor validation + per-method timeout/HTTPError handlers
# ---------------------------------------------------------------------------


def test_constructor_rejects_placeholder_token() -> None:
    with pytest.raises(MatrixConfigurationError):
        MatrixClient(base_url="https://matrix.example.org", access_token="your-matrix-token")


def test_constructor_rejects_non_https() -> None:
    with pytest.raises(MatrixConfigurationError):
        MatrixClient(base_url="http://matrix.example.org", access_token="s3cr3t")


@pytest.mark.asyncio
async def test_send_document_timeout(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.TimeoutException("boom")))
    with pytest.raises(MatrixTimeoutError):
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_send_document_transport_error(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.ConnectError("nope")))
    with pytest.raises(MatrixClientError):
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_get_room_events_timeout(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.TimeoutException("boom")))
    with pytest.raises(MatrixTimeoutError):
        await _make_client().get_room_events("!r:example.org")


@pytest.mark.asyncio
async def test_get_room_events_transport_error(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(raise_exc=httpx.ConnectError("nope")))
    with pytest.raises(MatrixClientError):
        await _make_client().get_room_events("!r:example.org")


# ---------------------------------------------------------------------------
# Non-2xx (500) responses that pass through _with_retry, plus the invite loop
# ---------------------------------------------------------------------------


def _matrix_client_full(handler_factory):
    """Route by path: createRoom/invite/upload/send/messages, default handler."""

    def dispatch(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/createRoom"):
            return httpx.Response(200, json={"room_id": "!room:example.org"})
        if path.endswith("/invite"):
            return httpx.Response(200, json={})
        if path.endswith("/join"):
            return httpx.Response(200, json={})
        if path.endswith("/upload"):
            return httpx.Response(200, json={"content_uri": "mxc://x/y"})
        if "/send/" in path:
            return httpx.Response(200, json={"event_id": "$evt:example.org"})
        if path.endswith("/messages"):
            return httpx.Response(200, json={"chunk": []})
        return handler_factory(request) if handler_factory else httpx.Response(500)

    return _client_for(handler=dispatch)


@pytest.mark.asyncio
async def test_create_secure_room_invites_participants(patch_httpx) -> None:
    patch_httpx(lambda: _matrix_client_full(None))
    room_id = await _make_client().create_secure_room(
        participants=["@alice:example.org", "@bob:example.org"]
    )
    assert room_id == "!room:example.org"


@pytest.mark.asyncio
async def test_get_room_events_non_2xx(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"errcode": "M_UNKNOWN"})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().get_room_events("!r:example.org")
    assert "500" in str(exc.value)


# ---------------------------------------------------------------------------
# Misc coverable branches: close(), check_health, non-JSON error body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_is_noop(patch_httpx) -> None:
    patch_httpx(lambda: _client_for(status=200))
    await _make_client().close()  # line 155 (pass)


@pytest.mark.asyncio
async def test_matrix_error_non_json_body(patch_httpx) -> None:
    """_matrix_error must tolerate a non-JSON error body (lines 65-66)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/createRoom"):
            return httpx.Response(403, content=b"not-json")
        return httpx.Response(200, json={})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError):
        await _make_client().create_secure_room(participants=["@alice:example.org"])


@pytest.mark.asyncio
async def test_send_document_upload_non_2xx(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/upload"):
            return httpx.Response(500, json={"errcode": "M_UNKNOWN"})
        return httpx.Response(200, json={"event_id": "$e:example.org"})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )
    assert "500" in str(exc.value)


@pytest.mark.asyncio
async def test_send_document_send_non_2xx(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/upload"):
            return httpx.Response(200, json={"content_uri": "mxc://x/y"})
        return httpx.Response(500, json={"errcode": "M_UNKNOWN"})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError) as exc:
        await _make_client().send_document(
            room_id="!r:example.org",
            doc_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            mime_type="application/pdf",
        )
    assert "500" in str(exc.value)


@pytest.mark.asyncio
async def test_create_secure_room_invite_failure_logged(patch_httpx) -> None:
    """A failing invite (403) is logged, not raised — the room still returns."""
    calls = {"invite": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/createRoom"):
            return httpx.Response(200, json={"room_id": "!room:example.org"})
        if path.endswith("/invite"):
            calls["invite"] += 1
            return httpx.Response(403, json={"errcode": "M_FORBIDDEN"})
        if path.endswith("/join"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    patch_httpx(lambda: _client_for(handler=handler))
    room_id = await _make_client().create_secure_room(participants=["@alice:example.org"])
    assert room_id == "!room:example.org"
    assert calls["invite"] == 1


@pytest.mark.asyncio
async def test_create_secure_room_invite_timeout(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/createRoom"):
            return httpx.Response(200, json={"room_id": "!room:example.org"})
        if path.endswith("/invite"):
            raise httpx.TimeoutException("invite timed out")
        return httpx.Response(200, json={})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixTimeoutError):
        await _make_client().create_secure_room(participants=["@alice:example.org"])


@pytest.mark.asyncio
async def test_create_secure_room_invite_transport_error(patch_httpx) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/createRoom"):
            return httpx.Response(200, json={"room_id": "!room:example.org"})
        if path.endswith("/invite"):
            raise httpx.ConnectError("invite transport down")
        return httpx.Response(200, json={})

    patch_httpx(lambda: _client_for(handler=handler))
    with pytest.raises(MatrixClientError):
        await _make_client().create_secure_room(participants=["@alice:example.org"])
