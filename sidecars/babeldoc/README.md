# BabelDOC Sidecar

Isolated HTTP wrapper for the BabelDOC reference-PDF translation runtime.

The Cloudflare Python Worker backend must never import BabelDOC directly. This
sidecar owns the AGPL dependency and exposes the ADR-012 HTTP contract over
`POST /translate`.

Legal/ops references:

- `sidecars/babeldoc/AGPL-NOTICE.md`
- `docs/translation/babeldoc-sidecar-runbook.md`

## Local Run

```bash
docker compose --profile babeldoc up --build babeldoc
```

Health check:

```bash
curl http://localhost:8700/health
```

Run sidecar contract tests:

```bash
make test-babeldoc-sidecar
```

Equivalent Docker commands:

```bash
docker compose --profile babeldoc build babeldoc
docker run --rm evidence-eu-babeldoc python -m unittest discover -s tests -v
```

`/translate` validates the request, creates a request-local workspace, invokes
the pinned BabelDOC CLI, returns the translated reference PDF, and deletes the
workspace on success or failure.

The runtime requires three server-side variables:

```text
BABELDOC_OPENAI_BASE_URL=<Cloudflare AI Gateway /compat endpoint>
BABELDOC_OPENAI_API_KEY=<gateway token>
BABELDOC_OPENAI_MODEL=<OpenAI-compatible model identifier>
```

The API key is written to a mode `0600` request-local BabelDOC config rather
than exposed in the subprocess argument list. The config is removed with the
request workspace.

## Glossary Contract

`glossary_csv_b64` is optional. When present, it must be base64-encoded UTF-8
CSV with these required columns:

```csv
term_en,term_de,term_fr
residence permit,Aufenthaltserlaubnis,titre de séjour
```

The sidecar writes the decoded CSV to the request workspace and passes it to
BabelDOC as a glossary file.

## Error Contract

All `/translate` failures return the ADR-012 envelope shape:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Request payload failed validation",
    "retryable": false,
    "details": null
  }
}
```

Retryability is derived from the error code:

| Code | HTTP | Retryable |
|------|------|-----------|
| `TRANSLATION_FAILED` | 500 | false |
| `TIMEOUT` | 504 | true |
| `INVALID_INPUT` | 400 | false |
| `SERVICE_UNAVAILABLE` | 503 | true |
| `UNSUPPORTED_LANGUAGE` | 422 | false |
