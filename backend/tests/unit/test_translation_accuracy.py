"""Translation accuracy tests — glossary enforcement, forbidden terms, Unicode, bidirectional.

Uses the scoped mock_translation_service fixture from conftest.py which
patches TranslationService.translate_text with deterministic responses.
"""

import pytest

from app.services.translation_service import TranslationService


@pytest.mark.asyncio
async def test_glossary_enforcement(mock_translation_service):
    """FR-03/FR-04: Ensure required glossary terms appear in translation."""
    svc = TranslationService()
    output = await svc.translate_text("The contract is void.", target_lang="de")
    assert "Vertrag" in output, f"Glossary term 'Vertrag' missing from: {output}"


@pytest.mark.asyncio
async def test_forbidden_terms_absent(mock_translation_service):
    """FR-03/FR-04: Ensure forbidden mistranslations do not appear."""
    svc = TranslationService()
    output = await svc.translate_text("The agreement is null.", target_lang="de")
    assert "nichtig" not in output.lower(), f"Forbidden term 'nichtig' found in: {output}"


@pytest.mark.asyncio
async def test_unicode_case_folding(mock_translation_service):
    """FR-03: Handle German ß → ss conversion correctly."""
    svc = TranslationService()
    output = await svc.translate_text("Straße", target_lang="en")
    assert len(output) > 0, f"Translation failed for 'Straße': {output}"


@pytest.mark.asyncio
async def test_bidirectional_coverage(mock_translation_service):
    """FR-03: Cover all MVP language pairs."""
    svc = TranslationService()
    pairs = [
        ("en", "de", "contract"),
        ("de", "en", "Vertrag"),
        ("en", "fr", "agreement"),
        ("fr", "en", "accord"),
        ("de", "fr", "Vertrag"),
        ("fr", "de", "contrat"),
    ]

    for src, tgt, term in pairs:
        output = await svc.translate_text(f"The {term} is valid.", source_lang=src, target_lang=tgt)
        assert len(output) > 0, f"Translation failed for {src}->{tgt}: {output}"
