# SPDX-License-Identifier: AGPL-3.0-or-later
"""
RAG Answer Generation facade — provider dispatch.

Unifies the two answer-generation backends behind one import surface so call
sites (search.py, rag_service.py) stay DRY and ignorant of the active provider:

  - "workers-ai"  (default) → Cloudflare Workers AI free tier, no wholesale
        credits required. Uses ``CF_WORKERS_AI_API_TOKEN``. See
        ``workers_ai_adapter.py``.
  - "huggingface"         → Apertus 8B (Swiss sovereign LLM) via the **Public
        AI** provider on the HuggingFace Inference Providers router — free public
        inference, no wholesale credits. Requires ``HF_API_TOKEN``. See
        ``apertus_adapter.py``.

Provider is selected by ``settings.RAG_LLM_PROVIDER``. All provider URLs are
centralized in ``app/integrations/cloudflare/gateway.py`` (REM-8 compliant).

No-op contract: ``is_enabled()`` is False when the active provider's token is
unset; ``generate_answer`` returns ``None`` and callers degrade gracefully.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnswerModelInfo:
    """Public, non-secret metadata for the active answer-generation model."""

    provider: str
    provider_display: str
    model: str
    display_name: str

    def as_event_payload(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "provider_display": self.provider_display,
            "model": self.model,
            "display_name": self.display_name,
        }


def _provider() -> str:
    """Resolve the active answer-generation provider (lowercased, default workers-ai)."""
    return (settings.RAG_LLM_PROVIDER or "workers-ai").strip().lower()


def is_enabled() -> bool:
    """True if the active provider is configured with a usable token."""
    if _provider() == "huggingface":
        from app.integrations.llm.apertus_adapter import is_enabled as _hf_enabled

        return _hf_enabled()
    from app.integrations.llm.workers_ai_adapter import is_enabled as _wa_enabled

    return _wa_enabled()


def _display_name(model: str) -> str:
    normalized = model.lower()
    if "apertus" in normalized:
        return "Apertus 8B"
    if "llama-4-scout" in normalized:
        return "Llama 4 Scout"
    if "llama-3.3-70b" in normalized:
        return "Llama 3.3 70B"
    if "llama-3.1-8b" in normalized:
        return "Llama 3.1 8B"
    if "mistral" in normalized:
        return "Mistral"
    return model.rsplit("/", 1)[-1].split(":", 1)[0]


def active_model_info(prompt: str | None = None) -> AnswerModelInfo | None:
    """Describe the model that will handle a RAG answer, if configured.

    When *prompt* is provided, the Workers AI path selects the model that
    ``_select_model`` would choose for that query (fast vs frontier).
    """
    if _provider() == "huggingface":
        from app.integrations.llm.apertus_adapter import model_name as _hf_model_name

        model = _hf_model_name()
        if model is None:
            return None
        return AnswerModelInfo(
            provider="public-ai",
            provider_display="Public AI",
            model=model,
            display_name=_display_name(model),
        )

    import app.integrations.llm.workers_ai_adapter as _wa_mod

    model = _wa_mod.select_model_for_prompt(prompt) if prompt else _wa_mod.model_name()
    if model is None:
        return None
    return AnswerModelInfo(
        provider="cloudflare-workers-ai",
        provider_display="Cloudflare Workers AI",
        model=model,
        display_name=_display_name(model),
    )


async def generate_answer(prompt: str) -> Any:
    """Generate a grounded answer via the active provider.

    Returns an object exposing ``.answer`` / ``.model`` / ``.processing_time_ms``,
    or ``None`` when disabled.
    """
    if _provider() == "huggingface":
        from app.integrations.llm.apertus_adapter import generate_answer as _hf_generate

        resp = await _hf_generate(prompt)
        if resp is None:
            return None
        # Re-wrap the Apertus response in the provider-agnostic shape.
        from app.integrations.llm.workers_ai_adapter import AnswerResponse

        return AnswerResponse(
            answer=resp.answer, model=resp.model, processing_time_ms=resp.processing_time_ms
        )

    from app.integrations.llm.workers_ai_adapter import generate_answer as _wa_generate

    return await _wa_generate(prompt)


async def generate_answer_stream(
    prompt: str,
    *,
    neuron_budget_kv: Any | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a grounded answer via the active provider."""
    if _provider() == "huggingface":
        from app.integrations.llm.apertus_adapter import generate_answer_stream as _hf_stream

        async for token in _hf_stream(prompt):
            yield token
        return

    from app.integrations.llm.workers_ai_adapter import generate_answer_stream as _wa_stream

    async for token in _wa_stream(prompt, neuron_budget_kv=neuron_budget_kv):
        yield token


async def generate_greeting_stream(user_message: str) -> AsyncGenerator[str, None]:
    """Stream a greeting/small-talk response from the Workers AI adapter."""
    from app.integrations.llm.workers_ai_adapter import generate_greeting_stream as _wa_greet

    async for token in _wa_greet(user_message):
        yield token
