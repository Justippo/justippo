# ADR-005: Domain Glossary & Terminology Management

**Date:** 2026-05-26
**Status:** Accepted
**Deciders:** Mihai Chindriș, team
**Context source:** Feedback from [Marketa Cizmar](https://www.linkedin.com/in/marketa-cizmar/) (Co-founder, [Tolgee](https://tolgee.io)) — May 2026

---

## Context

Legal and administrative documents contain domain-specific terminology where a near-synonym can change the legal meaning of a document entirely. Examples:

- DE: `Aufenthaltstitel` → EN: "residence permit" (not "residence card", not "stay title")
- FR: `acte authentique` → EN: "notarial deed" (not "authentic act")
- DE: `Vollmacht` → EN: "power of attorney" (not "authorization", not "proxy")

BabelDOC handles layout preservation well but does not enforce domain-specific term consistency by default. Without a controlled vocabulary layer, the same term can be translated differently across pages of the same document — which undermines legal validity.

This also affects RAG recall: if indexed documents use inconsistent terminology, cross-language queries will miss matches.

---

## Decision

Implement a **lightweight domain glossary layer** in Sprint 2:

1. **Storage:** A `glossaries` table in Cloudflare D1 (production) / SQLite (dev):
   ```sql
   CREATE TABLE glossaries (
     id INTEGER PRIMARY KEY,
     term TEXT NOT NULL,
     source_lang TEXT NOT NULL,       -- e.g. "de"
     target_lang TEXT NOT NULL,       -- e.g. "en"
     preferred_translation TEXT NOT NULL,
     domain TEXT NOT NULL,            -- "legal" | "administrative" | "medical" (Phase 2)
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

2. **Injection:** Pass glossary terms to BabelDOC at translation time via its custom glossary API. Terms in the glossary take priority over the model's default translation.

3. **Seed data:** Pre-populate with ~50 high-frequency legal/administrative terms for EN↔DE and EN↔FR at Sprint 2 start. Source: EUR-Lex multilingual glossary (public domain).

4. **API endpoint:** `GET /api/v1/glossary?domain=legal&source=de&target=en` — exposes the term base for future UI integration.

5. **Phase 2 extension:** Add `medical` domain terms when EHDS/clinical features are activated. Architecture supports it via the `domain` column — no schema change needed.

---

## Alternatives Considered

| Option | Verdict |
|--------|---------|
| **Tolgee** | Built for software string localization, not document translation. No OCR, no PDF pipeline. Rejected. |
| **OmegaT translation memory** | Powerful but requires a separate service, Java runtime, and manual management. Overkill for capstone. |
| **No glossary (rely on BabelDOC defaults)** | Risk: inconsistent terminology across a document damages legal validity. Rejected. |
| **Azure Translator glossary API** | Paid, vendor lock-in, doesn't integrate with BabelDOC pipeline. Rejected. |

---

## Consequences

- **Positive:** Consistent legal terminology across all translations; improved RAG cross-language recall; Phase 2 medical extension path already built-in.
- **Positive:** Differentiates EvidenceEU from generic translation tools (Harvey, Legora, DeepL) — none expose domain glossary management.
- **Negative:** ~1 day additional Sprint 2 implementation effort.
- **Neutral:** Glossary quality depends on seed data — start small (50 terms), grow over time.

---

## Related

- [ADR-002](ADR-002-translation-babeldoc.md) — BabelDOC as translation engine
- [ADR-001](ADR-001-rag-vector-db.md) — RAG vector store (glossary improves recall)
- GitHub Issue: #32 — Domain glossary management
