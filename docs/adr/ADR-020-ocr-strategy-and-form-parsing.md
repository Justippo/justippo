# ADR-020: OCR Strategy and Fillable PDF Form Parsing

**Date:** 2026-07-16

**Status:** Accepted

**Decider:** Mihai Chindriș (PO/Dev)

**Supersedes:** n/A — fills a gap in the original document processing pipeline

**Related:** fillable PDF analysis (Slack 2026-07-16), BabelDOC sidecar (ADR-012), Hindsight hosting (ADR-016)

---

## Context

EvidenceEU's current document processing pipeline sends every PDF through Mistral OCR
(via Cloudflare Workers AI) and returns only extracted page text. This works for
scanned/image PDFs but fundamentally breaks fillable AcroForm PDFs (e.g. the
Ausländerbehörde residence permit application forms our users upload):

- Fillable PDFs contain a native text layer + interactive form objects (widgets,
  field values, tooltips, appearance definitions).
- OCR rasterizes the PDF to an image, discarding the form structure entirely.
- The original editable form is destroyed — the user cannot submit it to the authority.
- The `preserve_layout` parameter in the translation service is accepted but never
  wired to any layout-preserving processor.

It was correctly identified that the translation step has no access to AcroForm fields,
widgets, or appearance definitions because the PDF byte buffer is deleted after OCR.

## Decision

We adopt a **three-path document processing strategy** with a PDF type router
(`PDFDocumentRouter`) that classifies uploads before OCR:

### Path 1: Scanned / Image PDFs → Mistral OCR (existing, retained)

- Current pipeline, already deployed and working.
- Mistral OCR via Cloudflare Workers AI — $0 incremental cost.
- Produces page text for translation.
- **Keep as-is for capstone MVP.**

### Path 2: Fillable AcroForm PDFs → Direct form field parsing (new, pre-capstone)

- Use pypdf or pdfminer.six to read the PDF's native text layer and AcroForm
  widgets directly — no OCR, no rasterization.
- Extract: field labels, field values, tooltips, section headings, instructions.
- Produce a **translated reference copy** (labels/headings translated, original
  form structure preserved for submission).
- Both libraries are pure Python, $0, Pyodide-compatible (no native extensions).
- **Target: wire into the translate endpoint before capstone submission.**

### Path 3: XFA / Dynamic / Encrypted PDFs → Restricted fallback

- XFA forms (XML Forms Architecture, common in German government PDFs) are
  structurally different from AcroForms and harder to parse.
- For the capstone: return a clear "unsupported format" message with guidance.
- Post-capstone: evaluate dedicated XFA parsing libraries.

### Deferred: dots.ocr (Modal GPU sidecar) — post-capstone evaluation

**dots.ocr** (RedNote-HiLab, 1.7B params) is an LLM-based OCR model that produces
structured layout output with bounding boxes, categories (Title/Table/Text/etc.),
and JSON. It is significantly more accurate than Mistral OCR on complex layouts
(tables, multi-column, mixed languages).

**Why we are NOT adopting it for the capstone:**

| Constraint | Impact |
|-----------|--------|
| Requires GPU (A10G minimum) | Cannot run at $0 — Modal GPU costs ~$0.001/page ($1.10/hr A10G) |
| ~6 GB model weights + PyTorch + flash-attn | Cold start ~30s, heavy image build |
| Still image-based OCR | Does NOT solve the fillable PDF problem — rasterizes the PDF |
| Mistral OCR is sufficient for capstone | Scanned document quality is adequate for demo and NFR evidence |

**Why it may be valuable post-capstone:**

- Better table extraction (returns HTML `<table>` from complex layouts).
- Bounding boxes enable spatial search and highlighted citations.
- Multilingual layout detection outperforms Mistral on German bureaucratic forms
  with mixed FR/DE/EN text.
- At ~$0.001/page, affordable for occasional use (not always-on).

**Post-capstone evaluation criteria:**

1. Does Mistral OCR produce acceptable quality on our real document corpus?
   (Test with 20+ Ausländerbehörde / EU regulation PDFs)
2. Is table extraction quality a blocker for user trust?
3. Can dots.ocr run as a GPU sidecar on Modal with `min_containers=0` and
   scale-to-zero? (Yes, but GPU billing is per-second — cannot be $0)
4. Would the ~$0.001/page cost be acceptable within the $30/mo credit?
   (At 500 pages/month = $0.50 — well within budget)

### Why Azure Document Intelligence is NOT adopted for the capstone

A question was raised about Azure DI. It offers excellent AcroForm/XFA parsing via
`prebuilt-layout` and custom models, with a generous free tier (500 pages/month).
However:

- Introduces a third cloud provider (Azure) with its own account, billing, secrets.
- The free tier is sufficient for the capstone, but adds operational complexity.
- The same form-parsing capability is achievable with pypdf/pdfminer.six ($0,
  pure Python, no new cloud dependency).
- **Deferred to post-capstone** if the pure-Python libraries prove insufficient
  for complex German government forms.

## Consequences

### Immediate (pre-capstone)

- Build `PDFDocumentRouter` in `app/services/` to classify PDFs by type
  (scanned / AcroForm / XFA) using pypdf's `PdfReader.get_fields()` or
  pdfminer.six's `extract_text()` fallback detection.
- Wire AcroForm path into `translate.py` endpoint — extract form fields,
  translate labels/headings, return translated reference + original form.
- The BabelDOC sidecar (ADR-012) remains the layout-preserving translation
  engine for scanned documents. It handles a different stage (render) than
  the form parser (understand).

### Post-capstone

- Evaluate dots.ocr on 20+ real documents — measure layout detection accuracy
  vs. Mistral OCR, especially for tables and mixed-language content.
- If adopted, deploy as a Modal GPU sidecar with `min_containers=0`
  (scale-to-zero, per-page billing). Budget impact: ~$0.50/month at 500 pages.
- Evaluate Azure DI only if pypdf/pdfminer.six cannot handle XFA forms or
  the complexity of specific Ausländerbehörde form templates.
