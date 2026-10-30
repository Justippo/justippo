"""
Unit tests for OCRService (Sprint 2)

Coverage:
- Mistral success path (mocked gateway response)
- Tesseract fallback triggered on Mistral 503
- Tesseract fallback triggered on Mistral timeout
- No temp files left in /tmp after either path completes
- _parse_mistral_response schema parsing
- process() with MISTRAL_OCR_ENABLED=False goes straight to Tesseract

All HTTP calls are mocked — no real network calls are made.
"""

from __future__ import annotations

import glob
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.ocr_service import (
    OCRPage,
    OCRService,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_FAKE_PDF_BYTES = b"%PDF-1.4 fake content"
_FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n fake png"

_MISTRAL_SUCCESS_RESPONSE: dict[str, Any] = {
    "model": "mistral-ocr-latest",
    "pages": [
        {
            "index": 0,
            "markdown": "# Page One\nHello world.",
            "confidence_scores": {"average_page_confidence_score": 0.97},
        },
        {
            "index": 1,
            "markdown": "# Page Two\nMore text here.",
            "confidence_scores": {"average_page_confidence_score": 0.93},
        },
    ],
    "usage_info": {"pages_processed": 2},
}


def _make_httpx_response(status_code: int, json_body: Any = None, text: str = "") -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_body or {}
    return resp


# ---------------------------------------------------------------------------
# _parse_mistral_response tests
# ---------------------------------------------------------------------------


class TestParseMistralResponse:
    def test_parses_pages_correctly(self) -> None:
        pages = OCRService._parse_mistral_response(_MISTRAL_SUCCESS_RESPONSE)
        assert len(pages) == 2
        assert pages[0]["page"] == 1
        assert pages[0]["text"] == "# Page One\nHello world."
        assert pages[0]["confidence"] == pytest.approx(0.97)
        assert pages[1]["page"] == 2
        assert pages[1]["confidence"] == pytest.approx(0.93)

    def test_missing_confidence_scores_returns_none(self) -> None:
        data = {"pages": [{"index": 0, "markdown": "text", "confidence_scores": None}]}
        pages = OCRService._parse_mistral_response(data)
        assert pages[0]["confidence"] is None

    def test_confidence_scores_dict_with_none_avg_returns_none(self) -> None:
        """Branch: confidence_scores is a dict but average_page_confidence_score is None."""
        data = {
            "pages": [
                {
                    "index": 0,
                    "markdown": "text",
                    "confidence_scores": {"average_page_confidence_score": None},
                }
            ]
        }
        pages = OCRService._parse_mistral_response(data)
        assert pages[0]["confidence"] is None

    def test_empty_pages_list(self) -> None:
        pages = OCRService._parse_mistral_response({"pages": []})
        assert pages == []

    def test_missing_pages_key(self) -> None:
        pages = OCRService._parse_mistral_response({})
        assert pages == []


# ---------------------------------------------------------------------------
# Mistral success path
# ---------------------------------------------------------------------------


class TestMistralSuccessPath:
    @pytest.mark.asyncio
    async def test_process_returns_ocr_pages_on_mistral_success(self) -> None:
        """Happy path: Mistral returns 200 with valid OCR data."""
        service = OCRService()
        mock_response = _make_httpx_response(200, json_body=_MISTRAL_SUCCESS_RESPONSE)

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch(
                "app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock
            ) as mock_layout,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            # Wire up httpx mock
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            mock_layout.return_value = {}

            pages = await service.process(_FAKE_PDF_BYTES, "application/pdf")

        assert len(pages) == 2
        assert pages[0]["page"] == 1
        assert pages[0]["text"] == "# Page One\nHello world."
        assert pages[0]["confidence"] == pytest.approx(0.97)
        assert pages[1]["page"] == 2
        # Layout analysis was called (non-blocking)
        mock_layout.assert_called_once()

    @pytest.mark.asyncio
    async def test_mistral_gateway_url_used(self) -> None:
        """Ensures get_gateway_url is called — never a direct Mistral endpoint."""
        service = OCRService()
        mock_response = _make_httpx_response(200, json_body=_MISTRAL_SUCCESS_RESPONSE)

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.get_gateway_url") as mock_gw,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"
            mock_gw.return_value = "https://gateway.ai.cloudflare.com/v1/acct/gw/mistral/v1/ocr"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await service.process(_FAKE_PDF_BYTES, "application/pdf")

        mock_gw.assert_called_once_with("mistral", "v1/ocr")


# ---------------------------------------------------------------------------
# Tesseract fallback on Mistral 503
# ---------------------------------------------------------------------------


class TestTesseractFallbackOn503:
    @pytest.mark.asyncio
    async def test_falls_back_to_tesseract_on_mistral_503(self) -> None:
        """Mistral returns 503 → OCRService falls through to Tesseract."""
        service = OCRService()
        mock_503 = _make_httpx_response(503, text="Service Unavailable")

        tesseract_pages: list[OCRPage] = [OCRPage(page=1, text="Tesseract text", confidence=None)]

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"
            mock_settings.TESSERACT_LANG = "eng"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_503)
            mock_client_cls.return_value = mock_client

            mock_tess.return_value = tesseract_pages

            pages = await service.process(_FAKE_PDF_BYTES, "application/pdf")

        mock_tess.assert_called_once_with(_FAKE_PDF_BYTES, "application/pdf")
        assert pages[0]["confidence"] is None
        assert pages[0]["text"] == "Tesseract text"

    @pytest.mark.asyncio
    async def test_mistral_4xx_raises_not_falls_back(self) -> None:
        """Mistral 4xx (bad auth/bad request) must raise MistralOCRError, not fall back.

        Falling back to Tesseract on 4xx would silently produce garbage output
        while masking misconfiguration (e.g. wrong API key).
        """
        service = OCRService()
        mock_401 = _make_httpx_response(401, text="Unauthorized")

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "bad-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_401)
            mock_client_cls.return_value = mock_client

            from app.services.ocr_service import MistralOCRError

            with pytest.raises(MistralOCRError) as exc_info:
                await service.process(_FAKE_PDF_BYTES, "application/pdf")

        assert exc_info.value.status_code == 401
        mock_tess.assert_not_called()

    @pytest.mark.asyncio
    async def test_confidence_is_none_in_tesseract_results(self) -> None:
        """Tesseract results always have confidence=None to signal fallback was used."""
        service = OCRService()
        mock_503 = _make_httpx_response(503, text="Service Unavailable")

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_503)
            mock_client_cls.return_value = mock_client

            mock_tess.return_value = [OCRPage(page=1, text="abc", confidence=None)]

            pages = await service.process(_FAKE_PNG_BYTES, "image/png")

        for p in pages:
            assert p["confidence"] is None, "Tesseract fallback must set confidence=None"


# ---------------------------------------------------------------------------
# Tesseract fallback on timeout
# ---------------------------------------------------------------------------


class TestTesseractFallbackOnTimeout:
    @pytest.mark.asyncio
    async def test_falls_back_to_tesseract_on_timeout(self) -> None:
        """Mistral request raises TimeoutError → falls through to Tesseract."""
        service = OCRService()
        tesseract_pages: list[OCRPage] = [
            OCRPage(page=1, text="Timeout fallback text", confidence=None)
        ]

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            # Simulate timeout
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException(""))
            mock_client_cls.return_value = mock_client

            mock_tess.return_value = tesseract_pages

            pages = await service.process(_FAKE_PDF_BYTES, "application/pdf")

        mock_tess.assert_called_once()
        assert pages[0]["text"] == "Timeout fallback text"
        assert pages[0]["confidence"] is None

    @pytest.mark.asyncio
    async def test_mistral_disabled_goes_straight_to_tesseract(self) -> None:
        """MISTRAL_OCR_ENABLED=False → Mistral is never called; Tesseract runs directly."""
        service = OCRService()
        tesseract_pages: list[OCRPage] = [OCRPage(page=1, text="Direct Tesseract", confidence=None)]

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient"),
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
            patch.object(service, "_process_mistral", new_callable=AsyncMock) as mock_mist,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = False
            mock_tess.return_value = tesseract_pages

            pages = await service.process(_FAKE_PDF_BYTES, "application/pdf")

        mock_mist.assert_not_called()
        mock_tess.assert_called_once()
        assert pages[0]["text"] == "Direct Tesseract"


# ---------------------------------------------------------------------------
# Ephemeral guarantee — no /tmp files after either path
# ---------------------------------------------------------------------------


class TestEphemeralGuarantee:
    """Verify that no leftover files appear in /tmp after OCR extraction."""

    def _snapshot_tmp(self) -> set[str]:
        return set(glob.glob("/tmp/*"))

    @pytest.mark.asyncio
    async def test_no_tmp_files_after_mistral_path(self) -> None:
        """Mistral path: no files created in /tmp."""
        service = OCRService()
        mock_response = _make_httpx_response(200, json_body=_MISTRAL_SUCCESS_RESPONSE)
        before = self._snapshot_tmp()

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

            await service.process(_FAKE_PDF_BYTES, "application/pdf")

        after = self._snapshot_tmp()
        new_files = after - before
        assert not new_files, f"Mistral path left files in /tmp: {new_files}"

    @pytest.mark.asyncio
    async def test_no_tmp_files_after_tesseract_path(self) -> None:
        """Tesseract path: no files created in /tmp (pytesseract cleans up after itself)."""
        service = OCRService()
        before = self._snapshot_tmp()

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = False
            mock_tess.return_value = [OCRPage(page=1, text="tess", confidence=None)]

            await service.process(_FAKE_PNG_BYTES, "image/png")

        after = self._snapshot_tmp()
        new_files = after - before
        assert not new_files, f"Tesseract path left files in /tmp: {new_files}"


# ---------------------------------------------------------------------------
# DocLayout-YOLO integration — non-blocking
# ---------------------------------------------------------------------------


class TestDocLayoutYOLOIntegration:
    @pytest.mark.asyncio
    async def test_doclayout_failure_does_not_abort_ocr(self) -> None:
        """DocLayout-YOLO errors must not propagate — OCR result is still returned."""
        service = OCRService()
        mock_response = _make_httpx_response(200, json_body=_MISTRAL_SUCCESS_RESPONSE)

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch(
                "app.services.ocr_service._run_doclayout_analysis",
                new_callable=AsyncMock,
                side_effect=RuntimeError("YOLO model not loaded"),
            ),
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            # Should NOT raise despite layout analysis failing
            pages = await service.process(_FAKE_PDF_BYTES, "application/pdf")

        assert len(pages) == 2


# ---------------------------------------------------------------------------
# _process_tesseract — unavailable guards + _run_tesseract_sync paths
# ---------------------------------------------------------------------------


class TestProcessTesseractGuards:
    @pytest.mark.asyncio
    async def test_returns_empty_when_tesseract_not_available(self) -> None:
        """When pytesseract is absent, _process_tesseract returns [] gracefully."""
        service = OCRService()
        with (
            patch("app.services.ocr_service._TESSERACT_AVAILABLE", False),
            patch("app.services.ocr_service.settings") as mock_settings,
        ):
            mock_settings.TESSERACT_LANG = "eng"
            pages = await service._process_tesseract(b"bytes", "image/png")
        assert pages == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_pdf_deps_unavailable_for_pdf(self) -> None:
        """When pypdfium2/Pillow absent and input is PDF, returns [] gracefully."""
        service = OCRService()
        with (
            patch("app.services.ocr_service._TESSERACT_AVAILABLE", True),
            patch("app.services.ocr_service._PDF_DEPS_AVAILABLE", False),
            patch("app.services.ocr_service.settings") as mock_settings,
        ):
            mock_settings.TESSERACT_LANG = "eng"
            pages = await service._process_tesseract(b"bytes", "application/pdf")
        assert pages == []

    @pytest.mark.asyncio
    async def test_delegates_to_run_tesseract_sync_via_executor(self) -> None:
        """Happy path: both guards pass → run_in_executor calls _run_tesseract_sync."""
        service = OCRService()
        expected = [OCRPage(page=1, text="executor result", confidence=None)]

        with (
            patch("app.services.ocr_service._TESSERACT_AVAILABLE", True),
            patch("app.services.ocr_service._PDF_DEPS_AVAILABLE", True),
            patch("app.services.ocr_service.settings") as mock_settings,
            patch.object(service, "_run_tesseract_sync", return_value=expected) as mock_sync,
        ):
            mock_settings.TESSERACT_LANG = "deu"
            pages = await service._process_tesseract(b"pdf bytes", "application/pdf")

        mock_sync.assert_called_once_with(b"pdf bytes", "application/pdf", "deu")
        assert pages == expected


class TestRunTesseractSync:
    def test_pdf_path_calls_render_and_tesseract(self) -> None:
        """_run_tesseract_sync PDF branch: calls _render_pdf_bytes_to_pil_images + pytesseract."""
        mock_image = MagicMock()
        with (
            patch(
                "app.services.ocr_service._render_pdf_bytes_to_pil_images",
                return_value=[mock_image],
            ),
            patch("app.services.ocr_service.pytesseract") as mock_tess,
        ):
            mock_tess.image_to_string.return_value = "Extracted text"
            results = OCRService._run_tesseract_sync(b"pdf", "application/pdf", "eng")

        assert len(results) == 1
        assert results[0]["page"] == 1
        assert results[0]["text"] == "Extracted text"
        assert results[0]["confidence"] is None

    def test_image_path_uses_bytesio(self) -> None:
        """_run_tesseract_sync image branch: uses BytesIO + PIL Image.open."""
        mock_img = MagicMock()
        with (
            patch("app.services.ocr_service.Image") as mock_pil,
            patch("app.services.ocr_service.pytesseract") as mock_tess,
        ):
            mock_pil.open.return_value = mock_img
            mock_tess.image_to_string.return_value = "Image text"
            results = OCRService._run_tesseract_sync(b"\x89PNG\r\n", "image/png", "eng")

        assert len(results) == 1
        assert results[0]["page"] == 1
        assert results[0]["text"] == "Image text"
        assert results[0]["confidence"] is None


# ---------------------------------------------------------------------------
# Both paths fail — graceful degradation (not silent crash)
# ---------------------------------------------------------------------------


class TestBothPathsFailGracefully:
    """When both Mistral returns 5xx and Tesseract returns empty, process()
    must not crash — it returns empty list so the caller can surface a
    meaningful user-facing error."""

    @pytest.mark.asyncio
    async def test_mistral_5xx_and_tesseract_empty_returns_empty_list(self) -> None:
        """Mistral 503 + Tesseract returns [] → graceful empty result, no raise."""
        service = OCRService()
        mock_503 = MagicMock()
        mock_503.status_code = 503
        mock_503.text = "Service Unavailable"

        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_503)
            mock_client_cls.return_value = mock_client

            mock_tess.return_value = []  # Tesseract also failed

            pages = await service.process(_FAKE_PDF_BYTES, "application/pdf")

        mock_tess.assert_called_once()
        assert pages == [], "Both paths failed: should return empty list gracefully"
