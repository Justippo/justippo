"""
Unit tests for /api/v1/documents/ endpoint (Sprint 2)

Coverage:
- Unsupported MIME type → HTTP 422 with descriptive message
- PDF / DOCX / PNG accepted (happy path, mocked OCRService)
- Response shape: doc_id, status, ephemeral=True, page_count, pages[]
- Per-page fields: page, text, confidence
- doc_id is unique per upload (UUID)
- OCR exception → HTTP 500 with detail message
- GET /{document_id} → 501 (Sprint 3 stub)
- GET /{document_id}/download → 501 (Sprint 3 stub)

All OCR calls are mocked — no real Mistral or Tesseract calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.document_explanation import DocumentExplanation
from app.services.ocr_service import OCRPage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}


@pytest.fixture(autouse=True)
def mock_classification() -> object:
    from app.services.classification_service import DocumentClassification

    classification = DocumentClassification(document_type="unknown", language_code="en")
    with patch("app.api.v1.endpoints.documents.classify_document", new_callable=AsyncMock) as mock:
        mock.return_value = classification
        yield mock


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app, headers=GDPR_HEADERS)


def _ocr_pages(*texts: str) -> list[OCRPage]:
    """Build a list of OCRPage dicts for mocking OCRService.process."""
    return [
        OCRPage(page=i + 1, text=text, confidence=round(0.95 - i * 0.01, 2))
        for i, text in enumerate(texts)
    ]


# ---------------------------------------------------------------------------
# Content-type validation
# ---------------------------------------------------------------------------


class TestContentTypeValidation:
    def test_unsupported_type_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/documents/",
            data={"target_lang": "de"},
            files={"file": ("doc.txt", b"plain text content", "text/plain")},
        )
        assert response.status_code == 422
        assert "text/plain" in response.json()["detail"]

    def test_html_type_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/documents/",
            data={"target_lang": "en"},
            files={"file": ("page.html", b"<html/>", "text/html")},
        )
        assert response.status_code == 422

    def test_pdf_accepted(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("PDF text")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF-1.4 content", "application/pdf")},
            )
        assert response.status_code == 200

    def test_invalid_pdf_signature_returns_typed_422(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"not actually a PDF", "application/pdf")},
            )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "INVALID_PDF"
        mock_ocr.assert_not_awaited()

    def test_docx_accepted(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("DOCX content")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "fr"},
                files={
                    "file": (
                        "doc.docx",
                        b"PK\x03\x04",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
        assert response.status_code == 200

    def test_png_accepted(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("Image text")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "en"},
                files={"file": ("scan.png", b"\x89PNG\r\n", "image/png")},
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestUploadResponseShape:
    def test_response_has_required_fields(self, client: TestClient) -> None:
        explanation = DocumentExplanation(
            document_type="unknown",
            language="de",
            requirements=[],
            legal_context_status="unavailable",
            citations=[],
            warnings=["LEGAL_RETRIEVAL_UNAVAILABLE"],
        )
        with (
            patch(
                "app.api.v1.endpoints.documents._ocr.process",
                new_callable=AsyncMock,
            ) as mock_ocr,
            patch(
                "app.api.v1.endpoints.documents.explain_document",
                new_callable=AsyncMock,
                return_value=explanation,
            ),
        ):
            mock_ocr.return_value = _ocr_pages("Hello world")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )
        data = response.json()
        assert "doc_id" in data
        assert data["status"] == "processed"
        assert data["ephemeral"] is True
        assert data["page_count"] == 1
        assert len(data["pages"]) == 1
        assert data["pdf_processing"] == {
            "route": "document_understanding_translation",
            "output_mode": "extracted_text",
            "layout_preserved": False,
            "original_unchanged": True,
            "form_filling_supported": False,
            "is_fillable_form": False,
        }
        assert data["document_explanation"]["legal_context_status"] == "unavailable"
        assert data["target_language"] == "de"

    def test_source_language_is_not_reused_as_target(self, client: TestClient) -> None:
        explanation = DocumentExplanation(
            document_type="unknown",
            language="de",
            requirements=[],
            legal_context_status="unavailable",
            citations=[],
            warnings=[],
        )
        with (
            patch(
                "app.api.v1.endpoints.documents._ocr.process",
                new_callable=AsyncMock,
                return_value=_ocr_pages("English text"),
            ),
            patch(
                "app.api.v1.endpoints.documents.explain_document",
                new_callable=AsyncMock,
                return_value=explanation,
            ) as mock_explain,
        ):
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "en"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )

        assert response.status_code == 200
        assert response.json()["target_language"] == "de"
        assert mock_explain.await_args.kwargs["language"] == "de"

    def test_babeldoc_ready_routes_pdf_to_layout_reference(self, client: TestClient) -> None:
        with (
            patch(
                "app.api.v1.endpoints.documents._ocr.process",
                new_callable=AsyncMock,
            ) as mock_ocr,
            patch(
                "app.api.v1.endpoints.documents.is_babeldoc_ready",
                return_value=True,
            ),
        ):
            mock_ocr.return_value = _ocr_pages("Hello world")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )

        assert response.status_code == 200
        assert response.json()["pdf_processing"] == {
            "route": "pdf_reference_translation",
            "output_mode": "reference",
            "layout_preserved": True,
            "original_unchanged": True,
            "form_filling_supported": False,
            "is_fillable_form": False,
        }
        assert response.json()["document_explanation"] is None

    def test_non_pdf_has_no_pdf_processing_profile(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("Image text")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "fr"},
                files={"file": ("scan.png", b"\x89PNG", "image/png")},
            )

        assert response.status_code == 200
        assert response.json()["pdf_processing"] is None

    def test_multi_page_response(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("Page one text", "Page two text")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "fr"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )
        data = response.json()
        assert data["page_count"] == 2
        assert len(data["pages"]) == 2

    def test_page_fields_present(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("Page one text", "Page two text")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "fr"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )
        page = response.json()["pages"][0]
        assert page["page"] == 1
        assert page["text"] == "Page one text"
        assert "confidence" in page

    def test_doc_id_is_unique_per_request(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = _ocr_pages("text")
            r1 = client.post(
                "/api/v1/documents/",
                data={"target_lang": "en"},
                files={"file": ("a.pdf", b"%PDF", "application/pdf")},
            )
            r2 = client.post(
                "/api/v1/documents/",
                data={"target_lang": "en"},
                files={"file": ("b.pdf", b"%PDF", "application/pdf")},
            )
        assert r1.json()["doc_id"] != r2.json()["doc_id"]

    def test_confidence_none_preserved(self, client: TestClient) -> None:
        """Tesseract fallback pages have confidence=None — must pass through unchanged."""
        pages = [OCRPage(page=1, text="Tesseract result", confidence=None)]
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.return_value = pages
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "en"},
                files={"file": ("scan.png", b"\x89PNG", "image/png")},
            )
        assert response.json()["pages"][0]["confidence"] is None


# ---------------------------------------------------------------------------
# OCR failure → HTTP 500
# ---------------------------------------------------------------------------


class TestUploadOCRFailure:
    def test_ocr_exception_returns_500(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.side_effect = RuntimeError("Mistral unreachable")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF content", "application/pdf")},
            )
        assert response.status_code == 500
        assert "OCR extraction failed" in response.json()["detail"]

    def test_ocr_rate_limited_returns_503_with_retry_after(self, client: TestClient) -> None:
        from app.services.ocr_service import MistralOCRError

        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.side_effect = MistralOCRError(429, "Rate limit exceeded", retry_after=7.2)
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF content", "application/pdf")},
            )
        assert response.status_code == 503
        assert response.headers["retry-after"] == "8"
        body = response.json()["detail"]
        assert body["code"] == "ocr_rate_limited"
        assert "Rate limit" not in body["message"]  # upstream body is not leaked

    def test_ocr_tier_limit_returns_413(self, client: TestClient) -> None:
        from app.services.ocr_service import OCRTierLimitError

        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.side_effect = OCRTierLimitError("5 pages exceeds the F0 limit of 2 pages")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF content", "application/pdf")},
            )
        assert response.status_code == 413
        detail = response.json()["detail"]
        assert detail["code"] == "ocr_tier_limit_exceeded"
        assert detail["message"] == "Document exceeds current OCR tier limits."
        assert "F0" not in str(detail)  # provider tier details are not leaked

    def test_ocr_non_rate_limit_mistral_error_stays_500(self, client: TestClient) -> None:
        from app.services.ocr_service import MistralOCRError

        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.side_effect = MistralOCRError(401, "Unauthorized")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF content", "application/pdf")},
            )
        assert response.status_code == 500

    def test_ocr_exception_detail_includes_cause(self, client: TestClient) -> None:
        with patch(
            "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
        ) as mock_ocr:
            mock_ocr.side_effect = ValueError("unsupported PDF version")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )
        assert "unsupported PDF version" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GDPR NFR-04: No file content persisted to disk (ephemeral processing)
# ---------------------------------------------------------------------------


class TestGDPREphemeralProcessing:
    """Verify that document upload never writes file content to disk (NFR-04)."""

    def test_no_disk_writes_during_upload(self, client: TestClient) -> None:
        """Assert the upload handler never persists bytes via open(), os.open(), or tempfile.

        NFR-04 requires that no user-uploaded content is written to disk. This test
        instruments all three common disk-write vectors and asserts none fire in a
        write/create mode during an upload request.
        """
        import builtins
        import os

        original_open = builtins.open
        original_os_open = os.open
        disk_writes: list[str] = []

        def patched_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if any(m in str(mode) for m in ("w", "a", "x", "+")):
                disk_writes.append(f"builtins.open:{file}:{mode}")
            return original_open(file, mode, *args, **kwargs)

        def patched_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> Any:
            # O_WRONLY=1, O_RDWR=2, O_CREAT=0o100, O_APPEND=0o2000 — any write intent
            write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND
            if flags & write_flags:
                disk_writes.append(f"os.open:{path}:flags={flags}")
            return original_os_open(path, flags, *args, **kwargs)

        def patched_mkstemp(*args: Any, **kwargs: Any) -> Any:
            disk_writes.append("tempfile.mkstemp")
            raise AssertionError("tempfile.mkstemp called — NFR-04 violation")

        def patched_named_tmp(*args: Any, **kwargs: Any) -> Any:
            disk_writes.append("tempfile.NamedTemporaryFile")
            raise AssertionError("tempfile.NamedTemporaryFile called — NFR-04 violation")

        with (
            patch(
                "app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock
            ) as mock_ocr,
            patch("builtins.open", side_effect=patched_open),
            patch("os.open", side_effect=patched_os_open),
            patch("tempfile.mkstemp", side_effect=patched_mkstemp),
            patch("tempfile.NamedTemporaryFile", side_effect=patched_named_tmp),
        ):
            mock_ocr.return_value = _ocr_pages("Test content")
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("secret.pdf", b"%PDF-sensitive-content", "application/pdf")},
            )

        # Upload must still succeed (sanity — we didn't break the happy path)
        assert response.status_code == 200, response.text
        # NFR-04: No file content shall be persisted server-side via any vector
        assert disk_writes == [], f"NFR-04 violation: upload handler wrote to disk: {disk_writes}"


# ---------------------------------------------------------------------------
# Sprint 3 stub endpoints → 501
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_get_document_returns_404(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.documents.D1Client.from_scope") as mock_db_cls:
            mock_db = AsyncMock()
            mock_db.fetch_one.return_value = None
            mock_db_cls.return_value = mock_db

            response = client.get("/api/v1/documents/nonexistent")
            assert response.status_code == 404

    def test_get_document_success(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.documents.D1Client.from_scope") as mock_db_cls:
            mock_db = AsyncMock()
            mock_db.fetch_one.return_value = {
                "id": "doc123",
                "filename": "test.pdf",
                "status": "processed",
                "detected_language": "en",
                "page_count": 5,
                "created_at": "2023-10-27T10:00:00Z",
            }
            mock_db.fetch_all.return_value = [
                {"target_language": "de", "status": "completed"},
                {"target_language": "fr", "status": "queued"},
            ]
            mock_db_cls.return_value = mock_db

            response = client.get("/api/v1/documents/doc123")
            assert response.status_code == 200
            data = response.json()
            assert data["document_id"] == "doc123"
            assert len(data["translations"]) == 2
            assert data["translations"][0]["language"] == "de"
            assert (
                data["translations"][0]["download_url"]
                == "/api/v1/documents/doc123/download?language=de"
            )
            assert data["translations"][1]["language"] == "fr"
            assert data["translations"][1]["download_url"] == ""

    def test_get_document_db_unavailable(self, client: TestClient) -> None:
        with patch("app.api.v1.endpoints.documents.D1Client.from_scope") as mock_db_cls:
            mock_db_cls.return_value = None

            response = client.get("/api/v1/documents/doc123")
            assert response.status_code == 503

    def test_download_document_returns_200(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def mock_get_file(self, object_key: str) -> bytes:
            return b"%PDF-1.4 mock pdf bytes"

        monkeypatch.setattr("app.services.storage_service.StorageService.get_file", mock_get_file)
        response = client.get("/api/v1/documents/some-doc-id/download?language=fr")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == b"%PDF-1.4 mock pdf bytes"


# ── Classification-failure + 404 edge cases (Issue #251) ───────────────────


class TestDocumentEdgeCases:
    def test_classification_failure_falls_back_to_default(self, client: TestClient) -> None:
        """classify_document raising → default_classification used, upload still 200."""
        with (
            patch(
                "app.api.v1.endpoints.documents._ocr.process",
                new_callable=AsyncMock,
                return_value=_ocr_pages("PDF text"),
            ),
            patch(
                "app.api.v1.endpoints.documents.classify_document",
                new_callable=AsyncMock,
                side_effect=RuntimeError("classifier down"),
            ),
        ):
            response = client.post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF-1.4 content", "application/pdf")},
            )
        assert response.status_code == 200
        # The default classification is served (document_type "unknown").
        assert response.json()["classification"]["document_type"] == "unknown"

    def test_get_classification_missing_id_returns_404(self, client: TestClient) -> None:
        """GET /{document_id}/classification with unknown id → 404 (arc 380)."""
        response = client.get("/api/v1/documents/does-not-exist/classification")
        assert response.status_code == 404
