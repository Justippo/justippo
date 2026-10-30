"""HTTP wrapper for the PII redaction sidecar.

This service is intentionally isolated from the Cloudflare Python Worker backend.
It owns the Presidio + spaCy dependencies and exposes only an HTTP contract.
Follows the BabelDOC sidecar pattern (ADR-012).
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EvidenceEU PII Redaction Sidecar",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Engine initialization (lazy-loaded on first request to keep cold start fast)
# ---------------------------------------------------------------------------

_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None

# Default entities for EU legal/administrative/HR documents
DEFAULT_ENTITIES = [
    "PERSON",
    "LOCATION",
    "DATE_TIME",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "NRP",  # National registration number / ID
    "URL",
]


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RedactRequest(BaseModel):
    """Request payload for POST /redact."""

    text: str = Field(min_length=1, max_length=500_000)
    language: str = Field(default="en", min_length=2, max_length=8)
    entities: list[str] | None = None  # None = use defaults


class HealthResponse(BaseModel):
    """Health payload for Docker readiness checks."""

    status: str
    service: str
    version: str


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def error_response(
    *,
    code: str,
    message: str,
    details: str | None = None,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": code in {"TIMEOUT", "SERVICE_UNAVAILABLE"},
                "details": details,
            }
        },
    )


def summarize_validation_errors(exc: RequestValidationError) -> str:
    summaries = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "Invalid value")
        summaries.append(f"{location}: {message}")
    return "; ".join(summaries)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return error_response(
        code="INVALID_INPUT",
        message="Request payload failed validation",
        details=summarize_validation_errors(exc),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return sidecar readiness for Docker health checks."""
    return HealthResponse(
        status="ok",
        service="pii-redactor",
        version=app.version,
    )


@app.post("/redact")
def redact(request: RedactRequest) -> JSONResponse:
    """Detect and redact PII entities from text.

    Sync endpoint (not async) — Presidio's analyze() and anonymize() are
    blocking CPU-bound calls. FastAPI runs sync endpoints in a threadpool,
    preventing event-loop blocking.
    """
    start = time.perf_counter()

    try:
        analyzer = _get_analyzer()
        anonymizer = _get_anonymizer()
    except Exception:
        logger.error("Failed to initialize Presidio engines")
        return error_response(
            code="SERVICE_UNAVAILABLE",
            message="PII detection engine is not available",
            status_code=503,
        )

    entities = request.entities if request.entities else DEFAULT_ENTITIES
    language = request.language.strip().lower()

    try:
        results = analyzer.analyze(
            text=request.text,
            entities=entities,
            language=language,
        )
    except Exception:
        logger.error("Presidio analysis failed")
        return error_response(
            code="REDACTION_FAILED",
            message="PII detection failed during analysis",
            status_code=500,
        )

    # Redact using replace operator: [ENTITY_TYPE] for each detected entity.
    operators: dict[str, OperatorConfig] = {}
    entity_types_found = set()
    for result in results:
        entity_types_found.add(result.entity_type)

    # Use a single "replace" operator per entity type with a generic placeholder.
    # This keeps it simple and avoids index tracking complexity in the anonymizer.
    for entity_type in entity_types_found:
        operators[entity_type] = OperatorConfig(
            operator_name="replace",
            params={"new_value": f"[{entity_type}]"},
        )

    try:
        anonymized = anonymizer.anonymize(
            text=request.text,
            analyzer_results=results,
            operators=operators,
        )
        redacted_text = anonymized.text
    except Exception:
        logger.error("Presidio anonymization failed")
        return error_response(
            code="REDACTION_FAILED",
            message="PII redaction failed during anonymization",
            status_code=500,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return JSONResponse(
        status_code=200,
        content={
            "redacted_text": redacted_text,
            "entity_count": len(results),
            "entity_types": sorted(entity_types_found),
            "processing_time_ms": round(elapsed_ms, 2),
        },
    )