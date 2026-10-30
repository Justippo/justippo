# ADR-002: Document Translation Engine — BabelDOC

**Date:** 2026-05-14 (updated 2026-06-25)
**Status:** Accepted — BabelDOC is the capstone translation engine with full layout preservation via DocLayout-YOLO. HTTP sidecar pattern (ADR-012) isolates AGPL-3.0 license. CF Workers AI m2m100-1.2b remains as text-only fallback.
**Author:** Mihai Chindriș

> **⚠️ License note (added 2026-05-30):** BabelDOC 0.6.2 is licensed **AGPL-3.0** and hard-depends on `pymupdf>=1.25.1` (also AGPL). This is **fine for the graded capstone** (no distribution/commercial trigger), but is a **blocker for the planned startup phase** as a network-served product. The Sprint 2 evaluation of Doclingo/BelinDoc (below) must now weigh **license** as a first-class criterion, not just quality. See [ADR-006](ADR-006-pdf-extraction-license.md) for full findings.

## Context

Document layout preservation during translation is the core technical differentiator of EvidenceEU. Generic translation APIs (DeepL, Google Translate) handle text but destroy PDF structure — tables collapse, columns overflow, signatures lose position.

## Decision

Use **BabelDOC** as the primary capstone translation engine for layout-preserving PDF translation. BabelDOC runs as an HTTP sidecar (ADR-012) and uses DocLayout-YOLO for layout analysis — preserving tables, columns, headers, and signatures during translation. Cloudflare Workers AI `m2m100-1.2b` remains as a text-only fallback for Pyodide-safe operation when the sidecar is unavailable.

Translation chain: `BabelDOC (layout-preserving, sidecar) → m2m100-1.2b (text-only, Pyodide) → glossary enforcement → manual review`

BabelDOC's AGPL-3.0 license is isolated behind the HTTP boundary — the MIT-licensed codebase never imports BabelDOC directly.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| DeepL API | Breaks document layout; text-only output |
| Google Translate | Same layout problem; privacy concerns for GDPR |
| Custom fine-tuned model | Out of scope for capstone timeline |
| Doclingo / BelinDoc | Evaluate in Sprint 2 as potential replacements |

## Consequences

- Sprint 2 ships a Pyodide-safe translation path with no native layout engine dependency
- German (`deu`) and French (`fra`) Tesseract language packs installed in backend Dockerfile for OCR fallback
- Translation quality for bureaucratic/legal documents must be validated with real German administrative PDFs in Sprint 2
- BabelDOC sidecar work stays isolated behind HTTP so the AGPL boundary remains clear
