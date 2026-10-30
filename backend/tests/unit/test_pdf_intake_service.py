"""Tests for provider-neutral PDF validation and routing."""

import pytest

from app.services.pdf_intake_service import (
    PDF_MAX_BYTES,
    PDFIntakeError,
    route_pdf_upload,
)


def test_routes_native_pdf_to_reference_translation() -> None:
    result = route_pdf_upload(b"%PDF-1.7 native text", "application/pdf")

    assert result is not None
    assert result.route == "pdf_reference_translation"
    assert result.output_mode == "reference"
    assert result.layout_preserved is True
    assert result.original_unchanged is True
    assert result.form_filling_supported is False
    assert result.is_fillable_form is False


def test_explicit_document_understanding_profile_does_not_claim_layout() -> None:
    result = route_pdf_upload(b"%PDF-1.7 native text", "application/pdf")

    assert result is not None
    understanding = result.document_understanding()
    assert understanding.route == "document_understanding_translation"
    assert understanding.output_mode == "extracted_text"
    assert understanding.layout_preserved is False


def test_routes_pdf_with_leading_comment() -> None:
    result = route_pdf_upload(b"%comment\n%PDF-1.7 content", "application/pdf")

    assert result is not None


def test_non_pdf_keeps_existing_route() -> None:
    assert route_pdf_upload(b"\x89PNG\r\n", "image/png") is None


def test_rejects_bytes_without_pdf_header() -> None:
    with pytest.raises(PDFIntakeError) as exc_info:
        route_pdf_upload(b"not a pdf", "application/pdf")

    assert exc_info.value.code == "INVALID_PDF"
    assert exc_info.value.status_code == 422


def test_rejects_pdf_header_after_scan_window() -> None:
    with pytest.raises(PDFIntakeError) as exc_info:
        route_pdf_upload(b"x" * 1024 + b"%PDF-1.7", "application/pdf")

    assert exc_info.value.code == "INVALID_PDF"


def test_rejects_oversized_pdf_before_processing() -> None:
    with pytest.raises(PDFIntakeError) as exc_info:
        route_pdf_upload(b"%PDF" + b"x" * PDF_MAX_BYTES, "application/pdf")

    assert exc_info.value.code == "FILE_TOO_LARGE"
    assert exc_info.value.status_code == 413
