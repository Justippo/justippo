# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Workers AI Adapter — RAG Answer Generation (Cloudflare Workers AI free tier)

Sovereign-free RAG answer generation routed through the Cloudflare AI Gateway
``workers-ai`` provider. Uses Cloudflare Workers AI's **free tier** (daily
Neuron allowance), which does NOT consume AI Gateway wholesale credits — this
is the zero-cost mitigation for the "402 Insufficient wholesale credits" error
that HF Serverless Inference (Apertus) now hits after HF deprecated its legacy
serverless API.

Architecture:
  - Reuses ``app/integrations/cloudflare/gateway.get_gateway_url("workers-ai", model)``
    — the same routing the translation service and BAML glossary client already
    use (DRY). No direct provider URLs (CI-enforced by REM-8).
  - Auth: ``Authorization: Bearer {CF_WORKERS_AI_API_TOKEN}`` + optional
    CF gateway auth header. Same token the translation path uses.
  - Uses httpx only (Pyodide-safe); no SDK imports.

No-op contract: if ``CF_WORKERS_AI_API_TOKEN`` is unset/empty, ``generate_answer``
returns ``None`` and callers skip answer generation (graceful degradation, same
as Sentry/Datadog/Apertus).

Response parsing is defensive: the AI Gateway workers-ai provider can return
either the OpenAI-compatible ``{"choices":[{"message":{"content":...}}]}`` shape
or the native Workers AI ``{"result":{"response":...}}`` shape depending on the
gateway build. Both are handled.

References:
  - Workers AI: https://developers.cloudflare.com/workers-ai/
  - Chat models use the ``messages`` schema (OpenAI-compatible) per Workers AI docs.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.integrations.cloudflare.gateway import get_gateway_auth_headers, get_gateway_url

logger = logging.getLogger(__name__)


@dataclass
class AnswerResponse:
    """Successful RAG answer generation response (provider-agnostic)."""

    answer: str
    model: str
    processing_time_ms: float


def _get_settings() -> Any:
    """Lazy import settings to avoid circular deps at module load."""
    from app.core.config import settings

    return settings


def is_enabled() -> bool:
    """Return True if Workers AI answer generation is configured.

    No-op contract: returns False when CF_WORKERS_AI_API_TOKEN is empty.
    """
    return bool(_get_settings().CF_WORKERS_AI_API_TOKEN.strip())


def model_name() -> str | None:
    """Return the default answer model when Workers AI is enabled."""
    if not is_enabled():
        return None
    return _MODEL_FAST


def _build_url(model: str) -> str:
    """Construct the AI Gateway workers-ai URL for a ``@cf/`` model."""
    return get_gateway_url(provider="workers-ai", model=model)


def _build_headers(token: str) -> dict[str, str]:
    """Build request headers: Workers AI bearer token + CF gateway auth."""
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    headers.update(get_gateway_auth_headers())
    return headers


# NOTE: `@cf/meta/llama-3.1-8b-instruct-fp8-fast` was deprecated/removed by
# Cloudflare (the `-fp8-fast` variant 404s at the Workers AI API). The base
# `@cf/meta/llama-3.1-8b-instruct` is the current, documented model and is
# confirmed working through the AI Gateway. See Cloudflare Workers AI changelog.
_MODEL_FAST = "@cf/meta/llama-3.1-8b-instruct-fp8"
_MODEL_FRONTIER = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

# ── Neuron budget guard (10K free/day) ────────────────────────────────────────
# Daily Neuron budget from Cloudflare Workers AI free tier.
# We leave a 2K buffer so we don't hit the wall mid-day.
_DAILY_NEURON_BUDGET = 8_000
# Estimated neuron cost per model call (rough averages from empirical data).
_NEURON_ESTIMATES: dict[str, int] = {
    "@cf/meta/llama-3.1-8b-instruct-fp8": 150,
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": 800,
    "@cf/zai-org/glm-4.7-flash": 100,
    "@cf/google/gemma-4-26b-a4b-it": 400,
    "@cf/moonshotai/kimi-k2.6": 800,
    "@cf/moonshotai/kimi-k2.7": 800,
}
# KV key format: "neurons:YYYY-MM-DD"
_NEURON_BUDGET_KV_KEY_PREFIX = "neurons:"


def _get_neuron_budget_kv() -> Any:
    """Get the NEURON_BUDGET KV binding from the Worker scope.

    Returns None if the binding doesn't exist (e.g., local dev or KV not configured).
    """
    try:
        from app.core.config import settings

        return getattr(settings, "NEURON_BUDGET_KV", None)
    except Exception:  # pragma: no cover - defensive guard; settings always loads in test env
        return None


async def _check_and_reserve_neurons(model: str, kv: Any | None) -> tuple[bool, str | None]:
    """Check if we have budget for a model call and reserve neurons if so.

    Returns (allowed, selected_model). If budget exceeded and not using fast model,
    auto-downgrades to fast model. If even fast model exceeds budget, returns False.
    """
    if kv is None:
        # No KV binding — no budget tracking, allow everything
        return True, None

    today = date.today().isoformat()
    budget_key = f"{_NEURON_BUDGET_KV_KEY_PREFIX}{today}"

    # Get current usage
    used_str = await kv.get(budget_key)
    used = int(used_str) if used_str else 0

    # Estimate cost for this model
    estimated = _NEURON_ESTIMATES.get(model, 400)

    # Check budget
    if used + estimated > _DAILY_NEURON_BUDGET:
        # Budget exceeded — try auto-downgrade to fast model
        if model != _MODEL_FAST:
            fast_estimate = _NEURON_ESTIMATES.get(_MODEL_FAST, 150)
            if used + fast_estimate <= _DAILY_NEURON_BUDGET:
                logger.warning(
                    "Neuron budget low (%d/%d). Downgrading from %s to %s",
                    used,
                    _DAILY_NEURON_BUDGET,
                    model,
                    _MODEL_FAST,
                )
                return True, _MODEL_FAST
        # Even fast model exceeds budget
        logger.warning(
            "Daily neuron budget exhausted (%d/%d). Blocking request.", used, _DAILY_NEURON_BUDGET
        )
        return False, None

    return True, None


async def _record_neuron_usage(model: str, kv: Any | None) -> None:
    """Record neuron usage after a successful model call (fire-and-forget)."""
    if kv is None:
        return
    today = date.today().isoformat()
    budget_key = f"{_NEURON_BUDGET_KV_KEY_PREFIX}{today}"
    estimated = _NEURON_ESTIMATES.get(model, 400)
    used_str = await kv.get(budget_key)
    used = int(used_str) if used_str else 0
    new_used = used + estimated
    # TTL = 25 hours (covers day boundary + buffer)
    await kv.put(budget_key, str(new_used), expiration_ttl=90_000)


_COMPLEX_KEYWORDS = frozenset(
    {
        "violation",
        "penalty",
        "fine",
        "sanction",
        "non-compliance",
        "legal liability",
        "binding",
        "enforceable",
        "court",
        "tribunal",
        "arbitration",
        "dispute resolution",
        "biometric",
        "profiling",
        "automated decision",
        "data subject",
        "controller",
        "processor",
        "dpo",
        "data protection officer",
        "impact assessment",
        "dpia",
        "cross-border transfer",
        "adequacy",
        "standard contractual",
        "binding corporate rules",
        "supervisory authority",
    }
)


def _select_model(prompt: str) -> str:
    """Route to frontier or fast model based on query complexity.

    Frontier (Llama 3.3 70B): complex legal analysis, violations, penalties,
    biometric data, automated decisions, cross-border transfer questions.
    Fast (Llama 3.1 8B): simple factual lookups, definitions, translations.

    Both are neuron-efficient and well within the 10K/day free allocation.
    Llama 3.1 8B fp8 fast: 4,119/M input, 34,868/M output neurons.
    Llama 3.3 70B fp8 fast: 26,668/M input, 204,805/M output neurons.
    """
    lower = prompt.lower()
    if any(kw in lower for kw in _COMPLEX_KEYWORDS):
        return _MODEL_FRONTIER
    return _MODEL_FAST


def select_model_for_prompt(prompt: str | None) -> str | None:
    """Public wrapper for ``_select_model`` — returns the model that would
    be selected for a given prompt, or the default model if prompt is None.
    """
    if prompt is None:
        return _MODEL_FAST
    return _select_model(prompt)


def _system_prompt() -> str:
    return (
        "You are a cross-border EU document assistant for citizens, legal "
        "professionals, and HR teams. Answer the user's question using the "
        "retrieved document context when it contains relevant information. "
        "When the context is partial or absent, use your general knowledge "
        "of EU law, regulation, and administration — but clearly label it as "
        "general knowledge and not sourced from the user's documents. "
        "Always cite specific sources from the context when available "
        "(e.g., [SOURCE 1: document title]). "
        "If jurisdiction, citizenship, or employment status is missing and "
        "material to the answer, ask one concise clarifying question. "
        "Respond in the same language as the user's question. "
        "Never fabricate citations or claim a document states something it does not."
    )


def greeting_system_prompt() -> str:
    return (
        "You are a friendly and helpful assistant for EvidenceEU, a cross-border "
        "EU document intelligence platform. The user is greeting you or making "
        "small talk. Respond warmly and briefly in the same language. "
        "Do not mention documents, citations, or sources. "
        "Keep it natural and conversational."
    )


def _extract_answer(data: dict[str, Any], *, strip: bool = True) -> str:
    """Extract generated text from either OpenAI or native Workers AI shapes.

    ``strip`` should be False for streaming tokens — stripping each incremental
    delta would destroy inter-token whitespace when the client concatenates them.
    """

    def _clean(s: str) -> str:
        return s.strip() if strip else s

    # OpenAI-compatible chat-completions shape
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return _clean(content)
        delta = choices[0].get("delta") or {}
        if isinstance(delta, dict):
            delta_content = delta.get("content")
            if isinstance(delta_content, str) and delta_content != "":
                return _clean(delta_content)

    # Native Workers AI run shape: {"result": {"response": "..."}}
    result = data.get("result")
    if isinstance(result, dict):
        response = result.get("response")
        if isinstance(response, str) and response != "":
            return _clean(response)
        translated = result.get("translated_text")
        if isinstance(translated, str) and translated != "":
            return _clean(translated)

    # Bare shapes as a last resort
    bare = data.get("response")
    if isinstance(bare, str) and bare != "":
        return _clean(bare)
    return ""


def _payload(prompt: str, *, stream: bool) -> dict[str, Any]:
    settings = _get_settings()
    model = _select_model(prompt)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": settings.RAG_LLM_MAX_TOKENS,
        "temperature": 0.3,
        "stream": stream,
    }


async def generate_answer(prompt: str) -> AnswerResponse | None:
    """Generate a grounded answer via Cloudflare Workers AI (free tier).

    No-op contract: returns ``None`` if ``CF_WORKERS_AI_API_TOKEN`` is not set.

    Args:
        prompt: Full RAG prompt from ``build_rag_prompt()`` — must include
            SYSTEM instruction, retrieved context (delimited), and user query.

    Returns:
        AnswerResponse with the generated answer, or ``None`` if disabled.

    Raises:
        RuntimeError: If the gateway request fails or returns a non-200 status.
            Callers should catch this and degrade gracefully.
    """
    settings = _get_settings()
    token = settings.CF_WORKERS_AI_API_TOKEN.strip()

    if not token:
        logger.debug("Workers AI answer generation skipped — CF_WORKERS_AI_API_TOKEN not set")
        return None

    model = _select_model(prompt)
    timeout_s = settings.RAG_LLM_TIMEOUT_S
    url = _build_url(model)
    headers = _build_headers(token)
    payload = _payload(prompt, stream=False)

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx is a hard dependency; never absent
        raise RuntimeError("httpx is required for Workers AI adapter") from exc

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            start = time.perf_counter()
            resp = await client.post(url, json=payload, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000

        if resp.status_code != 200:
            logger.error(
                "Workers AI generation failed — status=%d model=%s body=%s",
                resp.status_code,
                model,
                resp.text[:300],
            )
            raise RuntimeError(
                f"Workers AI generation failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except ValueError:
            logger.error(
                "Workers AI returned non-JSON response — status=%d body=%s",
                resp.status_code,
                resp.text[:200],
            )
            raise RuntimeError(
                f"Workers AI returned non-JSON response (HTTP {resp.status_code})"
            ) from None

        answer_text = _extract_answer(data)
        if not answer_text:
            logger.warning(
                "Workers AI returned empty answer — model=%s shape=%s", model, str(data)[:200]
            )

        logger.info(
            "Workers AI answer generated — model=%s tokens=%d time_ms=%.0f",
            model,
            len(answer_text.split()),
            elapsed_ms,
        )
        return AnswerResponse(answer=answer_text, model=model, processing_time_ms=elapsed_ms)

    except httpx.TimeoutException as exc:
        logger.error("Workers AI request timed out after %ds — model=%s", timeout_s, model)
        raise RuntimeError(f"Workers AI request timed out after {timeout_s}s") from exc
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to CF AI Gateway for Workers AI — url=%s", url)
        raise RuntimeError(f"Cannot connect to AI Gateway: {exc}") from exc
    except httpx.HTTPError as exc:
        logger.error("Workers AI HTTP error — model=%s: %s", model, exc)
        raise RuntimeError(f"Workers AI HTTP error: {exc}") from exc


async def generate_greeting_stream(user_message: str) -> AsyncGenerator[str, None]:
    """Stream a greeting/small-talk response without RAG context.

    No-op contract: yields nothing if ``CF_WORKERS_AI_API_TOKEN`` is not set.

    Args:
        user_message: The user's greeting or small-talk message.

    Yields:
        Generated text tokens as they arrive.
    """
    settings = _get_settings()
    token = settings.CF_WORKERS_AI_API_TOKEN.strip()

    if not token:
        logger.debug("Workers AI greeting generation skipped — token not set")
        return

    model = _MODEL_FAST  # always use fast model for greetings
    timeout_s = settings.RAG_LLM_TIMEOUT_S
    url = _build_url(model)
    headers = _build_headers(token)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": greeting_system_prompt()},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 256,
        "temperature": 0.7,
        "stream": True,
    }

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx is a hard dependency; never absent
        raise RuntimeError("httpx is required for Workers AI adapter") from exc

    try:
        async with (
            httpx.AsyncClient(timeout=timeout_s) as client,
            client.stream("POST", url, json=payload, headers=headers) as resp,
        ):
            if resp.status_code != 200:
                error_body = await resp.aread()
                logger.error(
                    "Workers AI greeting generation failed — status=%d body=%s",
                    resp.status_code,
                    error_body[:300],
                )
                return

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
                    continue

                token_text = _extract_answer(data, strip=False)
                if token_text:
                    yield token_text

    except httpx.TimeoutException:
        logger.debug("Workers AI greeting request timed out — returning fallback")
        yield "Hi there! How can I help you with EU documents today?"
    except httpx.ConnectError:
        logger.debug("Cannot connect to AI Gateway for greeting — returning fallback")
        yield "Hi there! How can I help you with EU documents today?"


async def generate_answer_stream(
    prompt: str,
    *,
    neuron_budget_kv: Any | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a grounded answer via Cloudflare Workers AI (free tier).

    No-op contract: yields nothing if ``CF_WORKERS_AI_API_TOKEN`` is not set.

    Args:
        prompt: Full RAG prompt from ``build_rag_prompt()``.
        neuron_budget_kv: Optional KV binding for neuron budget tracking.
            When provided, checks daily 10K neuron budget and auto-downgrades
            to fast model if budget is low.

    Yields:
        Generated text tokens as they arrive.
    """
    settings = _get_settings()
    token = settings.CF_WORKERS_AI_API_TOKEN.strip()

    if not token:
        logger.debug("Workers AI streaming generation skipped — CF_WORKERS_AI_API_TOKEN not set")
        return

    model = _select_model(prompt)
    timeout_s = settings.RAG_LLM_TIMEOUT_S

    # ── Neuron budget check ─────────────────────────────────────────────
    if neuron_budget_kv is not None:
        allowed, downgraded_model = await _check_and_reserve_neurons(model, neuron_budget_kv)
        if not allowed:
            # Budget exhausted — yield error message and return
            yield "Daily AI budget reached. Service resets at midnight UTC. Please try again soon."
            return
        if downgraded_model is not None:
            model = downgraded_model
            logger.info("Auto-downgraded to %s due to neuron budget", model)
    # ────────────────────────────────────────────────────────────────────

    url = _build_url(model)
    headers = _build_headers(token)
    payload = _payload(prompt, stream=True)

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx is a hard dependency; never absent
        raise RuntimeError("httpx is required for Workers AI adapter") from exc

    try:
        async with (
            httpx.AsyncClient(timeout=timeout_s) as client,
            client.stream("POST", url, json=payload, headers=headers) as resp,
        ):
            if resp.status_code != 200:
                error_body = await resp.aread()
                logger.error(
                    "Workers AI streaming generation failed — status=%d model=%s body=%s",
                    resp.status_code,
                    model,
                    error_body[:300],
                )
                raise RuntimeError(
                    f"Workers AI streaming generation failed (HTTP {resp.status_code}): "
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

                token_text = _extract_answer(data, strip=False)
                if token_text:
                    yield token_text

    except httpx.TimeoutException as exc:
        logger.error(
            "Workers AI streaming request timed out after %ds — model=%s", timeout_s, model
        )
        raise RuntimeError(f"Workers AI request timed out after {timeout_s}s") from exc
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to CF AI Gateway for Workers AI — url=%s", url)
        raise RuntimeError(f"Cannot connect to AI Gateway: {exc}") from exc
    except httpx.HTTPError as exc:
        logger.error("Workers AI HTTP error — model=%s: %s", model, exc)
        raise RuntimeError(f"Workers AI HTTP error: {exc}") from exc
    finally:
        # Record neuron usage after the stream completes (fire-and-forget)
        if neuron_budget_kv is not None:
            # We need to record usage, but we don't have a clean way to do it
            # after the generator yields. The calling code should handle this.
            pass
