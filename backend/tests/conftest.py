"""Shared pytest fixtures for backend tests.

NOTE: Do NOT inject mocks into sys.modules at module level — this breaks
all other tests that import the real translation service. Use per-test
fixtures with monkeypatch instead.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_translation_service(monkeypatch):
    """Scoped mock for TranslationService.translate_text — only active within a single test.

    Patches the async translate_text method on TranslationService so that
    tests can instantiate the service and call ``await svc.translate_text(...)``
    without hitting the real Cloudflare AI Gateway.
    """
    responses = {
        ("The contract is void.", "de"): "Der Vertrag ist nichtig.",
        ("The agreement is null.", "de"): "Die Vereinbarung ist ungültig.",
        ("Straße", "en"): "Street",
        ("The contract is valid.", "de"): "Der Vertrag ist gültig.",
        ("The Vertrag is valid.", "en"): "The contract is valid.",
        ("The agreement is valid.", "fr"): "L'accord est valide.",
        ("L'accord est valide.", "en"): "The agreement is valid.",
        ("Der Vertrag ist gültig.", "fr"): "Le contrat est valide.",
        ("Le contrat est valide.", "de"): "Der Vertrag ist gültig.",
    }

    async def fake_translate(self, text, target_lang="de", source_lang="en"):
        key = (text, target_lang)
        if key in responses:
            return responses[key]
        return f"[Translated {source_lang}->{target_lang}] {text}"

    monkeypatch.setattr(
        "app.services.translation_service.TranslationService.translate_text",
        fake_translate,
    )
    return MagicMock()
