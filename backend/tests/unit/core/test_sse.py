import asyncio

import pytest

from app.core.sse import KEEPALIVE_INTERVAL, keepalive, sse_frame


def test_sse_frame_string():
    result = sse_frame("message", "hello world")
    assert result == "event: message\ndata: hello world\n\n"


def test_sse_frame_dict():
    result = sse_frame("update", {"key": "value", "unicode": "✓"})
    assert result == 'event: update\ndata: {"key": "value", "unicode": "✓"}\n\n'


def test_sse_frame_empty_string():
    result = sse_frame("empty", "")
    assert result == "event: empty\ndata: \n\n"


def test_sse_frame_list():
    result = sse_frame("list", [1, 2, 3])
    assert result == "event: list\ndata: [1, 2, 3]\n\n"


@pytest.mark.asyncio
async def test_keepalive_yields_ping():
    # Use a very short interval for testing
    ka = keepalive(expected_interval=0.01)

    # Get the first item
    first_ping = await anext(ka)
    assert first_ping == ": ping\n\n"

    # Clean up
    await ka.aclose()


@pytest.mark.asyncio
async def test_keepalive_cancellation():
    ka = keepalive(expected_interval=0.01)

    task = asyncio.create_task(anext(ka))

    # Cancel the task
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    await ka.aclose()


@pytest.mark.asyncio
async def test_keepalive_default_interval():
    # Test that it uses KEEPALIVE_INTERVAL when no interval is provided
    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock) as mock_sleep:
        ka = keepalive()

        first_ping = await anext(ka)
        assert first_ping == ": ping\n\n"

        mock_sleep.assert_called_once_with(KEEPALIVE_INTERVAL)

        await ka.aclose()
