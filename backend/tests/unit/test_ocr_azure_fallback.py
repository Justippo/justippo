"""Azure Document Intelligence as the OCR fallback when Mistral is unavailable.

Chain under test (OCRService.process): Mistral -> Azure -> Tesseract. Tesseract
cannot run on the Worker, so a rate-limited Mistral with no Azure must surface the
real error instead of returning Tesseract's empty result.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.services.ocr_service as ocr_mod
from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    AzureDocumentIntelligenceErrorDetail,
    AzureDocumentIntelligenceLimits,
)
from app.services.ocr_service import MistralOCRError, OCRService, OCRTierLimitError

_PNG = b"\x89PNG fake"
_PDF = b"%PDF-1.4 fake"


def _f0(max_bytes: int = 4 * 1024 * 1024, max_pages: int = 2) -> AzureDocumentIntelligenceLimits:
    return AzureDocumentIntelligenceLimits(tier="F0", max_bytes=max_bytes, max_pages=max_pages)


def _azure_ok(text: str = "azure text") -> AzureDocumentAnalysis:
    return AzureDocumentAnalysis(model_id="prebuilt-layout", api_version="x", content=text)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    """Hermetic OCR env: Mistral rate-limited, Azure enabled on F0, Tesseract mocked."""
    monkeypatch.setattr(ocr_mod.settings, "MISTRAL_OCR_ENABLED", True)
    monkeypatch.setattr(ocr_mod, "azure_is_enabled", lambda: True)
    monkeypatch.setattr(ocr_mod, "get_analysis_limits", lambda: _f0())
    monkeypatch.setattr(ocr_mod, "_run_doclayout_analysis", AsyncMock())
    mistral = AsyncMock(side_effect=MistralOCRError(429, "Rate limit exceeded"))
    azure = AsyncMock(return_value=_azure_ok())
    tesseract = AsyncMock(return_value=[{"page": 1, "text": "tess", "confidence": None}])
    monkeypatch.setattr(OCRService, "_process_mistral", mistral)
    monkeypatch.setattr(OCRService, "_process_tesseract", tesseract)
    monkeypatch.setattr(ocr_mod, "analyze_pdf", azure)
    return {"mistral": mistral, "azure": azure, "tesseract": tesseract, "mp": monkeypatch}


@pytest.mark.asyncio
async def test_mistral_429_falls_back_to_azure_for_images(env) -> None:
    pages = await OCRService().process(_PNG, "image/png")

    assert pages == [{"page": 1, "text": "azure text", "confidence": None}]
    assert env["azure"].await_args.kwargs["content_type"] == "image/png"
    env["tesseract"].assert_not_awaited()


@pytest.mark.asyncio
async def test_mistral_disabled_goes_straight_to_azure(env) -> None:
    env["mp"].setattr(ocr_mod.settings, "MISTRAL_OCR_ENABLED", False)

    pages = await OCRService().process(_PNG, "image/png")

    assert pages[0]["text"] == "azure text"
    env["mistral"].assert_not_awaited()


@pytest.mark.asyncio
async def test_prefetched_azure_analysis_is_reused_not_refetched(env) -> None:
    pages = await OCRService().process(_PDF, "application/pdf", azure_analysis=_azure_ok("shared"))

    assert pages[0]["text"] == "shared"
    env["azure"].assert_not_awaited()  # F0 allows 1 request/second: never call twice


@pytest.mark.asyncio
async def test_rate_limited_with_azure_disabled_raises_instead_of_empty_tesseract(env) -> None:
    env["mp"].setattr(ocr_mod, "azure_is_enabled", lambda: False)

    with pytest.raises(MistralOCRError) as exc:
        await OCRService().process(_PNG, "image/png")

    assert exc.value.is_rate_limited
    env["azure"].assert_not_awaited()
    env["tesseract"].assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_media_type_skips_azure(env) -> None:
    with pytest.raises(MistralOCRError):
        await OCRService().process(b"RIFF webp", "image/webp")

    env["azure"].assert_not_awaited()


@pytest.mark.asyncio
async def test_over_byte_limit_raises_tier_error(env) -> None:
    env["mp"].setattr(ocr_mod, "get_analysis_limits", lambda: _f0(max_bytes=4))

    with pytest.raises(OCRTierLimitError, match="bytes"):
        await OCRService().process(_PNG, "image/png")

    env["azure"].assert_not_awaited()


@pytest.mark.asyncio
async def test_pdf_over_page_limit_raises_tier_error(env) -> None:
    env["mp"].setattr(ocr_mod, "_pdf_bytes_page_count", lambda _b: 3)

    with pytest.raises(OCRTierLimitError, match="pages"):
        await OCRService().process(_PDF, "application/pdf")

    env["azure"].assert_not_awaited()  # F0 would silently truncate to 2 pages


@pytest.mark.asyncio
async def test_unknown_pdf_page_count_defers_to_provider(env) -> None:
    env["mp"].setattr(ocr_mod, "_pdf_bytes_page_count", lambda _b: None)

    pages = await OCRService().process(_PDF, "application/pdf")

    assert pages[0]["text"] == "azure text"


@pytest.mark.asyncio
async def test_azure_failure_after_mistral_5xx_falls_through_to_tesseract(env) -> None:
    env["mistral"].side_effect = MistralOCRError(503, "down")
    env["azure"].side_effect = AzureDocumentIntelligenceError(
        AzureDocumentIntelligenceErrorDetail(
            code="SERVICE_UNAVAILABLE", message="down", retryable=True
        )
    )

    pages = await OCRService().process(_PNG, "image/png")

    assert pages[0]["text"] == "tess"


@pytest.mark.asyncio
async def test_non_rate_limit_4xx_never_reaches_azure(env) -> None:
    env["mistral"].side_effect = MistralOCRError(401, "Unauthorized")

    with pytest.raises(MistralOCRError) as exc:
        await OCRService().process(_PNG, "image/png")

    assert exc.value.status_code == 401
    env["azure"].assert_not_awaited()


def test_pdf_page_count_is_none_when_unparseable() -> None:
    assert ocr_mod._pdf_bytes_page_count(b"not a pdf") is None


_THREE_PAGE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type /Pages /Count 3 /Kids [2 0 R 3 0 R 4 0 R]>>endobj\n"
    b"2 0 obj<</Type /Page>>endobj 3 0 obj<</Type/Page>>endobj 4 0 obj<</Type /Page>>endobj"
)


def test_pdf_page_count_byte_scan_when_pdfium_unavailable(monkeypatch) -> None:
    """Pyodide (the Worker) has no pypdfium2: the byte scan must still count pages."""
    monkeypatch.setattr(ocr_mod, "_PDF_DEPS_AVAILABLE", False)
    assert ocr_mod._pdf_bytes_page_count(_THREE_PAGE_PDF) == 3


def test_pdf_page_count_scan_does_not_count_the_pages_node(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod, "_PDF_DEPS_AVAILABLE", False)
    assert ocr_mod._pdf_bytes_page_count(b"<</Type /Pages /Kids []>>") is None
