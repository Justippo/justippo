# AGENTS.md

Runtime instruction set for AI coding agents. Every line prevents a mistake or tells you how to verify your work.

---

## Project Overview

**EvidenceEU** — Multilingual document intelligence platform for cross-border document users in Europe. Phase 1 (capstone): legal/administrative/HR documents. Phase 2 (roadmap): healthcare/EHDS — "OpenEvidence for Europe" clinical decision support. MSSE Capstone, Quantic School of Business and Technology.

**Team:** Mihai Chindriș (sole submitter — PO/Dev)

---

## Boundaries

### ALWAYS
- Run `make lint` before committing
- Run `make test-backend` or `cd backend && uv run pytest <test> -v` before committing
- Use `uv` for Python deps (not pip)
- Route all LLM calls through `app/integrations/cloudflare/gateway.py`

### ASK FIRST
- Modifying `worker.py` (sys.modules injection — do not remove)
- Changing `wrangler.toml` files
- Adding new Python dependencies
- Modifying GDPR middleware or consent flow

### NEVER
- Direct LLM API URLs outside `app/integrations/cloudflare/gateway.py` (CI enforces via REM-8 grep)
- Disk writes in backend — runs in Pyodide (Cloudflare Python Worker), in-memory only
- Propose Odoo as alternative or fallback (evaluated and rejected)
- Add healthcare features to MVP scope (architecture supports it, capstone does not build it)
- Revert use-case.md to clinical framing (v3.0 is canonical, cross-border only)
- Add `sentry-sdk` to backend `pyproject.toml` — uses threading.Lock/socket/ssl, all non-functional in Pyodide/WASM (use `app/integrations/sentry.py` custom forwarder instead)
- Add `ddtrace` to backend `pyproject.toml` — uses socket/threading/C extensions, all non-functional in Pyodide/WASM (use `app/integrations/datadog.py` custom forwarder instead)
- Add `newrelic` (Python agent) to backend `pyproject.toml` — uses socket/threading/C extensions, all non-functional in Pyodide/WASM (use browser agent only — frontend)
- Add `lmnr` to backend `pyproject.toml` — depends on grpcio/opentelemetry-sdk/opentelemetry-instrumentation-threading/blake3, all non-functional in Pyodide/WASM (use `app/integrations/laminar.py` custom OTLP/HTTP/json forwarder instead — see `docs/adal/laminar-instrumentation-research.md`)
- Add `grpcio` to backend `pyproject.toml` — C extension using socket/ssl/threading, non-functional in Pyodide/WASM (transitive dep of lmnr, opentelemetry-exporter-otlp-proto-grpc)
- Add `opentelemetry-sdk` to backend `pyproject.toml` — BatchSpanProcessor uses threading.Thread for background export loops, non-functional in Pyodide/WASM (transitive dep of lmnr)
- Add `opentelemetry-instrumentation-threading` to backend `pyproject.toml` — monkey-patches the threading module (does not exist in Pyodide), non-functional in Pyodide/WASM (explicit dep of lmnr)
- Add `blake3` to backend `pyproject.toml` — C/Rust extension requiring native compilation, non-functional in Pyodide/WASM (transitive dep of lmnr)
- Add `langfuse` to backend `pyproject.toml` — depends on opentelemetry-sdk which uses threading.Thread in BatchSpanProcessor, non-functional in Pyodide/WASM (use `app/integrations/langfuse.py` custom Basic Auth OTLP dispatch instead — see `docs/adal/laminar-instrumentation-research.md`)
- Add `opentelemetry-sdk` to backend `pyproject.toml` — BatchSpanProcessor uses threading.Thread for background export loops, non-functional in Pyodide/WASM (already documented above as transitive dep of lmnr; also blocks langfuse SDK)

---

## Architecture

```
Browser → Cloudflare Pages (Next.js) → Proxy Worker (worker/index.ts) → API Worker (backend/app/worker.py) → FastAPI (backend/app/main.py)
```

- Proxy → API Worker via **Service Binding** (not HTTP) — defined in `worker/wrangler.toml`
- `worker.py` injects `app` into `sys.modules` to fix Wrangler's bundle flattening
- All LLM calls → `app/integrations/cloudflare/gateway.py` → Cloudflare AI Gateway (CI-enforced)
- `GDPRConsentMiddleware` runs on every request; missing consent headers → `451 Unavailable For Legal Reasons`

### Sentry Integration (Sprint 3)

**Three-surface observability with no sentry-sdk in Pyodide:**

| Surface | Technology | Key file |
|---------|-----------|----------|
| Frontend (Next.js) | `@sentry/nextjs` SDK | `frontend/instrumentation.ts` + `frontend/instrumentation-client.ts` + `sentry.server.config.ts` |
| Proxy Worker | `@sentry/cloudflare` SDK | `worker/index.ts` → `withSentry()` wrapper |
| API Worker (FastAPI) | Custom Envelope forwarder | `backend/app/integrations/sentry.py` |

**Why a custom forwarder for the FastAPI backend:**
The Python `sentry-sdk` uses `threading.Lock`, `socket`, and `ssl` — all non-functional in Pyodide/WASM. The custom forwarder in `app/integrations/sentry.py` uses only `httpx` (already a dependency) and implements the Sentry Envelope API directly. See `AGENTS.md` NEVER list — do NOT add `sentry-sdk` to `pyproject.toml`.

**SENTRY_DSN env var — three injection points:**
- **Frontend:** `NEXT_PUBLIC_SENTRY_DSN` in `frontend/.env.local` (build-time, safe for browser)
- **Proxy Worker:** `SENTRY_DSN` as Cloudflare Worker secret → `wrangler secret put` in CI
- **API Worker:** `SENTRY_DSN` as Cloudflare Worker secret → `worker.py` `_ENV_BINDINGS` → `os.environ`

**No-op contract (all three surfaces):**
If `SENTRY_DSN` is unset or empty, ALL Sentry code must be a transparent no-op. No errors, no warnings, no side effects. Follows the same graceful-degradation pattern as `D1Client`.

### Sentry Gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| `sentry-sdk` import fails in Pyodide | Uses threading/socket/ssl | Use `app/integrations/sentry.py` custom forwarder instead |
| Frontend build fails with `Cannot find module '@sentry/nextjs'` | `bun install` not run after adding dep | Run `cd frontend && bun add @sentry/nextjs` |
| Worker deploy fails with `Cannot find module '@sentry/cloudflare'` | `bun install` not run in worker dir | Run `bun add @sentry/cloudflare` (from repo root — workspace) |
| Sentry shows `0ms` spans on Cloudflare Workers | V8 isolate security model — timers don't advance during CPU-bound work | Expected behavior; see Sentry CF Workers docs |
| `withSentry` type error in worker | `process.env` not available in Workers | Use hardcoded env string or `env.APP_ENV` binding |
| SentryMiddlware blocks health checks | Middleware catches all exceptions including `/health` | Middleware only catches unhandled 500s — health probe 200s pass through untouched |

### Datadog Integration (Sprint 3)

**Three-surface observability (frontend RUM + backend metrics + Cloudflare Logpush):**

| Surface | Technology | Key file |
|---------|-----------|----------|
| Frontend (Next.js) | `@datadog/browser-rum` + `@datadog/browser-logs` | `frontend/src/lib/datadog-config.ts` + `frontend/src/components/DatadogInit.tsx` |
| API Worker (FastAPI) | Custom metrics forwarder via httpx | `backend/app/integrations/datadog.py` |
| Cloudflare edge | Logpush → Datadog (dashboard-only) | `docs/observability/datadog-logpush.md` |

**Why a custom metrics forwarder for the FastAPI backend:**
The Python `ddtrace` agent uses `socket`, `threading`, and native C extensions — all non-functional in Pyodide/WASM. The custom forwarder in `app/integrations/datadog.py` uses only `httpx` (already a dependency) via the shared `http_forwarder.py` module. See `AGENTS.md` NEVER list — do NOT add `ddtrace` to `pyproject.toml`.

**Shared HTTP forwarder (DRY):**
Both `sentry.py` and `datadog.py` use `app/integrations/http_forwarder.py` for fire-and-forget POST. This is the single place where `asyncio.create_task` + no-loop fallback logic lives — zero duplication.

**DATADOG_API_KEY — server-only, never exposed to browser:**
- **Backend:** `DATADOG_API_KEY` as Cloudflare Worker secret → `worker.py` `_ENV_BINDINGS` → `os.environ`
- **Frontend:** `NEXT_PUBLIC_DATADOG_APPLICATION_ID` + `NEXT_PUBLIC_DATADOG_CLIENT_TOKEN` (client token ≠ API key — safe for browser by design)

**NFR Traceability:**
- NFR-01 (p95 latency ≤ 5s): `evidence_eu.request.duration` metric, grouped by route tag
- NFR-02 (error rate < 1%): `evidence_eu.request.count` metric, filtered by `status:5xx` tag
- NFR-09 (CDN p95 load ≤ 3s): Datadog RUM Core Web Vitals from `@datadog/browser-rum`

**Middleware order constraint:**
`DatadogMetricsMiddleware` must run AFTER `SentryMiddleware` in the stack so Sentry captures errors before Datadog records the status code. In FastAPI, later-added middleware wraps earlier middleware — Datadog is added last, so it measures the full request lifecycle including Sentry's error handling.

**No-op contract:**
If `DATADOG_API_KEY` is unset or empty, ALL Datadog code must be a transparent no-op. Same pattern as Sentry and D1Client.

### Datadog Gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ddtrace` import fails in Pyodide | Uses socket/threading/C extensions | Use `app/integrations/datadog.py` custom forwarder instead |
| Frontend build fails with `Cannot find module '@datadog/browser-rum'` | `bun install` not run | Run `cd frontend && bun add @datadog/browser-rum @datadog/browser-logs` |
| No metrics in Datadog dashboard | Wrong API key or site | Verify `DATADOG_API_KEY` in Datadog → Organization Settings → API Keys |
| High cardinality tags | UUIDs in route paths | `normalize_route()` in `datadog.py` replaces UUIDs with `{id}` |
| PII in metric tags | Query params contain document content | `normalize_route()` strips ALL query params from tags |
| Datadog RUM not loading on Pages | SSR crash from `datadogRum.init()` | `DatadogInit` component uses `'use client'` + dynamic import |

### BrowserStack + New Relic (Sprint 3)

**BrowserStack cross-browser E2E:**
- Runs Firefox + WebKit on real devices (main-branch push ONLY — never on PRs)
- Chromium is already covered in the frontend CI job (every push) — complementary, not duplicated
- No `BROWSERSTACK_LOCAL` tunnel needed — tests hit the public deployed URL (`LIVE_FRONTEND_URL`)
- `continue-on-error: true` — BrowserStack rate limits never block the deployment pipeline
- GitHub secrets: `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY`

**New Relic browser agent:**
- Frontend-only — the Python/Node.js agent uses socket/threading, not viable in Pyodide
- Same constraint as `sentry-sdk` and `ddtrace` — see AGENTS.md NEVER list
- Injected via `next/script` with `strategy="beforeInteractive"` in `layout.tsx`
- Config in `frontend/src/lib/newrelic-config.ts` (same DRY pattern as Sentry + Datadog)
- Browser-safe env vars: `NEXT_PUBLIC_NEW_RELIC_*` (browser license key ≠ API key)

**Dashboard usage guide (which tool to open for which question):**
- **Sentry** → "Is the app erroring in production?"
- **Datadog Metrics** → "What's the p95 latency per endpoint?" / "What's the error rate?"
- **Datadog RUM** → "How fast does the frontend load?" (Core Web Vitals)
- **New Relic Browser** → "What's the Apdex score?" / "Show me transaction traces"
- **BrowserStack** → "Are there cross-browser issues?" (CI job logs)
- **Datadog Logs** → "What's the Worker CPU time?" / "Is D1 slow?" (via Logpush)
- **Laminar** → "What did the LLM call actually do?" (model, tokens, cost, latency per pipeline stage) / "Why did the translation come out wrong?" (trace the full request flow through OCR → translate → RAG search)

**Full reference:** `docs/observability/monitoring-overview.md` — single source of truth for all monitoring tools, env vars, and NFR mapping.



Before writing code for any task, follow this process:

1. **Product design** — What does this feature do for the user? Success criteria? Scope boundaries?
2. **Technical design** — Function signatures, API contracts, component props, test seams, module layout. Ask architecture questions before choosing patterns (e.g., "Should this use a new endpoint or extend an existing one?"). Do NOT start implementation until this is confirmed.
3. **Plan** — Step-by-step in what order to build and test.
4. **Implement** — Write code, following the design exactly. If the design proves wrong mid-implementation, stop and revise the design first.

Each PR must include a **"Deviations from plan"** section noting where implementation diverged from spec and why.

---

## Gotchas (Symptom → Cause → Fix)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `wrangler deploy` fails with bundling error | `worker.py` sys.modules injection removed | Restore the injection block in `worker.py` |
| CI fails with "direct LLM URL detected" | URL outside `app/integrations/cloudflare/gateway.py` | Move URL to cloudflare/gateway.py, import from there |
| `docker compose config` errors on missing `.env` | `frontend/.env.local` doesn't exist | Create stub: `NEXT_PUBLIC_API_URL=http://localhost:8000` |
| Hindsight crashes with "LLM API key required" | Docker Compose `.env` doesn't inject into containers | Add `env_file: - ./.env` to hindsight service in `docker-compose.yml` |
| pytest fails with import errors | Wrong dep group installed | Backend uses `workers` group for deploy, full groups for local dev |
| Backend 451 on all requests | Missing `X-GDPR-Consent` header | Include consent header in requests (see middleware.py) |
| D1 migrations not applied | New migration SQL isn't added to CI deploy step | Add `wrangler d1 migrations apply` step to `.github/workflows/ci.yml` |
| `wrangler deploy` breaks on API change | `compatibility_date` is stale (2024-05-02) | Bump cautiously — test locally first, then update all 3 wrangler.toml files |
| CI token verification fails | `CLOUDFLARE_API_TOKEN` expired or is a Global API Key | Regenerate a scoped API token in Cloudflare dashboard; CI verifies via `/user/tokens/verify` |
| `_headers` file changes not reflected | `frontend/public/_headers` edited but frontend not redeployed | `_headers` is read at Pages deploy time; run deploy CI again |
| D1 `migrations apply` creates tracking table on first run | Existing DB has tables from prior `execute --file` | First run is safe — all SQL uses `IF NOT EXISTS`; `d1_migrations` table tracks future migrations |
| Notion→ClickUp sync not running | `CLICKUP_API_TOKEN` secret missing or expired | Check GitHub repo → Settings → Secrets; regenerate token if expired |
| ClickUp tasks stale after Notion update | Sync workflow failed silently or cron didn't fire | Check Actions → sync-notion-to-clickup → latest run logs |
| ClickUp tasks duplicated | Name-matching index has collisions (normalized names collide) | Check workflow logs for "UPDATED" duplicates; fix task names in Notion |

---

## Essential Commands

```bash
make dev                # Full stack via Docker Compose
make lint               # Ruff (backend) + ESLint (frontend)
make format             # Ruff + Prettier
make test-backend       # pytest in container
make test-frontend      # Vitest
make test-e2e           # Playwright
```

### Single backend test
```bash
cd backend && uv run pytest tests/path/to/test_file.py::test_name -v
```

### Deploy (CI auto-deploys on push to main)
```bash
cd backend && uv run --group workers pywrangler deploy
cd worker  && npx wrangler deploy --env production
cd frontend && npx wrangler pages deploy out --project-name evidence-eu-frontend --branch main
```

---

## Project Decisions (Don't Re-Litigate)

- **Phase 1 market:** Cross-border migrants, legal professionals, HR — NOT healthcare
- **Phase 2 market:** Healthcare / EHDS — architecture supports it, capstone excludes it
- **Odoo:** Evaluated and rejected
- **3 languages in MVP:** English, German, French

---

## When Editing use-case.md

- v3.0 is canonical. Do not revert to clinical framing.
- Section 10 Odoo = "evaluated and rejected," not "viable fallback."
- Do not add healthcare features to MVP scope.

---

## Task Status

See GitHub Issues for open tasks and sprint tracking.

---

## OCR Benchmark Protocol

### Fixture Generator

**Location:** `backend/tests/benchmark/pdf_fixture_generator.py`

- **In-memory generation** (CI-safe, no disk writes): `generate_all_samples()` → returns 10 `SampleMeta` with PDF bytes. Used by `TestOCRBenchmark`.
- **Disk fixture generation** (manual validation): `save_fixtures_to_disk(output_dir)` → writes 10 `.pdf` files to disk. Uses pypdfium2 + Pillow scan simulation pipeline for fixtures d04 and d09.
- **To regenerate fixtures:**
  ```bash
  cd backend && uv run python -c "from tests.benchmark.pdf_fixture_generator import save_fixtures_to_disk; from pathlib import Path; save_fixtures_to_disk(Path('tests/benchmark/fixtures'))"
  ```
- **Fixture files live in:** `backend/tests/benchmark/fixtures/` (git-committed, synthetic data only — GDPR-safe)

### Manual Validation Pass Protocol

**What "sign-off" means operationally:**
1. Regenerate fixtures to disk (command above)
2. Open each `.pdf` in a viewer — confirm text is readable, formatting is correct
3. Run full benchmark: `cd backend && uv run pytest tests/benchmark/ -k "not Live and not Reducto" -v`
4. Verify: all 16 tests pass, no regressions
5. Fill in the per-fixture pass/fail checklist in `docs/testing/ocr-benchmark.md`

### Sign-off Criteria

A benchmark run passes when:
- All 10 Mistral-path tests pass (`TestOCRBenchmarkWithDiskFixtures::test_disk_fixture_mistral[*]`)
- Tesseract fallback test passes (`test_tesseract_fallback_all_fixtures`)
- No existing benchmark tests regress (5 tests in `TestOCRBenchmark`)
- Blank page fixture (d10) returns confidence < 0.1 or empty text
- Non-blank fixtures return confidence > 0.5 (Mistral) or text > 0 chars (Tesseract)

### ß/Unicode Constraint

**re.IGNORECASE does not handle ß → SS case folding** — `ß.upper()` = `'SS'` (2 chars), but `'SS'.lower()` = `'ss'` (not `'ß'`). Test cases deliberately use ä/ö/ü but NEVER ß. Cross-reference: translation QA task handles ß case folding at the application level.

---

## Translation Accuracy Test Suite

### ß / Unicode Case Folding

**Never rely on `re.IGNORECASE` for German `ß` → `ss` equivalence.** Python's regex
engine uses simple case folding, so `ß` does not match `SS` and vice versa.
The translation accuracy suite uses `tests.translation_accuracy_utils.normalize_for_comparison()`,
which applies `str.casefold()` (correctly folds `ß` to `ss`) plus punctuation stripping
and whitespace collapsing. All case-insensitive comparisons in translation tests must
use this helper or import `term_present()` from the same module.

### Mock vs Real Model Tests

| Suite | File | Speed | Runs when |
|-------|------|-------|-----------|
| Mock-based | `backend/tests/integration/test_translation_accuracy.py` | Fast | Always (CI default) |
| Real m2m100 | `TestTranslationAccuracyRealModel` in same file | ~30s for 23 cases | Only when `TRANSLATION_INTEGRATION_TESTS=true` |

The real-model suite calls `TranslationService.translate_text()` and therefore exercises
the same Cloudflare AI Gateway path as production. It is gated by an environment variable
so CI does not accidentally burn Workers AI quota on every push.

### Running Real Model Tests

```bash
export TRANSLATION_INTEGRATION_TESTS=true
export TRANSLATION_TEST_DELAY_S=0.5
cd backend && uv run pytest tests/integration/test_translation_accuracy.py -v -k RealModel
```

### Failure Classification

Real-model failures are classified automatically as:
- **SERVICE_BUG** — TranslationService raised an exception or returned a failed job.
- **MODEL_LIMITATION** — Translation was produced but expected/forbidden term checks failed.
- **TEST_CASE_STALE** — The source term leaked into the output untranslated; review the YAML expectation.

---

## BabelDOC Sidecar Pattern

### Why BabelDOC Cannot Run in Pyodide

BabelDOC requires PyTorch, DocLayout-YOLO (ONNX), disk I/O, and threading — the same fundamental constraints that prevent `sentry-sdk`, `ddtrace`, and `newrelic` from running in Cloudflare Python Workers (Pyodide/WASM). Cross-reference: Sentry Integration section above.

### HTTP Boundary Rule

BabelDOC is called over HTTP only, NEVER imported as a Python module in the FastAPI app. The adapter lives at `backend/app/integrations/babeldoc_adapter.py`. Direct imports would violate AGPL license isolation.

### AGPL Isolation Principle

The HTTP boundary is what keeps AGPL from propagating to EvidenceEU's MIT codebase:
- BabelDOC runs as a separate Docker container (sidecar)
- Communication is via HTTP POST to `/translate`
- The adapter uses `httpx` (already a dependency, Pyodide-safe)
- An AST test in `tests/unit/test_babeldoc_adapter.py` enforces that `babeldoc` is never imported directly in services or API code

**Do NOT** accidentally import BabelDOC directly — this would propagate AGPL to the entire codebase.

### License CI Check

`.github/workflows/license-check.yml` runs on PRs that modify `backend/pyproject.toml`:
- Generates dependency license report via `pip-licenses`
- **Warnings** (non-blocking): AGPL/GPL/LGPL — acceptable due to sidecar isolation (ADR-008)
- **Hard fail**: SSPL, Commons Clause, Proprietary — cannot redistribute
- Report uploaded as CI artifact for audit trail

---

## NFR Evidence Map (canonical reference)

> `docs/requirements.md` links here for evidence citations. Do NOT duplicate this list.
> Commit SHAs reference the backend HEAD at time of evidence collection.

| NFR | Evidence file | Result | Commit |
|-----|--------------|--------|--------|
| NFR-01 (p95 ≤ 5s) | `tests/benchmark/test_ocr_benchmark.py` | OCR mean ~250ms, 16/16 benchmark tests pass | 78950e5 |
| NFR-01 (p95 ≤ 5s) | `tests/benchmark/k6_search.js` + `docs/testing/performance-report.md §10` | ✅ k6 live run 2026-07-16: 141 iters, 0 errors, results-ready ~2.4s, full-stream p95 6.94s (10 VU) | 5af38c1 |
| NFR-02 (50 users, <1% err) | `tests/benchmark/k6_search.js` + `docs/testing/performance-report.md §10` | ✅ k6 live run 2026-07-16: 652 iters, 0.00% errors, full-stream p95 7.70s (50 VU) | 5af38c1 |
| NFR-03 (AI Gateway) | `.github/workflows/ci.yml` REM-8 grep | CI-enforced on every push (grep exits 1 on direct URLs) | 78950e5 |
| NFR-04 (ephemeral) | Architecture: Pyodide = no disk | Verified by constraint — disk writes architecturally impossible | N/A |
| NFR-05 (GDPR Art. 5) | `backend/app/core/middleware.py` GDPRConsentMiddleware | 451 on missing header; audit log metadata-only | 78950e5 |
| NFR-06 (WCAG 2.1 AA) | `tests/e2e/` Playwright a11y | **[EVIDENCE NEEDED: axe-core run on deployed Pages URL]** | — |
| NFR-07 (≥70% coverage) | `pytest --cov=app` CI report | **83% total** (exceeds 70% target) | 0804e79 |
| NFR-08 (CI gates) | `.github/workflows/ci.yml` | All jobs passing: ruff, mypy, pytest, Vitest, Playwright | 78950e5 |
| NFR-09 (CDN ≤3s) | Datadog RUM Core Web Vitals | **[EVIDENCE NEEDED: Datadog dashboard screenshot post-deploy]** | — |
| NFR-10 (Matrix E2EE) | Manual verification | **[EVIDENCE NEEDED: Sprint 3 Matrix integration test]** | — |

## SRS Version Control Convention

SRS releases use annotated git tags with format: `v{MAJOR}.{MINOR}-srs`

```bash
git tag -a v1.0-srs -m "SRS v1.0 — initial scaffold"
git tag -a v1.2-srs -m "SRS v1.2 — backend slice reviewed (NFR evidence, FR implementation notes, Pyodide constraints)"
git tag -a v1.3-srs -m "SRS v1.3 — backend slice expanded (FR-05/06/10/11/12/14 impl notes, Section 6 expanded, api-contract shapes corrected to match backend)"
git push origin --tags
```

Current: `v2.0-srs` (2026-07-17, IEEE 29148 restructure)
Next: post-capstone (no further SRS releases planned for the capstone submission)

## Pyodide Constraint Catalog

These constraints affect NFRs and are documented in `docs/requirements.md §6` as architectural constraints, NOT defects.

| Constraint | NFRs affected | Workaround in use |
|-----------|--------------|------------------|
| No `threading` | NFR-02 (concurrency model) | asyncio event loop; horizontal isolate scaling |
| No `socket` / `ssl` | NFR-01 (observability), NFR-03 | `httpx` (Pyodide-safe) for all network I/O |
| No `subprocess` | NFR-02 | N/A — no subprocess needed |
| No disk I/O | NFR-04 (compliance benefit) | In-memory only; D1 for structured data |
| Cold start 2–5s | NFR-01 (excluded from p95) | DemoWarmupMiddleware; pre-demo warm-up protocol |
| Limited stdlib | NFR-08 (deploy complexity) | `worker.py` sys.modules injection |
| No `sentry-sdk` | NFR-01 (observability) | Custom Sentry envelope forwarder (`integrations/sentry.py`) |
| No `ddtrace` | NFR-01 (observability) | Custom Datadog metrics forwarder (`integrations/datadog.py`) |
| No `lmnr` | NFR-01 (observability) | Custom OTLP/HTTP/json forwarder (`integrations/laminar.py`) — follows sentry.py/datadog.py pattern; grpcio/opentelemetry-sdk/opentelemetry-instrumentation-threading/blake3 all non-functional in Pyodide |
| No `langfuse` | NFR-01 (observability) | Custom Basic Auth OTLP dispatch (`integrations/langfuse.py`) — shares otlp_builder.py with laminar.py; opentelemetry-sdk thread pool non-functional in Pyodide |

## AI Model Routing (Not Diamond)

### Architecture

Translation and RAG queries pass through a Not Diamond routing layer (`app/integrations/routing/not_diamond.py`) before reaching the CF AI Gateway. The router selects the best model per task based on metadata signals only — **never document content** (GDPR).

```
User → CF Worker → NotDiamondRouter.route(task_type, metadata)
                → Not Diamond API (POST /v2/modelRouter/modelSelect)
                → selected model → CF AI Gateway → model inference
```

### Models and Roles

| Model | Task | Role | Avg Quality | Origin |
|-------|------|------|-------------|--------|
| Mistral Large | Translation | Frontier (complex legal/bureaucratic) | 0.811 | France 🇫🇷 |
| Apertus 8B | RAG + Translation | Sovereign (Swiss, Apache 2.0) | 0.611 | Switzerland 🇨🇭 |
| m2m100-1.2b | Translation | Cheap baseline (free on CF Workers AI) | 0.542 | Open-source |

### Custom Router

A custom Not Diamond router (`preference_id` in `NOT_DIAMOND_PREFERENCE_ID`) was trained on EvidenceEU's 30 translation test cases (`docs/testing/not_diamond_training_data.csv`). Training script: `backend/scripts/train_not_diamond_router.py`.

### Feature Flag

`NOT_DIAMOND_ENABLED` (default `false`). When `false`, the router is a no-op — returns `NOT_DIAMOND_DEFAULT_MODEL` immediately, no HTTP call. When `true`, routes via the Not Diamond API with an 800ms timeout. Any failure falls back to the default model silently.

### GDPR Guard

Three layers of defense:
1. Application-level: `_enforce_no_content()` rejects forbidden metadata keys (`content`, `text`, `document`, etc.) and strings >5000 chars
2. Only a synthesized ≤300-char task description is sent to Not Diamond
3. `hash_content=True` at the Not Diamond API layer

### Config Keys

All defined in `app/core/config.py`:
- `NOT_DIAMOND_ENABLED` — feature flag (bool, default `false`)
- `NOT_DIAMOND_API_KEY` — Bearer token (empty = no-op)
- `NOT_DIAMOND_PREFERENCE_ID` — custom router ID (empty = use pre-trained)
- `NOT_DIAMOND_DEFAULT_MODEL` — fallback model (default `@cf/meta/m2m100-1.2b`)
- `NOT_DIAMOND_TIMEOUT_MS` — API timeout (default 800ms)
- `NOT_DIAMOND_BASE_URL` — API endpoint (default `https://api.notdiamond.ai/v2`)

### Post-Capstone Plan

See [ADR-015](docs/adr/ADR-015-translation-model-replacement-strategy.md): replace m2m100 (CC-BY-NC) with Apertus 8B (Apache 2.0) as the cheap translation tier. Apertus already outperforms m2m100 (0.611 vs 0.542) on real translation quality data.

---

## Demo Pipeline (Sprint 2)

### Pipeline Path & Expected Latencies

```
POST /api/v1/documents/  (upload + OCR)       → 2-8s (warm/cold)
POST /api/v1/translate/  (m2m100 EN→DE)       → 2-8s (warm/cold)
GET  /api/v1/search/     (SSE streaming RAG)   → 1-6s first event
```

**Full contract:** `docs/demo/api-contracts.md` (single source of truth)

### Cold-Start Mitigation Strategy

1. **DemoWarmupMiddleware** (`app/core/middleware.py`):
   - Activated by `DEMO_MODE=true` env var.
   - Detects first request after cold start, adds `X-Cold-Start: true` header.
   - Logs cold-start latency separately (visible in Datadog without polluting p95).
   - No-op when `DEMO_MODE=false` (default).

2. **Pre-demo warm-up protocol:**
   - Hit `GET /api/v1/health/` 30s before presenting.
   - Confirm pipeline status via `GET /api/v1/health/pipeline`.
   - All components should report "healthy" before starting.

3. **CI smoke test** already warms the proxy Worker post-deploy (`scripts/smoke.sh`).

### Demo Fallback Protocol

If the live API fails mid-demo:
1. **Pre-recorded screen capture:** stored in `docs/demo/recordings/` (placeholder).
2. **Static JSON fixture:** `frontend/public/demo-fallback.json` — frontend renders without API.
3. **Translation quality validation** of recorded output against expected quality.

### Demo-Safe Limits

| Setting | Default | Effect |
|---------|---------|--------|
| `DEMO_MODE` | `false` | Activates middleware + truncation |
| `DEMO_MAX_CHARS` | `2000` | Max chars/page sent to m2m100 (prevents timeout) |

---

## Context Shards (per-subdirectory instructions)

| Directory | File | When to read |
|-----------|------|-------------|
| `backend/` | `backend/AGENTS.md` | Writing Python/Pyodide code, adding endpoints, modifying services |
| `frontend/` | `frontend/AGENTS.md` | Writing React/Next.js/Tailwind code, Storybook stories |

---

## Reference Docs (read on demand)

| Doc | When to read |
|-----|-------------|
| `use-case.md` | Product decisions, feature scope |
| `docs/branding-manifesto.md` | **Platform visual identity (v1.0)** — single source of truth for brand, colors, typography, component rules. Read first for any UI work. |
| `docs/design-and-testing.md` | Testing strategy, architecture details |
| `docs/requirements.md` | SRS spec |
| `docs/adr/` | Architecture decision records (21 total) |
| `docs/testing/` | Test cases, benchmark results |
| `assets/` | OverViz architecture + tech stack diagrams (PNG) |

---

## NFR Evidence Map (QA Harness)

> Added 2026-06-24

| NFR ID | Requirement | Test File(s) | Status | Evidence Location |
|--------|-------------|-------------|--------|-------------------|
| NFR-01 | p95 RAG latency ≤ 5s (user-perceived results-ready ~2-3s) | `tests/benchmark/k6_search.js` | ✅ Done | `docs/testing/performance-report.md §10` |
| NFR-02 | Error rate < 1% under 50 users | `tests/benchmark/k6_search.js` | ✅ Done | `docs/testing/performance-report.md §10` |
| NFR-11 | Capstone MVP envelope: 15 fixtures, 0 failures, p95 ≤15s | `tests/benchmark/k6_search.js` | ✅ Done | `docs/adr/ADR-017-capstone-mvp-operating-envelope.md` |
| NFR-06 | WCAG 2.1 AA compliance | `backend/tests/e2e/test_accessibility.py` | In Progress | `docs/testing/accessibility-report.md` |
| NFR-T1 | Translation latency < 2s | TBD | Not Started | — |
| NFR-T2 | Terminology consistency | `backend/tests/unit/test_translation_accuracy.py` | Done | Mocked; awaiting real API integration |

---

## UI Revamp Context (Issue #30)

> Added 2026-07-14 — applies to all frontend work on the UI revamp (Issue #30).
> Frontend-specific conventions in `frontend/AGENTS.md` still apply; this section
> adds the revamp-specific rules (Stitch, Astro conversion, design tokens, banned strings).

### Stitch Project

- Project ID: `16375579204261083556` (do NOT use the archived `14853395309297419919`)
- 105 screens total (desktop + mobile)
- `build_site` returns Astro-flavored HTML — always convert to Next.js before writing components

### Astro-to-Next.js Conversion (apply before every component)

- Remove frontmatter (`---` blocks)
- Convert `<slot />` → `{children}`
- Strip Astro-specific imports
- Convert Astro routing → Next.js App Router conventions

### Non-Negotiable Rules (all sessions)

- All props: `Readonly<T>` or `ReadonlyArray<T>`
- All logic: in `frontend/src/hooks/use*.ts` files only
- Tailwind: theme-mapped CSS variables only — zero hardcoded hex in component files
- Barrel `index.ts` in every new component folder
- Icons: `lucide-react` named imports only, color via `currentColor`
- Zero emojis anywhere (including `\u{1F}` unicode escapes)

### Banned Copy Strings (zero tolerance)

`Connecting to backend` | `Connecting…` | `Demo mode` | `backend offline` |
`Connection lost` | `mock login` | `Sprint 3` | `truncated for demo` |
`github.com` | `Inspect, audit` | `MIT licensed` | `prototype`

### Canonical Design Tokens

Verified against GOV.UK Design System ([source](https://design-system.service.gov.uk/styles/colour/)).

| Token | Hex | Role |
|-------|-----|------|
| Primary | `#005796` | EvidenceEU's own blue (between EU #004494 and GOV.UK #1d70b8 — not a copy of either) |
| Primary-container | `#1B5E9E` | Darker EU blue shade (passes WCAG AA with light text, distinct from GOV.UK) |
| Error | `#DA2130` | EU ECL error red |
| Warning | `#8B4A0B` | EU ECL warning orange darkened for WCAG AA text contrast (passes both as text and as bg with white text) |
| Success | `#467A39` | EU ECL success green |
| Focus ring | `#FFD617` | EU ECL yellow (not GOV.UK #FFDD00) |

All tokens defined in `frontend/src/styles/tokens.css`.

### Google Fonts

Fonts are installed **locally** — `@font-face` declarations exist in CSS.

- **NEVER** add `@import url('fonts.googleapis.com/...')` — deliberately removed
- **NEVER** import from any external font CDN

### 4 States (every page component)

| State | Render |
|-------|--------|
| Loading | Skeleton (no spinner under 1s) |
| Success | Full content |
| Error | User-friendly message + clear next action (no raw API errors) |
| Empty | Helpful CTA |

### Per-Session Deliverables

After every screen block:

1. Run `node scripts/validate.js && make lint`
2. Fix every violation before proceeding — show both outputs in full
3. Write one Storybook story per organism (all 4 states)
4. Write one Vitest test file per component (all 4 states)
