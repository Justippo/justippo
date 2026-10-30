# SPDX-License-Identifier: AGPL-3.0-or-later
# See docs/adr/ADR-006 — do not re-introduce pymupdf or fitz imports
"""
OCR Service — Document Text and Layout Extraction (Sprint 2)

Responsibilities:
- Accept uploaded file bytes + MIME type (PDF/DOCX/PNG/JPEG)
- Extract text content preserving reading order and structure
- Route to Mistral OCR (primary) or Tesseract (fallback) based on config and availability
- Return structured page-level results ready for RAG indexing or translation

Data flow:
  file_bytes + mime_type
    → [mistral_ocr | tesseract_fallback]
    → list[OCRPage]
    → (non-blocking) doclayout_yolo layout analysis

Ephemeral guarantee:
  No file_bytes, page images, or extracted text are written to disk or any DB
  at any point in this service. All processing is in-memory via BytesIO.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import httpx

from app.core.config import settings
from app.integrations.azure_document_intelligence import (
    SUPPORTED_CONTENT_TYPES as AZURE_CONTENT_TYPES,
)
from app.integrations.azure_document_intelligence import (
    AzureDocumentAnalysis,
    AzureDocumentIntelligenceError,
    analyze_pdf,
    get_analysis_limits,
)
from app.integrations.azure_document_intelligence import is_enabled as azure_is_enabled
from app.integrations.cloudflare.gateway import get_gateway_auth_headers, get_gateway_url
from app.integrations.laminar import observe
from app.integrations.langfuse import observe_generation

if TYPE_CHECKING:
    from collections.abc import Generator

# pypdfium2 and Pillow are Sprint 2 dependencies not available in Pyodide.
# Import lazily so the worker boots cleanly; ImportError surfaces only when
# OCR is actually invoked (Sprint 2+).
try:
    import pypdfium2 as pdfium
    from PIL import Image
    from pypdfium2 import PdfiumError

    _PDF_DEPS_AVAILABLE: bool = True
except ImportError:  # pragma: no cover
    _PDF_DEPS_AVAILABLE = False

try:
    import pytesseract

    _TESSERACT_AVAILABLE: bool = True
except ImportError:  # pragma: no cover
    _TESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_RENDER_DPI = 300
"""DPI used when rasterizing PDF pages for OCR (1 PDF point = 1/72 inch)."""

_MISTRAL_OCR_MODEL = "mistral-ocr-latest"

_MISTRAL_TIMEOUT_SECONDS = 30
"""Per-request timeout for Mistral OCR. On expiry, falls through to Tesseract."""

_HTTP_TOO_MANY_REQUESTS = 429
_MISTRAL_429_MAX_RETRIES = 2
"""Extra attempts after a 429. Mistral limits are per-second/minute, so a short
wait usually clears them; more retries would eat into the NFR-01 latency budget."""
_MISTRAL_429_MAX_DELAY_S = 4.0
"""Upper bound on any single wait, whatever Retry-After says."""

_SUPPORTED_PDF_SUFFIXES: frozenset[str] = frozenset({".pdf"})

_MIME_TO_DOCUMENT_TYPE: dict[str, str] = {
    "application/pdf": "document_url",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document_url",
    "image/png": "image_url",
    "image/jpeg": "image_url",
    "image/jpg": "image_url",
    "image/webp": "image_url",
}

_MIME_TO_DATA_URI_PREFIX: dict[str, str] = {
    "application/pdf": "data:application/pdf;base64,",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,",
    "image/png": "data:image/png;base64,",
    "image/jpeg": "data:image/jpeg;base64,",
    "image/jpg": "data:image/jpeg;base64,",
    "image/webp": "data:image/webp;base64,",
}


# ---------------------------------------------------------------------------
# Typed return schema
# ---------------------------------------------------------------------------


class OCRPage(TypedDict):
    """Single page result from OCR extraction.

    confidence is None when the Tesseract fallback path was used,
    signalling that no model-level confidence is available.
    """

    page: int
    text: str
    confidence: float | None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OCRError(Exception):
    """Base error for OCR service failures."""


class MistralOCRError(OCRError):
    """Raised when the Mistral OCR API returns an error response."""

    def __init__(self, status_code: int, detail: str, retry_after: float | None = None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        """Seconds the upstream asked us to wait (429 only); None when not provided."""
        super().__init__(f"Mistral OCR API error {status_code}: {detail}")

    @property
    def is_rate_limited(self) -> bool:
        return self.status_code == _HTTP_TOO_MANY_REQUESTS


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Seconds from a numeric Retry-After header, or None if absent/unparseable."""
    raw = response.headers.get("retry-after")
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except ValueError:  # HTTP-date form: not worth parsing for a 4s cap
        return None


def _rate_limit_delay(response: httpx.Response, attempt: int) -> float:
    """Wait before retrying a 429: honour Retry-After, else 1s, 2s, ... — capped."""
    hinted = _parse_retry_after(response)
    delay = hinted if hinted is not None else float(2**attempt)
    return min(delay, _MISTRAL_429_MAX_DELAY_S)


class OCRTierLimitError(OCRError):
    """The document exceeds the configured OCR provider tier's size/page limits."""


_PDF_PAGE_OBJ_RE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")
_PDF_COUNT_RE = re.compile(rb"/Count\s+(\d+)")


def _pdf_bytes_page_count(file_bytes: bytes) -> int | None:
    """Best-effort page count of in-memory PDF bytes, or None if unknown.

    None means "unknown", never "zero": callers skip the page-limit pre-check and
    let the provider decide. EPHEMERAL: bytes are only read in memory.

    Strategy: pypdfium2 when present (exact; local/CI). The Worker runs on Pyodide
    where pypdfium2 does not exist, so otherwise scan the raw bytes for page
    objects and the page-tree ``/Count`` and take the larger. This is a lower
    bound: PDFs whose page tree lives in compressed object streams can be
    undercounted, in which case the provider's own limits still apply.
    """
    if _PDF_DEPS_AVAILABLE:
        try:
            return len(pdfium.PdfDocument(file_bytes))
        except Exception:  # noqa: BLE001 - fall through to the byte scan
            pass
    counts = [int(m) for m in _PDF_COUNT_RE.findall(file_bytes)]
    estimate = max(len(_PDF_PAGE_OBJ_RE.findall(file_bytes)), max(counts, default=0))
    return estimate or None


class PDFExtractionError(Exception):
    """Base error for PDF extraction failures."""


class PDFFileNotFoundError(PDFExtractionError):
    """Raised when the PDF file does not exist at the given path."""


class PDFInvalidError(PDFExtractionError):
    """Raised when the file is not a valid PDF or is corrupted."""


class PDFEncryptedError(PDFExtractionError):
    """Raised when the PDF is password-protected and no password was provided."""


class PDFEmptyError(PDFExtractionError):
    """Raised when the PDF contains zero pages."""


# ---------------------------------------------------------------------------
# Data model (legacy file-path API — kept for backward compatibility)
# ---------------------------------------------------------------------------


@dataclass
class ExtractedContent:
    document_id: str
    text: str
    language: str
    page_count: int
    layout_metadata: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# PDF helpers (pypdfium2, Apache-2.0/BSD-3 — ADR-006)
# ---------------------------------------------------------------------------


def _validate_pdf_path(file_path: Path) -> None:
    """Validate that file_path exists and has a .pdf extension."""
    if not file_path.exists():
        raise PDFFileNotFoundError(f"PDF file not found: {file_path}")
    if file_path.suffix.lower() not in _SUPPORTED_PDF_SUFFIXES:
        raise PDFInvalidError(f"Expected a .pdf file, got '{file_path.suffix}': {file_path}")


def _open_pdf(file_path: Path) -> pdfium.PdfDocument:
    """Open a PDF with comprehensive error handling."""
    _validate_pdf_path(file_path)
    try:
        return pdfium.PdfDocument(file_path)
    except PdfiumError as exc:
        msg = str(exc).lower()
        if "password" in msg or "encrypted" in msg:
            raise PDFEncryptedError(f"PDF is password-protected: {file_path}") from exc
        raise PDFInvalidError(
            f"Failed to open PDF (corrupted or malformed): {file_path} — {exc}"
        ) from exc
    except Exception as exc:
        raise PDFInvalidError(f"Unexpected error opening PDF: {file_path} — {exc}") from exc


def pdf_page_count(file_path: Path) -> int:
    """Return the number of pages in a PDF document."""
    pdf = _open_pdf(file_path)
    try:
        count = len(pdf)
        if count == 0:
            raise PDFEmptyError(f"PDF has zero pages: {file_path}")
        return count
    except PDFEmptyError:
        raise
    except Exception as exc:
        raise PDFInvalidError(f"Unexpected error parsing PDF length: {file_path} — {exc}") from exc
    finally:
        pdf.close()


def pdf_extract_text(file_path: Path) -> str:
    """Extract text from all pages of a PDF, preserving reading order."""
    pdf = _open_pdf(file_path)
    try:
        page_count = len(pdf)
        if page_count == 0:
            raise PDFEmptyError(f"PDF has zero pages: {file_path}")
        pages_text: list[str] = []
        for i in range(page_count):
            page = pdf[i]
            textpage = page.get_textpage()
            pages_text.append(textpage.get_text_bounded())
            textpage.close()
            page.close()
        return "\n\n".join(pages_text)
    except PDFEmptyError:
        raise
    except Exception as exc:
        raise PDFInvalidError(f"Unexpected error parsing PDF length: {file_path} — {exc}") from exc
    finally:
        pdf.close()


def pdf_render_pages(
    file_path: Path, *, dpi: int = _DEFAULT_RENDER_DPI
) -> Generator[Image.Image, None, None]:
    """Yield each page of a PDF as a PIL Image at the given DPI.

    EPHEMERAL: images are held in memory only — never written to disk.
    """
    if dpi <= 0:
        raise ValueError(f"dpi must be a positive integer, got {dpi}")
    scale = dpi / 72
    pdf = _open_pdf(file_path)
    try:
        page_count = len(pdf)
        if page_count == 0:
            raise PDFEmptyError(f"PDF has zero pages: {file_path}")
        for i in range(page_count):
            page = pdf[i]
            bitmap = page.render(scale=scale)
            # EPHEMERAL: .copy() keeps image in memory after page/bitmap are released;
            # this is never a file write — bitmap.to_pil() returns a PIL.Image backed
            # by in-memory bytes, not a tempfile.
            pil_image = bitmap.to_pil().copy()
            page.close()
            yield pil_image
    except PDFEmptyError:
        raise
    except Exception as exc:
        raise PDFInvalidError(f"Unexpected error parsing PDF length: {file_path} — {exc}") from exc
    finally:
        pdf.close()


def _render_pdf_bytes_to_pil_images(
    pdf_bytes: bytes, *, dpi: int = _DEFAULT_RENDER_DPI
) -> list[Image.Image]:
    """Render all pages of an in-memory PDF buffer to PIL Images.

    EPHEMERAL: pdf_bytes and resulting images never touch the filesystem.
    pypdfium2 accepts a bytes object directly — no tempfile is created.
    """
    if dpi <= 0:
        raise ValueError(f"dpi must be a positive integer, got {dpi}")
    # EPHEMERAL: PdfDocument(bytes) loads the PDF entirely in RAM;
    # no intermediate file is written by pypdfium2 for this call path.
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        # Initialize the form environment BEFORE rendering so that filled-in
        # AcroForm/XFA field values are drawn into the bitmap. Without this,
        # PDFium renders only the blank template — Tesseract then OCRs an
        # empty form, silently dropping every value the user filled in.
        # No-op for PDFs without forms (see pypdfium2 init_forms() docs);
        # wrapped defensively so a forms-layer quirk degrades to prior
        # (template-only) rendering rather than aborting extraction.
        pdf.init_forms()
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF form initialization failed — rendering without form layer (%s)", exc)
    images: list[Image.Image] = []
    scale = dpi / 72
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = page.render(scale=scale)
            images.append(bitmap.to_pil().copy())
            page.close()
    finally:
        pdf.close()
    return images


def pdf_metadata(file_path: Path) -> dict[str, str]:
    """Return standard PDF metadata (Title, Author, etc.)."""
    pdf = _open_pdf(file_path)
    try:
        result: dict[str, str] = pdf.get_metadata_dict(skip_empty=True)
        return result
    finally:
        pdf.close()


# ---------------------------------------------------------------------------
# DocLayout-YOLO integration stub (non-blocking)
# ---------------------------------------------------------------------------


async def _run_doclayout_analysis(
    pages: list[OCRPage],
    page_images: list[Image.Image] | None,
) -> dict[str, object]:
    """Pass OCR results to DocLayout-YOLO for layout analysis.

    Non-blocking: if the integration is unavailable, logs a warning and returns {}.
    EPHEMERAL: page_images are in-memory PIL objects; nothing is persisted here.
    """
    try:
        from app.integrations.ocr import analyze_layout  # type: ignore[attr-defined]

        result: dict[str, object] = await analyze_layout(pages=pages, page_images=page_images)
        return result
    except (ImportError, NotImplementedError):
        logger.warning(
            "DocLayout-YOLO integration unavailable — layout analysis skipped. "
            "Text extraction results are still complete."
        )
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DocLayout-YOLO analysis failed (%s) — continuing without layout metadata.", exc
        )
        return {}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OCRService:
    """
    Abstracts over Mistral OCR (cloud) and Tesseract (local fallback).

    Primary API: process(file_bytes, mime_type) → list[OCRPage]
    Legacy API:  extract(file_path) → ExtractedContent  (kept for backward compat)

    Routing logic:
      - MISTRAL_OCR_ENABLED=true  → try Mistral first
      - Mistral timeout (30 s) or 5xx  → fall through to Tesseract
      - MISTRAL_OCR_ENABLED=false  → Tesseract directly
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public Sprint-2 API
    # ------------------------------------------------------------------

    # ADD: trace engine used (Mistral/Tesseract), page count, confidence score
    @observe(name="document.ocr", span_type="TOOL")
    # END ADD
    async def process(
        self,
        file_bytes: bytes,
        mime_type: str,
        *,
        is_fillable_form: bool = False,
        azure_analysis: AzureDocumentAnalysis | None = None,
    ) -> list[OCRPage]:
        """Extract text from document bytes, returning per-page structured results.

        Args:
            file_bytes: Raw document bytes (PDF, DOCX, PNG, JPEG, WEBP).
            mime_type:  MIME type string, e.g. "application/pdf", "image/png".
            is_fillable_form: When True (PDF has an AcroForm/XFA layer, detected
                at intake), prefer Azure Document Intelligence — its
                ``keyValuePairs`` feature reliably reads filled-in field values,
                whereas Mistral/Tesseract rasterization can miss them (see
                ``_render_pdf_bytes_to_pil_images``). Falls through to
                Mistral/Tesseract if Azure is disabled, over the tier's byte
                limit, or the call fails.
            azure_analysis: Pre-fetched Azure result to reuse instead of making
                a second API call (the caller may already need Azure output for
                document-understanding; F0 allows 1 request/second). Used by the
                fillable-form path and by the Azure fallback.

        Returns:
            List of OCRPage dicts ordered by page index (1-based).
            confidence is None when Tesseract fallback was used.

        EPHEMERAL: file_bytes are never written to disk at any point in this method.
        """
        # EPHEMERAL: file_bytes is a plain bytes object; it lives only in heap memory.
        # Do NOT pass it to any function that writes to disk (e.g., open(..., "wb")).
        pages: list[OCRPage] = []
        mistral_error: MistralOCRError | None = None

        if is_fillable_form and mime_type == "application/pdf":
            form_pages = await self._process_fillable_form(file_bytes, azure_analysis)
            if form_pages is not None:
                try:
                    await _run_doclayout_analysis(form_pages, page_images=None)
                except Exception as _layout_exc:  # noqa: BLE001
                    logger.warning("Layout analysis raised unexpectedly: %s", _layout_exc)
                return form_pages

        if settings.MISTRAL_OCR_ENABLED:
            try:
                pages = await self._process_mistral(file_bytes, mime_type)
            except httpx.TimeoutException:
                logger.warning(
                    "Mistral OCR timed out after %ds — falling back to Tesseract.",
                    _MISTRAL_TIMEOUT_SECONDS,
                )
            except MistralOCRError as exc:
                if exc.status_code < 500 and not exc.is_rate_limited:
                    # 4xx (except 429) = bad auth / malformed request — no fallback
                    # can fix this; re-raise so the caller gets a meaningful error
                    # instead of silent garbage output.
                    raise
                mistral_error = exc
                logger.warning(
                    "Mistral OCR returned %s — falling back (Azure, then Tesseract).", exc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Mistral OCR unexpected error (%s) — falling back to Tesseract.", exc
                )
            else:
                # Mistral succeeded — run layout analysis (non-blocking) and return.
                # Guard with try/except: layout analysis must never abort OCR results.
                try:
                    await _run_doclayout_analysis(pages, page_images=None)
                except Exception as _layout_exc:  # noqa: BLE001
                    logger.warning("Layout analysis raised unexpectedly: %s", _layout_exc)
                return pages

        # Fallback chain (also used when MISTRAL_OCR_ENABLED=False): Azure, then
        # Tesseract. OCRTierLimitError deliberately propagates — an over-limit
        # document must surface as a clear error, not as silently truncated text.
        try:
            pages = await self._process_azure(file_bytes, mime_type, azure_analysis)
        except AzureDocumentIntelligenceError as exc:
            logger.warning("Azure OCR fallback unavailable (%s).", exc)
            pages = []
        if pages:
            try:
                await _run_doclayout_analysis(pages, page_images=None)
            except Exception as _layout_exc:  # noqa: BLE001
                logger.warning("Layout analysis raised unexpectedly: %s", _layout_exc)
            return pages

        if mistral_error is not None and mistral_error.is_rate_limited:
            # Tesseract cannot run on the Worker (no native binary); returning its
            # empty result would look like success. Report the real cause instead.
            raise mistral_error

        pages = await self._process_tesseract(file_bytes, mime_type)
        try:
            await _run_doclayout_analysis(pages, page_images=None)
        except Exception as _layout_exc:  # noqa: BLE001
            logger.warning("Layout analysis raised unexpectedly: %s", _layout_exc)
        return pages

    # ------------------------------------------------------------------
    # Fillable-form path (Azure Document Intelligence)
    # ------------------------------------------------------------------

    async def _process_fillable_form(
        self,
        file_bytes: bytes,
        azure_analysis: AzureDocumentAnalysis | None,
    ) -> list[OCRPage] | None:
        """Extract text from a fillable PDF via Azure Document Intelligence.

        Returns None (never raises) when Azure is disabled, the document
        exceeds the configured tier's byte limit, or the call fails — the
        caller falls through to the Mistral/Tesseract path in that case.

        Azure's ``prebuilt-layout`` model (with ``keyValuePairs`` requested —
        see ``analyze_pdf``) reads filled-in AcroForm/XFA field values directly
        from the PDF's form dictionary, which is what Mistral/Tesseract
        rasterization can miss for interactive forms.
        """
        try:
            pages = await self._process_azure(file_bytes, "application/pdf", azure_analysis)
        except OCRTierLimitError as exc:
            logger.info(
                "Fillable form exceeds Azure tier limits (%s) — using Mistral/Tesseract.", exc
            )
            return None
        except AzureDocumentIntelligenceError as exc:
            logger.warning(
                "Azure form analysis unavailable (%s) — falling back to Mistral/Tesseract.",
                exc,
            )
            return None
        return pages or None

    async def _process_azure(
        self,
        file_bytes: bytes,
        mime_type: str,
        azure_analysis: AzureDocumentAnalysis | None = None,
    ) -> list[OCRPage]:
        """Extract text via Azure Document Intelligence (shared by form + fallback paths).

        Returns ``[]`` when Azure cannot serve the request: disabled, unsupported
        media type, or empty content. Callers treat that as "try the next option".

        Raises:
            OCRTierLimitError: document exceeds the configured tier's byte/page
                limit. Checked up front because F0 silently analyses only the
                first pages — truncated text must never look like a full result.
            AzureDocumentIntelligenceError: provider/config failure.

        Azure's layout model returns one markdown document per analysis, not
        per-page text. The full content is attributed to page 1 rather than
        guessing a page split — downstream consumers treat OCRPage.text as the
        source of truth regardless of how many physical pages exist.
        """
        analysis = azure_analysis
        if analysis is None:
            if not azure_is_enabled() or mime_type not in AZURE_CONTENT_TYPES:
                return []
            limits = get_analysis_limits()
            if len(file_bytes) > limits.max_bytes:
                raise OCRTierLimitError(
                    f"{len(file_bytes)} bytes exceeds the {limits.tier} limit of "
                    f"{limits.max_bytes} bytes"
                )
            if mime_type == "application/pdf":
                page_count = _pdf_bytes_page_count(file_bytes)
                if page_count is not None and page_count > limits.max_pages:
                    raise OCRTierLimitError(
                        f"{page_count} pages exceeds the {limits.tier} limit of "
                        f"{limits.max_pages} pages"
                    )
            analysis = await analyze_pdf(file_bytes, content_type=mime_type)

        if not analysis.content.strip():
            return []
        return [OCRPage(page=1, text=analysis.content, confidence=None)]

    # ------------------------------------------------------------------
    # Mistral OCR path
    # ------------------------------------------------------------------

    # ADD: Langfuse GENERATION span — traces Mistral OCR model/tokens/latency
    @observe_generation(name="ocr.mistral", model="mistral-ocr")
    # END ADD
    async def _process_mistral(self, file_bytes: bytes, mime_type: str) -> list[OCRPage]:
        """Call Mistral OCR via Cloudflare AI Gateway and parse results.

        EPHEMERAL: file_bytes are base64-encoded in-memory; no disk writes occur.
        The base64 string is constructed in a local variable and discarded after
        the HTTP response is received.

        Raises:
            MistralOCRError: on any 4xx/5xx HTTP response from the gateway.
            httpx.TimeoutException: if the request exceeds _MISTRAL_TIMEOUT_SECONDS.
        """
        # EPHEMERAL: base64.b64encode() returns a bytes object in RAM only.
        # Do NOT write b64_str to a file or DB — it is the full document content.
        b64_str: str = base64.b64encode(file_bytes).decode("ascii")

        doc_type = _MIME_TO_DOCUMENT_TYPE.get(mime_type, "document_url")
        data_uri_prefix = _MIME_TO_DATA_URI_PREFIX.get(
            mime_type, "data:application/octet-stream;base64,"
        )
        # EPHEMERAL: data_uri is a string in heap memory; not persisted anywhere.
        data_uri = f"{data_uri_prefix}{b64_str}"

        # Always route through the Cloudflare AI Gateway — never call Mistral directly.
        gateway_url = get_gateway_url("mistral", "v1/ocr")

        payload: dict[str, object] = {
            "model": _MISTRAL_OCR_MODEL,
            "document": {
                "type": doc_type,
                doc_type: data_uri,
            },
            "confidence_scores_granularity": "page",
        }

        async with httpx.AsyncClient(timeout=_MISTRAL_TIMEOUT_SECONDS) as client:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            # BYOK: when the gateway has a stored Mistral key (Provider Keys in
            # dashboard), it injects the Authorization header automatically.
            # We still send the key as a fallback for environments where BYOK
            # is not yet configured (local dev, CI). When both BYOK and a local
            # key are present, the gateway ignores our Authorization in favour
            # of the stored key.
            if settings.MISTRAL_API_KEY:  # pragma: no cover - CI runs without BYOK key
                headers["Authorization"] = f"Bearer {settings.MISTRAL_API_KEY}"
            # Authenticate to the gateway itself for provider-native URLs.
            # AI Gateway bindings are pre-authenticated; raw HTTPS calls are not.
            headers.update(get_gateway_auth_headers())

            # Only 429 is retried: it is the one 4xx that is transient by definition.
            for attempt in range(_MISTRAL_429_MAX_RETRIES + 1):
                response = await client.post(
                    gateway_url,
                    json=payload,
                    headers=headers,
                )
                if response.status_code != _HTTP_TOO_MANY_REQUESTS:
                    break
                if attempt < _MISTRAL_429_MAX_RETRIES:
                    delay = _rate_limit_delay(response, attempt)
                    logger.warning(
                        "Mistral OCR rate-limited (429) — retry %d/%d in %.1fs.",
                        attempt + 1,
                        _MISTRAL_429_MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)

        if response.status_code >= 400:
            # 5xx triggers Tesseract fallback in process(); 4xx (incl. an exhausted
            # 429) surfaces as a hard error. retry_after lets the API tell the client
            # when to try again.
            raise MistralOCRError(
                response.status_code,
                response.text[:200],
                retry_after=_parse_retry_after(response),
            )

        data = response.json()
        return self._parse_mistral_response(data)

    @staticmethod
    def _parse_mistral_response(data: dict[str, object]) -> list[OCRPage]:
        """Convert raw Mistral OCR JSON response to the OCRPage schema.

        Response schema (from Mistral docs):
            {"pages": [{"index": int, "markdown": str, "confidence_scores": dict|null, ...}]}
        """
        raw_pages: list[dict[str, object]] = data.get("pages", [])  # type: ignore[assignment]
        results: list[OCRPage] = []
        for raw in raw_pages:
            index: int = int(str(raw.get("index", 0) or 0))
            text: str = str(raw.get("markdown", "") or "")
            confidence_scores = raw.get("confidence_scores")
            confidence: float | None = None
            if isinstance(confidence_scores, dict):
                avg = confidence_scores.get("average_page_confidence_score")
                if avg is not None:
                    confidence = float(avg)
            results.append(OCRPage(page=index + 1, text=text, confidence=confidence))
        return results

    # ------------------------------------------------------------------
    # Tesseract fallback path
    # ------------------------------------------------------------------

    async def _process_tesseract(self, file_bytes: bytes, mime_type: str) -> list[OCRPage]:
        """Extract text via Tesseract (local, offline fallback).

        EPHEMERAL: all rasterized PIL images are created in-memory via BytesIO
        and pypdfium2's in-memory PDF loader.  No intermediate files are written
        to /tmp or any other path.

        Returns:
            List of OCRPage with confidence=None (Tesseract provides no model confidence).
        """
        if not _TESSERACT_AVAILABLE:
            logger.error("pytesseract is not installed; cannot use Tesseract fallback.")
            return []
        if not _PDF_DEPS_AVAILABLE and mime_type == "application/pdf":
            logger.error("pypdfium2/Pillow not available; cannot rasterize PDF for Tesseract.")
            return []

        lang: str = settings.TESSERACT_LANG

        # Run the blocking pytesseract calls in a thread pool to avoid blocking
        # the async event loop.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._run_tesseract_sync, file_bytes, mime_type, lang
        )

    @staticmethod
    def _run_tesseract_sync(file_bytes: bytes, mime_type: str, lang: str) -> list[OCRPage]:
        """Synchronous Tesseract extraction (called from thread pool executor).

        EPHEMERAL: PDF-to-image conversion uses pypdfium2's in-memory loader
        (PdfDocument(bytes)) — no tempfile is created.
        PIL images are kept in heap memory only.
        """
        results: list[OCRPage] = []

        if mime_type == "application/pdf":
            # EPHEMERAL: _render_pdf_bytes_to_pil_images accepts raw bytes;
            # pypdfium2 does NOT write a tempfile for this call path.
            images = _render_pdf_bytes_to_pil_images(file_bytes)
            for page_num, img in enumerate(images, start=1):
                # EPHEMERAL: pytesseract.image_to_string() receives a PIL Image
                # object held in memory; pytesseract writes a temporary internal
                # file during processing but cleans it up automatically.
                # We do NOT write img to disk here.
                text: str = pytesseract.image_to_string(img, lang=lang)
                results.append(OCRPage(page=page_num, text=text, confidence=None))
        else:
            # Image types (PNG, JPEG, WEBP, etc.)
            # EPHEMERAL: BytesIO wraps file_bytes in memory; Image.open() reads
            # from the buffer without creating any file on disk.
            buf = BytesIO(file_bytes)
            img = Image.open(buf)
            text = pytesseract.image_to_string(img, lang=lang)
            results.append(OCRPage(page=1, text=text, confidence=None))

        return results

    # ------------------------------------------------------------------
    # Legacy file-path API (Sprint 1 stub signatures — do not remove)
    # ------------------------------------------------------------------

    async def extract(self, file_path: Path) -> ExtractedContent:
        """Extract text and layout metadata from a PDF or image file.

        Reads file_path into bytes and delegates to process().
        Kept for backward compatibility with Sprint 1 call sites.

        EPHEMERAL: file contents are read into a local bytes variable and
        never re-persisted. The bytes object is garbage-collected after this call.
        """
        mime_type = _infer_mime_type(file_path)
        # EPHEMERAL: file_bytes is read into RAM here. Do not write it back
        # anywhere else in this method.
        file_bytes = file_path.read_bytes()
        pages = await self.process(file_bytes, mime_type)
        full_text = "\n\n".join(p["text"] for p in pages)
        avg_conf = (
            sum(p["confidence"] for p in pages if p["confidence"] is not None)
            / max(1, sum(1 for p in pages if p["confidence"] is not None))
            if pages
            else 0.0
        )
        return ExtractedContent(
            document_id=file_path.stem,
            text=full_text,
            language="",  # Populated by detect_language() in caller
            page_count=len(pages),
            layout_metadata={},
            confidence=avg_conf,
        )

    async def _extract_mistral(self, file_path: Path) -> ExtractedContent:
        """Mistral OCR path via file path (legacy stub — delegates to process())."""
        mime_type = _infer_mime_type(file_path)
        file_bytes = file_path.read_bytes()
        pages = await self._process_mistral(file_bytes, mime_type)
        full_text = "\n\n".join(p["text"] for p in pages)
        avg_conf = (
            sum(p["confidence"] for p in pages if p["confidence"] is not None)
            / max(1, sum(1 for p in pages if p["confidence"] is not None))
            if pages
            else 0.0
        )
        return ExtractedContent(
            document_id=file_path.stem,
            text=full_text,
            language="",
            page_count=len(pages),
            confidence=avg_conf,
        )

    async def _extract_tesseract(self, file_path: Path) -> ExtractedContent:
        """Tesseract fallback via file path (legacy stub — delegates to process())."""
        mime_type = _infer_mime_type(file_path)
        file_bytes = file_path.read_bytes()
        pages = await self._process_tesseract(file_bytes, mime_type)
        full_text = "\n\n".join(p["text"] for p in pages)
        return ExtractedContent(
            document_id=file_path.stem,
            text=full_text,
            language="",
            page_count=len(pages),
            confidence=0.0,
        )

    async def detect_language(self, text_sample: str) -> str:
        """Detect the primary language of a text sample (returns ISO 639-1 code)."""
        from app.core.lang_detect import detect_language

        return detect_language(text_sample, default="en")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_mime_type(file_path: Path) -> str:
    """Infer MIME type from file extension for the legacy file-path API."""
    suffix = file_path.suffix.lower()
    mapping: dict[str, str] = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return mapping.get(suffix, "application/octet-stream")
