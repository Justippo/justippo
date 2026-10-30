# ADR-001: RAG Vector Database Strategy

**Date:** 2026-05-14
**Status:** Accepted
**Author:** Mihai Chindriș

## Context

The RAG engine requires a vector database for storing and querying multilingual document embeddings. Two environments must be supported: local development (no cloud credentials needed) and production (Cloudflare-native).

## Decision

Use **ChromaDB** for local development and **Cloudflare Vectorize** for production. Abstract over both via a `VectorStoreClient` interface in `app/integrations/cloudflare/vectorize.py`.

The active backend is selected via the `VECTOR_DB_PROVIDER` environment variable (`chromadb` | `cloudflare`).

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Pinecone | External SaaS, adds cost, not Cloudflare-native |
| Weaviate | Complex self-hosting, overkill for capstone scope |
| pgvector | Requires PostgreSQL, heavier than needed |
| Cloudflare Vectorize only | No local dev without CF credentials |

## Consequences

- Sprint 1 delivers search over ChromaDB locally; Sprint 2 migrates to Cloudflare Vectorize in CI/CD
- The `VectorStoreClient` abstraction must be kept thin — don't leak ChromaDB-specific APIs into services
- Vectorize Hindsight wraps Vectorize and adds agent memory; activate in Sprint 1 alongside ChromaDB
