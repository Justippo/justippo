# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Translation Service — Layout-Preserving Document Translation (Sprint 2)

Responsibilities:
- Accept OCR-extracted text blocks and a target language
- Route to Cloudflare Workers AI m2m100-1.2b (Sprint 2, Pyodide-safe)
- Apply glossary enforcement via post-editing replacement (ADR-005)
- Return per-page translated text with job tracking
- Preserve an in-memory job store (ephemeral; Sprint 3 wires to D1)

Data flow:
  document_id → OCRService.process() → [OCRPage, ...]
    → TranslationService.translate()
    → [CF Workers AI m2m100-1.2b per block]
    → glossary post-editing replacement
    → TranslationJob(status="done", pages=[...])

Engine roadmap (see ADR-008 Addendum 2026-06-04):
  Sprint 2 demo  : CF Workers AI @cf/meta/m2m100-1.2b  (free, HTTP, Pyodide-safe)
  Community tier : BabelDOC sidecar (AGPL, layout-preserving, Docker)
  Commercial tier: Doclingo API or Argos Translate (MIT, no ToS restriction)
  EXCLUDED       : DeepL API — ToS §8.1.1(f) prohibits use in translation products
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.integrations.cloudflare.gateway import get_gateway_auth_headers, get_gateway_url
from app.integrations.laminar import observe
from app.integrations.langfuse import observe_generation
from app.integrations.pii_redaction_adapter import (
    PIIRedactionRequest,
    is_redaction_ready,
    redact_with_fallback,
)
from app.models.glossary import parse_mistranslations
from app.models.translation_quality import TranslationQualityReport
from app.services.glossary_service import extract_terms
from app.services.translation_quality_service import build_translation_quality_report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported language pairs for m2m100-1.2b (MVP scope: EN / DE / FR)
# ---------------------------------------------------------------------------
# CF Workers AI m2m100-1.2b sync-input.json schema specifies ISO 639-1 codes
# (e.g. "en", "de") — see https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/
# We accept and send ISO 639-1 codes directly.

_SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "de", "fr"})

_SUPPORTED_PAIRS: list[dict[str, str]] = [
    {"source": src, "target": tgt}
    for src in _SUPPORTED_LANGUAGES
    for tgt in _SUPPORTED_LANGUAGES
    if src != tgt
]

_TRANSLATION_SECTION_MAX_CHARS = 800
_TRANSLATION_CONCURRENCY = 4
_TRANSLATION_MAX_ATTEMPTS = 2

_PAGE_MARKER_RE = re.compile(
    r"^(?:page|seite)\s+\d+(?:\s+(?:of|von|sur)\s+\d+)?$",
    re.IGNORECASE,
)
_DECORATED_PAGE_NUMBER_RE = re.compile(r"^[-–—]\s*\d+\s*[-–—]$")
_STRUCTURAL_ONLY_RE = re.compile(r"^[|+\-–—_=:.]+$")

_CANONICAL_FORM_TERMS: dict[str, dict[str, str]] = {
    "first_name": {
        "en": "First name",
        "de": "Vorname",
        "fr": "Prénom",
    },
    "yes": {
        "en": "Yes",
        "de": "Ja",
        "fr": "Oui",
    },
    "no": {
        "en": "No",
        "de": "Nein",
        "fr": "Non",
    },
}


def _canonical_form_cell(
    text: str,
    *,
    source_lang: str,
    target_lang: str,
) -> str | None:
    """Return an exact, gender-neutral translation for known form cells."""
    if source_lang == "auto":
        return None

    normalized = text.casefold().strip().rstrip(":")
    for translations in _CANONICAL_FORM_TERMS.values():
        source_term = translations.get(source_lang)
        target_term = translations.get(target_lang)
        if source_term and target_term and normalized == source_term.casefold():
            return target_term
    return None


def _table_cells(text: str) -> list[str] | None:
    """Parse a pipe-delimited OCR row while retaining its cell boundaries."""
    stripped = text.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _render_table_row(cells: list[str]) -> str:
    return f"| {' | '.join(cells)} |"


def _is_non_translatable_structure(text: str, *, page_number: object | None = None) -> bool:
    """Identify page furniture and borders that contain no translatable content."""
    stripped = text.strip()
    if not stripped:
        return True

    compact = re.sub(r"\s+", "", stripped)
    if (
        len(compact) >= 2
        and _STRUCTURAL_ONLY_RE.fullmatch(compact)
        and any(marker in compact for marker in "-–—_=")
    ):
        return True

    if _PAGE_MARKER_RE.fullmatch(stripped) or _DECORATED_PAGE_NUMBER_RE.fullmatch(stripped):
        return True

    return page_number is not None and stripped == str(page_number)


def _split_translation_sections(
    text: str,
    *,
    max_chars: int = _TRANSLATION_SECTION_MAX_CHARS,
    page_number: object | None = None,
) -> list[str]:
    """Split OCR text into stable, readable translation units.

    Blank lines remain the primary section boundary. Oversized paragraphs are
    split at sentence and then word boundaries so compact translation models
    never receive a full OCR page as one sequence.
    """
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n+", normalized):
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip() and not _is_non_translatable_structure(line, page_number=page_number)
        ]
        if not lines:
            continue
        if len(lines) > 1 and all(line.startswith("|") and line.endswith("|") for line in lines):
            # Preserve tabular structure and source/target row alignment. Sending
            # a whole table as prose encourages compact models to reorder cells.
            paragraphs.extend(lines)
        else:
            paragraphs.append(" ".join(lines))
    sections: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            sections.append(paragraph)
            continue

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", paragraph) if part.strip()]
        current = ""
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    sections.append(current)
                    current = ""
                words = sentence.split()
                word_chunk = ""
                for word in words:
                    candidate = f"{word_chunk} {word}".strip()
                    if word_chunk and len(candidate) > max_chars:
                        sections.append(word_chunk)
                        word_chunk = word
                    else:
                        word_chunk = candidate
                if word_chunk:
                    sections.append(word_chunk)
                continue

            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                sections.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            sections.append(current)

    return sections


# ---------------------------------------------------------------------------
# In-memory job store (Sprint 2 — replaced by D1 in Sprint 3)
# ---------------------------------------------------------------------------

_jobs: dict[str, TranslationJob] = {}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TranslationJob:
    job_id: str
    document_id: str
    source_language: str
    target_language: str
    status: str  # queued | processing | done | failed
    translated_pages: list[dict[str, object]] = field(default_factory=list)
    quality_report: TranslationQualityReport | None = None
    glossary_terms_applied: int = 0
    error: str | None = None
    output_path: str | None = None  # Sprint 3: D1 / R2 object key
    redaction_metadata: dict[str, object] | None = None  # PII redaction stats (Art. 5)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TranslationError(Exception):
    """Raised when the translation backend returns an unrecoverable error."""


class UnsupportedLanguagePairError(TranslationError):
    """Raised when source→target language pair is not supported."""


@dataclass
class _GlossaryEnforcementResult:
    pages: list[dict[str, object]]
    terms_applied: int
    checked: bool


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TranslationService:
    """
    Translates OCR-extracted text using Cloudflare Workers AI m2m100-1.2b.

    All calls go through the Cloudflare AI Gateway (logging + caching).
    No text is written to disk; the translated pages live in the TranslationJob.

    Sprint 2 limitations:
    - Plain text translation only (no layout reconstruction — BabelDOC sidecar in Sprint 3)
    - In-memory job store (no persistence across Worker restarts)
    - m2m100-1.2b quality is lower than BabelDOC for complex layouts
    """

    def __init__(self, glossary_repo: Any | None = None) -> None:
        self._glossary_repo = glossary_repo

    @staticmethod
    def _length_bucket(n_chars: int) -> str:
        """Bucket character count for the Not Diamond routing signal.

        Routing signal only — Not Diamond uses this to bias toward cheaper
        or stronger models. Keep buckets coarse (5 levels) so we never leak
        exact document size."""
        if n_chars < 200:
            return "tiny"
        if n_chars < 1000:
            return "short"
        if n_chars < 5000:
            return "medium"
        if n_chars < 20000:
            return "long"
        return "huge"

    # ADD: trace model, language pair, char count (no source/translated text — GDPR)
    @observe(name="translate.llm", span_type="LLM")
    # END ADD
    async def translate(
        self,
        document_id: str,
        source_language: str,
        target_language: str,
        pages: list[dict[str, object]] | None = None,
        preserve_layout: bool = True,  # reserved for Sprint 3 BabelDOC sidecar
        glossary_repo: Any | None = None,
    ) -> TranslationJob:
        """
        Translate extracted OCR pages to the target language.

        Args:
            document_id:     Caller-supplied document identifier.
            source_language: ISO 639-1 source language code, or "auto" for detection.
            target_language: ISO 639-1 target language code (en | de | fr).
            pages:           List of OCRPage-like dicts with at least {"page": int, "text": str}.
                             If None, returns a job with status="done" and no pages (stub mode).
            preserve_layout: Reserved for Sprint 3 BabelDOC sidecar; currently ignored.

        Returns:
            TranslationJob with status="done" and translated_pages populated.
        """
        job_id = str(uuid.uuid4())
        job = TranslationJob(
            job_id=job_id,
            document_id=document_id,
            source_language=source_language,
            target_language=target_language,
            status="queued",
        )
        _jobs[job_id] = job

        # Validate language pair
        effective_source = source_language if source_language != "auto" else None
        if effective_source and effective_source not in _SUPPORTED_LANGUAGES:
            job.status = "failed"
            job.error = (
                f"Unsupported source language '{source_language}'. "
                f"Supported: {sorted(_SUPPORTED_LANGUAGES)}"
            )
            return job
        if target_language not in _SUPPORTED_LANGUAGES:
            job.status = "failed"
            job.error = (
                f"Unsupported target language '{target_language}'. "
                f"Supported: {sorted(_SUPPORTED_LANGUAGES)}"
            )
            return job

        if not pages:
            # No content to translate — return done with empty pages
            job.status = "done"
            return job

        job.status = "processing"
        translated: list[dict[str, object]] = []

        try:
            page_specs: list[tuple[object, list[str]]] = []
            for page in pages:
                page_num = page.get("page", 0)
                text = str(page.get("text", "")).strip()
                page_specs.append(
                    (
                        page_num,
                        _split_translation_sections(text, page_number=page_num),
                    )
                )

            semaphore = asyncio.Semaphore(_TRANSLATION_CONCURRENCY)

            # PII redaction state (GDPR Art. 5(1)(c) data minimisation).
            # When enabled, redact each section BEFORE it reaches the external
            # translation backend. Falls back to unredacted text on sidecar
            # failure — translation (the user's primary intent) is never blocked.
            redaction_enabled = is_redaction_ready()
            _redaction_total_entities = 0
            _redaction_entity_types: list[str] = []
            _redaction_succeeded = True

            async def translate_section(source_text: str) -> dict[str, object]:
                nonlocal _redaction_total_entities, _redaction_entity_types, _redaction_succeeded
                async with semaphore:
                    # Redact PII before sending to external translation backend
                    text_to_translate = source_text
                    if redaction_enabled:
                        redacted, succeeded, result = await redact_with_fallback(
                            PIIRedactionRequest(
                                text=source_text,
                                language=source_language if source_language != "auto" else "en",
                                timeout_seconds=settings.PII_REDACTION_TIMEOUT_S,
                            )
                        )
                        text_to_translate = redacted
                        if result is not None:
                            _redaction_total_entities += result.entity_count
                            for etype in result.entity_types:
                                if etype not in _redaction_entity_types:
                                    _redaction_entity_types.append(etype)
                        if not succeeded:
                            _redaction_succeeded = False

                    for attempt in range(1, _TRANSLATION_MAX_ATTEMPTS + 1):
                        try:
                            translated_text = await self._translate_section_content(
                                text=text_to_translate,
                                source_lang=source_language,
                                target_lang=target_language,
                            )
                            if not translated_text.strip():
                                raise TranslationError("Translation provider returned empty text")
                            return {
                                "translated_text": translated_text,
                                "status": "translated",
                                "attempts": attempt,
                                "error_code": None,
                            }
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Translation section attempt %s/%s failed (%s→%s): %s",
                                attempt,
                                _TRANSLATION_MAX_ATTEMPTS,
                                source_language,
                                target_language,
                                type(exc).__name__,
                            )
                    return {
                        "translated_text": "",
                        "status": "failed",
                        "attempts": _TRANSLATION_MAX_ATTEMPTS,
                        "error_code": "TRANSLATION_SECTION_FAILED",
                    }

            source_sections = [section for _, sections in page_specs for section in sections]
            section_results = await asyncio.gather(
                *(translate_section(section) for section in source_sections)
            )

            cursor = 0
            for page_num, sections in page_specs:
                section_rows: list[dict[str, object]] = []
                for index, source_text in enumerate(sections):
                    section_result = section_results[cursor]
                    cursor += 1
                    section_rows.append(
                        {
                            "index": index,
                            "source_text": source_text,
                            **section_result,
                        }
                    )
                failed_sections = sum(section.get("status") == "failed" for section in section_rows)
                page_status = (
                    "translated"
                    if failed_sections == 0
                    else "failed"
                    if failed_sections == len(section_rows)
                    else "partial"
                )
                translated.append(
                    {
                        "page": page_num,
                        "text": "\n\n".join(
                            str(section["translated_text"]) for section in section_rows
                        ),
                        "sections": section_rows,
                        "status": page_status,
                    }
                )
                logger.info(
                    "Translated page %s of document %s in %s sections (%s→%s)",
                    page_num,
                    document_id,
                    len(section_rows),
                    source_language,
                    target_language,
                )
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.warning(
                "Translation orchestration failed: %s", type(exc).__name__
            )  # pragma: no cover
            job.status = "failed"  # pragma: no cover
            job.error = "Translation could not be orchestrated."  # pragma: no cover
            return job  # pragma: no cover

        glossary_result = self._apply_glossary_enforcement_result(
            pages,
            translated,
            source_language,
            target_language,
        )
        job.translated_pages = glossary_result.pages
        job.glossary_terms_applied = glossary_result.terms_applied
        redaction_metadata = {
            "enabled": redaction_enabled,
            "total_entities": _redaction_total_entities,
            "entity_types": _redaction_entity_types,
            "succeeded": _redaction_succeeded,
        }
        job.redaction_metadata = redaction_metadata
        if redaction_enabled:
            logger.info(
                "PII redaction for document %s: entities=%d, types=%s, succeeded=%s",
                document_id,
                _redaction_total_entities,
                _redaction_entity_types,
                _redaction_succeeded,
            )
        terminology_review_status: Literal[
            "applied",
            "checked_no_changes",
            "not_checked",
        ] = (
            "not_checked"
            if not glossary_result.checked
            else "applied"
            if glossary_result.terms_applied > 0
            else "checked_no_changes"
        )
        job.quality_report = build_translation_quality_report(
            job.translated_pages,
            terminology_review_status=terminology_review_status,
        )
        failed_sections = job.quality_report.failed_section_count
        if failed_sections == 0:
            job.status = "done"
        elif failed_sections == job.quality_report.source_section_count:
            job.status = "failed"
            job.error = (
                f"All translation sections failed after {_TRANSLATION_MAX_ATTEMPTS} attempts."
            )
        else:
            job.status = "partial"
            job.error = (
                f"{failed_sections} translation sections require review after "
                f"{_TRANSLATION_MAX_ATTEMPTS} attempts."
            )
        return job

    async def get_job(self, job_id: str) -> TranslationJob | None:
        """Retrieve a translation job by ID from the in-memory store."""
        return _jobs.get(job_id)

    async def get_supported_language_pairs(self) -> list[dict[str, str]]:
        """Return all supported source→target language pairs for the current engine."""
        return _SUPPORTED_PAIRS

    async def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Thin testable wrapper around the m2m100 backend.

        Translates a single text block without job bookkeeping. This is the
        entry point used by integration tests so they exercise the same HTTP
        path as production while keeping the test surface small.

        Note: glossary enforcement is applied only in translate(), which works
        on full documents. Single-block callers get the raw model output.
        """
        return await self._call_m2m100(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    async def _translate_section_content(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Translate content without flattening form rows into prose."""
        cells = _table_cells(text)
        if cells is None:
            canonical = _canonical_form_cell(
                text,
                source_lang=source_lang,
                target_lang=target_lang,
            )
            if canonical is not None:
                return canonical
            return await self._call_m2m100(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
            )

        translated_cells: list[str] = []
        for cell in cells:
            if not cell:
                translated_cells.append("")
                continue

            canonical = _canonical_form_cell(
                cell,
                source_lang=source_lang,
                target_lang=target_lang,
            )
            if canonical is not None:
                translated_cells.append(canonical)
                continue

            translated_cells.append(
                await self._call_m2m100(
                    text=cell,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
            )

        return _render_table_row(translated_cells)

    # ------------------------------------------------------------------
    # Glossary enforcement (post-editing replacement)
    # ------------------------------------------------------------------

    def _apply_glossary_enforcement(
        self,
        input_pages: list[dict[str, object]],
        translated_pages: list[dict[str, object]],
        source_lang: str,
        target_lang: str,
    ) -> list[dict[str, object]]:
        """Preserve the legacy list-returning helper for focused unit callers."""
        return self._apply_glossary_enforcement_result(
            input_pages,
            translated_pages,
            source_lang,
            target_lang,
        ).pages

    def _apply_glossary_enforcement_result(
        self,
        input_pages: list[dict[str, object]],
        translated_pages: list[dict[str, object]],
        source_lang: str,
        target_lang: str,
    ) -> _GlossaryEnforcementResult:
        """Replace mistranslated glossary terms with canonical target terms.

        m2m100-1.2b has no native glossary support, so we extract terms from
        the source text and post-edit the model output. Replacement uses
        casefold-aware, word-boundary-safe matching to avoid false positives.

        Glossary extraction failures are logged but do not fail the job — the
        raw translation is still useful and the extraction endpoint may be
        unavailable in some environments.
        """
        if source_lang == "auto":
            source_lang = "en"

        if source_lang not in _SUPPORTED_LANGUAGES or target_lang not in _SUPPORTED_LANGUAGES:
            return _GlossaryEnforcementResult(translated_pages, 0, False)

        target_field = f"term_{target_lang}"
        source_field = f"term_{source_lang}"
        terms_applied = 0
        checked = True

        def enforce_text(source_text: str, translated_text: str, terms: list[Any]) -> str:
            nonlocal terms_applied
            for term in terms:
                source_term = getattr(term, source_field, "")
                target_term = getattr(term, target_field, "")
                if not source_term or not target_term:
                    continue
                if not _term_appears(source_term, source_text):
                    continue
                if _term_appears(target_term, translated_text):
                    continue

                replaced = False
                for mistranslation in parse_mistranslations(term):
                    if not mistranslation:
                        continue
                    updated_text = _replace_term(translated_text, mistranslation, target_term)
                    if updated_text != translated_text:
                        logger.info(
                            "Glossary enforcement: replaced mistranslation '%s' with '%s' (%s->%s)",
                            mistranslation,
                            target_term,
                            source_lang,
                            target_lang,
                        )
                        translated_text = updated_text
                        terms_applied += 1
                        replaced = True
                        break

                if not replaced:
                    updated_text = _replace_term(translated_text, source_term, target_term)
                    if updated_text != translated_text:
                        logger.info(
                            "Glossary enforcement: replaced '%s' with '%s' (%s->%s)",
                            source_term,
                            target_term,
                            source_lang,
                            target_lang,
                        )
                        translated_text = updated_text
                        terms_applied += 1
            return translated_text

        enforced_pages: list[dict[str, object]] = []
        for in_page, trans_page in zip(input_pages, translated_pages, strict=False):
            in_text = str(in_page.get("text", ""))
            if not in_text.strip():
                enforced_pages.append(trans_page)
                continue

            try:
                terms = extract_terms(in_text, source_lang)
            except Exception as exc:  # noqa: BLE001
                checked = False
                logger.warning(
                    "Glossary extraction skipped for page %s: %s", in_page.get("page"), exc
                )
                enforced_pages.append(trans_page)
                continue

            raw_sections = trans_page.get("sections")
            if isinstance(raw_sections, list):
                enforced_sections: list[dict[str, object]] = []
                for raw_section in raw_sections:
                    if not isinstance(raw_section, dict):
                        continue
                    section_source = str(raw_section.get("source_text", ""))
                    section_translation = enforce_text(
                        section_source,
                        str(raw_section.get("translated_text", "")),
                        terms,
                    )
                    enforced_sections.append(
                        {
                            **raw_section,
                            "translated_text": section_translation,
                        }
                    )
                enforced_pages.append(
                    {
                        **trans_page,
                        "text": "\n\n".join(
                            str(section["translated_text"]) for section in enforced_sections
                        ),
                        "sections": enforced_sections,
                    }
                )
                continue

            enforced_pages.append(
                {
                    "page": trans_page.get("page"),
                    "text": enforce_text(in_text, str(trans_page.get("text", "")), terms),
                }
            )

        return _GlossaryEnforcementResult(enforced_pages, terms_applied, checked)

    # ------------------------------------------------------------------
    # CF Workers AI m2m100-1.2b call
    # ------------------------------------------------------------------

    # ADD: Langfuse GENERATION span — traces model, tokens, latency per LLM call
    @observe_generation(name="translate.llm", model="m2m100-1.2b")
    # END ADD
    async def _call_m2m100(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        *,
        timeout: int = 30,
    ) -> str:
        """
        Translate a text block via Cloudflare Workers AI m2m100-1.2b.

        Routed through the Cloudflare AI Gateway for logging and caching.
        The model endpoint path is:
          /workers-ai/@cf/meta/m2m100-1.2b

        Request schema (CF Workers AI REST API):
          {"text": str, "source_lang": str, "target_lang": str}

        Response schema:
          {"result": {"translated_text": str}, "success": bool, "errors": [...]}

        Raises:
            TranslationError: on non-2xx response or API-level error.
        """
        # Cloudflare Workers AI m2m100-1.2b REST schema specifies language codes
        # (e.g. "en", not "english") per the official sync-input.json schema.
        # "auto" defaults to English for the common EU document source case.
        payload_source = source_lang if source_lang != "auto" else "en"

        # ── BEFORE: hardcoded model in URL, no routing layer ─────────────────
        # url = get_gateway_url("workers-ai", "@cf/meta/m2m100-1.2b")
        # ── AFTER: routing picks the model; URL is built from it ─────────────
        # Opt-in via NOT_DIAMOND_ENABLED. Falls back to m2m100 silently on
        # any error — never raises, never blocks the request path.
        from app.integrations.routing.not_diamond import (
            NotDiamondRouter,
            TaskType,
        )

        _signals: dict[str, object] = {
            "language_pair": f"{payload_source}-{target_lang}",
            "source_language": payload_source,
            "target_language": target_lang,
            "text_length_bucket": self._length_bucket(len(text)),
        }
        selected_model = await NotDiamondRouter().route(TaskType.TRANSLATION, _signals)

        # Branch on the routed model: m2m100 (cheap) vs Mistral Large (frontier).
        # The sentinel "mistral-large-translation" triggers the LLM chat-completion
        # path; any @cf/ model uses the m2m100 REST path; anything else falls back
        # to m2m100 (defensive — BabelDOC is document-level, can't do text blocks).
        if selected_model == "mistral-large-translation":
            return await self._call_mistral_large(text, payload_source, target_lang, timeout)

        if not selected_model.startswith("@cf/"):
            logger.warning(
                "Not Diamond returned unsupported model %s for translation; falling back to m2m100",
                selected_model,
            )
            selected_model = "@cf/meta/m2m100-1.2b"

        url = get_gateway_url("workers-ai", selected_model)
        headers = {
            "Authorization": f"Bearer {settings.CF_WORKERS_AI_API_TOKEN}",
            "Content-Type": "application/json",
        }
        headers.update(get_gateway_auth_headers())
        payload = {
            "text": text,
            "source_lang": payload_source,
            "target_lang": target_lang,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise TranslationError(
                f"CF Workers AI m2m100 returned HTTP {response.status_code}: {response.text[:200]}"
            )

        data: dict[str, object] = response.json()
        if not data.get("success", True):
            errors = data.get("errors", [])
            raise TranslationError(f"CF Workers AI m2m100 error: {errors}")

        result = data.get("result", {})
        if not isinstance(result, dict):
            raise TranslationError(f"Unexpected CF Workers AI response shape: {str(data)[:200]}")

        translated = result.get("translated_text", "")
        return str(translated)

    async def _call_mistral_large(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        timeout: int,
    ) -> str:
        """Translate a text block via Mistral Large (European frontier LLM).

        Mistral Large is natively fluent in EN/FR/DE/ES/IT and outperforms
        m2m100 on complex legal/bureaucratic text. Routed through the CF AI
        Gateway (mistral provider) — no direct URLs (CI-enforced by REM-8).

        Uses a chat-completion call with a translation system prompt. The
        source/target language codes are expanded to full names for clarity.
        """
        _LANG_NAMES = {"en": "English", "de": "German", "fr": "French"}
        src_name = _LANG_NAMES.get(source_lang, source_lang)
        tgt_name = _LANG_NAMES.get(target_lang, target_lang)

        url = get_gateway_url("mistral", "v1/chat/completions")
        headers = {
            "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        }
        headers.update(get_gateway_auth_headers())
        payload = {
            "model": "mistral-large-latest",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are a professional legal translator. "
                        f"Translate the following text from {src_name} to {tgt_name}. "
                        f"Preserve legal terminology, formatting, and structure. "
                        f"Output only the translation, no explanations."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise TranslationError(
                f"Mistral Large returned HTTP {response.status_code}: {response.text[:200]}"
            )

        data: dict[str, object] = response.json()
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise TranslationError(f"Unexpected Mistral Large response shape: {str(data)[:200]}")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise TranslationError(f"Unexpected Mistral choice shape: {str(first_choice)[:200]}")

        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            raise TranslationError(f"Unexpected Mistral message shape: {str(message)[:200]}")

        translated = message.get("content", "")
        return str(translated)


# ---------------------------------------------------------------------------
# Shared matching helpers (also used by tests)
# ---------------------------------------------------------------------------


def _term_appears(term: str, text: str) -> bool:
    """Return True if *term* appears in *text* as a whole word/phrase."""
    normalized_term = _normalize_for_matching(term)
    normalized_text = _normalize_for_matching(text)
    if " " in normalized_term:
        return normalized_term in normalized_text
    return bool(
        re.search(
            r"(?<!\w)" + re.escape(normalized_term) + r"(?!\w)",
            normalized_text,
        )
    )


def _replace_term(text: str, source_term: str, target_term: str) -> str:
    """Replace occurrences of *source_term* in *text* with *target_term*.

    Uses a Unicode-aware word-boundary regex so compound words are not
    accidentally modified. Falls back to substring replacement for
    multi-word terms.
    """
    normalized_source = _normalize_for_matching(source_term)
    if " " in normalized_source:
        # Multi-word term: case-insensitive substring replacement.
        pattern = re.compile(re.escape(source_term), re.IGNORECASE)
        return pattern.sub(target_term, text)

    # Single-word term: word-boundary guarded replacement.
    pattern = re.compile(
        r"(?<!\w)" + re.escape(source_term) + r"(?!\w)",
        re.IGNORECASE,
    )
    return pattern.sub(target_term, text)


def _normalize_for_matching(text: str) -> str:
    """Normalize text for robust case/punctuation/whitespace matching."""
    text = str(text).casefold()
    # Collapse periods between single letters (C.E. -> CE) before stripping punctuation.
    text = re.sub(r"(?<=\b\w)\.(?=\w\b)", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
