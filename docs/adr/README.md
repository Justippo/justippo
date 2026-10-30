# Architecture Decision Records (ADR)

This directory follows the **MADR** convention (Markdown Architectural Decision Records —
see [adr.github.io/madr](https://adr.github.io/madr/)). MADR is the de-facto standard for
lightweight, markdown-based ADRs and is the format this project has adopted for recording
architectural and engineering decisions.

## Convention

- **One decision per ADR.** Each file records exactly one architectural decision. Related
  decisions cross-reference each other (e.g. `ADR-021` extends `ADR-002`/`ADR-006`/`ADR-012`)
  rather than being merged.
- **Filename:** `ADR-NNN-short-title.md`, numbered sequentially from `ADR-001`.
- **Status vocabulary** (MADR canonical set):

  | Status | Meaning |
  |--------|---------|
  | `proposed` | Under discussion, not yet agreed |
  | `accepted` | Agreed and (where applicable) implemented |
  | `deprecated` | No longer recommended; kept for history |
  | `superseded by ADR-XXXX` | Replaced by a later decision (link it) |

  This repo uses Title Case (`Accepted`, `Proposed`, `Superseded`) for the status keyword;
  both forms are acceptable under MADR.

- **Minimum structure:** title, date, status, decision-makers, then
  Context → Decision → Consequences (MADR's `Context and Problem Statement`,
  `Decision Outcome`, `Consciousness` map onto these).

## Index

| ADR | Title | Status | Decision |
|-----|-------|--------|----------|
| [ADR-001](ADR-001-rag-vector-db.md) | RAG Vector Database Strategy | Accepted | ChromaDB (dev) + Cloudflare Vectorize (prod) |
| [ADR-002](ADR-002-translation-babeldoc.md) | Document Translation Engine — BabelDOC | Accepted | BabelDOC (layout-preserving, capstone) via HTTP sidecar; m2m100-1.2b text-only fallback via Cloudflare Workers AI |
| [ADR-003](ADR-003-matrix-protocol.md) | Secure Cross-Border Document Exchange — Matrix Protocol | Accepted | Matrix protocol for E2EE federated exchange |
| [ADR-004](ADR-004-cloudflare-infrastructure.md) | Infrastructure — Cloudflare-Native Edge Stack | Accepted | Cloudflare Workers/Pages/D1/Vectorize/AI Gateway |
| [ADR-005](ADR-005-glossary-terminology.md) | Domain Glossary & Terminology Management | Accepted | Legal term consistency (EN/DE/FR), `medical` domain reserved |
| [ADR-006](ADR-006-pdf-extraction-license.md) | PDF Extraction Library | Accepted | License-driven choice (PyMuPDF → pypdfium2) |
| [ADR-007](ADR-007-memory-rag-layer.md) | Memory / RAG Layer | Accepted | Single-vendor discipline (Hindsight; Letta/Cognee deferred) |
| [ADR-008](ADR-008-licensing-strategy.md) | Licensing Strategy | Accepted | AGPL open core with dual licensing |
| [ADR-009](ADR-009-reducto-vs-inhouse-ocr.md) | Reducto vs In-House OCR | Accepted | Reducto public-corpus only; in-house OCR for user uploads (GDPR) |
| [ADR-010](ADR-010-baml-llm-interface.md) | BAML Type-Safe LLM Generation Interface | Accepted | BAML for glossary only + AdalFlow offline prompt optimization |
| [ADR-011](ADR-011-ui-testing.md) | UI Testing Strategy | Accepted | Storybook 8.6 + Chromatic TurboSnap + Vitest boundary (Playwright deferred) |
| [ADR-012](ADR-012-babeldoc-sidecar-runtime.md) | BabelDOC HTTP Sidecar Runtime | Accepted | External HTTP sidecar, AGPL isolation, Docker container |
| [ADR-013](ADR-013-release-tagging-strategy.md) | Release Tagging Strategy | Accepted | Pre-1.0 semver per sprint, SRS tags, GitHub Releases |
| [ADR-014](ADR-014-defer-adal-sdk-cloud-agents.md) | Defer AdaL SDK & Cloud Agents | Accepted | Post-capstone; in-house RAG + translation sufficient |
| [ADR-015](ADR-015-translation-model-replacement-strategy.md) | Translation Model Replacement | Proposed | Apertus 8B replaces m2m100 post-capstone; EuroLLM-22B as Phase 2 |
| [ADR-016](ADR-016-hindsight-hosting-strategy.md) | Hindsight Hosting Strategy | Accepted | Local Docker + Cloudflare Tunnel for capstone (Cloud/BYOC fallback) |
| [ADR-017](ADR-017-capstone-mvp-operating-envelope.md) | Capstone MVP Operating Envelope | Accepted | NFR-01/NFR-02 verified; NFR-11 Capstone MVP acceptance envelope |
| [ADR-018](ADR-018-matrix-authentication.md) | Matrix Authentication | Superseded | `matrix.org` homeserver as user store (superseded by ADR-019) |
| [ADR-019](ADR-019-matrix-oauth-pkce-authentication.md) | Matrix OAuth 2.0 + PKCE | Proposed | Delegated OAuth flow with PKCE (supersedes ADR-018) |
| [ADR-020](ADR-020-ocr-strategy-and-form-parsing.md) | OCR Strategy & Fillable PDF Parsing | Accepted | Three-path routing (scanned → Mistral OCR, fillable → pypdf, XFA → fallback); dots.ocr deferred |
| [ADR-021](ADR-021-composed-fillable-pdf-translation.md) | Composed PDF Reference Translation | Accepted | Native-text & fillable PDF understanding + EU-law context (extends ADR-002/006/012) |
| [ADR-022](ADR-022-knowledgebase-integration.md) | KnowledgeBase Integration | Accepted | Offline clustering (HDBSCAN+BERTopic), NER (spaCy EN/DE/FR), Sigma.js graph, graph-augmented RAG; all pipelines offline — no NFR-01 impact (extends ADR-007 Memory/RAG) |
| [ADR-023](ADR-023-linus-integration.md) | Linus Integration Strategy | Accepted | Grounding gate (DEC-0059), loud healthz (DEC-0060), network policy (DEC-0061), cross-session memory (DEC-0028); feature-flagged, Pyodide-safe (extends ADR-022, ADR-007) |
