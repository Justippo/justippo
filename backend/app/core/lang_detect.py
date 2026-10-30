"""Dependency-free EN/DE/FR language detection (Pyodide-safe).

``langdetect`` ships as an sdist only (no wheels on PyPI or the Pyodide index),
so it cannot be installed under Cloudflare Python Workers, where ``pywrangler
deploy`` resolves dependencies with ``--no-build``. Rather than pin a broken
dependency, EvidenceEU detects its three MVP languages (English, German,
French) with a lightweight stop-word heuristic.

This is intentionally small and shared (DRY) — ``classification_service``,
``rag_service`` and ``ocr_service`` all route through :func:`detect_language`.
"""

from __future__ import annotations

import re

# Distinctive stop words / markers per language. German is checked first, then
# French, then English, because English function words ("the", "of") are the
# most likely to appear as loanwords in the other two.
_DE = re.compile(r"\b(der|die|das|und|nicht|eine|einen|ein|ist|mit|für|aufenthalt|bescheinigung)\b")
_FR = re.compile(
    r"\b(le|la|les|des|une|un|est|pour|avec|dans|cette|ceci|texte|français|séjour|attestation)\b"
)
_EN = re.compile(r"\b(the|and|of|to|this|english|certificate|permit|application)\b")


def detect_language(text: str, default: str = "und") -> str:
    """Return the ISO 639-1 code (``en``/``de``/``fr``) for ``text``.

    Args:
        text: Text sample to classify (only the first 4000 chars are inspected).
        default: Value returned when no language marker matches. Callers that
            require a usable query language pass ``"en"``; classification passes
            the ISO 639-3 ``"und"`` (undetermined) sentinel.
    """
    sample = f" {text[:4000].lower()} "
    if _DE.search(sample):
        return "de"
    if _FR.search(sample):
        return "fr"
    if _EN.search(sample):
        return "en"
    return default
