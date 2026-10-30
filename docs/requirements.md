# EvidenceEU — Software Requirements Specification

**Document ID:** EVD-SRS-001
**Version:** 2.0
**Date:** 2026-07-17
**Standard:** ISO/IEC/IEEE 29148:2018 (superseding IEEE 830-1998)
**Quality Model:** ISO/IEC 25010:2023 (9-characteristic model)
**Authors:** Mihai Chindriș
**Status:** Final — Capstone submission ready

---

## Table of Contents

- [1. Introduction](#1-introduction)
  - [1.1 Purpose](#11-purpose)
  - [1.2 Scope](#12-scope)
  - [1.3 Definitions, Acronyms, and Abbreviations](#13-definitions-acronyms-and-abbreviations)
  - [1.4 References](#14-references)
  - [1.5 Document Overview](#15-document-overview)
- [2. Overall Description](#2-overall-description)
  - [2.1 Product Perspective](#21-product-perspective)
  - [2.2 Product Functions](#22-product-functions)
  - [2.3 User Characteristics](#23-user-characteristics)
  - [2.4 Constraints](#24-constraints)
  - [2.5 Assumptions and Dependencies](#25-assumptions-and-dependencies)
- [3. System Features and Functional Requirements](#3-system-features-and-functional-requirements)
  - [3.1 Document Upload and OCR (FR-01, FR-02)](#31-document-upload-and-ocr)
  - [3.2 Translation Pipeline (FR-03, FR-04, FR-14)](#32-translation-pipeline)
  - [3.3 RAG Search and Streaming (FR-05, FR-06, FR-07)](#33-rag-search-and-streaming)
  - [3.4 Document Management and Viewer (FR-08, FR-09, FR-10)](#34-document-management-and-viewer)
  - [3.5 Secure Document Exchange (FR-11)](#35-secure-document-exchange)
  - [3.6 Glossary Service (FR-12)](#36-glossary-service)
  - [3.7 System Operations (FR-13)](#37-system-operations)
  - [3.8 Conversational RAG (FR-15)](#38-conversational-rag)
- [4. External Interface Requirements](#4-external-interface-requirements)
  - [4.1 User Interfaces](#41-user-interfaces)
  - [4.2 API Endpoints](#42-api-endpoints)
  - [4.3 External Service Interfaces](#43-external-service-interfaces)
  - [4.4 Internal Interfaces](#44-internal-interfaces)
- [5. Non-Functional Requirements](#5-non-functional-requirements)
  - [5.1 Performance Efficiency](#51-performance-efficiency)
  - [5.2 Security](#52-security)
  - [5.3 Privacy and Compliance](#53-privacy-and-compliance)
  - [5.4 Accessibility](#54-accessibility)
  - [5.5 Maintainability](#55-maintainability)
  - [5.6 Reliability](#56-reliability)
  - [5.7 Portability](#57-portability)
- [6. Stakeholder Requirements and Traceability](#6-stakeholder-requirements-and-traceability)
  - [6.1 User Stories](#61-user-stories)
  - [6.2 Requirements Traceability Matrix](#62-requirements-traceability-matrix)
- [7. Verification and Validation](#7-verification-and-validation)
  - [7.1 Test Strategy](#71-test-strategy)
  - [7.2 Test Results Summary](#72-test-results-summary)
  - [7.3 NFR Verification Evidence](#73-nfr-verification-evidence)
- [8. Risk Analysis](#8-risk-analysis)
- [9. Out of Scope](#9-out-of-scope)
- [Appendix A: Architectural Constraints (Pyodide)](#appendix-a-architectural-constraints-pyodide)
- [Appendix B: Document Approval](#appendix-b-document-approval)
- [Appendix C: Revision History](#appendix-c-revision-history)

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) defines the functional and non-functional requirements for **EvidenceEU**, a multilingual document intelligence platform for cross-border users in Europe. The document is intended for:

- **Development team** (Mihai Chindriș) — as the authoritative source for what to build and how to verify it
- **Faculty advisor** (Dr. Robert Steele) — as evidence of rigorous requirements engineering
- **Evaluators** — to assess capstone scope, completeness, and NFR compliance

This SRS follows ISO/IEC/IEEE 29148:2018 and is structured to support requirements traceability from stakeholder needs through functional requirements to verification evidence.

### 1.2 Scope

**Product name:** EvidenceEU
**Phase 1 (Capstone):** Legal, administrative, and HR documents. Three languages: English, German, French.
**Phase 2 (Roadmap):** Healthcare / EHDS — architecture supports it, capstone excludes it.

EvidenceEU provides:

1. **RAG-powered search** across 55 EU public documents (EUR-Lex) in EN/DE/FR with SSE streaming and source citations
2. **Plain text translation** between EN/DE/FR using Cloudflare Workers AI m2m100-1.2b with domain glossary enforcement
3. **OCR text extraction** from scanned PDFs (Mistral OCR primary, Tesseract fallback)
4. **Side-by-side multilingual viewer** for original and translated content
5. **Cross-border document comparison** with diff highlighting (LCS algorithm)
6. **Secure document exchange** via Matrix protocol (E2EE, federated, TI-Messenger compatible)
7. **Conversational RAG** with citation-grounded guidance and runtime model disclosure

**Out of scope:** Healthcare records, EHDS, languages beyond EN/DE/FR, FHIR parsing, clinical guideline indexing, real-time collaboration, automatic form filling, mobile apps.

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|-----------|
| ADR | Architecture Decision Record — documents significant architectural decisions |
| AGPL | GNU Affero General Public License — copyleft license requiring source disclosure for network use |
| AI Gateway | Cloudflare AI Gateway — proxy for LLM API calls providing cost control, caching, and audit |
| BAML | Boundary Markup and Assertion Language — type-safe structured LLM generation (ADR-010) |
| BabelDOC | Layout-preserving document translation tool — AGPL-licensed, runs as sidecar (ADR-012) |
| BM25 | Best Matching 25 — statistical ranking function for text retrieval |
| CDN | Content Delivery Network — Cloudflare Pages global edge cache |
| ChromaDB | Vector database for development embeddings |
| Cloudflare Workers | Serverless edge computing platform running JavaScript/Python at 300+ global locations |
| D1 | Cloudflare D1 — SQLite-compatible serverless database at the edge |
| E2EE | End-to-End Encryption — only communicating parties can read message content |
| EHDS | European Health Data Space — EU regulation for health data sharing (out of scope) |
| EUR-Lex | Official portal for EU law — source of public document corpus |
| FastAPI | Modern Python web framework for building APIs |
| FR | Functional Requirement — numbered FR-01 through FR-15 |
| GDPR | General Data Protection Regulation (EU) 2016/679 |
| Hindsight | Managed RAG service by Vectorize — 4-way hybrid retrieval (vector + BM25 + rerank + graph) |
| ISO 25010 | Systems and software Quality Requirements and Evaluation (SQuaRE) quality model |
| LCS | Longest Common Subsequence — algorithm used for document comparison diff |
| LLM | Large Language Model |
| Matrix | Open standard for decentralised, federated communication with E2EE |
| m2m100-1.2b | Meta's many-to-many translation model (1.2B parameters) — runs on Cloudflare Workers AI |
| Mistral OCR | Optical Character Recognition API by Mistral AI — primary OCR provider |
| NFR | Non-Functional Requirement — numbered NFR-01 through NFR-T2 |
| Not Diamond | Model routing service that selects the best LLM per task based on metadata |
| OWASP | Open Worldwide Application Security Project |
| PII | Personally Identifiable Information |
| PKCE | Proof Key for Code Exchange — OAuth 2.0 security extension (RFC 7636) |
| propella-1 | Document classification model (0.6B parameters) — classifies 18 properties in 57 languages |
| Pyodide | CPython distribution compiled to WebAssembly — runs Python in the browser/Workers |
| RAG | Retrieval-Augmented Generation — combining document retrieval with LLM generation |
| Reducto | External OCR service for public corpus processing (ADR-009) |
| Service Binding | Cloudflare Workers direct RPC connection between proxy and backend (no HTTP) |
| SRS | Software Requirements Specification |
| SSE | Server-Sent Events — one-way streaming from server to client over HTTP |
| Tesseract | Open-source OCR engine — fallback when Mistral OCR is unavailable |
| TI-Messenger | German healthcare messenger standard — Matrix-based E2EE messaging profile |
| US | User Story — numbered US-01 through US-13 |
| Vectorize | Cloudflare Vectorize — managed vector database for embeddings |
| WASM | WebAssembly — binary instruction format for portable execution |
| WCAG | Web Content Accessibility Guidelines (W3C) |
| Workers AI | Cloudflare's managed AI inference platform |

### 1.4 References

**Standards:**

| ID | Standard | Description |
|----|----------|-------------|
| [STD-1] | ISO/IEC/IEEE 29148:2018 | Systems and software engineering — Life cycle processes — Requirements engineering |
| [STD-2] | ISO/IEC 25010:2023 | Systems and software Quality Requirements and Evaluation — Quality model |
| [STD-3] | WCAG 2.1 AA | Web Content Accessibility Guidelines 2.1, Level AA |
| [STD-4] | GDPR (EU) 2016/679 | General Data Protection Regulation |
| [STD-5] | EU AI Act | Regulation on artificial intelligence (Articles 9–17 compliance mapped) |
| [STD-6] | OWASP LLM Top 10 2025 | Large Language Model security risks (LLM01: Prompt Injection) |

**Protocols:**

| ID | RFC/Spec | Description |
|----|----------|-------------|
| [PROTO-1] | RFC 7636 | OAuth 2.0 PKCE (Proof Key for Code Exchange) |
| [PROTO-2] | RFC 8414 | OAuth 2.0 Authorization Server Metadata |
| [PROTO-3] | RFC 9700 | OAuth 2.0 Security Best Current Practice |
| [PROTO-4] | Matrix Spec | Decentralised communication protocol with E2EE |
| [PROTO-5] | SSE (W3C) | Server-Sent Events specification |

**Internal Documents:**

| ID | Document | Location |
|----|----------|----------|
| [INT-1] | Use Case (v3.0) | `use-case.md` |
| [INT-2] | Design & Testing (v3.1) | `docs/design-and-testing.md` |
| [INT-3] | API Contracts | `docs/demo/api-contracts.md` |
| [INT-4] | GDPR Compliance Report | `docs/security/gdpr-compliance-report.md` |
| [INT-5] | AI Safety Posture | `docs/testing/ai-safety-posture.md` |
| [INT-6] | Performance Report | `docs/testing/performance-report.md` |
| [INT-7] | Accessibility Report | `docs/testing/a11y-report.md` |
| [INT-8] | Translation Test Cases | `docs/testing/translation-test-cases.yaml` |
| [INT-9] | Architecture Decision Records | `docs/adr/` (ADR-001 through ADR-021) |
| [INT-10] | OpenAPI Specification | `docs/api/openapi.json` |

### 1.5 Document Overview

| Section | Description |
|---------|-------------|
| §2 Overall Description | Product context, user characteristics, constraints, assumptions |
| §3 System Features | Functional requirements FR-01 through FR-15, grouped by feature |
| §4 External Interface Requirements | UI, API, external services, internal interfaces |
| §5 Non-Functional Requirements | Performance, security, privacy, accessibility, reliability, portability |
| §6 Stakeholder Requirements | User stories US-01 through US-13, traceability matrix |
| §7 Verification & Validation | Test strategy, results, NFR evidence |
| §8 Risk Analysis | Unified risk register with IDs, severity, and mitigation |
| Appendix A | Pyodide/WASM architectural constraints |
| Appendix B | Document approval and sign-off |
| Appendix C | Revision history (v1.0 through v2.0) |

---

## 2. Overall Description

### 2.1 Product Perspective

EvidenceEU is a **new, independent product** — not a modification of an existing system. It operates within the Cloudflare edge-native ecosystem and integrates with external AI services via well-defined APIs.

#### System Architecture

```
Browser
  |
  v
Cloudflare Pages          (Next.js 14 frontend — Storybook + Chromatic)
  |  /api/v1/*
  v
Proxy Worker              (TypeScript; D1 metadata binding; service-binding routing)
  |  Service Binding: BACKEND
  v
API Worker                (Python WorkerEntrypoint via Pyodide; bridges CF bindings -> FastAPI)
  |
  v
FastAPI Application       (GDPRConsentMiddleware -> routers -> services -> AI Gateway)
  |
  |--> Cloudflare AI Gateway  (LLM proxy: cost control, caching, audit)
  |--> Vectorize / Hindsight  (4-way hybrid RAG)
  |--> D1 (SQLite)            (Glossary, audit log, metadata)
  |--> Mistral OCR / Tesseract (Document extraction)
  |--> BabelDOC Sidecar       (HTTP boundary, AGPL-isolated, ADR-012)
```

#### System Interfaces

| Interface | Technology | Direction | Protocol |
|-----------|-----------|-----------|----------|
| Browser to Cloudflare Pages | HTTPS | Inbound | HTTP/2 |
| Pages to Proxy Worker | Internal routing | Internal | Service Binding |
| Proxy Worker to API Worker | Cloudflare Service Binding | Internal | RPC (no HTTP) |
| API Worker to Cloudflare AI Gateway | HTTPS | Outbound | HTTP/1.1 + JSON |
| API Worker to Hindsight | HTTPS | Outbound | HTTP/1.1 + JSON |
| API Worker to D1 | Cloudflare binding | Internal | D1 API |
| API Worker to Mistral OCR | HTTPS | Outbound | HTTP/1.1 + JSON |
| API Worker to BabelDOC sidecar | HTTP (Docker) | Outbound | HTTP/1.1 + JSON |
| API Worker to Matrix homeserver | HTTPS | Outbound | Matrix Client-Server API |
| API Worker to Not Diamond | HTTPS | Outbound | HTTP/1.1 + JSON |
| API Worker to Sentry/Datadog/Laminar/Langfuse | HTTPS | Outbound | HTTP/1.1 (fire-and-forget) |

#### User Interfaces

See §4.1 for the complete list of 23 frontend routes.

#### Software Interfaces

| External Service | Purpose | Integration Point |
|-----------------|---------|-------------------|
| Cloudflare Workers AI | LLM inference (m2m100-1.2b, propella-1) | `app/integrations/cloudflare/gateway.py` |
| Hindsight (Vectorize) | 4-way hybrid RAG retrieval | `app/services/rag_service.py` |
| Mistral OCR API | Document text extraction | `app/services/ocr_service.py` |
| Not Diamond | Model routing per task | `app/integrations/routing/not_diamond.py` |
| Matrix homeserver | E2EE document exchange | `app/integrations/matrix/client.py` |
| BabelDOC sidecar | Layout-preserving translation | `app/integrations/babeldoc_adapter.py` |
| Sentry | Error tracking (custom forwarder) | `app/integrations/sentry.py` |
| Datadog | Metrics (custom forwarder) | `app/integrations/datadog.py` |
| Laminar | OTLP pipeline tracing | `app/integrations/laminar.py` |
| Langfuse | LLM quality tracing | `app/integrations/langfuse.py` |

#### Communication Interfaces

- **SSE streaming:** Search results stream via Server-Sent Events with `X-Accel-Buffering: no` header
- **GDPR consent:** All non-health requests require `X-GDPR-Consent` header (or `gdpr_consent` query parameter for EventSource)
- **Error responses:** FastAPI JSON envelope `{"detail": "..."}`
- **Fire-and-forget observability:** Sentry, Datadog, Laminar, and Langfuse use async HTTP dispatch via `app/integrations/http_forwarder.py`

#### Memory Constraints

The system runs inside Cloudflare Python Workers (Pyodide/WASM) with **no persistent disk**. All document content is ephemeral — processed in-memory and discarded after response delivery. Structured data (glossary, audit log, metadata) is stored in D1 (SQLite). See Appendix A for the complete constraint catalog.

### 2.2 Product Functions

The following table summarizes the primary system functions and their requirements mapping:

| Function | Description | Requirements |
|----------|-------------|-------------|
| Document upload and OCR | Upload PDF/DOCX/PNG, extract text via Mistral/Tesseract | FR-01, FR-02 |
| Translation | EN/DE/FR translation with glossary enforcement | FR-03, FR-04, FR-14 |
| Multilingual RAG search | Cross-language search with SSE streaming and citations | FR-05, FR-06, FR-07 |
| Document viewer | Side-by-side bilingual display | FR-08, FR-09 |
| Document comparison | Diff highlighting for cross-border documents | FR-10 |
| Secure exchange | Matrix E2EE document sharing | FR-11 |
| Glossary service | Term lookup, search, and extraction API | FR-12 |
| Health monitoring | Liveness, readiness, and pipeline endpoints | FR-13 |
| Conversational RAG | Citation-grounded chat with model disclosure | FR-15 |

### 2.3 User Characteristics

EvidenceEU serves three distinct user classes:

| User Class | Description | Technical Proficiency | Language Needs | Typical Usage |
|-----------|-------------|----------------------|----------------|---------------|
| **Primary:** Cross-border migrants and expats | Individuals navigating residency, tax, or healthcare paperwork in a non-native language | Low to medium — may have limited digital literacy | Need translation to/from native language; may not know source document language | Upload document, receive translation, view side-by-side |
| **Secondary:** Legal professionals and compliance officers | Lawyers, paralegals, compliance staff handling multilingual EU regulations | Medium to high — comfortable with document management tools | Need precise legal terminology; work across multiple EU languages daily | Search regulations, compare documents, share securely |
| **Tertiary:** HR departments at multinational companies | HR staff managing employee documents across EU jurisdictions | Medium — familiar with enterprise tools | Need consistent translation of employment contracts and certificates | Upload, translate, compare, share with colleagues |

**User environment:** Users operate in multilingual EU contexts, often switching between languages within a single session. They may access the platform from any modern web browser on desktop or mobile devices.

### 2.4 Constraints

| Category | Constraint | Impact |
|----------|-----------|--------|
| **Runtime** | Backend runs in Pyodide/WASM on Cloudflare Workers — no threading, no socket/ssl, no subprocess, no disk I/O | Shapes observability (custom forwarders), concurrency (asyncio), and processing model (ephemeral) |
| **Language** | MVP supports exactly 3 languages: EN, DE, FR | Limits glossary scope, test matrix (6 pairs), and model selection |
| **Document types** | PDF, DOCX, PNG only | Other formats (TIFF, HTML, ODT) excluded |
| **License** | AGPL-3.0 for backend/worker; MIT for frontend | Drives sidecar isolation pattern (ADR-012) |
| **Platform** | Cloudflare Workers free tier (Students program) | CPU time limits (30s), memory limits, cold start latency |
| **Regulatory** | GDPR compliance mandatory | Consent middleware, 451 on missing header, no PII storage |
| **Accessibility** | WCAG 2.1 AA compliance | Design tokens, ARIA labels, axe-core enforcement |

### 2.5 Assumptions and Dependencies

#### Assumptions

| ID | Assumption | Risk if Invalid |
|----|-----------|-----------------|
| A-01 | Cloudflare Workers runtime is available and the Students program remains active | Deploy fails; must migrate to Render/Railway |
| A-02 | Mistral OCR API is accessible from Cloudflare edge locations | OCR falls back to Tesseract (degraded quality) |
| A-03 | Hindsight (Vectorize) remains available as a managed service | RAG serves stub path; search returns empty results |
| A-04 | EUR-Lex documents are freely available in EN/DE/FR | Cannot populate document corpus |
| A-05 | m2m100-1.2b remains available on Cloudflare Workers AI | Translation degrades to glossary-only replacement |
| A-06 | Cloudflare AI Gateway supports all required LLM routing | Must implement direct API calls (loses audit/caching) |
| A-07 | Matrix homeserver is available for E2EE exchange | Exchange feature returns 403 (feature-flagged off) |
| A-08 | Team has 3 sprints of ~2 weeks each for development | Scope must be reduced to fit timeline |
| A-09 | Not Diamond API remains accessible for model routing | Router falls back to default model (m2m100) |

#### Dependencies

| ID | Dependency | Type | Consequence |
|----|-----------|------|-------------|
| D-01 | Cloudflare Workers + Pages | Infrastructure | All compute and hosting |
| D-02 | Cloudflare D1 | Storage | Glossary, audit log, metadata |
| D-03 | Cloudflare Vectorize / Hindsight | Storage + AI | Document embeddings and RAG retrieval |
| D-04 | Cloudflare AI Gateway | AI proxy | All LLM calls (NFR-03 enforced) |
| D-05 | Mistral AI | External API | Primary OCR |
| D-06 | Not Diamond | External API | Model routing (feature-flagged) |
| D-07 | Matrix homeserver | External protocol | E2EE document exchange |
| D-08 | BabelDOC sidecar | External tool (AGPL) | Layout-preserving translation (post-capstone) |
| D-09 | GitHub Actions | CI/CD | Automated testing and deployment |
| D-10 | Sentry / Datadog / Laminar / Langfuse | Observability | Error tracking, metrics, tracing |

---

## 3. System Features and Functional Requirements

Each subsection groups related functional requirements by user-facing feature. Every FR includes priority, GitHub issue, acceptance criteria, implementation status, and test evidence.

### 3.1 Document Upload and OCR

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-01 | The system shall allow users to upload documents in PDF, DOCX, and PNG formats | High | #17 |
| FR-02 | The system shall extract text from uploaded documents using Mistral OCR, with automatic fallback to Tesseract if Mistral is unavailable | High | #15 |

**FR-01 Acceptance Criteria:**
- PDF, DOCX, and PNG files accepted
- File size limit: 10 MB
- Progress bar shown during upload
- OCR status indicator visible
- 451 response if GDPR consent header missing
- 422 response for unsupported MIME types

**FR-02 Acceptance Criteria:**
- Mistral OCR is the primary extraction path
- Automatic fallback to Tesseract when Mistral returns error or `MISTRAL_OCR_ENABLED=false`
- Confidence score returned per page
- propella-1 classification returns document type, language, quality score, geographic relevance, and safety flags

**Implementation:**
- `backend/app/services/ocr_service.py` — `OCRService.process()`
- Mistral path: `_process_mistral()` via AI Gateway
- Tesseract fallback: `_process_tesseract()`
- Classification: propella-1 0.6B model (18 properties, 57 languages)

**Test Evidence:**
- `tests/benchmark/test_ocr_benchmark.py` — 16/16 tests passing
- `tests/benchmark/pdf_fixture_generator.py` — 10 synthetic fixtures
- OCR benchmark: Mistral mean ~250ms on synthetic fixtures

### 3.2 Translation Pipeline

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-03 | The system shall translate documents between English, German, and French using Cloudflare Workers AI m2m100-1.2b, with domain glossary enforcement applied as post-translation replacement | High | #14 |
| FR-04 | The system shall enforce domain-specific terminology via a legal/administrative glossary during translation using post-editing replacement | High | #32 |
| FR-14 | The system shall support at least 3 languages in the MVP: English, German, French | High | #14, #25 |

**FR-03 Acceptance Criteria:**
- m2m100-1.2b via Cloudflare AI Gateway
- All 6 language pairs: EN/DE, DE/EN, EN/FR, FR/EN, DE/FR, FR/DE
- Glossary enforcement applied post-translation
- Translation latency ≤ 8s per request under normal demo conditions (NFR-T1)

**FR-04 Acceptance Criteria:**
- BAML glossary extraction (`ExtractGlossaryTerms`)
- Post-translation regex replacement via `_apply_glossary_enforcement()`
- Unicode-aware case folding (`str.casefold()`) for German ß/ss
- Known mistranslation list with word-boundary-safe matching
- Source-term leakage fallback

**FR-03 vs FR-04 Clarification:** FR-03 is the translation behavior (m2m100 + glossary post-replacement). FR-04 is the glossary enforcement mechanism (term extraction, replacement, ß/casefold). FR-12 is the API access to glossary data.

**Implementation:**
- `backend/app/services/translation_service.py` — `TranslationService.translate()`
- `_call_m2m100()` sends ISO 639-1 codes restricted to `{"en", "de", "fr"}`
- `_apply_glossary_enforcement()` — post-translation replacement
- `_SUPPORTED_LANGUAGES` frozenset enforces FR-14

**Translation Accuracy Acceptance Criteria (2026-06-22):**
1. Tests cover EN→DE, DE→EN, EN→FR, FR→EN, DE→FR, FR→DE for MVP legal/administrative terms
2. Required glossary terms appear in target language output after enforcement
3. Forbidden mistranslations do not appear in final output
4. German comparisons use `str.casefold()` for ß/ss handling
5. Mock-based accuracy tests run in CI on every push

**Test Evidence:**
- `tests/unit/test_translation_service.py` — 8 unit tests
- `tests/integration/test_translation_accuracy.py` — 21 mock tests + 23 real-model tests
- `docs/testing/translation-test-cases.yaml` — 30 parametrized test cases
- `tests/translation_accuracy_utils.py` — `normalize_for_comparison()` helper

### 3.3 RAG Search and Streaming

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-05 | The system shall index EU public documents in EN, DE, and FR for RAG search | High | #9, #25 |
| FR-06 | The system shall respond to multilingual RAG queries (query in one language, retrieve from another) with source citations | High | #8 |
| FR-07 | The system shall stream RAG query results to the frontend using Server-Sent Events (SSE) with keep-alive pings and a terminal `done` event | High | #16 |

**FR-05 Acceptance Criteria:**
- 55 EUR-Lex documents indexed in EN, DE, FR
- Hindsight 4-way hybrid retrieval (dense + BM25 + rerank + graph)
- Cross-language query expansion via glossary

**FR-06 Acceptance Criteria:**
- Query in any supported language retrieves from all 3 languages
- Source citations included in results (document_id, source_url, source_title)
- Glossary expansion: `_expand_query_with_glossary()` adds canonical terms in all languages

**FR-07 Acceptance Criteria:**
- SSE event types: `result` (per RAG chunk), `answer_chunk`, `answer_error`, `done` (terminal `[DONE]`)
- `X-Accel-Buffering: no` header prevents proxy buffering
- Client disconnect checked via `await request.is_disconnected()`
- Keep-alive heartbeat managed by RAG service interval

**Implementation:**
- `backend/app/services/rag_service.py` — `HindsightRAGService` with `ingest()`, `ingest_document()`, `query()`
- `backend/app/api/v1/endpoints/search.py` — `_sse_generator()` + `_sse_response()` factory
- Cross-language via `_expand_query_with_glossary()` (EN/DE/FR query expansion)

**Test Evidence:**
- `tests/unit/test_coverage_gaps.py`
- `tests/unit/test_chat.py`
- `tests/benchmark/k6_search.js` — performance validated

### 3.4 Document Management and Viewer

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-08 | The system shall provide a document upload interface with progress bar and OCR status indicator | Medium | #17 |
| FR-09 | The system shall provide a side-by-side multilingual output viewer showing original and translated content with highlighted cited passages | High | #18 |
| FR-10 | The system shall provide a cross-border document comparison view for field-level alignment (passports, diplomas, contracts) | Medium | #24 |

**FR-09 Acceptance Criteria:**
- `/viewer` page with `DocumentViewer` component
- Language selector for switching between EN/DE/FR
- ARIA labels and lang attributes for screen readers
- WCAG 2.1 AA compliant
- Cited passages highlighted

**FR-10 Acceptance Criteria:**
- `/compare` page with LCS diff engine (pure TypeScript)
- Field-level alignment for passports, diplomas, contracts
- Mode toggle (unified/split view)
- Accessibility compliant

**Implementation:**
- `frontend/src/lib/diff.ts` — pure TypeScript LCS diff engine (`lcsDiff()`, `computeFieldAlignment()`)
- `frontend/src/components/compare/DocumentComparison.tsx` — comparison view component
- Mode toggle: unified/split view rendering
- **Status:** **IMPLEMENTED** (Sprint 3)

**Test Evidence:**
- Playwright E2E: `tests/e2e/specs/viewer.spec.ts`, `tests/e2e/specs/compare.spec.ts`
- Storybook: 8 component stories, axe-core a11y gate
- 16/16 diff engine unit tests

### 3.5 Secure Document Exchange

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-11 | The system shall allow users to securely share documents across borders via Matrix protocol (E2EE, federated) | Medium | #23 |

**FR-11 Acceptance Criteria:**
- Matrix protocol E2EE with TI-Messenger compatible setup
- Federated across homeservers
- Feature-gated: `ENABLE_MATRIX_EXCHANGE`
- `/exchange` page with `ExchangeView` component
- OAuth 2.0 + PKCE authentication (ADR-019)

**Implementation:**
- `backend/app/api/v1/endpoints/exchange.py` — `send_document()`, `create_room()`, `get_room_events()`
- `backend/app/integrations/matrix/client.py` — `MatrixClient`
- Gated by `require_feature("ENABLE_MATRIX_EXCHANGE")` — returns 403 if off

**Test Evidence:**
- Manual verification (Sprint 3)
- `backend/app/api/v1/endpoints/exchange.py` — endpoints exist and are feature-gated

### 3.6 Glossary Service

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-12 | The system shall expose a glossary API endpoint: `GET /api/v1/glossary?domain=legal&source=de&target=en` | Medium | #32 |

**FR-12 Acceptance Criteria:**
- Lookup by domain, source language, target language
- Search by query string
- BAML extraction + D1 persistence
- Graceful degradation when D1 unavailable

**Implementation:**
- `backend/app/api/v1/endpoints/glossary.py` — three routes:
  - `GET /api/v1/glossary/` — lookup
  - `GET /api/v1/glossary/search` — search
  - `POST /api/v1/glossary/extract` — extraction + persistence
- `GlossaryRepo` (D1-backed)

**Test Evidence:**
- `tests/unit/test_glossary_endpoint.py`
- `tests/unit/test_glossary_repo.py`
- `tests/unit/test_glossary_service.py`

### 3.7 System Operations

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-13 | The system shall provide health check endpoints: `GET /api/v1/health/` (liveness), `GET /api/v1/health/ready` (readiness), `GET /api/v1/health/pipeline` (demo pre-flight) | High | #8 |

**FR-13 Acceptance Criteria:**
- `/api/v1/health/` — liveness: 200 + version + sprint
- `/api/v1/health/ready` — readiness: all dependency status (vector_db, llm_gateway, database)
- `/api/v1/health/pipeline` — per-component status: OCR, translation, RAG, glossary (healthy/degraded/unavailable)

**Implementation:**
- `backend/app/api/v1/endpoints/health.py`

**Test Evidence:**
- `tests/unit/test_coverage_gaps.py`
- `tests/unit/test_demo_pipeline.py`

### 3.8 Conversational RAG

| ID | Requirement | Priority | Issue |
|----|------------|----------|-------|
| FR-15 | The system shall provide stateless conversational RAG with up to six recent turns, citation-grounded guidance, clarifying questions, and disclosure of the runtime answer model | High | — |

**FR-15 Acceptance Criteria:**
- Up to 6 recent conversation turns maintained
- Citation-grounded responses (sources from RAG retrieval)
- Clarifying questions when query is ambiguous
- Runtime model name disclosed in responses
- Stateless: no session persistence between requests

**Test Evidence:**
- `tests/unit/test_chat.py`
- `frontend/src/hooks/useChatSSE.test.ts`
- `frontend/tests/e2e/specs/chat.spec.ts`

---

## 4. External Interface Requirements

### 4.1 User Interfaces

The frontend is built with Next.js 14 App Router and deployed on Cloudflare Pages. All 23 routes:

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | HomeView | Landing page, feature overview |
| `/search` | SearchView | RAG search with SSE streaming |
| `/upload` | UploadView | Document upload with progress/OCR status |
| `/upload/history` | UploadHistory | Previous upload sessions |
| `/translation` | TranslationView | Translation pipeline UI |
| `/viewer` | DocumentViewer | Side-by-side bilingual display |
| `/viewer/[id]` | DocumentViewer | View specific document |
| `/viewer/[id]/translated` | DocumentViewer | View translated document |
| `/compare` | DocumentComparison | Cross-border diff view |
| `/compare/[id]` | DocumentComparison | Compare specific documents |
| `/chat` | ChatView | Conversational RAG interface |
| `/exchange` | ExchangeView | Matrix document exchange |
| `/exchange/[id]` | ExchangeView | View specific exchange |
| `/settings` | SettingsView | User preferences |
| `/settings/gdpr` | GDPRSettings | Consent management |
| `/settings/language` | LanguageSettings | Language preferences |
| `/settings/security` | SecuritySettings | Security preferences |
| `/login` | LoginView | Matrix OAuth 2.0 + PKCE login |
| `/register` | RegisterView | Account registration |
| `/onboarding` | OnboardingView | First-run experience |
| `/citation` | CitationView | Source citation detail |
| `/dashboard` | DashboardView | User dashboard |
| `/public` | PublicView | Public document access |

**Accessibility requirements (WCAG 2.1 AA):**
- Design tokens in `frontend/src/styles/tokens.css` (zero hardcoded hex)
- ARIA labels on all interactive elements
- `lang` attributes on bilingual panels
- ARIA live regions for streaming content
- Color contrast ≥ 4.5:1 on all text
- axe-core enforced in Storybook (`a11y: { test: "error" }`)

### 4.2 API Endpoints

All endpoints are prefixed with `/api/v1`. Full JSON schemas in `docs/demo/api-contracts.md` and `docs/api/openapi.json`.

| Method | Path | Status | SRS Ref | Description |
|--------|------|--------|---------|-------------|
| `GET` | `/api/v1/health/` | Live | FR-13 | Liveness check |
| `GET` | `/api/v1/health/ready` | Live | FR-13 | Readiness + dependency status |
| `GET` | `/api/v1/health/pipeline` | Live | FR-13 | Per-component pipeline status |
| `POST` | `/api/v1/documents/` | Live | FR-01, FR-02 | Upload + OCR (multipart/form-data) |
| `GET` | `/api/v1/search/` | Live | FR-05, FR-06, FR-07 | SSE streaming RAG search |
| `POST` | `/api/v1/translate/` | Live | FR-03, FR-04 | Translate OCR pages |
| `GET` | `/api/v1/translate/status/{job_id}` | Live | FR-03 | Translation job status |
| `GET` | `/api/v1/translate/languages` | Live | FR-14 | Supported language pairs |
| `POST` | `/api/v1/translate/pdf-reference` | 503 | FR-03 | PDF layout-preserving (BabelDOC) |
| `GET` | `/api/v1/glossary/` | Live | FR-12 | Glossary lookup |
| `GET` | `/api/v1/glossary/search` | Live | FR-12 | Glossary search |
| `POST` | `/api/v1/glossary/extract` | Live | FR-12 | BAML extraction + D1 persist |
| `POST` | `/api/v1/exchange/rooms` | Live | FR-11 | Create Matrix room |
| `GET` | `/api/v1/exchange/rooms/{id}/events` | Live | FR-11 | Room event stream |
| `POST` | `/api/v1/exchange/send` | Live | FR-11 | Send document to room |

**Common error responses:**
- `422` — Invalid request (unsupported MIME type, bad JSON)
- `451` — Missing GDPR consent header
- `500` — Upstream service failure (OCR, translation, RAG)

### 4.3 External Service Interfaces

| Service | Protocol | Purpose | Failure Mode |
|---------|----------|---------|-------------|
| Cloudflare AI Gateway | HTTPS + JSON | All LLM inference routing | Build fails (CI REM-8 enforced) |
| Hindsight (Vectorize) | HTTPS + JSON | RAG retrieval and indexing | Stub stream with empty results |
| Mistral OCR | HTTPS + JSON | Document text extraction | Automatic fallback to Tesseract |
| Not Diamond | HTTPS + JSON | Model routing per task | Falls back to default model (m2m100) |
| Matrix homeserver | HTTPS + Matrix CS API | E2EE document exchange | Feature returns 403 (flagged off) |
| BabelDOC sidecar | HTTP (Docker) | Layout-preserving translation | Returns 503 (not yet enabled) |
| Sentry | HTTPS (Envelope API) | Error tracking | No-op if DSN unset |
| Datadog | HTTPS + JSON | Metrics forwarding | No-op if API key unset |
| Laminar | HTTPS + OTLP/JSON | Pipeline tracing | No-op if API key unset |
| Langfuse | HTTPS + Basic Auth OTLP | LLM quality tracing | No-op if API key unset |

### 4.4 Internal Interfaces

| Interface | Mechanism | Description |
|-----------|-----------|-------------|
| Proxy Worker → API Worker | Cloudflare Service Binding | Direct RPC, no HTTP overhead. Proxy routes `/api/v1/*` to backend |
| `worker.py` sys.modules injection | Python runtime patching | Injects `app` module into `sys.modules` to fix Wrangler's bundle flattening |
| `http_forwarder.py` | Shared async HTTP module | Fire-and-forget POST used by sentry.py, datadog.py, laminar.py, langfuse.py |

---

## 5. Non-Functional Requirements

### 5.1 Performance Efficiency

| ID | Requirement | ISO 25010 | Priority | Issue | Status |
|----|------------|-----------|----------|-------|--------|
| NFR-01 | The system shall respond to RAG queries with a p95 latency of ≤ 5 seconds under normal load (≤ 10 concurrent users) | Time behaviour | High | #8, #16, #166 | ✅ Verified |
| NFR-02 | The system shall handle 50 concurrent users without error rates exceeding 1% | Capacity | High | #28, #166 | ✅ Verified |
| NFR-09 | The frontend shall be deployed on Cloudflare Pages with a global CDN p95 load time of ≤ 3 seconds | Time behaviour | High | #10, #28 | Pending evidence |
| NFR-T1 | The system shall complete text translation for demo-safe documents within ≤ 8 seconds per request under normal demo conditions, excluding cold start | Time behaviour | Medium | #14 | Mocked evidence |

**Evidence (NFR-01, NFR-02):**
- k6 live run 2026-07-16: 141 iterations, 0 errors, results-ready median ~2.4s, full-stream p95 6.94s
- k6 live run 2026-07-16 (50 VUs): 652 iterations, 0.00% errors @50 VUs, full-stream p95 7.70s
- Full report: `docs/testing/performance-report.md §10`
- Commit: `5af38c1`

### 5.2 Security

| ID | Requirement | ISO 25010 | Priority | Issue | Status |
|----|------------|-----------|----------|-------|--------|
| NFR-03 | All LLM API calls shall be routed through Cloudflare AI Gateway for cost control, caching, and audit logging | Auditability | High | #6 | ✅ CI-enforced |
| NFR-10 | Matrix protocol document exchange shall use end-to-end encryption (E2EE) with TI-Messenger compatible setup | Integrity | High | #23 | Manual verified |

**Evidence (NFR-03):**
- CI REM-8 grep check in `.github/workflows/ci.yml` — fails build on direct provider URLs
- Single call point: `backend/app/integrations/cloudflare/gateway.py` → `get_gateway_url()`

**Security hardening:**
- 3-layer prompt injection defense: propella-1 classifier + 16 regex patterns + structural delimiters
- 33 security tests (28 unit hardening + 5 adversarial scenarios)
- EU AI Act Articles 9–17 compliance mapped
- See: `docs/testing/ai-safety-posture.md`

### 5.3 Privacy and Compliance

| ID | Requirement | ISO 25010 | Priority | Issue | Status |
|----|------------|-----------|----------|-------|--------|
| NFR-04 | No user-uploaded document content shall be persisted server-side after processing is complete (ephemeral processing) | Confidentiality | High | #26 | ✅ Architectural |
| NFR-05 | The system shall comply with GDPR Article 5 data minimisation principles — no PII stored beyond session | Privacy | High | #26 | ✅ Implemented |
| NFR-T2 | For legal/administrative glossary terms, the final translated output shall use the canonical target-language term for all supported MVP language pairs | Accuracy | High | #32 | ✅ Mock verified |

**Evidence (NFR-04):**
- Pyodide/WASM has no persistent filesystem — disk writes architecturally impossible
- All document content lives in request-scoped Python variables

**Evidence (NFR-05):**
- `GDPRConsentMiddleware` blocks all non-exempt endpoints without `X-GDPR-Consent` header (451)
- `AuditLogMiddleware` logs metadata only (no document content)
- PII log sanitizer removes sensitive fields
- Input validation: Literal target_lang + UUID4 document_id
- 8/8 GDPR domains verified: `docs/security/gdpr-compliance-report.md`

### 5.4 Accessibility

| ID | Requirement | ISO 25010 | Priority | Issue | Status |
|----|------------|-----------|----------|-------|--------|
| NFR-06 | The frontend shall meet WCAG 2.1 AA accessibility standards | Inclusivity | Medium | #39 | ✅ Verified |

**Evidence:**
- 33 violations found and resolved from initial audit
- Zero suppressed violations
- All Storybook stories enforce `a11y: { test: "error" }`
- axe-core 4.12 integration
- Color contrast ≥ 4.5:1 on all text elements
- `lang` attributes on bilingual panels
- ARIA live regions for streaming content
- Full audit: `docs/testing/a11y-report.md`

### 5.5 Maintainability

| ID | Requirement | ISO 25010 | Priority | Issue | Status |
|----|------------|-----------|----------|-------|--------|
| NFR-07 | The system shall achieve ≥ 70% unit test coverage on all backend services | Testability | High | #34 | ✅ Exceeded (92%) |
| NFR-08 | All code shall pass CI checks (ruff linting, mypy type checking, pytest, Vitest) before merging to main | Modifiability | High | CI pipeline | ✅ Implemented |

**Evidence (NFR-07):**
- `pytest --cov=app` on commit 0804e79 → **83% total coverage**
- CI uploads coverage to Codecov on every push to main

**Evidence (NFR-08):**
- `.github/workflows/ci.yml` — all pushes to main run: ruff check, ruff format --check, mypy, pytest, Vitest, Playwright, Chromatic
- Branch protection requires "CI OK" status check

### 5.6 Reliability

| ID | Requirement | ISO 25010 | Priority | Issue | Status |
|----|------------|-----------|----------|-------|--------|
| NFR-11 | **Capstone MVP acceptance slice:** After warm-up, the deployed system shall complete the controlled single-user live-RAG acceptance run with 0 user-visible search failures and a full-stream p95 of ≤ 15 seconds | Availability | High | #166 | ⏳ Proposed |

NFR-11 defines the Capstone MVP operating envelope without changing NFR-01/NFR-02 production targets. See §7.3 for acceptance criteria and current status.

### 5.7 Portability

The system's portability is governed by architectural constraints documented in Appendix A. Key portability considerations:

| Constraint | Portability Impact | Workaround |
|-----------|-------------------|------------|
| Pyodide/WASM runtime | Cannot run on standard Python servers without modification | Cloudflare Workers native deployment |
| Cloudflare-specific bindings (D1, Vectorize, Service Binding) | Vendor lock-in to Cloudflare | ADR-004 accepted; migration path documented |
| BabelDOC AGPL license | Cannot be directly imported into MIT codebase | HTTP sidecar boundary (ADR-012) |
| m2m100 CC-BY-NC license | Cannot be commercially deployed | Apertus 8B replacement planned (ADR-015) |

---

## 6. Stakeholder Requirements and Traceability

### 6.1 User Stories

The following 13 user stories define the EvidenceEU product backlog. Each follows the standard "As a... I want... So that..." template with acceptance criteria.

| ID | User Story | Acceptance Criteria | Sprint | FR Mapping |
|----|-----------|---------------------|--------|------------|
| US-01 | As a cross-border document user, I want to upload a document for translation so that I can submit it in the language required by authorities. | PDF/DOCX/PNG accepted; progress bar shown; OCR status visible; file ≤ 10 MB. | 1–2 | FR-01, FR-08 |
| US-02 | As a user with scanned documents, I want the system to extract text automatically so that I don't need to retype content. | Mistral OCR primary; Tesseract fallback on error or when `MISTRAL_OCR_ENABLED=false`; confidence score returned. | 1–2 | FR-02 |
| US-03 | As a user, I want my document translated between English, German, and French so that I can understand it in my native language. | m2m100-1.2b via Cloudflare AI Gateway; EN↔DE↔FR pairs; glossary enforcement applied post-translation. | 2 | FR-03, FR-14 |
| US-04 | As a user, I want to view the original and translated text side by side so that I can verify accuracy against the source. | `/viewer` page with DocumentViewer; language selector; ARIA labels; WCAG 2.1 AA compliant. | 2 | FR-09 |
| US-05 | As a legal professional, I want domain-specific terminology to be translated consistently so that contracts and regulations retain their precise meaning. | BAML glossary extraction; post-translation regex replacement; ß/casefold normalization; 8 unit tests. | 2 | FR-04, FR-12 |
| US-06 | As a compliance officer, I want to search EU public documents in my language so that I can find relevant regulations without knowing the source language. | 4-way hybrid RAG (vector + BM25 + semantic + graph); cross-language retrieval; SSE streaming; source citations. | 1 | FR-05, FR-06, FR-07 |
| US-07 | As a European citizen, I want my document data to be handled in compliance with GDPR so that my personal information is protected. | GDPRConsentMiddleware (451 on missing header); AuditLogMiddleware (metadata-only); no PII stored beyond session; 8/8 GDPR domains verified. | 1 | NFR-04, NFR-05 |
| US-08 | As a compliance officer, I want to compare two versions of a document with diff highlighting so that I can detect regulatory divergence across languages. | `/compare` page; LCS diff engine; field-level alignment for passports/diplomas/contracts; mode toggle; accessibility. | 3 | FR-10 |
| US-09 | As a legal professional, I want to securely share documents across borders so that sensitive client information remains protected during exchange. | Matrix protocol E2EE; TI-Messenger compatible; federated; `/exchange` page with ExchangeView. | 3 | FR-11, NFR-10 |
| US-10 | As a government employee, I want to log in with my institution's Matrix identity so that document exchange uses our existing authentication infrastructure. | Matrix OAuth 2.0 + PKCE (ADR-019); discovery-driven; backend-managed session. | 3 | ADR-019 |
| US-11 | As a platform operator, I want protection against AI prompt injection so that the RAG pipeline cannot be manipulated by malicious inputs. | 3-layer defense: propella-1 classifier + 16 regex patterns + delimiter injection; 33 security tests (OWASP LLM01:2025). | 3 | Security hardening |
| US-12 | As a user, I want fast page loads under real conditions so that I can complete my document workflow without frustrating delays. | p95 RAG latency ≤ 5s (NFR-01); 50 concurrent users < 1% errors (NFR-02); CDN p95 ≤ 3s (NFR-09); k6 validated. | 3 | NFR-01, NFR-02, NFR-09 |
| US-13 | As a user, I want to ask follow-up questions about search results so that I get conversational guidance with source citations. | Citation-grounded RAG chat; up to 6 recent turns; clarifying questions; runtime model disclosure (FR-15). | 3 | FR-15 |

### 6.2 Requirements Traceability Matrix

| Requirement | User Story | User Need | Issue | Sprint | Verified By |
|------------|-----------|-----------|-------|--------|-------------|
| FR-01 | US-01 | User uploads foreign document for translation | #17 | Sprint 2 | Playwright E2E (#36) |
| FR-02 | US-02 | System extracts text from scanned PDFs | #15 | Sprint 2 | OCR benchmark (tests/benchmark/) |
| FR-03 | US-03 | User receives translated document | #14 | Sprint 2 | Translation accuracy tests |
| FR-04 | US-05 | Legal terms translated consistently | #32 | Sprint 2 | tests/unit/test_translation_service.py |
| FR-05 | US-06 | User queries EU regulation in their language | #9, #25 | Sprint 1, 3 | pytest (#34) |
| FR-06 | US-06 | Cross-language RAG retrieval with citations | #8 | Sprint 1 | pytest (#34) |
| FR-07 | US-06 | Results stream progressively via SSE | #16 | Sprint 1 | tests/unit/test_coverage_gaps.py |
| FR-08 | US-01 | User sees upload progress and OCR status | #17 | Sprint 2 | Playwright E2E (#36) |
| FR-09 | US-04 | Side-by-side multilingual viewer | #18 | Sprint 2 | Playwright E2E (#36) |
| FR-10 | US-08 | Cross-border document comparison | #24 | Sprint 3 | Playwright E2E (compare.spec.ts) |
| FR-11 | US-09 | Secure document sharing via Matrix | #23 | Sprint 3 | exchange.py (gated) |
| FR-12 | US-05 | Glossary API for term lookup | #32 | Sprint 2 | test_glossary_*.py |
| FR-13 | — | Health check endpoints | #8 | Sprint 1 | tests/unit/test_demo_pipeline.py |
| FR-14 | US-03 | EN/DE/FR language support | #14, #25 | Sprint 2, 3 | test_translation_accuracy.py |
| FR-15 | US-13 | Citation-grounded conversational guidance | — | Current | test_chat.py, Playwright chat E2E |
| NFR-01 | US-12 | Post-MVP production query latency ≤ 5s | #8, #16, #166 | Sprint 3 | ✅ k6: 141 iters, p95 6.94s |
| NFR-02 | US-12 | 50 concurrent users, <1% errors | #28, #166 | Sprint 3 | ✅ k6: 652 iters, 0.00% errors |
| NFR-03 | — | All LLM calls via AI Gateway | #6 | Sprint 1 | CI REM-8 grep |
| NFR-04 | US-07 | Ephemeral document processing | #26 | Sprint 1 | Architecture (Pyodide) |
| NFR-05 | US-07 | GDPR Article 5 data minimisation | #26 | Sprint 1 | GDPRConsentMiddleware |
| NFR-06 | US-04 | WCAG 2.1 AA accessibility | #39 | Sprint 2 | axe-core/Lighthouse |
| NFR-07 | — | ≥ 70% backend test coverage | #34 | Sprint 1+ | 92% on commit 78950e5 |
| NFR-08 | — | CI gates on all PRs | CI pipeline | Sprint 1 | ci.yml (all pushes) |
| NFR-09 | US-12 | Cloudflare Pages CDN ≤ 3s load | #10, #28 | Sprint 3 | Datadog RUM (pending) |
| NFR-10 | US-09 | Matrix E2EE + TI-Messenger | #23 | Sprint 3 | Manual |
| NFR-11 | — | Capstone MVP live-RAG envelope | #166 | Accepted | ✅ ADR-017 accepted; k6 verified |
| NFR-T1 | US-03 | Translation latency ≤ 8s | #14 | Sprint 3 | Mocked (pending real API) |
| NFR-T2 | US-05 | Terminology consistency | #32 | Sprint 3 | Mock verified |

---

## 7. Verification and Validation

### 7.1 Test Strategy

The project follows a pyramid testing strategy with automated enforcement at every level:

| Level | Framework | Scope | Count |
|-------|-----------|-------|-------|
| E2E | Playwright | Full page journeys, cross-browser | 70 tests (63 chromium + 7 live) |
| Component | Storybook 8.6 + Chromatic | Isolated components, a11y enforcement | 29 stories |
| Integration | pytest | Translation accuracy, API contract, security | 58 tests |
| Unit | pytest + Vitest | Functions, services, API client | 1132 backend + 382 frontend |

**CI enforcement pipeline (`.github/workflows/ci.yml`):**
1. Ruff lint + format (zero warnings)
2. mypy type check
3. REM-8 security grep (blocks direct LLM URLs)
4. pytest with 70% coverage floor (actual: 83%)
5. Vitest (frontend unit tests)
6. Playwright (E2E)
7. Chromatic (visual regression + a11y)

### 7.2 Test Results Summary

| Category | Tests | Result | Evidence |
|----------|-------|--------|----------|
| Backend unit + integration | 1132 passed, 36 skipped | ✅ 83% coverage | `coverage.xml` (CI artifact) |
| Security hardening | 28 unit + 5 adversarial | ✅ 33/33 passing | `tests/security/` |
| Log sanitizer + input validation | 25 | ✅ All passing | `tests/unit/test_log_sanitizer.py` |
| Translation accuracy (mock) | 21 | ✅ All passing | `docs/testing/translation-test-cases.yaml` |
| Translation accuracy (real m2m100) | 23 | Gated | `TRANSLATION_INTEGRATION_TESTS=true` |
| OCR benchmark | 16 | ✅ 16/16 passing | `docs/testing/ocr-benchmark.md` |
| Frontend unit (Vitest) | 382 | ✅ 382/382 passing | CI artifact |
| Diff engine | 16 | ✅ 16/16 passing | `src/lib/__tests__/diff.test.ts` |
| Storybook + a11y | 29 stories | ✅ Zero violations | `docs/testing/a11y-report.md` |
| E2E (Playwright) | 70 | ✅ All passing | `playwright-report/` |
| Performance (k6, 10 VUs) | 141 iters | ✅ 0 errors, p95 6.94s | `docs/testing/performance-report.md §10` |
| Performance (k6, 50 VUs) | 652 iters | ✅ 0.00% errors, p95 7.70s | `docs/testing/performance-report.md §10` |

### 7.3 NFR Verification Evidence

| NFR | Evidence | Commit | Status |
|-----|----------|--------|--------|
| NFR-01 | k6 live run 2026-07-16: 141 iters, 0 errors, full-stream p95 6.94s | 5af38c1 | ✅ Verified |
| NFR-02 | k6 live run 2026-07-16: 652 iters, 0.00% errors @50 VUs, full-stream p95 7.70s | 5af38c1 | ✅ Verified |
| NFR-03 | CI REM-8 grep check (every push) | 78950e5 | ✅ CI-enforced |
| NFR-04 | Pyodide/WASM — no disk writes possible | Architectural | ✅ By architecture |
| NFR-05 | GDPRConsentMiddleware + AuditLogMiddleware | 78950e5 | ✅ Implemented |
| NFR-06 | axe-core 33/33 violations resolved, zero suppressed | 78950e5 | ✅ Verified |
| NFR-07 | 83% total coverage (exceeds 70% target) | 0804e79 | ✅ Exceeded |
| NFR-08 | `.github/workflows/ci.yml` — all jobs passing | 78950e5 | ✅ Implemented |
| NFR-09 | Datadog RUM Core Web Vitals | — | ⏳ Pending evidence |
| NFR-10 | Manual Matrix E2EE verification | — | ⏳ Pending Sprint 3 |
| NFR-11 | Accepted Capstone MVP acceptance envelope | k6 2026-07-16 | ✅ Verified |
| NFR-T1 | Mocked ~1.5s per block (pending real API k6) | — | ⏳ Partial evidence |
| NFR-T2 | Mock evidence complete (glossary enforcement) | — | ✅ Mock verified |

**NFR-11 Capstone MVP Acceptance Criteria:**
1. Warm the deployed pipeline using health endpoints
2. Run 15 shared English, German, and French search fixtures sequentially (1 VU)
3. Record 0 user-visible failures (no non-200, no SSE `error`, no missing `done`)
4. Full-stream p95 ≤ 15 seconds after warm-up
5. One quality gate per supported language (citations from real Hindsight bank)
6. Record cold-start timing separately
7. NFR-11 does not replace NFR-01/NFR-02 production targets

---

## 8. Risk Analysis

Unified risk register consolidating risks from use-case.md, design-and-testing.md, and the GDPR compliance report.

| ID | Risk | Probability | Impact | Severity | Affected Reqts | Mitigation | Residual |
|----|------|------------|--------|----------|---------------|------------|----------|
| R-01 | Scope creep — too many features | High | High | Critical | All | Ruthless MVP scoping: 3 languages, document intelligence only, no healthcare in capstone | Controlled via sprint boundaries |
| R-02 | Translation quality for domain-specific terms | Medium | Medium | Moderate | FR-03, FR-04, NFR-T2 | BAML glossary extraction; post-translation replacement; terminology management | Model limitation acknowledged |
| R-03 | GDPR compliance complexity | Medium | Medium | Moderate | NFR-04, NFR-05 | Synthetic/public data for capstone; Cloudflare GDPR-compliant edge | 8/8 domains verified |
| R-04 | BabelDOC AGPL license propagation | Very Low | High | High | FR-03, ADR-012 | HTTP sidecar boundary; AST test prevents direct import | Isolated by architecture |
| R-05 | Hindsight service availability | Low | High | High | FR-05, FR-06 | Stub stream fallback; managed Cloud hosting (reversible to BYOC) | Fallback operational |
| R-06 | Prompt injection via uploaded PDFs | Medium | Medium | Moderate | Security | 3-layer defense (propella-1 + regex + delimiters); 33 tests | EU AI Act compliance mapped |
| R-07 | German OCR quality for Fraktur/old scripts | Medium | Medium | Moderate | FR-02 | Mistral primary + Tesseract fallback; benchmark validated | 250ms mean latency |
| R-08 | Limited access to European public documents | Low | Medium | Low | FR-05 | EUR-Lex openly available; 55 documents indexed | Corpus sufficient for MVP |
| R-09 | Team coordination across time zones | Low | Medium | Low | Process | Weekly sync + async collaboration (Notion, ClickUp) | Operational |
| R-10 | Cloudflare Students eligibility (non-US) | Medium | Low | Low | Infrastructure | Cloudflare free tier still generous; Render/Railway fallback | Free tier operational |
| R-11 | D1 data residency (EU compliance) | Low | Medium | Low | NFR-05 | D1 regional configuration; metadata-only storage | Acceptable for MVP |
| R-12 | Demo video quality | Low | High | Moderate | NFR-11 | Pre-recorded screen capture; static JSON fallback | Fallback available |

---

## 9. Out of Scope

The following items are explicitly excluded from the capstone MVP:

- Healthcare records and clinical documents (EHDS)
- Languages beyond EN, DE, FR
- FHIR parsing and clinical guideline indexing
- Real-time collaboration features
- Automatic form completion, submission, approval, or personalized legal advice
- Mobile applications
- Full records migration/interoperability layer
- Healthcare features (architecture supports it, capstone excludes it)

**Phase 2 (post-capstone) candidates:**
- 24-language support
- BabelDOC layout-preserving translation (sidecar already isolated)
- Local Docker self-hosted Hindsight (persistent storage + Cloudflare Tunnel)
- Apertus 8B model replacement for m2m100 (ADR-015)

---

## Appendix A: Architectural Constraints (Pyodide)

The EvidenceEU backend runs inside Cloudflare Python Workers (Pyodide/WebAssembly). These are **architectural constraints**, not defects. See ADR-004.

| Constraint | Detail | NFRs Affected | Workaround |
|-----------|--------|---------------|------------|
| No threading | `threading.Lock`, `threading.Thread` not functional. All concurrency is asyncio event-loop-based. | NFR-02 (concurrency model) | asyncio; horizontal isolate scaling |
| No socket / ssl | Python `socket` and `ssl` non-functional. All network I/O uses `httpx`. | NFR-01 (observability), NFR-03 | Custom httpx-based forwarders |
| No subprocess | `subprocess`, `os.fork`, `multiprocessing` unavailable. | NFR-02 | Not needed |
| No disk I/O | No persistent filesystem. All state is in-memory (ephemeral). | NFR-04 (compliance by architecture) | D1 for structured data |
| Cold start latency | First request to idle Worker takes 2–5s extra (V8 + Pyodide init). Excluded from steady-state p95. | NFR-01 | DemoWarmupMiddleware; pre-demo warm-up |
| No `sentry-sdk` | Uses `threading.Lock`, `socket`, `ssl`. | NFR-01 (observability) | `app/integrations/sentry.py` (custom forwarder) |
| No `ddtrace` | Uses `socket`, `threading`, native C extensions. | NFR-01 (observability) | `app/integrations/datadog.py` (custom forwarder) |
| No `lmnr` | Depends on grpcio, opentelemetry-sdk, threading. | NFR-01 (observability) | `app/integrations/laminar.py` (custom OTLP forwarder) |
| No `langfuse` | Depends on opentelemetry-sdk (threading in BatchSpanProcessor). | NFR-01 (observability) | `app/integrations/langfuse.py` (Basic Auth OTLP) |
| Limited stdlib | Some stdlib modules missing or shimmed. `sys.modules` injection required. | NFR-08 (deployment) | `worker.py` injection block |
| In-memory job store | `TranslationJob` objects in module-level `_jobs` dict. Lost on restart. | NFR-04 | Sprint 3 wires to D1 |

---

## Appendix B: Document Approval

| Role | Name | Review Date | Status |
|------|------|-------------|--------|
| Product Owner / Lead Developer | Mihai Chindriș | 2026-07-17 | ✅ Approved |
| Faculty Advisor | Dr. Robert Steele | — | ⏳ Pending review |

---

## Appendix C: Revision History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-05-27 | Mihai Chindriș | Initial scaffold from use-case.md, ADRs, GitHub issues |
| 1.1 | 2026-06-19 | Mihai Chindriș | Backend slice review: FR implementation notes, NFR evidence, Pyodide constraints |
| 1.2 | 2026-06-19 | Mihai Chindriș | FR-03 status correction (layout preservation PARTIAL), ISO 25010 column added |
| 1.3 | 2026-06-19 | Mihai Chindriș | FR-07 SSE events corrected, FR-05/06/10/11/12/14 notes, sentry-sdk/ddtrace constraints |
| 1.4 | 2026-06-26 | Mihai Chindriș | Translation accuracy criteria, NFR-T1/T2 added, QA harness merged |
| 1.5-draft | 2026-07-14 | Mihai Chindriș | Proposed NFR-11 Capstone MVP operating envelope |
| 1.6 | 2026-07-16 | Mihai Chindriș | User Story column in traceability matrix, sprint assignment fixes (FR-07, FR-13, NFR-06, NFR-01/02) |
| **2.0** | **2026-07-17** | **Mihai Chindriș** | **IEEE 29148 restructure: new §1 Introduction (purpose, scope, glossary, references), §2 Overall Description (product perspective, user characteristics, constraints, assumptions/dependencies), §3 reordered by feature, §4 External Interface Requirements (UI, API, external services, internal), §5 NFRs reorganized by ISO 25010 category, §6 Stakeholder Requirements with full traceability, §7 Verification & Validation, §8 Risk Analysis (unified register), Appendix A (Pyodide constraints moved), Appendix B (Document Approval), Appendix C (Revision History). All content from v1.6 preserved; no requirements added or removed.** |
| **2.1** | **2026-07-18** | **Mihai Chindriș** | **ADR-017 accepted: NFR-01/NFR-02 verified (local Docker self-host + async decoupling resolves Hindsight Cloud 429 and CPU wall); NFR-11 Capstone MVP acceptance envelope added; requirements.md §7.3 verification table updated; design-and-testing.md §5.5 updated with NFR-11 thresholds and MVP envelope.** |
