# Backend Conventions

Python / FastAPI / Cloudflare Python Worker (Pyodide)

---

## Key Patterns

- **FastAPI routers** in `app/api/v1/endpoints/*.py` — one file per resource
- **Services** in `app/services/*.py` — business logic, never directly in endpoints
- **Models** in `app/models/*.py` — Pydantic request/response schemas
- **Integrations** in `app/integrations/*/` — third-party adapters (cloudflare, matrix, ocr, rag, translation)
- **Core** in `app/core/` — config, middleware, dependencies
- **Tests** in `tests/unit/` and `tests/integration/` — test files mirror `app/` structure

## Testing

```bash
uv run pytest tests/path/to/test.py::test_name -v    # single test
uv run pytest tests/ -v                                # all tests
uv run pytest tests/unit/ -v                           # unit only
```

- Use `pytest-asyncio` for async tests
- Mock external services (OCR, translation, RAG) in unit tests
- Integration tests hit real endpoints with test fixtures

## Deploy

```bash
uv sync --group workers   # install deploy deps only
npx wrangler deploy       # deploy to Cloudflare
```

## API Endpoints

| Method | Path | File | Notes |
|--------|------|------|-------|
| GET | `/api/v1/health` | `health.py` | Liveness + readiness |
| POST | `/api/v1/documents/` | `documents.py` | Multipart upload (PDF/DOCX/PNG) |
| GET | `/api/v1/search/` | `search.py` | SSE streaming search |
| POST | `/api/v1/translate/` | `translate.py` | Layout-preserving translation |
| POST/POST/GET | `/api/v1/exchange/` | `exchange.py` | Matrix protocol (feature-flagged) |

## Pyodide Gotchas

- **No disk writes** — `tempfile.TemporaryDirectory()` fails silently. Use `io.BytesIO` for in-memory processing.
- **No subprocess** — `subprocess.run()` not available. OCR models must be HTTP-based.
- **Cold start** — ~2-3s on first request. Warm-up pings mitigate this.
- **Dep groups** — `pyproject.toml` has `workers`, `rag`, `ocr`, `translation` groups. `workers` is the minimum for deploy.
