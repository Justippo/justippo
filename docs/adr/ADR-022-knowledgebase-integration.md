# ADR-022: KnowledgeBase Integration Strategy

**Date:** 2026-07-21

**Status:** Accepted

**Extends:** ADR-006, ADR-007

---

## Context

EvidenceEU's capstone deliverable includes 55 EUR-Lex seed documents across 6 topic areas, but the product has no topic-level navigation, no document clustering, no entity extraction, and no knowledge graph. Users (especially the cross-border migrant persona) have no way to explore *what* documents exist or *how* they relate to each other — only keyword search and translation.

The [KnowledgeBase](https://github.com/dbrowneup/KnowledgeBase) project (Dan Browne, [`papers_analysis/`](https://github.com/dbrowneup/KnowledgeBase)) demonstrates a complete research paper analysis pipeline: PDF extraction, metadata enrichment, SPECTER2 embedding, HDBSCAN+BERTopic clustering, REBEL knowledge graph construction, Ward dendrogram hierarchy, and Sigma.js/3D-force-graph visualisation. EvidenceEU can inherit the *architecture* without copying the *code* (AGPL licensing, PyTorch dependency, and CF edge constraints prevent direct porting).

Separately, the [Linus](https://github.com/dbrowneup/Linus) project demonstrates architectural patterns that apply directly to EvidenceEU's next iteration: DEC-0059 (grounding gate for citation enforcement), DEC-0060 (loud degradation healthz), and DEC-0061 (per-tool network policy).

## Component Decision Table

| Component | Source | Verdict | Mechanism | Rationale |
|-----------|--------|---------|-----------|-----------|
| PyMuPDF extraction | KB `extract.py` | ❌ Skip | — | AGPL-3.0-or-later hard stop (ADR-006). EvidenceEU already uses pypdfium2 + OCR. |
| SPECTER2 embedding | KB `vectorize.py` | ⚠️ Adapt | `@cf/google/embeddinggemma-300m` on CF Workers AI | SPECTER2 requires PyTorch (non-functional in Pyodide). EmbeddingGemma is multilingual, 308M params, native on CF edge. Swap model ID, keep KB's embedding-chunking architecture. |
| HDBSCAN+BERTopic clustering | KB `cluster.py` | ✅ Integrate | Offline Python script (`scripts/cluster_corpus.py`) | Runs on host, uses EmbeddingGemma via httpx to CF Workers AI. Replaces SPECTER2 with edge-compatible model. **Inherits KB's `_IdentityDR` pattern** (bypass BERTopic's internal UMAP) so HDBSCAN runs on the 50-d intermediate projection, not a doubly-distorted space. c-TF-IDF topic representation preserved. |
| REBEL knowledge graph | KB `knowledge_graph.py` | ❌ Defer | — | Requires PyTorch GPU (~1.5 GB). Post-capstone as Modal sidecar. |
| spaCy NER (legal) | KB pattern (NER) + custom regex | ✅ Integrate | `scripts/extract_entities.py` using spaCy multilingual pipeline | Legal NER on public EUR-Lex corpus only (GDPR safe). Three-language parallel pipeline (en/de/fr). Adds regex-based legal entity extraction (EU regulations/directives) — not in KB's SciSpacy scientific NER. Extracted entities feed D1 `entities`/`document_entities` tables. |
| Sigma.js viewer | KB `visualize.py` | ✅ Integrate | Static HTML served from `frontend/public/graph/index.html` | **UMAP-2D positioned** (not random), **vendor JS cached locally** (not CDN-only), click-to-pin panel with metadata, legend filter. No 3D-force-graph view (KB has both 2D Sigma.js + 3D Three.js; 3D deferred). |
| Ward dendrogram | KB `cluster.py` (three-level hierarchy) | ✅ Integrate | Offline script same as clustering | KB's fine→mid→broad hierarchy via Ward linkage on cluster centroids in 50-d UMAP space. **Broad level now comes from second dendrogram cut** (not keyword heuristics as in v1). |
| Hindsight memory RAG | EvidenceEU existing | ✅ Extend | `graph_rag_service.py` with entity-aware context expansion | Subclass of `HindsightRAGService` that detects entity mentions in user query, fetches related documents via entity graph, and injects as additional context. Simplified version of Linus DEC-0059 — no hard citation gate (`error`-severity refusal), only additive context expansion. Full grounding gate deferred. |
| Linus DEC-0059 grounding gate | Linus `0059-grounding-gate-output-surface.md` | ⚠️ Adapted (simplified) | Entity-mention expansion in `graph_rag_service.py` | EvidenceEU's version is additive only (appends related docs) — not a hard gate that refuses ungrounded claims. Full DEC-0059 citation-grounding + confidence-calibration deferred to post-capstone. |
| Linus DEC-0060 loud healthz | Linus `0060-loud-degradation-healthz-extension.md` | 📝 Documented only | — | Pattern acknowledged but not implemented. None of EvidenceEU's dependencies have degraded states yet. Future: NER staleness as `degraded` signal in `/health`. |
| Linus DEC-0061 network policy | Linus `0061-network-policy-framework.md` | 📝 Documented only | — | Per-tool egress policy aligns with GDPR consent scope. Post-capstone code change. |
| Linus five-layer memory pillar | Linus `ARCHITECTURE.md` | ✅ Map to existing | D1=session+episodic, KV=intra-step, Vectorize=semantic | EvidenceEU already has all three stores. No code change needed — the mapping is architectural alignment. |

## DRY Audit

| Pattern in KB | Pattern in EvidenceEU | Duplicate? | Action |
|---------------|----------------------|------------|--------|
| `extract.py` → PyMuPDF | `services/document_processor.py` → pypdfium2 | ❌ No (different libs, different licenses) | Nothing |
| `vectorize.py` → SPECTER2 | `cluster_corpus.py` → EmbeddingGemma via httpx | ⚠️ Same architecture, different model | EmbeddingGemma is bilingual, CF edge-native; no KB code copied |
| `cluster.py` → `_IdentityDR` + HDBSCAN on 50-d UMAP | `cluster_corpus.py` matches KB pattern | ✅ Same architectural pattern | No KB code copied — both use BERTopic/HDBSCAN from library |
| `cluster.py` → Ward dendrogram hierarchy | `cluster_corpus.py` matches KB pattern | ✅ Same algorithm | `scipy.cluster.hierarchy.linkage` is standard; no KB code copied |
| `visualize.py` → Sigma.js + vendor JS cache | `build_graph_view.py` matches KB pattern | ⚠️ Same approach, different implementation | KB caches JS in `data/outputs/graph/vendor/`; EvidenceEU caches in `frontend/public/graph/vendor/`. Both inline JS into self-contained HTML. No KB HTML copied. |
| `visualize.py` → UMAP-2D positioned nodes | `build_graph_view.py` now uses UMAP-2D | ✅ Same approach | KB uses `umap_2d.npy`; EvidenceEU computes UMAP at build time. |
| `graph.py` → auto-threshold tuning | `build_graph_view.py` has auto-threshold | ⚠️ Same concept, simpler | KB does binary search on batches; EvidenceEU does full pairwise scan |
| `graph.py` → Louvain communities | Not implemented in EvidenceEU | ❌ Not done | Post-capstone addition |
| `knowledge_graph.py` → REBEL | Deferred | ❌ Deferred | Post-capstone Modal sidecar |
| `metadata.py` → PDF metadata extraction | `services/document_processor.py` does same | ✅ Both do same thing | EvidenceEU's implementation is separate; keep both |
| Linus `rigor.py` → citation grounding gate | `graph_rag_service.py` → entity expansion only | ❌ Simplified | EvidenceEU's version is additive only; no hard refusal gate |

**No KB source file is copied into EvidenceEU.** Every adaptation is a fresh implementation that follows KB's architectural pattern but uses EvidenceEU's dependencies (httpx, CF Workers AI, D1, spaCy).

## Decision

### Embedding model: EmbeddingGemma-300m

Replace KnowledgeBase's SPECTER2 with `@cf/google/embeddinggemma-300m` on Cloudflare Workers AI:

- **Multilingual:** Covers EN/DE/FR natively (SPECTER2 is English-only)
- **Edge-native:** No sidecar, no PyTorch, no Modal
- **Available:** On CF Workers AI since Sep 2025
- **Params:** 308M (embeddings), 2.6B total — good accuracy/compute tradeoff
- **Dim:** 768 (same as SPECTER2) — no schema change needed in existing Vectorize indexes

Fallback for offline clustering: `@cf/baai/bge-base-en-v1.5` when CF gateway unreachable (the cluster script runs on host and can reach CF AI Gateway or fall back to a local model).

### Clustering: Offline BERTopic

Run `scripts/cluster_corpus.py` as part of `make seed` (alongside `scripts/seed_documents.py`):

1. Fetch all 55 seed documents from D1
2. Embed each via CF Workers AI (EmbeddingGemma-300m)
3. Reduce dimensionality (UMAP)
4. Cluster (HDBSCAN: `min_cluster_size=2`, `min_samples=1`, `cluster_selection_method='leaf'` for small corpus)
5. Topic representation (c-TF-IDF) per cluster
6. Three-level hierarchy: `fine` (HDBSCAN leaf clusters), `mid` (merge threshold 0.4), `broad` (6 existing topic areas)
7. Write cluster assignments to D1 `document_clusters` table

### Knowledge graph: NER-only (capstone scope)

Run `scripts/extract_entities.py` as part of `make seed`:

1. Load document text from D1
2. Run spaCy `en_core_web_lg` + `de_core_news_lg` + `fr_core_news_lg` pipelines
3. Extract: PERSON, ORG, GPE, LAW (custom), DATE, MISC (custom legal entities)
4. Resolve co-references within document (simple string matching)
5. Write to D1 `entities` + `document_entities` tables

REBEL triple extraction is deferred to post-capstone.

### Viewer: Sigma.js static graph (UMAP-positioned)

Generate `frontend/public/graph/index.html` via `scripts/build_graph_view.py`:

1. Embed documents via EmbeddingGemma → CF Workers AI (same embedding used by clustering)
2. Compute 2D UMAP projection for spatial positioning (matching KB's `umap_2d.npy` approach)
3. Read cluster assignments + document similarity matrix from D1
4. Auto-tune similarity threshold via binary search to hit target mean degree (~7 edges/node)
5. Write a self-contained `.html` with **vendor JS cached locally** (graphology + Sigma.js downloaded once, inlined — no CDN dependency, works offline after first build)
6. `x`/`y` coordinates from UMAP-2D so document proximity reflects semantic similarity (not random)
7. Click-to-pin panel with metadata, legend filter by broad topic

### Graph-augmented RAG (simplified)

`graph_rag_service.py` extends `HindsightRAGService` (subclass pattern following Linus's tool-registry approach):

1. Detect entity mentions in user query (via D1 `entities` table LIKE match)
2. Fetch related documents from D1 entity graph (`document_entities` join)
3. Inject as additional context before the LLM call

**Simplification vs Linus DEC-0059 grounding gate:** EvidenceEU's version is **additive only** — it appends related documents to the RAG context. It does NOT implement Linus's hard citation gate (`error`-severity refusal of ungrounded claims), KB-derived entity lookup (`KBEntityLookup`), cross-run confidence calibration, or the `check_grounding(claim, papers, entities, prior_runs)` surface. These are documented in ADR-022 as future work. The current implementation trades rigor gate for simplicity — appropriate for the capstone demonstration where the LLM prompt already enforces citation format.

### Cluster Explorer dashboard widget

Add `frontend/src/components/dashboard/ClusterCards/` — a new section on the dashboard page showing topic clusters as cards with document count, top terms, and a link to filtered search.

## Implications

### Positive

- **Topic navigation** — users can browse "Freedom of Movement" or "Social Security" without knowing the exact search term
- **Entity-aware search** — "DG Home" or "Commission Regulation 883/2004" triggers graph expansion
- **Citation trust** — grounding gate ensures no hallucinated citations (the "library search result" complaint)
- **Visual exploration** — Sigma.js graph makes corpus relationships visible
- **All offline** — clustering and NER run once at seed time, not on user-request path; no NFR-01 impact

### Negative

- spaCy models add ~500 MB to dev environment (not deployed to CF Worker)
- cluster quality depends on corpus size (55 docs is small for BERTopic; tuning required)
- EmbeddingGemma calls from host to CF Workers AI require internet at seed time

### Neutral

- D1 gets three new tables: `document_clusters`, `entities`, `document_entities`
- Cluster labels are static until re-seed; dynamic re-clustering is future work
- Sigma.js viewer loads in <2s for 55 nodes; degradation point at ~1000 docs

## Dependencies

- `bertopic`, `umap-learn`, `hdbscan` (pip, host only — not added to `pyproject.toml`)
- `spacy` + `en_core_web_lg`, `de_core_news_lg`, `fr_core_news_lg` (host only)
- `sentence-transformers` (host only, for offline fallback embedding)
- `httpx` (already in `pyproject.toml` — used for CF Workers AI calls)

All offline dependencies are listed in `requirements-offline.txt` (new file). They are NEVER added to `pyproject.toml` because they must not install in the Cloudflare Worker.

## Future work (post-capstone)

### KnowledgeBase patterns
- REBEL triple extraction as Modal sidecar
- Dynamic user-upload clustering (GDPR boundary — requires differential privacy)
- Real-time NER on uploaded documents
- Dynamic cluster re-computation on corpus change
- Louvain community detection for graph nodes
- 3D-force-graph view (KB's `export_3d_html`)

### Linus patterns
- **DEC-0059 full grounding gate** — hard citation-enforcement that refuses ungrounded claims (`error`-severity), `KBEntityLookup` backed by knowledge graph, cross-run confidence calibration via `check_grounding(claim, papers, entities, prior_runs)` surface
- **DEC-0060 loud degradation healthz** — `effective_state ∈ {"live", "degraded", "down"}` + `degradations[]` with per-component severity and remediation
- **DEC-0061 per-tool network policy** — egress audit logging per tool, GDPR consent boundary enforcement

> **Updated per ADR-023:** These three patterns are now implemented (not just "documented"). See [ADR-023](ADR-023-linus-integration.md) for implementation details.

### Reference implementations
- [KnowledgeBase](https://github.com/dbrowneup/KnowledgeBase) — `papers_analysis/cluster.py` (`_IdentityDR` pattern), `papers_analysis/graph.py` (auto-threshold, Louvain), `papers_analysis/visualize.py` (Sigma.js + 3D-force-graph, vendor JS caching)
- [Linus](https://github.com/dbrowneup/Linus) — `docs/adr/0059-grounding-gate-output-surface.md`, `docs/adr/0060-loud-degradation-healthz-extension.md`, `docs/adr/0061-network-policy-framework.md`
