# ADR-016: Hindsight Hosting Strategy — Managed Cloud (reversible to BYOC / EU self-host)

**Date:** 2026-07-12
**Status:** Accepted (capstone prod = local Docker + Cloudflare Tunnel; see 2026-07-21 amendment below)
**Decider:** Mihai Chindriș (PO/Dev)
**Extends:** ADR-007 (Hindsight as the single RAG/memory layer), ADR-001 (RAG vector store), ADR-004 (Cloudflare infrastructure)
**Context source:** Hosting research, July 2026.

---

## Amendment (2026-07-21): capstone production host = local Docker + Cloudflare Tunnel

The Modal self-host (2026-07-18 amendment) was itself superseded during Sprint 3.
Modal costs were burning credits ($11.84 remaining), HF Spaces Docker was
no longer free ($9/mo minimum), and the capstone demo requires a reliable
always-on host. The solution: **local Docker containers exposed via
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)**.

- **$0 ongoing cost.** Docker runs on the local machine; Cloudflare Tunnel is
  free forever. Only variable cost is the Mistral API (already paying).
- **GDPR stronger than cloud.** Data never leaves the local machine (EU region).
- **Persistent storage.** Unlike Modal's ephemeral pg0, local Docker uses
  `~/.hindsight-data` for durable PostgreSQL storage — no re-seeding needed.
- **Stable HTTPS URLs.** Cloudflare Tunnel provides auto-reconnecting HTTPS
  endpoints (`hindsight.evidenceeu.eu.mihai.codes`,
  `babeldoc.evidenceeu.eu.mihai.codes`) reachable from the deployed Worker.
- **Single-vendor + DRY preserved.** `rag_service.py`'s `_HindsightHttpClient`
  still talks to one base URL + optional bearer; only the URL changed.

**Deployment:** `deploy/local/docker-compose.yml` runs both Hindsight and
BabelDOC. Config at `~/.cloudflared/config-evidenceeu.yml`. Seed script:
`scripts/seed-hindsight-if-needed.sh` (EUR-Lex corpus, 9 chunks).

Cloud (managed SaaS) remains the **documented fallback / post-capstone path** for
EU data residency (BYOC/on-prem) when real PII documents arrive — the API contract
is unchanged. Everything else in this ADR (why not CF Workers/Containers on `pg0`,
the `_HindsightHttpClient` abstraction, GDPR caveat, cost model) still holds.

---

## Amendment (2026-07-20): post-capstone production backend = Azure Database for PostgreSQL

The capstone uses local Docker with persistent storage (2026-07-21 amendment above). When EvidenceEU
onboards real user documents (cross-border migrants' PII), pg0's ephemeral disk
is no longer acceptable — persistent storage becomes a hard requirement under
GDPR Art. 5(1)(e) (storage limitation + integrity).

### Trigger to migrate

The migration from pg0 to an external PostgreSQL is triggered by **any** of:

1. Real user documents containing PII are ingested (no longer synthetic corpus)
2. Cold-start re-seeding latency becomes unacceptable (>60s at scale)
3. Corpus size grows beyond ~1M tokens (re-seeding cost exceeds external DB cost)
4. GDPR audit requires documented EU-resident data storage

### Chosen backend: Azure Database for PostgreSQL Flexible Server (Italy North)

| Criterion | Azure DB for PostgreSQL | Supabase | Neon | Hindsight Cloud |
|-----------|----------------------|----------|------|-----------------|
| **Already in stack** | ✅ Azure for Students sub active | ❌ New account/billing | ❌ New account/billing | ❌ US HQ, GDPR issue |
| **EU residency** | ✅ Italy North | ⚠️ EU (Frankfurt) | ⚠️ EU (Frankfurt) | ❌ US (CLOUD Act) |
| **pgvector support** | ✅ Allowlisted extension | ✅ Built-in | ✅ Extension | N/A (managed) |
| **Free tier** | ✅ Burstable B1ms ~$0/mo (student credits) | ✅ 500MB free | ✅ 0.5GB free | ⚠️ Credits expire |
| **GDPR compliance** | ✅ EU residency, Microsoft DPA | ✅ SOC 2, EU | ✅ SOC 2, EU | ❌ Schrems II risk |
| **Hindsight-tested** | ✅ Listed in docs | ✅ Listed in docs | ✅ Listed in docs | ✅ Native |

**Why Azure wins:** (1) subscription already exists — no new signup, (2) Italy
North matches Azure Document Intelligence's region, (3) zero incremental cost on
student credits, (4) cleanest GDPR story (EU-resident, EU processor, no CLOUD
Act exposure). Hindsight docs list Azure Database for PostgreSQL as a
tested managed service.

### Migration: one env var, zero code changes

```python
# docker-compose.yml — add one env var to the Hindsight service
HINDSIGHT_API_DATABASE_URL="postgresql://user:pass@hindsight-pg.postgres.database.azure.com:5432/hindsight"
```

When `HINDSIGHT_API_DATABASE_URL` is set, Hindsight skips embedded pg0 entirely
and connects to the external PostgreSQL. No application code change, no
`rag_service.py` change, no `_HindsightHttpClient` change. The `_HindsightHttpClient`
abstraction (base URL + bearer) remains identical — only the storage backend
behind Hindsight changes.

### Architecture after migration

```
Local Hindsight (Docker) → Azure DB for PostgreSQL (Italy North, always-on)
                                        ↑ durable, survives scale-to-zero
                                        ↑ no re-seeding needed
                                        ↑ pgvector for HNSW vector search
                                        ↑ BM25 via pg_textsearch (if needed)
```

### Azure DB for PostgreSQL setup (post-capstone)

1. Create Flexible Server in Italy North region (Portal or CLI)
2. Allow `vector` extension: `az postgres flexible-server parameter set --name azure.extensions --value "vector"`
3. Hindsight auto-creates schema on first connection
4. Seed corpus once (not per-cold-start)
5. Set `HINDSIGHT_API_DATABASE_URL` in `deploy/local/.env`
6. Redeploy: `cd deploy/local && docker compose up -d hindsight`

### Cost at production scale

- Burstable B1ms: ~$12/mo (or ~$0 on remaining student credits)
- 32 GB storage included in free tier
- Auto-backups: included
- No per-token storage fee (unlike Hindsight Cloud at $0.25/M tokens/mo)

### What changes vs. capstone

| Aspect | Capstone (pg0) | Production (Azure DB) |
|--------|---------------|----------------------|
| Storage | Persistent local Docker volume | Always-on Azure DB |
| Re-seeding | Every cold start (~30-60s) | One-time, then queryable |
| Seed script | `seed_hindsight.py` (background thread) | Run once manually, then delete |
| Data persistence | None (embraced, not fought) | Durable, GDPR-compliant |
| Cost | $0 | ~$12/mo (or $0 on student credits) |
| Cold start penalty | ~30-60s (re-seed) | ~2-5s (pg0 init skipped) |

### Why this is NOT needed for the capstone

The capstone corpus is 55 synthetic EUR-Lex documents (~500K tokens). Re-seeding
takes ~30-60s on cold start. The idempotency guard (`_bank_has_data()`) prevents
redundant work on warm restarts. The `_seed_after_ready()` background thread
ensures the server is responsive immediately. **This is sufficient for the
capstone demo.** The Azure DB migration is deferred to when real PII arrives.

Everything else in this ADR still holds. Nothing in `rag_service.py` changes.

---

## Context

ADR-007 decided **which** memory/RAG vendor EvidenceEU uses (Hindsight). It did
**not** decide **where** Hindsight runs in production. That gap is the current
blocker: the deployed API Worker points `HINDSIGHT_API_URL` at
`http://localhost:8600`, which is unreachable from the Cloudflare edge, so live
`GET /api/v1/search/` returns nothing (see the wiring issue + runbook).

Hindsight (`ghcr.io/vectorize-io/hindsight:latest`) is a stateful, ~9 GB Docker
image: PyTorch + local ML embeddings, an embedded PostgreSQL (`.pg0`) with
pgvector, disk I/O, and threading. This is the **same class of workload** that
`sentry-sdk`, `ddtrace`, `newrelic`, and BabelDOC fall into — none can run inside
Cloudflare Workers (Pyodide/WASM). See the `AGENTS.md` NEVER list and ADR-012.

So the question is narrow: **what host serves the Hindsight HTTP API that our
Pyodide backend calls over `httpx`?**

### Hosting options evaluated

| Option | What it is | Verdict |
|--------|-----------|---------|
| **Cloudflare Workers (Pyodide)** | Run Hindsight in the API Worker | ❌ Impossible — 9 GB image, torch, embedded Postgres, threading, disk. Same constraint as sentry-sdk/babeldoc. |
| **Cloudflare Containers** | CF's GA container runtime (Worker + Durable Object) | ❌ Not viable for the default `pg0` mode. The image *fits* (`standard-3/4`, 16–20 GB disk), but **CF Container disks are ephemeral** — on scale-to-zero or host restart the disk is wiped, destroying the seeded corpus. Making it durable requires an **external** Postgres (Neon/Supabase) + the slim image + an external embedding provider — i.e. it does not remove the external dependency, it relocates it and adds a re-architecture. |
| **External always-on host** (Render / Fly.io / VPS) | Run the full image with a persistent volume | 🟡 Works, matches `docker-compose` exactly. But it is the **only** self-managed, stateful, always-on box in an otherwise 100% serverless/managed stack — architecturally inconsistent (see DRY argument), and pays for 24/7 compute regardless of usage. |
| **Hindsight Cloud** (managed SaaS) | Vectorize-hosted API, pay-as-you-go on tokens | ✅ **Chosen.** Pure HTTP wiring, zero infra, scales to zero cost when idle. Fits EvidenceEU's established integration pattern exactly. |

---

## Decision

**Use Hindsight Cloud (managed SaaS) as the production host for the Hindsight
RAG API.** The integration is pure configuration — no `rag_service.py` code
change — and the hosting choice remains **reversible** (see below).

### Issue #166 capacity decision

The first remediation path for the measured 50-VU `429 Too Many Requests`
failures is a **managed-capacity increase on Hindsight Cloud**, preferably
dedicated infrastructure with an explicit concurrency commitment. The public
Cloud and billing documentation exposes no self-service concurrency control,
so this requires provider confirmation rather than another application retry.

EvidenceEU will retain the existing bounded three-attempt retry only for brief
bursts. It will not increase retry counts to mask sustained throttling: doing so
adds tail latency without creating upstream capacity.

The fallback trigger is objective: if Vectorize cannot provide a Cloud tier
that completes the documented 50-VU, 60-second production run with zero
Hindsight 429 responses and less than 1% total errors, migrate the same bank to
Enterprise BYOC or an EU-hosted persistent self-managed deployment. The public
SSE API and `_HindsightHttpClient` contract remain unchanged; only the base URL,
secret, and bank migration change.

Before comparing hosting options again, deploy the stage metrics added for
Issue #166 and use `evidence_eu.search.stage.duration` to separate
`stage:hindsight_recall` from `stage:answer_generation`. Query text, document
content, document IDs, and bank IDs are never metric tags.

### Why this is the DRY / "most native" choice

The instinct to avoid Render because it "isn't native" is correct — but the
thing to be native **to** is EvidenceEU's own architecture, not Cloudflare
specifically. EvidenceEU is already a **constellation of managed APIs called over
`httpx` from Pyodide**, every one following the identical pattern
`managed cloud API + httpx forwarder + transparent no-op when the key is absent`:

- CF AI Gateway (`app/integrations/cloudflare/gateway.py`)
- Sentry (`app/integrations/sentry.py`)
- Datadog (`app/integrations/datadog.py`)
- Laminar (`app/integrations/laminar.py`)
- Langfuse (`app/integrations/langfuse.py`)
- Not Diamond (`app/integrations/routing/not_diamond.py`)

Hindsight Cloud fits that pattern precisely. Self-hosting (Render/Fly/CF
Containers + Postgres) would be the **only** self-managed stateful component in
the entire system — the un-DRY, architecturally inconsistent option. The
"purest" integration is the managed API.

### Why the decision is low-risk: it is reversible

`rag_service.py`'s `_HindsightHttpClient` abstracts the host behind a single
base URL + optional bearer token. Because the Hindsight **API is identical**
across managed Cloud, self-hosted Docker, and Enterprise BYOC/on-prem,
migrating between them later is a **config swap, not a code change**. Vectorize
also offers assisted Cloud → self-host data migration. This is the payoff of
ADR-007's single-vendor discipline: we are not locked in.

---

## Cost analysis (Hindsight Cloud)

**There is no perpetual free tier.** Billing is pay-as-you-go with **free
starting credits** granted at signup (1 credit = $1). When the balance reaches
$0, API operations return `HTTP 402` until credits are topped up ($5–$1,000 via
Stripe). Rates effective 2026-07-06:

| Operation | Unit | Rate | Relevance to EvidenceEU |
|-----------|------|------|--------------------------|
| **Retain** (store memories) | per M **input** tokens | $10.00 | The cost driver — runs LLM extraction on ingest |
| **Recall** (retrieve) | per M **output** tokens | $0.75 | Per-query — negligible |
| **Reflect** | per call | $0.05 | Not on the core search path — negligible |
| **File Conversion (Iris)** | per M output tokens | $7.50 | **Opt-in.** Use Standard (Markitdown) extraction = no extra charge |
| **Storage** | per M tokens / month | $0.25 | First **30 days free**; memories never deleted |

### Does current usage fit the free credits? Yes — effectively $0 for the capstone.

EvidenceEU's corpus is a small **synthetic** EU-reference set. Retaining on the
order of ~500K tokens of documents ≈ ~$5 one-time; recall on demo queries is
effectively free. Using **Standard** (not Iris) extraction keeps it trivial. The
free starting credits cover the capstone with room to spare.

**Long-run cost driver = Retain volume.** At production scale, ingesting many /
large user documents accrues cost at $10/M input tokens (recall stays cheap).
This is the trigger to revisit hosting (self-host / BYOC) or negotiate volume /
startup credits — see below.

---

## GDPR caveat (the real long-run constraint)

Vectorize is **US-headquartered** (Dover, Delaware). Hindsight Cloud is SOC 2
Type II certified and encrypts data in transit and at rest, **but** a US
provider carries CLOUD Act exposure, which triggers a Schrems II analysis for
EU personal data regardless of processing region.

- **Capstone / now:** Acceptable. The corpus is synthetic public EU regulation
  text (no PII), and query text is never logged (only a truncated SHA-256
  `q_hash`, per `rag_service.py`). Low risk.
- **Production with real user documents:** EvidenceEU's actual use case is
  cross-border migrants' documents — which **contain PII**. Sending that content
  to a US-managed service for retain/extraction is a genuine data-residency
  problem. The mitigation is the **Enterprise BYOC / on-prem tier** (EU region),
  or EU self-hosting (e.g. Fly Frankfurt / CF Containers `weur` + EU Postgres).
  Same Hindsight API → no application rewrite.

Cross-reference: ADR-007 already records that Hindsight Cloud's **$15K startup
program** is deferred to post-incorporation (3-month credit clock, "incorporated
company" eligibility), with a **direct student accommodation request to Chris
Latimer (Vectorize)** as the interim path. The BYOC/EU-residency conversation
belongs in that same outreach.

---

## Consequences

### Positive
- **$0 for the capstone** (free starting credits cover a small synthetic corpus).
- **Pure wiring** — zero `rag_service.py` change; only `HINDSIGHT_API_URL` +
  a `HINDSIGHT_ACCESS_KEY` secret.
- **DRY / architecturally consistent** — identical to every other managed-API
  integration; no self-managed stateful infra introduced.
- **Scales to zero cost** when idle (no 24/7 VM bill).
- **Managed reliability** — 99.9% uptime SLA, daily backups, usage analytics.
- **Reversible** — Cloud → self-host → BYOC is a config swap, not a rewrite.

### Negative / risks
- **No perpetual free tier** — beyond free credits it is pay-as-you-go; Retain
  volume is the cost driver at scale.
- **GDPR data residency** — US provider; acceptable for synthetic-corpus capstone,
  requires BYOC/EU-residency before onboarding real PII documents.
- **External dependency** — a Cloud outage degrades search. Mitigated: the
  pipeline already degrades gracefully (no 500s) when Hindsight is unreachable
  (`rag_service.py` — returns chunks-only / empty rather than erroring).

### Neutral
- Secret handling: `HINDSIGHT_ACCESS_KEY` is a **Cloudflare Worker secret**
  (`wrangler secret put`), never a `wrangler.toml` var or a tracked file, and
  must be added to `_ENV_BINDINGS` in `worker.py`.

---

## What we explicitly do NOT do

- ❌ Run Hindsight in Cloudflare Workers (Pyodide) — architecturally impossible.
- ❌ Run Hindsight in Cloudflare Containers on `pg0` mode — ephemeral disk wipes
  the corpus on restart.
- ❌ Switch `VECTOR_DB_PROVIDER` to `cloudflare` as a shortcut — the Vectorize
  path is intentionally not implemented in `rag_service.py` (see ADR-001/ADR-007).
- ❌ Store the access key anywhere except a Worker secret.

---

## Implementation (config only — see runbook for full steps)

1. Sign up at `ui.hindsight.vectorize.io/signup` → obtain API base URL +
   `HINDSIGHT_ACCESS_KEY`.
2. `backend/wrangler.toml` `[vars]` → `HINDSIGHT_API_URL` = Cloud endpoint.
   **⚠️ ASK-FIRST file per `AGENTS.md`.**
3. `cd backend && uv run --group workers pywrangler secret put HINDSIGHT_ACCESS_KEY`.
4. Add `"HINDSIGHT_ACCESS_KEY"` to `_ENV_BINDINGS` in `backend/app/worker.py`.
5. Seed the corpus (Standard extraction) into bank `evidence-eu-docs`.
6. Deploy + verify a live `GDPR Germany` query returns ≥1 real source.

Full procedure: `docs/infrastructure/hindsight-production-runbook.md`.

---

## References

- `docs/infrastructure/hindsight-production-runbook.md` — operational steps
- ADR-007 — Hindsight as single RAG/memory layer; startup-program deferral
- ADR-012 — BabelDOC sidecar (same Pyodide-can't-host-it constraint class)
- Hindsight Cloud pricing — https://vectorize.io/pricing
- Hindsight Cloud billing docs — https://docs.hindsight.vectorize.io/billing
- Issue #166 — production Hindsight latency and 50-user reliability
- Hindsight (MIT, self-host) — https://github.com/vectorize-io/hindsight
- Hindsight storage docs — https://hindsight.vectorize.io/developer/storage
- Cloudflare Containers (GA, ephemeral disk) — https://developers.cloudflare.com/containers/
- Azure Database for PostgreSQL Flexible Server — https://azure.microsoft.com/en-us/products/postgresql/
- Azure DB for PostgreSQL pgvector extension — https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions
