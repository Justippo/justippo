# Use Case: Multilingual Document Intelligence for Cross-Border Europe

**Date:** 2026-06-27
**Team:** Mihai Chindriș (sole submitter)
**Status:** v3.2 — Sprint 3 complete, v1.0.0 released + GDPR audit logging
**Capstone Program:** Master of Science in Software Engineering, Quantic School of Business and Technology

---

## TL;DR

An AI-powered platform that helps cross-border document users — migrants, legal professionals, compliance officers, and HR departments — search, understand, and translate bureaucratic, legal, and administrative documents across EU languages with formatting preserved. Think "DeepL that doesn't break your tables" combined with a multilingual research assistant for public-sector and regulatory paperwork. Phase 1 (capstone) targets legal/administrative/HR documents; Phase 2 (roadmap) extends the same multilingual engine into healthcare and the European Health Data Space (EHDS) as an "OpenEvidence for Europe" clinical decision-support layer.

---

## 1. Problem Statement

### The Gap

Europe has 24 official languages and one of the world's most mobile populations — yet cross-border document handling remains a manual, error-prone, expensive nightmare. No existing tool solves the full stack:

1. **Bureaucratic paperwork overload:** Migrants, expats, and cross-border workers constantly face foreign-language forms — residency permits, tax declarations, social-security registrations, university applications. DeepL translates the words but destroys the layout, making filled forms unusable by authorities.

2. **Legal and compliance fragmentation:** EU regulations (GDPR, AI Act, MiCA, DORA) are published in 24 languages but not consistently synchronized. Compliance officers in multinational companies must compare versions across languages to detect divergence. Law firms handling cross-border contracts manually reconcile clauses in German, French, and English.

3. **HR documentation chaos:** Multinational HR departments receive CVs, certificates, contracts, and reference letters in languages their recruiters don't read. Current tools translate content but lose formatting — tables, signatures, and official stamps become garbled.

4. **Document translation destroys structure:** DeepL, Google Translate, and Smartcat handle text well but annihilate document layout. Tables break, columns overflow, signatures disappear, and official stamps lose positioning. For bureaucratic and legal documents where structure carries legal meaning, this is a critical failure. This was experienced firsthand with German administrative documents.

5. **No unified cross-border document intelligence:** The market is split between generic translators (DeepL, Google), legal-specific tools (Legora — English-first), and healthcare-specific tools (OpenEvidence — US-only). No platform combines multilingual search, layout-preserving translation, and secure cross-border exchange for the _general_ cross-border document user.

### Who Feels This Pain

- **Primary:** Cross-border migrants and expats navigating foreign-language bureaucracy (residency, tax, healthcare registration, education)
- **Secondary:** Legal professionals and compliance officers reviewing EU regulations and cross-border contracts across languages
- **Tertiary:** HR departments at multinational companies processing foreign-language employee documentation

---

## 2. Proposed Solution

### Core Product: "EvidenceEU" (working name)

An AI-powered platform with three pillars:

#### Pillar 1: Multilingual Document Search & Intelligence (RAG-powered)

- Search across EU public-sector documents, regulatory filings, and administrative guidelines in any EU language
- AI-generated answers with source citations from official EU publications and national registers
- Query in your language, get results from documents written in others
- Powered by Vectorize Hindsight for agent memory and learning across sessions (4-way hybrid search: semantic + BM25 + graph + temporal)

#### Pillar 2: Document Translation with Formatting Preservation

- Upload bureaucratic, legal, or HR documents (PDFs, scans, forms) in any EU language
- Get translated documents that preserve the original layout, tables, columns, signatures, and formatting
- OCR support for scanned documents (Mistral OCR + Tesseract fallback)
- MVP uses Cloudflare Workers AI m2m100-1.2b for text-block translation (EN/DE/FR, Pyodide-safe)
- BabelDOC sidecar provides layout-preserving PDF translation (AGPL-isolated via HTTP boundary, ADR-012)
- Side-by-side bilingual viewer (/viewer) and document comparison with diff highlighting (/compare)

#### Pillar 3: Cross-Border Document Exchange & Intelligence

- Securely share and review translated documents across borders
- Structured data extraction from standardized forms (e.g., EU tax forms, social-security documents)
- Compliance tooling for cross-border regulatory alignment
- Matrix protocol for end-to-end encrypted, federated document exchange

---

## 3. Market Validation

### Comparable Companies

| Company      | Vertical        | Valuation | Geography              | Our Advantage                                                                     |
| ------------ | --------------- | --------- | ---------------------- | --------------------------------------------------------------------------------- |
| DeepL        | Translation     | ~$2B      | Global                 | We preserve document formatting + domain expertise + RAG intelligence             |
| Smartcat     | Translation/LSP | ~$200M    | Global                 | We combine translation + search + secure exchange in one platform                 |
| Legora       | Legal AI        | $5.5B     | Global (English-first) | We handle cross-border multilingual legal docs with layout preservation           |
| Harvey       | Legal AI        | $11B      | Global (English-first) | We preserve document formatting across 24 EU languages                            |
| OpenEvidence | Medical AI      | $12B      | US only, **blocked in EU** | Our multilingual architecture addresses a broader EU document intelligence market; OpenEvidence explicitly not available in EU/UK due to AI Act regulatory uncertainty |
| Luminance    | Legal AI        | ~$500M    | Global                 | We combine legal + administrative + translation in one platform                   |

### Regulatory Tailwinds

- **EU Digital Strategy:** The EU is pushing for cross-border digital public services (Single Digital Gateway) — creates forced demand for multilingual document handling
- **EU AI Act:** Classifies certain AI as "high-risk" — general document translation and search are lower-risk categories, reducing compliance burden
- **GDPR:** European data sovereignty requirements mean US tools can't easily serve this market. Our local deployment option and Matrix protocol address this from day one.
- **Competitor EU blockage:** OpenEvidence ($12B US medical AI) explicitly states on their website: "Due to mounting regulatory uncertainty regarding the treatment of AI systems in the European Union and the United Kingdom, including, among other rules, the EU Artificial Intelligence Act, OpenEvidence is not available in the European Union or the United Kingdom." This validates EvidenceEU's market positioning — we are built for the exact gap that blocks US competitors.

### Market Size

- EU cross-border migrant population: ~40M people (residency, tax, healthcare paperwork)
- Document translation services market: $50B+ globally, $28.86B in 2026 growing to $36.35B by 2030
- Legal AI market in Europe: rapidly growing, driven by EU AI Act compliance needs

---

## 4. Technical Architecture (MVP)

The system is built on a layered, edge-native architecture deployed entirely on Cloudflare:

| Layer                   | Component                                                 | Responsibilities                                                                                                 |
| ----------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Frontend**            | Next.js 14 App Router · Cloudflare Pages                  | Document search, upload, /viewer (side-by-side EN/DE/FR), /compare (diff highlighting), cross-border exchange UI |
| **Proxy Worker**        | TypeScript · Cloudflare Workers                           | Routes `/api/v1/*` to backend via Service Binding; D1 metadata binding                                           |
| **API Gateway**         | FastAPI · Python Worker (Pyodide)                         | GDPR consent middleware, SSE streaming, endpoint routing                                                         |
| **RAG Engine**          | Hindsight · LangChain                                     | 4-way hybrid search (vector + BM25 + semantic + keyword); glossary query expansion                               |
| **Document Processing** | Mistral OCR · Tesseract · propella-1 0.6B · BAML Glossary | Text extraction, document classification (18 properties, 57 languages), legal term extraction                    |
| **Translation Engine**  | m2m100-1.2b · Cloudflare Workers AI                       | EN↔DE↔FR translation with domain terminology management                                                          |
| **Secure Exchange**     | Matrix Protocol                                           | E2EE federated cross-border document exchange; TI-Messenger compatible                                           |
| **Storage**             | ChromaDB/Vectorize · SQLite/D1                            | Document embeddings, metadata, glossary, translation jobs                                                        |

### Tech Stack (Shipped)

| Category                    | Technology                                       | Role                                                            |
| --------------------------- | ------------------------------------------------ | --------------------------------------------------------------- |
| **Backend**                 | Python 3.12 · FastAPI · Pyodide                  | API layer, GDPR middleware, SSE streaming                       |
| **Frontend**                | Next.js 14 App Router · Cloudflare Pages         | Web UI — search, upload, /viewer, /compare, exchange            |
| **RAG**                     | Hindsight · LangChain                            | 4-way hybrid retrieval (vector + BM25 + semantic + graph)       |
| **Document Classification** | propella-1 0.6B · OpenEuroLLM                    | 18 properties · 57 languages · type/quality/language/safety/geo |
| **OCR**                     | Mistral AI + Tesseract fallback                  | PDF and scanned document text extraction                        |
| **Translation**             | m2m100-1.2b · Cloudflare Workers AI              | EN↔DE↔FR layout-preserving translation                          |
| **Glossary**                | BAML · ExtractGlossaryTerms                      | Type-safe legal term extraction; feeds RAG expansion            |
| **Secure Exchange**         | Matrix Protocol                                  | E2EE federated cross-border document exchange                   |
| **Infrastructure**          | Cloudflare Workers · D1 · Vectorize · AI Gateway | Edge compute, metadata store, embeddings, LLM proxy             |
| **CI/CD**                   | GitHub Actions (self-hosted Bun + Turborepo)     | lint → test → coverage → deploy (~2.5 min warm cache)           |

---

## 5. Capstone Scope & Requirements Alignment

### Capstone Handbook Requirements Checklist

| Requirement                            | How We Address It                                                                |
| -------------------------------------- | -------------------------------------------------------------------------------- |
| GitHub repository with documented code | Main project repo, shared with `quantic-grader`                                  |
| Deployed web application               | Cloudflare Pages (frontend) + Workers (API) — free tier via Students program     |
| Agile task board (Trello/Scrum Board)  | Notion board (public) + ClickUp (team) — 58 cards, 13 user stories, 4 sprint lists |
| Design and testing document            | Architecture decisions, patterns, deployment options, all testing documented     |
| CI/CD tools                            | GitHub Actions for automated testing and deployment                              |
| At least 3 sprints                     | Planned: 3 formal sprints (see below)                                            |
| 15-20 min recorded demo                | All 4 members present on camera with government ID, screen share of deployed app |
| Sprint review recordings               | Demo recording at end of each sprint for Product Owner                           |

### What We Delivered (MVP — Sprint 3 Complete ✅)

1. **Working RAG search engine** over EU public documents in EN/DE/FR with SSE streaming and source citations ✅
2. **Document translation** (m2m100-1.2b, EN/DE/FR) with glossary enforcement and terminology consistency ✅
3. **Side-by-side bilingual viewer** (/viewer — DocumentPanel with ARIA, lang attributes, WCAG 2.1 AA) ✅
4. **Cross-border document comparison** (/compare — LCS diff engine, mode toggle, accessibility) ✅
5. **Matrix E2EE secure document exchange** (/exchange — federated, TI-Messenger compatible) ✅
6. **GDPR compliance** (8/8 domains verified — consent middleware, Article 30 audit log with pseudonymization, PII sanitizer) ✅
7. **3-layer prompt injection defense** (propella-1 + 16 regex patterns + delimiters + audit log, 33 tests) ✅
8. **Design and testing document** v3.0 — 11 sections, full traceability matrix ✅
9. **Deployed on Cloudflare Pages + Workers** — v1.0.0 released ✅
10. **1132 backend tests (83% coverage), 382 Vitest, 70 Playwright E2E** ✅

### What We Will NOT Build in Capstone

- Full 24-language support (start with 3, prove the architecture works)
- Healthcare records and EHDS-specific features (out of capstone scope)
- Full 24-language support (EN/DE/FR for capstone, extensible architecture)
- Mobile apps
- Full records migration/interoperability layer

### Sprint Plan (3 Sprints — Completed)

| Sprint       | Period          | Focus                                                                     | Outcome                                                               |
| ------------ | --------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| **Sprint 1** | May 18 – Jun 14 | Cloudflare infrastructure, RAG pipeline, EU document corpus               | ✅ Working RAG search, OCR, SSE streaming, CI/CD                      |
| **Sprint 2** | Jun 15 – Jun 28 | Translation pipeline, frontend, Storybook, performance testing, licensing | ✅ EN/DE/FR translation, Playwright E2E, AGPL open core, 83% coverage |
| **Sprint 3** | Jun 29 – Jul 22 | Security hardening, GDPR, viewer/compare, Matrix, production deploy       | ✅ v1.0.0 released, all 8 GDPR domains, 33 security tests, demo ready |

### Roles & Responsibilities

| Role              | Responsibilities                                                                               |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| **Product Owner** | Product vision, user stories, sprint priorities, stakeholder communication                     |
| **Lead Developer** | RAG engine, backend architecture, Cloudflare infrastructure, CI/CD, Vectorize integration, frontend development, document translation pipeline, OCR/formatting preservation, UX design, testing framework, documentation |

### User Stories (Product Backlog)

The following 13 user stories define the EvidenceEU product backlog. Each follows the standard "As a... I want... So that..." template with acceptance criteria. Stories are prioritized by sprint assignment; all are complete.

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

**Traceability:** Each user story maps to one or more Functional Requirements (FR-01 through FR-15) or Non-Functional Requirements (NFR-01 through NFR-11) defined in the SRS (`docs/requirements.md`). The full FR → US mapping is maintained in the Requirements Traceability Matrix (§4 of `docs/requirements.md`).

**Board links:** [Notion Scrum Board](https://interesting-crawdad-5e0.notion.site/38cbf1cf330681b484d0c68d7fc9505c?v=38cbf1cf330680d3b7db000c67ca4e8d) (primary) | [ClickUp Board](https://app.clickup.com/90121672895/v/f/901211405830/90127249325) (legacy, auto-synced from Notion)

---

## 6. Competitive Advantages

1. **Europe-native:** Built for European multilingual fragmentation from day one — not a translation layer bolted onto an English product
2. **Document intelligence-first:** Translation + formatting preservation + search = unique capability no competitor combines
3. **Immediate addressable market:** Cross-border migrants, legal professionals, and HR departments exist now and feel the pain now — no 12-18 month enterprise sales cycles
4. **Open regulatory window:** EU Digital Strategy and Single Digital Gateway create forced demand for cross-border document handling
5. **No incumbent in general cross-border docs:** DeepL does translation but no search or exchange; Legora/Harvey are English-first legal tools; no one serves the general cross-border document user
6. **Local deployment option:** Addresses GDPR-sensitive markets (especially Germany) with on-premise LLM support
7. **Agent memory:** Vectorize Hindsight enables the system to learn and improve from interactions over time
8. **Cloudflare-native infrastructure:** Edge deployment via Cloudflare Pages + Workers means global latency, automatic scaling, and zero server management — plus free tier for students
9. **EU regulatory moat:** US competitors like OpenEvidence are explicitly blocked from the EU market due to AI Act regulatory uncertainty — EvidenceEU is built for this exact gap

---

## 7. Risks & Mitigations

| Risk                                          | Likelihood | Impact | Mitigation                                                                                                                                        |
| --------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scope creep (too many features)               | High       | High   | Ruthless MVP scoping — 3 languages, document intelligence only, no healthcare features in capstone                                                |
| Translation quality for domain-specific terms | Medium     | Medium | Start with general bureaucratic/legal language (lower bar than clinical); iterate with user feedback; terminology management via Hindsight memory |
| GDPR compliance complexity                    | Medium     | Medium | Use synthetic/public data for capstone, local LLM deployment option, Cloudflare's GDPR-compliant edge infrastructure                              |
| Limited access to European public documents   | Low        | Medium | EU publications are openly available; start with EUR-Lex, national registers, and openly published guidelines                                     |
| Team coordination across time zones           | Low        | Medium | Weekly sync + async collaboration tools (Slack)                                                                                                   |
| BabelDOC limitations long-term                | Medium     | Low    | Evaluate alternatives during Sprint 2; modular architecture allows swapping                                                                       |
| Cloudflare Students eligibility (non-US)      | Medium     | Low    | Cloudflare free tier still generous; fallback to Render/Railway if Students program unavailable                                                   |

---

## 8. Advisory Network & External Resources

| Contact               | Organization                        | How They Can Help                                                                                 | Relationship                                                                                     |
| --------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Chris Latimer**     | Vectorize (Hindsight)               | RAG pipeline architecture, agent memory setup, hybrid search implementation                       | Mihai's 1st-degree LinkedIn connection; previously invited Mihai to contribute to Hindsight repo |
| **Maria Sukhareva**   | AI Realist (independent researcher) | Applied AI research guidance, no-hype technical assessment, NLP expertise, German market insights | Mihai's 1st-degree LinkedIn connection; AI researcher based in Nuremberg, Germany                |
| **Legora team**       | Legora ($5.5B legal AI)             | Legal AI landscape insights; Legal AI Scholars Program for academic institutions                  | Potential outreach via their academic program (legora.com/academic)                              |
| **Dr. Robert Steele** | Quantic Faculty                     | Capstone guidance, academic requirements, project scoping                                         | Faculty advisor                                                                                  |

### Research Component

This project has a genuine research dimension:

- **Multilingual document RAG:** How to build retrieval systems that work across languages with domain-specific terminology
- **Document layout preservation in translation:** An unsolved problem at the intersection of OCR, NLP, and layout analysis
- **Cross-border secure document exchange:** Practical implementation of federated, E2EE document sharing via Matrix protocol
- Maria Sukhareva's applied AI expertise and research network can provide iterative guidance on these aspects

---

## 9. Previously Discussed Alternative: Odoo AI Integration

During the team meeting on May 6, 2026, an AI-powered business intelligence module for Odoo was proposed as an alternative direction. Both options were evaluated and the EvidenceEU direction (cross-border document intelligence) was selected for the following reasons:

- **Faster time-to-validation:** Cross-border document users feel pain today and can be reached without enterprise sales cycles
- **Research depth:** Multilingual RAG + layout preservation + secure exchange offer stronger academic research dimensions for the capstone
- **Technical ambition:** The architecture (FastAPI, Hindsight, BabelDOC, Matrix, Cloudflare) demonstrates a broader range of AI engineering techniques
- **Extensible architecture:** The Cloudflare-native edge stack, multilingual RAG, and Matrix protocol are designed to scale to new document domains and languages

The Odoo concept was evaluated and rejected during Sprint 1 planning — the team confirmed the cross-border document use case is stronger for the capstone.

---

## 11. Branding

- **Name:** EvidenceEU (confirmed)
- **Deployed at:** [https://evidence-eu-frontend.pages.dev](https://evidence-eu-frontend.pages.dev)
- **Domain:** `evidence.eu` is taken. `EvidenceEU` as the platform name is sufficient for capstone scope. Domain registration deferred to post-graduation commercial launch.

---

## 12. Video & Presentation

A **15-20 minute recorded demo** is required for capstone submission with:

- All team members present and visible on camera with government-issued ID
- Screen share of the deployed, working application
- Demonstration of all functional capabilities



---

## 13. Resources & References

- [OpenEvidence](https://www.openevidence.com/) — US clinical AI benchmark ($12B valuation); **explicitly blocked in EU/UK due to AI Act regulatory uncertainty**
- [Harvey AI](https://www.harvey.ai/) — Legal AI benchmark ($11B valuation)
- [Legora](https://legora.com/) — Legal AI platform ($5.5B valuation, Swedish/YC-backed)
- [DeepL](https://www.deepl.com/) — Translation benchmark (~$2B valuation)
- [Smartcat](https://www.smartcat.com/) — Translation management platform
- [EHDS Regulation](https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en) — EU cross-border health data mandate
- [BabelDOC](https://github.com/funstory-ai/BabelDOC) — Open source document translator
- [Vectorize Hindsight](https://github.com/vectorize-io/hindsight) — Agent memory system (open source)
- [BAML / AI That Works](https://boundaryml.com/podcast/2026-04-07-sse-streaming) — SSE streaming architecture reference
- [Cloudflare for Students](https://www.cloudflare.com/students/) — Free developer platform for students
- [Capstone Handbook](https://quantic.edu) — MSSE Capstone requirements and rubric
- [AI Realist (Maria Sukhareva)](https://msukhareva.substack.com/) — Applied AI research newsletter

---

_Version 3.2 — Sprint 3 complete. v1.0.0 released 2026-06-27. GDPR audit logging added 2026-06-29. Cross-border document intelligence platform for EU migrants, legal professionals, and HR departments._
