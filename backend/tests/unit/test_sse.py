import asyncio

import pytest

from app.core.sse import keepalive, sse_frame


def test_sse_frame_string():
    """Test sse_frame encoding a string data."""
    result = sse_frame("message", "hello")
    assert result == "event: message\ndata: hello\n\n"


def test_sse_frame_dict():
    """Test sse_frame encoding a dict data."""
    result = sse_frame("update", {"status": "ok"})
    assert result == 'event: update\ndata: {"status": "ok"}\n\n'


def test_sse_frame_unicode():
    """Test sse_frame encoding unicode without escaping ascii."""
    result = sse_frame("message", {"text": "café"})
    assert result == 'event: message\ndata: {"text": "café"}\n\n'


@pytest.mark.asyncio
async def test_keepalive_yields_ping():
    """Test keepalive yields ping comments."""
    ka = keepalive(0.001)

    # Collect a few pings
    pings = []
    async for frame in ka:
        pings.append(frame)
        if len(pings) >= 3:
            break

    assert len(pings) == 3
    for ping in pings:
        assert ping == ": ping\n\n"


@pytest.mark.asyncio
async def test_keepalive_cancellation():
    """Test keepalive can be cancelled cleanly."""
    ka = keepalive(10.0)

    async def run_ka():
        async for _ in ka:
            pass

    task = asyncio.create_task(run_ka())

    # Let it start and sleep
    await asyncio.sleep(0.01)

    # Cancel the task
    task.cancel()

    await task  # Should not raise CancelledError because run_ka finishes gracefully!

    # Let's test the generator's behavior more directly.
    ka2 = keepalive(10.0)
    # Using ensure_future instead of create_task to handle awaitable
    task2 = asyncio.ensure_future(ka2.__anext__())
    await asyncio.sleep(0.01)
    task2.cancel()

    with pytest.raises((asyncio.CancelledError, StopAsyncIteration)):
        await task2


@pytest.mark.asyncio
async def test_keepalive_aclose():
    """Test keepalive handles aclose()."""
    ka3 = keepalive(0.001)
    await ka3.__anext__()
    await ka3.aclose()  # Should close cleanly without issues.
