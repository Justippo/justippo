"""Tests for the composed reference-only PDF translation workflow."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import pytest

from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    AzureDocumentIntelligenceErrorDetail,
)
from app.integrations.babeldoc_adapter import (
    BabelDocError,
    BabelDocResponse,
    BabelDocSidecarError,
)
from app.models.document_explanation import DocumentExplanation, DocumentRequirement
from app.services.classification_service import DocumentClassification
from app.services.pdf_reference_translation_service import (
    PDFReferenceTranslationError,
    _contains_source_form_label_leakage,
    translate_pdf_reference,
)


def _pdf() -> bytes:
    return b"%PDF-1.7\nsynthetic fixture\n%%EOF"


def _analysis(
    page_count: int = 2,
    *,
    content: str = "You must provide proof of residence.",
    language: str | None = None,
    word_height: float | None = None,
) -> AzureDocumentAnalysis:
    words = (
        [
            {
                "content": f"word-{index}",
                "polygon": [0.0, 0.0, 1.0, 0.0, 1.0, word_height, 0.0, word_height],
            }
            for index in range(5)
        ]
        if word_height is not None
        else []
    )
    return AzureDocumentAnalysis(
        model_id="prebuilt-layout",
        api_version="2024-11-30",
        content=content,
        pages=[
            {"pageNumber": page, **({"words": words} if words else {})}
            for page in range(1, page_count + 1)
        ],
        paragraphs=[{"content": content}],
        key_value_pairs=[{"key": {"content": "Proof of residence"}}],
        languages=[{"locale": language, "confidence": 0.95}] if language else [],
    )


def _classification() -> DocumentClassification:
    return DocumentClassification(
        document_type="residence_application",
        language_code="en",
        geographic_relevance=["Germany"],
        confidence=0.9,
    )


def _rendered(*, source: str = "en", target: str = "de") -> BabelDocResponse:
    return BabelDocResponse(
        translated_b64=base64.b64encode(b"%PDF-1.7\ntranslated\n%%EOF").decode("ascii"),
        source_lang=source,
        target_lang=target,
        detected_lang=source,
        processing_time_ms=1250,
        layout_preserved=True,
        pages_processed=2,
        warnings=["REFERENCE_COPY_ONLY"],
    )


def _explanation() -> DocumentExplanation:
    return DocumentExplanation(
        document_type="residence_application",
        language="de",
        requirements=[DocumentRequirement(text="Proof of residence", kind="field")],
        legal_context_status="not_found",
        citations=[],
        warnings=["NO_VERIFIED_EU_LAW_SOURCE"],
    )


@pytest.mark.asyncio
async def test_composes_required_providers_and_grounded_explanation() -> None:
    analyze = AsyncMock(return_value=_analysis())
    render = AsyncMock(return_value=_rendered())
    classify = AsyncMock(return_value=_classification())
    explain = AsyncMock(return_value=_explanation())

    result = await translate_pdf_reference(
        _pdf(),
        "en",
        "de",
        2,
        request_id="request-123",
        analyze=analyze,
        render=render,
        classify=classify,
        explain=explain,
    )

    assert result.status == "done"
    assert result.ephemeral is True
    assert result.output_mode == "reference"
    assert result.original_unchanged is True
    assert result.form_filling_supported is False
    assert result.translated_pdf_b64 == _rendered().translated_b64
    assert result.pages_processed == 2
    assert result.warnings == ["REFERENCE_COPY_ONLY", "NO_VERIFIED_EU_LAW_SOURCE"]

    assert analyze.await_count == 2
    assert analyze.await_args_list[0].args == (_pdf(),)
    assert analyze.await_args_list[0].kwargs == {"request_id": "request-123"}
    classify.assert_awaited_once_with(_analysis().content, "application/pdf")
    babel_request = render.await_args.args[0]
    assert base64.b64decode(babel_request.document_b64) == _pdf()
    assert babel_request.source_lang == "en"
    assert babel_request.target_lang == "de"
    assert babel_request.timeout_seconds == 300
    assert babel_request.options == {"max_pages": 2}
    assert explain.await_args.kwargs["language"] == "de"


@pytest.mark.asyncio
async def test_page_limit_stops_before_rendering_or_explanation() -> None:
    render = AsyncMock()
    explain = AsyncMock()

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "en",
            "fr",
            2,
            analyze=AsyncMock(return_value=_analysis(page_count=21)),
            render=render,
            classify=AsyncMock(return_value=_classification()),
            explain=explain,
        )

    assert exc_info.value.detail.code == "PAGE_LIMIT_EXCEEDED"
    assert exc_info.value.status_code == 422
    render.assert_not_awaited()
    explain.assert_not_awaited()


@pytest.mark.asyncio
async def test_azure_unavailable_is_content_safe_503() -> None:
    analyze = AsyncMock(
        side_effect=AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="private endpoint and secret",
                retryable=False,
            )
        )
    )

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(_pdf(), "en", "de", 2, analyze=analyze)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail.code == "SERVICE_UNAVAILABLE"
    assert "private" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_babeldoc_timeout_maps_to_retryable_processing_timeout() -> None:
    render = AsyncMock(
        side_effect=BabelDocSidecarError(
            BabelDocError(
                error_code="TIMEOUT",
                message="private sidecar output",
                retryable=True,
            )
        )
    )

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "en",
            "de",
            2,
            analyze=AsyncMock(return_value=_analysis()),
            render=render,
            classify=AsyncMock(return_value=_classification()),
            explain=AsyncMock(return_value=_explanation()),
        )

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail.code == "PROCESSING_TIMEOUT"
    assert exc_info.value.detail.retryable is True
    assert "private" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_explanation_failure_preserves_reference_and_requirements() -> None:
    result = await translate_pdf_reference(
        _pdf(),
        "en",
        "fr",
        2,
        analyze=AsyncMock(return_value=_analysis()),
        render=AsyncMock(return_value=_rendered(target="fr")),
        classify=AsyncMock(return_value=_classification()),
        explain=AsyncMock(side_effect=RuntimeError("private document content")),
    )

    assert result.status == "done"
    assert result.document_explanation.legal_context_status == "unavailable"
    assert result.document_explanation.requirements[0].text == "Proof of residence"
    assert result.document_explanation.warnings == ["DOCUMENT_EXPLANATION_UNAVAILABLE"]


@pytest.mark.asyncio
async def test_invalid_translated_artifact_is_rejected() -> None:
    invalid = _rendered()
    invalid.translated_b64 = base64.b64encode(b"not a PDF").decode("ascii")

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "en",
            "de",
            2,
            analyze=AsyncMock(return_value=_analysis()),
            render=AsyncMock(return_value=invalid),
            classify=AsyncMock(return_value=_classification()),
            explain=AsyncMock(return_value=_explanation()),
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail.code == "BABELDOC_TRANSLATION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "target", "code"),
    [("es", "de", "UNSUPPORTED_LANGUAGE"), ("en", "en", "INVALID_LANGUAGE_PAIR")],
)
async def test_rejects_invalid_language_pairs(source: str, target: str, code: str) -> None:
    analyze = AsyncMock()

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(_pdf(), source, target, 2, analyze=analyze)

    assert exc_info.value.detail.code == code
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_f0_rejects_more_than_two_pages_before_provider_calls() -> None:
    analyze = AsyncMock()
    render = AsyncMock()

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(_pdf(), "en", "de", 3, analyze=analyze, render=render)

    assert exc_info.value.detail.code == "PAGE_LIMIT_EXCEEDED"
    assert "F0" in exc_info.value.detail.message
    analyze.assert_not_awaited()
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_f0_rejects_more_than_four_mib_before_provider_calls() -> None:
    analyze = AsyncMock()

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            b"%PDF-1.7\n" + b"x" * (4 * 1024 * 1024),
            "en",
            "de",
            2,
            analyze=analyze,
        )

    assert exc_info.value.detail.code == "FILE_TOO_LARGE"
    assert "F0" in exc_info.value.detail.message
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_incomplete_azure_analysis_stops_before_rendering() -> None:
    render = AsyncMock()

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "en",
            "de",
            2,
            analyze=AsyncMock(return_value=_analysis(page_count=1)),
            render=render,
        )

    assert exc_info.value.detail.code == "AZURE_ANALYSIS_FAILED"
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_rendered_pdf_in_the_wrong_target_language() -> None:
    analyze = AsyncMock(
        side_effect=[
            _analysis(language="en"),
            _analysis(
                content="Ce formulaire doit être traduit en français.",
                language="fr",
            ),
        ]
    )

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "en",
            "de",
            2,
            analyze=analyze,
            render=AsyncMock(return_value=_rendered()),
            classify=AsyncMock(return_value=_classification()),
            explain=AsyncMock(return_value=_explanation()),
        )

    assert exc_info.value.detail.code == "TRANSLATION_QUALITY_FAILED"
    assert "target language" in exc_info.value.detail.message


@pytest.mark.asyncio
async def test_rejects_rendered_pdf_with_collapsed_text_size() -> None:
    analyze = AsyncMock(
        side_effect=[
            _analysis(language="en", word_height=0.1),
            _analysis(
                content="Die Übersetzung enthält weiterhin lesbaren Text.",
                language="de",
                word_height=0.02,
            ),
        ]
    )

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "en",
            "de",
            2,
            analyze=analyze,
            render=AsyncMock(return_value=_rendered()),
            classify=AsyncMock(return_value=_classification()),
            explain=AsyncMock(return_value=_explanation()),
        )

    assert exc_info.value.detail.code == "TRANSLATION_QUALITY_FAILED"
    assert "not readable" in exc_info.value.detail.message


@pytest.mark.asyncio
async def test_rejects_rendered_pdf_with_untranslated_short_form_labels() -> None:
    analyze = AsyncMock(
        side_effect=[
            _analysis(
                content="Vorname Raphaella Karen Ja Nein Bis Ort Arbeitgeber Arbeitszeit",
                language="de",
            ),
            _analysis(
                content="First name Raphaella Karen Ja No Until Place Employer Working hours",
                language="en",
            ),
        ]
    )

    with pytest.raises(PDFReferenceTranslationError) as exc_info:
        await translate_pdf_reference(
            _pdf(),
            "de",
            "en",
            2,
            analyze=analyze,
            render=AsyncMock(return_value=_rendered(source="de", target="en")),
            classify=AsyncMock(return_value=_classification()),
            explain=AsyncMock(return_value=_explanation()),
        )

    assert exc_info.value.detail.code == "TRANSLATION_QUALITY_FAILED"
    assert "administrative labels" in exc_info.value.detail.message


def test_source_label_check_ignores_values_dates_and_separators() -> None:
    source = (
        "Vorname | Raphaella Karen | Arbeitgeber | SWISS KRONO Tec GmbH | "
        "Ort | Berlin | Ab / Seit | 01.06.2026 | ---"
    )
    translated = (
        "First name | Raphaella Karen | Employer | SWISS KRONO Tec GmbH | "
        "Place | Berlin | From | 01.06.2026 | ---"
    )

    assert _contains_source_form_label_leakage(source, translated, "de") is False
