# ADR-006: PDF Extraction Library — License-Driven Choice

**Date:** 2026-05-29
**Status:** Implemented (direct dep swap) — escalated (transitive AGPL via BabelDOC remains). GitHub #41, #14, #15
**Deciders:** Mihai Chindriș, team
**Context source:** Surfaced during collaboration talks with [Dan Browne](https://github.com/dbrowneup) (KnowledgeBase / Linus), who independently hit the same AGPL friction.

---

## Context

EvidenceEU previously depended on **PyMuPDF** (`pymupdf>=1.24.0`, in the `ocr` optional-dependency group) for PDF text extraction.

PyMuPDF is licensed under **AGPL-3.0-or-later**. The AGPL's network-use clause (Section 13) means that for a **network-served web application** — exactly what EvidenceEU is — the source-disclosure obligation extends to the *entire combined work*, not just modifications to PyMuPDF itself.

This was a non-issue while EvidenceEU was framed purely as a graded capstone. **It becomes a blocker now that the team intends to pursue EvidenceEU as a startup after submission** (commercial / potentially closed-source product, EU launch). Continuing to build on PyMuPDF accrues technical debt that is expensive to unwind later, because PDF extraction sits at the bottom of the document pipeline.

---

## ⚠️ BLOCKER — BabelDOC Transitive AGPL Dependency

**Investigated:** 2026-06-03 — BabelDOC v0.6.3 `pyproject.toml` (GitHub `main` branch)

### Dependency chain

```
evidence-eu-backend
  └─ [translation] BabelDOC >=0.6.2  (AGPL-3.0)
       └─ pymupdf >=1.26.7           (AGPL-3.0)
```

### Key findings

1. **BabelDOC hard-depends on `pymupdf>=1.26.7`** — confirmed in BabelDOC v0.6.3 `pyproject.toml` `[project].dependencies`. Removing our *direct* `pymupdf` dependency does NOT remove PyMuPDF from the installed environment; it still arrives transitively through our core translation engine.

2. **BabelDOC is itself licensed AGPL-3.0** (`license = "AGPL-3.0"` in its `pyproject.toml`). So the translation engine is a *second, independent* AGPL surface — even a complete PyMuPDF elimination leaves an AGPL component at the heart of the product.

3. **All other BabelDOC dependencies are permissively licensed** (MIT, BSD, Apache-2.0): numpy, onnxruntime, openai, httpx, Pillow, scikit-image, opencv-python-headless, etc.

### Risk assessment

For a **network-served commercial product**, the AGPL exposure is driven primarily by **BabelDOC itself**, not just its transitive PyMuPDF. The pypdfium2 swap (done — see Decision below) removes one AGPL surface from our *direct* control path, but is **not sufficient** to make the product closed-source-safe.

### Proposed mitigations (pre-commercialization, not capstone-blocking)

| Option | Effort | Notes |
|--------|--------|-------|
| **Replace BabelDOC with permissively-licensed alternative** (Doclingo, BelinDoc) | High | Sprint 2 evaluation already planned (ADR-002) |
| **Run BabelDOC as isolated microservice** (AGPL boundary via network API) | Medium | Legally debatable; isolates copyleft to one container |
| **Negotiate commercial license with funstory-ai** | Low | Depends on upstream willingness |
| **Open-source EvidenceEU under AGPL** | Zero | Eliminates friction but constrains business model |
| **File upstream issue requesting permissive relicensing** | Low | Unlikely to succeed but costs nothing |

### Capstone impact

For the **capstone itself** (graded academic deliverable, not distributed/commercialized), AGPL creates **no friction** — there is no distribution or network-service-for-third-parties trigger that forces source disclosure in a school project. This blocker is strictly a **pre-commercialization** concern.

---

## Decision

Migrate away from PyMuPDF to a **permissively licensed** PDF extraction library for all *direct* usage, AND treat the translation-engine license as a separate pre-commercialization decision (ADR-002):

1. ~~**Investigate first:** whether BabelDOC transitively depends on PyMuPDF.~~ ✅ **DONE — it does (v0.6.3: `pymupdf>=1.26.7`), and BabelDOC is itself AGPL. See BLOCKER section.**

2. **Primary target (direct dep):** **`pypdfium2`** (Apache-2.0 / BSD-3-Clause) — an ABI-level binding to Google's PDFium. Fast, high-quality text extraction, liberally licensed. ✅ **DONE — `backend/pyproject.toml` updated, `ocr_service.py` migrated.**

3. **Fallback for tables/layout:** `pdfplumber` (MIT) if richer table extraction is needed.

4. **Poppler / `pdf2image` posture:** `pdf2image` shells out to the Poppler CLI (GPLv2) as a *separate process* (arm's-length invocation, not linked). This is materially lower risk than a linked AGPL library, but should be documented and, ideally, made optional.

---

## Implementation (2026-06-03)

- Removed `pymupdf>=1.24.0` from `backend/pyproject.toml` `[project.optional-dependencies].ocr`
- Added `pypdfium2>=4.30.0` with license comment
- Rewrote `backend/app/services/ocr_service.py`:
  - Added guard comment: `# See docs/adr/ADR-006 — do not re-introduce pymupdf or fitz imports`
  - Added DRY helper functions: `pdf_page_count()`, `pdf_extract_text()`, `pdf_render_pages()`, `pdf_metadata()`
  - All helpers use pypdfium2's `PdfDocument`, `PdfPage.get_textpage()`, and `PdfPage.render()` APIs
  - Function signatures unchanged; Tesseract fallback logic untouched

---

## Alternatives Considered

| Option | License | Verdict |
|--------|---------|---------|
| **Keep PyMuPDF** | AGPL-3.0 | ❌ Incompatible with a future commercial/closed product served over a network |
| **PyMuPDF commercial license** | Paid | ❌ Unjustifiable cost for a student team; only revisit if pypdfium2 quality proves inadequate |
| **`pypdfium2`** | Apache-2.0 / BSD-3 | ✅ **Chosen** — permissive, fast, strong extraction quality |
| **`pdfplumber`** | MIT | ✅ Fallback for table-heavy documents; pure-Python, slower at scale |
| **`pypdf`** | BSD | 🟡 Viable, permissive, but extraction quality below pypdfium2 for complex layouts |

---

## Consequences

- **Positive:** Clears the largest licensing obstacle to commercializing EvidenceEU's direct dependencies. Keeps the future grant / closed-source path open for the OCR pipeline.
- **Positive:** Aligns EvidenceEU with Dan's KnowledgeBase if he migrates too — a concrete, mutual contribution-back opportunity.
- **Negative / Remaining risk:** BabelDOC transitive AGPL remains. The translation-engine decision (ADR-002) must be revisited in Sprint 2 — this is the larger blast radius.
- **Neutral:** Minor API differences between PyMuPDF (`fitz`) and pypdfium2; isolated to `app/services/ocr_service.py` helper functions.

---

## Related

- [ADR-002](ADR-002-translation-babeldoc.md) — BabelDOC translation engine (transitive PyMuPDF + AGPL source)
- GitHub Issues: [#41](https://github.com/evidenceeu/evidenceeu/issues/41) — Migration + BabelDOC investigation
- GitHub Issues: [#14](https://github.com/evidenceeu/evidenceeu/issues/14), [#15](https://github.com/evidenceeu/evidenceeu/issues/15) — Related license concerns
- Backend dependency: `backend/pyproject.toml` (`ocr` group)
