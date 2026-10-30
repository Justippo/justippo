# EvidenceEU — Backend API for Wireframes

**Author:** Mihai Chindriș (Backend)
**Audience:** Frontend wireframes, Translation QA
**Date:** 2026-06-19
**Data shapes source of truth:** `docs/demo/api-contracts.md`
**Status:** LIVE — reference this doc when sketching wireframe states

> This document maps API responses to specific UI states.
> Request/response schemas are defined once in `api-contracts.md` and
> referenced here by section number. Do NOT redefine schemas here.

---

## Section 1: Upload Flow — Wireframe Data Shapes

Reference: `api-contracts.md §1` for full request/response schema.

### 1.1 Component States

| UI State | Trigger | What to Show |
|----------|---------|-------------|
| **idle** | Page load | File picker, drag-drop zone, 10 MB limit badge, language selector for `target_lang` |
| **uploading** | File selected, POST in flight | Progress bar (indeterminate), filename, "Uploading…" |
| **processing** | POST returned 200, OCR running | Spinner + "Extracting text…", estimated wait (3–8s) |
| **complete** | Response body received | Confidence badge, language chip, page count, preview text |
| **error** | 4xx/5xx response | Error banner with `error_code` + `message` + retry button (if `retryable: true`) |

**Sprint 2 upload form note:** The `POST /api/v1/documents/` endpoint requires both `file` and `target_lang` form fields. the upload component must include a language picker (EN/DE/FR) whose value is sent as `target_lang`. This value is accepted but not yet wired to the pipeline (Sprint 3 target).

### 1.2 Fields the Component Reads at Each State

```
// complete state — fields consumed by the upload result card
// ACTUAL Sprint 2 response shape (see api-contracts.md §1)
{
  doc_id: string,            // pass to translate endpoint as document_id
  status: string,            // "processed"
  ephemeral: boolean,        // always true
  page_count: number,        // show as "2 pages"
  pages: [{                  // per-page OCR results
    page: number,
    text: string,            // show first 200 chars of page 1 as preview
    confidence: number|null  // show avg as "Quality: 92%" badge (null when Tesseract)
  }]
}
```

```
// error state — Sprint 2 actual (FastAPI default envelope)
{
  detail: string        // human-readable error, show in error banner
}

// Sprint 3 target — structured envelope
// { error_code: string, message: string, retryable: boolean }
// For now, check non-2xx status and display `detail`.
```

### 1.3 Concern: "OCR complete" state

The OCR complete card must show:
- **Confidence score** → field: `confidence` (0.0–1.0, display as %) — indicates scan quality
- **Detected language** → infer from source_lang in subsequent translate response; OCR endpoint does not return detected_language directly in Sprint 2
- **Page count** → field: `page_count`

*QA note:* If confidence < 0.7, the card should show a warning: "Low scan quality — translation accuracy may be reduced." The threshold is validated.

---

## Section 2: SSE Search Results — Wireframe Data Shapes

Reference: `api-contracts.md §3` for full SSE event schema and connection parameters.

### 2.1 Each SSE Event Type Mapped to a UI State

**Sprint 2 (actual) — flat schema from HindsightRAGService:**

| Event type | What the UI renders |
|------------|-------------------|
| `result` | **Citation card appears** — show `text` excerpt, `rank` as position, `type` as chip |
| `done` | **Spinner stops**, notify user results complete |
| `error` | **Error banner**: `message` text + "Try again" button |

**Sprint 3 (enriched target) — adds `sequence` and separate `citation` events:**

| Event type | `sequence` | What the UI renders |
|------------|-----------|-------------------|
| `result` | 1, 2, 3… | **Citation card appears** — title, snippet, relevance score bar |
| `citation` | after result | **Source chip appended** to previous card — law/directive name, page |
| `done` | final | **Spinner stops**, "Found N results" summary line shown |
| `error` | any | **Error banner**: message + "Try again" button (if `retryable: true`) |

### 2.2 Fields per Event Type

```typescript
// Sprint 2 ACTUAL — "result" event is a raw HindsightRAGService chunk
{
  id: string,            // chunk UUID
  text: string,          // document excerpt — render as card body
  type: string,          // "world" | "experience"
  chunk_id: string,
  entities: object[],    // extracted entities (may be empty)
  rank: number           // relevance rank 1..top_k
}

// Sprint 3 ENRICHED — "result" event
{
  type: "result",
  data: {
    title: string,         // card heading
    snippet: string,       // 2-3 sentence excerpt
    score: number,         // 0.0–1.0, display as relevance bar
    document_id: string    // deep-link to document viewer
  },
  sequence: number
}

// Sprint 3 ENRICHED — "citation" event (append source chip to card)
{
  type: "citation",
  data: {
    source: string,        // e.g. "EU Directive 2003/109/EC"
    page: number,
    relevance: number
  },
  sequence: number
}

// Sprint 3 ENRICHED — "done" event (stop spinner)
{
  type: "done",
  data: {
    total_results: number,
    processing_time_ms: number
  },
  sequence: number
}

// Sprint 3 ENRICHED — "error" event (show banner)
{
  type: "error",
  data: {
    error_code: string,
    message: string,
    retryable: boolean
  },
  sequence: number
}
```

### 2.3 Streaming Sequence — What the User Sees

**Sprint 2 (actual):**
```
t=0ms    User submits query → spinner appears, "Searching…"
t=200ms  "result" event → citation card slides in with text excerpt
t=1200ms "done" event → spinner stops, "Search complete"
```

**Sprint 3 (enriched target):**
```
t=0ms    User submits query → spinner appears, "Searching…"
t=200ms  First "result" event → citation card #1 slides in
t=400ms  Second "result" event → citation card #2 slides in
t=500ms  "citation" event → source chip attaches to card #1
t=800ms  "done" event → spinner stops, "Found 3 results in 0.8s"
```

Progressive rendering: cards appear as events arrive, not all at once.

### 2.4 the SSE Implementation (Next.js App Router, 2026)

Use `EventSource` with `gdpr_consent` query param (browser API cannot send custom headers):

```typescript
'use client'
import { useState, useEffect, useRef } from 'react'

export function useSearchSSE(query: string, lang: string) {
  const [results, setResults] = useState<ResultEvent[]>([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!query) return

    // Sprint 2: no lang param — HindsightRAGService hardcodes lang="en"
    const url = new URL('/api/v1/search/', process.env.NEXT_PUBLIC_API_URL!)
    url.searchParams.set('q', query)
    url.searchParams.set('gdpr_consent', 'accepted')
    url.searchParams.set('top_k', '5')

    const es = new EventSource(url.toString())
    esRef.current = es

    es.addEventListener('result', (e) => {
      setResults(prev => [...prev, JSON.parse(e.data)])
    })
    es.addEventListener('done', () => {
      setDone(true)
      es.close()
    })
    es.addEventListener('error', (e) => {
      const data = JSON.parse((e as MessageEvent).data ?? '{}')
      setError(data.message)
      es.close()
    })
    es.onerror = () => {
      // EventSource auto-reconnects; log but don't crash
      console.warn('SSE connection dropped, browser will retry')
    }

    return () => {
      es.close()  // ← critical: cleanup on unmount prevents zombie connections
    }
  }, [query, lang])

  return { results, done, error }
}
```

Key points for wireframe:
- Show `results` list — new cards appear as array grows
- Show spinner while `!done && !error`
- Show error banner when `error !== null` with retry button
- Deduplicate by `sequence` if reconnect causes duplicate events

### 2.5 Concern: Source Language on Citation Card

The `source` field in citation events contains the document name/law number (e.g. "EU Directive 2003/109/EC"). The source language is not in the SSE event directly in Sprint 2. The frontend should display the `lang` parameter the query was made in as the result language context. Flag if source language labeling is required for QA — will be added to Sprint 3 citation schema if needed.

---

## Section 3: Translation Viewer — Wireframe Data Shapes

Reference: `api-contracts.md §2` for full translate endpoint schema.

### 3.1 translated_text Field Format

- **Format:** Plain UTF-8 text, flowing paragraphs.
- **Not** Markdown, not HTML, not structured XML.
- Tables from the original document are **not preserved** in Sprint 2 (m2m100 limitation). BabelDOC sidecar will add HTML table output in the community tier.
- Whitespace: paragraphs separated by `

`. Single newlines within a paragraph are preserved.

```typescript
// Translation viewer — ACTUAL Sprint 2 response shape
{
  job_id: string,                // for job status polling
  status: string,                // "done" | "failed" | "processing"
  translated_pages: [{           // per-page translations
    page: number,
    text: string                 // plain UTF-8, display in <pre> or whitespace-pre div
  }],
  error: string | null,          // null when status="done"
  download_url: string | null    // Sprint 3: R2 signed URL
}

// Sprint 2 caveat: no glossary_terms_applied count in response.
// Glossary enforcement is validated by inspecting translated text directly.
```

### 3.2 glossary_terms_applied — UI Representation (Sprint 3 Target)

> **Sprint 2 caveat:** `glossary_terms_applied` is NOT in the API response. Glossary enforcement happens silently server-side. The wireframes should reserve space for the badge, but it won't populate in Sprint 2. Glossary enforcement is validated by inspecting translated text for known terms (see §4.3).

When `glossary_terms_applied > 0` (Sprint 3):
- Show a small badge: "✓ 3 terms enforced" (teal/green)
- Tooltip on hover: "Domain-specific legal terminology was corrected by the EvidenceEU glossary."

When `glossary_terms_applied === 0` (Sprint 3):
- No badge shown (no false reassurance)

### 3.3 Concern: ä/ö/ü/ß Rendering

- **Encoding:** All translated text is returned as UTF-8. No escaping, no HTML entities.
- `ä` is sent as U+00E4 (one byte pair: 0xC3 0xA4 in UTF-8)
- `ö` is U+00F6, `ü` is U+00FC, `ß` is U+00DF
- **No special handling needed** in the React component — standard `<div>` or `<pre>` renders these correctly in all modern browsers.
- Set `lang="de"` on the translated text container for correct hyphenation and font shaping.
- Verify in Chrome, Firefox, Safari. BrowserStack CI covers Firefox + WebKit on every main push.

### 3.4 Layout Preservation (Sprint 2 Limitation)

| Document element | Sprint 2 output | Sprint 3+ (BabelDOC) |
|-----------------|----------------|----------------------|
| Regular paragraphs | Preserved as `

` separated text | Same |
| Tables | Flattened to text, column alignment lost | HTML `<table>` |
| Multi-column layout | Text extracted left-to-right | CSS grid |
| Signatures / stamps | Ignored | Image overlay |
| Page headers/footers | Mixed into body text | Separate zone |

Wireframe note: use a scrollable `<pre style="white-space: pre-wrap">` container for Sprint 2. The side-by-side viewer (FR-09) should use equal-width columns with overflow scroll.

### 3.5 truncated Warning Banner

> **Sprint 2 caveat:** `truncated` is NOT in the API response. The only truncation signal is `[truncated for demo]` appended to the translated text. Wireframe should detect this suffix as a heuristic. Sprint 3 adds `truncated: bool` to the response schema.

When `truncated: true` (Sprint 3 target):
- Show amber banner: "⚠ Document was truncated for demo. Full translation available in production mode."
- The translated text will end with `[truncated for demo]` — do NOT strip this; it signals to QA that should not evaluate the tail.

---

## Section 4: DE Language Scenario — Complete Wireframe Data

A complete example of the data flowing through all three wireframe screens for a German-language document processing scenario.

### 4.1 Example: Aufenthaltstitel document

**Upload response (Sprint 2 actual):**
```json
{
  "doc_id": "de-residence-permit-abc123",
  "status": "processed",
  "ephemeral": true,
  "page_count": 1,
  "pages": [
    {
      "page": 1,
      "text": "Aufenthaltstitel\nDieser Aufenthaltstitel berechtigt den Inhaber zum Aufenthalt in der Bundesrepublik Deutschland...",
      "confidence": 0.94
    }
  ]
}
```

**Upload card wireframe state (complete):**
- Title: "Aufenthaltstitel.pdf"
- Quality badge: "94% confidence" (green) — compute as avg of `pages[*].confidence`
- "1 page"
- Preview: first 200 chars of `pages[0].text`

**Translation response (DE→EN):**
```json
{
  "job_id": "job-xyz789",
  "status": "done",
  "translated_pages": [
    {
      "page": 1,
      "text": "Residence Permit\nThis residence permit entitles the holder to reside in the Federal Republic of Germany..."
    }
  ],
  "error": null,
  "download_url": null
}
```

**Translation viewer wireframe state:**
- Left panel: original DE text from `pages[0].text` with `lang="de"` attribute
- Right panel: translated EN text from `translated_pages[0].text`
- Language chips: DE → EN
- Glossary badge: not returned in Sprint 2 response; enforcement is validated manually

**SSE search query (in DE):**
```
GET /api/v1/search/?q=Aufenthaltstitel+verlängern&gdpr_consent=accepted&top_k=5
```

**SSE events sequence (Sprint 2 actual):**
```
event: result
data: {"id":"chunk-abc","text":"Die Verlängerung eines Aufenthaltstitels richtet sich nach §8 AufenthG...","type":"world","chunk_id":"chunk-abc","entities":[],"rank":1}

event: done
data: [DONE]
```

### 4.2 Character Rendering Notes for DE Scenario

| Character | Unicode | Expected display | Font requirement |
|-----------|---------|-----------------|----------------|
| ä (U+00E4) | LATIN SMALL LETTER A WITH DIAERESIS | ä | System font (no special font needed) |
| ö (U+00F6) | LATIN SMALL LETTER O WITH DIAERESIS | ö | System font |
| ü (U+00FC) | LATIN SMALL LETTER U WITH DIAERESIS | ü | System font |
| ß (U+00DF) | LATIN SMALL LETTER SHARP S | ß | System font |

All macOS/Windows/Linux system fonts support these characters. No special font loading required.

**RTL note:** German is a LTR language. No RTL styling needed.
**Hyphenation:** Set `hyphens: auto` on DE text containers with `lang="de"` for correct German compound word breaking.

### 4.3 DE Scenario QA

Section 4 QA ownership:
1. Verify ä/ö/ü/ß render correctly in the viewer (no `?` or `â€`-style encoding artifacts)
2. Verify "Aufenthaltstitel" is used (not "Aufenthaltserlaubnis") in EN→DE translations
3. Verify glossary badge appears and count matches expected replacements
4. Flag any compound word that was incorrectly split or hyphenated in the viewer
