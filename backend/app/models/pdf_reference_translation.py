"""Contracts for the composed, reference-only PDF translation workflow."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.document_explanation import DocumentExplanation
from app.services.classification_service import DocumentClassification

SupportedLanguage = Literal["en", "de", "fr"]
PDFReferenceErrorCode = Literal[
    "INVALID_PDF",
    "FILE_TOO_LARGE",
    "PAGE_LIMIT_EXCEEDED",
    "PASSWORD_REQUIRED",
    "UNSUPPORTED_LANGUAGE",
    "INVALID_LANGUAGE_PAIR",
    "AZURE_ANALYSIS_FAILED",
    "BABELDOC_TRANSLATION_FAILED",
    "TRANSLATION_QUALITY_FAILED",
    "PROCESSING_TIMEOUT",
    "SERVICE_UNAVAILABLE",
]


class PDFReferenceTranslationResult(BaseModel):
    """Ephemeral translated reference plus document understanding metadata."""

    request_id: str
    status: Literal["done"] = "done"
    ephemeral: Literal[True] = True
    output_mode: Literal["reference"] = "reference"
    original_unchanged: Literal[True] = True
    form_filling_supported: Literal[False] = False
    source_language: SupportedLanguage
    target_language: SupportedLanguage
    translated_pdf_b64: str = Field(min_length=1)
    translated_pdf_content_type: Literal["application/pdf"] = "application/pdf"
    detected_source_language: str
    layout_preserved: bool
    pages_processed: int = Field(ge=0)
    classification: DocumentClassification
    document_explanation: DocumentExplanation
    warnings: list[str] = Field(default_factory=list)


class PDFReferenceTranslationErrorDetail(BaseModel):
    """Content-safe error returned by the composed workflow."""

    code: PDFReferenceErrorCode
    message: str
    retryable: bool = False
