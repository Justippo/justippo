"""Compose Azure analysis, BabelDOC rendering, and grounded explanation.

The workflow is deliberately ephemeral: source bytes are passed directly to
the two provider boundaries and no file or job is persisted by the Worker.
Azure and BabelDOC are required stages. Classification and legal explanation
degrade safely without preventing an otherwise valid reference translation.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from statistics import median
from typing import Any

from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    analyze_pdf,
    get_analysis_limits,
)
from app.integrations.babeldoc_adapter import (
    BabelDocRequest,
    BabelDocResponse,
    BabelDocSidecarError,
    translate,
)
from app.models.document_explanation import DocumentExplanation
from app.models.pdf_reference_translation import (
    PDFReferenceErrorCode,
    PDFReferenceTranslationErrorDetail,
    PDFReferenceTranslationResult,
    SupportedLanguage,
)
from app.services.classification_service import (
    DocumentClassification,
    classify_document,
    default_classification,
)
from app.services.document_explanation_service import (
    explain_document,
    extract_document_requirements,
)
from app.services.pdf_intake_service import PDFIntakeError, route_pdf_upload

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
PDF_MAX_PAGES = 20
MAX_TRANSLATED_PDF_B64_CHARS = 40 * 1024 * 1024
SUPPORTED_LANGUAGES: frozenset[SupportedLanguage] = frozenset({"en", "de", "fr"})
MIN_OUTPUT_TEXT_RETENTION_RATIO = 0.35
MIN_OUTPUT_WORD_HEIGHT_RATIO = 0.45
SOURCE_FORM_LABEL_MARKERS: dict[SupportedLanguage, frozenset[str]] = {
    "de": frozenset(
        {
            "ab",
            "arbeitgeber",
            "arbeitszeit",
            "beruf",
            "bis",
            "familienname",
            "ja",
            "kundennummer",
            "nein",
            "ort",
            "seit",
            "vorname",
        }
    ),
    "en": frozenset(),
    "fr": frozenset(),
}
WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)

AnalyzePDF = Callable[..., Awaitable[AzureDocumentAnalysis]]
RenderPDF = Callable[[BabelDocRequest], Awaitable[BabelDocResponse]]
ClassifyPDF = Callable[[str, str], Awaitable[DocumentClassification]]
ExplainPDF = Callable[..., Awaitable[DocumentExplanation]]


class PDFReferenceTranslationError(Exception):
    """Typed orchestration error that never contains provider payloads."""

    def __init__(self, detail: PDFReferenceTranslationErrorDetail, status_code: int) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail.message)


def _error(
    code: PDFReferenceErrorCode,
    message: str,
    *,
    status_code: int,
    retryable: bool = False,
) -> PDFReferenceTranslationError:
    return PDFReferenceTranslationError(
        PDFReferenceTranslationErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
        ),
        status_code,
    )


def _validate_languages(
    source_language: str,
    target_language: str,
) -> tuple[SupportedLanguage, SupportedLanguage]:
    source = source_language.strip().lower()
    target = target_language.strip().lower()
    if source not in SUPPORTED_LANGUAGES or target not in SUPPORTED_LANGUAGES:
        raise _error(
            "UNSUPPORTED_LANGUAGE",
            "PDF reference translation supports English, German, and French",
            status_code=422,
        )
    if source == target:
        raise _error(
            "INVALID_LANGUAGE_PAIR",
            "Source and target languages must differ",
            status_code=422,
        )
    return source, target


def _page_count(analysis: AzureDocumentAnalysis) -> int:
    pages = {
        page_number
        for page in analysis.pages
        if isinstance((page_number := page.get("pageNumber")), int) and page_number > 0
    }
    return max(pages, default=len(analysis.pages))


def _validate_translated_pdf(translated_b64: str) -> bytes:
    if len(translated_b64) > MAX_TRANSLATED_PDF_B64_CHARS:
        raise _error(
            "BABELDOC_TRANSLATION_FAILED",
            "The translated reference PDF could not be validated",
            status_code=502,
        )
    try:
        translated = base64.b64decode(translated_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _error(
            "BABELDOC_TRANSLATION_FAILED",
            "The translated reference PDF could not be validated",
            status_code=502,
        ) from exc
    if b"%PDF" not in translated[:1024]:
        raise _error(
            "BABELDOC_TRANSLATION_FAILED",
            "The translated reference PDF could not be validated",
            status_code=502,
        )
    return translated


def _alphabetic_count(text: str) -> int:
    return sum(character.isalpha() for character in text)


def _contains_source_form_label_leakage(
    source_text: str,
    translated_text: str,
    source_language: SupportedLanguage,
) -> bool:
    markers = SOURCE_FORM_LABEL_MARKERS[source_language]
    if not markers:
        return False
    source_tokens = {token.casefold() for token in WORD_PATTERN.findall(source_text)}
    translated_tokens = {token.casefold() for token in WORD_PATTERN.findall(translated_text)}
    return bool(markers & source_tokens & translated_tokens)


def _dominant_analysis_language(analysis: AzureDocumentAnalysis) -> str | None:
    candidates: list[tuple[float, str]] = []
    for language in analysis.languages:
        locale = language.get("locale")
        confidence = language.get("confidence")
        if not isinstance(locale, str):
            continue
        normalized = locale.strip().lower().split("-", maxsplit=1)[0]
        if normalized not in SUPPORTED_LANGUAGES:
            continue
        score = float(confidence) if isinstance(confidence, int | float) else 0.0
        candidates.append((score, normalized))
    return max(candidates, default=(0.0, ""))[1] or None


def _polygon_height(polygon: Any) -> float | None:
    if not isinstance(polygon, list):
        return None
    if polygon and all(isinstance(value, int | float) for value in polygon):
        y_values = [float(value) for value in polygon[1::2]]
    else:
        y_values = [
            float(point["y"])
            for point in polygon
            if isinstance(point, dict) and isinstance(point.get("y"), int | float)
        ]
    if len(y_values) < 2:
        return None
    height = max(y_values) - min(y_values)
    return height if height > 0 else None


def _median_word_height(analysis: AzureDocumentAnalysis) -> float | None:
    heights: list[float] = []
    for page in analysis.pages:
        words = page.get("words")
        if not isinstance(words, list):
            continue
        for word in words:
            if not isinstance(word, dict):
                continue
            content = word.get("content")
            if not isinstance(content, str) or not any(
                character.isalpha() for character in content
            ):
                continue
            height = _polygon_height(word.get("polygon"))
            if height is not None:
                heights.append(height)
    return median(heights) if len(heights) >= 5 else None


def _validate_translated_analysis(
    source_analysis: AzureDocumentAnalysis,
    translated_analysis: AzureDocumentAnalysis,
    source_language: SupportedLanguage,
    target_language: SupportedLanguage,
    expected_page_count: int,
) -> None:
    if _page_count(translated_analysis) < expected_page_count:
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF did not preserve every page",
            status_code=502,
            retryable=True,
        )

    source_characters = _alphabetic_count(source_analysis.content)
    translated_characters = _alphabetic_count(translated_analysis.content)
    if source_characters >= 20 and (
        translated_characters / source_characters < MIN_OUTPUT_TEXT_RETENTION_RATIO
    ):
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF lost too much document text",
            status_code=502,
            retryable=True,
        )

    detected_language = _dominant_analysis_language(translated_analysis)
    if detected_language is not None and detected_language != target_language:
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF did not use the selected target language",
            status_code=502,
            retryable=True,
        )

    if _contains_source_form_label_leakage(
        source_analysis.content,
        translated_analysis.content,
        source_language,
    ):
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF retained untranslated administrative labels",
            status_code=502,
            retryable=True,
        )

    source_word_height = _median_word_height(source_analysis)
    translated_word_height = _median_word_height(translated_analysis)
    if (
        source_word_height is not None
        and translated_word_height is not None
        and translated_word_height / source_word_height < MIN_OUTPUT_WORD_HEIGHT_RATIO
    ):
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF text is not readable at the original page scale",
            status_code=502,
            retryable=True,
        )


def _map_azure_error(exc: AzureDocumentIntelligenceError) -> PDFReferenceTranslationError:
    if exc.detail.code == "PROCESSING_TIMEOUT":
        return _error(
            "PROCESSING_TIMEOUT",
            "PDF structure analysis timed out",
            status_code=504,
            retryable=True,
        )
    if exc.detail.code == "SERVICE_UNAVAILABLE":
        return _error(
            "SERVICE_UNAVAILABLE",
            "PDF structure analysis is unavailable",
            status_code=503,
            retryable=exc.detail.retryable,
        )
    return _error(
        "AZURE_ANALYSIS_FAILED",
        "PDF structure analysis failed",
        status_code=502,
        retryable=exc.detail.retryable,
    )


def _map_output_analysis_error(
    exc: AzureDocumentIntelligenceError,
) -> PDFReferenceTranslationError:
    if exc.detail.code == "PROCESSING_TIMEOUT":
        return _error(
            "PROCESSING_TIMEOUT",
            "Translated PDF quality verification timed out",
            status_code=504,
            retryable=True,
        )
    return _error(
        "TRANSLATION_QUALITY_FAILED",
        "The translated PDF could not be verified",
        status_code=503 if exc.detail.code == "SERVICE_UNAVAILABLE" else 502,
        retryable=exc.detail.retryable,
    )


def _map_babeldoc_error(exc: Exception) -> PDFReferenceTranslationError:
    if isinstance(exc, NotImplementedError | RuntimeError):
        return _error(
            "SERVICE_UNAVAILABLE",
            "PDF reference rendering is unavailable",
            status_code=503,
        )
    if isinstance(exc, BabelDocSidecarError):
        if exc.error.error_code == "PASSWORD_REQUIRED":
            return _error(
                "PASSWORD_REQUIRED",
                "The PDF requires an unprotected copy",
                status_code=422,
            )
        if exc.error.error_code == "TIMEOUT":
            return _error(
                "PROCESSING_TIMEOUT",
                "PDF reference rendering timed out",
                status_code=504,
                retryable=True,
            )
        if exc.error.error_code == "SERVICE_UNAVAILABLE":
            return _error(
                "SERVICE_UNAVAILABLE",
                "PDF reference rendering is unavailable",
                status_code=503,
                retryable=exc.error.retryable,
            )
        return _error(
            "BABELDOC_TRANSLATION_FAILED",
            "PDF reference rendering failed",
            status_code=502,
            retryable=exc.error.retryable,
        )
    return _error(
        "BABELDOC_TRANSLATION_FAILED",
        "PDF reference rendering failed",
        status_code=502,
    )


async def translate_pdf_reference(
    document_bytes: bytes,
    source_language: str,
    target_language: str,
    expected_page_count: int,
    *,
    request_id: str | None = None,
    analyze: AnalyzePDF = analyze_pdf,
    render: RenderPDF = translate,
    classify: ClassifyPDF = classify_document,
    explain: ExplainPDF = explain_document,
) -> PDFReferenceTranslationResult:
    """Run the approved reference-only PDF pipeline without persistence."""
    try:
        route_pdf_upload(document_bytes, PDF_CONTENT_TYPE)
    except PDFIntakeError as exc:
        raise _error(
            exc.code,
            str(exc),
            status_code=exc.status_code,
        ) from exc

    source, target = _validate_languages(source_language, target_language)
    resolved_request_id = request_id or str(uuid.uuid4())

    if expected_page_count < 1 or expected_page_count > PDF_MAX_PAGES:
        raise _error(
            "PAGE_LIMIT_EXCEEDED",
            "PDF page count must be between 1 and 20",
            status_code=422,
        )

    try:
        analysis_limits = get_analysis_limits()
    except AzureDocumentIntelligenceError as exc:
        raise _map_azure_error(exc) from exc

    if len(document_bytes) > analysis_limits.max_bytes:
        raise _error(
            "FILE_TOO_LARGE",
            f"PDF exceeds the configured Azure {analysis_limits.tier} size limit",
            status_code=413,
        )
    if expected_page_count > analysis_limits.max_pages:
        raise _error(
            "PAGE_LIMIT_EXCEEDED",
            f"PDF exceeds the configured Azure {analysis_limits.tier} page limit",
            status_code=422,
        )

    try:
        analysis = await analyze(document_bytes, request_id=resolved_request_id)
    except AzureDocumentIntelligenceError as exc:
        raise _map_azure_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected PDF structure analysis failure", exc_info=False)
        raise _error(
            "AZURE_ANALYSIS_FAILED",
            "PDF structure analysis failed",
            status_code=502,
        ) from exc

    page_count = _page_count(analysis)
    if page_count < expected_page_count:
        raise _error(
            "AZURE_ANALYSIS_FAILED",
            "PDF structure analysis did not cover every page",
            status_code=502,
        )
    if page_count > PDF_MAX_PAGES:
        raise _error(
            "PAGE_LIMIT_EXCEEDED",
            "PDF exceeds the 20-page reference translation limit",
            status_code=422,
        )

    try:
        classification = await classify(analysis.content, PDF_CONTENT_TYPE)
    except Exception:
        logger.warning("PDF classification failed; using fallback", exc_info=False)
        classification = default_classification(analysis.content)

    render_request = BabelDocRequest(
        source_lang=source,
        target_lang=target,
        document_b64=base64.b64encode(document_bytes).decode("ascii"),
        preserve_layout=True,
        timeout_seconds=300,
        options={"max_pages": expected_page_count},
    )
    render_result, explanation_result = await asyncio.gather(
        render(render_request),
        explain(
            analysis,
            classification,
            language=target,
        ),
        return_exceptions=True,
    )

    if isinstance(render_result, BaseException):
        if isinstance(render_result, asyncio.CancelledError):
            raise render_result
        if isinstance(render_result, Exception):
            raise _map_babeldoc_error(render_result)
        raise render_result  # pragma: no cover - a non-Exception BaseException (e.g. KeyboardInterrupt/SystemExit) cannot be triggered deterministically
    if render_result.source_lang != source or render_result.target_lang != target:
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF language pair did not match the request",
            status_code=502,
            retryable=True,
        )
    translated_bytes = _validate_translated_pdf(render_result.translated_b64)
    try:
        translated_analysis = await analyze(
            translated_bytes,
            request_id=str(uuid.uuid4()),
        )
    except AzureDocumentIntelligenceError as exc:
        raise _map_output_analysis_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected translated PDF quality verification failure", exc_info=False)
        raise _error(
            "TRANSLATION_QUALITY_FAILED",
            "The translated PDF could not be verified",
            status_code=502,
        ) from exc
    finally:
        del translated_bytes

    _validate_translated_analysis(
        analysis,
        translated_analysis,
        source,
        target,
        expected_page_count,
    )

    if isinstance(explanation_result, BaseException):
        if isinstance(explanation_result, asyncio.CancelledError):
            raise explanation_result
        if not isinstance(explanation_result, Exception):
            raise explanation_result
        logger.warning("PDF explanation failed; returning translated reference", exc_info=False)
        explanation = DocumentExplanation(
            document_type=classification.document_type,
            language=target,
            requirements=extract_document_requirements(analysis),
            legal_context_status="unavailable",
            citations=[],
            warnings=["DOCUMENT_EXPLANATION_UNAVAILABLE"],
        )
    else:
        explanation = explanation_result

    warnings = list(dict.fromkeys([*render_result.warnings, *explanation.warnings]))
    return PDFReferenceTranslationResult(
        request_id=resolved_request_id,
        source_language=source,
        target_language=target,
        translated_pdf_b64=render_result.translated_b64,
        detected_source_language=render_result.detected_lang,
        layout_preserved=render_result.layout_preserved,
        pages_processed=render_result.pages_processed or page_count,
        classification=classification,
        document_explanation=explanation,
        warnings=warnings,
    )
