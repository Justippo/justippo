"""
Advanced OCR service tests — PDF helpers, legacy file-path API, and uncovered
edge cases in process() and _run_doclayout_analysis().

Coverage targets:
- _validate_pdf_path: file not found, wrong extension
- _open_pdf: encrypted error, generic error, success
- pdf_page_count: zero pages, success
- pdf_extract_text: zero pages, multi-page success
- pdf_render_pages: invalid dpi, zero pages, success (generator)
- _render_pdf_bytes_to_pil_images: invalid dpi, success
- pdf_metadata: success
- _run_doclayout_analysis: success path, generic Exception path
- OCRService.process(): generic Mistral exception fallback, layout
  exception guard in the Mistral-success else-branch
- OCRService.extract(): legacy file-path API
- OCRService._extract_mistral(): legacy
- OCRService._extract_tesseract(): legacy
- OCRService.detect_language(): raises NotImplementedError
- _infer_mime_type(): all supported extensions + unknown fallback

All pdfium / pytesseract / PIL calls are mocked — no heavy deps required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ocr_service import (
    OCRPage,
    OCRService,
    PDFEmptyError,
    PDFEncryptedError,
    PDFFileNotFoundError,
    PDFInvalidError,
    _infer_mime_type,
    _run_doclayout_analysis,
)

# ---------------------------------------------------------------------------
# DRY helpers / fixtures
# ---------------------------------------------------------------------------


def _make_mock_pdf(
    *,
    num_pages: int = 2,
    text_per_page: str = "Page text",
) -> MagicMock:
    """Build a mock PdfDocument with configurable pages and text."""
    mock_doc = MagicMock()
    mock_doc.__len__ = MagicMock(return_value=num_pages)
    mock_doc.close = MagicMock()

    mock_textpage = MagicMock()
    mock_textpage.get_text_bounded.return_value = text_per_page
    mock_textpage.close = MagicMock()

    mock_bitmap = MagicMock()
    mock_pil = MagicMock()
    mock_bitmap.to_pil.return_value.copy.return_value = mock_pil

    mock_page = MagicMock()
    mock_page.get_textpage.return_value = mock_textpage
    mock_page.render.return_value = mock_bitmap
    mock_page.close = MagicMock()

    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.get_metadata_dict = MagicMock(return_value={"Title": "Test Doc"})

    return mock_doc


def _make_fake_pdfium_error() -> type:
    """Create a local exception class that acts as PdfiumError."""
    return type("PdfiumError", (Exception,), {})


@pytest.fixture
def tmp_pdf(tmp_path: Path) -> Path:
    """Return a path to a temp file with .pdf extension that exists on disk."""
    p = tmp_path / "sample.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


@pytest.fixture
def mock_pdfium_ctx(tmp_pdf: Path):
    """Context fixture: patches pdfium + PdfiumError at the ocr_service level."""
    FakePdfiumError = _make_fake_pdfium_error()
    mock_doc = _make_mock_pdf()

    with (
        patch("app.services.ocr_service.pdfium") as mock_pdfium,
        patch("app.services.ocr_service.PdfiumError", FakePdfiumError),
        patch("app.services.ocr_service._PDF_DEPS_AVAILABLE", True),
    ):
        mock_pdfium.PdfDocument.return_value = mock_doc
        mock_pdfium.PdfiumError = FakePdfiumError
        yield mock_pdfium, mock_doc, FakePdfiumError, tmp_pdf


# ---------------------------------------------------------------------------
# _validate_pdf_path
# ---------------------------------------------------------------------------


class TestValidatePdfPath:
    def test_raises_file_not_found_when_missing(self, tmp_path: Path) -> None:
        from app.services.ocr_service import _validate_pdf_path

        missing = tmp_path / "missing.pdf"
        with pytest.raises(PDFFileNotFoundError, match="not found"):
            _validate_pdf_path(missing)

    def test_raises_invalid_when_wrong_extension(self, tmp_path: Path) -> None:
        from app.services.ocr_service import _validate_pdf_path

        txt_file = tmp_path / "doc.txt"
        txt_file.write_bytes(b"plain text")
        with pytest.raises(PDFInvalidError, match=".txt"):
            _validate_pdf_path(txt_file)

    def test_passes_for_valid_pdf_path(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import _validate_pdf_path

        _validate_pdf_path(tmp_pdf)  # Should not raise


# ---------------------------------------------------------------------------
# _open_pdf
# ---------------------------------------------------------------------------


class TestOpenPdf:
    def test_raises_encrypted_error_on_password_message(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import _open_pdf

        FakePdfiumError = _make_fake_pdfium_error()

        with (
            patch("app.services.ocr_service.PdfiumError", FakePdfiumError),
            patch("app.services.ocr_service.pdfium") as mock_pdfium,
        ):
            mock_pdfium.PdfDocument.side_effect = FakePdfiumError("password required")

            with pytest.raises(PDFEncryptedError, match="password-protected"):
                _open_pdf(tmp_pdf)

    def test_raises_pdf_invalid_on_pdfium_error(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import _open_pdf

        FakePdfiumError = _make_fake_pdfium_error()

        with (
            patch("app.services.ocr_service.PdfiumError", FakePdfiumError),
            patch("app.services.ocr_service.pdfium") as mock_pdfium,
        ):
            mock_pdfium.PdfDocument.side_effect = FakePdfiumError("corrupted stream")

            with pytest.raises(PDFInvalidError):
                _open_pdf(tmp_pdf)

    def test_raises_pdf_invalid_on_unexpected_exception(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import _open_pdf

        FakePdfiumError = _make_fake_pdfium_error()

        with (
            patch("app.services.ocr_service.PdfiumError", FakePdfiumError),
            patch("app.services.ocr_service.pdfium") as mock_pdfium,
        ):
            mock_pdfium.PdfDocument.side_effect = OSError("permission denied")

            with pytest.raises(PDFInvalidError, match="Unexpected error"):
                _open_pdf(tmp_pdf)

    def test_returns_document_on_success(self, mock_pdfium_ctx: Any) -> None:
        from app.services.ocr_service import _open_pdf

        mock_pdfium, mock_doc, _, tmp_pdf = mock_pdfium_ctx
        result = _open_pdf(tmp_pdf)
        assert result is mock_doc


# ---------------------------------------------------------------------------
# pdf_page_count
# ---------------------------------------------------------------------------


class TestPdfPageCount:
    def test_raises_empty_on_zero_pages(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_page_count

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_doc = _make_mock_pdf(num_pages=0)
            mock_doc.close = MagicMock()
            mock_open.return_value = mock_doc
            with pytest.raises(PDFEmptyError, match="zero pages"):
                pdf_page_count(tmp_pdf)

    def test_returns_page_count(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_page_count

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_open.return_value = _make_mock_pdf(num_pages=3)
            assert pdf_page_count(tmp_pdf) == 3


# ---------------------------------------------------------------------------
# pdf_extract_text
# ---------------------------------------------------------------------------


class TestPdfExtractText:
    def test_raises_empty_on_zero_pages(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_extract_text

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_open.return_value = _make_mock_pdf(num_pages=0)
            with pytest.raises(PDFEmptyError):
                pdf_extract_text(tmp_pdf)

    def test_returns_joined_text(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_extract_text

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_open.return_value = _make_mock_pdf(num_pages=2, text_per_page="Hello")
            text = pdf_extract_text(tmp_pdf)

        assert "Hello" in text
        # Two pages → joined with \n\n
        assert text == "Hello\n\nHello"

    def test_raises_unexpected_error_on_len(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import PDFInvalidError, pdf_extract_text

        class MockPDFException:
            def __len__(self):
                raise Exception("Test unexpected len exception in extract")

            def close(self):
                pass

        with (
            patch("app.services.ocr_service._open_pdf", return_value=MockPDFException()),
            pytest.raises(
                PDFInvalidError,
                match="Unexpected error parsing PDF length:.*Test unexpected len exception in extract",
            ),
        ):
            pdf_extract_text(tmp_pdf)


# ---------------------------------------------------------------------------
# pdf_render_pages
# ---------------------------------------------------------------------------


class TestPdfRenderPages:
    def test_raises_value_error_on_invalid_dpi(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_render_pages

        with pytest.raises(ValueError, match="dpi must be a positive integer"):
            list(pdf_render_pages(tmp_pdf, dpi=0))

    def test_raises_value_error_on_negative_dpi(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_render_pages

        with pytest.raises(ValueError):
            list(pdf_render_pages(tmp_pdf, dpi=-10))

    def test_raises_empty_on_zero_pages(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_render_pages

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_open.return_value = _make_mock_pdf(num_pages=0)
            with pytest.raises(PDFEmptyError):
                list(pdf_render_pages(tmp_pdf))

    def test_yields_pil_images(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_render_pages

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_doc = _make_mock_pdf(num_pages=2)
            mock_open.return_value = mock_doc
            images = list(pdf_render_pages(tmp_pdf, dpi=72))

        assert len(images) == 2

    def test_raises_unexpected_error_on_len(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import PDFInvalidError, pdf_render_pages

        class MockPDFException:
            def __len__(self):
                raise Exception("Test unexpected len exception in render")

            def close(self):
                pass

        with (
            patch("app.services.ocr_service._open_pdf", return_value=MockPDFException()),
            pytest.raises(
                PDFInvalidError,
                match="Unexpected error parsing PDF length:.*Test unexpected len exception in render",
            ),
        ):
            list(pdf_render_pages(tmp_pdf))


# ---------------------------------------------------------------------------
# _render_pdf_bytes_to_pil_images
# ---------------------------------------------------------------------------


class TestRenderPdfBytesToPilImages:
    def test_raises_value_error_on_invalid_dpi(self) -> None:
        from app.services.ocr_service import _render_pdf_bytes_to_pil_images

        with pytest.raises(ValueError, match="dpi must be a positive integer"):
            _render_pdf_bytes_to_pil_images(b"pdf", dpi=0)

    def test_returns_images_list(self) -> None:
        from app.services.ocr_service import _render_pdf_bytes_to_pil_images

        with patch("app.services.ocr_service.pdfium") as mock_pdfium:
            mock_doc = _make_mock_pdf(num_pages=2)
            mock_pdfium.PdfDocument.return_value = mock_doc
            images = _render_pdf_bytes_to_pil_images(b"pdf bytes", dpi=72)

        assert len(images) == 2


# ---------------------------------------------------------------------------
# pdf_metadata
# ---------------------------------------------------------------------------


class TestPdfMetadata:
    def test_returns_metadata_dict(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import pdf_metadata

        with patch("app.services.ocr_service._open_pdf") as mock_open:
            mock_doc = _make_mock_pdf()
            mock_open.return_value = mock_doc
            result = pdf_metadata(tmp_pdf)

        assert result == {"Title": "Test Doc"}


# ---------------------------------------------------------------------------
# _run_doclayout_analysis — all three branches
# ---------------------------------------------------------------------------


class TestRunDoclayoutAnalysis:
    @pytest.mark.asyncio
    async def test_returns_result_on_success(self) -> None:
        mock_analyze = AsyncMock(return_value={"boxes": [1, 2, 3]})
        mock_mod = MagicMock()
        mock_mod.analyze_layout = mock_analyze

        with patch.dict(sys.modules, {"app.integrations.ocr": mock_mod}):
            result = await _run_doclayout_analysis([], None)

        assert result == {"boxes": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_returns_empty_on_import_error(self) -> None:
        # sys.modules entry of None causes ImportError on `from ... import`
        with patch.dict(sys.modules, {"app.integrations.ocr": None}):
            result = await _run_doclayout_analysis([], None)

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_generic_exception(self) -> None:
        mock_analyze = AsyncMock(side_effect=RuntimeError("YOLO crashed"))
        mock_mod = MagicMock()
        mock_mod.analyze_layout = mock_analyze

        with patch.dict(sys.modules, {"app.integrations.ocr": mock_mod}):
            result = await _run_doclayout_analysis([], None)

        assert result == {}


# ---------------------------------------------------------------------------
# OCRService.process() — uncovered edge cases
# ---------------------------------------------------------------------------


class TestOCRServiceProcessEdgeCases:
    @pytest.mark.asyncio
    async def test_generic_mistral_exception_falls_back_to_tesseract(self) -> None:
        """Generic exception (not Timeout, not MistralOCRError) → Tesseract fallback."""
        service = OCRService()
        tesseract_pages = [OCRPage(page=1, text="Tess fallback", confidence=None)]

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch.object(service, "_process_mistral", new_callable=AsyncMock) as mock_mistral,
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_mistral.side_effect = ConnectionError("DNS resolution failed")
            mock_tess.return_value = tesseract_pages

            pages = await service.process(b"pdf bytes", "application/pdf")

        mock_tess.assert_called_once()
        assert pages[0]["text"] == "Tess fallback"

    @pytest.mark.asyncio
    async def test_layout_exception_guard_in_mistral_success_path(self) -> None:
        """When Mistral succeeds but _run_doclayout_analysis raises, process still returns pages."""
        service = OCRService()
        mistral_pages = [OCRPage(page=1, text="Mistral text", confidence=0.99)]

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch.object(service, "_process_mistral", new_callable=AsyncMock) as mock_mistral,
            patch(
                "app.services.ocr_service._run_doclayout_analysis",
                new_callable=AsyncMock,
                side_effect=RuntimeError("layout crash"),
            ),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_mistral.return_value = mistral_pages

            pages = await service.process(b"bytes", "application/pdf")

        assert len(pages) == 1
        assert pages[0]["text"] == "Mistral text"

    @pytest.mark.asyncio
    async def test_layout_exception_guard_in_tesseract_path(self) -> None:
        """When Tesseract runs and _run_doclayout_analysis raises, process still returns pages."""
        service = OCRService()
        tess_pages = [OCRPage(page=1, text="Tess text", confidence=None)]

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
            patch(
                "app.services.ocr_service._run_doclayout_analysis",
                new_callable=AsyncMock,
                side_effect=ValueError("layout error"),
            ),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = False
            mock_tess.return_value = tess_pages

            pages = await service.process(b"bytes", "image/png")

        assert pages[0]["text"] == "Tess text"


# ---------------------------------------------------------------------------
# OCRService — legacy file-path API
# ---------------------------------------------------------------------------


class TestOCRServiceLegacyAPI:
    @pytest.mark.asyncio
    async def test_extract_delegates_to_process(self, tmp_pdf: Path) -> None:
        service = OCRService()
        mock_pages = [
            OCRPage(page=1, text="Page one text", confidence=0.95),
            OCRPage(page=2, text="Page two text", confidence=0.90),
        ]

        with (
            patch.object(service, "process", new_callable=AsyncMock, return_value=mock_pages),
            patch("app.services.ocr_service._infer_mime_type", return_value="application/pdf"),
        ):
            # Write real bytes so read_bytes() succeeds
            tmp_pdf.write_bytes(b"%PDF-1.4 content")
            result = await service.extract(tmp_pdf)

        assert result.document_id == tmp_pdf.stem
        assert result.page_count == 2
        assert "Page one text" in result.text
        assert result.confidence == pytest.approx((0.95 + 0.90) / 2)

    @pytest.mark.asyncio
    async def test_extract_with_no_confidence_scores(self, tmp_pdf: Path) -> None:
        """When all pages have confidence=None, avg_conf should be 0.0."""
        service = OCRService()
        mock_pages = [OCRPage(page=1, text="tess", confidence=None)]

        with (
            patch.object(service, "process", new_callable=AsyncMock, return_value=mock_pages),
        ):
            tmp_pdf.write_bytes(b"%PDF-1.4")
            result = await service.extract(tmp_pdf)

        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_with_empty_pages(self, tmp_pdf: Path) -> None:
        """Empty page list → page_count=0, confidence=0.0."""
        service = OCRService()
        with (
            patch.object(service, "process", new_callable=AsyncMock, return_value=[]),
        ):
            tmp_pdf.write_bytes(b"%PDF-1.4")
            result = await service.extract(tmp_pdf)

        assert result.page_count == 0
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_mistral_delegates(self, tmp_pdf: Path) -> None:
        service = OCRService()
        mock_pages = [OCRPage(page=1, text="Mistral extracted", confidence=0.97)]

        with (
            patch.object(
                service, "_process_mistral", new_callable=AsyncMock, return_value=mock_pages
            ),
            patch("app.services.ocr_service._infer_mime_type", return_value="application/pdf"),
        ):
            tmp_pdf.write_bytes(b"%PDF")
            result = await service._extract_mistral(tmp_pdf)

        assert result.text == "Mistral extracted"
        assert result.confidence == pytest.approx(0.97)

    @pytest.mark.asyncio
    async def test_extract_tesseract_delegates(self, tmp_pdf: Path) -> None:
        service = OCRService()
        mock_pages = [OCRPage(page=1, text="Tesseract extracted", confidence=None)]

        with (
            patch.object(
                service, "_process_tesseract", new_callable=AsyncMock, return_value=mock_pages
            ),
            patch("app.services.ocr_service._infer_mime_type", return_value="application/pdf"),
        ):
            tmp_pdf.write_bytes(b"%PDF")
            result = await service._extract_tesseract(tmp_pdf)

        assert result.text == "Tesseract extracted"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_detect_language(self) -> None:
        service = OCRService()
        lang = await service.detect_language("Ceci est un texte en français.")
        assert lang == "fr"
        lang = await service.detect_language("This is an English text.")
        assert lang == "en"


# ---------------------------------------------------------------------------
# _infer_mime_type
# ---------------------------------------------------------------------------


class TestInferMimeType:
    def test_pdf(self) -> None:
        assert _infer_mime_type(Path("doc.pdf")) == "application/pdf"

    def test_docx(self) -> None:
        assert "wordprocessingml" in _infer_mime_type(Path("doc.docx"))

    def test_png(self) -> None:
        assert _infer_mime_type(Path("scan.png")) == "image/png"

    def test_jpg(self) -> None:
        assert _infer_mime_type(Path("photo.jpg")) == "image/jpeg"

    def test_jpeg(self) -> None:
        assert _infer_mime_type(Path("photo.jpeg")) == "image/jpeg"

    def test_webp(self) -> None:
        assert _infer_mime_type(Path("img.webp")) == "image/webp"

    def test_unknown_falls_back_to_octet_stream(self) -> None:
        assert _infer_mime_type(Path("file.bin")) == "application/octet-stream"

    def test_uppercase_extension(self) -> None:
        assert _infer_mime_type(Path("SCAN.PDF")) == "application/pdf"


# ---------------------------------------------------------------------------
# MIME type coverage — _MIME_TO_DOCUMENT_TYPE and _MIME_TO_DATA_URI_PREFIX
# ---------------------------------------------------------------------------


class TestMimeMappingCoverage:
    """Verify all supported MIME types have entries in both mapping dicts."""

    def test_all_mime_types_in_document_type_map(self) -> None:
        from app.services.ocr_service import _MIME_TO_DOCUMENT_TYPE

        expected_types = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
        ]
        for mt in expected_types:
            assert mt in _MIME_TO_DOCUMENT_TYPE, (
                f"MIME type '{mt}' missing from _MIME_TO_DOCUMENT_TYPE"
            )

    def test_all_mime_types_in_data_uri_prefix_map(self) -> None:
        from app.services.ocr_service import _MIME_TO_DATA_URI_PREFIX

        expected_types = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
        ]
        for mt in expected_types:
            assert mt in _MIME_TO_DATA_URI_PREFIX, (
                f"MIME type '{mt}' missing from _MIME_TO_DATA_URI_PREFIX"
            )

    def test_document_type_and_prefix_maps_have_same_keys(self) -> None:
        from app.services.ocr_service import (
            _MIME_TO_DATA_URI_PREFIX,
            _MIME_TO_DOCUMENT_TYPE,
        )

        assert set(_MIME_TO_DOCUMENT_TYPE.keys()) == set(_MIME_TO_DATA_URI_PREFIX.keys()), (
            "MIME mapping dicts must have identical key sets"
        )


# ---------------------------------------------------------------------------
# process() with image MIME types — PNG, JPEG, WEBP paths
# ---------------------------------------------------------------------------


class TestOCRServiceImageProcessing:
    """Covers process() with image MIME types (PNG, JPEG, WEBP)."""

    @pytest.mark.asyncio
    async def test_process_png_goes_to_mistral(self) -> None:
        """PNG upload routes through Mistral when enabled."""
        service = OCRService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pages": [
                {
                    "index": 0,
                    "markdown": "PNG text",
                    "confidence_scores": {"average_page_confidence_score": 0.95},
                }
            ]
        }
        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            pages = await service.process(b"\x89PNG\r\n\x1a\n fake", "image/png")

        assert len(pages) == 1
        assert pages[0]["text"] == "PNG text"
        assert pages[0]["confidence"] == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_process_jpeg_routes_correctly(self) -> None:
        """JPEG upload is treated as image_url by Mistral."""
        service = OCRService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pages": [
                {
                    "index": 0,
                    "markdown": "JPEG scan result",
                    "confidence_scores": {"average_page_confidence_score": 0.88},
                }
            ]
        }
        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            pages = await service.process(b"\xff\xd8\xff\xe0 fake jpeg", "image/jpeg")

        assert pages[0]["text"] == "JPEG scan result"

    @pytest.mark.asyncio
    async def test_process_webp_routes_correctly(self) -> None:
        """WEBP upload uses correct MIME and data URI prefix."""
        service = OCRService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pages": [
                {
                    "index": 0,
                    "markdown": "WEBP content",
                    "confidence_scores": {"average_page_confidence_score": 0.90},
                }
            ]
        }
        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            pages = await service.process(b"RIFF\x00\x00 fake webp", "image/webp")

        assert pages[0]["text"] == "WEBP content"

    def test_raises_unexpected_error_on_len(self, tmp_pdf: Path) -> None:
        from app.services.ocr_service import PDFInvalidError, pdf_page_count

        class MockPDFException:
            def __len__(self):
                raise Exception("Test unexpected len exception")

            def close(self):
                pass

        with (
            patch("app.services.ocr_service._open_pdf", return_value=MockPDFException()),
            pytest.raises(
                PDFInvalidError,
                match="Unexpected error parsing PDF length:.*Test unexpected len exception",
            ),
        ):
            pdf_page_count(tmp_pdf)
