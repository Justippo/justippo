"""HTTP contract tests for the composed PDF reference route."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.document_explanation import DocumentExplanation
from app.models.pdf_reference_translation import (
    PDFReferenceTranslationErrorDetail,
    PDFReferenceTranslationResult,
)
from app.services.classification_service import DocumentClassification
from app.services.pdf_reference_translation_service import PDFReferenceTranslationError


def _result() -> PDFReferenceTranslationResult:
    return PDFReferenceTranslationResult(
        request_id="request-123",
        source_language="en",
        target_language="de",
        translated_pdf_b64=base64.b64encode(b"%PDF-1.7 translated").decode("ascii"),
        detected_source_language="en",
        layout_preserved=True,
        pages_processed=1,
        classification=DocumentClassification(language_code="en"),
        document_explanation=DocumentExplanation(
            document_type="unknown",
            language="de",
            requirements=[],
            legal_context_status="not_found",
            citations=[],
        ),
    )


def test_pdf_reference_endpoint_returns_ephemeral_result() -> None:
    workflow = AsyncMock(return_value=_result())
    with patch("app.api.v1.endpoints.translate.translate_pdf_reference", workflow):
        response = TestClient(app, headers={"X-GDPR-Consent": "test"}).post(
            "/api/v1/translate/pdf-reference",
            files={"file": ("form.pdf", b"%PDF-1.7 fixture", "application/pdf")},
            data={
                "source_language": "en",
                "target_language": "de",
                "expected_page_count": "1",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["ephemeral"] is True
    assert payload["original_unchanged"] is True
    assert payload["form_filling_supported"] is False
    workflow.assert_awaited_once_with(b"%PDF-1.7 fixture", "en", "de", 1)


def test_pdf_reference_endpoint_returns_typed_safe_error() -> None:
    workflow = AsyncMock(
        side_effect=PDFReferenceTranslationError(
            PDFReferenceTranslationErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="PDF structure analysis is unavailable",
                retryable=False,
            ),
            503,
        )
    )
    with patch("app.api.v1.endpoints.translate.translate_pdf_reference", workflow):
        response = TestClient(app, headers={"X-GDPR-Consent": "test"}).post(
            "/api/v1/translate/pdf-reference",
            files={"file": ("form.pdf", b"%PDF-1.7 fixture", "application/pdf")},
            data={
                "source_language": "en",
                "target_language": "de",
                "expected_page_count": "1",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "SERVICE_UNAVAILABLE",
        "message": "PDF structure analysis is unavailable",
        "retryable": False,
    }


def test_pdf_reference_endpoint_rejects_non_pdf_before_workflow() -> None:
    workflow = AsyncMock()
    with patch("app.api.v1.endpoints.translate.translate_pdf_reference", workflow):
        response = TestClient(app, headers={"X-GDPR-Consent": "test"}).post(
            "/api/v1/translate/pdf-reference",
            files={"file": ("note.txt", b"not a PDF", "text/plain")},
            data={
                "source_language": "en",
                "target_language": "de",
                "expected_page_count": "1",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PDF"
    workflow.assert_not_awaited()
