# ADR-012: BabelDOC as External HTTP Sidecar Runtime

**Date:** 2026-06-19 (updated 2026-06-25)
**Status:** Accepted — BabelDOC is part of the capstone implementation (not post-capstone). Full layout-preserving PDF translation via DocLayout-YOLO is included. HTTP sidecar pattern maintained for AGPL isolation.
**Deciders:** Mihai Chindriș
**Context source:** ADR-008 (AGPL strategy), ADR-006 (PDF extraction license), BabelDOC GitHub

**Composed reference translation:** ADR-020 defines how this sidecar participates in the proposed
Azure Document Intelligence + BabelDOC PDF reference pipeline. ADR-020 is additive and does not
change this endpoint until its phased implementation is approved and verified.

---

## Context

BabelDOC is a layout-preserving PDF translation engine (AGPL-3.0). It requires:
- Python 3.12+
- PyTorch / DocLayout-YOLO (ONNX runtime)
- Disk I/O for intermediate PDF processing
- Threading for parallel translation workers
- ~2-4 GB RAM minimum for document processing
- OpenAI-compatible LLM endpoint for translation (configurable)

None of these are available in the Pyodide/WASM sandbox used by Cloudflare Python Workers. This is the same fundamental constraint that prevents `sentry-sdk`, `ddtrace`, and `newrelic` from running in our backend — threading, socket, and disk I/O are non-functional in Pyodide.

### Key Findings (2026-06-19)

1. **No native HTTP API**: BabelDOC exposes a CLI and a Python API (`high_level.do_translate_async_stream`). All internal APIs are explicitly marked "not supported for direct use." There is no built-in HTTP server.
2. **AGPL-3.0**: Cannot be imported as a Python module in our MIT-licensed codebase without AGPL propagation. The HTTP boundary is what isolates the licenses.
3. **PDFMathTranslate-next**: Community wrapper that provides a WebUI + self-deployment path around BabelDOC. Could serve as the sidecar's base image.

---

## Decision

**BabelDOC runs as an external Docker sidecar, called exclusively over HTTP from the FastAPI backend. It is NEVER imported as a Python module.**

### Architecture

```
Cloudflare Worker (Pyodide)
  └── FastAPI (backend/app/)
        └── babeldoc_adapter.py  ← httpx POST (async)
              │
              ▼ HTTP (localhost:8750 or Docker network)
        ┌─────────────────────────┐
        │  BabelDOC Sidecar       │
        │  (Docker container)     │
        │  - Python 3.12          │
        │  - BabelDOC + deps      │
        │  - Thin HTTP wrapper    │
        │  - AGPL-3.0 isolated    │
        └─────────────────────────┘
```

### Why NOT a Python Import

| Constraint | Same as |
|-----------|---------|
| Threading (BabelDOC uses thread pools) | `sentry-sdk` |
| Socket (httpx for LLM calls) | `ddtrace` |
| Disk I/O (PDF intermediate files) | N/A (unique to BabelDOC) |
| AGPL license propagation | Unique legal constraint |

---

## Sidecar API Contract (Authoritative Spec)

### Endpoint

```
POST /translate
Content-Type: application/json
```

### Request

```json
{
  "source_lang": "en",
  "target_lang": "de",
  "document_b64": "<base64-encoded PDF bytes>",
  "preserve_layout": true,
  "glossary_csv_b64": null,
  "options": {
    "qps": 4,
    "max_pages": null,
    "watermark": false
  }
}
```

### Success Response (HTTP 200)

```json
{
  "translated_b64": "<base64-encoded translated PDF>",
  "detected_lang": "en",
  "processing_time_ms": 45230,
  "layout_preserved": true,
  "pages_processed": 5,
  "warnings": []
}
```

### Error Response (HTTP 4xx/5xx)

```json
{
  "error": {
    "code": "TRANSLATION_FAILED",
    "message": "BabelDOC processing failed: insufficient memory for 200-page document",
    "retryable": false,
    "details": null
  }
}
```

### Error Codes

| Code | HTTP | Retryable | Meaning |
|------|------|-----------|---------|
| `TRANSLATION_FAILED` | 500 | false | BabelDOC internal error |
| `TIMEOUT` | 504 | true | Processing exceeded timeout |
| `INVALID_INPUT` | 400 | false | Bad PDF or unsupported language |
| `SERVICE_UNAVAILABLE` | 503 | true | Sidecar starting up / overloaded |
| `UNSUPPORTED_LANGUAGE` | 422 | false | Language pair not supported |

### Timeout Strategy

- Default timeout: 120 seconds (configurable via `BabelDocRequest.timeout_seconds`)
- BabelDOC can take 30-60s for a 10-page document, 2-5 minutes for 50+ pages
- Client-side: exponential backoff (2s → 4s → 8s) on 503/504, max 3 attempts
- Sidecar-side: internal timeout at 300s (kill processing, return 504)

---

## Deployment Requirements

| Requirement | Value |
|-------------|-------|
| Base image | `python:3.12-slim` + BabelDOC via pip |
| Memory floor | 2 GB (4 GB recommended for >20-page docs) |
| CPU | 2+ cores recommended; no GPU required (ONNX CPU) |
| Disk | 500 MB for models + temp space for PDF processing |
| Port | 8750 (configurable) |
| Health check | `GET /health` → `{"status": "ok"}` |
| Startup time | 15-30s (model loading on first request) |

---

## Block Conditions (must clear before implementation)

1. **#42 resolved**: Team confirms AGPL Open Core strategy (ADR-008 approved)
2. **Docker image available**: Either community PDFMathTranslate-next image or custom thin wrapper
3. **the integration tests**: EN↔DE/FR sample documents validated against sidecar contract

### Runtime Status (updated 2026-07-16)

The repository includes the HTTP sidecar runtime in `sidecars/babeldoc/`. It
provides:

- Docker Compose profile `babeldoc`
- `GET /health`
- `POST /translate` request validation and BabelDOC CLI execution
- ADR-012 error envelopes
- glossary CSV contract validation
- Dockerized contract tests wired into CI
- request-local temporary storage with cleanup on success and failure
- a mode `0600` temporary BabelDOC config so gateway credentials do not appear
  in the subprocess argument list

The runtime uses an OpenAI-compatible model exclusively through the approved
Cloudflare AI Gateway endpoint. Live infrastructure configuration remains a
deployment concern; missing configuration returns `SERVICE_UNAVAILABLE`.

Legal and operational references:

- `sidecars/babeldoc/AGPL-NOTICE.md`
- `docs/translation/babeldoc-sidecar-runbook.md`

---

## Consequences

### Positive
- AGPL isolation maintained — MIT codebase is safe
- BabelDOC upgrades are decoupled from main app deployments
- Sidecar can scale independently (GPU instance for heavy workloads)
- Same pattern as Sentry/Datadog forwarders — team already understands it

### Negative
- Added infrastructure complexity (Docker container management)
- Network latency between Worker and sidecar (~1-5ms on same host)
- Cold start on first request (15-30s model loading)

### Neutral
- Capstone demo uses BabelDOC sidecar for full layout-preserving PDF translation. CF Workers AI `m2m100-1.2b` remains available as a text-only fallback for Pyodide-safe operation.

---

## Related

- [ADR-008](ADR-008-licensing-strategy.md) — AGPL Open Core licensing strategy
- [ADR-006](ADR-006-pdf-extraction-license.md) — PDF extraction license
- [ADR-021](ADR-021-composed-fillable-pdf-translation.md) — composed PDF reference translation
- GitHub: [#42](https://github.com/chindris-mihai-alexandru/evidence-eu/issues/42) — Licensing decision
- GitHub: [#45](https://github.com/chindris-mihai-alexandru/evidence-eu/issues/45) — BabelDOC sidecar runtime
- BabelDOC upstream: [funstory-ai/BabelDOC](https://github.com/funstory-ai/BabelDOC)
