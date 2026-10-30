# EvidenceEU — Full E2E Integration Audit (Final)

**Date:** 2026-07-23
**Scope:** Every user journey exercised against the REAL backend pipeline (no mocks) —
unauthenticated landing + public RAG search, demo sign-in, session persistence,
authenticated RAG search, chat streaming, document upload + OCR, and adversarial checks.
**Method:** New `frontend/tests/e2e/specs/live.integration.spec.ts` (7 tests) driving the
live stack (Next.js dev + FastAPI/Pyodide backend + Hindsight RAG + Mistral OCR + CF AI
Gateway), plus curl-level SSE verification and backend log inspection.

---

## Result Summary

| # | Journey | Status | Issues found | Fix |
|---|---------|--------|--------------|-----|
| 1 | Unauth landing (no auth leak, CTA nav) | PASS | — | — |
| 2 | Public RAG search — real SSE results + streamed answer | PASS | **Search returned 0 results for every query** | `_has_query_coverage` over-filter (see BUG-1) |
| 3 | Demo sign-in → dashboard + sidebar | PASS | — | — |
| 4 | Session persists on new tab (no re-login) | PASS | — | — |
| 5 | Authenticated RAG search | PASS | (same recall path as #2) | BUG-1 |
| 6 | Chat streams grounded response w/ citations | PASS | RAG answer 404'd on removed model | BUG-2 |
| 7 | Upload → Mistral OCR → extracted text + citation | PASS | test harness only (see notes) | test fixes |

**Live suite: 7/7 PASS** (`npx playwright test --project=live --workers=1`, 1.8 min).
**Mock suite: 63/63 PASS** (unchanged — no regressions).
**Backend unit: `test_rag_service.py` 69/69, model-adapter suites 18/18.**
**CI: green** (run 30038587777 — Frontend, E2E Chromium, Deploy, Lighthouse, BrowserStack, post-deploy live E2E all ✓).

---

## Root-Cause Bugs Found & Fixed

### BUG-1 (CRITICAL) — Search returned "No results found" for every query
- **Symptom:** Browser EventSource received `results_complete` + `done` but zero `result`
  events; UI showed "No results found" on all searches (authenticated and public).
- **Investigation:** Direct Hindsight recall returned 149 results in ~3s; the backend's
  `arecall` (from inside the container) also returned 149 — yet `HindsightRAGService.query()`
  returned `[]`. Instrumented the SSE generator: `n_results=0` with no exception → results
  were being filtered out post-recall.
- **Root cause:** `rag_service._has_query_coverage()` required **≥2 exact query terms** to
  appear in **every** recalled chunk. Hindsight's hybrid recall returns topically-relevant
  but lexically-diverse chunks; for a multi-term query like "residence permit extension
  Germany" few individual chunks contain 2+ of those exact words — so the guard silently
  dropped **100%** of the semantically-correct results.
- **Fix:** require **≥1** term overlap (a true weak match is *zero* overlap, per the guard's
  own docstring intent). Single-term queries still bypass the guard (semantic ranking
  preserved). `backend/app/services/rag_service.py`.
- **Verification:** browser + curl now return 6 results per query across
  "residence permit", "data protection", "free movement".

### BUG-2 — RAG answer generation 404 on removed Cloudflare model
- **Symptom:** backend log `Workers AI streaming generation failed — status=404
  model=@cf/meta/llama-3.1-8b-instruct-fp8-fast`; chat/search answers never streamed.
- **Root cause:** the pinned fast model was deprecated/removed by Cloudflare.
- **Fix:** repointed `_MODEL_FAST` to a currently-valid model in
  `backend/app/integrations/llm/workers_ai_adapter.py`; updated unit-test literals.
- **Verification:** `answer_chunk` SSE events now stream; chat returns grounded GDPR
  answers with Article 15/17 citations.

### BUG-3 (infra) — Backend could not reach Hindsight
- **Symptom:** `ConnectError: Name or service not known` — committed compose hardcodes
  `HINDSIGHT_API_URL=http://hindsight:8888` (not present in the local stack).
- **Fix:** `docker-compose.override.yml` (gitignored, local-only) →
  `HINDSIGHT_API_URL=http://host.docker.internal:8600`. No committed config touched.

### Seed performance (explicit user request) — corpus now fully seeded
- **Before:** sequential ingest, ~40 min, killed at 12/55 docs.
- **Fix:** `scripts/seed_documents.py` refactored to a semaphore-bounded concurrent worker
  with `SEED_CONCURRENCY` + `SEED_CHUNK_CONCURRENCY`, preventing an 80-chunk document from
  bursting hundreds of simultaneous embedding requests.
- **Result:** **all 55 EUR-Lex documents seeded** (61 Hindsight items incl. DE/FR chunks).
- **Note:** concurrency ≥6 saturates a single local Hindsight (occasional 500s / recall
  ReadTimeouts). Concurrency 3–4 is the safe steady-state; run the seed when no live search
  traffic is competing.

---

## Adversarial / Edge Cases Checked

- **GDPR consent:** unauth browser search sends `gdpr_consent=demo` query param (not header)
  and is accepted; missing consent → 451 (middleware verified).
- **No raw JSON / auth leak on landing:** assertion in test #1.
- **Session persistence:** new browser tab retains auth (test #4).
- **No secrets in fixtures:** demo creds redacted; PDF fixture is synthetic.
- **SSE robustness:** verified event ordering `result → results_complete → answer_chunk →
  done`; keepalive `: ping` comments correctly ignored by EventSource.

---

## Test Harness Notes (not app bugs)

Fixing test #7 (upload) surfaced three brittle-selector / interaction issues in the *new*
live spec, all corrected:
1. Clicked the Browse button (`type="button"`, opens file chooser) instead of the form's
   `type="submit"` button → no upload POST fired.
2. Missing the required **GDPR consent checkbox** (`upload-gdpr-consent`) which gates
   `canSubmit` → submit button stayed disabled.
3. Default 30s per-test timeout < Mistral OCR round-trip → added `test.setTimeout(150_000)`.

The `live` project is **excluded from CI** (needs a real backend + seeded Hindsight);
CI runs only the mock chromium/firefox/webkit suites. Run the audit locally with:

```bash
npx playwright test --project=live --workers=1
```

---

## Reproduction

```bash
# 1. Stack
docker compose up -d backend chromadb           # + Hindsight on :8600
cd frontend && npm run dev                        # :3000

# 2. Seed (safe steady-state concurrency)
HINDSIGHT_API_URL=http://localhost:8600 \
  SEED_CONCURRENCY=3 SEED_CHUNK_CONCURRENCY=4 \
  PYTHONPATH=. .seedvenv/bin/python -m scripts.seed_documents

# 3. Live audit (serial)
cd frontend && npx playwright test --project=live --workers=1
```
