# SPDX-License-Identifier: AGPL-3.0-or-later
"""
BAML Environment Injection & Client Factory

All BAML client access flows through create_glossary_client() — the single
entry point that guarantees env vars are set BEFORE baml_client import.

Never import baml_client directly at module level. Always call the factory.
This eliminates the fragile "import must happen after configure()" race.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from baml_client.sync_client import BamlSyncClient

logger = logging.getLogger(__name__)

# Default model — free tier on Workers AI, routed through CF AI Gateway compat endpoint.
_DEFAULT_MODEL = "workers-ai/@cf/meta/llama-4-scout-17b-16e-instruct"
_DEFAULT_FALLBACK_MODEL = "gpt-4.1-mini"


def _inject_env() -> None:
    """Inject AI Gateway routing + fallback into environment for BAML client init.

    Safe to call multiple times — env vars are set only if not already present.

    Primary (CFGateway):
      - BAML_GLOSSARY_BASE_URL → CF Gateway /compat endpoint (Workers AI)
      - BAML_GLOSSARY_API_KEY   → Cloudflare API Token
      - BAML_GLOSSARY_MODEL     → Default: Llama-4-Scout free tier

    Fallback (CFGatewayOAI):
      - BAML_GLOSSARY_FALLBACK_BASE_URL  → CF Gateway /openai endpoint (BYOK)
      - BAML_GLOSSARY_FALLBACK_API_KEY   → CF AIG Authorization token
      - BAML_GLOSSARY_FALLBACK_MODEL     → Default: gpt-4.1-mini
    """
    account_id = settings.CLOUDFLARE_ACCOUNT_ID or settings.CF_ACCOUNT_ID
    gateway_id = settings.CLOUDFLARE_GATEWAY_ID or settings.CF_AI_GATEWAY_ID

    # ── Primary: CF Gateway /compat (Workers AI) ──────────────────────────
    if "BAML_GLOSSARY_BASE_URL" not in os.environ:
        os.environ["BAML_GLOSSARY_BASE_URL"] = (
            f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat"
        )

    if "BAML_GLOSSARY_API_KEY" not in os.environ:
        token = settings.CLOUDFLARE_API_TOKEN
        os.environ["BAML_GLOSSARY_API_KEY"] = token if isinstance(token, str) else ""

    if "BAML_GLOSSARY_MODEL" not in os.environ:
        os.environ["BAML_GLOSSARY_MODEL"] = os.environ.get(
            "BAML_GLOSSARY_MODEL_OVERRIDE", _DEFAULT_MODEL
        )

    # ── Fallback: CF Gateway /openai (BYOK) ───────────────────────────────
    if "BAML_GLOSSARY_FALLBACK_BASE_URL" not in os.environ:
        os.environ["BAML_GLOSSARY_FALLBACK_BASE_URL"] = (
            f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/openai"
        )

    if "BAML_GLOSSARY_FALLBACK_API_KEY" not in os.environ:
        # CF AIG Authorization token authenticates to the gateway itself;
        # the OpenAI key is injected by the gateway's BYOK config.
        aig = settings.CF_AIG_AUTHORIZATION
        os.environ["BAML_GLOSSARY_FALLBACK_API_KEY"] = aig if isinstance(aig, str) else ""

    if "BAML_GLOSSARY_FALLBACK_MODEL" not in os.environ:
        os.environ["BAML_GLOSSARY_FALLBACK_MODEL"] = _DEFAULT_FALLBACK_MODEL

    logger.debug(
        "BAML env injected: primary=%s fallback=%s",
        os.environ.get("BAML_GLOSSARY_BASE_URL", "")[:60],
        os.environ.get("BAML_GLOSSARY_FALLBACK_BASE_URL", "")[:60],
    )


def create_glossary_client() -> BamlSyncClient:
    """Create a BAML sync client with env vars guaranteed injected first.

    This is THE single entry point for accessing the BAML glossary client.
    Call it at function scope (never module scope) to avoid import races.

    Returns:
        BamlSyncClient configured with the GlossaryClient fallback chain.
    """
    _inject_env()

    # Late import — ONLY after env vars are set
    from baml_client.sync_client import b as _baml_client  # noqa: PLC0415

    return _baml_client


# Backward-compat alias — existing tests and code that call configure()
# are routed to the same env injection logic.
configure = _inject_env
