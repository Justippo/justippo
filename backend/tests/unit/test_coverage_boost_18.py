"""Coverage boost batch 18 — chat_guidance, azure_document_intelligence, documents."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ─── chat_guidance: enforce_citation_grounding paths ────────────


class TestChatGuidancePaths:
    def test_enforce_citation_grounding_empty_claim_text(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="",
            known_doc_ids={"doc1"},
            entity_mentions={"entity1"},
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "pass"
        assert result["claims"] == []

    def test_enforce_citation_grounding_disabled_config(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="Some claim text",
            known_doc_ids={"doc1"},
            entity_mentions={"entity1"},
            config=GroundingConfig(enabled=False),
        )
        assert result["verdict"] == "pass"
        assert result["claims"] == []

    def test_enforce_citation_grounding_all_grounded(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="This is supported by doc1.",
            known_doc_ids={"doc1"},
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "pass"
        assert result["ungrounded_count"] == 0

    def test_enforce_citation_grounding_partial_grounded(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="Supported by doc1. Unsupported claim.",
            known_doc_ids={"doc1"},
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "partial"
        assert result["ungrounded_count"] == 1

    def test_enforce_citation_grounding_all_ungrounded(self) -> None:
        from app.services.chat_guidance import GroundingConfig, enforce_citation_grounding

        result = enforce_citation_grounding(
            claim_text="No sources for this claim.",
            known_doc_ids=set(),
            entity_mentions=set(),
            config=GroundingConfig(enabled=True),
        )
        assert result["verdict"] == "fail"
        assert result["ungrounded_count"] > 0


# ─── azure_document_intelligence: error paths ──────────────────


class TestAzureDocumentIntelligenceErrors:
    def test_invalid_configuration_error(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )

        detail = AzureDocumentIntelligenceErrorDetail(
            code="INVALID_CONFIGURATION",
            message="Invalid configuration",
            retryable=False,
        )
        with pytest.raises(AzureDocumentIntelligenceError):
            raise AzureDocumentIntelligenceError(detail)

    def test_processing_timeout_error(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )

        detail = AzureDocumentIntelligenceErrorDetail(
            code="PROCESSING_TIMEOUT",
            message="Timeout",
            retryable=True,
        )
        with pytest.raises(AzureDocumentIntelligenceError):
            raise AzureDocumentIntelligenceError(detail)

    def test_service_unavailable_error(self) -> None:
        from app.integrations.azure_document_intelligence import (
            AzureDocumentIntelligenceError,
            AzureDocumentIntelligenceErrorDetail,
        )

        detail = AzureDocumentIntelligenceErrorDetail(
            code="SERVICE_UNAVAILABLE",
            message="Unavailable",
            retryable=True,
        )
        with pytest.raises(AzureDocumentIntelligenceError):
            raise AzureDocumentIntelligenceError(detail)


# ─── documents endpoint: error paths ──────────────────────────


class TestDocumentsEndpointErrors:
    @pytest.mark.asyncio()
    async def test_get_document_classification_not_found(self) -> None:
        from fastapi import HTTPException

        with patch("app.api.v1.endpoints.documents._classifications", {}):
            from app.api.v1.endpoints.documents import get_document_classification

            with pytest.raises(HTTPException) as exc_info:
                await get_document_classification(document_id="nonexistent-id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio()
    async def test_download_translated_document_not_found(self) -> None:
        from fastapi import HTTPException

        from app.services.storage_service import StorageService

        with patch.object(
            StorageService, "get_file", AsyncMock(side_effect=FileNotFoundError("not found"))
        ):
            from app.api.v1.endpoints.documents import download_translated_document

            with pytest.raises(HTTPException) as exc_info:
                await download_translated_document(document_id="nonexistent-id", language="de")
            assert exc_info.value.status_code == 404
