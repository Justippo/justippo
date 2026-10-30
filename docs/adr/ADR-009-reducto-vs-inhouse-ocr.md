# ADR-009: Reducto vs In-House OCR — Public Corpus Only

**Date:** 2026-06-13
**Status:** Accepted
**Deciders:** Mihai Chindriș
**Context:** Sprint 2 OCR expansion — Reducto's agentic parsing for the public EUR-Lex corpus (code already shipped)
**See also:** [ADR-006](ADR-006-pdf-extraction-license.md) — PDF extraction (pypdfium2 in-house)

---

## TL;DR

Reducto is adopted as an **optional** parse path in `scripts/seed_documents.py` for the **public EUR-Lex corpus only** (no personal data → GDPR-safe). User-uploaded documents stay on ephemeral in-house OCR (Mistral + Tesseract) — Reducto is never used for citizen data. Reducto's [EU data residency](https://docs.reducto.ai/security/eu-data-residency) guarantees all document data is processed/stored/deleted exclusively within the EU; [24-hour ZDR](https://llms.reducto.ai/trust-center-on-prem-zero-retention-hipaa-soc2-baa) is enforced on Growth+ tiers. `ENABLE_REDUCTO=false` (default); set `ENABLE_REDUCTO=true` to activate. Code shipped; 18 unit tests (covering 11 scenarios) in `backend/tests/unit/test_reducto_ingest.py`.

---

## Context

### The Problem with In-House OCR for Seed Data

`scripts/seed_documents.py` currently fetches EUR-Lex HTML (structured text, no OCR needed) via `BeautifulSoup`. This works for clean regulatory HTML but will break for:

- EUR-Lex documents served as **scanned PDFs** (imaging-only publications, older OJ articles)
- **PDF attachments** linked from EUR-Lex HTML pages (not the HTML itself)
- Any non-HTML public corpus sources added post-Sprint 1

The in-house OCR path (Mistral + Tesseract via `ocr_service.py`) is designed for **user-uploaded documents** and is properly ephemeral (no disk writes, GDPR-safe). It is not wired into the seeding pipeline.

### Reducto's Offer

[Reducto](https://reducto.ai/) is an agentic document parsing API:
- Layout-aware OCR for complex PDFs, tables, handwriting
- Returns LLM-ready chunks with bounding boxes + citations
- 99.24% claimed accuracy, 1B+ pages processed, SOC 2 Type II
- Python SDK (`pip install reductoai`, Python 3.9+)
- `chunk_mode: variable` produces 750-1250 char chunks — direct replacement for `seed_documents.py`'s `RecursiveCharacterTextSplitter`

### The GDPR Problem

| Reducto Tier | EU Data Residency | Zero Data Retention | Cost |
|---|---|---|---|
| **Standard** (free) | ❌ US-hosted only | ❌ Not available | Free (15K credits) |
| **Growth** (custom) | ✅ EU/AU endpoints | ✅ ZDR Agreement | Custom pricing |
| **Enterprise** (custom) | ✅ VPC + On-Prem | ✅ ZDR Agreement | Custom pricing |

The **Standard (free) tier** stores parsed document data on US AWS with no data retention guarantees. Sending citizen-uploaded PDFs through this tier would directly contradict:
- `GDPRConsentMiddleware` (GDPR Article 7 gate)
- `AuditLogMiddleware` (GDPR Article 30 audit trail)
- `No disk writes` / `ephemeral OCR` guarantees in `ocr_service.py`
- Sprint 3 task #26 "Security review & GDPR compliance check"

### The Decision

**Scope Reducto to the public EUR-Lex corpus only.** Public EU regulations contain no personal data — GDPR does not apply to documents with no natural-person data. Reducto's Standard tier is safe for this use case.

**User-uploaded documents stay on ephemeral in-house OCR** (Mistral + Tesseract). Reducto's EU endpoints + ZDR are not needed because no user PII ever reaches Reducto's servers.

---

## Decision

Add an optional Reducto parse path to `scripts/seed_documents.py` for public corpus ingestion:

1. **Feature flag:** `ENABLE_REDUCTO` env var (default: `false`)
2. **Public corpus only:** Only EUR-Lex documents (no personal data) use Reducto
3. **EU endpoint assumed:** Configured via `REDUCTO_API_KEY` pointing to Growth/Enterprise key; EU residency + ZDR are server-side configuration (not a client-side choice)
4. **In-house OCR unchanged:** User-uploaded PDFs continue to use Mistral + Tesseract via `ocr_service.py`
5. **Graceful fallback:** When Reducto is disabled or unavailable, fall back to existing BeautifulSoup HTML extraction (current behavior)
6. **Idempotency:** Same as existing — Hindsight's upsert deduplicates by `document_id`

### Architecture

```
scripts/seed_documents.py
  │
  ├─ ENABLE_REDUCTO=true  →  Reducto upload + parse.run(chunk_mode=variable)
  │                            └─► chunks.content → RecursiveCharacterTextSplitter → Hindsight
  │
  └─ ENABLE_REDUCTO=false (default) → existing BeautifulSoup HTML extraction path
                                        └─► RecursiveCharacterTextSplitter → Hindsight
```

### Why Not Route User Uploads Through Reducto?

1. **GDPR:** Standard tier is US-only/no-ZDR. User PDFs may contain personal data. This would contradict the GDPR-native pitch.
2. **Cost:** EU endpoints + ZDR require Growth/Enterprise (custom pricing). No free tier for user-upload routing.
3. **Architecture:** User uploads are ephemeral (BytesIO, no disk). Reducto's server-side processing doesn't match the ephemeral guarantee.
4. **ADR-006 alignment:** pypdfium2 (in-house) is already chosen for direct PDF extraction. Reducto's value is for complex/scanned docs in the seeding pipeline.

### What Happens When the Corpus Grows Beyond 15K Credits?

The ~55-document initial corpus consumes ~55-165 credits at Reducto's Standard rate (~1-3 credits/page). The multilingual pass (DE+FR, 55 docs × 2 = 110 docs) adds ~110-330 credits. Total for Sprint 1-2: **~165-495 credits**, well within the 15K free tier.

If the corpus grows to thousands of documents (post-capstone), the options are:
- **Community edition:** Stay on Standard, accept US-only processing for the public corpus (acceptable — no PII)
- **Growth tier:** Pay for EU residency + ZDR if commercial tier requires it
- **On-prem Reducto:** Enterprise option for self-hosted deployment

---

## Alternatives Considered

| Option | Verdict | Notes |
|--------|---------|-------|
| Route user uploads through Reducto Standard | ❌ Rejected | US-only, no ZDR — contradicts GDPR-native pitch |
| Route user uploads through Reducto's EU endpoint (Growth tier) | ❌ Rejected | Custom pricing; unnecessary since in-house OCR is already ephemeral |
| Replace in-house OCR entirely with Reducto | ❌ Rejected | Removes the ephemeral/no-disk-write guarantee for user uploads |
| Add Reducto to `ocr_service.py` as alternative provider | ❌ Rejected | ocr_service.py handles user uploads; Reducto's value is corpus seeding |
| Keep current BeautifulSoup-only approach | 🟡 Accepted (baseline) | Works for clean HTML; misses scanned PDFs and PDF attachments |
| **Adopted: optional Reducto for corpus, in-house for uploads** | ✅ Chosen | Clean separation, GDPR-safe, graceful fallback |

---

## Implementation

### Files Changed

| File | Change |
|------|--------|
| `backend/pyproject.toml` | Add `reductoai>=0.22.0` to `[project.optional-dependencies].reducto` group |
| `scripts/seed_documents.py` | Add `ENABLE_REDUCTO` env var; `_reducto_available()` guard; `_fetch_with_reducto()` helper with PDF-link discovery + Reducto parse + fallback to BeautifulSoup HTML path |
| `docs/adr/ADR-009-reducto-vs-inhouse-ocr.md` | This document |
| `docs/testing/ocr-benchmark.md` | 3-way OCR benchmark table: Mistral vs Tesseract vs Reducto |
| `backend/tests/unit/test_reducto_ingest.py` | 18 unit tests across 5 classes: availability gating (3), Reducto parse + fallback (7), routing (4), multilingual (1), GDPR scope (3) — no real network calls |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_REDUCTO` | `false` | Set `true` to activate Reducto path in seed script |
| `REDUCTO_API_KEY` | `""` | Reducto API key (from studio.reducto.ai). EU endpoint + ZDR are server-side; provide Growth/Enterprise key |
| `REDUCTO_BASE_URL` | `https://api.reducto.ai` | Override for EU regional endpoint if required |

### Key Code Patterns

**Reducto parse call in `_fetch_with_reducto()` (behind ENABLE_REDUCTO):**
```python
# Step 1: Discover PDF link from EUR-Lex HTML page
soup = BeautifulSoup(resp.content, "html.parser")
for a in soup.find_all("a", href=True):
    href = a["href"]
    if href.lower().endswith(".pdf") or "pdf" in href.lower():
        pdf_link = href
        break
pdf_url = f"https://eur-lex.europa.eu{pdf_link}"

# Step 2: Fetch PDF bytes (in-memory, no disk write)
pdf_resp = client.get(pdf_url, timeout=60)
pdf_bytes = pdf_resp.content

# Step 3: Upload to Reducto + parse with variable chunking
client_red = Reducto(api_key=REDUCTO_API_KEY, base_url=REDUCTO_BASE_URL)
upload = client_red.upload(file=io.BytesIO(pdf_bytes), filename=f"{celex}.pdf")
result = client_red.parse.run(
    input=upload,  # Upload object (not file_id string) — SDK quickstart pattern
    retrieval={"chunking": {"chunk_mode": "variable"}},
)
# Return (markdown_bytes, "utf-8") or None on any error → falls back to BeautifulSoup
for chunk in result.result.chunks:
    parts.append(chunk.content)
```

**GDPR enforcement (enforced by architecture — not configuration):**
```python
# _fetch_with_reducto() ONLY lives in scripts/seed_documents.py
# It is NEVER imported, called, or referenced from ocr_service.py or any user-facing endpoint.
# User uploads → ocr_service.py → Mistral/Tesseract (ephemeral, in-memory only)
# Public corpus → seed_documents.py → Reducto (EUR-Lex PDFs, no personal data)
```

---

## Consequences

### Positive
- Higher parsing quality for scanned PDFs and PDF attachments in the public corpus
- Direct drop-in replacement for `RecursiveCharacterTextSplitter` (chunk_mode: variable = 750-1250 chars, similar to existing 2048/256 config)
- Produces bounding boxes + confidence scores for future quality reporting
- High-value demo artifact for Sprint 2: "3-way OCR benchmark: Mistral vs Tesseract vs Reducto"
- 15K free Standard credits are sufficient for the ~165-document EN+DE+FR corpus

### Negative / Risks
- **New external SaaS dependency** for the seeding pipeline (mitigated: public corpus only, no PII)
- **Standard tier uses US subprocessors by default** — for EUR-Lex public documents this is acceptable (zero personal data); [EU data residency](https://docs.reducto.ai/security/eu-data-residency) + [ZDR](https://llms.reducto.ai/trust-center-on-prem-zero-retention-hipaa-soc2-baa) on Growth/Enterprise tiers are documented for future commercial scaling
- **Credit monitoring needed** — if corpus grows beyond 15K docs, track credit usage or switch tiers (current ~165-495 credits for full EN+DE+FR corpus fits free tier)
- **`reductoai>=0.22.0`** (not `>=1.0.0`) — the PyPI line is 0.x; `>=1.0.0` was unresolvable at time of implementation

### Neutral
- Feature flag means zero behavior change for existing runs (ENABLE_REDUCTO=false by default)
- No changes to production user-facing endpoints or CI pipeline

---

## Related

- [ADR-006](ADR-006-pdf-extraction-license.md) — PDF extraction library (pypdfium2 for in-house, AGPL via BabelDOC remains)
- [ADR-008](ADR-008-licensing-strategy.md) — Open core licensing (Reducto is external SaaS, not bundled — no AGPL implication)
- `scripts/seed_documents.py` — Corpus seeding script (ENABLE_REDUCTO flag added here)
- `backend/app/services/ocr_service.py` — User-upload OCR (unchanged; Reducto's public-corpus path does not touch this file)
- GitHub Issue: #15 — "Integrate Mistral OCR + Tesseract fallback" (Sprint 2)
- GitHub Issue: #37 — "OCR quality report — Mistral vs Tesseract vs Reducto (3-way)" (Sprint 2)
- GitHub Issue: #26 — "Security review & GDPR compliance check" (Sprint 3)
