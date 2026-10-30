# ADR-023: Linus Integration Evaluation & Strategy

**Date:** 2026-07-21

**Status:** Accepted

**Extends:** ADR-022 (KnowledgeBase integration), ADR-007 (memory RAG)

---

## Context

ADR-022 introduced Linus's DEC-0059 (grounding gate), DEC-0060 (loud healthz), and DEC-0061 (network policy) as documented-but-deferred patterns. This ADR re-evaluates the **entire Linus codebase** — ARCHITECTURE.md, VISION.md, DECISIONS.md, SAFETY.md, CLAUDE.md, ROADMAP.md, and all ADRs — against EvidenceEU's Cloudflare edge infrastructure, identifies every applicable pattern, classifies each as adapted/simplified/deferred/incompatible, and implements the highest-value patterns immediately.

### Linus repo structure

Linus (github.com/dbrowneup/Linus) is a macOS-native AI research assistant using Ollama local models and Apple Silicon Metal acceleration. Its architecture is fundamentally different from EvidenceEU's serverless edge deployment. Every pattern evaluation must account for this infrastructure mismatch.

### EvidenceEU constraints that filter all evaluations

1. **Cloudflare Python Workers (Pyodide/WASM)** — no threading, no socket/ssl, no subprocess, no disk I/O, no C extensions
2. **cpu_ms=30000** — hard 30s CPU limit per invocation
3. **D1 (SQLite-at-edge, ~60ms reads)** — no Postgres, no ORM with connection pooling
4. **KV, Vectorize, AI Gateway** — available as Worker bindings
5. **FastAPI running via ASGI bridge** — WSGI frameworks incompatible
6. **GDPR Art. 5 compliance** — no document content in logs, metrics, or third-party APIs
7. **NFR-01 p95 <5s** — no slow sync operations on user-request path

---

## Ultra-Think: Component Classification

### Section A: Infrastructure Mismatch — What Cannot Run

| Linus Component | Why Incompatible | Classification |
|-----------------|-----------------|----------------|
| Ollama local models | macOS-only, Metal GPU | ❌ Incompatible (M-series host bound) |
| Local filesystem corpus `~/linus/` | No disk I/O in Pyodide | ❌ Incompatible |
| Claude Desktop MCP integration | macOS-only IPC (stdio over local) | ❌ Incompatible |
| `rich`-formatted terminal UI | CF Workers have no TTY | ❌ Incompatible |
| Watchdog filesystem watcher | No subprocess/no inotify | ❌ Incompatible |
| LM Studio / Ollama model download | No subprocess, no disk | ❌ Incompatible |
| Python `venv` module isolation | Single-process FastAPI — no venv isolation per-invocation | ❌ Incompatible (not needed) |
| Pandoc document conversion | No subprocess | ❌ Incompatible |

### Section B: Kernel Patterns — What Transfers

These are the architectural kernels (not code) that transfer to EvidenceEU:

| Linus Kernel | EvidenceEU Adaptation | Classification |
|--------------|----------------------|----------------|
| **DEC-0059: Grounding gate at output surface** | `enforce_citation_grounding()` in `chat_guidance.py` — claim-level citation validation against known sources + soft refusal with guidance fallback | ✅ Adapted (soft refusal, not hard error) |
| **DEC-0060: Loud healthz** | `effective_state` + `degradations[]` in `/health` + `/health/pipeline` responses — structured degradation report at every health surface | ✅ Adapted |
| **DEC-0061: Per-tool network policy** | `@network_policy()` decorator + egress field in AuditLogMiddleware | ✅ Adapted |
| **Five-layer memory pillar (DEC-0028)** | D1=session+episodic, KV=intra-step, Vectorize=semantic — same architecture, different stores | ✅ Adapted (evidence already in ADR-022) |
| **FastMCP tool registry (DEC-0045)** | Cannot run in Pyodide. Docker/local FastAPI MCP server via `FastMCP.from_fastapi()` | ⚠️ Docker-only |
| **Safety bypass protocol** | EvidenceEU has no need — no file system or dangerous system access | ❌ N/A |
| **Persona system (CLAUDE.md)** | EvidenceEU uses per-component prompting in `chat_guidance.py` + `rag_service.py` | ⚠️ Conceptual alignment only |
| **HyDE retrieval (query expansion)** | Already in `chat.py` via `build_contextual_retrieval_query()` at `app/api/v1/endpoints/chat.py:103` | ❌ Already done |
| **Per-tool egress audit** | Extends AuditLogMiddleware with egress URL hashes | ✅ Adapted |
| **Workflow failure visualization** | No equivalent in capstone scope | ❌ Deferred |

### Section C: Memory Pillar — Detailed Mapping

| Linus Memory Layer | Store | Linus Implementation | EvidenceEU Equivalent | Classification |
|--------------------|-------|---------------------|----------------------|----------------|
| Intra-step | Python dict | `linus.context` | `conversation_history` param in SSE generators | ✅ Aligned |
| Session | KV/JSON | Session-scoped key-value | Not implemented (stateless by design) | ⚠️ New: D1 `chat_sessions` table |
| Episodic | SQLite (JSON) | Conversation summaries | D1 `journey_state` via `JourneyState` model (ephemeral, browser-held) | ⚠️ New: D1 `session_messages` table |
| Investigation | SQLite (JSON) | Long-running research traces | Not implemented | ⚠️ New: D1 `user_investigations` table |
| Semantic | Vector DB | Chroma/embeddings | Vectorize via HindsightRAGService | ✅ Aligned |

### Section D: Grounding Gate — Full DEC-0059 Evaluation

| DEC-0059 Feature | EvidenceEU Implementation | Classification |
|------------------|--------------------------|----------------|
| Citation enforcement per claim | `enforce_citation_grounding()` in `chat_guidance.py` — splits output into claims, validates each against D1 `documents` table | ✅ Adapted (simplified) |
| `KBEntityLookup` backed by knowledge graph | Uses D1 `entities` + `document_entities` tables (NER from ADR-022) | ✅ Adapted |
| Cross-run confidence calibration | No tracking across runs — stateless by design | ❌ Deferred |
| `check_grounding(claim, papers, entities, prior_runs)` surface | `enforce_citation_grounding(claim_text, doc_ids, entity_mentions)` — no `prior_runs` param | ✅ Adapted (simplified) |
| Hard refusal (`error`-severity) for ungrounded claims | Soft refusal — returns guidance fallback instead of error response | ⚠️ Simplified (product decision) |

### Section E: FastMCP Strategy

**Verdict: Docker/local only. Never in Cloudflare Worker.**

FastMCP's `from_fastapi()` requires running an MCP server (SSE transport or stdio) — this is fundamentally incompatible with Pyodide's single-request execution model. Even if the HTTP transport worked, the Python runtime in Pyodide doesn't support the persistent process required for MCP tool discovery.

Strategy:
- Docker Compose gets a new `mcp-server` service using `FastMCP.from_fastapi(app)`
- EvidenceEU's existing FastAPI app is exposed via FastMCP's SSE transport
- MCP tools: `search_documents`, `translate_document`, `get_document`, `list_clusters`
- GDPR consent enforced via FastMCP `Depends()` injection (same pattern as `GDPRConsentMiddleware`)
- Documented as opt-in (`docker compose --profile mcp up`)
- Frontend does NOT use MCP — only external AI tools (Claude, Cursor, etc.)

### Section F: Safety Posture Comparison

| Domain | Linus | EvidenceEU | Assessment |
|--------|-------|-----------|------------|
| LLM prompt injection | System prompt hardening (CLAUDE.md) | `build_rag_prompt()` wraps chunks in structural delimiters; `detect_placeholders()` post-generation check | EvidenceEU is stronger (structural defense + post-hoc detection) |
| File system access | `bypass_confirmation_for` with user approval | No file system access at all | EvidenceEU inherently safer (no disk in Pyodide) |
| Tool execution | Bypassable function calling | No dangerous tools exposed | Comparable |
| GDPR compliance | Not addressed (local-only) | `GDPRConsentMiddleware`, `redact_query_string()`, PII-free logs | EvidenceEU stronger by requirement |
| Citation grounding | Trust-but-verify approach | `enforce_citation_grounding()` + `build_empty_result_guidance()` fallback | Both implement grounding; different mechanisms |

### Section G: DRY Audit (Linus-specific)

| Pattern in Linus | Pattern in EvidenceEU | Duplicate? | Action |
|------------------|----------------------|------------|--------|
| `rigor.py` → `check_grounding()` | `chat_guidance.py` → `enforce_citation_grounding()` | ⚠️ Same concept, different implementation | No code copied — both independently implement citation validation |
| `healthz.py` → `effective_state` + `degradations[]` | `health.py` → `PipelineStatus` + `ComponentStatus` | ⚠️ Same concept, different shape | This ADR updates health.py to match the loud-healthz pattern |
| `network_policy.py` → per-tool egress decorator | `middleware.py` → `AuditLogMiddleware` | ⚠️ Same concept, different mechanism | This ADR adds `@network_policy()` decorator |
| `memory.py` → five-layer pillar | D1 + Vectorize + KV | ✅ Same architecture, different stores | Architectural alignment only |
| `fastmcp_server.py` → MCP | No equivalent | ⚠️ New addition (Docker only) | No code copied — fresh implementation |

**No Linus source file is copied into EvidenceEU.** Every adaptation follows Linus's architectural pattern but uses EvidenceEU's dependencies (D1, httpx, CF Workers AI, Pyodide-safe primitives).

### Section H: Incompatible-by-Environment (Transferred-to-ADR-022 Treatment)

These were evaluated during the KB/Linus review in ADR-022 but the Linus-specific rationale is documented here:

| ADR-022 Item | Linus Source | Why Deferred/Simplified |
|-------------|-------------|------------------------|
| Full DEC-0059 grounding gate (hard refusal) | `rigor.py` | Product decision: soft refusal is safer for capstone users (the migrant persona) |
| DEC-0060 loud healthz (was "Documented only") | `healthz.py` | Now implemented — this ADR upgrades from "documented only" to "adapted" |
| DEC-0061 network policy (was "Documented only") | `network_policy.py` | Now implemented — this ADR upgrades from "documented only" to "adapted" |

---

## Decision

### 1. Implement Grounding Gate (immediate)

Add `enforce_citation_grounding()` to `chat_guidance.py` and integrate into `chat.py` system prompt:

```python
def enforce_citation_grounding(
    claim_text: str,
    known_doc_ids: set[str],
    entity_mentions: set[str],
) -> GroundingVerdict:
```

- Splits input into claim sentences
- Checks each against known document IDs and entity mentions
- Returns `GroundedClaim` per sentence + overall `pass/fail` verdict
- On fail: emits `guidance` SSE event (soft refusal), not an error
- Integrated as filter step in the SSE generator before answer streaming

### 2. Implement Cross-Session Memory (immediate)

Three new D1 tables:
- `chat_sessions` — session metadata (start time, language, journey_type)
- `session_messages` — individual messages with role and content summary
- `user_investigations` — long-running research traces across sessions

New repository: `repositories/memory_repository.py`

Pattern follows `glossary_repo.py` exactly — D1Client-based, graceful no-op when unavailable, async, all methods return empty on error.

Feature-flagged by `SESSION_MEMORY_ENABLED` (default false).

### 3. FastMCP (Docker/local only)

New Docker Compose profile `mcp`. Uses `FastMCP.from_fastapi()` to expose existing FastAPI endpoints as MCP tools. GDPR consent enforced via `Depends()` injection.

Implementation deferred to post-ADR-023 — this ADR documents the strategy only.

### 4. Loud Healthz (immediate)

Restructure `health.py`:
- `/health` liveness: adds `effective_state` field (`live` | `degraded` | `down`)
- `/health/ready` readiness: adds `effective_state` + `degradations[]`
- `/health/pipeline` pipeline status: already matches loud pattern — no change needed

### 5. Per-Tool Network Policy (immediate)

New decorator `@network_policy(allow_egress=True, audit_egress=True)` in `app/core/network_policy.py`.

Extends `AuditLogMiddleware` to capture egress URL hashes when `audit_egress=True`.

### 6. LLM Trace Recorder (immediate, DEC-0041 partial)

New module `app/integrations/trace_recorder.py`:

- In-memory ring buffer of LLM call metadata (model, prompt hash, response hash, latency, token count, error)
- GDPR-safe: no document content stored — SHA-256 hashes only + 200-char response preview
- Feature-flagged by `ENABLE_LLM_TRACING` (default false) — zero overhead when disabled
- Async API: `record()`, `search()`, `stats()`
- Singleton via `get_recorder()`

This is a partial resolution of DEC-0041 (deterministic replay). Full threading-based checkpointing remains blocked by Pyodide.

---

## Implications

### Positive

- **Citation trust** — `enforce_citation_grounding()` prevents hallucinated claims for the "library search result" complaint
- **Cross-session continuity** — migrant users can return to a previous session and see their investigation history
- **Health observability** — `effective_state` gives operators instant degradation awareness
- **Network audit trail** — per-tool egress log satisfies GDPR Art. 30 for third-party API calls

### Negative

- Three new D1 tables add ~200 bytes/row storage for session messages
- Grounding gate adds ~5ms per claim on warm path (D1 lookup)
- Feature flags add config complexity

### Neutral

- All new code is feature-flagged off by default (SESSION_MEMORY_ENABLED, GROUNDING_GATE_ENABLED, ENABLE_LLM_TRACING)
- FastMCP profile is opt-in via `docker compose --profile mcp up`
- Grounding gate is soft refusal only — product can decide to hard-refuse later
- Trace recorder is metadata-only — no document content stored, GDPR-safe by design

---

## Dependencies

- No new Python dependencies (all new code uses existing imports: D1Client, asyncio, uuid, datetime, dataclasses, httpx)
- FastMCP requires `fastmcp` pip package (Docker/local only — NOT added to `pyproject.toml`)
- FastMCP listed in `requirements-mcp.txt` (host-only, never in Worker)

---

## Implementation Summary (2026-07-21)

### Completed

| Item | Files | Status |
|------|-------|--------|
| **Grounding gate** (`enforce_citation_grounding`) | `chat_guidance.py`, `search.py` | ✅ 19 tests, DRY refactored |
| **DRY refactoring** (`extract_known_doc_ids`, `build_grounding_verdict`) | `chat_guidance.py` | ✅ Inline set-comp in `search.py` replaced with single call |
| **Cross-session memory** (D1 0009-0011) | `memory_repository.py`, migrations | ✅ 36 tests, **100% coverage** |
| **Loud healthz** (`effective_state` + `degradations[]`) | `health.py` | ✅ Restructured for `/ready` and `/pipeline` |
| **Per-tool network policy** (`@network_policy()` decorator) | `network_policy.py`, `middleware.py` | ✅ 19 tests, **100% coverage** |
| **LLM trace recorder** (DEC-0041 partial) | `trace_recorder.py`, `config.py`, `hash_utils.py` | ✅ 22 tests, feature-flagged (`ENABLE_LLM_TRACING`, default `false`), 97% coverage |
| **E2E SSE fix** (route interception) | `pipeline.live.spec.ts` | ✅ Fixes Playwright `response.text()` on SSE stream |
| **CI** | `ci.yml`, `lint.yml` | ✅ All 4 cycles green (test assertion → lint → mypy → format) |

### Trace Recorder (DEC-0041 Partial)

Full deterministic replay (threading-based checkpointing) is blocked by Pyodide — see Section A. As a partial resolution, `backend/app/integrations/trace_recorder.py` provides:

- **In-memory ring buffer** of LLM call metadata (model, prompt hash, response hash, latency, token count, error)
- **GDPR-safe**: no document content stored — hashes only + 200-char response preview
- **Feature-flagged**: `ENABLE_LLM_TRACING` (default `false`) — zero overhead when disabled
- **Async API**: `record()`, `search()`, `stats()` — suitable for instrumentation of any gateway call
- **Coverage**: 97% (remaining uncovered line is `_percentile()` guard for empty list — never reached because `stats()` guards against it)

### Test Coverage

| Module | Tests | Coverage |
|--------|-------|----------|
| `memory_repository.py` | 36 | **100%** |
| `network_policy.py` | 19 | **100%** |
| `chat_guidance.py` | 19 | 87% (new code 100%; remaining 8 lines are pre-existing guidance logic) |
| `trace_recorder.py` | 22 | 97% (edge cases in `_percentile`) |
| **Total new tests** | **96** | |

### E2E Fix Detail

The Post-deploy live E2E test (`pipeline.live.spec.ts`) failed with `Protocol error (Network.getResponseBody): No data found for resource with given identifier`. Root cause: Playwright's `response.text()` relies on CDP `Network.getResponseBody`, which does not buffer streamed SSE bodies.

**Fix**: Replace `waitForResponse` + `response.text()` with `page.route()` interception and a 30s timeout:

```typescript
function withTimeout<T>(promise: Promise<T>, label: string, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`${label} timed out after ${ms}ms`)),
        ms,
      );
      timer.unref?.();
    }),
  ]);
}

await page.route("**/api/v1/search/**", async (route) => {
  const response = await route.fetch();
  const body = await response.text();
  searchBodyPromiseResolve(body);
  await route.fulfill({ response, body });
});

// ...
const searchBody = await withTimeout(searchBodyPromise, "SSE body", 30_000);
```

`route.fetch()` reads the full stream (including the terminal `done` event) before the browser can discard it. The body is then passed to `route.fulfill()` so the browser renders normally. The `withTimeout` wrapper prevents the test from hanging indefinitely if the SSE stream never completes (e.g., backend crash mid-stream).

### CI Cycles

| Cycle | Commit | Change |
|-------|--------|--------|
| 1 | `d16047f` | Fix test assertion for `grounding_verdict` |
| 2 | `05fa6ab` | Add comprehensive tests (memory, policy, guidance) |
| 3 | `ac4347e` + `d66371d` | Fix ruff lint/format |
| 4 | `5132b2b` | Fix mypy type-args |

### Blocked Items

- **Deterministic replay (DEC-0041)** — threading-based checkpointing blocked by Pyodide. Trace recorder provides metadata-only partial resolution.
- **FastMCP (DEC-0062)** — `FastMCP.from_fastapi()` not viable in Pyodide (requires persistent MCP server). Docker/local only; deferred to post-capstone.

---

## Future Work (post-capstone)

1. **Hard refusal gate** — upgrade `enforce_citation_grounding()` from soft refusal (`guidance` event) to hard refusal (`error` event) when confidence < threshold
2. **Cross-run confidence calibration** — track `prior_runs` in D1 `user_investigations` table for per-claim confidence over time
3. **FastMCP deployment** — MCP server as Docker sidecar, GDPR consent via Depends()
4. **Dynamic memory pruning** — stale session cleanup in D1 via TTL column
5. **Vectorize-backed semantic memory** — connect `user_investigations` summaries to Vectorize for cross-session recall

### Reference implementations
- [Linus](https://github.com/dbrowneup/Linus) — `docs/adr/0059-grounding-gate-output-surface.md`, `docs/adr/0060-loud-degradation-healthz-extension.md`, `docs/adr/0061-network-policy-framework.md`
