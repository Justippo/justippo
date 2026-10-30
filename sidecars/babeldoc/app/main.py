"""HTTP wrapper bootstrap for the BabelDOC sidecar.

This service is intentionally isolated from the Cloudflare Python Worker backend.
It owns the AGPL BabelDOC dependency and exposes only the ADR-012 HTTP contract.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hmac
import io
import logging
import os
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from starlette.responses import JSONResponse

from app.runtime import (
    BabelDocConfigError,
    BabelDocInvalidInputError,
    BabelDocRuntimeError,
    BabelDocTimeoutError,
    get_runtime_config,
    run_babeldoc_translation,
)

SUPPORTED_LANGUAGES = {"en", "de", "fr"}
ERROR_STATUS = {
    "TRANSLATION_FAILED": 500,
    "TIMEOUT": 504,
    "INVALID_INPUT": 400,
    "UNAUTHORIZED": 401,
    "SERVICE_UNAVAILABLE": 503,
    "UNSUPPORTED_LANGUAGE": 422,
}
RETRYABLE_ERRORS = {"TIMEOUT", "SERVICE_UNAVAILABLE"}
GLOSSARY_REQUIRED_COLUMNS = {"term_en", "term_de", "term_fr"}
MAX_PDF_BYTES = 10 * 1024 * 1024
PDF_HEADER_SCAN_BYTES = 1024

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EvidenceEU BabelDOC Sidecar",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)


class BabelDocRequest(BaseModel):
    """Request payload accepted by POST /translate."""

    source_lang: str = Field(min_length=2, max_length=8)
    target_lang: str = Field(min_length=2, max_length=8)
    document_b64: str = Field(min_length=1)
    preserve_layout: bool = True
    timeout_seconds: int = Field(default=120, ge=1, le=300)
    glossary_csv_b64: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_lang", "target_lang")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        """Normalize ISO language values used by EvidenceEU."""
        return value.strip().lower()


class HealthResponse(BaseModel):
    """Health payload for Docker and local readiness checks."""

    status: str
    service: str
    version: str


def error_response(
    *,
    code: str,
    message: str,
    details: str | None = None,
) -> JSONResponse:
    """Return the ADR-012 error envelope shape."""
    status_code = ERROR_STATUS[code]
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": code in RETRYABLE_ERRORS,
                "details": details,
            }
        },
    )


def validate_base64_pdf(document_b64: str) -> bytes:
    """Decode and minimally validate a PDF before runtime execution."""
    try:
        document = base64.b64decode(document_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("document_b64 must be valid base64") from exc

    if not document:
        raise ValueError("document_b64 decoded to an empty document")
    if len(document) > MAX_PDF_BYTES:
        raise ValueError("document exceeds the 10 MiB PDF limit")
    if b"%PDF" not in document[:PDF_HEADER_SCAN_BYTES]:
        raise ValueError("document_b64 must contain PDF bytes")

    return document


def validate_glossary_csv(glossary_csv_b64: str | None) -> list[dict[str, str]]:
    """Decode and validate optional glossary CSV bytes.

    The real BabelDOC execution path will write this decoded CSV to a temp file
    and pass it through `--glossary-files`.
    """
    if glossary_csv_b64 is None:
        return []

    try:
        glossary_bytes = base64.b64decode(glossary_csv_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("glossary_csv_b64 must be valid base64") from exc

    if not glossary_bytes:
        raise ValueError("glossary_csv_b64 decoded to an empty CSV")

    try:
        glossary_text = glossary_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("glossary_csv_b64 must decode to UTF-8 CSV") from exc

    reader = csv.DictReader(io.StringIO(glossary_text))
    columns = set(reader.fieldnames or [])
    missing_columns = sorted(GLOSSARY_REQUIRED_COLUMNS - columns)
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"glossary CSV missing required columns: {missing}")

    rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    rows = [row for row in rows if any(row.values())]
    if not rows:
        raise ValueError("glossary CSV must contain at least one term row")

    for index, row in enumerate(rows, start=1):
        empty_terms = [
            column for column in sorted(GLOSSARY_REQUIRED_COLUMNS) if not row.get(column)
        ]
        if empty_terms:
            missing = ", ".join(empty_terms)
            raise ValueError(f"glossary CSV row {index} missing required terms: {missing}")

    return rows


def require_bearer_auth(authorization: str | None) -> str | None:
    """Enforce Authorization: Bearer against BABELDOC_AUTH_TOKEN, when set.

    Returns None when the request is authorized (or no token is configured —
    matching the graceful no-op contract used across the codebase's other
    optional integrations). Returns an error code string otherwise so the
    caller can produce the correct ADR-012 error envelope.

    No-op-safe: an unset BABELDOC_AUTH_TOKEN allows all requests, preserving
    existing local-dev/CI behavior. Production deployments MUST set this
    token per the issue's "do not ship an unauthenticated endpoint" gate.
    """
    expected_token = os.environ.get("BABELDOC_AUTH_TOKEN", "").strip()
    if not expected_token:
        return None

    if not authorization or not authorization.startswith("Bearer "):
        return "UNAUTHORIZED"

    provided_token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided_token, expected_token):
        return "UNAUTHORIZED"

    return None


def summarize_validation_errors(exc: RequestValidationError) -> str:
    """Summarize validation errors without echoing request input."""
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
    """Normalize FastAPI/Pydantic validation errors to the ADR-012 envelope."""
    return error_response(
        code="INVALID_INPUT",
        message="Request payload failed validation",
        details=summarize_validation_errors(exc),
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return process liveness only — does NOT verify configuration or the
    babeldoc CLI. Do not gate production routing on this alone; use /ready.
    """
    return HealthResponse(
        status="ok",
        service="babeldoc-sidecar",
        version=app.version,
    )


# DRY: shared dependency check reused by both /health (liveness only, no
# probes) and /ready (full readiness including reachability).
def _check_dependencies(*, probe_llm_endpoint: bool) -> tuple[dict[str, bool], list[str]]:
    """Run the readiness checks and return (checks, errors).

    probe_llm_endpoint=False skips the network HEAD request — used when a
    caller only needs the cheap, local checks (configuration + executable).
    """
    checks: dict[str, bool] = {}
    errors: list[str] = []

    try:
        config = get_runtime_config()
        checks["configuration"] = True
    except BabelDocConfigError as exc:
        config = None
        checks["configuration"] = False
        errors.append(str(exc))

    import shutil  # noqa: PLC0415 — lazy import, only needed for this probe

    babeldoc_path = shutil.which("babeldoc")
    checks["babeldoc_executable"] = babeldoc_path is not None
    if babeldoc_path is None:
        errors.append("babeldoc executable not found on PATH")

    if probe_llm_endpoint:
        checks["llm_endpoint_reachable"] = False
        if config is not None:
            try:
                import httpx  # noqa: PLC0415 — lazy import, only needed for this probe

                with httpx.Client(timeout=2.0) as client:
                    response = client.head(config.openai_base_url)
                # Any response (even 4xx/405 for a HEAD-unsupported endpoint)
                # proves the host is reachable and TLS-terminating correctly.
                # Only a network-level failure means "not reachable".
                checks["llm_endpoint_reachable"] = response.status_code < 500
            except Exception as exc:  # noqa: BLE001 — reachability probe only
                errors.append(f"LLM endpoint unreachable: {exc}")
        else:
            errors.append("LLM endpoint reachability skipped: no configuration")

    return checks, errors


@app.get("/ready")
async def ready() -> JSONResponse:
    """Verify the sidecar can actually serve a translation request.

    Distinct from /health: confirms required env vars are set, the
    `babeldoc` executable is present on PATH, and the configured LLM
    endpoint responds to a lightweight HEAD probe (<2s) — catching auth/
    connectivity misconfigurations at startup rather than mid-translation.
    """
    checks, errors = _check_dependencies(probe_llm_endpoint=True)
    is_ready = all(checks.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"ready": is_ready, "checks": checks, "errors": errors},
    )


@app.post("/translate")
async def translate(
    request: BabelDocRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Validate and execute layout-preserving reference-PDF translation."""
    auth_error = require_bearer_auth(authorization)
    if auth_error is not None:
        return error_response(
            code=auth_error,
            message="Missing or invalid Authorization bearer token",
        )

    if request.source_lang not in SUPPORTED_LANGUAGES:
        return error_response(
            code="UNSUPPORTED_LANGUAGE",
            message=f"Unsupported source language: {request.source_lang}",
        )

    if request.target_lang not in SUPPORTED_LANGUAGES:
        return error_response(
            code="UNSUPPORTED_LANGUAGE",
            message=f"Unsupported target language: {request.target_lang}",
        )

    if request.source_lang == request.target_lang:
        return error_response(
            code="INVALID_INPUT",
            message="source_lang and target_lang must differ",
        )

    try:
        document = validate_base64_pdf(request.document_b64)
    except ValueError as exc:
        return error_response(
            code="INVALID_INPUT",
            message=str(exc),
        )

    try:
        glossary_rows = validate_glossary_csv(request.glossary_csv_b64)
    except ValueError as exc:
        return error_response(
            code="INVALID_INPUT",
            message=str(exc),
        )

    try:
        result = await run_babeldoc_translation(
            document=document,
            glossary_rows=glossary_rows,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            preserve_layout=request.preserve_layout,
            timeout_seconds=request.timeout_seconds,
            options=request.options,
        )
    except BabelDocInvalidInputError as exc:
        return error_response(code=exc.error_code, message=str(exc))
    except BabelDocTimeoutError as exc:
        return error_response(code=exc.error_code, message=str(exc))
    except BabelDocConfigError:
        return error_response(
            code="SERVICE_UNAVAILABLE",
            message="Layout-preserving PDF translation is not configured",
        )
    except BabelDocRuntimeError as exc:
        return error_response(
            code=exc.error_code,
            message="The PDF could not be translated",
        )
    except Exception:
        logger.error("Unexpected BabelDOC runtime failure")
        return error_response(
            code="TRANSLATION_FAILED",
            message="The PDF could not be translated",
        )

    return JSONResponse(
        status_code=200,
        content={
            "translated_b64": result.translated_b64,
            "source_lang": result.source_lang,
            "target_lang": result.target_lang,
            "detected_lang": result.detected_lang,
            "processing_time_ms": result.processing_time_ms,
            "layout_preserved": result.layout_preserved,
            "pages_processed": result.pages_processed,
            "warnings": result.warnings,
        },
    )
