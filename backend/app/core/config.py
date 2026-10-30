# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Core Configuration — Pydantic Settings

Responsibilities:
- Load all environment variables from .env file
- Provide typed, validated settings to the entire application
- Enforce 12-factor app compliance (no hardcoded secrets or URLs)
- Expose feature flags for gating Phase 2 / Sprint 3 functionality
"""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ───────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    APP_SECRET_KEY: str = Field(
        default="change-me-in-production",
        description="JWT signing secret — override via .env or Cloudflare Worker secret binding",
    )
    APP_DEBUG: bool = False
    APP_LOG_LEVEL: str = "info"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "https://evidence-eu-frontend.pages.dev",
    ]

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./evidence_eu.db"
    CF_D1_DATABASE_ID: str = ""

    # ── Cloudflare ────────────────────────────────────────────────────────
    CF_ACCOUNT_ID: str = ""
    CF_API_TOKEN: str = ""
    CF_AI_GATEWAY_ID: str = "evidence-eu-gateway"
    CF_AIG_AUTHORIZATION: str = ""
    CF_VECTORIZE_INDEX_NAME: str = "evidence-eu-docs"
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_GATEWAY_ID: str = "evidence-eu-gateway"
    CLOUDFLARE_API_TOKEN: str = ""

    # ── RAG / Vector DB ───────────────────────────────────────────────────
    VECTOR_DB_PROVIDER: str = "chromadb"
    CHROMADB_URL: str = "http://chromadb:8500"
    HINDSIGHT_API_URL: str = "http://localhost:8600"
    # Hindsight Cloud bearer token (ADR-016). Empty = no auth header (self-hosted
    # local dev). Set as a Worker secret in prod — never a wrangler.toml var.
    HINDSIGHT_ACCESS_KEY: str = ""
    HINDSIGHT_BANK_ID: str = "evidence-eu-docs"
    # Hindsight's documented defaults. The prior production profile used the
    # maximum search depth and twice the documented response-token default.
    HINDSIGHT_RECALL_BUDGET: Literal["low", "mid", "high"] = "mid"
    HINDSIGHT_RECALL_MAX_TOKENS: int = Field(default=4096, ge=1)
    HINDSIGHT_RECALL_TIMEOUT_S: float = Field(default=20.0, ge=1.0)
    GLOSSARY_EXPANSION_MAX_TOKENS: int = Field(default=6, ge=1)
    GLOSSARY_EXPANSION_MAX_TERMS: int = Field(default=9, ge=1)
    GLOSSARY_EXPANSION_MAX_CHARS: int = Field(default=500, ge=50)
    GLOSSARY_EXPANSION_DEADLINE_S: float = Field(default=1.0, ge=0.1)
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # ── RAG Answer Generation ──────────────────────────────────────────────
    # Provider dispatch (app/integrations/llm/answer_generation.py):
    #   "workers-ai"  (DEFAULT) → Cloudflare Workers AI free tier. Uses
    #       CF_WORKERS_AI_API_TOKEN (same token as translation). Does NOT consume
    #       AI Gateway wholesale credits — zero-cost mitigation for the
    #       "402 Insufficient wholesale credits" error that HF Serverless
    #       Inference (Apertus) now hits after HF deprecated its legacy
    #       serverless API (Cloudflare error 1016 = origin DNS failure).
    #   "huggingface"         → Apertus 8B (Swiss sovereign LLM) via Public AI.
    #       Preferred route: the DIRECT Public AI platform (api.publicai.co) when
    #       PUBLICAI_API_KEY is set — genuinely free, sovereign, no HF metering.
    #       Fallback route: the HF Inference Providers router (router.huggingface.co)
    #       when only HF_API_TOKEN is set (note: HF meters this against the account's
    #       monthly included credits and returns 402 once depleted).
    #       Model auto-resolves to swiss-ai/apertus-8b-instruct (direct) or
    #       swiss-ai/Apertus-8B-Instruct-2509:publicai (HF router).
    RAG_LLM_PROVIDER: str = "workers-ai"
    # Default model for the active provider. For workers-ai this is a current,
    # multilingual, free-tier Cloudflare model (proven via the BAML glossary
    # client in this repo). For huggingface, override to the Apertus model.
    RAG_LLM_MODEL: str = "@cf/meta/llama-4-scout-17b-16e-instruct"
    # Apertus settings — only used when RAG_LLM_PROVIDER == "huggingface".
    # Two routes to Apertus, resolved in this priority order:
    #   1. PUBLICAI_API_KEY set → DIRECT Public AI platform (api.publicai.co).
    #      Preferred: genuinely free sovereign utility, no HuggingFace metering.
    #   2. HF_API_TOKEN set     → HF Inference Providers router (:publicai suffix).
    #      Fallback: metered against HF monthly included credits (402 when depleted).
    # No-op contract: if BOTH are empty, answer generation is skipped and search
    # returns chunks only (graceful degradation, same as Sentry/Datadog/D1Client).
    PUBLICAI_API_KEY: str = ""
    HF_API_TOKEN: str = ""
    RAG_LLM_MAX_TOKENS: int = 512
    RAG_LLM_TIMEOUT_S: int = 30

    # ── SSE Streaming ────────────────────────────────────────────────────
    SSE_CHUNK_DELAY_MS: int = Field(
        default=0,
        ge=0,
        description=(
            "Artificial delay (ms) between SSE result yields for backpressure / "
            "client rate-limiting. Set to 0 (default) to disable."
        ),
    )

    # ── OCR ───────────────────────────────────────────────────────────────
    OCR_PROVIDER: str = "mistral"
    MISTRAL_API_KEY: str = ""
    MISTRAL_OCR_ENABLED: bool = True  # Set to false to skip Mistral and use Tesseract directly
    TESSERACT_LANG: str = "eng"  # Tesseract language pack(s), e.g. "eng+deu+fra"

    # ── Azure Document Intelligence ─────────────────────────────────────
    # Direct REST integration only; no Azure SDK dependency. Disabled by
    # default and transparent until endpoint/key secrets are configured.
    AZURE_DOCUMENT_INTELLIGENCE_ENABLED: bool = False
    AZURE_DOCUMENT_INTELLIGENCE_TIER: Literal["F0", "S0"] = "F0"
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: str = ""
    AZURE_DOCUMENT_INTELLIGENCE_KEY: str = ""
    AZURE_DOCUMENT_INTELLIGENCE_API_VERSION: str = "2024-11-30"
    AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID: str = "prebuilt-layout"
    AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S: float = 30.0
    AZURE_DOCUMENT_INTELLIGENCE_POLL_INTERVAL_S: float = 1.0
    AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS: int = 120

    # ── Document Classification ───────────────────────────────────────────
    PROPELLA_ENABLED: bool = True
    PROPELLA_BASE_URL: str = "http://propella:8700"

    # ── Translation ───────────────────────────────────────────────────────
    # Sprint 2: Cloudflare Workers AI m2m100-1.2b (free, Pyodide-safe, EN/DE/FR)
    # Post-graduation community: BabelDOC sidecar (AGPL, layout-preserving)
    # Post-graduation commercial: Doclingo API or Argos Translate (MIT)
    # Note: DeepL API is excluded — ToS §8.1.1(f) prohibits use in translation products.
    TRANSLATION_PROVIDER: str = "cf_workers_ai"  # cf_workers_ai | babeldoc_sidecar
    CF_WORKERS_AI_API_TOKEN: str = ""  # Set via Cloudflare Worker secret or .env
    CF_WORKERS_AI_TRANSLATION_MODEL: str = "@cf/meta/m2m100-1.2b"
    # BabelDOC sidecar URL (local Docker or Cloudflare Tunnel)
    BABELDOC_URL: str = "http://localhost:8750"

    # ── Not Diamond Model Routing (Sprint 3, opt-in) ─────────────────────────
    # Layered on top of the CF AI Gateway + BAML: picks the best LLM per task
    # (translation, RAG query). NO document content is sent — only metadata.
    # No-op contract: when NOT_DIAMOND_ENABLED is False OR the API key is empty,
    # the router falls back to NOT_DIAMOND_DEFAULT_MODEL without any HTTP call.
    # Default False so existing CI passes without the key being set.
    NOT_DIAMOND_ENABLED: bool = False
    NOT_DIAMOND_API_KEY: str = ""  # Bearer token. Empty = no-op.
    NOT_DIAMOND_BASE_URL: str = "https://api.notdiamond.ai/v2"
    NOT_DIAMOND_DEFAULT_MODEL: str = "@cf/meta/m2m100-1.2b"
    NOT_DIAMOND_TIMEOUT_MS: int = 800  # 800ms — fast enough for edge routing
    NOT_DIAMOND_PREFERENCE_ID: str = (
        ""  # Custom router ID from trainCustomRouter (empty = use pre-trained)
    )

    # ── PII Redaction (GDPR Art. 5(1)(c) data minimisation) ──────────────
    # Redact personal data (names, addresses, dates, ID numbers) from OCR text
    # BEFORE it reaches external translation backends. Follows the BabelDOC
    # sidecar pattern (ADR-012) — Presidio + spaCy run in a Docker container,
    # never imported in the Pyodide backend.
    # No-op contract: when PII_REDACTION_ENABLED is False, redaction is a
    # transparent no-op — translation proceeds with unredacted text (same as
    # Sentry/Datadog/D1Client graceful degradation).
    PII_REDACTION_ENABLED: bool = False
    PII_REDACTION_BASE_URL: str = "http://pii-redactor:8760"
    PII_REDACTION_TIMEOUT_S: int = 10

    # ── Matrix Protocol ───────────────────────────────────────────────────
    MATRIX_HOMESERVER_URL: str = "https://synapse.evidenceeu.eu.mihai.codes"
    MATRIX_ACCESS_TOKEN: str = ""
    MATRIX_DEVICE_ID: str = ""
    MATRIX_CLIENT_ID: str = ""
    MATRIX_CLIENT_SECRET: str = ""
    MATRIX_ROOM_PREFIX: str = "evidence-eu"
    MATRIX_OAUTH_CALLBACK_URL: str = (
        # MUST go through the proxy Worker (evidence-eu-worker), NOT directly
        # to the API Worker (evidence-eu-api). The session cookie is set on
        # whichever domain serves the callback response. If the callback goes
        # to the API Worker directly, the cookie is set on evidence-eu-api.*
        # but the frontend's session check fetch goes to evidence-eu-worker.*
        # (API_BASE) — the cookie won't be sent and the user appears logged out.
        # The proxy Worker forwards /api/v1/* to the backend and passes through
        # Set-Cookie headers, so the cookie lands on the proxy domain.
        "https://evidence-eu-worker.mc146.workers.dev/api/v1/auth/matrix/callback"
    )
    MATRIX_OAUTH_POST_LOGIN_URL: str = "https://evidence-eu-frontend.pages.dev/dashboard"
    MATRIX_OAUTH_COOKIE_NAME: str = "evidenceeu_session"
    MATRIX_OAUTH_STATE_TTL_S: int = Field(default=300, ge=60, le=900)
    MATRIX_OAUTH_SESSION_TTL_S: int = Field(default=3600, ge=300, le=86400)

    # ── Demo ───────────────────────────────────────────────────────────────
    DEMO_MODE: bool = False  # Activates DemoWarmupMiddleware + demo-safe limits
    DEMO_MAX_CHARS: int = 2000  # Max chars per page sent to m2m100 in demo mode (0=disabled)

    # ── Feature Flags ─────────────────────────────────────────────────────
    ENABLE_MATRIX_EXCHANGE: bool = False  # Sprint 3
    ENABLE_MATRIX_AUTH: bool = False
    ENABLE_HEALTHCARE_PHASE2: bool = False  # Phase 2 — never true in capstone
    ENABLE_FHIR_PARSING: bool = False  # Phase 2

    # ── Linus Integration (ADR-023) ─────────────────────────────────────────
    # Grounding gate (DEC-0059): claim-level citation validation.
    # Default False — opt-in until full integration testing completes.
    GROUNDING_GATE_ENABLED: bool = False
    # Cross-session memory pillar: D1-backed session/message/investigation tables.
    # Default False — no data persisted until explicitly enabled.
    SESSION_MEMORY_ENABLED: bool = False
    # LLM trace recorder (DEC-0041 partial): in-memory ring buffer of LLM call
    # metadata (model, prompt hash, latency, token count, error). No document
    # content stored — GDPR-safe by design. Use for debugging, latency audits,
    # and prompt reproducibility. Default False — no overhead until enabled.
    ENABLE_LLM_TRACING: bool = False

    # ── PostHog ───────────────────────────────────────────────────────────
    POSTHOG_PROJECT_TOKEN: str = ""  # If unset, PostHog is a no-op (graceful degradation)
    POSTHOG_HOST: str = "https://eu.i.posthog.com"
    POSTHOG_DISABLED: bool = False

    # ── Sentry ────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""  # If unset, Sentry is a no-op (graceful degradation)

    # ── Datadog ──────────────────────────────────────────────────────────
    # SERVER-ONLY — never expose to browser. Used for custom metrics via httpx.
    DATADOG_API_KEY: str = ""  # If unset, Datadog is a no-op (graceful degradation)

    # ── Laminar ──────────────────────────────────────────────────────────
    # Custom OTLP/HTTP/json forwarder (no lmnr SDK — Pyodide-incompatible).
    # No-op unless LMNR_ENABLED=True AND LMNR_PROJECT_API_KEY is set.
    LMNR_PROJECT_API_KEY: str = ""
    LMNR_ENABLED: bool = False
    LMNR_ENDPOINT: str = "https://api.lmnr.ai:443/v1/traces"
    LMNR_SEND_PROMPT_CONTENT: bool = False  # GDPR: keep False in production
    LMNR_SAMPLE_RATE: float = 0.1
    LMNR_SERVICE_NAME: str = "evidence-eu-backend"

    # ── Langfuse ─────────────────────────────────────────────────────────
    # Custom Basic Auth OTLP dispatch (no langfuse SDK — opentelemetry-sdk
    # uses threading, non-functional in Pyodide/WASM).
    # No-op unless LANGFUSE_ENABLED=True AND both keys are set.
    # See app/integrations/langfuse.py for the custom forwarder.
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_ENDPOINT: str = "https://cloud.langfuse.com/api/public/otel/v1/traces"
    LANGFUSE_SEND_PROMPT_CONTENT: bool = False  # GDPR: keep False in production
    LANGFUSE_SAMPLE_RATE: float = 0.1
    LANGFUSE_SERVICE_NAME: str = "evidence-eu-backend"

    # ── Eurostat ─────────────────────────────────────────────────────────
    EUROSTAT_API_URL: str = (
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/migr_pop1ctz"
    )
    EUROSTAT_CACHE_TTL_S: int = 86400  # 24h — dataset updates annually

    # ── GDPR ──────────────────────────────────────────────────────────────
    DATA_RESIDENCY_REGION: str = "EU"
    GDPR_CONSENT_REQUIRED: bool = True
    AUDIT_LOG_ENABLED: bool = True

    @model_validator(mode="after")
    def enforce_secret_key_in_production(self) -> "Settings":
        """Refuse to start in production with the default placeholder secret key.

        This prevents JWT tokens from being signed with a well-known string if
        APP_SECRET_KEY is accidentally left as the default value in production.
        Override via .env or Cloudflare Worker secret binding.
        """
        if self.APP_ENV == "production" and self.APP_SECRET_KEY == "change-me-in-production":
            raise ValueError(
                "APP_SECRET_KEY must be set to a secure random value in production. "
                'Use: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self

    @property
    def cloudflare_ai_gateway_url(self) -> str:
        """Construct the Cloudflare AI Gateway base URL."""
        account_id = self.CLOUDFLARE_ACCOUNT_ID or self.CF_ACCOUNT_ID
        gateway_id = self.CLOUDFLARE_GATEWAY_ID or self.CF_AI_GATEWAY_ID
        return f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()
