# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Apertus 8B Adapter — Sovereign LLM for RAG Answer Generation

Architecture: Apertus (Swiss sovereign LLM, Apache 2.0) is accessed **free** via
the **Public AI Inference Utility** over two OpenAI-compatible routes, resolved
by ``_resolve_route()`` in priority order:

  1. **Direct** (preferred) — the Public AI platform at ``api.publicai.co/v1``
     when ``PUBLICAI_API_KEY`` is set. Genuinely free sovereign utility, no
     HuggingFace metering. Model id ``swiss-ai/apertus-8b-instruct``.
  2. **HF router** (fallback) — ``router.huggingface.co/v1`` with the
     ``:publicai`` model suffix when only ``HF_API_TOKEN`` is set. Public AI is
     the sole free provider here, but HF meters it against the account's monthly
     included credits (``402 depleted your monthly included credits`` once used up).

Both URLs are centralized in ``app/integrations/cloudflare/gateway.py``
(REM-8 compliant — no direct provider URLs in this module). See
``gateway.get_publicai_url()`` and ``gateway.get_hf_router_url()`` for rationale.

Why NOT the CF AI Gateway huggingface provider: it proxies HuggingFace's legacy
Serverless Inference API, which HF deprecated and now bills as paid wholesale
(the ``402 Insufficient wholesale credits`` / CF 1016 errors).

HTTP boundary: Uses httpx only (Pyodide-safe). No HuggingFace SDK import —
same isolation principle as the BabelDOC adapter (ADR-012).

No-op contract: If BOTH ``PUBLICAI_API_KEY`` and ``HF_API_TOKEN`` are unset,
``generate_answer()`` returns ``None`` and the caller skips answer generation.
Same graceful-degradation pattern as Sentry, Datadog, and D1Client.

Prompt injection safety: Callers MUST pass retrieved chunks through
``build_rag_prompt()`` (Layer 2 defense) before sending to this adapter.
This adapter forwards that prompt as a single OpenAI ``user`` message; the
router applies Apertus's chat template server-side.

References:
  - Apertus model: https://huggingface.co/swiss-ai/Apertus-8B-Instruct-2509
  - Public AI (direct): https://platform.publicai.co
  - Public AI (HF router): https://huggingface.co/docs/inference-providers/providers/publicai
  - ADR-014 (candidate): Apertus integration strategy
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from app.integrations.cloudflare.gateway import get_hf_router_url, get_publicai_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class ApertusResponse:
    """Successful response from Apertus answer generation."""

    answer: str
    model: str
    processing_time_ms: float


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Public AI = the only free public inference provider on the HF router.
_PUBLICAI_PROVIDER = "publicai"
# Model id on the DIRECT Public AI platform (api.publicai.co) — no provider suffix.
_PUBLICAI_DIRECT_MODEL = "swiss-ai/apertus-8b-instruct"
# Model id on the HF Inference Providers router — carries the ``:publicai`` suffix
# to force the free Public AI provider. Used when only HF_API_TOKEN is set.
_DEFAULT_APERTUS_MODEL = f"swiss-ai/Apertus-8B-Instruct-2509:{_PUBLICAI_PROVIDER}"
# Public AI's platform requires a non-empty User-Agent header on every request.
_USER_AGENT = "EvidenceEU/1.0 (+https://github.com/evidence-eu)"

# System message — grounds Apertus for factual, document-based answers.
_SYSTEM_MSG = (
    "You are Apertus, a helpful multilingual assistant created by the Swiss AI "
    "initiative. Answer strictly from the provided context. If the context does "
    "not contain the answer, say so."
)


@dataclass(frozen=True)
class _Route:
    """A resolved Apertus inference route: where to POST, how to auth, which model."""

    name: str
    url: str
    headers: dict[str, str]
    model: str


def _get_settings() -> Any:
    """Lazy import settings to avoid circular deps at module load."""
    from app.core.config import settings

    return settings


def _resolve_hf_model() -> str:
    """Resolve the Apertus model id for the HF router, ensuring a ``:publicai`` suffix.

    ``RAG_LLM_MODEL`` is shared with the Workers AI answer-gen provider, so when
    ``RAG_LLM_PROVIDER == "huggingface"`` it may still hold a ``@cf/...`` default.
    In that case (or when empty) fall back to the Apertus model on Public AI.
    An explicit HF model without a provider suffix gets ``:publicai`` appended so
    inference stays on the free tier.
    """
    model = (_get_settings().RAG_LLM_MODEL or "").strip()
    if not model or model.startswith("@cf/"):
        return _DEFAULT_APERTUS_MODEL
    if ":" not in model:
        return f"{model}:{_PUBLICAI_PROVIDER}"
    return model


def _resolve_route() -> _Route | None:
    """Resolve the active Apertus route in priority order, or None if disabled.

    Priority:
      1. ``PUBLICAI_API_KEY`` → direct Public AI platform (preferred, unmetered).
      2. ``HF_API_TOKEN``     → HF Inference Providers router (metered fallback).

    No-op contract: returns ``None`` when neither credential is set.
    """
    settings = _get_settings()

    publicai_key = settings.PUBLICAI_API_KEY.strip()
    if publicai_key:
        return _Route(
            name="publicai-direct",
            url=get_publicai_url(),
            headers={
                "Authorization": f"Bearer {publicai_key}",
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
            model=_PUBLICAI_DIRECT_MODEL,
        )

    hf_token = settings.HF_API_TOKEN.strip()
    if hf_token:
        return _Route(
            name="hf-router",
            url=get_hf_router_url(),
            headers={
                "Authorization": f"Bearer {hf_token}",
                "Content-Type": "application/json",
            },
            model=_resolve_hf_model(),
        )

    return None


def is_enabled() -> bool:
    """Return True if Apertus answer generation is configured.

    No-op contract: returns False when neither PUBLICAI_API_KEY nor HF_API_TOKEN
    is set. Callers check this before calling ``generate_answer()``.
    """
    return _resolve_route() is not None


def model_name() -> str | None:
    """Return the resolved Apertus model without exposing route credentials."""
    route = _resolve_route()
    return route.model if route is not None else None


def _build_payload(prompt: str, model: str, max_tokens: int, *, stream: bool) -> dict[str, Any]:
    """Build the OpenAI-compatible chat-completions payload for Apertus."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,  # Low temp for factual grounded answers
        "top_p": 0.9,  # Model card recommends 0.9
        "stream": stream,
    }


# Special tokens Apertus may echo in output. The OpenAI router normally strips
# these, but we defensively clean them so the frontend never sees control tokens.
_APERTUS_SPECIAL_TOKENS: tuple[str, ...] = (
    "<|system_start|>",
    "<|system_end|>",
    "<|developer_start|>",
    "<|developer_end|>",
    "<|user_start|>",
    "<|user_end|>",
    "<|assistant_start|>",
    "<|assistant_end|>",
    "<|inner_prefix|>",
    "<|inner_suffix|>",
    "<|tools_prefix|>",
    "<|tools_suffix|>",
    "<|image|>",
    "<|begin_of_text|>",
    "<|end_of_text|>",
)


def _strip_special_tokens(text: str) -> str:
    """Remove any Apertus special tokens from generated text and trim whitespace."""
    cleaned = text
    for token in _APERTUS_SPECIAL_TOKENS:
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


async def generate_answer(prompt: str) -> ApertusResponse | None:
    """Generate a grounded answer via Apertus 8B on Public AI (free tier).

    No-op contract: returns ``None`` if ``HF_API_TOKEN`` is not set.

    Args:
        prompt: Full RAG prompt from ``build_rag_prompt()`` — must include
            SYSTEM instruction, retrieved context (delimited), and user query.

    Returns:
        ApertusResponse with the generated answer, or ``None`` if disabled.

    Raises:
        RuntimeError: If the router request fails or returns a non-200 status.
            Callers should catch this and degrade gracefully (return chunks
            without an answer).
    """
    settings = _get_settings()
    route = _resolve_route()

    if route is None:
        logger.debug(
            "Apertus answer generation skipped — neither PUBLICAI_API_KEY nor HF_API_TOKEN set"
        )
        return None

    model = route.model
    max_tokens = settings.RAG_LLM_MAX_TOKENS
    timeout_s = settings.RAG_LLM_TIMEOUT_S

    url = route.url
    headers = route.headers
    payload = _build_payload(prompt, model, max_tokens, stream=False)

    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required for Apertus adapter") from exc

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            start = time.perf_counter()
            resp = await client.post(url, json=payload, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000

        if resp.status_code != 200:
            logger.error(
                "Apertus generation failed — status=%d model=%s body=%s",
                resp.status_code,
                model,
                resp.text[:300],
            )
            raise RuntimeError(
                f"Apertus generation failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error(
                "Apertus returned non-JSON response — status=%d body=%s",
                resp.status_code,
                resp.text[:200],
            )
            raise RuntimeError(
                f"Apertus returned non-JSON response (HTTP {resp.status_code})"
            ) from exc

        answer_text = _parse_chat_completion(data)
        answer_text = _strip_special_tokens(answer_text)

        if not answer_text:
            logger.warning("Apertus returned empty content — model=%s", model)

        logger.info(
            "Apertus answer generated — model=%s tokens=%d time_ms=%.0f",
            model,
            len(answer_text.split()),
            elapsed_ms,
        )

        return ApertusResponse(
            answer=answer_text,
            model=model,
            processing_time_ms=elapsed_ms,
        )

    except httpx.TimeoutException as exc:
        logger.error("Apertus request timed out after %ds — model=%s", timeout_s, model)
        raise RuntimeError(f"Apertus request timed out after {timeout_s}s") from exc
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to Apertus route %s — url=%s", route.name, url)
        raise RuntimeError(f"Cannot connect to Apertus route {route.name}: {exc}") from exc
    except httpx.HTTPError as exc:
        logger.error("Apertus HTTP error — model=%s: %s", model, exc)
        raise RuntimeError(f"Apertus HTTP error: {exc}") from exc


def _parse_chat_completion(data: Any) -> str:
    """Extract assistant content from an OpenAI-compatible chat completion body."""
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
    logger.warning("Apertus returned unexpected response shape: %s", str(data)[:200])
    return ""


async def generate_answer_stream(prompt: str) -> AsyncGenerator[str, None]:
    """Generate a grounded answer via Apertus 8B on Public AI, streaming tokens.

    No-op contract: yields nothing if ``HF_API_TOKEN`` is not set.

    Args:
        prompt: Full RAG prompt from ``build_rag_prompt()``.

    Yields:
        Generated text deltas as they arrive.
    """
    settings = _get_settings()
    route = _resolve_route()

    if route is None:
        logger.debug(
            "Apertus streaming generation skipped — neither PUBLICAI_API_KEY nor HF_API_TOKEN set"
        )
        return

    model = route.model
    max_tokens = settings.RAG_LLM_MAX_TOKENS
    timeout_s = settings.RAG_LLM_TIMEOUT_S

    url = route.url
    headers = route.headers
    payload = _build_payload(prompt, model, max_tokens, stream=True)

    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required for Apertus adapter") from exc

    try:
        async with (
            httpx.AsyncClient(timeout=timeout_s) as client,
            client.stream("POST", url, json=payload, headers=headers) as resp,
        ):
            if resp.status_code != 200:
                error_body = await resp.aread()
                logger.error(
                    "Apertus streaming generation failed — status=%d model=%s body=%s",
                    resp.status_code,
                    model,
                    error_body[:300],
                )
                raise RuntimeError(
                    f"Apertus streaming generation failed (HTTP {resp.status_code}): "
                    f"{error_body[:200].decode(errors='ignore')}"
                )

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    continue
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning("Failed to decode SSE data line: %s", data_str[:100])
                    continue

                delta_text = _parse_stream_delta(data)
                if delta_text:
                    cleaned = _strip_special_tokens(delta_text)
                    if cleaned:
                        yield cleaned

    except httpx.TimeoutException as exc:
        logger.error("Apertus streaming request timed out after %ds — model=%s", timeout_s, model)
        raise RuntimeError(f"Apertus request timed out after {timeout_s}s") from exc
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to Apertus route %s — url=%s", route.name, url)
        raise RuntimeError(f"Cannot connect to Apertus route {route.name}: {exc}") from exc
    except httpx.HTTPError as exc:
        logger.error("Apertus HTTP error — model=%s: %s", model, exc)
        raise RuntimeError(f"Apertus HTTP error: {exc}") from exc


def _parse_stream_delta(data: Any) -> str:
    """Extract the incremental content delta from an OpenAI-compatible SSE chunk."""
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
    return ""
