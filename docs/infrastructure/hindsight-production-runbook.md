# Hindsight (RAG) Production Runbook

Status: **production wiring complete.** The RAG pipeline
(`backend/app/services/rag_service.py`) is implemented and the deployed API
Worker points `HINDSIGHT_API_URL` at the local Hindsight instance exposed via
Cloudflare Tunnel (`backend/wrangler.toml`), so live `GET /api/v1/search/`
returns grounded RAG results. This runbook documents the **as-built**
production host.

**Hosting decision (as-built):** Hindsight runs **self-hosted on local Docker
via [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)** —
see the 2026-07-21 amendment in [ADR-016](../adr/ADR-016-hindsight-hosting-strategy.md).
The deployment (`deploy/local/docker-compose.yml`) runs the
`ghcr.io/vectorize-io/hindsight:latest` image with persistent local storage
at `~/.hindsight-data`. Cloudflare Tunnel exposes stable HTTPS endpoints
(`hindsight.evidenceeu.eu.mihai.codes`) reachable from the deployed Worker.
Hindsight **cannot** run inside Cloudflare Workers (Pyodide) — it is a ~9 GB
stateful image (torch, embedded Postgres, disk, threading), the same constraint
class as `sentry-sdk`/BabelDOC.

---

## Symptom → Cause → Fix

| Symptom | Cause | Fix |
|---------|-------|-----|
| Live `/api/v1/search/` returns no sources / empty answer | Worker `HINDSIGHT_API_URL` not pointing at tunnel URL, or tunnel not running | Verify `HINDSIGHT_API_URL` in `wrangler.toml` points to tunnel hostname; run `cloudflared tunnel run evidenceeu` |
| `httpx.ConnectError` / timeout in Worker logs on search | Cloudflare Tunnel not running or DNS not routed | Run `cloudflared tunnel run evidenceeu`; check DNS with `cloudflared tunnel route dns evidenceeu hindsight.evidenceeu.eu.mihai.codes` |
| Search works locally but not in prod | Tunnel URL mismatch between `wrangler.toml` and actual tunnel config | Verify both use the same hostname |

---

## How the URL is resolved (call chain)

1. `HindsightRAGService.__init__` reads `settings.HINDSIGHT_API_URL`
   (`backend/app/services/rag_service.py`).
2. `settings.HINDSIGHT_API_URL` default is `http://localhost:8600`
   (`backend/app/core/config.py:50`).
3. In production the value comes from the Worker environment. `worker.py`
   copies `HINDSIGHT_API_URL` from the Worker env into `os.environ`
   (`_ENV_BINDINGS`, `backend/app/worker.py:54`) so pydantic-settings can read it.
4. The Worker env value is currently set by **`backend/wrangler.toml` `[vars]`
   line 14** → `HINDSIGHT_API_URL = "http://localhost:8600"`. This is the value
   that actually ships to production and must change.

Related settings (same resolution path):

- `HINDSIGHT_BANK_ID` — namespace, default `evidence-eu-docs`.
- `HINDSIGHT_ACCESS_KEY` — optional bearer token; if the hosted instance is
  protected, set it as a **Worker secret** (not a plain var).
- `VECTOR_DB_PROVIDER` — `chromadb` (default, Sprint 1 = Hindsight path) vs
  `cloudflare` (routes to a separate Vectorize service, not wired here).

---

## Fix procedure

> ⚠️ `wrangler.toml` is an **ASK-FIRST** file per `AGENTS.md`. Get sign-off
> before editing it. The commands below assume that approval.

### 1. Provision a reachable Hindsight instance

**As-built (capstone prod): local Docker + Cloudflare Tunnel** —
`deploy/local/docker-compose.yml` runs `ghcr.io/vectorize-io/hindsight:latest`
with persistent storage at `~/.hindsight-data`. Cloudflare Tunnel config at
`~/.cloudflared/config-evidenceeu.yml` exposes `hindsight.evidenceeu.eu.mihai.codes`.
The corpus is seeded once via `scripts/seed-hindsight-if-needed.sh` (EUR-Lex,
9 chunks) and persists across restarts.

> **Secret hygiene:** the Mistral API key is in `deploy/local/.env` (not
> committed). The `HINDSIGHT_ACCESS_KEY` (backend Worker secret) is the
> bearer token the Cloudflare Worker sends to the local instance.

**Documented fallback (post-capstone / EU data residency): Hindsight Cloud
(managed SaaS).** Sign up at `ui.hindsight.vectorize.io/signup`, copy the API
base URL + API key (Account → API Keys); free starting credits cover a small
corpus. Alternative hosts if EU residency or high Retain volume rules out Cloud
(see ADR-016): full image + persistent volume on Fly.io (Frankfurt) / Render / a
VPS, or Cloudflare Containers **with an external EU Postgres**. Any host must
expose the `/v1/recall` and `/v1/memories`
endpoints the client calls (see `_HindsightHttpClient` in `rag_service.py`).

Confirm it answers:

```bash
curl -sS https://<your-hindsight-host>/v1/recall \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <HINDSIGHT_ACCESS_KEY>" \
  -d '{"bank_id":"evidence-eu-docs","query":"test","budget":"high","include_chunks":true,"max_tokens":128}'
```

Expect HTTP 200 with a JSON body containing a `results` array.

EvidenceEU defaults recall to Hindsight's documented `mid` search depth and a
4096-token response limit. Override `HINDSIGHT_RECALL_BUDGET` (`low`, `mid`, or
`high`) and `HINDSIGHT_RECALL_MAX_TOKENS` only as a measured quality/latency
tradeoff; the public EvidenceEU search contract does not change.

### 2. Point the API Worker at it

Edit `backend/wrangler.toml` `[vars]` (after approval):

```toml
# was: HINDSIGHT_API_URL = "http://localhost:8600"
HINDSIGHT_API_URL = "https://<your-hindsight-host>"
```

The access key is stored as a **secret**, never a var. It is already wired end
to end (ADR-016):

- GitHub repo secret `HINDSIGHT_ACCESS_KEY` — set (2026-07-12).
- CI pushes it on deploy — `.github/workflows/ci.yml` "Push secrets to backend
  Worker" (`wrangler secret put HINDSIGHT_ACCESS_KEY --name evidence-eu-api`).
- Bound into `os.environ` — `_ENV_BINDINGS` in `backend/app/worker.py`.
- Read by settings — `HINDSIGHT_ACCESS_KEY` field in `backend/app/core/config.py`
  (empty = no auth header; consumed in `rag_service.py`).

The Worker URL (`HINDSIGHT_API_URL`) points to the Cloudflare Tunnel hostname:
`https://hindsight.evidenceeu.eu.mihai.codes`. The local Docker instance runs
on `127.0.0.1:8600` (mapped to container port 8888).

### 3. Seed the corpus (for the demo)

The master brief (§1.4) requires a guaranteed search result on the live deploy.
Ingest at least one reference document so a query like `GDPR Germany` returns
≥1 result. Ingestion goes through `HindsightRAGService.ingest_document()`
(sanitize → chunk → `aretain`) into bank `evidence-eu-docs`.

### 4. Deploy and verify

```bash
cd backend && uv run --group workers pywrangler deploy

# Verify (include the GDPR consent header — middleware returns 451 without it):
curl -sS "https://evidence-eu-api.mc146.workers.dev/api/v1/search/?q=GDPR%20Germany&gdpr_consent=demo"
```

Expect `event: result` frames with real source excerpts followed by
`event: done`, instead of an empty result set.

---

## Cost

| Item | Cost |
|------|------|
| Cloudflare Tunnel | $0 (free forever) |
| Hindsight Docker on local machine | $0 (electricity only) |
| Mistral API (LLM for Hindsight) | Already paying |
| **Total new spend** | **$0** |

Long-run: if real PII documents arrive, migrate to Azure DB for PostgreSQL
(Italy North) for GDPR-compliant persistent storage — see ADR-016 §Amendment
(2026-07-20).

## GDPR

- Vectorize is **US-headquartered** → CLOUD Act / Schrems II exposure for EU
  personal data, despite SOC 2 Type II + encryption at rest/in transit.
- **Capstone:** acceptable — corpus is synthetic public EU regulation text (no
  PII); query text is never logged (only a truncated SHA-256 `q_hash`).
- **Production with real user documents (PII):** requires EU data residency →
  Enterprise **BYOC / on-prem** tier or EU self-host. Same Hindsight API, so it
  is a config swap, not a rewrite (ADR-016). Raise with Chris Latimer alongside
  the startup-program request (ADR-007).

## Notes

- **No-op / graceful degradation:** if Hindsight is unreachable, the pipeline
  should degrade without 500s. Answer generation (Apertus) is already a no-op
  when `HF_API_TOKEN` is empty — search returns chunks only.
- **Do not** switch `VECTOR_DB_PROVIDER` to `cloudflare` as a shortcut — the
  Vectorize path is intentionally not implemented in `rag_service.py`.
- **GDPR:** raw query text is never logged; only a truncated SHA-256 hash
  (`q_hash`) is emitted for correlation (`rag_service.py` `query()`).
