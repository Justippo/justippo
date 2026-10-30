# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Not Diamond Model Router — Single Source of Truth for LLM Routing

Not Diamond is a meta-model router that picks the best LLM provider for a
given task based on complexity/cost/latency signals. It is layered on top of
the existing Cloudflare AI Gateway (which still handles caching, logging,
observability) and on top of BAML (which still handles prompt engineering).

Architecture:
  User → CF Worker → NotDiamondRouter.route(task_type, metadata)
                ↓
            Not Diamond REST API (POST /v2/modelRouter/modelSelect)
                ↓
            selected model id
                ↓
          (downstream code calls CF AI Gateway with the selected model)

Three task types are routed:
  - TRANSLATION  → picks between m2m100 (cheap), BabelDOC (layout-preserving),
                   and a frontier fallback for complex legal/bureaucratic text.
  - RAG_QUERY    → picks between Apertus 8B (sovereign default) and a frontier
                   fallback for cross-lingual / multi-entity queries.
  - OCR_POST     → NOT ROUTED via Not Diamond (the only sensible "structuring"
                   decision is Mistral OCR 4's built-in structured_outputs
                   feature, which is part of the OCR call itself). This enum
                   value exists so callers can be explicit; route() returns the
                   default model immediately without an HTTP call.

GDPR guarantee:
  Only metadata signals (language pair, document type, text length,
  complexity score, language count, has_tables) are sent to Not Diamond.
  Document content is NEVER transmitted — only synthesized "task description"
  text built from the metadata. A runtime guard (assert in dev, log+skip in
  prod) refuses any metadata dict containing a "content" key.

No-op contract:
  - If NOT_DIAMOND_ENABLED is False → route() returns the default model
    immediately, no HTTP call.
  - If NOT_DIAMOND_API_KEY is empty → route() returns the default model.
  - If the API call fails or times out (NOT_DIAMOND_TIMEOUT_MS) → fallback
    to default model, logged at WARNING level. Routing is best-effort.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task type enum — the single switch that drives all routing decisions.
# Adding a new task type = adding one enum value + one entry in CANDIDATES.
# ---------------------------------------------------------------------------


class TaskType(StrEnum):
    """Routable task types. Values are sent as the 'task' metadata field."""

    TRANSLATION = "translation"
    RAG_QUERY = "rag_query"
    OCR_POST = "ocr_post"  # Not routed — always returns default (see docstring).


# ---------------------------------------------------------------------------
# Single source of truth for candidates per task type.
# Model ids are config-driven (see app/core/config.py) but the *candidate
# lists* live here because they are routing logic, not deployment config.
# ---------------------------------------------------------------------------


# LLM provider identifiers for Not Diamond (per OpenAPI spec).
# Not Diamond only recognizes 17 providers (verified via GET /v2/models):
# anthropic, cohere, deepseek, google, inception, meta-llama, minimax,
# mistral, moonshotai, openai, openrouter, perplexity, qwen, replicate,
# togetherai, x-ai, z-ai.
# Cloudflare Workers AI, BabelDOC, and HuggingFace are NOT recognized.
#
# Architecture: Not Diamond routes between models it knows (mistral-small as
# a cheap proxy, mistral-large as a frontier proxy). The selected model is
# then mapped to EvidenceEU's internal model id via MODEL_MAP — so ND's
# decision ("cheap" vs "frontier") drives the actual provider call.
# Pre-trained candidates (used when NOT_DIAMOND_PREFERENCE_ID is empty).
# These are recognized ND providers that act as proxies for our internal models.
_TRANSLATION_CANDIDATES: list[dict[str, object]] = [
    {"provider": "mistral", "model": "mistral-small-latest"},  # cheap proxy → m2m100
    {
        "provider": "mistral",
        "model": "mistral-large-latest",
    },  # frontier proxy → frontier translation
    {"provider": "openai", "model": "gpt-4o-mini"},  # frontier fallback
]

# Custom candidates (used when NOT_DIAMOND_PREFERENCE_ID is set — trained on
# EvidenceEU's 30 translation test cases via trainCustomRouter).
_CUSTOM_TRANSLATION_CANDIDATES: list[dict[str, object]] = [
    {"provider": "evidence-eu", "model": "m2m100-1.2b", "is_custom": True},
    {"provider": "evidence-eu", "model": "apertus-8b", "is_custom": True},
    {"provider": "evidence-eu", "model": "mistral-large", "is_custom": True},
]

_RAG_CANDIDATES: list[dict[str, object]] = [
    {"provider": "mistral", "model": "mistral-small-latest"},  # simple proxy → Apertus
    {"provider": "openai", "model": "gpt-4o-mini"},  # frontier proxy → frontier RAG
]

CANDIDATES_BY_TASK: dict[TaskType, list[dict[str, object]]] = {
    TaskType.TRANSLATION: _TRANSLATION_CANDIDATES,
    TaskType.RAG_QUERY: _RAG_CANDIDATES,
    # OCR_POST has no candidate list — see docstring.
}

# Map Not Diamond's selected model → EvidenceEU's internal model id.
# This is the bridge between ND's routing decision and EvidenceEU's
# provider-specific dispatch (CF Workers AI, BabelDOC, HF, etc.).
# If a model isn't in this map, the DEFAULT_MODEL is used.
#
# IMPORTANT: the translation path (_call_m2m100) only supports CF Workers AI
# models (must start with @cf/). BabelDOC is a document-level translator
# (expects base64-encoded documents, not text blocks), so it can't drop into
# the per-text-block translation path. Until a frontier text-translation
# model is available on CF Workers AI, all translation picks map to m2m100.
# The routing decision is still logged for audit/analytics — it records
# what ND recommended even when the actual model stays the same.
MODEL_MAP: dict[str, str] = {
    # Pre-trained router picks (proxy models)
    "mistral-small-latest": "@cf/meta/m2m100-1.2b",
    "mistral-large-latest": "mistral-large-translation",
    "gpt-4o-mini": "mistral-large-translation",
    # Custom router picks (trained on EvidenceEU data via trainCustomRouter)
    "m2m100-1.2b": "@cf/meta/m2m100-1.2b",
    "apertus-8b": "mistral-large-translation",  # Apertus for translation routes to Mistral Large (text-block path)
    "mistral-large": "mistral-large-translation",
}


# Metadata keys that must NEVER appear in the routing payload.
# The guard is a defense-in-depth check against accidental content leakage;
# Not Diamond's API-side hash_content=True is the second layer.
_FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "content",
        "text",
        "document",
        "page_text",
        "ocr_text",
        "translation",
        "answer",
        "raw_text",
        "body",
        "message",
        "messages",
    }
)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class NotDiamondRouter:
    """Async Not Diamond client. One instance per app (singleton via module
    lazy-init in gateway.py). All API calls flow through _call_api() — that
    is the only place httpx is touched, in keeping with the DRY rule."""

    # Hardcoded fallback ONLY for when settings is not yet loaded (e.g., during
    # import-time errors). At runtime, _default_model() reads from settings.
    _HARDCODED_FALLBACK: str = "@cf/meta/m2m100-1.2b"

    def __init__(self) -> None:
        # Lazy: read settings at call time so test fixtures can swap them.
        self._base_url: str = getattr(
            settings, "NOT_DIAMOND_BASE_URL", "https://api.notdiamond.ai/v2"
        )
        self._endpoint: str = f"{self._base_url}/modelRouter/modelSelect"

    @property
    def DEFAULT_MODEL(self) -> str:
        """Runtime default model — read from settings, not a hardcoded constant.

        DRY: single source of truth is NOT_DIAMOND_DEFAULT_MODEL in config.py.
        The class-level _HARDCODED_FALLBACK is only for settings-not-loaded edge cases."""
        return getattr(settings, "NOT_DIAMOND_DEFAULT_MODEL", "") or self._HARDCODED_FALLBACK

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(self, task_type: TaskType, metadata: dict[str, object]) -> str:
        """Return the model id Not Diamond recommends for this task.

        Graceful fallback contract: returns DEFAULT_MODEL on any failure,
        never raises. Failures are logged at WARNING with the task type and
        reason (no payload contents are logged).
        """
        # 1. Feature flag / token short-circuit.
        if not self._is_enabled():
            return self.DEFAULT_MODEL

        # 2. Per-task fast path: OCR_POST never routes (see module docstring).
        if task_type is TaskType.OCR_POST:
            return self.DEFAULT_MODEL

        # 3. GDPR guard (raises in dev, logs+skips in prod).
        try:
            self._enforce_no_content(metadata)
        except ValueError as guard_err:
            if getattr(settings, "APP_ENV", "development") == "development":
                raise
            logger.warning(
                "Not Diamond GDPR guard rejected metadata (task=%s): %s",
                task_type.value,
                guard_err,
            )
            return self.DEFAULT_MODEL

        # 4. Build payload + call API. Any exception → fallback.
        try:
            # Use custom candidates if a preference_id is configured (trained on
            # EvidenceEU data), otherwise use pre-trained ND proxy models.
            pref_id = getattr(settings, "NOT_DIAMOND_PREFERENCE_ID", "")
            if pref_id and task_type == TaskType.TRANSLATION:
                candidates = _CUSTOM_TRANSLATION_CANDIDATES
            else:
                candidates = CANDIDATES_BY_TASK[task_type]
            payload = self._build_payload(task_type, metadata, candidates)
            response_body = await self._call_api(payload)
            nd_model = self._parse_model_id(response_body)
            # Map Not Diamond's model → EvidenceEU's internal model id.
            # If ND returns a model not in MODEL_MAP, fall back to default.
            mapped = MODEL_MAP.get(nd_model, "")
            if not mapped:
                logger.warning(
                    "Not Diamond returned unmapped model %s (task=%s, fallback=%s)",
                    nd_model,
                    task_type.value,
                    self.DEFAULT_MODEL,
                )
                return self.DEFAULT_MODEL
            logger.info(
                "Not Diamond routed task=%s to %s → %s",
                task_type.value,
                nd_model,
                mapped,
            )
            return mapped
        except Exception as exc:  # noqa: BLE001 — best-effort routing
            logger.warning(
                "Not Diamond routing failed (task=%s, fallback=%s): %s",
                task_type.value,
                self.DEFAULT_MODEL,
                exc.__class__.__name__,
            )
            return self.DEFAULT_MODEL

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        """Feature flag + token presence. Both must be true to route."""
        if not getattr(settings, "NOT_DIAMOND_ENABLED", False):
            return False
        return bool(getattr(settings, "NOT_DIAMOND_API_KEY", ""))

    def _enforce_no_content(self, metadata: dict[str, object]) -> None:
        """Defense-in-depth GDPR check. metadata must contain only routing
        signals — no document content, no raw text, no translations."""
        leaked = _FORBIDDEN_METADATA_KEYS.intersection(metadata.keys())
        if leaked:
            raise ValueError(f"metadata contains forbidden content keys: {sorted(leaked)}")
        # Also reject nested dicts that carry content under arbitrary names.
        for key, value in metadata.items():
            if isinstance(value, str) and len(value) > 5000:
                raise ValueError(
                    f"metadata['{key}'] is a {len(value)}-char string — "
                    "routing signals must be short metadata, not document text"
                )

    def _build_payload(
        self,
        task_type: TaskType,
        metadata: dict[str, object],
        candidates: list[dict[str, object]],
    ) -> dict[str, object]:
        """Construct the Not Diamond modelSelect request body.

        Only a synthesized "task description" is sent (derived from metadata),
        never raw text. ``hash_content=True`` is set so even the synthesized
        description is hashed at the API layer (defense in depth)."""
        task_description = self._synthesize_task_description(task_type, metadata)
        payload: dict[str, object] = {
            "messages": [{"role": "user", "content": task_description}],
            "llm_providers": candidates,
            "tradeoff": "cost",
            "cost_quality_tradeoff": 3,  # lean toward cost (matches free-tier usage)
            "hash_content": True,
            "metric": "accuracy",
        }
        # Use custom router if a preference_id is configured (from trainCustomRouter)
        pref_id = getattr(settings, "NOT_DIAMOND_PREFERENCE_ID", "")
        if pref_id:
            payload["preference_id"] = pref_id
        return payload

    def _synthesize_task_description(self, task_type: TaskType, metadata: dict[str, object]) -> str:
        """Build a short task description from metadata. Stays under ~300
        chars so it can never accidentally leak large content."""
        parts: list[str] = [f"Task: {task_type.value}"]
        for key in (
            "language_pair",
            "doc_type",
            "source_language",
            "target_language",
            "language_count",
            "text_length_bucket",
            "complexity_score",
            "has_tables",
        ):
            if key in metadata:
                parts.append(f"{key}={metadata[key]}")
        return " | ".join(parts)[:300]

    async def _call_api(self, payload: dict[str, object]) -> dict[str, object]:
        """Single point of httpx contact. DRY: all HTTP error handling lives
        here. Timeout is configurable via NOT_DIAMOND_TIMEOUT_MS (default
        800ms — fast enough for edge routing)."""
        timeout_ms = int(getattr(settings, "NOT_DIAMOND_TIMEOUT_MS", 800))
        timeout_s = timeout_ms / 1000.0
        api_key = getattr(settings, "NOT_DIAMOND_API_KEY", "")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(self._endpoint, json=payload, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Not Diamond API returned HTTP {response.status_code}")
        return dict(response.json())

    def _parse_model_id(self, body: dict[str, object]) -> str:
        """Extract the recommended model id from the Not Diamond response.

        Response shape (per OpenAPI):
          {"providers": [{"provider": str, "model": str}], "session_id": str}

        Returns DEFAULT_MODEL on any unexpected shape (defensive)."""
        providers = body.get("providers")
        if not isinstance(providers, list) or not providers:
            return self.DEFAULT_MODEL
        first = providers[0]
        if not isinstance(first, dict):
            return self.DEFAULT_MODEL
        model = first.get("model")
        if not isinstance(model, str) or not model:
            return self.DEFAULT_MODEL
        return model


# ---------------------------------------------------------------------------
# Module-level singleton (lazy). gateway.py imports `router` and calls
# router.route(...). Re-instantiation is safe; httpx is created per call.
# ---------------------------------------------------------------------------

_router: NotDiamondRouter | None = None


def get_router() -> NotDiamondRouter:
    """Return the process-wide NotDiamondRouter (lazy singleton)."""
    global _router
    if _router is None:
        _router = NotDiamondRouter()
    return _router
