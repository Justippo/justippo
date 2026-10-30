# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Translate Endpoint — Document Translation via CF Workers AI (Sprint 2)

Responsibilities:
- Accept a document_id, source/target language, and optional pre-extracted pages
- Delegate to TranslationService (CF Workers AI m2m100-1.2b)
- Return job_id, status, and translated pages
- GET /status/{job_id} for job polling (Sprint 2: in-memory store)

Sprint 3: replace in-memory job store with D1, add SSE progress streaming.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.db.d1_client import D1Client
from app.models.audit import AuditAction
from app.models.document_explanation import DocumentExplanation
from app.models.pdf_reference_translation import PDFReferenceTranslationResult
from app.models.translation_quality import TranslationQualityReport
from app.repositories.glossary_repo import GlossaryRepo
from app.services.audit_service import AuditService
from app.services.classification_service import (
    DocumentClassification,
    default_classification,
)
from app.services.document_explanation_service import (
    analysis_from_extracted_pages,
    explain_document,
    extract_document_requirements,
)
from app.services.pdf_reference_translation_service import (
    PDFReferenceTranslationError,
    translate_pdf_reference,
)
from app.services.translation_service import TranslationService

router = APIRouter()
_svc = TranslationService()

# UUID4 format regex (RFC 4122 variant)
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class TranslationRequest(BaseModel):
    document_id: str
    source_language: str = Field(default="auto", description="ISO 639-1 or 'auto'")
    target_language: Literal["en", "de", "fr"] = Field(description="ISO 639-1: en | de | fr")
    preserve_layout: bool = True
    pages: list[dict[str, Any]] | None = Field(
        default=None,
        description="Pre-extracted OCR pages: [{page: int, text: str}]. "
        "If omitted, translation runs on empty content (stub mode).",
    )
    classification: DocumentClassification | None = None
    include_document_explanation: bool = False

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, v: str) -> str:
        """Validate document_id as UUID4 format (GDPR Domain 7 — input validation)."""
        if not _UUID4_RE.match(v):
            raise ValueError("document_id must be a valid UUID4")
        return v


class TranslationSection(BaseModel):
    index: int
    source_text: str
    translated_text: str
    status: Literal["translated", "failed"] = "translated"
    attempts: int = Field(default=1, ge=1, le=2)
    error_code: Literal["TRANSLATION_SECTION_FAILED"] | None = None


class TranslatedPage(BaseModel):
    page: int
    text: str
    sections: list[TranslationSection] = Field(default_factory=list)
    status: Literal["translated", "partial", "failed"] = "translated"


class TranslationResponse(BaseModel):
    job_id: str
    status: str  # queued | processing | done | failed
    translated_pages: list[TranslatedPage] = Field(default_factory=list)
    quality_report: TranslationQualityReport | None = None
    glossary_terms_applied: int = Field(default=0, ge=0)
    document_explanation: DocumentExplanation | None = None
    redaction_metadata: dict[str, Any] | None = None
    error: str | None = None
    download_url: str | None = None  # Sprint 3: R2 signed URL


def _validated_pages(pages: list[dict[str, object]]) -> list[TranslatedPage]:
    return [TranslatedPage.model_validate(page) for page in pages]


async def _refresh_document_explanation(
    payload: TranslationRequest,
) -> DocumentExplanation | None:
    if not payload.include_document_explanation or not payload.pages:
        return None
    analysis = analysis_from_extracted_pages(payload.pages)
    combined_text = "\n\n".join(str(page.get("text", "")) for page in payload.pages)
    classification = payload.classification or default_classification(combined_text)
    try:
        return await explain_document(
            analysis,
            classification,
            language=payload.target_language,
        )
    except Exception:
        return DocumentExplanation(
            document_type=classification.document_type,
            language=payload.target_language,
            requirements=extract_document_requirements(analysis),
            legal_context_status="unavailable",
            citations=[],
            warnings=["DOCUMENT_EXPLANATION_UNAVAILABLE"],
        )


class LanguagePairsResponse(BaseModel):
    pairs: list[dict[str, str]]


@router.post(
    "/pdf-reference",
    response_model=PDFReferenceTranslationResult,
    status_code=200,
)
async def translate_pdf_reference_document(
    request: Request,
    file: Annotated[UploadFile, File(description="PDF to translate as a reference copy")],
    source_language: Annotated[str, Form(description="Source language: en | de | fr")],
    target_language: Annotated[str, Form(description="Target language: en | de | fr")],
    expected_page_count: Annotated[
        int,
        Form(
            ge=1,
            le=20,
            description="Page count returned by the preceding upload analysis",
        ),
    ],
) -> PDFReferenceTranslationResult:
    """Translate and explain a PDF without retaining or modifying the original."""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PDF",
                "message": "PDF reference translation accepts PDF files only",
                "retryable": False,
            },
        )

    document_bytes = await file.read()
    try:
        result = await translate_pdf_reference(
            document_bytes,
            source_language,
            target_language,
            expected_page_count,
        )
        from app.integrations.posthog import capture_event  # noqa: PLC0415

        await capture_event(
            "pdf_reference_translated",
            distinct_id=getattr(request.state, "posthog_distinct_id", ""),
            properties={
                "source_language": source_language,
                "target_language": target_language,
                "page_count": expected_page_count,
            },
            session_id=getattr(request.state, "posthog_session_id", None),
        )
        return result
    except PDFReferenceTranslationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail.model_dump(),
        ) from exc
    finally:
        del document_bytes


@router.post("/", response_model=TranslationResponse, status_code=200)
async def translate_document(
    request: Request,
    payload: TranslationRequest,
) -> TranslationResponse:
    """
    Translate a document's extracted text to the target language.

    Uses Cloudflare Workers AI @cf/meta/m2m100-1.2b (EN/DE/FR).
    Pass `pages` from a prior OCR call; omit to run in stub mode (empty result).
    """
    job = await _svc.translate(
        document_id=payload.document_id,
        source_language=payload.source_language,
        target_language=payload.target_language,
        pages=payload.pages,
        preserve_layout=payload.preserve_layout,
        glossary_repo=GlossaryRepo(D1Client.from_scope(request.scope)),
    )
    document_explanation = await _refresh_document_explanation(payload)

    # CONFLICT RESOLVED: Bot added PostHog capture, main added PII redaction
    # audit trail. Both are preserved — PostHog event first, then audit log.
    from app.integrations.posthog import capture_event  # noqa: PLC0415

    await capture_event(
        "document_translated",
        distinct_id=getattr(request.state, "posthog_distinct_id", ""),
        properties={
            "source_language": payload.source_language,
            "target_language": payload.target_language,
            "page_count": len(payload.pages) if payload.pages else 0,
            "glossary_terms_applied": job.glossary_terms_applied,
            "has_quality_report": job.quality_report is not None,
            "status": job.status,
        },
        session_id=getattr(request.state, "posthog_session_id", None),
    )

    # Persist PII redaction metadata to the D1 audit trail (GDPR Art. 30).
    # Metadata only: entity count, types, succeeded flag — NO entity values.
    if job.redaction_metadata and job.redaction_metadata.get("enabled"):
        audit = AuditService(
            d1=D1Client.from_scope(request.scope),
            jurisdiction=settings.DATA_RESIDENCY_REGION,
        )
        await audit.log_event(
            actor_id=request.headers.get("X-User-Id", "anonymous"),
            action=AuditAction.TRANSLATION_REDACTED,
            resource_type="document",
            resource_id=payload.document_id,
            metadata={
                "job_id": job.job_id,
                "source_language": payload.source_language,
                "target_language": payload.target_language,
                "entity_count": job.redaction_metadata.get("total_entities", 0),
                "entity_types": job.redaction_metadata.get("entity_types", []),
                "succeeded": job.redaction_metadata.get("succeeded", False),
            },
        )

    return TranslationResponse(
        job_id=job.job_id,
        status=job.status,
        translated_pages=_validated_pages(job.translated_pages),
        quality_report=job.quality_report,
        glossary_terms_applied=job.glossary_terms_applied,
        document_explanation=document_explanation,
        redaction_metadata=job.redaction_metadata,
        error=job.error,
    )


@router.get("/status/{job_id}", response_model=TranslationResponse)
async def get_translation_status(job_id: str) -> TranslationResponse:
    """Poll translation job status by job_id."""
    job = await _svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Translation job '{job_id}' not found.")
    return TranslationResponse(
        job_id=job.job_id,
        status=job.status,
        translated_pages=_validated_pages(job.translated_pages),
        quality_report=job.quality_report,
        glossary_terms_applied=job.glossary_terms_applied,
        error=job.error,
    )


@router.get("/languages", response_model=LanguagePairsResponse)
async def list_supported_languages() -> LanguagePairsResponse:
    """Return all supported source→target language pairs."""
    pairs = await _svc.get_supported_language_pairs()
    return LanguagePairsResponse(pairs=pairs)
