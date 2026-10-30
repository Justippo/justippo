# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Glossary Extraction Service

Wraps the BAML-generated ExtractGlossaryTerms function with validation,
error handling, and integration with the Domain Glossary (ADR-005).

This is a PROMPT → TYPED-OUTPUT generation call — BAML's sweet spot.
Do NOT extend this service to cover OCR, translation, or retrieval calls.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.integrations.baml_setup import create_glossary_client as _create_client

if TYPE_CHECKING:
    from baml_client.sync_client import BamlSyncClient
    from baml_client.types import GlossaryTerm

logger = logging.getLogger(__name__)

# Thread-safe singleton — double-checked locking pattern.
# Pyodide (Cloudflare Workers Python) is single-threaded but this code also
# runs in Docker with uvicorn workers where thread safety matters.
_lock = threading.Lock()
_b: BamlSyncClient | None = None


def _is_baml_native_panic(exc: BaseException) -> bool:
    """Return whether *exc* is the catchable PyO3 panic emitted by BAML.

    PyO3 deliberately derives ``PanicException`` from ``BaseException``. Match
    both its type and native module so cancellation and process-control signals
    such as ``KeyboardInterrupt`` and ``SystemExit`` are never swallowed.
    """
    exc_type = type(exc)
    return exc_type.__name__ == "PanicException" and exc_type.__module__ == "pyo3_runtime"


def _get_baml_client() -> BamlSyncClient:
    """Lazy-create and cache the BAML sync client with full thread safety.

    Uses double-checked locking: the first None check avoids lock contention
    in the common (already-initialized) path; the lock protects the race
    window where two threads might both see None.
    """
    global _b
    if _b is None:
        with _lock:
            if _b is None:
                _b = _create_client()
    return _b


def extract_terms(text: str, source_lang: str) -> list[GlossaryTerm]:
    """Extract domain-specific legal terminology from a document text chunk.

    Args:
        text: Raw document text (unstructured, any length).
        source_lang: Source language ISO code (en, de, or fr).

    Returns:
        List of GlossaryTerm objects with canonical EN/DE/FR terms + definitions.
        Empty list if no legal terminology found or text is whitespace-only.

    Raises:
        ValueError: If source_lang is not one of en/de/fr.
        RuntimeError: If BAML LLM call fails (network, auth, or parse error).
    """
    # Guard against None inputs
    if text is None:
        text = ""
    if source_lang is None:
        raise ValueError("source_lang must not be None")

    source_lang = source_lang.lower().strip()
    if source_lang not in ("en", "de", "fr"):
        raise ValueError(f"Unsupported language '{source_lang}' — must be en, de, or fr")

    # Truncate to reasonable chunk size for glossary extraction
    truncated = text[:8000] if len(text) > 8000 else text

    if not truncated.strip():
        return []

    try:
        b = _get_baml_client()
        raw_terms = b.ExtractGlossaryTerms(truncated, source_lang)
        terms = _unwrap_checked_terms(raw_terms)
        logger.info(
            "Extracted %d glossary terms from %d-char text (%s)",
            len(terms),
            len(truncated),
            source_lang,
        )
        return terms
    except Exception as exc:
        logger.error("Glossary extraction failed: %s", exc)
        raise RuntimeError(f"Glossary extraction failed: {exc}") from exc
    except BaseException as exc:
        if not _is_baml_native_panic(exc):
            raise
        logger.error("Glossary extraction failed after BAML native panic: %s", exc)
        raise RuntimeError(f"Glossary extraction failed: {exc}") from exc


async def insert_terms(
    terms: list[GlossaryTerm],
    doc_id: str | None = None,
    source_lang: str | None = None,
    db: object | None = None,
) -> list[dict[str, object]]:
    """Persist extracted glossary terms via the repository layer.

    This is intentionally fire-and-forget: persistence failures are logged and
    swallowed so glossary extraction never blocks the document pipeline.
    """
    if not terms:
        return []

    try:
        from app.repositories.glossary_repo import GlossaryRepo  # noqa: PLC0415

        repo = GlossaryRepo(db)  # type: ignore[arg-type]
        payload: list[dict[str, object]] = []
        for term in terms:
            payload.append(
                {
                    "term_en": str(getattr(term, "term_en", "") or ""),
                    "term_de": str(getattr(term, "term_de", "") or ""),
                    "term_fr": str(getattr(term, "term_fr", "") or ""),
                    "definition": str(getattr(term, "definition", "") or ""),
                    "mistranslations": getattr(term, "mistranslations", None),
                    "source_doc_id": doc_id,
                    "source_lang": source_lang,
                    "confidence": float(getattr(term, "confidence", 1.0) or 1.0),
                }
            )

        return await repo.upsert_terms(payload, doc_id=doc_id or "", lang=source_lang or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Glossary persistence skipped: %s", exc)
        return []


def _unwrap_checked_terms(raw_terms: list) -> list:  # type: ignore[type-arg]
    """Unwrap Checked<T> fields from BAML @check decorators in-place.

    BAML's @check wraps checked fields in Checked<T> (e.g., term_en becomes
    Checked[str, Literal['term_en_nonempty']]). We use object.__setattr__ to
    bypass Pydantic validation and set the underlying value directly, so
    consumers see plain strings for backward compatibility.

    Returns the same list (mutated in-place) for convenience.
    """
    for term in raw_terms:
        object.__setattr__(term, "term_en", _maybe_unwrap(term.term_en))
        object.__setattr__(term, "term_de", _maybe_unwrap(term.term_de))
        object.__setattr__(term, "term_fr", _maybe_unwrap(term.term_fr))
        object.__setattr__(term, "definition", _maybe_unwrap(term.definition))
    return list(raw_terms) if raw_terms else []


def _maybe_unwrap(field_value: object) -> object:
    """If field_value is a Checked<T>, return field_value.value; else return as-is.

    Uses isinstance (not hasattr) to avoid false positives with MagicMock
    objects that have every attribute.
    """
    from baml_client.types import Checked  # noqa: PLC0415

    if isinstance(field_value, Checked):
        return field_value.value
    return field_value
