# EvidenceEU API contract

This reference documents the backend contracts consumed by the EvidenceEU frontend. It describes
implemented behavior only. The generated OpenAPI snapshot at `docs/api/openapi.json` remains the
machine-readable source for request and response types.

## Runtime conventions

- Default API origin: `https://evidence-eu-worker.mc146.workers.dev`
- Frontend override: `NEXT_PUBLIC_API_URL`
- API prefix: `/api/v1`
- Supported product languages: English (`en`), German (`de`), and French (`fr`)
- Error responses use FastAPI's JSON envelope: `{"detail": "..."}`

All non-health requests require GDPR consent when `GDPR_CONSENT_REQUIRED=true`:

```http
X-GDPR-Consent: demo
```

Browser `EventSource` cannot set custom headers, so streaming search sends the same token as the
`gdpr_consent` query parameter. Missing consent returns `451 Unavailable For Legal Reasons`.

## Health

Health endpoints are consent-exempt so infrastructure and the frontend can warm and inspect the
service without processing user data.

### `GET /api/v1/health/`

Returns liveness information:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "sprint": 2
}
```

The frontend calls this endpoint silently on application startup. It does not block or replace the
product UI with connection-status copy.

### `GET /api/v1/health/ready`

Returns readiness and dependency status:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "vector_db": "ok",
    "llm_gateway": "ok",
    "database": "ok"
  }
}
```

### `GET /api/v1/health/pipeline`

Returns lightweight configuration checks for OCR, translation, RAG, and glossary components. Each
component reports `healthy`, `degraded`, or `unavailable`; the overall status is `healthy`,
`degraded`, or `unhealthy`.

## Upload and OCR

### `POST /api/v1/documents/`

Accepts a document in memory, performs OCR and classification, and returns page results. Supported
MIME types are PDF, DOCX, and PNG.

```http
Content-Type: multipart/form-data
X-GDPR-Consent: demo
```

Multipart fields:

| Field         | Type   | Required | Description                         |
| ------------- | ------ | -------: | ----------------------------------- |
| `file`        | binary |      yes | PDF, DOCX, or PNG document          |
| `target_lang` | string |      yes | Requested ISO 639-1 target language |

Successful response:

```json
{
  "doc_id": "8cde5a13-330a-46f7-9e63-79a7e54631a0",
  "status": "processed",
  "ephemeral": true,
  "page_count": 1,
  "pages": [
    {
      "page": 1,
      "text": "Extracted document text",
      "confidence": 0.94
    }
  ],
  "classification": {
    "document_type": "residence_permit",
    "language_code": "en",
    "quality_score": 0.94,
    "geographic_relevance": ["DE"],
    "safety_flags": [],
    "confidence": 0.94
  }
}
```

The uploaded byte buffer is released after processing. The frontend keeps the returned OCR pages in
the browser session only so they can be sent to translation.

Common errors:

- `422` for an unsupported MIME type or invalid multipart request
- `451` when required consent is missing
- `500` when OCR extraction fails

## Translation

### `POST /api/v1/translate/`

Translates OCR pages between English, German, and French. `document_id` must be a UUID4.

```json
{
  "document_id": "8cde5a13-330a-46f7-9e63-79a7e54631a0",
  "source_language": "en",
  "target_language": "de",
  "preserve_layout": true,
  "pages": [
    {
      "page": 1,
      "text": "The residence permit is valid for five years."
    }
  ]
}
```

Successful response:

```json
{
  "job_id": "f76d5dd2-6de2-41e6-94ca-f62b203ed213",
  "status": "done",
  "translated_pages": [
    {
      "page": 1,
      "text": "Die Aufenthaltserlaubnis ist fünf Jahre gültig.",
      "sections": [
        {
          "index": 0,
          "source_text": "The residence permit is valid for five years.",
          "translated_text": "Die Aufenthaltserlaubnis ist fünf Jahre gültig."
        }
      ]
    }
  ],
  "error": null,
  "download_url": null
}
```

Each OCR page is split at paragraph or sentence boundaries and translated as bounded sections. The
`sections` array preserves source-to-target alignment for readable rendering. The page-level `text`
field remains the ordered section translations joined together, preserving compatibility with
existing clients and stored jobs that do not contain `sections`.

Related endpoints:

- `GET /api/v1/translate/status/{job_id}` returns the same response shape.
- `GET /api/v1/translate/languages` returns supported source-target pairs.

### `POST /api/v1/translate/pdf-reference`

Accepts an unprotected PDF as multipart form data with `source_language`, `target_language`, and
the preceding upload response's `expected_page_count`.
Supported languages are `en`, `de`, and `fr`, and the pair must differ. The request runs the
required Azure structure analysis and BabelDOC layout-preserving translation stages, then returns
the translated PDF inline as base64 together with classification and a citation-grounded document
explanation.

The response explicitly identifies the artifact as an ephemeral reference copy, confirms the
browser-held original remains unchanged, and states that form filling is unsupported. The endpoint
is implemented but returns a typed `503 SERVICE_UNAVAILABLE` until both provider integrations are
enabled and configured. Full fields and error codes are documented in
`backend/app/integrations/babeldoc_adapter.py` (source of truth).

## Search

### `GET /api/v1/search/`

Streams multilingual RAG results with Server-Sent Events.

| Query parameter | Type    |                    Required | Default | Description                     |
| --------------- | ------- | --------------------------: | ------- | ------------------------------- |
| `q`             | string  |                         yes | —       | Natural-language query          |
| `top_k`         | integer |                          no | `5`     | Result limit from 1 to 50       |
| `language`      | string  |                          no | `en`    | `en`, `de`, or `fr`             |
| `gdpr_consent`  | string  | yes when consent is enabled | —       | Consent token for `EventSource` |

Example:

```text
GET /api/v1/search/?q=Aufenthaltstitel%20verlängern&language=de&top_k=5&gdpr_consent=demo
```

Implemented event types:

```text
event: result
data: {"id":"chunk-abc","text":"Relevant excerpt","type":"world","chunk_id":"chunk-abc","entities":[],"document_id":"eurlex-32004L0038","source_url":"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038","source_title":"Directive 2004/38/EC","source_language":"en","rank":1}

event: answer_chunk
data: {"text":"Generated answer token"}

event: answer_error
data: {"message":"Answer generation unavailable"}

event: error
data: {"message":"Search service error"}

event: done
data: [DONE]
```

During a slow upstream query, the server sends `: ping` comments every ten seconds. The frontend
ignores comments, closes the stream after `done`, and retries transport or application errors with
2, 4, and 8 second backoff delays, up to three retries.

The search interface treats each query independently. The conversational chat contract below
reuses the same retrieval and answer-generation pipeline without changing this endpoint.

Citation provenance is selected from Hindsight document metadata and recalled source facts.
Seeded EUR-Lex document identifiers also reconstruct their canonical official URL when Hindsight
returns an observation without copied metadata. `source_url` is emitted only for HTTPS sources
hosted on official `europa.eu` domains. Results without verified provenance retain their excerpt
but do not render a citation action in the frontend.

Anonymous search results link to the same-origin `/citation` access page. The page identifies the
official document and offers sign-in and sign-up actions; authentication returns the user to that
citation. Authenticated users can then open the verified official source in a new tab.

For queries containing at least two meaningful terms, results must match at least two terms across
the excerpt, source title, topic, or entities. This precision guard prevents a single generic word
from presenting an unrelated document as a confident answer. Hindsight rank is displayed as rank;
the frontend does not manufacture a confidence percentage when the provider returns none.

## Conversational chat

### `POST /api/v1/chat/`

Streams a citation-grounded conversation over the public EUR-Lex corpus. The browser sends a
bounded recent history with each request; the API does not persist conversations. Required GDPR
consent is supplied through the `X-GDPR-Consent` header.

```json
{
  "message": "What documents do I need?",
  "language": "en",
  "top_k": 5,
  "history": [
    {
      "role": "user",
      "content": "How do I extend a residence permit in Germany?"
    },
    {
      "role": "assistant",
      "content": "The applicable rules depend on your residence category."
    }
  ]
}
```

`message` and each history item are limited to 2,000 characters. At most six prior turns are
accepted. Short follow-up questions are retrieved with the latest user question as context, while
new topics remain independent.

The stream uses the search events above and additionally emits verified model metadata immediately
before the first generated answer token:

```text
event: answer_model
data: {"provider":"public-ai","provider_display":"Public AI","model":"swiss-ai/apertus-8b-instruct","display_name":"Apertus 8B"}
```

The model event describes the runtime answer model; it is never a static claim. Retrieval remains
Hindsight-backed. Mistral OCR and routed translation belong to their respective product flows and
are not attributed to chat answers unless Mistral is actually configured as the answer model.

Generated chat guidance must remain grounded in retrieved sources. It may explain rules, identify
general next steps, list documents supported by the context, or ask one clarifying question. It
must distinguish EU-level rules from national procedures and explicitly report insufficient
evidence. It does not complete, submit, approve, or legally validate forms.

### `POST /api/v1/search/`

Provides a non-streaming alternative with a JSON request:

```json
{
  "query": "How do I renew a residence permit?",
  "language": "en",
  "document_types": [],
  "max_results": 10
}
```

It returns `answer`, `sources`, `query_language`, and `result_languages`.

## Secure exchange

Exchange endpoints are available when `ENABLE_MATRIX_EXCHANGE=true`. When the feature is disabled,
the API returns `403 Forbidden`.

### `POST /api/v1/exchange/rooms`

Creates an encrypted Matrix room and invites at least one participant. Participant identifiers use
the federated Matrix format `@localpart:domain.tld`.

```json
{
  "participants": ["@reviewer:organisation.eu"]
}
```

Successful response:

```json
{
  "room_id": "!permit-review:organisation.eu"
}
```

Common errors:

- `422` when the participant list is empty or an identifier is malformed
- `451` when required consent is missing
- `502` when the Matrix homeserver cannot create the room

### `POST /api/v1/exchange/send`

Sends an in-memory document to a room using multipart fields `room_id` and `file`. The response
contains `event_id`, `room_id`, and `ephemeral: true`. The file byte reference is deleted before the
request completes.

### `GET /api/v1/exchange/rooms/{room_id}/events`

Returns 1–100 recent room events; `limit` defaults to 20. Raw document bodies are removed from the
returned event content.

## Matrix OAuth authentication

ADR-019 authentication is independently gated by `ENABLE_MATRIX_AUTH` on the backend and
`NEXT_PUBLIC_MATRIX_AUTH_PREVIEW_ENABLED` in the frontend build. Production enables both gates;
local environments can leave them disabled when no Matrix OAuth client is configured.

### `GET /api/v1/auth/matrix/status`

Returns `{ "enabled": false, "available": false }` while disabled. When enabled, the API discovers
OAuth metadata from the configured homeserver and reports availability without exposing endpoint
metadata to the browser. An unavailable response includes only a bounded diagnostic `reason`:
`transport_error`, `unsupported`, `unexpected_status`, or `incomplete_metadata`. Provider URLs,
response bodies, and exception messages remain server-only.

### `GET /api/v1/auth/matrix/login`

Discovers the authorization endpoint, stores a single-use five-minute state transaction, and
redirects with Authorization Code + PKCE S256 parameters. The request includes Matrix API and
device scopes. It never includes the PKCE verifier.

### `GET /api/v1/auth/matrix/callback`

Consumes the state exactly once, exchanges the code at the discovered token endpoint, verifies
identity through Matrix `/account/whoami`, and redirects with an opaque `HttpOnly`, `SameSite=Lax`
EvidenceEU session cookie. Matrix tokens are never returned to browser JavaScript. The preview
fails closed in production until encrypted token persistence is approved and activated.

### `GET /api/v1/auth/matrix/session`

Returns only `authenticated`, `user_id`, and `device_id`. Expired sessions attempt the discovered
refresh-token grant and fail closed when refresh is unavailable.

### `POST /api/v1/auth/matrix/logout`

Revokes refresh and access tokens through the discovered revocation endpoint, deletes the local
session, and expires the browser cookie. Revocation failure does not retain the local session.

## Offline sample-data contract

`frontend/public/demo-fallback.json` is a frontend asset, not a backend endpoint. If all health
retries fail and the asset is available, the application renders its upload, translation, and search
results through the same success-state components and displays the standard sample-data banner.
Offline processing does not send document data to the backend.

## Type generation and verification

The typed frontend client is generated from `docs/api/openapi.json` with
`@hey-api/openapi-ts`. Frontend calls use the generated SDK through
`frontend/src/lib/api-generated/index.ts`, which adds consent headers and narrows loosely typed page
objects.

When an endpoint shape changes:

1. regenerate `docs/api/openapi.json` from the FastAPI application;
2. regenerate the TypeScript client;
3. run frontend type, unit, and E2E checks;
4. update this reference in the same pull request.
