"""
Unit tests for GlossaryService — BAML integration layer (ADR-010).

Covers:
- Language validation (en/de/fr only — reject others)
- Empty/whitespace text returns empty list
- Text truncation at 8000 chars
- Successful term extraction with mocked BAML client
- RuntimeError raised when BAML call fails
- Gateway URL routing through baml_setup (REM-8)

All BAML calls are mocked — no real LLM calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.glossary_service import extract_terms, insert_terms

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_glossary_term(
    term_en="residence permit",
    term_de="Aufenthaltstitel",
    term_fr="titre de séjour",
    definition="A legal authorization...",
) -> MagicMock:
    return MagicMock(term_en=term_en, term_de=term_de, term_fr=term_fr, definition=definition)


def _mock_baml_client(terms: list[MagicMock] | None = None) -> MagicMock:
    """Return a mock baml_client sync client with ExtractGlossaryTerms."""
    mock_b = MagicMock()
    mock_b.ExtractGlossaryTerms.return_value = terms or []
    return mock_b


# ── Language validation ──────────────────────────────────────────────────────


class TestLanguageValidation:
    def test_accepts_en(self) -> None:
        with patch(
            "app.services.glossary_service._get_baml_client", return_value=_mock_baml_client([])
        ):
            result = extract_terms("Some English legal text about residence permits", "en")
            assert result == []

    def test_accepts_de(self) -> None:
        with patch(
            "app.services.glossary_service._get_baml_client", return_value=_mock_baml_client([])
        ):
            result = extract_terms("Ein deutscher Gesetzestext über Aufenthaltstitel", "de")
            assert result == []

    def test_accepts_fr(self) -> None:
        with patch(
            "app.services.glossary_service._get_baml_client", return_value=_mock_baml_client([])
        ):
            result = extract_terms("Un texte juridique français sur les titres de séjour", "fr")
            assert result == []

    def test_rejects_es(self) -> None:
        with pytest.raises(ValueError, match="Unsupported language"):
            extract_terms("Texto legal español", "es")

    def test_rejects_uppercase_de(self) -> None:
        # Uppercase DE should be normalized and accepted
        with patch(
            "app.services.glossary_service._get_baml_client", return_value=_mock_baml_client([])
        ):
            result = extract_terms("Ein Gesetzestext", "DE")
            assert result == []

    def test_rejects_empty_lang(self) -> None:
        with pytest.raises(ValueError, match="Unsupported language"):
            extract_terms("Some text", "")

    def test_none_text_returns_empty(self) -> None:
        """None text should be treated as empty string (graceful degradation)."""
        with patch(
            "app.services.glossary_service._get_baml_client", return_value=_mock_baml_client([])
        ):
            result = extract_terms(None, "en")
            assert result == []

    def test_none_lang_raises_value_error(self) -> None:
        """None source_lang should raise ValueError immediately."""
        with pytest.raises(ValueError, match="source_lang must not be None"):
            extract_terms("Some text", None)


# ── Text handling ────────────────────────────────────────────────────────────


class TestTextHandling:
    def test_empty_text_returns_empty_list(self) -> None:
        # Should NOT call BAML for empty text
        mock_b = _mock_baml_client()
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("", "en")
            assert result == []
            mock_b.ExtractGlossaryTerms.assert_not_called()

    def test_whitespace_text_returns_empty_list(self) -> None:
        mock_b = _mock_baml_client()
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("   \n  \t  ", "en")
            assert result == []
            mock_b.ExtractGlossaryTerms.assert_not_called()

    def test_text_truncated_at_8000_chars(self) -> None:
        long_text = "legal term " * 1000  # ~12000 chars
        mock_b = _mock_baml_client([])
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            extract_terms(long_text, "en")
            called_text = mock_b.ExtractGlossaryTerms.call_args[0][0]
            assert len(called_text) <= 8000


# ── Successful extraction ────────────────────────────────────────────────────


class TestSuccessfulExtraction:
    def test_returns_terms_from_baml(self) -> None:
        term = _make_glossary_term()
        mock_b = _mock_baml_client([term])
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("Applicants must hold a valid residence permit.", "en")
            assert len(result) == 1
            assert result[0].term_en == "residence permit"
            assert result[0].term_de == "Aufenthaltstitel"
            mock_b.ExtractGlossaryTerms.assert_called_once_with(
                "Applicants must hold a valid residence permit.", "en"
            )

    def test_returns_multiple_terms(self) -> None:
        terms = [_make_glossary_term(), _make_glossary_term(term_en="notarial deed")]
        mock_b = _mock_baml_client(terms)
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("Residence permit and notarial deed required.", "en")
            assert len(result) == 2

    def test_returns_empty_list_when_no_terms_found(self) -> None:
        mock_b = _mock_baml_client([])
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("No special terms here", "en")
            assert result == []


class TestPersistence:
    @pytest.mark.asyncio
    async def test_insert_terms_persists_via_repository(self) -> None:
        mock_repo = MagicMock()
        mock_repo.upsert_terms = AsyncMock(return_value=[{"id": "seed-1"}])

        with patch("app.repositories.glossary_repo.GlossaryRepo", return_value=mock_repo):
            result = await insert_terms(
                [
                    _make_glossary_term(),
                ],
                doc_id="doc-1",
                source_lang="en",
                db=object(),
            )

        assert result == [{"id": "seed-1"}]
        mock_repo.upsert_terms.assert_awaited_once()


# ── Error handling ───────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_raises_runtime_error_on_baml_failure(self) -> None:
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = ConnectionError("Gateway unreachable")
        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(RuntimeError, match="Glossary extraction failed"),
        ):
            extract_terms("Some text", "en")

    def test_raises_runtime_error_on_parse_failure(self) -> None:
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = ValueError("Invalid JSON in response")
        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(RuntimeError, match="Glossary extraction failed"),
        ):
            extract_terms("Some text", "de")


# ── Gateway routing (REM-8 compliance) ───────────────────────────────────────


class TestGatewayRouting:
    def test_baml_setup_uses_gateway_url(self) -> None:
        """Verify baml_setup.configure() sets BAML_GLOSSARY_BASE_URL to CF Gateway compat endpoint."""
        import os

        from app.integrations.baml_setup import configure

        # Remove env var to force re-injection
        os.environ.pop("BAML_GLOSSARY_BASE_URL", None)
        os.environ.pop("BAML_GLOSSARY_API_KEY", None)
        os.environ.pop("BAML_GLOSSARY_MODEL", None)

        with patch("app.integrations.baml_setup.settings") as mock_settings:
            mock_settings.CLOUDFLARE_ACCOUNT_ID = "acct-123"
            mock_settings.CLOUDFLARE_GATEWAY_ID = "gw-456"
            mock_settings.CLOUDFLARE_API_TOKEN = "test-token"
            configure()
            assert "BAML_GLOSSARY_BASE_URL" in os.environ
            base_url = os.environ["BAML_GLOSSARY_BASE_URL"]
            assert "gateway.ai.cloudflare.com" in base_url
            assert "acct-123" in base_url
            assert "gw-456" in base_url
            assert "/compat" in base_url
            assert os.environ["BAML_GLOSSARY_API_KEY"] == "test-token"
            assert os.environ["BAML_GLOSSARY_MODEL"].startswith("workers-ai/")

    def test_baml_setup_no_direct_llm_url(self) -> None:
        """Verify the gateway URL does NOT contain any direct provider base URL."""
        import os

        from app.integrations.baml_setup import configure

        os.environ.pop("BAML_GLOSSARY_BASE_URL", None)
        os.environ.pop("BAML_GLOSSARY_API_KEY", None)
        os.environ.pop("BAML_GLOSSARY_MODEL", None)

        with patch("app.integrations.baml_setup.settings") as mock_settings:
            mock_settings.CLOUDFLARE_ACCOUNT_ID = "acct-123"
            mock_settings.CLOUDFLARE_GATEWAY_ID = "gw-456"
            mock_settings.CLOUDFLARE_API_TOKEN = "token"
            configure()
            base_url = os.environ["BAML_GLOSSARY_BASE_URL"]
            # Must route through CF Gateway compat endpoint, not any direct provider
            assert "api.openai.com" not in base_url
            assert "api.mistral" not in base_url
            assert "api.groq.com" not in base_url
            assert "openrouter.ai" not in base_url
            assert "/compat" in base_url

    def test_baml_setup_idempotent(self) -> None:
        """Multiple calls to configure() should not change already-set values."""
        import os

        from app.integrations.baml_setup import configure

        os.environ["BAML_GLOSSARY_BASE_URL"] = "https://my-custom-gateway.example.com"
        first_url = os.environ["BAML_GLOSSARY_BASE_URL"]

        with patch("app.integrations.baml_setup.settings"):
            configure()

        assert os.environ["BAML_GLOSSARY_BASE_URL"] == first_url


class TestExtractTermsEdgeCases:
    def test_extract_terms_raises_runtime_error_if_baml_client_fails(self) -> None:
        """Tests that a BAML client failure during extract_terms raises a RuntimeError."""
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = Exception("API error")
        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(RuntimeError, match="Glossary extraction failed"),
        ):
            extract_terms("Valid text", "en")

    @pytest.mark.asyncio
    async def test_insert_terms_empty_returns_empty(self) -> None:
        result = await insert_terms([], doc_id="doc-1", source_lang="en", db=object())
        assert result == []

    @pytest.mark.asyncio
    async def test_insert_terms_handles_persistence_exception(self) -> None:
        """Tests that database exception is swallowed gracefully by insert_terms."""
        with patch("app.repositories.glossary_repo.GlossaryRepo") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.upsert_terms = AsyncMock(side_effect=Exception("DB connection failed"))
            mock_repo_class.return_value = mock_repo

            result = await insert_terms(
                [_make_glossary_term()], doc_id="doc-1", source_lang="en", db=object()
            )

            assert result == []
            mock_repo.upsert_terms.assert_awaited_once()


class TestCheckedUnwrapping:
    def test_maybe_unwrap_returns_value_for_checked(self) -> None:
        """Tests that _maybe_unwrap properly unwraps a Checked object."""
        mock_checked = MagicMock()
        with patch("app.services.glossary_service.isinstance", return_value=True):
            mock_checked.value = "unwrapped_string"
            from app.services.glossary_service import _maybe_unwrap

            assert _maybe_unwrap(mock_checked) == "unwrapped_string"

    def test_maybe_unwrap_returns_as_is_for_non_checked(self) -> None:
        """Tests that _maybe_unwrap returns the original value for non-Checked objects."""
        from app.services.glossary_service import _maybe_unwrap

        assert _maybe_unwrap("plain_string") == "plain_string"
        assert _maybe_unwrap(123) == 123
