"""Tests for request-scoped Cloudflare background HTTP delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations import http_forwarder


@pytest.fixture(autouse=True)
def _clear_wait_until() -> None:
    token = http_forwarder.bind_wait_until(None)
    yield
    http_forwarder.reset_wait_until(token)


@pytest.mark.asyncio
async def test_registers_post_with_request_wait_until() -> None:
    registered_posts: list[Awaitable[None]] = []
    token = http_forwarder.bind_wait_until(registered_posts.append)

    try:
        with patch.object(http_forwarder, "_post", new=AsyncMock()) as post:
            await http_forwarder.fire_and_forget(
                "https://metrics.example.test",
                {"Authorization": "test"},
                {"series": []},
            )

            assert len(registered_posts) == 1
            assert not isinstance(registered_posts[0], asyncio.Task)
            await registered_posts[0]
            post.assert_awaited_once()
    finally:
        http_forwarder.reset_wait_until(token)


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_wait_until_callbacks() -> None:
    registrations: dict[str, list[Awaitable[None]]] = {"a": [], "b": []}

    async def send(label: str) -> None:
        token = http_forwarder.bind_wait_until(registrations[label].append)
        try:
            await asyncio.sleep(0)
            await http_forwarder.fire_and_forget(
                f"https://{label}.example.test",
                {},
                "payload",
            )
        finally:
            http_forwarder.reset_wait_until(token)

    with patch.object(http_forwarder, "_post", new=AsyncMock()):
        await asyncio.gather(send("a"), send("b"))
        assert len(registrations["a"]) == 1
        assert len(registrations["b"]) == 1
        assert registrations["a"][0] is not registrations["b"][0]
        await asyncio.gather(*registrations["a"], *registrations["b"])


@pytest.mark.asyncio
async def test_registration_failure_awaits_post_without_raising() -> None:
    wait_until = MagicMock(side_effect=RuntimeError("context closed"))
    token = http_forwarder.bind_wait_until(wait_until)

    try:
        with patch.object(http_forwarder, "_post", new=AsyncMock()) as post:
            await http_forwarder.fire_and_forget("https://example.test", {}, "payload")
            post.assert_awaited_once()
    finally:
        http_forwarder.reset_wait_until(token)


@pytest.mark.asyncio
async def test_local_runtime_keeps_detached_task_fallback() -> None:
    with patch.object(http_forwarder, "_post", new=AsyncMock()) as post:
        await http_forwarder.fire_and_forget("https://example.test", {}, "payload")
        await asyncio.sleep(0)
        post.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_now_awaits_compact_json_delivery() -> None:
    with patch.object(http_forwarder, "_post", new=AsyncMock()) as post:
        await http_forwarder.post_now(
            "https://metrics.example.test",
            {"Authorization": "test"},
            {"series": [{"metric": "test"}]},
            timeout=2.0,
        )

    post.assert_awaited_once()
    url, headers, content, timeout, _ = post.await_args.args
    assert url == "https://metrics.example.test"
    assert headers == {"Authorization": "test"}
    assert content == '{"series":[{"metric":"test"}]}'
    assert timeout == 2.0
