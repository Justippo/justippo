"""
Tests — OCR service fillable-form path coverage.

Exercises ``OCRService.process`` with ``is_fillable_form=True`` and
``_process_fillable_form`` in isolation. ``analyze_pdf``, ``get_analysis_limits``,
and ``_run_doclayout_analysis`` are monkeypatched so no network / GPU calls occur.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    AzureDocumentIntelligenceErrorDetail,
    AzureDocumentIntelligenceLimits,
)
from app.services import ocr_service as ocr_mod
from app.services.ocr_service import OCRPage, OCRService


def _analysis(content="page one text content here") -> AzureDocumentAnalysis:
    return AzureDocumentAnalysis(
        model_id="prebuilt-layout",
        api_version="2023-02-28",
        content=content,
        pages=[{}],
        languages=[],
    )


def _limits(max_bytes=10_000_000, max_pages=20) -> AzureDocumentIntelligenceLimits:
    return AzureDocumentIntelligenceLimits(
        tier="standard", max_bytes=max_bytes, max_pages=max_pages
    )


@pytest.fixture
def _ocrd(monkeypatch: pytest.MonkeyPatch):
    """Patch OCR service externals hermetically."""
    monkeypatch.setattr(ocr_mod, "get_analysis_limits", lambda: _limits())
    monkeypatch.setattr(ocr_mod, "_run_doclayout_analysis", AsyncMock())
    monkeypatch.setattr(OCRService, "_process_mistral", AsyncMock(return_value=[]))
    return monkeypatch


@pytest.mark.asyncio
async def _call(_ocrd, **kw) -> list[OCRPage]:
    svc = OCRService()
    return await svc.process(
        b"%PDF-1.4 source bytes", "application/pdf", is_fillable_form=True, **kw
    )


@pytest.mark.asyncio
async def test_process_fillable_form_with_preanalyzed(_ocrd) -> None:
    # azure_analysis provided -> skip the analyze_pdf call, return OCRPage from content
    result = await _call(_ocrd, azure_analysis=_analysis())
    assert result == [{"page": 1, "text": "page one text content here", "confidence": None}]


@pytest.mark.asyncio
async def test_process_fillable_form_form_analysis_succeeds(_ocrd) -> None:
    # _run_doclayout_analysis succeeds -> form_pages returned (lines 418-422)
    result = await _call(_ocrd, azure_analysis=_analysis())
    assert result[0]["page"] == 1


@pytest.mark.asyncio
async def test_process_fillable_form_form_analysis_fails(_ocrd) -> None:
    # _run_doclayout_analysis raises -> warning logged, form_pages still returned (420-421)
    _ocrd.setattr(
        ocr_mod, "_run_doclayout_analysis", AsyncMock(side_effect=RuntimeError("layout boom"))
    )
    result = await _call(_ocrd, azure_analysis=_analysis())
    assert result[0]["page"] == 1


@pytest.mark.asyncio
async def test_process_fillable_form_empty_content(_ocrd) -> None:
    # analysis.content is whitespace-only -> returns None -> falls through to Mistral (mocked -> [])
    result = await _call(_ocrd, azure_analysis=_analysis(content="   "))
    assert result == []


@pytest.mark.asyncio
async def test_process_fillable_form_file_too_large(_ocrd) -> None:
    # azure_analysis=None, file exceeds Azure tier limit -> return None (484-491)
    _ocrd.setattr(ocr_mod, "azure_is_enabled", lambda: True)
    _ocrd.setattr(ocr_mod, "get_analysis_limits", lambda: _limits(max_bytes=10))
    result = await _call(_ocrd, azure_analysis=None)
    assert result == []


@pytest.mark.asyncio
async def test_process_fillable_form_azure_error(_ocrd) -> None:
    # azure_analysis=None and analyze_pdf raises AzureDocumentIntelligenceError -> return None
    async def _boom(b, *a, **k):
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(code="E", message="azure down", retryable=False)
        )

    _ocrd.setattr(ocr_mod, "analyze_pdf", _boom)
    result = await _call(_ocrd, azure_analysis=None)
    assert result == []


@pytest.mark.asyncio
async def test_process_fillable_form_analyze_success(_ocrd) -> None:
    # azure_analysis=None, analyze_pdf succeeds with valid content -> OCRPage returned
    _ocrd.setattr(
        ocr_mod,
        "analyze_pdf",
        AsyncMock(return_value=_analysis(content="filled form value text")),
    )
    _ocrd.setattr(ocr_mod, "azure_is_enabled", lambda: True)
    result = await _call(_ocrd, azure_analysis=None)
    assert result[0]["text"] == "filled form value text"


def test_render_pdf_form_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # init_forms() raises -> defensive handler logs and continues (295-296)
    mock_pdf = MagicMock()
    mock_pdf.init_forms.side_effect = RuntimeError("form layer quirk")
    mock_pdf.__len__ = lambda self: 0  # type: ignore[override]
    mock_pdf.close = MagicMock()
    monkeypatch.setattr(ocr_mod.pdfium, "PdfDocument", lambda b: mock_pdf)
    images = ocr_mod._render_pdf_bytes_to_pil_images(b"%PDF-1.4 stub")
    assert images == []
