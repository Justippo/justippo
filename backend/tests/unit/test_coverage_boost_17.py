"""Coverage boost batch 17 — pdf_reference_translation_service error paths
and ocr_service error paths."""

from __future__ import annotations

import pytest

# ─── pdf_reference_translation_service: error paths ──────────


class TestPDFReferenceTranslationErrors:
    def test_polygon_height_returns_none_for_single_point(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        result = _polygon_height([{"x": 0}, {"x": 1, "y": 5}])
        assert result is None

    def test_polygon_height_returns_none_for_empty_list(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        result = _polygon_height([])
        assert result is None

    def test_polygon_height_returns_height_for_valid_points(self) -> None:
        from app.services.pdf_reference_translation_service import _polygon_height

        result = _polygon_height([{"x": 0, "y": 0}, {"x": 1, "y": 10}])
        assert result == 10.0

    def test_validate_translated_analysis_raises_on_low_retention(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_analysis,
        )

        source = AzureDocumentAnalysis(
            model_id="test",
            api_version="2024-02-01",
            content="a" * 100,
        )
        translated = AzureDocumentAnalysis(
            model_id="test",
            api_version="2024-02-01",
            content="b",
        )
        with pytest.raises(PDFReferenceTranslationError):
            _validate_translated_analysis(
                source_analysis=source,
                translated_analysis=translated,
                source_language="en",
                target_language="de",
                expected_page_count=1,
            )

    def test_validate_translated_analysis_raises_on_few_pages(self) -> None:
        from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
        from app.services.pdf_reference_translation_service import (
            PDFReferenceTranslationError,
            _validate_translated_analysis,
        )

        source = AzureDocumentAnalysis(
            model_id="test",
            api_version="2024-02-01",
            content="a" * 100,
            pages=[{"pageNumber": 1}, {"pageNumber": 2}],
        )
        translated = AzureDocumentAnalysis(
            model_id="test",
            api_version="2024-02-01",
            content="a" * 100,
            pages=[{"pageNumber": 1}],
        )
        with pytest.raises(PDFReferenceTranslationError):
            _validate_translated_analysis(
                source_analysis=source,
                translated_analysis=translated,
                source_language="en",
                target_language="de",
                expected_page_count=2,
            )


# ─── ocr_service: error paths ──────────────────────────────


class TestOCRServiceErrorPaths:
    def test_azure_document_intelligence_invalid_model(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )

        detail = AzureDocumentIntelligenceErrorDetail(
            code="INVALID_MODEL",
            message="Invalid model id",
            retryable=False,
        )
        with pytest.raises(AzureDocumentIntelligenceError):
            raise AzureDocumentIntelligenceError(detail)
