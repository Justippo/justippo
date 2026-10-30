# ADR-021: Composed PDF Reference Translation and Understanding

**Date:** 2026-07-16

**Status:** Accepted — Phases 2–8 implemented; live-provider enablement pending

**Decision owner:** Mihai Chindriș

**Production approvals still required:** Product Owner, Azure subprocessor/privacy review,
and deployment configuration review

**Extends:** ADR-002, ADR-006, ADR-012

---

## Context

EvidenceEU accepts PDF uploads and extracts their visible content through OCR. The product must also
accept native-text PDFs and interactive PDF forms so that a user can read a translated reference
copy, understand what the document asks for, and find the relevant EU-law context.

The current scope does **not** let a user fill, edit, sign, submit, or otherwise modify a form in
EvidenceEU. It does not promise to preserve editable fields in the translated output. Form filling
and editable-PDF reconstruction are a separate future product phase.

Azure Document Intelligence and BabelDOC have complementary roles. Azure analyzes document
structure and relationships; BabelDOC translates and re-renders visible page content. They are
required stages of one composed workflow, not fallbacks for each other.

## Decision

Introduce a feature-flagged, reference-only PDF workflow:

```text
Browser-held original PDF
  -> existing upload and text extraction
  -> provider-neutral PDF intake route
  -> Azure Document Intelligence structure analysis ----+
  -> BabelDOC layout-preserving translation ------------+-> translated reference PDF
  -> EvidenceEU document classification / RAG ----------------> requirements and EU-law context
```

All readable, unprotected PDFs use the same route. EvidenceEU does not need to classify a PDF as a
scan, native document, AcroForm, or XFA form before choosing the route because those types all
produce the same reference-only output.

### Division of responsibility

| Responsibility                                                              | Owner                                       |
| --------------------------------------------------------------------------- | ------------------------------------------- |
| Validate that the upload is a PDF and apply EvidenceEU limits               | Provider-neutral intake service             |
| Extract reading order, tables, key/value relationships, and selection marks | Azure Document Intelligence                 |
| Translate and re-render visible page content                                | BabelDOC                                    |
| Classify the document and explain what it requires                          | Existing EvidenceEU classification/RAG path |
| Retrieve relevant EU-law sources with citations                             | Existing EvidenceEU RAG/search path         |
| Preserve the unchanged source file during the session                       | Browser                                     |

Azure Document Translation is not applied after BabelDOC because that would translate the same
content twice. Azure's role is document understanding through Document Intelligence.

## Product behavior

### Reference output

Every successful PDF job produces a translated reference copy. The UI must state that the output
helps the user understand the source document and is not an official replacement for it. The
browser keeps the user's original `File`; the service does not mutate or return a second copy of
the original.

Interactive controls, entered values, signatures, calculations, submit actions, and other PDF
behavior are out of scope. They may be absent or flattened in the translated reference copy.

### Supported input

The intended supported set is any PDF whose visible pages can be read without a password,
including:

- native-text PDFs;
- scanned/image-only PDFs;
- mixed text-and-image PDFs;
- AcroForm and XFA forms when their visible pages render;
- signed PDFs, without changing the signed original.

“Any PDF” does not include corrupt files, password-protected files, or documents whose visible
pages cannot be rendered by the processing services.

### Rejected input

Encrypted or password-protected PDFs require an unprotected copy. EvidenceEU does not accept
passwords or attempt to remove protection. Invalid, corrupt, oversized, or over-page-limit files
return typed errors without sending content to downstream processors.

## Technical design

### Processing boundary

The browser sends the original file once and retains its local `File` object. The Cloudflare Python
Worker continues to process uploads in memory only. BabelDOC uses temporary disk only inside its
isolated sidecar and deletes request files in a `finally` path.

Initial contract limits are:

- PDF only for the composed reference workflow;
- English, German, and French;
- maximum 10 MiB input;
- maximum 20 pages;
- maximum processing time of 300 seconds.

These are EvidenceEU contract limits, not claims about provider maxima. The active Azure tier can
narrow them. The Capstone configuration uses F0, so the composed route accepts at most two pages
and 4 MiB until the resource is deliberately changed to S0.

### Phased module layout

```text
backend/app/services/pdf_intake_service.py
backend/app/integrations/azure_document_intelligence.py
backend/app/integrations/babeldoc_adapter.py
backend/app/services/pdf_reference_translation_service.py

sidecars/babeldoc/app/runtime.py

frontend/src/hooks/usePdfReferenceTranslation.ts
frontend/src/components/translation/PdfReferenceResult/
```

No PDF parsing dependency is added to the Cloudflare Worker. Phase 2 performs provider-neutral
signature validation and routing only. Page-count, encryption, and renderability checks happen
when the document processors are integrated.

### Phase 2 routing contract

For `application/pdf`, intake checks that a PDF header exists within the first 1,024 bytes. A valid
PDF receives this metadata-safe decision:

```json
{
  "route": "pdf_reference_translation",
  "output_mode": "reference",
  "original_unchanged": true,
  "form_filling_supported": false
}
```

DOCX and PNG retain their existing upload behavior and do not receive a PDF routing decision.

### Test seams

- Intake routing is a pure byte-level service with synthetic fixtures.
- Azure HTTP calls will be behind an adapter and mocked in unit tests.
- BabelDOC execution remains behind the existing HTTP adapter.
- Live provider tests are opt-in and never use personal documents.
- EU-law answers must use retrieved sources and preserve the existing prompt-injection defenses.

## Privacy and data residency

The existing `X-GDPR-Consent` requirement remains mandatory. Before Azure is enabled in production,
the consent notice must identify Azure as a document-processing subprocessor for this route.

Production Azure configuration must:

- use an approved European processing region;
- send document bytes directly to the analyze API rather than expose public document URLs;
- keep document bytes and extracted content out of telemetry;
- document contracted retention and deletion terms;
- store endpoint and key only as server-side secrets.

The user's recently created Azure Document Intelligence account is not yet integrated into this
repository's deployed environment. Phase 3 adds a disabled-by-default REST adapter; its endpoint
and key remain unset until the privacy and deployment settings are confirmed.

### Azure Phase 3 contract

The adapter uses the GA `2024-11-30` Analyze Document From Stream API with:

- model `prebuilt-layout`;
- direct `application/pdf` request bytes;
- `keyValuePairs` and `languages` features;
- Markdown top-level content for later explanation/RAG preparation;
- bounded asynchronous polling of the provider operation URL;
- same-origin validation of the provider-supplied operation URL;
- a best-effort Delete Analyze Result request in the cleanup path.

Microsoft documents that analysis inputs and results are temporarily retained in same-region
Azure storage for asynchronous retrieval and otherwise remain available for up to 24 hours after
completion. EvidenceEU therefore requests deletion immediately after success or failure. A cleanup
failure is logged without document content and does not replace the primary analysis outcome.

### BabelDOC Phase 4 contract

The existing ADR-012 `POST /translate` boundary now executes the pinned
`BabelDOC==0.6.3` CLI. Each request uses an isolated temporary workspace for
the source PDF, glossary, runtime config, intermediate files, and output. The
workspace is removed on success, validation failure, timeout, or runtime error.

The CLI receives a request-local TOML configuration rather than gateway
credentials in its argument list. The config has mode `0600`, is never logged,
and points only to an HTTPS `gateway.ai.cloudflare.com` origin. Successful
output remains a translated reference PDF; no editable-form guarantee is made.

### Evidence-grounded explanation Phase 5 contract

Document understanding produces two deliberately separate evidence layers:

1. Requirements stated by the uploaded PDF are extracted deterministically from field labels and
   explicit instruction sentences. Field values are never treated as requirements.
2. EU-law context is retrieved with a privacy-minimized query containing only document type,
   geographic metadata, and bounded field labels. Full document prose and field values are not
   sent as the retrieval query.

Only verified HTTPS sources on official `europa.eu` hosts can become legal citations. The uploaded
document is passed to generation as user-provided evidence and explicitly marked as non-authoritative.
The existing RAG prompt delimiters isolate retrieved and uploaded content from system instructions.

A generated explanation is exposed only when it cites at least one verified official source with a
valid `[SOURCE N]` marker. If retrieval, generation, or citation validation fails, the service still
returns deterministic document requirements and any verified citations, but no unsupported legal
narrative. Phase 6 exposes this service only through the composed orchestrator.

### Composed orchestration Phase 6 contract

`POST /api/v1/translate/pdf-reference` accepts one multipart PDF plus explicit source and target
languages. The Worker validates the 10 MiB intake limit and PDF signature, then runs Azure analysis
first. Azure's normalized pages enforce the 20-page limit before BabelDOC receives the document.

After classification, BabelDOC reference rendering and the evidence-grounded explanation run as
independent tasks. BabelDOC remains required: a rendering failure fails the request. Explanation is
advisory and degrades to deterministic requirements when its retrieval or generation path is
unavailable. The successful response contains the translated PDF as base64 because the Worker does
not retain an artifact or write it to disk.

The public response repeats `ephemeral`, `output_mode`, `original_unchanged`, and
`form_filling_supported` so clients cannot misrepresent the reference copy. All provider failures
are mapped to content-safe typed errors. Live Azure and BabelDOC settings remain disabled by default.

### Frontend integration Phase 7 contract

The unified Translate flow retains the selected PDF `File` in React memory while the user reviews
upload analysis and selects a target language. It sends that original `File` to the composed endpoint
only after the user continues to translation. The file is never serialized into session storage.

If the page reloads before the composed request, the UI asks for the PDF again instead of silently
falling back to extracted-text translation. Non-PDF uploads and older non-reference sessions retain
the existing page-text translation behavior.

The successful screen provides translation-only and original/translated comparison views, open and
download actions for the browser-created reference artifact, deterministic requirements, and
verified official citations. It always shows the reference-only limitation. Loading, error, empty,
and success states are keyboard accessible and use product-safe error copy.

### Capstone readiness Phase 8 contract

`AZURE_DOCUMENT_INTELLIGENCE_TIER` is an explicit server-side setting and defaults to `F0`.
The browser forwards the trusted page count returned by the preceding upload analysis. Before a
billable Azure request starts, the orchestrator rejects a document above the configured tier's
page or byte limit. After analysis, it verifies that Azure returned every expected page before
BabelDOC receives the document. This prevents F0's first-two-pages behavior from producing an
apparently complete explanation of a longer PDF.

Live secrets remain intentionally unset. Provider activation follows
`docs/translation/pdf-reference-capstone-readiness.md` and still requires the rollout approvals
below. The BabelDOC endpoint must be protected at its hosting boundary with service-to-service
authentication; an unauthenticated public endpoint is not an approved deployment.

## Dependencies

Phase 2 adds no dependency. In particular, `pypdf` is no longer required because editable form
inspection and reconstruction are outside the current scope.

## Observability

Only metadata-safe values may be recorded: request identifier, stage, elapsed time, byte-size and
page-count buckets, source and target language, reference output mode, and provider HTTP status
category. Filenames, extracted strings, translated strings, document bytes, field names, values,
and provider payloads are prohibited.

## Alternatives considered

### Preserve editable PDF forms now

Deferred. It requires field-tree reconciliation, action and signature safety checks, and a form
filling product flow that is explicitly outside the current phase.

### BabelDOC alone

Insufficient for structured explanation of key/value relationships, selection marks, and tables.

### Azure alone

Insufficient for the selected layout-preserving translated reference PDF experience.

### Provider fallback chain

Rejected for this workflow. Azure analysis and BabelDOC rendering contribute different required
outputs; one does not silently replace the other.

## Approval and rollout gates

- [x] Translation/UX owner approved reference-only PDF scope.
- [x] Translation/UX owner approved provider-neutral Phase 2 intake and routing.
- [ ] Product Owner approves the external-service boundary.
- [ ] Azure subprocessor, European region, and retention terms are approved.
- [ ] Synthetic fixture suite passes before any live document is used.
- [ ] Live Azure/BabelDOC validation passes with non-personal fixtures.
- [ ] Feature flag remains disabled until final rollout approval.
