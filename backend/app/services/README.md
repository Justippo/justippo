# Backend Services

## `classification_service.py` — propella-1 document classification

`classification_service.classify_document(text, mime_type)` enriches OCR output immediately after extraction and before RAG ingestion.

Returned `DocumentClassification` fields:
- `document_type`
- `language_code`
- `quality_score` (`0.0`–`1.0`)
- `geographic_relevance`
- `safety_flags`
- `confidence`

Runtime behavior:
- `PROPELLA_ENABLED=false` returns a deterministic fallback using dependency-free EN/DE/FR language hints.
- `PROPELLA_BASE_URL` routes to the local SGLang/llguidance sidecar (`/v1/chat/completions`).
- If `PROPELLA_BASE_URL` is empty, the service routes through Cloudflare AI Gateway via `get_gateway_url()`.
- Timeout is capped at 5 seconds; failures log a warning and return a fallback classification.
- No disk writes; all OCR text and classification payloads stay in memory.

RAG metadata keys added by upload flow:
- `doc_type`
- `lang_code`
- `quality_score`
- `safety_flags`
