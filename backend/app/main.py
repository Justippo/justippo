# SPDX-License-Identifier: AGPL-3.0-or-later
"""
EvidenceEU — FastAPI Application Entry Point

Responsibilities:
- Bootstrap the FastAPI app with all middleware (CORS, auth, GDPR consent)
- Register all API routers (v1: search, documents, translate, exchange, health)
- Configure lifespan events (DB init, vector store warm-up)
- Apply feature-flag-gated routes (Matrix exchange, Phase 2 healthcare)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.middleware import GDPRConsentMiddleware
from app.services.rag_service import HindsightRAGService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle events."""
    # Sprint 2: Configure BAML Gateway routing before any generation call
    from app.integrations.baml_setup import configure as configure_baml

    configure_baml()

    # Configure PostHog product analytics (graceful no-op if token unset)
    from app.integrations.posthog import configure as configure_posthog

    configure_posthog(
        settings.POSTHOG_PROJECT_TOKEN,
        settings.POSTHOG_HOST,
        disabled=settings.POSTHOG_DISABLED,
    )

    # Sprint 3: Configure Sentry error monitoring (graceful no-op if DSN unset)
    from app.integrations.sentry import configure as configure_sentry

    configure_sentry(settings.SENTRY_DSN)

    # Sprint 3: Configure Datadog custom metrics (graceful no-op if API key unset)
    from app.integrations.datadog import configure as configure_datadog

    configure_datadog(settings.DATADOG_API_KEY)

    # ADD: Configure Laminar OTLP/HTTP/json forwarder (graceful no-op if disabled)
    from app.integrations.laminar import configure as configure_laminar

    configure_laminar(
        settings.LMNR_PROJECT_API_KEY,
        settings.LMNR_ENDPOINT,
        enabled=settings.LMNR_ENABLED,
        service_name=settings.LMNR_SERVICE_NAME,
        send_prompt_content=settings.LMNR_SEND_PROMPT_CONTENT,
        sample_rate=settings.LMNR_SAMPLE_RATE,
    )
    # END ADD

    # ADD: Configure Langfuse Basic Auth OTLP dispatch (graceful no-op if disabled)
    from app.integrations.langfuse import configure as configure_langfuse

    configure_langfuse(
        settings.LANGFUSE_PUBLIC_KEY,
        settings.LANGFUSE_SECRET_KEY,
        settings.LANGFUSE_ENDPOINT,
        enabled=settings.LANGFUSE_ENABLED,
        service_name=settings.LANGFUSE_SERVICE_NAME,
        send_prompt_content=settings.LANGFUSE_SEND_PROMPT_CONTENT,
        sample_rate=settings.LANGFUSE_SAMPLE_RATE,
    )
    # END ADD

    # Sprint 1 — initialize SQLite/D1 database tables via SQLModel
    from sqlmodel import SQLModel, create_engine

    # Import models so SQLModel registers them before create_all

    # Initialize tables for local SQLite db
    # (Cloudflare D1 uses migrations, so this gracefully skips if unsupported)
    if settings.DATABASE_URL.startswith("sqlite"):
        sync_url = settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
        try:
            engine = create_engine(sync_url)
            SQLModel.metadata.create_all(engine)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Database initialization skipped: %s", exc)
            pass

    rag_service = HindsightRAGService()
    yield

    # No explicit connection cleanup required in Cloudflare Workers isolate execution model.
    rag_service.close()

    # PostHog uses direct HTTP fire-and-forget (no SDK queue to flush).
    # Pending capture tasks complete via http_forwarder's ctx.waitUntil.


app = FastAPI(
    title="EvidenceEU API",
    description="Multilingual Document Intelligence for Cross-Border Europe",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── Middleware ────────────────────────────────────────────────────────────────
# NOTE: In Starlette/FastAPI, add_middleware() wraps earlier middleware.
# The LAST add_middleware() call is OUTERMOST (runs first on inbound, last on outbound).
# CORSMiddleware MUST be outermost so every response — including error responses from
# inner middleware — receives proper CORS headers. See GitHub issue #275.

# GDPR Article 7 — consent gate (Sprint 1). Returns 451 for non-exempt routes
# lacking an X-GDPR-Consent header. See docs/security/gdpr-compliance-report.md.
app.add_middleware(GDPRConsentMiddleware)

# GDPR Article 30 — structured audit log for document/translation operations.
# Writes metadata-only entries to D1; gracefully degrades (no-op) without binding.
from app.core.middleware import (  # noqa: E402
    AuditLogMiddleware,
    DatadogMetricsMiddleware,
    DemoWarmupMiddleware,
    PostHogMiddleware,
    SentryMiddleware,
)

app.add_middleware(AuditLogMiddleware)

# Sentry middleware — captures unhandled 500s and ships to Sentry (graceful no-op if disabled)
app.add_middleware(SentryMiddleware)

# Datadog metrics middleware — records request duration + status (runs AFTER Sentry)
app.add_middleware(DatadogMetricsMiddleware)

# Demo warmup middleware — annotates cold-start responses (no-op unless DEMO_MODE=true)
app.add_middleware(DemoWarmupMiddleware)

# ADD: Laminar middleware — creates a root SERVER span per request (no-op unless LMNR_ENABLED=true)
from app.integrations.laminar import LaminarMiddleware  # noqa: E402

app.add_middleware(LaminarMiddleware)
# END ADD

# PostHog middleware — wraps each request in a PostHog context to correlate backend
# events with frontend user sessions via X-POSTHOG-DISTINCT-ID / X-POSTHOG-SESSION-ID headers.
app.add_middleware(PostHogMiddleware)

# CORS middleware — MUST be last add_middleware() call (outermost in the ASGI stack).
# This guarantees CORS headers are added to every response, including error responses
# from SentryMiddleware re-raises, GDPR 451s, and feature-flag 403s. (issue #275)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Basic liveness probe — returns 200 if the app is running."""
    return {"status": "ok", "version": "0.1.0"}
