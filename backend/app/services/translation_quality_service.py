"""Local, deterministic checks for extracted-text translations."""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from app.models.translation_quality import (
    TranslationQualityCheck,
    TranslationQualityReport,
)

_REFERENCE_TOKEN_RE = re.compile(r"(?<!\w)(?=[^\s]*\d)[A-Za-zÀ-ÖØ-öø-ÿ0-9][\w./:%+-]*(?!\w)")
_PROPER_NAME_RE = re.compile(r"\b[A-ZÀ-ÖØ-Þ][\w'’-]+(?:\s+[A-ZÀ-ÖØ-Þ][\w'’-]+)+\b")


def _normalized_counter(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(
        match.casefold().rstrip(".,;:") for match in pattern.findall(text) if match.rstrip(".,;:")
    )


def _missing_values(source: Counter[str], translated: Counter[str]) -> list[str]:
    missing = source - translated
    return sorted(missing.elements())


def build_translation_quality_report(
    translated_pages: list[dict[str, object]],
    *,
    terminology_review_status: Literal[
        "applied",
        "checked_no_changes",
        "not_checked",
    ] = "not_checked",
) -> TranslationQualityReport:
    """Evaluate section coverage and preservation without another model call."""
    sections: list[dict[str, object]] = []
    for page in translated_pages:
        raw_sections = page.get("sections")
        if isinstance(raw_sections, list):
            sections.extend(section for section in raw_sections if isinstance(section, dict))

    source_count = len(sections)
    failed_count = sum(section.get("status") == "failed" for section in sections)
    empty_count = sum(
        section.get("status") != "failed" and not str(section.get("translated_text", "")).strip()
        for section in sections
    )
    translated_count = source_count - failed_count - empty_count
    source_text = "\n".join(str(section.get("source_text", "")) for section in sections)
    translated_text = "\n".join(
        str(section.get("translated_text", ""))
        for section in sections
        if section.get("status") != "failed"
    )

    checks: list[TranslationQualityCheck] = []
    coverage_ok = failed_count == 0
    checks.append(
        TranslationQualityCheck(
            code="SECTION_COVERAGE",
            status="pass" if coverage_ok else "warning",
            message=(
                "All extracted sections were translated."
                if coverage_ok
                else f"{failed_count} of {source_count} sections require review."
            ),
        )
    )
    checks.append(
        TranslationQualityCheck(
            code="EMPTY_TRANSLATION",
            status="warning" if empty_count else "pass",
            message=(
                f"{empty_count} sections returned an empty translation."
                if empty_count
                else "No translated sections are empty."
            ),
        )
    )

    identical_sections = sum(
        bool(str(section.get("source_text", "")).strip())
        and str(section.get("source_text", "")).casefold().strip()
        == str(section.get("translated_text", "")).casefold().strip()
        for section in sections
        if section.get("status") != "failed"
    )
    checks.append(
        TranslationQualityCheck(
            code="SOURCE_TEXT_LEAKAGE",
            status="warning" if identical_sections else "pass",
            message=(
                f"{identical_sections} translated sections are unchanged from the source."
                if identical_sections
                else "No complete source sections were returned unchanged."
            ),
        )
    )

    missing_references = _missing_values(
        _normalized_counter(_REFERENCE_TOKEN_RE, source_text),
        _normalized_counter(_REFERENCE_TOKEN_RE, translated_text),
    )
    checks.append(
        TranslationQualityCheck(
            code="REFERENCE_PRESERVATION",
            status="warning" if missing_references else "pass",
            message=(
                "Review missing dates, amounts, or references: " + ", ".join(missing_references[:8])
                if missing_references
                else "Dates, amounts, and reference numbers were preserved."
            ),
        )
    )

    missing_names = _missing_values(
        _normalized_counter(_PROPER_NAME_RE, source_text),
        _normalized_counter(_PROPER_NAME_RE, translated_text),
    )
    checks.append(
        TranslationQualityCheck(
            code="PROPER_NAME_PRESERVATION",
            status="warning" if missing_names else "pass",
            message=(
                "Review possible changed names: " + ", ".join(missing_names[:8])
                if missing_names
                else "Detected multi-word proper names were preserved."
            ),
        )
    )

    requires_review = terminology_review_status == "not_checked" or any(
        check.status == "warning" for check in checks
    )
    return TranslationQualityReport(
        status="review" if requires_review else "pass",
        terminology_review_status=terminology_review_status,
        source_section_count=source_count,
        translated_section_count=translated_count,
        failed_section_count=failed_count,
        checks=checks,
    )
