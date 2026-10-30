"""
Cloudflare Python Worker entry point (backend/ root level).

Placed at backend/ root so `app/` is bundled as a proper Python package.
The wrangler.toml [[rules]] block restricts bundling to app/ + this file,
preventing the .venv from inflating the upload.
"""

from typing import Any

import asgi
from workers import WorkerEntrypoint

_app = None


class Default(WorkerEntrypoint):  # type: ignore[misc]
    async def on_fetch(self, request: Any, env: Any = None, ctx: Any = None) -> Any:
        global _app
        if _app is None:
            from app.main import app  # noqa: PLC0415

            _app = app
        return await asgi.fetch(_app, request, self.env)
