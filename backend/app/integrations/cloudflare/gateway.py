# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Cloudflare AI Gateway Proxy Routing

All LLM calls in this codebase must go through this proxy function to ensure they are
logged, cached, and metered correctly by the Cloudflare AI Gateway. Never make direct
provider-specific endpoint requests.

Routing rule:
- Base: https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}
- If a specific model or sub-path is required, append it.

BYOK (Bring Your Own Key):
- Provider API keys are stored in Cloudflare Secrets Store via the dashboard.
- When BYOK is configured, the gateway injects the provider key automatically.
- Local/dev requests need cf-aig-authorization header to authenticate to the gateway.
- Production uses provider-native HTTPS gateway URLs, so it also sends this header.

Account ID note:
- In Pyodide (Cloudflare Python Workers), pywrangler's [vars] are NOT always
  reachable via getattr(env, ...) before the settings singleton is frozen.
- The account_id is not a secret (it appears in the public wrangler.toml), so
  a module-level fallback is safe and prevents empty-segment URL errors (code 2035).
"""

import os

from app.core.config import settings

# Public Cloudflare account ID — NOT a secret.
# Already committed in backend/wrangler.toml. Used as a fallback when the
# pydantic Settings singleton is frozen before env bindings are bridged.
_CF_ACCOUNT_ID_FALLBACK = "9f26393d5ba4186296b36e2af8714b1c"
_CF_GATEWAY_ID_FALLBACK = "evidence-eu-gateway"


def get_gateway_url(provider: str, model: str) -> str:
    """
    Constructs the correct AI Gateway URL for a given provider and model.

    Priority order for account_id:
      1. CLOUDFLARE_ACCOUNT_ID / CF_ACCOUNT_ID env var (via pydantic Settings)
      2. os.environ direct read (catches late-bridged vars on warm Workers)
      3. Module-level fallback constant (public value, already in wrangler.toml)
    """
    account_id = (
        settings.CLOUDFLARE_ACCOUNT_ID
        or settings.CF_ACCOUNT_ID
        or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        or os.environ.get("CF_ACCOUNT_ID")
        or _CF_ACCOUNT_ID_FALLBACK
    )
    gateway_id = (
        settings.CLOUDFLARE_GATEWAY_ID
        or settings.CF_AI_GATEWAY_ID
        or os.environ.get("CLOUDFLARE_GATEWAY_ID")
        or os.environ.get("CF_AI_GATEWAY_ID")
        or _CF_GATEWAY_ID_FALLBACK
    )

    if not account_id:
        raise RuntimeError(
            "Cloudflare account_id is empty — cannot construct AI Gateway URL. "
            "Set CLOUDFLARE_ACCOUNT_ID in wrangler.toml [vars] or as a Worker secret."
        )

    base_url = f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}"
    if model:
        return f"{base_url}/{model}"
    return base_url


def get_hf_router_url() -> str:
    """Return the HuggingFace Inference Providers router URL (OpenAI-compatible).

    Centralized here to satisfy REM-8 (all LLM provider URLs live in gateway.py).

    Why not the CF AI Gateway ``huggingface`` provider? That provider proxies the
    LEGACY ``api-inference.huggingface.co/models/`` Serverless Inference API, which
    HuggingFace has deprecated and now bills as paid wholesale — the source of the
    ``402 Insufficient wholesale credits`` / Cloudflare 1016 errors seen with
    Apertus. The new HF Inference Providers router (``router.huggingface.co/v1``)
    is the only path to the **Public AI** provider, the sole *free* public
    inference provider on HuggingFace, which hosts Apertus (Swiss sovereign LLM).

    The route is OpenAI-compatible chat completions; callers append no path and
    select Public AI via the ``:publicai`` model suffix (e.g.
    ``swiss-ai/Apertus-8B-Instruct-2509:publicai``).

    Reference: https://huggingface.co/docs/inference-providers/providers/publicai
    """
    return "https://router.huggingface.co/v1/chat/completions"


def get_publicai_url() -> str:
    """Return the Public AI Inference Utility URL (OpenAI-compatible chat completions).

    Centralized here to satisfy REM-8 (all LLM provider URLs live in gateway.py).

    This is the **direct** Public AI platform (``api.publicai.co``), a sovereign,
    genuinely-free inference utility (Swiss AI initiative) hosting Apertus 8B. It
    is the preferred Apertus route because it bypasses HuggingFace's monthly
    included-credit metering on the Inference Providers router (which returns
    ``402 You have depleted your monthly included credits`` once the HF account
    allowance is exhausted — see ``get_hf_router_url``).

    Auth: Bearer ``PUBLICAI_API_KEY`` plus a required ``User-Agent`` header.
    Model id on this platform: ``swiss-ai/apertus-8b-instruct`` (no ``:publicai``
    suffix — that suffix is HF-router-only). Free tier is rate-limited
    (~20 req/min), sufficient for demo and capstone use.

    Reference: https://platform.publicai.co (API keys via SSO → /settings/api-keys)
    """
    return "https://api.publicai.co/v1/chat/completions"


def get_gateway_auth_headers() -> dict[str, str]:
    """Return auth headers for Cloudflare AI Gateway requests.

    When BYOK is configured in the dashboard, the gateway injects the provider
    key from Secrets Store. We send cf-aig-authorization to authenticate to the
    gateway itself. Cloudflare Workers are pre-authenticated only when using an
    AI Gateway binding; this app uses provider-native HTTPS gateway URLs.

    Returns an empty dict when CF_AIG_AUTHORIZATION is not set (e.g., in CI).
    """
    token = (settings.CF_AIG_AUTHORIZATION or os.environ.get("CF_AIG_AUTHORIZATION") or "").strip()
    if token:
        return {"cf-aig-authorization": f"Bearer {token}"}
    return {}
