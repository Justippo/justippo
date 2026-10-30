# ADR-004: Infrastructure — Cloudflare-Native Edge Stack

**Date:** 2026-05-14
**Status:** Accepted
**Author:** Mihai Chindriș

## Context

The capstone requires a deployed web application. The team needs zero-ops infrastructure that works within a student budget, supports EU data residency, and scales post-capstone without a full cloud migration.

## Decision

Use **Cloudflare's full edge stack** as the production infrastructure layer:

| Service | Purpose |
|---------|---------|
| Cloudflare Pages | Frontend hosting (Next.js static export + edge functions) |
| Cloudflare Workers | Edge API routing, lightweight serverless compute |
| Cloudflare AI Gateway | LLM proxy — caching, rate limiting, cost analytics (free on all plans) |
| Cloudflare Vectorize | Vector DB for production RAG (replaces ChromaDB) |
| Cloudflare D1 | SQLite-compatible metadata DB (replaces local SQLite) |

## Cloudflare for Students

Apply at `cloudflare.com/students` with `@quantic.edu`. Quantic is a US-accredited institution — the `.edu` eligibility check is institution-based, not location-based. Worst case: the always-free tier is sufficient for the entire capstone.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| AWS (EC2 + RDS + S3) | Cost, complexity, requires DevOps setup |
| Vercel + Supabase | Splits the stack; Supabase is US-hosted by default |
| Render / Railway | Good fallback but no AI Gateway or Vectorize equivalent |
| GCP Cloud Run | Overkill for capstone; no student credits path |

## Consequences

- Local dev uses Docker Compose with ChromaDB + SQLite (no CF credentials needed)
- Production deploy triggered by GitHub Actions on merge to `main`
- Cloudflare AI Gateway is the **permanent** LLM proxy — even post-capstone on AWS/Azure, CF sits in front
- D1 is SQLite-based; migrate to PlanetScale or Supabase if relational complexity grows post-capstone
