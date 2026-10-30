# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Integration test — verify PII redaction integrates with TranslationService.

Verifies:
- When PII_REDACTION_ENABLED=true, redacted text reaches _translate_section_content
- When PII_REDACTION_ENABLED=false, raw text reaches _translate_section_content
- Redaction metadata is populated on the TranslationJob
- Fallback: when sidecar fails, raw text reaches the backend (graceful degradation)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.translation_service import TranslationService


@pytest.fixture
def sample_pages() -> list[dict[str, object]]:
    """OCR page with PII (name, email)."""
    return [
        {
            "page": 1,
            "text": "John Smith signed the contract. Contact: john@example.com",
        }
    ]


class TestRedactionIntegrationEnabled:
    """When PII_REDACTION_ENABLED=true, redacted text reaches the translation backend."""

    @pytest.mark.asyncio
    async def test_redacted_text_reaches_backend(self, sample_pages: list) -> None:
        """When redaction is enabled, the translation backend receives redacted text."""
        svc = TranslationService()

        received_texts: list[str] = []

        async def mock_translate_section(self, text, source_lang, target_lang):
            received_texts.append(text)
            return f"translated: {text}"

        from app.integrations.pii_redaction_adapter import PIIRedactionResult

        mock_result = PIIRedactionResult(
            redacted_text="[PERSON] signed the contract. Contact: [EMAIL_ADDRESS]",
            entity_count=2,
            entity_types=["PERSON", "EMAIL_ADDRESS"],
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_ENABLED": "true",
                    "PII_REDACTION_BASE_URL": "http://pii-redactor:8760",
                    "NOT_DIAMOND_ENABLED": "false",
                },
            ),
            patch(
                "app.services.translation_service.TranslationService._translate_section_content",
                mock_translate_section,
            ),
            patch(
                "app.services.translation_service.redact_with_fallback",
                new_callable=AsyncMock,
            ) as mock_redact,
        ):
            mock_redact.return_value = (
                "[PERSON] signed the contract. Contact: [EMAIL_ADDRESS]",
                True,
                mock_result,
            )

            job = await svc.translate(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                source_language="en",
                target_language="de",
                pages=sample_pages,
            )

        assert len(received_texts) > 0
        assert "John Smith" not in received_texts[0]
        assert "john@example.com" not in received_texts[0]
        assert "[PERSON]" in received_texts[0]
        assert "[EMAIL_ADDRESS]" in received_texts[0]

        assert job.redaction_metadata is not None
        assert job.redaction_metadata["enabled"] is True
        assert job.redaction_metadata["total_entities"] == 2
        assert "PERSON" in job.redaction_metadata["entity_types"]
        assert "EMAIL_ADDRESS" in job.redaction_metadata["entity_types"]
        assert job.redaction_metadata["succeeded"] is True


class TestRedactionIntegrationDisabled:
    """When PII_REDACTION_ENABLED=false, raw text reaches the translation backend."""

    @pytest.mark.asyncio
    async def test_raw_text_reaches_backend(self, sample_pages: list) -> None:
        """When redaction is disabled, the backend receives raw text with PII."""
        svc = TranslationService()

        received_texts: list[str] = []

        async def mock_translate_section(self, text, source_lang, target_lang):
            received_texts.append(text)
            return f"translated: {text}"

        with (
            patch.dict(
                "os.environ",
                {"PII_REDACTION_ENABLED": "false", "NOT_DIAMOND_ENABLED": "false"},
            ),
            patch(
                "app.services.translation_service.TranslationService._translate_section_content",
                mock_translate_section,
            ),
        ):
            job = await svc.translate(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                source_language="en",
                target_language="de",
                pages=sample_pages,
            )

        assert len(received_texts) > 0
        assert "John Smith" in received_texts[0]
        assert "john@example.com" in received_texts[0]

        assert job.redaction_metadata is not None
        assert job.redaction_metadata["enabled"] is False


class TestRedactionIntegrationFallback:
    """When sidecar fails, raw text reaches the backend (graceful degradation)."""

    @pytest.mark.asyncio
    async def test_fallback_on_sidecar_failure(self, sample_pages: list) -> None:
        """When sidecar is unavailable, translation proceeds with raw text."""
        svc = TranslationService()

        received_texts: list[str] = []

        async def mock_translate_section(self, text, source_lang, target_lang):
            received_texts.append(text)
            return f"translated: {text}"

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_ENABLED": "true",
                    "PII_REDACTION_BASE_URL": "http://pii-redactor:8760",
                    "NOT_DIAMOND_ENABLED": "false",
                },
            ),
            patch(
                "app.services.translation_service.TranslationService._translate_section_content",
                mock_translate_section,
            ),
            patch(
                "app.services.translation_service.redact_with_fallback",
                new_callable=AsyncMock,
            ) as mock_redact,
        ):
            # Simulate sidecar failure — redact_with_fallback returns raw text
            mock_redact.return_value = (sample_pages[0]["text"], False, None)

            job = await svc.translate(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                source_language="en",
                target_language="de",
                pages=sample_pages,
            )

        assert len(received_texts) > 0
        assert "John Smith" in received_texts[0]

        assert job.redaction_metadata is not None
        assert job.redaction_metadata["enabled"] is True
        assert job.redaction_metadata["succeeded"] is False
        assert job.redaction_metadata["total_entities"] == 0
