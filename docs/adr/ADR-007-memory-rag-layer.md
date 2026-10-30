# ADR-007: Memory / RAG Layer — Single-Vendor Discipline (Hindsight)

**Date:** 2026-05-30
**Status:** Accepted
**Deciders:** Mihai Chindriș, team
**Context source:** Evaluation triggered by survey of Letta, Cognee, and Hindsight Cloud's startup program.

---

## Context

EvidenceEU's core technical need is **document retrieval** — hybrid search over a corpus of EU public documents, returning passages with citations (FR-05, FR-06). During Sprint 0 planning, three "memory" products were evaluated:

| Product | Category | What it solves |
|---------|----------|----------------|
| **Hindsight / Vectorize** | Document RAG | Hybrid search/retrieval over a corpus |
| **Cognee** | Knowledge-graph memory | Entity/relationship extraction + graph recall |
| **Letta (MemGPT)** | Stateful agent memory | Persistent per-user agent identity that learns across sessions |

These are frequently conflated as interchangeable "memory" tools. They are not. The risk being guarded against here is **vendor sprawl**: under compressed 2-3-2 week sprints, every added integration is a credential, a test mock, a dependency, and a demo explanation.

---

## Decision

1. **Hindsight is the single RAG/memory layer for the MVP.** It matches the core retrieval need and is already the basis of ADR-001.
2. **Letta is rejected.** EvidenceEU is a document-intelligence platform, not an agent-with-persistent-user-memory product. Stateful agent memory solves a problem EvidenceEU does not have.
3. **Cognee is deferred, not adopted.** Its knowledge-graph capability overlaps with the potential REBEL/knowledge-graph collaboration with Dan Browne (under separate evaluation). Adopting Cognee *and* exploring Dan's KG *and* running Hindsight would be three overlapping vendors for one feature.
4. **Graph memory is deferred to a post-MVP enhancement** (see honest assessment below).

---

## Is graph memory actually needed? (Honest assessment)

**For the MVP: No. Post-MVP for the legal domain specifically: genuinely valuable — more so than for a generic corpus.**

Research finding (2026): GraphRAG and vector RAG solve *different* problems. Vector RAG excels at precise answers from document internals; GraphRAG excels at **relationships across a document collection**. Critically, the legal/regulatory domain is one of the strongest cases for graph RAG — there is dedicated academic work (e.g. *"Graph RAG for Legal Norms: A Hierarchical and Temporal Approach"*, arXiv 2505.00039) because legal documents are densely cross-referential and temporal:

- "Regulation X **amends** Directive Y"
- "Article 5 **references** GDPR Article 17"
- "This provision **supersedes** the 2016 version"

Pure vector search misses these structural/temporal relationships. So graph memory **would** meaningfully improve EvidenceEU — *eventually*.

**But not for the capstone MVP, because:**
- The MVP must first prove the *core* loop: upload → OCR → translate → retrieve with citations. Vector RAG (Hindsight) delivers this.
- Graph construction adds significant build + validation cost that the 2-3-2 sprint compression cannot absorb.
- Graph RAG's value scales with corpus size and cross-reference density; the MVP's initial corpus (50+ docs/language) is too small to demonstrate clear payoff.

**Conclusion:** Graph memory is a real, domain-appropriate Phase 2 enhancement — not MVP scope. If pursued, it should come via the Dan Browne KG-technique collaboration (pending code review), not by adding Cognee as a vendor.

---

## Alternatives Considered

| Option | Verdict |
|--------|---------|
| Hindsight only | ✅ Chosen — single layer, matches core need |
| Hindsight + Letta | ❌ Letta solves a non-existent problem (per-user agent memory) |
| Hindsight + Cognee | ❌ Vendor overlap for a non-MVP feature |
| Replace Hindsight with Cognee | ❌ Cognee is KG-first; EvidenceEU's primary need is retrieval, not graph |
| Self-host Letta/Cognee (both OSS) | 🟡 Free, but irrelevant — neither belongs in MVP scope |

---

## Consequences

- **Positive:** Tight integration surface; one RAG vendor to learn, mock, and demo. Faster path through compressed sprints.
- **Positive:** Clear, defensible architecture story for graders — single retrieval layer, deliberate scoping.
- **Positive:** Graph-RAG path stays open via the Dan collaboration, with honest reasoning recorded for "future work" in the Design & Testing doc.
- **Neutral:** Hindsight Cloud's startup program ($15K credits) is **deferred to post-incorporation** — its 3-month credit clock and "incorporated company / building agents" eligibility make applying during the capstone premature. Student accommodation to be sought directly from Chris Latimer instead.

---

## Sprint 3 Note — propella-1 Metadata Enrichment

Sprint 3 adds `ellamind/propella-1-0.6b` as a non-blocking document classification sidecar before Hindsight ingestion. This does **not** add a parallel memory store; it enriches the existing Hindsight metadata with `doc_type`, `lang_code`, `quality_score`, and `safety_flags` so retrieval/filtering can use consistent document-level annotations. The sidecar is feature-flagged with `PROPELLA_ENABLED` and gracefully falls back when unavailable.

## Related

- [ADR-001](ADR-001-rag-vector-db.md) — RAG vector store (ChromaDB dev / Vectorize prod)
- Potential future ADR — Knowledge-graph augmentation (pending Dan Browne code review)
- `conversations-tracker.md` — Chris Latimer (Vectorize/Hindsight) outreach
