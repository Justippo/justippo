# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Shared HTTP Forwarder

Used by the Sentry, Datadog, Laminar, and Langfuse integrations to POST
payloads asynchronously without blocking the request path. In Cloudflare
Workers, the request-scoped execution context registers each post with
``ctx.waitUntil()`` so the runtime does not cancel it when the response
finishes.

DRY principle: this module is the single place where httpx async POST +
asyncio.create_task + Cloudflare waitUntil + no-loop fallback logic lives.
Sentry, Datadog, Laminar, and Langfuse all import from here — zero duplication.
Datadog's terminal SSE stage batch also uses the bounded ``post_now`` path so
the payload completes before the stream's ``done`` event is emitted.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any

logger = logging.getLogger(__name__)

WaitUntil = Callable[[Awaitable[None]], Any]

# Cloudflare may serve concurrent requests in one isolate. ContextVar keeps the
# execution-context callback request-local while still allowing deeply nested
# integrations to use the shared forwarder without threading ctx through every
# service and middleware signature.
_wait_until: ContextVar[WaitUntil | None] = ContextVar("http_forwarder_wait_until", default=None)


def bind_wait_until(callback: WaitUntil | None) -> Token[WaitUntil | None]:
    """Bind a Cloudflare ``ctx.waitUntil`` callback for the current request."""
    return _wait_until.set(callback)


def reset_wait_until(token: Token[WaitUntil | None]) -> None:
    """Restore the prior request context after the ASGI invocation completes."""
    _wait_until.reset(token)


async def fire_and_forget(
    url: str,
    headers: dict[str, str],
    content: bytes | str | dict[str, Any],
    *,
    timeout: float = 5.0,
) -> None:
    """POST a payload asynchronously, never blocking or raising.

    Creates an asyncio task to detach from the caller's flow. In Cloudflare,
    registers that task with the current request's ``ctx.waitUntil`` callback.
    If registration fails or no running loop exists, awaits the POST directly
    rather than silently dropping observability data. Any transport error is
    logged at DEBUG level — monitoring remains best-effort.

    Args:
        url:     Target URL for the POST request.
        headers: HTTP headers (must include auth + content-type).
        content: Request body — bytes, str, or dict (auto-serialized to JSON).
        timeout: Max seconds to wait for the POST (default 5s).
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available — cannot ship to %s", url)
        return

    if isinstance(content, dict):
        import json

        content = json.dumps(content, separators=(",", ":"))

    post = _post(url, headers, content, timeout, httpx)
    wait_until = _wait_until.get()
    if wait_until is not None:
        try:
            # Pass the coroutine itself across the Pyodide FFI boundary. This
            # matches Cloudflare's Python waitUntil contract; an asyncio Task
            # is not a JavaScript-compatible promise proxy.
            wait_until(post)
            return
        except Exception:  # noqa: BLE001 — fall back without failing request
            logger.debug("ctx.waitUntil registration failed — awaiting POST", exc_info=True)
            await post
            return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(post)
    except RuntimeError:
        # No running loop (e.g. unusual startup/test context).
        # Fall back to awaiting rather than dropping the event.
        await post
    except Exception:  # noqa: BLE001 — best-effort, never raise
        logger.debug("Failed to schedule fire-and-forget POST to %s", url, exc_info=True)


async def post_now(
    url: str,
    headers: dict[str, str],
    content: bytes | str | dict[str, Any],
    *,
    timeout: float = 5.0,
) -> None:
    """Complete one bounded best-effort POST before returning."""
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available — cannot ship to %s", url)
        return

    if isinstance(content, dict):
        import json

        content = json.dumps(content, separators=(",", ":"))

    await _post(url, headers, content, timeout, httpx)


async def _post(
    url: str,
    headers: dict[str, str],
    content: bytes | str,
    timeout: float,
    httpx_module: Any,
) -> None:
    """Perform the actual httpx POST with a short timeout."""
    try:
        async with httpx_module.AsyncClient(timeout=timeout) as client:
            await client.post(url, content=content, headers=headers)
    except Exception:
        logger.debug("Fire-and-forget POST to %s failed (best-effort)", url, exc_info=True)
