# SPDX-License-Identifier: AGPL-3.0-or-later
"""
SSE Utilities — Frame Encoding + Keepalive (Sprint 2)

Shared primitives for Server-Sent Events across all endpoints.
Extracted to core so translation-progress SSE (Sprint 3) can reuse.

Surface:
  sse_frame()        – Encode a single typed SSE frame.
  keepalive()        – AsyncGenerator yielding ``: ping`` comment lines.
  KEEPALIVE_INTERVAL – Seconds between pings (matches FastAPI routing.py).

Conventions:
  - Comment format ``: ping\n\n`` matches FastAPI's built-in
    EventSourceResponse (fastapi/routing.py _PING_INTERVAL = 15.0).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

# Matches FastAPI's built-in ping interval (fastapi.routing._PING_INTERVAL).
# Using the same format means client-side handling is identical whether
# we use StreamingResponse + our generator or EventSourceResponse directly.
KEEPALIVE_INTERVAL: float = 15.0


def sse_frame(event: str, data: Any) -> str:
    """
    Encode a single SSE frame per the W3C EventSource spec.

        event: <type>\\n
        data: <json>\\n
        \\n

    Strings are passed as-is (no extra quoting).
    """
    serialised = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {serialised}\n\n"


async def keepalive(expected_interval: float | None = None) -> AsyncGenerator[str, None]:
    """
    Yield ``: ping`` SSE comment lines every *interval* seconds until cancelled.

    SSE comments (lines beginning with ``:``) are ignored by the browser's
    EventSource API but keep the TCP connection alive through proxies
    (Cloudflare, nginx) during long gaps between data events.

    Cancel the generator (via ``ag.aclose()`` or task cancellation) when
    the main SSE stream ends to avoid leaking the background loop.

    Usage (with asyncio.Queue merging — Sprint 3 pattern)::

        ka = keepalive()
        async for frame in ka:
            queue.put(frame)
    """
    interval = KEEPALIVE_INTERVAL if expected_interval is None else expected_interval
    try:
        while True:
            await asyncio.sleep(interval)
            yield ": ping\n\n"
    except asyncio.CancelledError:
        pass
