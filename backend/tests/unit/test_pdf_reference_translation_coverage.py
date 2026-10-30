"""
Tests — PDF reference translation service coverage boost.

Covers the pure helpers (_dominant_analysis_language, _polygon_height,
_median_word_height, _alphabetic_count, _page_count, _validate_translated_analysis)
and every error/edge branch of ``translate_pdf_reference``. All external
dependencies are injected via the function's own dependency-injection kwargs
(analyze, render, classify, explain) plus monkeypatched route_pdf_upload /
get_analysis_limits — fully hermetic, no network, no real Azure/BabelDOC calls.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock

import pytest

from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    AzureDocumentIntelligenceErrorDetail,
    AzureDocumentIntelligenceLimits,
)
from app.integrations.babeldoc_adapter import BabelDocResponse
from app.services import pdf_reference_translation_service as svc
from app.services.classification_service import DocumentClassification
from app.services.pdf_reference_translation_service import (
    PDFReferenceTranslationError,
    _alphabetic_count,
    _dominant_analysis_language,
    _median_word_height,
    _page_count,
    _polygon_height,
    _validate_translated_analysis,
    translate_pdf_reference,
)

# ─── helpers ─────────────────────────────────────────────────────────────────


def _analysis(
    languages=None,
    pages=None,
    content="Hello world document text",
) -> AzureDocumentAnalysis:
    return AzureDocumentAnalysis(
        model_id="prebuilt-read",
        api_version="2023-02-28",
        content=content,
        pages=pages or [],
        languages=languages or [],
    )


def _azure_err(
    code: str = "E", message: str = "boom", retryable: bool = False
) -> AzureDocumentIntelligenceError:
    return AzureDocumentIntelligenceError(
        AzureDocumentIntelligenceErrorDetail(code=code, message=message, retryable=retryable)
    )


def _limits() -> AzureDocumentIntelligenceLimits:
    return AzureDocumentIntelligenceLimits(tier="standard", max_bytes=10_000_000, max_pages=20)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _fake_response(translated_b64: str, source="en", target="de") -> BabelDocResponse:
    return BabelDocResponse(
        translated_b64=translated_b64,
        source_lang=source,
        target_lang=target,
        detected_lang=target,
        processing_time_ms=1.0,
        layout_preserved=True,
        pages_processed=1,
        warnings=[],
    )


@pytest.fixture
def _wire(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch the two internal module-globals that aren't injectable kwargs."""
    monkeypatch.setattr(svc, "route_pdf_upload", lambda b, t: None)
    monkeypatch.setattr(svc, "get_analysis_limits", lambda: _limits())
    return monkeypatch


# ─── Pure helper tests ───────────────────────────────────────────────────────


def test_dominant_analysis_language_none_locale() -> None:
    assert _dominant_analysis_language(_analysis(languages=[{"locale": None}])) is None


def test_dominant_analysis_language_unsupported() -> None:
    assert _dominant_analysis_language(_analysis(languages=[{"locale": "xx"}])) is None


def test_dominant_analysis_language_valid() -> None:
    out = _dominant_analysis_language(_analysis(languages=[{"locale": "en-US", "confidence": 0.9}]))
    assert out == "en"


def test_dominant_analysis_language_highest_confidence() -> None:
    out = _dominant_analysis_language(
        _analysis(
            languages=[
                {"locale": "de", "confidence": 0.3},
                {"locale": "fr", "confidence": 0.8},
            ]
        )
    )
    assert out == "fr"


def test_polygon_height_non_list() -> None:
    assert _polygon_height("not-a-list") is None


def test_polygon_height_int_list() -> None:
    assert _polygon_height([0, 10, 5, 30, 10, 10]) == 20.0


def test_polygon_height_dict_list() -> None:
    assert _polygon_height([{"y": 5}, {"y": 25}, {"y": 15}]) == 20.0


def test_polygon_height_too_few() -> None:
    assert _polygon_height([{"y": 5}]) is None


def test_polygon_height_zero_height() -> None:
    assert _polygon_height([{"y": 5}, {"y": 5}]) is None  # height == 0


def test_median_word_height_no_words() -> None:
    assert _median_word_height(_analysis(pages=[{"words": "not-list"}])) is None


def test_median_word_height_non_dict_word() -> None:
    assert _median_word_height(_analysis(pages=[{"words": ["not-dict"]}])) is None


def test_median_word_height_non_alpha() -> None:
    assert (
        _median_word_height(
            _analysis(pages=[{"words": [{"content": "1234", "polygon": [{"y": 0}, {"y": 5}]}]}])
        )
        is None
    )


def test_median_word_height_too_few() -> None:
    pg = {"words": [{"content": "abc", "polygon": [{"y": 0}, {"y": 5}]}]}
    assert _median_word_height(_analysis(pages=[pg])) is None  # < 5 heights


def test_median_word_height_valid() -> None:
    words = [
        {"content": f"word{i}", "polygon": [{"y": 0}, {"y": float(10 + i * 10)}]} for i in range(5)
    ]
    result = _median_word_height(_analysis(pages=[{"words": words}]))
    assert result is not None


def test_alphabetic_count_empty() -> None:
    assert _alphabetic_count("") == 0


def test_alphabetic_count_content() -> None:
    assert _alphabetic_count("Hello123World") == 10


def test_page_count_empty() -> None:
    assert _page_count(_analysis()) == 0


def test_page_count_present() -> None:
    assert _page_count(_analysis(pages=[{}, {}, {}])) == 3


def test_validate_translated_analysis_page_mismatch() -> None:
    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_analysis(_analysis(), _analysis(), "en", "de", expected_page_count=5)


def test_validate_translated_analysis_retention_ratio() -> None:
    # 20+ source chars, matching page count, but very low translated retention
    src = _analysis(pages=[{}], content="x" * 100)
    tgt = _analysis(pages=[{}], content="y")
    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_analysis(src, tgt, "en", "de", expected_page_count=1)


def test_contains_source_form_label_leakage_no_markers() -> None:
    from app.services.pdf_reference_translation_service import (
        _contains_source_form_label_leakage,
    )

    assert _contains_source_form_label_leakage("hello", "welt", "en") is False


def test_contains_source_form_label_leakage_detected() -> None:
    from app.services.pdf_reference_translation_service import (
        _contains_source_form_label_leakage,
    )

    # "arbeitgeber" is a de marker and appears in both source and translated tokens
    assert (
        _contains_source_form_label_leakage("Arbeitgeber hat geschrieben", "Arbeitgeber hat", "de")
        is True
    )


def test_validate_translated_analysis_language_mismatch() -> None:
    # translated analysis reports a dominant language != target (de)
    tgt = _analysis(
        pages=[{}],
        content="x" * 100,
        languages=[{"locale": "fr", "confidence": 0.99}],
    )
    src = _analysis(pages=[{}], content="x" * 100)
    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_analysis(src, tgt, "en", "de", expected_page_count=1)


def test_validate_translated_analysis_label_leakage() -> None:
    src = _analysis(pages=[{}], content="Arbeitgeber hat geschrieben")
    tgt = _analysis(pages=[{}], content="Arbeitgeber hat")
    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_analysis(src, tgt, "de", "en", expected_page_count=1)


def test_validate_translated_analysis_passes() -> None:
    src = _analysis(pages=[{}], content="Source document body text content here now")
    tgt = _analysis(pages=[{}], content="Übersetztes Dokument Text hier ist gut genug")
    # Returns None when all validations pass
    assert _validate_translated_analysis(src, tgt, "en", "de", expected_page_count=1) is None


def test_median_word_height_mixed_valid_and_none() -> None:
    # A word with zero-height polygon (height None) mixed with valid ones —
    # exercises the `if height is not None` False branch (line 231->222).
    words = [
        {"content": f"word{i}", "polygon": [{"y": 0}, {"y": float(10 + i * 10)}]} for i in range(5)
    ]
    # Inject a zero-height word so the None-branch is exercised
    words[0]["polygon"] = [{"y": 5}, {"y": 5}]  # height == 0 -> None
    result = _median_word_height(_analysis(pages=[{"words": words}]))
    # 4 valid heights remain (i>=1), but that's < 5 -> returns None
    assert result is None


def test_validate_translated_analysis_height_ratio() -> None:
    # source words tall, translated words short -> ratio < MIN_OUTPUT_WORD_HEIGHT_RATIO (0.45)
    src_words = [{"content": f"word{i}", "polygon": [{"y": 0}, {"y": 100.0}]} for i in range(5)]
    tgt_words = [{"content": f"wort{i}", "polygon": [{"y": 0}, {"y": 5.0}]} for i in range(5)]
    src = _analysis(pages=[{"words": src_words}], content="x" * 100)
    tgt = _analysis(pages=[{"words": tgt_words}], content="x" * 100)
    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_analysis(src, tgt, "en", "de", expected_page_count=1)


# ─── translate_pdf_reference pipeline (kwargs injection) ───────────────────────


async def _happy(_wire, *, analyze=None, render=None, classify=None, explain=None):
    # `_wire` fixture (param above) patches route_pdf_upload + get_analysis_limits.
    return await translate_pdf_reference(
        document_bytes=b"%PDF-1.4 source",
        source_language="en",
        target_language="de",
        expected_page_count=1,
        analyze=analyze
        or AsyncMock(return_value=_analysis(pages=[{}], content="Source document body text")),
        render=render or AsyncMock(return_value=_fake_response(_b64(b"%PDF-1.4 translated"))),
        classify=classify or AsyncMock(return_value=DocumentClassification()),
        explain=explain or AsyncMock(side_effect=RuntimeError("explain failed")),
    )


@pytest.mark.asyncio
async def test_translate_success(_wire) -> None:
    result = await _happy(_wire)
    assert result is not None


@pytest.mark.asyncio
async def test_translate_analysis_page_count_too_low(_wire) -> None:
    # Source analysis has fewer pages than expected -> line 445
    analyze = AsyncMock(return_value=_analysis(pages=[], content="x" * 100))
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(
            b"%PDF-1.4 source",
            "en",
            "de",
            1,
            analyze=analyze,
        )


@pytest.mark.asyncio
async def test_translate_pdf_intake_error(monkeypatch: pytest.MonkeyPatch, _wire) -> None:
    from app.services.pdf_intake_service import PDFIntakeError

    def _boom(b, t):
        raise PDFIntakeError(code="INVALID_PDF", message="intake failed", status_code=400)

    monkeypatch.setattr(svc, "route_pdf_upload", _boom)
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(b"x", "en", "de", 1)


@pytest.mark.asyncio
async def test_translate_page_limit_low(_wire) -> None:
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(b"x", "en", "de", 0)


@pytest.mark.asyncio
async def test_translate_page_limit_high(_wire) -> None:
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(b"x", "en", "de", 25)


@pytest.mark.asyncio
async def test_translate_file_too_large(monkeypatch: pytest.MonkeyPatch, _wire) -> None:
    monkeypatch.setattr(
        svc,
        "get_analysis_limits",
        lambda: AzureDocumentIntelligenceLimits(tier="free", max_bytes=10, max_pages=20),
    )
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(b"x" * 100, "en", "de", 1)


@pytest.mark.asyncio
async def test_translate_limits_page_exceeded(monkeypatch: pytest.MonkeyPatch, _wire) -> None:
    # Azure tier max_pages < requested expected_page_count -> line 425
    monkeypatch.setattr(
        svc,
        "get_analysis_limits",
        lambda: AzureDocumentIntelligenceLimits(tier="free", max_bytes=10_000_000, max_pages=1),
    )
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(b"%PDF-1.4 source", "en", "de", 2)


@pytest.mark.asyncio
async def test_translate_analysis_too_many_pages(_wire) -> None:
    # Analysis returns > PDF_MAX_PAGES pages; expected count passes the limits
    # check (20) but the actual page_count (21) exceeds the hard cap -> line 451
    big_pages = [{"pageNumber": i + 1} for i in range(21)]
    analyze = AsyncMock(return_value=_analysis(pages=big_pages, content="x" * 100))
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(
            b"%PDF-1.4 source",
            "en",
            "de",
            20,
            analyze=analyze,
        )


@pytest.mark.asyncio
async def test_translate_azure_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.pdf_intake_service import PDFIntakeError  # noqa: F401

    monkeypatch.setattr(svc, "route_pdf_upload", lambda b, t: None)
    monkeypatch.setattr(
        svc, "get_analysis_limits", lambda: (_ for _ in ()).throw(_azure_err(code="LIMITS_DOWN"))
    )
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(b"x", "en", "de", 1)


@pytest.mark.asyncio
async def test_translate_azure_analysis_error(_wire) -> None:
    analyze = AsyncMock(side_effect=_azure_err(code="ANALYZE_DOWN"))
    with pytest.raises(PDFReferenceTranslationError):
        await _happy(_wire, analyze=analyze)


@pytest.mark.asyncio
async def test_translate_analysis_unexpected(_wire) -> None:
    analyze = AsyncMock(side_effect=RuntimeError("weird"))
    with pytest.raises(PDFReferenceTranslationError):
        await _happy(_wire, analyze=analyze)


@pytest.mark.asyncio
async def test_translate_classify_fallback(_wire) -> None:
    classify = AsyncMock(side_effect=RuntimeError("classify crashed"))
    result = await _happy(_wire, classify=classify)
    assert result is not None


@pytest.mark.asyncio
async def test_translate_render_cancelled(_wire) -> None:
    render = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await _happy(_wire, render=render)


@pytest.mark.asyncio
async def test_translate_render_exception(_wire) -> None:
    render = AsyncMock(side_effect=RuntimeError("render failed"))
    with pytest.raises(PDFReferenceTranslationError):
        await _happy(_wire, render=render)


@pytest.mark.asyncio
async def test_translate_language_mismatch(_wire) -> None:
    render = AsyncMock(
        return_value=_fake_response(_b64(b"%PDF translated"), source="fr", target="de")
    )
    with pytest.raises(PDFReferenceTranslationError):
        await _happy(_wire, render=render)


@pytest.mark.asyncio
async def test_translate_output_analysis_error(_wire) -> None:
    analyze = AsyncMock(
        side_effect=[_analysis(pages=[{}], content="x" * 100), _azure_err(code="OUTPUT_DOWN")]
    )
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(
            b"%PDF-1.4 source",
            "en",
            "de",
            1,
            analyze=analyze,
            render=AsyncMock(return_value=_fake_response(_b64(b"%PDF-1.4 translated"))),
            classify=AsyncMock(return_value=DocumentClassification()),
            explain=AsyncMock(side_effect=RuntimeError("explain failed")),
        )


@pytest.mark.asyncio
async def test_translate_output_verify_failure(_wire) -> None:
    analyze = AsyncMock(
        side_effect=[_analysis(pages=[{}], content="x" * 100), RuntimeError("verify boom")]
    )
    with pytest.raises(PDFReferenceTranslationError):
        await translate_pdf_reference(
            b"%PDF-1.4 source",
            "en",
            "de",
            1,
            analyze=analyze,
            render=AsyncMock(return_value=_fake_response(_b64(b"%PDF-1.4 translated"))),
            classify=AsyncMock(return_value=DocumentClassification()),
            explain=AsyncMock(side_effect=RuntimeError("explain failed")),
        )


# ─── Error mappers, validators & explanation branches (unit) ─────────────────


@pytest.mark.asyncio
async def test_translate_unsupported_language(_wire) -> None:
    from app.services.pdf_reference_translation_service import (
        _validate_languages,
    )

    with pytest.raises(PDFReferenceTranslationError):
        _validate_languages("en", "zh")


@pytest.mark.asyncio
async def test_translate_same_language(_wire) -> None:
    from app.services.pdf_reference_translation_service import (
        _validate_languages,
    )

    with pytest.raises(PDFReferenceTranslationError):
        _validate_languages("en", "en")


def test_validate_translated_pdf_too_large() -> None:
    from app.services.pdf_reference_translation_service import (
        MAX_TRANSLATED_PDF_B64_CHARS,
        _validate_translated_pdf,
    )

    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_pdf("A" * (MAX_TRANSLATED_PDF_B64_CHARS + 1))


def test_validate_translated_pdf_bad_base64() -> None:
    from app.services.pdf_reference_translation_service import _validate_translated_pdf

    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_pdf("!!!not-base64!!!")


def test_validate_translated_pdf_not_pdf() -> None:
    from app.services.pdf_reference_translation_service import _validate_translated_pdf

    # valid base64 of non-PDF bytes
    with pytest.raises(PDFReferenceTranslationError):
        _validate_translated_pdf(_b64(b"NOT A PDF DOCUMENT BODY"))


def test_map_azure_error_processing_timeout() -> None:
    from app.services.pdf_reference_translation_service import _map_azure_error

    err = _map_azure_error(_azure_err(code="PROCESSING_TIMEOUT", retryable=True))
    assert err is not None


def test_map_azure_error_service_unavailable() -> None:
    from app.services.pdf_reference_translation_service import _map_azure_error

    err = _map_azure_error(_azure_err(code="SERVICE_UNAVAILABLE", retryable=True))
    assert err is not None


def test_map_azure_error_generic() -> None:
    from app.services.pdf_reference_translation_service import _map_azure_error

    err = _map_azure_error(_azure_err(code="OTHER", retryable=False))
    assert err is not None


def test_map_output_analysis_error_timeout() -> None:
    from app.services.pdf_reference_translation_service import _map_output_analysis_error

    err = _map_output_analysis_error(_azure_err(code="PROCESSING_TIMEOUT", retryable=True))
    assert err is not None


def test_map_output_analysis_error_service_unavailable() -> None:
    from app.services.pdf_reference_translation_service import _map_output_analysis_error

    err = _map_output_analysis_error(_azure_err(code="SERVICE_UNAVAILABLE", retryable=False))
    assert err is not None


def test_map_output_analysis_error_generic() -> None:
    from app.services.pdf_reference_translation_service import _map_output_analysis_error

    err = _map_output_analysis_error(_azure_err(code="OTHER", retryable=False))
    assert err is not None


def test_map_babeldoc_error_not_implemented() -> None:
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    err = _map_babeldoc_error(NotImplementedError("nope"))
    assert err is not None


def _babeldoc_err(error_code="TIMEOUT", retryable=True):
    from app.integrations.babeldoc_adapter import BabelDocError, BabelDocSidecarError

    return BabelDocSidecarError(
        error=BabelDocError(error_code=error_code, message="msg", retryable=retryable)
    )


def test_map_babeldoc_error_password_required() -> None:
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    err = _map_babeldoc_error(_babeldoc_err(error_code="PASSWORD_REQUIRED", retryable=False))
    assert err is not None


def test_map_babeldoc_error_timeout() -> None:
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    err = _map_babeldoc_error(_babeldoc_err(error_code="TIMEOUT", retryable=True))
    assert err is not None


def test_map_babeldoc_error_service_unavailable() -> None:
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    err = _map_babeldoc_error(_babeldoc_err(error_code="SERVICE_UNAVAILABLE", retryable=False))
    assert err is not None


def test_map_babeldoc_error_password_other() -> None:
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    err = _map_babeldoc_error(_babeldoc_err(error_code="OTHER", retryable=False))
    assert err is not None


def test_map_babeldoc_error_generic() -> None:
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    err = _map_babeldoc_error(ValueError("weird"))
    assert err is not None


@pytest.mark.asyncio
async def test_translate_explanation_cancelled(_wire) -> None:
    import asyncio

    analyze = AsyncMock(return_value=_analysis(pages=[{}], content="Source document body text"))
    render = AsyncMock(return_value=_fake_response(_b64(b"%PDF-1.4 translated")))
    classify = AsyncMock(return_value=DocumentClassification())
    explain = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await translate_pdf_reference(
            b"%PDF-1.4 source",
            "en",
            "de",
            1,
            analyze=analyze,
            render=render,
            classify=classify,
            explain=explain,
        )


@pytest.mark.asyncio
async def test_translate_explanation_non_exception(_wire) -> None:
    analyze = AsyncMock(return_value=_analysis(pages=[{}], content="Source document body text"))
    render = AsyncMock(return_value=_fake_response(_b64(b"%PDF-1.4 translated")))
    classify = AsyncMock(return_value=DocumentClassification())
    # A BaseException that is NOT an Exception (e.g. SystemExit) -> re-raised at 524
    explain = AsyncMock(return_value=SystemExit("boom"))
    with pytest.raises(SystemExit):
        await translate_pdf_reference(
            b"%PDF-1.4 source",
            "en",
            "de",
            1,
            analyze=analyze,
            render=render,
            classify=classify,
            explain=explain,
        )


@pytest.mark.asyncio
async def test_translate_explanation_success(_wire) -> None:
    from app.models.document_explanation import DocumentExplanation

    analyze = AsyncMock(return_value=_analysis(pages=[{}], content="Source document body text"))
    render = AsyncMock(return_value=_fake_response(_b64(b"%PDF-1.4 translated")))
    classify = AsyncMock(return_value=DocumentClassification())
    explain = AsyncMock(
        return_value=DocumentExplanation(
            document_type="contract",
            language="de",
            requirements=[],
            legal_context_status="grounded",
            citations=[],
        )
    )
    result = await translate_pdf_reference(
        b"%PDF-1.4 source",
        "en",
        "de",
        1,
        analyze=analyze,
        render=render,
        classify=classify,
        explain=explain,
    )
    assert result is not None


def test_map_babeldoc_error_unknown_code_fallthrough() -> None:
    # An unknown error_code (not NotImplementedError/RuntimeError, not a known
    # BabelDoc code) falls through to the final return at the bottom of
    # _map_babeldoc_error.
    from app.services.pdf_reference_translation_service import _map_babeldoc_error

    result = _map_babeldoc_error(_babeldoc_err(error_code="UNKNOWN_CODE", retryable=False))
    assert result is not None
