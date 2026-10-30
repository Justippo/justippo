"""Unit tests for the dependency-free EN/DE/FR language detector.

Guards the Pyodide-safe replacement for ``langdetect`` (which ships sdist-only
and cannot install under ``pywrangler deploy --no-build``).
"""

import pytest

from app.core.lang_detect import detect_language


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Ceci est un texte en français.", "fr"),
        ("Une attestation pour le titre de séjour", "fr"),
        ("This is an English text.", "en"),
        ("The certificate application", "en"),
        ("Ein Antrag auf Aufenthalt", "de"),
        ("Der schnelle braune Fuchs mit Bescheinigung", "de"),
    ],
)
def test_detects_mvp_languages(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_unknown_returns_default_sentinel() -> None:
    assert detect_language("xyz abc gibberish qwerty") == "und"


def test_unknown_honours_custom_default() -> None:
    assert detect_language("xyz abc gibberish qwerty", default="en") == "en"


def test_empty_string_returns_default() -> None:
    assert detect_language("", default="en") == "en"


def test_german_checked_before_english_loanwords() -> None:
    # Contains the English loanword "application" but German markers win.
    assert detect_language("Die application und der Antrag") == "de"
