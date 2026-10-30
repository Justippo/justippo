# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Documents Endpoint — Upload and Process Documents (Sprint 2)

Responsibilities:
- Accept document uploads (PDF, DOCX, PNG) via multipart/form-data
- Validate file type — reject unsupported types with HTTP 422
- Pass file bytes to OCRService for text extraction
- Return structured document metadata including per-page OCR results
"""

import logging
import math
import uuid
from collections import OrderedDict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.db.d1_client import D1Client
from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    analyze_pdf,
    get_analysis_limits,
)
from app.integrations.babeldoc_adapter import is_babeldoc_ready
from app.models.document_explanation import DocumentExplanation
from app.models.pdf_intake import PDFProcessingProfile
from app.services.classification_service import (
    DocumentClassification,
    classify_document,
    default_classification,
)
from app.services.document_explanation_service import (
    analysis_from_extracted_pages,
    explain_document,
    extract_document_requirements,
)
from app.services.ocr_service import MistralOCRError, OCRPage, OCRService, OCRTierLimitError
from app.services.pdf_intake_service import PDFIntakeError, route_pdf_upload

logger = logging.getLogger(__name__)

router = APIRouter()
_ocr = OCRService()
_rag: Any | None = None  # Test seam; production RAG ingestion wiring remains provider-dependent.
_CLASSIFICATIONS_MAX = 1000
_OCR_RATE_LIMIT_RETRY_AFTER_S = 5
"""Retry-After (s) sent to clients when the upstream gave no hint."""
_classifications: OrderedDict[str, DocumentClassification] = OrderedDict()

# Supported MIME types for uploaded documents
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
    }
)

_ALLOWED_LABEL = "PDF, DOCX, or PNG"
_TARGET_LANGUAGES: tuple[Literal["en", "de", "fr"], ...] = ("en", "de", "fr")


class DocumentUploadResponse(BaseModel):
    doc_id: str
    status: str
    ephemeral: bool
    page_count: int
    pages: list[dict[str, object]]  # [{page: int, text: str, confidence: float|None}]
    classification: DocumentClassification
    target_language: Literal["en", "de", "fr"]
    ocr_method_used: str  # "mistral" | "tesseract" | "azure"
    pdf_processing: PDFProcessingProfile | None = None
    document_explanation: DocumentExplanation | None = None


class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    status: str
    detected_language: str
    page_count: int
    created_at: str
    translations: list[dict[str, str]]  # [{language, status, download_url}]
    classification: DocumentClassification | None = None


async def _try_fetch_azure_analysis(file_bytes: bytes) -> AzureDocumentAnalysis | None:
    """Best-effort Azure analysis fetch; returns None on any provider failure.

    Shared by the OCR fillable-form path and the document-understanding path so
    a single upload never issues two Azure calls for the same PDF bytes — the
    F0 tier has no call budget to spare for a duplicate request.
    """
    try:
        limits = get_analysis_limits()
        if len(file_bytes) > limits.max_bytes:
            return None
        return await analyze_pdf(file_bytes)
    except AzureDocumentIntelligenceError:
        logger.warning("Azure Document Intelligence analysis unavailable", exc_info=False)
        return None


async def _analyze_pdf_for_understanding(
    file_bytes: bytes,
    pages: list[OCRPage],
    *,
    azure_analysis: AzureDocumentAnalysis | None = None,
) -> AzureDocumentAnalysis:
    """Prefer Azure structure analysis and safely retain OCR as a fallback.

    Reuses a pre-fetched ``azure_analysis`` when the caller already obtained
    one (e.g. for a fillable-form upload) instead of fetching a second time.
    """
    analysis = (
        azure_analysis
        if azure_analysis is not None
        else await _try_fetch_azure_analysis(file_bytes)
    )
    if analysis is not None:
        return analysis
    fallback_pages: list[dict[str, object]] = [
        {
            "page": page["page"],
            "text": page["text"],
            "confidence": page["confidence"],
        }
        for page in pages
    ]
    return analysis_from_extracted_pages(fallback_pages)


def _resolve_target_language(
    requested: Literal["en", "de", "fr"],
    source_language: str,
) -> Literal["en", "de", "fr"]:
    """Avoid a no-op language pair after source-language detection."""
    if requested != source_language:
        return requested
    return next(language for language in _TARGET_LANGUAGES if language != source_language)


@router.post("/", response_model=DocumentUploadResponse, status_code=200)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description="Document to process (PDF, DOCX, PNG)")],
    target_lang: Annotated[
        Literal["en", "de", "fr"],
        Form(description="Target translation language (ISO 639-1)"),
    ],
) -> DocumentUploadResponse:
    """
    Accept a document upload, run OCR extraction, and return structured page results.

    - Validates content type; rejects anything other than PDF/DOCX/PNG with HTTP 422.
    - Reads the file entirely into memory; no disk writes occur (EPHEMERAL guarantee).
    - Passes bytes to OCRService (Mistral OCR primary; Azure Document Intelligence, then Tesseract, as fallback).
    - Returns per-page OCR text and confidence scores.
    - target_lang is accepted for downstream translation by TranslationService.
    """
    content_type: str = file.content_type or ""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type '{content_type}'. Only {_ALLOWED_LABEL} files are accepted."
            ),
        )

    # EPHEMERAL: read entirely into memory — no temp files, no disk I/O
    file_bytes: bytes = await file.read()

    pdf_processing: PDFProcessingProfile | None = None
    understanding_analysis: AzureDocumentAnalysis | None = None
    try:
        pdf_processing = route_pdf_upload(file_bytes, content_type)
        is_fillable_form = bool(pdf_processing is not None and pdf_processing.is_fillable_form)
        # Fetch once and share it: a fillable form needs Azure for both OCR text
        # (filled-in field values) and, below, document-understanding structure.
        shared_azure_analysis = (
            await _try_fetch_azure_analysis(file_bytes) if is_fillable_form else None
        )
        pages: list[OCRPage] = await _ocr.process(
            file_bytes,
            content_type,
            is_fillable_form=is_fillable_form,
            azure_analysis=shared_azure_analysis,
        )
        if pdf_processing is not None and not is_babeldoc_ready():
            pdf_processing = PDFProcessingProfile.document_understanding()
            understanding_analysis = await _analyze_pdf_for_understanding(
                file_bytes, pages, azure_analysis=shared_azure_analysis
            )
    except PDFIntakeError as exc:
        from app.integrations.posthog import capture_event  # noqa: PLC0415

        await capture_event(
            "document_upload_failed",
            distinct_id=getattr(request.state, "posthog_distinct_id", ""),
            properties={"content_type": content_type, "error_code": exc.code},
            session_id=getattr(request.state, "posthog_session_id", None),
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except Exception as exc:
        from app.integrations.posthog import capture_event  # noqa: PLC0415

        await capture_event(
            "document_upload_failed",
            distinct_id=getattr(request.state, "posthog_distinct_id", ""),
            properties={"content_type": content_type, "error_type": type(exc).__name__},
            session_id=getattr(request.state, "posthog_session_id", None),
        )
        if isinstance(exc, OCRTierLimitError):
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "ocr_tier_limit_exceeded",
                    "message": "Document exceeds current OCR tier limits.",
                },
            ) from exc
        if isinstance(exc, MistralOCRError) and exc.is_rate_limited:
            # Upstream OCR quota exhausted even after bounded retries: tell the
            # client to retry later (503 + Retry-After) instead of a 500 that
            # leaks the upstream response body.
            retry_after = max(1, math.ceil(exc.retry_after or _OCR_RATE_LIMIT_RETRY_AFTER_S))
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "ocr_rate_limited",
                    "message": "Text extraction is temporarily busy. Please retry shortly.",
                },
                headers={"Retry-After": str(retry_after)},
            ) from exc
        raise HTTPException(
            status_code=500,
            detail=f"OCR extraction failed: {exc}",
        ) from exc
    finally:
        # Explicitly release the in-memory buffer regardless of OCR outcome
        del file_bytes

    doc_id = str(uuid.uuid4())

    # Determine OCR method used: Mistral returns float confidence, Tesseract returns None.
    # Azure Document Intelligence also returns None confidence.
    has_mistral_confidence = any(p.get("confidence") is not None for p in pages)
    if is_fillable_form:
        ocr_method_used = "azure"
    elif has_mistral_confidence:
        ocr_method_used = "mistral"
    else:
        ocr_method_used = "tesseract"

    combined_text = "\n\n".join(str(p["text"]) for p in pages if p.get("text"))
    try:
        classification = await classify_document(combined_text, content_type)
    except Exception as exc:  # defensive: service should already degrade internally
        logger.warning(
            "Document classification failed for doc_id=%s — continuing (%s)", doc_id, exc
        )
        classification = default_classification(combined_text)

    resolved_target_language = _resolve_target_language(
        target_lang,
        classification.language_code,
    )
    document_explanation: DocumentExplanation | None = None
    if understanding_analysis is not None:
        try:
            document_explanation = await explain_document(
                understanding_analysis,
                classification,
                language=resolved_target_language,
            )
        except Exception:
            logger.warning(
                "PDF document explanation failed; returning deterministic requirements",
                exc_info=False,
            )
            document_explanation = DocumentExplanation(
                document_type=classification.document_type,
                language=resolved_target_language,
                requirements=extract_document_requirements(understanding_analysis),
                legal_context_status="unavailable",
                citations=[],
                warnings=["DOCUMENT_EXPLANATION_UNAVAILABLE"],
            )

    if len(_classifications) >= _CLASSIFICATIONS_MAX:
        _classifications.popitem(last=False)
    _classifications[doc_id] = classification

    if _rag is not None and combined_text.strip():
        metadata = {
            "language": classification.language_code,
            "doc_type": classification.document_type,
            "lang_code": classification.language_code,
            "quality_score": classification.quality_score,
            "safety_flags": classification.safety_flags,
        }
        try:
            await _rag.ingest_document(doc_id=doc_id, content=combined_text, metadata=metadata)
        except Exception as exc:
            logger.warning("RAG ingestion failed for doc_id=%s — continuing (%s)", doc_id, exc)

    from app.integrations.posthog import capture_event  # noqa: PLC0415

    await capture_event(
        "document_uploaded",
        distinct_id=getattr(request.state, "posthog_distinct_id", ""),
        properties={
            "page_count": len(pages),
            "content_type": content_type,
            "target_language": resolved_target_language,
            "document_type": classification.document_type,
            "has_explanation": document_explanation is not None,
            "has_pdf_processing": pdf_processing is not None,
        },
        session_id=getattr(request.state, "posthog_session_id", None),
    )

    return DocumentUploadResponse(
        doc_id=doc_id,
        status="processed",
        ephemeral=True,
        page_count=len(pages),
        classification=classification,
        target_language=resolved_target_language,
        ocr_method_used=ocr_method_used,
        pdf_processing=pdf_processing,
        document_explanation=document_explanation,
        pages=[
            {
                "page": p["page"],
                "text": p["text"],
                "confidence": p["confidence"],
            }
            for p in pages
        ],
    )


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(document_id: str, request: Request) -> DocumentMetadata:
    """Retrieve metadata and processing status for an uploaded document."""
    db = D1Client.from_scope(request.scope)
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    doc = await db.fetch_one(
        "SELECT id, filename, status, detected_language, page_count, created_at FROM documents WHERE id = ?",
        [document_id],
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    jobs = await db.fetch_all(
        "SELECT target_language, status FROM translation_jobs WHERE document_id = ?",
        [document_id],
    )

    translations = [
        {
            "language": job["target_language"],
            "status": job["status"],
            "download_url": f"/api/v1/documents/{document_id}/download?language={job['target_language']}"
            if job["status"] == "completed"
            else "",
        }
        for job in jobs
    ]

    classification = _classifications.get(document_id)

    return DocumentMetadata(
        document_id=doc["id"],
        filename=doc["filename"],
        status=doc["status"],
        detected_language=doc["detected_language"],
        page_count=doc["page_count"],
        created_at=doc["created_at"],
        translations=translations,
        classification=classification,
    )


@router.get("/{document_id}/classification", response_model=DocumentClassification)
async def get_document_classification(document_id: str) -> DocumentClassification:
    """Retrieve classification metadata for an uploaded document.

    The current implementation uses an in-memory metadata seam until D1-backed
    document persistence lands. Missing IDs return 404 rather than fabricating data.
    """
    classification = _classifications.get(document_id)
    if classification is None:
        raise HTTPException(status_code=404, detail="Classification metadata not found")
    return classification


@router.get("/{document_id}/download")
async def download_translated_document(document_id: str, language: str = "en") -> object:
    """Download the layout-preserved translated version of a document."""
    from fastapi import Response

    from app.services.storage_service import StorageService

    storage = StorageService()
    object_key = f"{document_id}_{language}.pdf"

    try:
        file_bytes = await storage.get_file(object_key)
        return Response(content=file_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Translated document not found or error: {e}"
        ) from e
