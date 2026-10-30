# Monitoring & Observability Overview

**Date:** 2026-07-09
**Status:** Reference document — single source of truth for all monitoring tools

---

## Tool Matrix

| Tool | Surface | Technology | Key File | NFR Evidence |
|------|---------|-----------|----------|-------------|
| **Sentry** | Frontend errors | `@sentry/nextjs` SDK | `frontend/sentry.client.config.ts` | Error monitoring, session replays |
| **Sentry** | Proxy Worker errors | `@sentry/cloudflare` SDK | `worker/index.ts` → `withSentry()` | Worker crash capture |
| **Sentry** | Backend 500s | Custom Envelope forwarder (httpx) | `backend/app/integrations/sentry.py` | Unhandled exception capture |
| **Datadog** | Frontend RUM | `@datadog/browser-rum` + `@datadog/browser-logs` | `frontend/src/lib/datadog-config.ts` | NFR-09 (CDN p95 ≤ 3s), Core Web Vitals |
| **Datadog** | Backend metrics | Custom metrics forwarder (httpx) | `backend/app/integrations/datadog.py` | NFR-01 (p95 ≤ 5s), NFR-02 (error rate < 1%) |
| **Datadog** | Cloudflare edge | Logpush → Datadog (dashboard-only) | `docs/observability/datadog-logpush.md` | Worker CPU time, D1 query latency |
| **New Relic** | Frontend browser | Browser agent (script tag) | `frontend/src/lib/newrelic-config.ts` | Apdex score, transaction traces |
| **BrowserStack** | Cross-browser E2E | BrowserStack Playwright SDK on Automate | `frontend/browserstack.yml` + `.github/workflows/ci.yml` | Remote Firefox/WebKit coverage |
| **Laminar** | Backend pipeline | Custom OTLP/HTTP/json forwarder (httpx) | `backend/app/integrations/laminar.py` | Pipeline tracing, latency per stage |
| **Langfuse** | Backend LLM calls | Custom Basic Auth OTLP dispatch (httpx) | `backend/app/integrations/langfuse.py` | Model, tokens, cost per LLM call, prompt quality |

---

## Environment Variables

### Server-only (NEVER expose to browser)

| Var | Used by | Injection point |
|-----|---------|-----------------|
| `SENTRY_DSN` (backend) | Sentry forwarder | Worker secret → `worker.py` `_ENV_BINDINGS` |
| `SENTRY_DSN` (worker) | `@sentry/cloudflare` | Worker secret → CI `wrangler secret put` |
| `DATADOG_API_KEY` | Datadog metrics forwarder | Worker secret → `worker.py` `_ENV_BINDINGS` |
| `LMNR_PROJECT_API_KEY` | Laminar OTLP forwarder | Worker secret → `worker.py` `_ENV_BINDINGS` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse OTLP dispatch | Worker secret → `worker.py` `_ENV_BINDINGS` |
| `LANGFUSE_SECRET_KEY` | Langfuse OTLP dispatch | Worker secret → `worker.py` `_ENV_BINDINGS` |

### Browser-safe (NEXT_PUBLIC_ prefix)

| Var | Used by | Safe because |
|-----|---------|-------------|
| `NEXT_PUBLIC_SENTRY_DSN` | `@sentry/nextjs` | DSN is designed to be public |
| `NEXT_PUBLIC_DATADOG_APPLICATION_ID` | `@datadog/browser-rum` | App ID is public |
| `NEXT_PUBLIC_DATADOG_CLIENT_TOKEN` | `@datadog/browser-rum` | Client token ≠ API key |
| `NEXT_PUBLIC_NEW_RELIC_ENABLED` | New Relic browser agent | Explicit opt-in feature flag (`true` enables) |
| `NEXT_PUBLIC_NEW_RELIC_ACCOUNT_ID` | New Relic browser agent | Browser config is public by design |
| `NEXT_PUBLIC_NEW_RELIC_APPLICATION_ID` | New Relic browser agent | Browser app ID is public |
| `NEXT_PUBLIC_NEW_RELIC_LICENSE_KEY` | New Relic browser agent | Browser license key ≠ API key |
| `NEXT_PUBLIC_NEW_RELIC_AGENT_ID` | New Relic browser agent | Agent ID is public |
| `NEXT_PUBLIC_NEW_RELIC_TRUST_KEY` | New Relic browser agent | Trust key is public |
| `NEXT_PUBLIC_LANGFUSE_PUBLIC_KEY` | Langfuse browser tracing | Public key is public by design |

### CI-only (GitHub secrets, never in code)

| Secret | Used by |
|--------|---------|
| `SENTRY_AUTH_TOKEN` | CI sourcemap upload |
| `SENTRY_ORG` | `withSentryConfig` |
| `SENTRY_PROJECT` | `withSentryConfig` |
| `SENTRY_DSN_BACKEND` | CI → Worker secret push |
| `SENTRY_DSN_WORKER` | CI → Worker secret push |
| `BROWSERSTACK_USERNAME` | BrowserStack E2E job |
| `BROWSERSTACK_ACCESS_KEY` | BrowserStack E2E job |
| `LMNR_PROJECT_API_KEY` | CI → Worker secret push |
| `LANGFUSE_PUBLIC_KEY` | CI → Worker secret push |
| `LANGFUSE_SECRET_KEY` | CI → Worker secret push |
| `NEXT_PUBLIC_LANGFUSE_PUBLIC_KEY` | CI → frontend build env |

---

## NFR Traceability

| NFR | Tool | Metric/Feature | Evidence location |
|-----|------|----------------|-------------------|
| NFR-01 (p95 ≤ 5s) | Datadog | `evidence_eu.request.duration` gauge | Datadog → Metrics → Explorer |
| NFR-02 (error rate < 1%) | Datadog | `evidence_eu.request.count` filtered by `status:5xx` | Datadog → Metrics → Explorer |
| NFR-06 (WCAG 2.1 AA) | Chromatic | axe-core a11y tests | CI → Chromatic dashboard |
| NFR-07 (≥ 70% coverage) | pytest | Coverage report | CI → Codecov |
| NFR-08 (CI checks) | GitHub Actions | ruff + mypy + pytest + Vitest | CI → workflow runs |
| NFR-09 (CDN p95 ≤ 3s) | Datadog RUM | Core Web Vitals (LCP, FID, CLS) | Datadog → RUM → Explorer |
| NFR-10 (E2EE) | Manual | Matrix protocol audit | `docs/security/gdpr-compliance-report.md` |
| NFR-T1 (translation p95 < 2s) | Langfuse | LLM generation latency per model | Langfuse → Traces |
| NFR-T2 (terminology consistency) | Langfuse | Prompt/response text comparison | Langfuse → Traces |

---

## Dashboard Usage Guide

| Question | Open this dashboard |
|----------|-------------------|
| "Is the app erroring in production?" | **Sentry** → Issues |
| "What's the p95 latency per endpoint?" | **Datadog** → Metrics → `evidence_eu.request.duration` |
| "What's the error rate?" | **Datadog** → Metrics → `evidence_eu.request.count` filtered by `status:5xx` |
| "How fast does the frontend load?" | **Datadog** → RUM → Core Web Vitals |
| "What's the Apdex score?" | **New Relic** → Browser → Overview |
| "Are there cross-browser issues?" | **BrowserStack Automate** → EvidenceEU cross-browser E2E build; CI links the originating run |
| "What's the Worker CPU time?" | **Datadog** → Logs → Workers trace events (via Logpush) |
| "Is the D1 query slow?" | **Datadog** → Logs → D1 Query Analytics (via Logpush) |

---

## Pyodide Constraints

The following Python packages CANNOT be used in the backend (Pyodide/WASM):

| Package | Why | Alternative |
|---------|-----|------------|
| `sentry-sdk` | Uses `threading.Lock`, `socket`, `ssl` | `app/integrations/sentry.py` (custom httpx forwarder) |
| `ddtrace` | Uses `socket`, `threading`, C extensions | `app/integrations/datadog.py` (custom httpx forwarder) |
| `newrelic` (Python agent) | Uses `socket`, `threading`, C extensions | Browser agent only (frontend) |
| `lmnr` (Python SDK) | Depends on `grpcio`, `opentelemetry-sdk`, `blake3` | `app/integrations/laminar.py` (custom OTLP forwarder) |
| `langfuse` (Python SDK) | Depends on `opentelemetry-sdk` (threading) | `app/integrations/langfuse.py` (custom Basic Auth dispatch) |
| `opentelemetry-sdk` | Uses `threading.Thread` in `BatchSpanProcessor` | Custom OTLP builder (`app/integrations/otlp_builder.py`) |

All custom forwarders use the shared `app/integrations/http_forwarder.py` module for fire-and-forget POST (DRY). Laminar and Langfuse additionally share `app/integrations/otlp_builder.py` for OTLP payload construction (single source of truth).

---

## No-op Contracts

Every monitoring tool follows the same graceful-degradation pattern:

| Tool | No-op condition |
|------|----------------|
| Sentry | `SENTRY_DSN` is unset or empty |
| Datadog | `DATADOG_API_KEY` is unset or empty |
| New Relic | `NEXT_PUBLIC_NEW_RELIC_ENABLED` is not `true`, or required browser config is empty |
| BrowserStack | `BROWSERSTACK_USERNAME` or `BROWSERSTACK_ACCESS_KEY` is unset |
| Laminar | `LMNR_ENABLED` is `False` or `LMNR_PROJECT_API_KEY` is empty |
| Langfuse | `LANGFUSE_ENABLED` is `False` or `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` is empty |

Backend observability posts are registered with the current Cloudflare
invocation's `ctx.waitUntil()` through the shared `http_forwarder.py`. This
keeps Datadog, Sentry, Laminar, and Langfuse delivery alive after the response
without adding third-party network latency to the user request. Local runtimes
retain the detached `asyncio` task fallback. See the
[Cloudflare Context API](https://developers.cloudflare.com/workers/runtime-apis/context/).

When the condition is met, ALL monitoring code is a transparent no-op — no errors, no warnings, no side effects.
