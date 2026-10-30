"""Shared utilities for translation accuracy tests (mock + real model).

DRY:
- Single YAML loader used by the mock-based and real-model integration suites.
- Single normalization helper for case-insensitive, punctuation-insensitive,
  Unicode-casefolded comparisons. This correctly handles German ß → ss,
  which re.IGNORECASE does NOT do in Python.

"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_YAML_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "testing" / "translation-test-cases.yaml"
)


@dataclass
class ExpectedTermDef:
    source: str
    target: str


@dataclass
class QualityThresholdsDef:
    term_accuracy: float = 0.80
    structural_pres: float = 0.90
    completeness: float = 0.95
    consistency: float = 0.90


@dataclass
class TranslationTestCase:
    id: str
    category: str
    description: str
    source_lang: str
    target_lang: str
    input_pages: list[dict[str, Any]]
    expected_terms: list[ExpectedTermDef]
    forbidden_terms: list[str]
    quality_thresholds: QualityThresholdsDef
    checks: list[str]
    enabled: bool = True


def normalize_for_comparison(text: str) -> str:
    """Normalize text for robust comparison across case, punctuation, and whitespace.

    Uses str.casefold() so German ß is folded to "ss". re.IGNORECASE does NOT
    perform this fold, so any case-insensitive comparison in the translation
    suite must go through this helper rather than .lower() or re.IGNORECASE.
    """
    text = str(text).casefold()
    translator = str.maketrans("", "", string.punctuation)
    text = text.translate(translator)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def term_present(term: str, text: str) -> bool:
    """Return True if *term* is present in *text* after normalization.

    For single-word terms, require word boundaries to avoid partial matches
    (e.g. "action" matching "interaction"). For multi-word terms, use substring.
    """
    if not term:
        return False

    normalized_term = normalize_for_comparison(term)
    normalized_text = normalize_for_comparison(text)

    if " " in normalized_term:
        return normalized_term in normalized_text

    return bool(re.search(r"\b" + re.escape(normalized_term) + r"\b", normalized_text))


def _parse_thresholds(data: dict[str, float] | None) -> QualityThresholdsDef:
    """Parse quality thresholds with deep-merge over sensible defaults."""
    defaults = QualityThresholdsDef()
    if not data:
        return defaults
    return QualityThresholdsDef(
        term_accuracy=data.get("term_accuracy", defaults.term_accuracy),
        structural_pres=data.get("structural_pres", defaults.structural_pres),
        completeness=data.get("completeness", defaults.completeness),
        consistency=data.get("consistency", defaults.consistency),
    )


def _parse_expected_terms(data: list[dict[str, str]] | None) -> list[ExpectedTermDef]:
    if not data:
        return []
    terms = []
    for t in data:
        if "source" not in t or "target" not in t:
            raise ValueError(f"Malformed expected_terms entry (missing 'source' or 'target'): {t}")
        if not t["source"] or not t["target"]:
            raise ValueError(f"Empty source/target in expected_terms entry: {t}")
        terms.append(ExpectedTermDef(source=t["source"], target=t["target"]))
    return terms


def load_translation_test_cases() -> list[TranslationTestCase]:
    """Load and parse all enabled test cases from the canonical YAML file."""
    if not _YAML_PATH.exists():
        raise FileNotFoundError(f"Test cases YAML not found: {_YAML_PATH}")

    with _YAML_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw = data.get("test_cases", []) if isinstance(data, dict) else data

    cases: list[TranslationTestCase] = []
    seen_ids: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        tc_id = entry["id"]
        if tc_id in seen_ids:
            raise ValueError(f"Duplicate test case id '{tc_id}' in YAML — each id must be unique")
        seen_ids.add(tc_id)
        tc = TranslationTestCase(
            id=entry["id"],
            category=entry.get("category", ""),
            description=entry.get("description", ""),
            source_lang=entry.get("source_lang", "en"),
            target_lang=entry.get("target_lang", "de"),
            input_pages=entry.get("input_pages", []),
            expected_terms=_parse_expected_terms(entry.get("expected_terms")),
            forbidden_terms=entry.get("forbidden_terms", []),
            quality_thresholds=_parse_thresholds(entry.get("quality_thresholds")),
            checks=entry.get("checks", ["terminology", "completeness", "no_forbidden_terms"]),
            enabled=entry.get("enabled", True),
        )
        if tc.enabled:
            cases.append(tc)
    return cases
