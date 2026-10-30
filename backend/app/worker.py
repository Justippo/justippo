"""
Cloudflare Python Worker entry point.

Wrangler flattens app/ to the bundle root (/session/metadata/), so
`api/`, `core/`, `main.py` etc. are all at the top level — but the
application code uses `from app.xxx import ...` everywhere.

Fix: inject a synthetic `app` namespace package whose __path__ points
at /session/metadata, so Python's import machinery resolves
`app.api`, `app.core`, etc. against the bundle root.
"""

import os
import sys
import types
from typing import Any

import asgi
from workers import WorkerEntrypoint

# ── Synthetic `app` namespace ─────────────────────────────────────────────────
# Wrangler places this file at /session/metadata/worker.py.
# Everything that was under app/ is now a sibling of this file.
# We need `import app.main` → finds /session/metadata/main.py, etc.
_bundle_root = "/session/metadata"

if "app" not in sys.modules:
    _app_ns = types.ModuleType("app")
    _app_ns.__path__ = [_bundle_root]
    _app_ns.__package__ = "app"
    _app_ns.__spec__ = None
    sys.modules["app"] = _app_ns

_asgi_app = None

# Env var names that Cloudflare injects as Worker bindings (vars + secrets).
# We copy them into os.environ so pydantic-settings can read them on startup.
# Bindings not present on the Worker are silently skipped — config.py defaults apply.
_ENV_BINDINGS = [
    "APP_SECRET_KEY",
    "APP_ENV",
    "APP_VERSION",
    "CF_ACCOUNT_ID",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_GATEWAY_ID",
    "CF_AIG_AUTHORIZATION",
    "MISTRAL_API_KEY",
    "CF_WORKERS_AI_API_TOKEN",
    "AZURE_DOCUMENT_INTELLIGENCE_ENABLED",
    "AZURE_DOCUMENT_INTELLIGENCE_TIER",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY",
    "AZURE_DOCUMENT_INTELLIGENCE_API_VERSION",
    "AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID",
    "AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S",
    "AZURE_DOCUMENT_INTELLIGENCE_POLL_INTERVAL_S",
    "AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS",
    "BABELDOC_ENABLED",
    "BABELDOC_SIDECAR_URL",
    "BABELDOC_AUTH_TOKEN",
    "MATRIX_ACCESS_TOKEN",
    "MATRIX_HOMESERVER_URL",
    "MATRIX_DEVICE_ID",
    "MATRIX_CLIENT_ID",
    "MATRIX_CLIENT_SECRET",
    "MATRIX_OAUTH_CALLBACK_URL",
    "MATRIX_OAUTH_POST_LOGIN_URL",
    "ENABLE_MATRIX_AUTH",
    "ENABLE_MATRIX_EXCHANGE",
    "HINDSIGHT_URL",
    "HINDSIGHT_API_URL",
    "HINDSIGHT_API_LLM_API_KEY",
    "BABELDOC_URL",
    "HINDSIGHT_ACCESS_KEY",
    "SENTRY_DSN",
    "DATADOG_API_KEY",
    "HF_API_TOKEN",
    "PUBLICAI_API_KEY",
    "RAG_LLM_MODEL",
    "RAG_LLM_MAX_TOKENS",
    "RAG_LLM_TIMEOUT_S",
    "EUROSTAT_API_URL",
]


def _bridge_env(env: Any) -> None:
    """Copy Cloudflare Worker env bindings into os.environ for pydantic-settings.

    Always overwrites — Worker secrets must win over .env file values that
    pywrangler may have loaded into os.environ before this code runs.

    Uses getattr() on self.env (official Pyodide pattern for env bindings).
    Bindings not present on the Worker are silently skipped — config.py defaults apply.
    """
    for key in _ENV_BINDINGS:
        val = getattr(env, key, None)
        if val is not None:
            os.environ[key] = str(val)


class Default(WorkerEntrypoint):
    async def on_fetch(self, request: Any, env: Any = None, ctx: Any = None) -> Any:
        global _asgi_app
        # Bridge bindings first so pydantic-settings sees them on first import.
        # self.env is the canonical way to access env bindings (Cloudflare docs).
        # The `env` parameter may be None in Pyodide — always use self.env.
        bridge_env = getattr(self, "env", None) or env
        if bridge_env is not None:
            _bridge_env(bridge_env)
        if _asgi_app is None:
            import starlette.datastructures
            from starlette.formparsers import MultiPartParser

            # Now resolves: /session/metadata/main.py → app.main
            from app.main import app as fastapi_app  # noqa: PLC0415

            # Patch Starlette's spool thresholds to prevent Pyodide threading crash on
            # multipart uploads >1 MB (cloudflare/workerd#6127). Pyodide has no thread
            # support, so Starlette's default 1 MB spool-to-thread path fails silently.
            # Raising both thresholds keeps file data in-memory at all times.
            starlette.datastructures.UploadFile.spool_max_size = 100 * 1024 * 1024  # type: ignore[attr-defined]
            MultiPartParser.spool_max_size = 100 * 1024 * 1024  # type: ignore[attr-defined]

            _asgi_app = fastapi_app

        # Bind this invocation's execution context so deeply nested monitoring
        # integrations can register background HTTP posts with ctx.waitUntil().
        # ContextVar isolation prevents concurrent requests in one isolate from
        # sharing callbacks. The synthetic app namespace injection above is
        # intentionally unchanged.
        from app.integrations.http_forwarder import (  # noqa: PLC0415
            bind_wait_until,
            reset_wait_until,
        )

        execution_ctx = getattr(self, "ctx", None) or ctx
        wait_until = getattr(execution_ctx, "waitUntil", None)
        wait_until_token = bind_wait_until(wait_until if callable(wait_until) else None)
        try:
            return await asgi.fetch(_asgi_app, request, self.env)
        finally:
            reset_wait_until(wait_until_token)

    async def on_scheduled(self, event: Any, env: Any = None, ctx: Any = None) -> None:
        """Daily Eurostat cache refresh (issue #232 Phase 3).

        Triggered by Cloudflare Cron Trigger (daily 6am UTC). Fetches
        fresh migration statistics from Eurostat and caches in D1 so
        the first user request each day gets an instant cache hit
        instead of a cold Eurostat API call.
        """
        bridge_env = getattr(self, "env", None) or env
        if bridge_env is not None:
            _bridge_env(bridge_env)

        import logging  # noqa: PLC0415

        logger = logging.getLogger(__name__)

        try:
            import httpx  # noqa: PLC0415

            from app.core.config import settings  # noqa: PLC0415
            from app.db.d1_client import D1Client  # noqa: PLC0415
            from app.repositories.eurostat_repo import EurostatRepo  # noqa: PLC0415

            # DRY: reuse the same Eurostat fetch + cache logic as the stats endpoint.
            # The scheduled handler runs outside an HTTP request scope, so we
            # construct D1Client from env bindings directly.
            db = D1Client.from_scope({"env": bridge_env})
            repo = EurostatRepo(db)

            # Check if a refresh is needed (within 23h = skip, avoids double-fetch)
            cached = await repo.get_fresh_snapshot()
            if cached is not None:
                logger.info("Eurostat cache still fresh — skipping scheduled refresh")
                return

            # Fetch from Eurostat
            filters = {
                "format": "JSON",
                "freq": "A",
                "citizen": "FOR_STLS",
                "sex": "T",
                "age": "TOTAL",
                "unit": "NR",
                "geo": ["DE", "FR", "IT", "ES", "NL", "AT", "BE", "PL", "SE", "EL", "EU27_2020"],
                "time": "2023",
            }
            parts = []
            for k, v in filters.items():
                if isinstance(v, list):
                    for item in v:
                        parts.append(f"{k}={item}")
                else:
                    parts.append(f"{k}={v}")
            params = "&".join(parts)
            url = f"{settings.EUROSTAT_API_URL}?{params}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                data = resp.json()
                await repo.save_snapshot(data)
                logger.info("Eurostat scheduled refresh succeeded")
            else:
                logger.warning("Eurostat scheduled refresh failed: HTTP %d", resp.status_code)

        except Exception as exc:
            logger.warning("Eurostat scheduled refresh error: %s", exc)
