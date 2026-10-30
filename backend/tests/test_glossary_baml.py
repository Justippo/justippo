"""
Tests for BAML Runtime Hardening — validation, unwrapping, fallback, threading.

Covers items from the BAML wiring hardening task:
- @check / @assert validation behavior (BamlValidationError handling)
- Checked<T> unwrapping in extract_terms()
- Thread-safe singleton (_get_baml_client with Lock)
- Fallback client env injection (_inject_env covers both primary and fallback)
- Edge cases: empty input, truncation, malformed responses

All BAML calls are mocked — no real LLM calls are made.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.services.glossary_service import (
    _maybe_unwrap,
    _unwrap_checked_terms,
    extract_terms,
)
from baml_client.types import Check, Checked, GlossaryTerm

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_check(name: str = "term_en_nonempty", status: str = "succeeded") -> Check:
    """Create a baml_client.types.Check instance (not a MagicMock)."""
    return Check(name=name, expression="{{ this|length > 0 }}", status=status)


def _make_checked_term(
    value: str = "residence permit",
    check_status: str = "succeeded",
) -> Checked:
    """Create a Checked[str, Literal['term_en_nonempty']] simulating BAML @check output."""
    checks: dict[str, Check] = {"term_en_nonempty": _make_check("term_en_nonempty", check_status)}
    return Checked[str, str](value=value, checks=checks)


def _make_raw_glossary_term(
    term_en: str = "residence permit",
    term_de: str = "Aufenthaltstitel",
    term_fr: str = "titre de séjour",
    definition: str = "A legal authorization to reside in a country for a specified period.",
) -> GlossaryTerm:
    """Create a real Pydantic GlossaryTerm with a Checked term_en field."""
    return GlossaryTerm(
        term_en=_make_checked_term(term_en),
        term_de=term_de,
        term_fr=term_fr,
        definition=definition,
    )


def _mock_baml_client(terms: list | None = None) -> MagicMock:
    mock_b = MagicMock()
    mock_b.ExtractGlossaryTerms.return_value = terms or []
    return mock_b


# ── Checked<T> Unwrapping ────────────────────────────────────────────────────


class TestCheckedUnwrapping:
    def test_maybe_unwrap_plain_string(self) -> None:
        result = _maybe_unwrap("residence permit")
        assert result == "residence permit"
        assert isinstance(result, str)

    def test_maybe_unwrap_checked_string(self) -> None:
        checked = _make_checked_term("Aufenthaltstitel")
        result = _maybe_unwrap(checked)
        assert result == "Aufenthaltstitel"
        assert isinstance(result, str)

    def test_maybe_unwrap_empty_checked_string(self) -> None:
        checked = _make_checked_term("")
        result = _maybe_unwrap(checked)
        assert result == ""

    def test_unwrap_checked_terms_in_place_mutation(self) -> None:
        """_unwrap_checked_terms mutates the original GlossaryTerm objects."""
        raw = _make_raw_glossary_term()
        # Before unwrapping: term_en is Checked[str]
        assert isinstance(raw.term_en, Checked)
        assert raw.term_en.value == "residence permit"

        result = _unwrap_checked_terms([raw])
        assert len(result) == 1
        # After unwrapping: term_en is plain str
        assert result[0].term_en == "residence permit"
        assert result[0].term_de == "Aufenthaltstitel"
        assert result[0].term_fr == "titre de séjour"
        assert (
            result[0].definition
            == "A legal authorization to reside in a country for a specified period."
        )
        # Same object reference
        assert result[0] is raw

    def test_unwrap_empty_list(self) -> None:
        assert _unwrap_checked_terms([]) == []

    def test_unwrap_mock_terms_handles_checked_field(self) -> None:
        """Term with Checked term_en gets unwrapped correctly via extract_terms."""
        term = _make_raw_glossary_term()
        mock_b = _mock_baml_client([term])
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("Applicants must hold a valid residence permit.", "en")
            assert len(result) == 1
            assert result[0].term_en == "residence permit"
            assert result[0].term_de == "Aufenthaltstitel"


# ── BAML Validation Error Handling ───────────────────────────────────────────


class TestBamlValidationHandling:
    def test_extract_terms_handles_baml_validation_error(self) -> None:
        """BAML validation failures (from @assert) are caught and re-raised as RuntimeError.

        BamlValidationError is documented at baml_py.BamlValidationError but may not be
        exported from the installed baml_py.abi3.so. We simulate the exception to verify
        the generic Exception → RuntimeError wrapping in the service layer.
        """
        # Simulate whatever exception BAML's runtime raises on @assert failure.
        # The extract_terms() catch-all wraps any Exception → RuntimeError.
        baml_val_error = RuntimeError(
            "BamlValidationError: definition_length: definition must be 10-500 chars"
        )
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = baml_val_error
        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(RuntimeError, match="Glossary extraction failed"),
        ):
            extract_terms("Some legal text about residence permits.", "en")

    def test_extract_terms_handles_parse_error_as_runtime(self) -> None:
        """Any exception during BAML call becomes RuntimeError."""
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = RuntimeError("JSON parse failure")
        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(RuntimeError, match="Glossary extraction failed"),
        ):
            extract_terms("Text that causes a parse error.", "en")

    def test_extract_terms_wraps_baml_native_panic(self) -> None:
        """BAML's catchable PyO3 panic degrades through the normal fallback."""
        panic_type = type("PanicException", (BaseException,), {"__module__": "pyo3_runtime"})
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = panic_type("Attempted to create a NULL object")

        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(RuntimeError, match="Glossary extraction failed"),
        ):
            extract_terms("Text that triggers the native runtime.", "en")

    def test_extract_terms_does_not_swallow_process_control_exceptions(self) -> None:
        """The native-panic guard must not catch unrelated BaseException types."""
        mock_b = MagicMock()
        mock_b.ExtractGlossaryTerms.side_effect = KeyboardInterrupt()

        with (
            patch("app.services.glossary_service._get_baml_client", return_value=mock_b),
            pytest.raises(KeyboardInterrupt),
        ):
            extract_terms("Text interrupted by the process.", "en")

    def test_extract_terms_empty_input_no_baml_call(self) -> None:
        """Empty text should short-circuit — no BAML call, no validation risk."""
        mock_b = _mock_baml_client()
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms("", "en")
            assert result == []
            mock_b.ExtractGlossaryTerms.assert_not_called()

    def test_extract_terms_truncation_preserves_validation(self) -> None:
        """Truncated text still goes through BAML validation pipeline."""
        long_text = "A. " * 5000  # ~15000 chars
        term = _make_raw_glossary_term()
        mock_b = _mock_baml_client([term])
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_b):
            result = extract_terms(long_text, "en")
            called_text = mock_b.ExtractGlossaryTerms.call_args[0][0]
            assert len(called_text) <= 8000
            assert len(result) == 1
            # term_en should be unwrapped to plain string
            assert result[0].term_en == "residence permit"


# ── Thread-Safe Singleton ───────────────────────────────────────────────────


class TestThreadSafeSingleton:
    def test_get_baml_client_returns_same_instance(self) -> None:
        """Calling _get_baml_client() twice returns the same cached instance."""
        # Reset the singleton for test isolation
        import app.services.glossary_service as gs
        from app.services.glossary_service import _get_baml_client

        gs._b = None

        mock_client = MagicMock()
        with patch(
            "app.services.glossary_service._create_client", return_value=mock_client
        ) as mock_factory:
            client1 = _get_baml_client()
            client2 = _get_baml_client()
            assert client1 is client2
            mock_factory.assert_called_once()

    def test_get_baml_client_thread_safety(self) -> None:
        """Multiple threads racing on first access all get the same client."""
        import app.services.glossary_service as gs

        gs._b = None

        call_count = 0
        lock = threading.Lock()

        def counting_factory():
            nonlocal call_count
            with lock:
                call_count += 1
            return MagicMock()

        with patch("app.services.glossary_service._create_client", side_effect=counting_factory):
            threads = []
            results = []

            def get_client():
                results.append(gs._get_baml_client())

            for _ in range(10):
                t = threading.Thread(target=get_client)
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert all(r is results[0] for r in results)
            assert call_count >= 1

    def test_get_baml_client_inner_lock_guard_race(self) -> None:
        """Covers the 42->44 branch: inner 'if _b is None' is False.

        This simulates the double-checked locking race: thread A passes the
        outer None check, then thread B initialises _b inside the lock. When
        thread A acquires the lock it finds _b already set, so _create_client
        must NOT be called again — it uses the existing client.
        """
        import app.services.glossary_service as gs

        # Pre-create the client that "another thread" set
        pre_existing_client = MagicMock(spec=["ExtractGlossaryTerms"])

        original_lock = gs._lock

        class RaceSimulatingLock:
            """Sets _b before releasing so the inner guard sees it already set."""

            def __enter__(self):
                # Simulate the competing thread initialising _b first
                gs._b = pre_existing_client
                return self

            def __exit__(self, *args):
                return False

        gs._b = None  # outer check will pass
        gs._lock = RaceSimulatingLock()  # type: ignore[assignment]
        try:
            with patch("app.services.glossary_service._create_client") as mock_factory:
                result = gs._get_baml_client()
                # _create_client must NOT be called — inner guard stopped it
                mock_factory.assert_not_called()
                # Must return the pre-existing client set by the simulated thread
                assert result is pre_existing_client
        finally:
            gs._lock = original_lock
            gs._b = None


# ── Fallback Client Env Injection ───────────────────────────────────────────


class TestFallbackEnvInjection:
    def test_inject_env_sets_fallback_urls(self) -> None:
        """_inject_env sets both primary and fallback env vars."""
        import os

        from app.integrations.baml_setup import _inject_env

        # Clean state
        for key in (
            "BAML_GLOSSARY_BASE_URL",
            "BAML_GLOSSARY_API_KEY",
            "BAML_GLOSSARY_MODEL",
            "BAML_GLOSSARY_FALLBACK_BASE_URL",
            "BAML_GLOSSARY_FALLBACK_API_KEY",
            "BAML_GLOSSARY_FALLBACK_MODEL",
        ):
            os.environ.pop(key, None)

        with patch("app.integrations.baml_setup.settings") as mock_settings:
            mock_settings.CLOUDFLARE_ACCOUNT_ID = "acct-123"
            mock_settings.CLOUDFLARE_GATEWAY_ID = "gw-456"
            mock_settings.CLOUDFLARE_API_TOKEN = "primary-token"
            mock_settings.CF_AIG_AUTHORIZATION = "aig-auth-token"
            _inject_env()

            # Primary
            assert "/compat" in os.environ["BAML_GLOSSARY_BASE_URL"]
            assert os.environ["BAML_GLOSSARY_API_KEY"] == "primary-token"
            assert "workers-ai/" in os.environ["BAML_GLOSSARY_MODEL"]

            # Fallback — both routes through CF Gateway
            assert "/openai" in os.environ["BAML_GLOSSARY_FALLBACK_BASE_URL"]
            assert os.environ["BAML_GLOSSARY_FALLBACK_API_KEY"] == "aig-auth-token"
            assert os.environ["BAML_GLOSSARY_FALLBACK_MODEL"] == "gpt-4.1-mini"

    def test_fallback_urls_are_cf_gateway_not_direct(self) -> None:
        """Both primary and fallback base URLs route through CF Gateway."""
        import os

        from app.integrations.baml_setup import _inject_env

        for key in list(os.environ):
            if key.startswith("BAML_GLOSSARY"):
                os.environ.pop(key, None)

        with patch("app.integrations.baml_setup.settings") as mock_settings:
            mock_settings.CLOUDFLARE_ACCOUNT_ID = "acct-123"
            mock_settings.CLOUDFLARE_GATEWAY_ID = "gw-456"
            mock_settings.CLOUDFLARE_API_TOKEN = "token"
            mock_settings.CF_AIG_AUTHORIZATION = "aig-token"
            _inject_env()

            for key in ("BAML_GLOSSARY_BASE_URL", "BAML_GLOSSARY_FALLBACK_BASE_URL"):
                url = os.environ[key]
                assert "gateway.ai.cloudflare.com" in url
                assert "api.openai.com" not in url
                assert "api.mistral" not in url
                assert "api.groq.com" not in url
                assert "openrouter.ai" not in url

    def test_create_glossary_client_injects_then_imports(self) -> None:
        """The factory function is the single entry point for client creation."""
        import os

        from app.integrations.baml_setup import create_glossary_client

        # Clean state
        for key in list(os.environ):
            if key.startswith("BAML_GLOSSARY"):
                os.environ.pop(key, None)

        with patch("app.integrations.baml_setup.settings") as mock_settings:
            mock_settings.CLOUDFLARE_ACCOUNT_ID = "acct-123"
            mock_settings.CLOUDFLARE_GATEWAY_ID = "gw-456"
            mock_settings.CLOUDFLARE_API_TOKEN = "token"
            mock_settings.CF_AIG_AUTHORIZATION = "aig-token"

            client = create_glossary_client()

            assert "BAML_GLOSSARY_BASE_URL" in os.environ
            assert "BAML_GLOSSARY_FALLBACK_BASE_URL" in os.environ
            assert hasattr(client, "ExtractGlossaryTerms")
