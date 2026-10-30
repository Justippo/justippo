"""Provider-neutral validation and routing for PDF uploads.

This module intentionally performs no PDF parsing. The Cloudflare Python Worker
stays dependency-free and in-memory; provider stages added later will determine
page count, encryption, and renderability.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.models.pdf_intake import PDFProcessingProfile

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
PDF_HEADER_SCAN_BYTES = 1024
PDF_MAX_BYTES = 10 * 1024 * 1024
PDFIntakeErrorCode = Literal["FILE_TOO_LARGE", "INVALID_PDF"]

# PDFium FORMTYPE_NONE == 0 — any other value means the PDF carries an
# interactive form (AcroForm, XFA, or XFAF). See pypdfium2 internal.consts
# .FormTypeToStr = {0: 'None', 1: 'AcroForm', 2: 'XFA', 3: 'XFAF'}.
_FORMTYPE_NONE = 0


class PDFIntakeError(ValueError):
    """A typed, content-safe PDF intake rejection."""

    def __init__(
        self,
        *,
        code: PDFIntakeErrorCode,
        message: str,
        status_code: int,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def route_pdf_upload(
    file_bytes: bytes,
    content_type: str,
) -> PDFProcessingProfile | None:
    """Validate and route PDF bytes; leave non-PDF upload behavior unchanged."""
    if content_type != PDF_CONTENT_TYPE:
        return None

    if len(file_bytes) > PDF_MAX_BYTES:
        raise PDFIntakeError(
            code="FILE_TOO_LARGE",
            message="PDF exceeds the 10 MiB upload limit",
            status_code=413,
        )

    # ISO 32000 readers conventionally search the opening 1,024 bytes for the
    # header. Accept the historical test-fixture shorthand `%PDF` as well as a
    # complete `%PDF-x.y` header; the document processor performs full parsing.
    if b"%PDF" not in file_bytes[:PDF_HEADER_SCAN_BYTES]:
        raise PDFIntakeError(
            code="INVALID_PDF",
            message="The uploaded file is not a readable PDF",
            status_code=422,
        )

    return PDFProcessingProfile(is_fillable_form=_detect_fillable_form(file_bytes))


def _detect_fillable_form(file_bytes: bytes) -> bool:
    """Detect an interactive form (AcroForm/XFA) without extracting content.

    Read-only, in-memory check via pypdfium2 (already a dependency — ADR-006).
    Never raises: a detection failure degrades to "not a form" so the existing
    reference/understanding routing is unaffected by this signal.
    """
    # Lazy import: pypdfium2 is not available in Pyodide (Cloudflare Workers).
    # Match the lazy-import pattern already used in ocr_service.py.
    try:
        import pypdfium2 as pdfium
        from pypdfium2 import PdfiumError
    except ImportError:
        return False
    try:
        pdf = pdfium.PdfDocument(file_bytes)
    except (PdfiumError, Exception):  # noqa: BLE001 — detection must never block upload
        return False
    try:
        return bool(pdf.get_formtype() != _FORMTYPE_NONE)
    except Exception:  # noqa: BLE001
        return False
    finally:
        pdf.close()
