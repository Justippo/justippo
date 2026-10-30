# Laminar Instrumentation Research Report

**Date:** 2026-07-09
**TL;DR:** Laminar can be instrumented across all three surfaces of EvidenceEU. The backend (Pyodide) requires a custom OTLP/HTTP/json forwarder — the `lmnr` Python SDK is non-functional in Pyodide for the same reasons as `sentry-sdk`, `ddtrace`, and `newrelic` (grpcio C extension, opentelemetry-sdk threading, blake3). The frontend (Next.js) can use the native `@lmnr-ai/lmnr` TS SDK. The proxy Worker can use Cloudflare's native OTel export (zero code, dashboard + wrangler.toml config). OTLP/HTTP/json payloads are simple hand-craftable JSON — no opentelemetry-sdk needed.

---

## 1. Executive Summary

Laminar is an OpenTelemetry-native LLM observability platform that traces AI agent execution, LLM calls, and tool usage as span trees. For EvidenceEU's three-surface architecture, the instrumentation strategy must account for the Pyodide/WASM constraint that already shaped the Sentry and Datadog integrations.

The key finding is that Laminar's OTLP/HTTP/json endpoint accepts standard JSON payloads conforming to the OTLP protocol spec — traceId and spanId as hex strings, lowerCamelCase keys, integer enum values, decimal-string timestamps in nanoseconds. This means we can construct valid trace spans using only Python stdlib (`json`, `secrets`, `time`, `uuid`) and ship them via `httpx` through the existing `http_forwarder.py` — exactly the pattern established by `sentry.py` and `datadog.py`.

The `lmnr` Python SDK (v0.7.55) depends on four packages that are non-functional in Pyodide: `grpcio` (C extension + socket + threading), `opentelemetry-sdk` (batch processor uses background threads), `opentelemetry-instrumentation-threading` (monkey-patches the threading module), and `blake3` (C extension). This is the identical constraint pattern documented in AGENTS.md for `sentry-sdk`, `ddtrace`, and `newrelic`.

For the frontend, the `@lmnr-ai/lmnr` TypeScript SDK (v0.8.26) provides automatic instrumentation and a `@observe` decorator. It initializes with a single `Laminar.initialize()` call and uses OpenTelemetry-compatible tracing. The browser/Next.js runtime is compatible.

For the proxy Worker, Cloudflare's native Workers OTel export (open beta) supports exporting traces to any OTLP endpoint via dashboard configuration + `wrangler.toml`. Cloudflare does not support binary protobuf — only HTTP-based OTLP — which is compatible with Laminar's endpoint.

Laminar's free tier provides 1GB of trace data per month with 15-day retention, which is sufficient for a capstone project.

---

## 2. Pyodide Compatibility Analysis

### 2.1 The `lmnr` Python SDK Dependency Tree

The `lmnr` package (v0.7.55) declares these core dependencies in its `pyproject.toml`:

| Dependency | Pyodide-compatible? | Why |
|-----------|-------------------|-----|
| `grpcio>=1` | ❌ No | C extension requiring native compilation; uses `socket`, `ssl`, and `threading` internally |
| `opentelemetry-sdk` (>=1.39.0, <2.0.0) | ❌ No | `BatchSpanProcessor` and `BatchLogRecordProcessor` use `threading.Thread` for background export loops |
| `opentelemetry-exporter-otlp-proto-grpc` | ❌ No | Depends on `grpcio` (C extension) |
| `opentelemetry-exporter-otlp-proto-http` | ⚠️ Partially | The HTTP exporter itself is pure Python, but it requires `opentelemetry-sdk` which uses threading |
| `opentelemetry-instrumentation-threading` | ❌ No | Monkey-patches the `threading` module — which doesn't exist in Pyodide |
| `blake3` (>=1.0.0, <2.0.0) | ❌ No | C extension/Rust extension requiring native compilation |
| `httpx` (>=0.24.0, <1.0.0) | ✅ Yes | Pure async HTTP client, already a dependency in EvidenceEU |
| `orjson` (>=3.0.0, <4.0.0) | ⚠️ Marginal | C extension, but has pure-Python fallback; however unnecessary — stdlib `json` suffices |
| `pydantic` (>=2.0.3, <3.0.0) | ✅ Yes | Already a dependency |
| `tenacity`, `python-dotenv`, `tqdm`, `packaging` | ✅ Yes | Pure Python utilities |

### 2.2 Verdict

The `lmnr` Python SDK **cannot be added to `backend/pyproject.toml`**. Four of its dependencies are architecturally incompatible with Pyodide/WASM. This follows the same pattern documented in AGENTS.md:

> The Python `sentry-sdk` uses `threading.Lock`, `socket`, and `ssl` — all non-functional in Pyodide/WASM.
> The Python `ddtrace` agent uses `socket`, `threading`, and native C extensions — all non-functional in Pyodide/WASM.

The `lmnr` SDK must be added to the AGENTS.md NEVER list alongside `sentry-sdk`, `ddtrace`, and `newrelic`.

### 2.3 Alternative: Custom OTLP/HTTP/json Forwarder

Since Laminar is an OTLP-compatible backend, we don't need the `lmnr` SDK at all. We can construct OTLP JSON payloads manually and POST them to Laminar's `/v1/traces` endpoint using `httpx` via the existing `http_forwarder.py` infrastructure. This is the same architectural decision made for Sentry (custom Envelope forwarder) and Datadog (custom metrics forwarder).

---

## 3. OTLP/HTTP/json Custom Forwarder Feasibility

### 3.1 Protocol Confirmation

The OTLP specification (v1.10.0) defines three wire formats for OTLP:
1. **OTLP/gRPC** — Protobuf over HTTP/2 (default port 4317) — NOT viable in Pyodide
2. **OTLP/HTTP/proto** — Binary Protobuf over HTTP/1.1 (default port 4318) — NOT viable (requires protobuf encoder)
3. **OTLP/HTTP/json** — JSON over HTTP/1.1 (default port 4318) — ✅ VIABLE with only `httpx` + stdlib `json`

Laminar's backend supports all three formats. The OTLP/HTTP/json endpoint for Laminar cloud is:

```
POST https://api.lmnr.ai:443/v1/traces
Content-Type: application/json
Authorization: Bearer <LMNR_PROJECT_API_KEY>
```

### 3.2 JSON Payload Structure

The OTLP/HTTP/json format uses Proto3 JSON mapping with specific deviations:

- **Keys are lowerCamelCase** (e.g., `droppedAttributesCount`, not `dropped_attributes_count`)
- **`traceId` and `spanId` are hex-encoded strings** (not base64) — 32 hex chars for traceId, 16 for spanId
- **Enum values are integers** (e.g., `kind: 2` for `SPAN_KIND_SERVER`, not the string name)
- **64-bit integers are decimal strings** (e.g., `"startTimeUnixNano": "1581452773000000512"`)
- **Receivers MUST ignore unknown fields** — forward compatibility is guaranteed

A minimal valid trace payload:

```json
{
  "resourceSpans": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "evidence-eu-api"}}
        ]
      },
      "scopeSpans": [
        {
          "scope": {"name": "evidence-eu.laminar-forwarder"},
          "spans": [
            {
              "traceId": "5b8efe124c889990330312012c4a0230",
              "spanId": "3c191d03fa8be065",
              "name": "POST /api/v1/translate",
              "kind": 2,
              "startTimeUnixNano": "1581452773000000512",
              "endTimeUnixNano": "1581452773000000756",
              "attributes": [
                {"key": "http.method", "value": {"stringValue": "POST"}},
                {"key": "http.status_code", "value": {"intValue": "200"}},
                {"key": "lmnr.span.type", "value": {"stringValue": "DEFAULT"}}
              ],
              "status": {"code": 1}
            }
          ]
        }
      ]
    }
  ]
}
```

### 3.3 Span Kind Values

| Integer | Constant | Meaning |
|---------|----------|---------|
| 0 | UNSPECIFIED | Unspecified |
| 1 | INTERNAL | Internal operation |
| 2 | SERVER | Server receives a request |
| 3 | CLIENT | Client sends a request |
| 4 | PRODUCER | Producer sends to async destination |
| 5 | CONSUMER | Consumer receives from async source |

### 3.4 Laminar-Specific Span Attributes

Laminar reads specific attributes to render traces in its UI:

| Attribute | Purpose |
|-----------|---------|
| `lmnr.span.type` | Span type: `LLM`, `TOOL`, `EXECUTOR`, `DEFAULT` |
| `lmnr.span.path` | Dot-separated path for grouping |
| `gen_ai.system` | Model provider name (e.g., `mistral`, `cf-workers-ai`) |
| `gen_ai.usage.input_tokens` | Input token count |
| `gen_ai.usage.output_tokens` | Output token count |
| `gen_ai.usage.cost` | Cost of the LLM call |
| `gen_ai.prompt.{i}.content` | Input message content |
| `gen_ai.prompt.{i}.role` | Input message role |

### 3.5 Implementation Viability

A custom forwarder can be built using:
- `json` (stdlib) — payload serialization
- `secrets` (stdlib) — generate hex traceId/spanId
- `time` (stdlib) — nanosecond timestamps via `time.time_ns()`
- `httpx` (existing dependency) — async HTTP POST
- `http_forwarder.fire_and_forget()` (existing module) — non-blocking dispatch

**No new dependencies needed.** The forwarder follows the exact pattern of `sentry.py` (build_envelope → ship_to_sentry) and `datadog.py` (build_metric_series → ship_metrics).

---

## 4. Frontend (Next.js) Integration — Retired

> **Current decision (2026-07-15):** EvidenceEU does not export Laminar traces directly
> from the browser. Browser-to-Laminar OTLP requests were rejected by Laminar's CORS
> policy and produced noisy console failures. Pipeline telemetry remains server-side via
> `backend/app/integrations/laminar.py`; browser performance and errors remain covered by
> Datadog RUM, Sentry, and New Relic.

### 4.1 SDK Compatibility

The `@lmnr-ai/lmnr` TypeScript SDK (v0.8.26) provides:
- `Laminar.initialize({ projectApiKey })` — one-time initialization
- `observe({ name }, fn)` — wrap functions to create spans
- `observeDecorator(config)` — class method decorator
- Automatic instrumentation of OpenAI, Anthropic, Vercel AI SDK, LangChain calls

The SDK uses OpenTelemetry-compatible tracing under the hood. In a browser/Next.js client context, it uses OTLP/HTTP (fetch API), not gRPC — making it compatible with Cloudflare Pages and browser environments.

### 4.2 Integration Pattern

Following the established pattern from `DatadogInit.tsx`:

1. `bun add @lmnr-ai/lmnr` in `frontend/`
2. Create `frontend/src/lib/laminar-config.ts` — config with `NEXT_PUBLIC_LMNR_PROJECT_API_KEY`
3. Create `frontend/src/components/LaminarInit.tsx` — client component with `'use client'` directive, dynamic import
4. Initialize in `layout.tsx` — trace page navigation, API calls, user interactions

The project API key is browser-safe by design (same as `NEXT_PUBLIC_DATADOG_CLIENT_TOKEN`).

### 4.3 Value Proposition

Frontend tracing captures:
- User interaction flows (document upload → translate → search)
- API call latency from the browser perspective
- Error context with full request/response traces
- Correlation with backend traces via shared trace IDs (W3C Trace Context headers)

---

## 5. Proxy Worker Integration

### 5.1 Cloudflare Native OTel Export

Cloudflare Workers now supports native OpenTelemetry export (open beta as of 2026). The feature:

- Exports traces and logs to any OTLP-compatible endpoint
- **Does NOT support binary protobuf** — only HTTP-based OTLP
- Configured via dashboard destination + `wrangler.toml`
- Supports head-based sampling
- Free for Workers Paid users during beta; $0.05/million events after March 2026

### 5.2 Configuration

1. **Dashboard:** Create a destination named `laminar-traces` with:
   - OTLP Endpoint: `https://api.lmnr.ai/v1/traces`
   - Custom Headers: `Authorization: Bearer <LMNR_PROJECT_API_KEY>`

2. **wrangler.toml:**
```toml
[observability.traces]
enabled = true
destinations = ["laminar-traces"]
head_sampling_rate = 0.1
persist = false
```

3. **Zero code changes** — Cloudflare auto-instruments the Worker's fetch handler.

### 5.3 Limitations

- Metrics export not yet supported
- The proxy Worker just forwards `/api/v1/*` — limited tracing value beyond the fetch span
- Lower priority than backend and frontend instrumentation

---

## 6. AI Gateway & LLM Call Visibility

### 6.1 The Challenge

EvidenceEU routes all LLM calls through `app/integrations/cloudflare/gateway.py` → Cloudflare AI Gateway. Since we can't use the `lmnr` SDK's auto-instrumentation (which monkey-patches OpenAI/Anthropic clients), we need manual span creation at the service layer.

### 6.2 Manual Span Strategy

Create spans around the key pipeline stages:

```
POST /api/v1/documents/          → root span "document.upload"
  ├── OCR span "document.ocr"    → model, input_tokens, output_tokens, latency
  └── Classification span        → "document.classify"

POST /api/v1/translate/           → root span "translate.request"
  └── Translation span "translate.llm" → model, source_lang, target_lang, latency

GET /api/v1/search/              → root span "search.rag"
  ├── Embedding span "search.embed"   → model, chunk_count
  ├── Retrieval span "search.retrieve" → top_k, scores
  └── Generation span "search.generate" → model, tokens, latency
```

Each LLM span includes Laminar's `gen_ai.*` attributes so the Laminar UI renders them as LLM spans with token/cost tracking.

### 6.3 GDPR Consideration

**Critical:** Laminar traces may contain document content if we populate `gen_ai.prompt.{i}.content` attributes. This is a PII risk for a document intelligence platform processing legal documents.

**Mitigation:** The custom forwarder should:
1. Default to `ignore_input=True` for any span touching document content
2. Only send metadata attributes (model, token counts, latency, language pair) — never raw text
3. Follow the same PII stripping pattern as `datadog.py`'s `normalize_route()` function
4. Add a `LMNR_SEND_PROMPT_CONTENT` config flag (default `false`) for controlled debugging

---

## 7. Observability Stack Overlap Analysis

| Tool | Primary Purpose | What It Captures | Overlap with Laminar |
|------|----------------|-----------------|---------------------|
| **Sentry** | Error tracking | Unhandled exceptions, stack traces, request context | Minimal — Sentry is error-first; Laminar is trace-first |
| **Datadog Metrics** | Infrastructure metrics | Request duration, error rate, p95 latency (NFR-01/02) | Some overlap on latency, but Laminar adds LLM-specific dimensions (tokens, model, cost) |
| **Datadog RUM** | Frontend performance | Core Web Vitals, page load times (NFR-09) | Minimal — RUM is browser perf; Laminar is user journey tracing |
| **New Relic Browser** | Apdex, transaction traces | Frontend transaction traces | Some overlap with Laminar frontend traces |
| **Laminar** | LLM observability | LLM call traces (prompts, responses, tokens, cost), agent execution trees, pipeline causality | Unique — no existing tool captures LLM call details |

**Verdict:** Laminar is complementary, not redundant. The existing stack captures infrastructure and error telemetry. Laminar adds the missing dimension: what the LLM models actually did (which model, how many tokens, what latency, what cost) and how pipeline stages relate causally.

---

## 8. GDPR & PII Considerations

### 8.1 Data Flow

```
Backend span → httpx POST → Laminar cloud (api.lmnr.ai) → ClickHouse storage
```

Laminar cloud is hosted (not self-hosted). Trace data leaves the Cloudflare Worker boundary. This is the same data flow as Sentry and Datadog — third-party SaaS observability.

### 8.2 PII Risk Assessment

| Span Type | PII Risk | Mitigation |
|-----------|----------|------------|
| HTTP request span | Low — only method, route, status | Same as Datadog: normalize route, strip query params |
| LLM call span | **High** — prompt/response may contain document content | Default: don't send `gen_ai.prompt.*.content`; only send metadata |
| Translation span | Medium — source/target language is metadata, not content | Safe — only send language codes, not text |
| OCR span | Low — only send page count, model, confidence | Safe — no document text |
| Search/RAG span | Medium — query may contain PII | Strip query content; only send chunk count, scores, model |

### 8.3 Consent Integration

The existing `GDPRConsentMiddleware` gates all document/translation endpoints. Laminar spans should only be created for requests that pass the consent gate — the middleware runs before the endpoint, so spans created in the endpoint handler are already consent-gated.

---

## 9. Recommended Implementation Plan

### Phase 1: Backend Custom Forwarder (High Value)

**Files to create:**
- `backend/app/integrations/laminar.py` — OTLP/HTTP/json forwarder (follows `sentry.py`/`datadog.py` pattern)
  - `configure(api_key, base_url)` — module-level state, no-op if key unset
  - `build_trace_payload(spans)` — construct OTLP JSON
  - `ship_traces(payload)` — fire-and-forget POST via `http_forwarder.py`
  - `create_span(name, kind, start_ns, end_ns, attributes, parent_span_id)` — span builder
  - `@observe(name)` decorator — wraps async functions, auto-creates spans
  - Context manager `span_context(name)` — for `with` block usage
  - Trace ID propagation via context vars (asyncio-safe, no threading)

**Files to modify:**
- `backend/app/core/config.py` — add `LMNR_PROJECT_API_KEY`, `LMNR_BASE_URL`, `LMNR_SEND_PROMPT_CONTENT` settings
- `backend/app/core/middleware.py` — add `LaminarMiddleware` (creates root span per request)
- `backend/app/main.py` — call `configure_laminar(settings.LMNR_PROJECT_API_KEY)` in lifespan, add middleware

**Key design decisions:**
- Use `contextvars` (not `threading.local`) for trace context propagation — asyncio-safe
- Generate traceId (32 hex chars) and spanId (16 hex chars) using `secrets.token_hex()`
- Timestamps via `time.time_ns()` — nanosecond precision, stdlib only
- Default: no prompt/response content in spans (GDPR-safe)
- No-op contract: if `LMNR_PROJECT_API_KEY` is empty, all functions return immediately

### Phase 2: Frontend SDK Integration (Retired)

This phase was evaluated and removed. Do not restore browser-side Laminar credentials or
direct browser OTLP export unless Laminar publishes a supported browser ingestion contract.

**Files to create:**
- `frontend/src/lib/laminar-config.ts` — config wrapper
- `frontend/src/components/LaminarInit.tsx` — client component (`'use client'` + dynamic import)

**Files to modify:**
- `frontend/package.json` — add `@lmnr-ai/lmnr` dependency
- `frontend/src/app/layout.tsx` — mount `LaminarInit` component
- `frontend/.env.local` — add `NEXT_PUBLIC_LMNR_PROJECT_API_KEY`

### Phase 3: Proxy Worker OTel Export (Low Value, Zero Code)

**Files to modify:**
- `worker/wrangler.toml` — add `[observability.traces]` section
- Dashboard: create Laminar destination

### Phase 4: AGENTS.md & Documentation

**Files to modify:**
- `AGENTS.md` — add `lmnr` to NEVER list; add Laminar to Pyodide Constraint Catalog
- `docs/observability/monitoring-overview.md` — add Laminar to dashboard usage guide

### Phase 5: Verify

1. Run `npx lmnr-cli setup` (interactive — may need to run manually in terminal)
2. Set `LMNR_PROJECT_API_KEY` in `backend/.env`
3. Run `make dev` (Docker Compose full stack)
4. Hit the pipeline: upload document → translate → search
5. Verify: `lmnr-cli sql query "SELECT * FROM traces ORDER BY start_time DESC LIMIT 1" --json`
6. View traces at https://laminar.sh dashboard

---

## 10. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| `lmnr-cli setup` hangs in non-interactive shell | Low | Run with `--no-browser` flag; user visits URL manually |
| Trace volume exceeds 1GB free tier | Low | Head-based sampling (10% default); capstone demo volume is minimal |
| PII leaks into trace attributes | High | Default `LMNR_SEND_PROMPT_CONTENT=false`; only send metadata attributes |
| Context var propagation breaks across middleware boundaries | Medium | Test with integration tests; fall back to explicit traceId passing |
| Laminar API downtime blocks requests | Low | Fire-and-forget pattern — POST failure is logged at DEBUG, never raised |
| `lmnr` SDK accidentally added to pyproject.toml | Medium | AST test (like BabelDOC import check) to enforce no `lmnr` import |
| Cloudflare Workers OTel export is still beta | Low | Proxy Worker tracing is Phase 3 (lowest priority); backend/frontend don't depend on it |

---

## Research Metadata

- Sources searched: 15 queries across OTLP specs, Laminar docs, Cloudflare docs, PyPI, npm, GitHub
- Sources fetched and analyzed: 12
- Key sources cited: OTLP spec v1.10.0, Laminar OpenTelemetry docs, Laminar pricing comparison blog, Cloudflare Workers OTel export docs, lmnr-python pyproject.toml, Honeycomb OTLP JSON example, Better Stack OTLP deep dive
