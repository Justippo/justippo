# PII Redaction Sidecar

Docker sidecar that detects and redacts PII from text using Microsoft Presidio + spaCy NER.

## Purpose

GDPR Article 5(1)(c) data minimisation — redact personal data (names, addresses, dates, ID numbers) from OCR-extracted text **before** it reaches external translation backends (CF Workers AI, Mistral).

## Architecture

Follows the BabelDOC sidecar pattern (ADR-012):
- HTTP boundary — Presidio/spaCy never imported in the Pyodide backend
- Docker container, isolated from the Cloudflare Worker
- Feature-flagged via `PII_REDACTION_ENABLED` (default: `false`)

## API

### `POST /redact`

```json
{
  "text": "John Smith lives at 123 Main St, Berlin.",
  "language": "en",
  "entities": ["PERSON", "LOCATION"]
}
```

Response:

```json
{
  "redacted_text": "[PERSON] lives at [LOCATION], [LOCATION].",
  "entity_count": 3,
  "entity_types": ["LOCATION", "PERSON"],
  "processing_time_ms": 45.2
}
```

### `GET /health`

```json
{
  "status": "ok",
  "service": "pii-redactor",
  "version": "0.1.0"
}
```

## Running

```bash
docker compose --profile pii-redaction up pii-redactor -d
```

Port: 8760