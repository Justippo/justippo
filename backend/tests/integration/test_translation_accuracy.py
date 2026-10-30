"""Translation Accuracy Integration Tests (ADR-005, Sprint 2)

Loads test cases from docs/testing/translation-test-cases.yaml and validates
each against the TranslationService + GlossaryService pipeline.

DRY principles:
- Test cases and normalization live in tests.translation_accuracy_utils and are
  shared between the mock-based and real-model integration suites.
- Mock responses are built by shared helpers, not hardcoded per test.

Usage:
    pytest backend/tests/integration/test_translation_accuracy.py -v
    TRANSLATION_INTEGRATION_TESTS=true pytest backend/tests/integration/test_translation_accuracy.py -v -k RealModel
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.glossary_service import extract_terms
from app.services.translation_service import TranslationService
from tests.translation_accuracy_utils import (
    ExpectedTermDef,
    TranslationTestCase,
    load_translation_test_cases,
    normalize_for_comparison,
)
from tests.translation_accuracy_utils import (
    term_present as _term_present,
)

# ---------------------------------------------------------------------------
# Shared mock helpers — DRY: one place for all mock construction
# ---------------------------------------------------------------------------


def _make_mock_m2m100_response(translated_text: str) -> MagicMock:
    """Build a mock httpx.Response for m2m100 success."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "success": True,
        "result": {"translated_text": translated_text},
        "errors": [],
    }
    return resp


def _make_mock_baml_client(terms: list[MagicMock] | None = None) -> MagicMock:
    """Build a mock BAML sync client with ExtractGlossaryTerms."""
    mock_b = MagicMock()
    mock_b.ExtractGlossaryTerms.return_value = terms or []
    return mock_b


def _make_glossary_term(
    term_en: str = "residence permit",
    term_de: str = "Aufenthaltstitel",
    term_fr: str = "titre de séjour",
    definition: str = "A legal authorization...",
) -> MagicMock:
    return MagicMock(term_en=term_en, term_de=term_de, term_fr=term_fr, definition=definition)


# Maps (source_lang, target_lang) → the GlossaryTerm field holding the target term.
_TARGET_FIELD: dict[tuple[str, str], str] = {
    ("en", "de"): "term_de",
    ("en", "fr"): "term_fr",
    ("de", "en"): "term_en",
    ("de", "fr"): "term_fr",
    ("fr", "en"): "term_en",
    ("fr", "de"): "term_de",
}


def _baml_mock_from_expected(
    expected_terms: list[ExpectedTermDef],
    source_lang: str,
    target_lang: str,
) -> MagicMock:
    """Build a BAML mock whose ExtractGlossaryTerms returns the case's expected terms.

    Shared by the always-run mock suite (so ``translate()``'s glossary enforcement
    applies the terms consistently across pages) and ``_check_glossary_enforcement``.
    """
    target_field = _TARGET_FIELD.get((source_lang, target_lang), "term_en")
    mock_terms = []
    for et in expected_terms:
        kwargs: dict[str, str] = {
            "term_en": "",
            "term_de": "",
            "term_fr": "",
            "definition": f"Expected translation of {et.source}",
        }
        kwargs[f"term_{source_lang}"] = et.source
        kwargs[target_field] = et.target
        mock_terms.append(_make_glossary_term(**kwargs))
    return _make_mock_baml_client(mock_terms)


# ---------------------------------------------------------------------------
# Reusable check functions — DRY: each check is a single function
# ---------------------------------------------------------------------------


def _check_terminology(
    translated_text: str,
    expected_terms: list[ExpectedTermDef],
    threshold: float,
) -> tuple[bool, float, list[str]]:
    """Check that expected glossary terms appear in the translated output.

    Returns (passed, score, failures).
    """
    if not expected_terms:
        return True, 1.0, []

    failures: list[str] = []
    hits = 0
    for term in expected_terms:
        if _term_present(term.target, translated_text):
            hits += 1
        else:
            failures.append(f"Expected '{term.target}' (from '{term.source}') not found in output")

    score = hits / len(expected_terms)
    passed = score >= threshold
    return passed, score, failures


def _check_no_forbidden_terms(
    translated_text: str,
    forbidden_terms: list[str],
) -> tuple[bool, list[str]]:
    """Check that none of the forbidden mistranslation terms appear."""
    violations: list[str] = []
    for ft in forbidden_terms:
        if _term_present(ft, translated_text):
            violations.append(f"Forbidden term '{ft}' found in output")
    return len(violations) == 0, violations


def _check_completeness(
    input_pages: list[dict[str, Any]],
    translated_pages: list[dict[str, Any]],
    threshold: float,
) -> tuple[bool, float, list[str]]:
    """Check that every input page has a corresponding translated page."""
    if not input_pages:
        return True, 1.0, []

    input_page_nums = {p.get("page", 0) for p in input_pages}
    translated_page_nums = {p.get("page", 0) for p in translated_pages}

    missing = input_page_nums - translated_page_nums
    score = len(input_page_nums - missing) / len(input_page_nums) if input_page_nums else 1.0
    passed = score >= threshold
    failures = [f"Missing translated page {p}" for p in sorted(missing)]
    return passed, score, failures


def _content_table_row_count(text: str) -> int:
    """Count table rows with values, excluding border/separator furniture."""
    rows = re.findall(r"^\s*\|.*\|\s*$", text, re.MULTILINE)
    return sum(
        not (re.fullmatch(r"[|:+\-–—_=.\s]+", row) and any(marker in row for marker in "-–—_="))
        for row in rows
    )


def _check_structural_preservation(
    input_pages: list[dict[str, Any]],
    translated_pages: list[dict[str, Any]],
    threshold: float,
) -> tuple[bool, float, list[str]]:
    """Check that structural markers (tables, form fields) survive translation.

    Detects content-bearing pipe-delimited rows, form underlines, and list
    markers. Decorative table borders are intentionally excluded because they
    are page furniture, not translatable content.
    """
    structural_markers = 0
    preserved = 0
    failures: list[str] = []

    for in_page in input_pages:
        text = str(in_page.get("text", ""))
        table_rows = _content_table_row_count(text)
        form_fields = len(re.findall(r"_{3,}", text))
        list_items = len(re.findall(r"^[\s]*[-•]\s", text, re.MULTILINE))

        total = table_rows + form_fields + list_items
        if total == 0:
            continue

        structural_markers += total

        page_num = in_page.get("page", 0)
        trans_page = next((p for p in translated_pages if p.get("page") == page_num), None)
        if trans_page is None:
            failures.append(f"Page {page_num}: missing entirely")
            continue

        trans_text = str(trans_page.get("text", ""))

        if table_rows > 0:
            trans_table_rows = _content_table_row_count(trans_text)
            preserved += min(trans_table_rows, table_rows)
            if trans_table_rows < table_rows:
                failures.append(f"Page {page_num}: table rows {trans_table_rows}/{table_rows}")

        if form_fields > 0:
            trans_fields = len(re.findall(r"_{3,}", trans_text))
            preserved += min(trans_fields, form_fields)
            if trans_fields < form_fields:
                failures.append(f"Page {page_num}: form fields {trans_fields}/{form_fields}")

        if list_items > 0:
            trans_items = len(re.findall(r"^[\s]*[-•]\s", trans_text, re.MULTILINE))
            preserved += min(trans_items, list_items)
            if trans_items < list_items:
                failures.append(f"Page {page_num}: list items {trans_items}/{list_items}")

    if structural_markers == 0:
        return True, 1.0, []

    score = preserved / structural_markers
    passed = score >= threshold
    return passed, score, failures


def _check_consistency(
    input_pages: list[dict[str, Any]],
    translated_pages: list[dict[str, Any]],
    expected_terms: list[ExpectedTermDef],
    threshold: float,
) -> tuple[bool, float, list[str]]:
    """Check that the same source term is translated consistently across pages.

    A source term is only checked on pages where it actually appears. The
    translated page must contain the expected target term in those cases.
    """
    if not expected_terms or len(translated_pages) <= 1:
        return True, 1.0, []

    failures: list[str] = []
    total_checks = 0
    consistent_checks = 0

    for term in expected_terms:
        source_hits = 0
        target_hits = 0

        for in_page, trans_page in zip(input_pages, translated_pages, strict=False):
            in_text = str(in_page.get("text", ""))
            trans_text = str(trans_page.get("text", ""))

            if not _term_present(term.source, in_text):
                continue

            source_hits += 1
            if _term_present(term.target, trans_text):
                target_hits += 1

        if source_hits < 2:
            continue

        total_checks += 1
        if target_hits == source_hits:
            consistent_checks += 1
        else:
            failures.append(
                f"'{term.source}': target '{term.target}' found on "
                f"{target_hits}/{source_hits} pages containing the source term"
            )

    if total_checks == 0:
        return True, 1.0, []

    score = consistent_checks / total_checks
    passed = score >= threshold
    return passed, score, failures


def _check_numeric_preservation(
    input_pages: list[dict[str, Any]],
    translated_pages: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Check that numeric values (amounts, percentages) are not altered."""
    failures: list[str] = []

    for in_page in input_pages:
        page_num = in_page.get("page", 0)
        text = str(in_page.get("text", ""))

        input_numbers = re.findall(r"\d[\d\s]*[\d%€$£]", text)
        if not input_numbers:
            continue

        trans_page = next((p for p in translated_pages if p.get("page") == page_num), None)
        if trans_page is None:
            failures.append(f"Page {page_num}: missing, cannot verify numbers")
            continue

        trans_text = str(trans_page.get("text", ""))
        for num in input_numbers:
            normalized = re.sub(r"\s+", " ", num.strip())
            if normalized not in trans_text:
                failures.append(f"Page {page_num}: number '{normalized}' missing in output")

    return len(failures) == 0, failures


def _run_suite_checks(
    tc: TranslationTestCase,
    input_pages: list[dict[str, Any]],
    translated_pages: list[dict[str, Any]],
) -> FindingResult:
    """Run all enabled checks for a test case and return a FindingResult.

    DRY: used by both the mock-based and real-model integration suites.
    """
    all_translated_text = " ".join(str(p.get("text", "")) for p in translated_pages)
    finding = FindingResult(test_id=tc.id, category=tc.category, passed=True)

    for check_name in tc.checks:
        if check_name == "terminology":
            passed, score, failures = _check_terminology(
                all_translated_text,
                tc.expected_terms,
                tc.quality_thresholds.term_accuracy,
            )
            finding.scores["term_accuracy"] = score
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        elif check_name == "no_forbidden_terms":
            passed, violations = _check_no_forbidden_terms(all_translated_text, tc.forbidden_terms)
            finding.scores["forbidden_terms"] = 1.0 if passed else 0.0
            if not passed:
                finding.passed = False
                finding.failures.extend(violations)

        elif check_name == "completeness":
            passed, score, failures = _check_completeness(
                input_pages,
                translated_pages,
                tc.quality_thresholds.completeness,
            )
            finding.scores["completeness"] = score
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        elif check_name == "structural_preservation":
            passed, score, failures = _check_structural_preservation(
                input_pages,
                translated_pages,
                tc.quality_thresholds.structural_pres,
            )
            finding.scores["structural_pres"] = score
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        elif check_name == "consistency":
            passed, score, failures = _check_consistency(
                input_pages,
                translated_pages,
                tc.expected_terms,
                tc.quality_thresholds.consistency,
            )
            finding.scores["consistency"] = score
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        elif check_name == "table_integrity":
            passed, score, failures = _check_structural_preservation(
                input_pages,
                translated_pages,
                tc.quality_thresholds.structural_pres,
            )
            finding.scores["table_integrity"] = score
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        elif check_name == "numeric_preservation":
            passed, failures = _check_numeric_preservation(input_pages, translated_pages)
            finding.scores["numeric_pres"] = 1.0 if passed else 0.0
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        elif check_name == "glossary_enforcement":
            input_text = " ".join(str(p.get("text", "")) for p in input_pages)
            passed, failures = _check_glossary_enforcement(
                input_text, tc.source_lang, tc.target_lang, tc.expected_terms
            )
            finding.scores["glossary_enforcement"] = 1.0 if passed else 0.0
            if not passed:
                finding.passed = False
                finding.failures.extend(failures)

        else:
            finding.passed = False
            finding.failures.append(
                f"Unknown check '{check_name}' — valid: terminology, no_forbidden_terms, "
                "completeness, structural_preservation, table_integrity, consistency, "
                "numeric_preservation, glossary_enforcement"
            )

    return finding


def _check_glossary_enforcement(
    input_text: str,
    source_lang: str,
    target_lang: str,
    expected_terms: list[ExpectedTermDef],
) -> tuple[bool, list[str]]:
    """Verify that glossary_service extracts the expected terms from source text."""
    failures: list[str] = []

    mock_baml = _baml_mock_from_expected(expected_terms, source_lang, target_lang)

    try:
        with patch("app.services.glossary_service._get_baml_client", return_value=mock_baml):
            extracted = extract_terms(input_text, source_lang)
    except (ValueError, RuntimeError) as exc:
        failures.append(f"Glossary extraction failed: {exc}")
        return False, failures

    for et in expected_terms:
        found = False
        for ext in extracted:
            ext_source = getattr(ext, f"term_{source_lang}", "")
            if ext_source.lower() == et.source.lower():
                found = True
                break
        if not found:
            failures.append(f"Glossary did not extract expected term '{et.source}'")

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# Findings report data model
# ---------------------------------------------------------------------------


@dataclass
class FindingResult:
    test_id: str
    category: str
    passed: bool
    scores: dict[str, float] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Load test cases once at module import time
# ---------------------------------------------------------------------------

try:
    _test_cases = load_translation_test_cases()
except FileNotFoundError as exc:
    pytest.skip(str(exc), allow_module_level=True)


# ---------------------------------------------------------------------------
# Mock-based translation accuracy tests (always run, fast)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def translation_service() -> TranslationService:
    """Shared TranslationService instance for all mock test cases."""
    return TranslationService()


def _case_id(tc: TranslationTestCase) -> str:
    return f"{tc.id}-{tc.category}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tc",
    _test_cases,
    ids=_case_id,
)
async def test_translation_accuracy(
    tc: TranslationTestCase,
    translation_service: TranslationService,
) -> None:
    """Run all enabled checks for a single YAML test case using mocked m2m100."""

    def _simulate_translation(source_text: str) -> str:
        """Apply each expected term's source→target substitution to the text."""
        out = source_text
        for et in tc.expected_terms:
            out = re.sub(re.escape(et.source), et.target, out, flags=re.IGNORECASE)
        return out

    async def fake_post(url: str, **kwargs: Any) -> MagicMock:
        # Translate the ACTUAL payload text rather than indexing by call order:
        # the Not Diamond routing layer issues its own POST per page on this same
        # mocked client, so call-order indexing mismatches pages → target terms.
        # The m2m100 payload carries the page text under "text"; other callers
        # (routing) omit it and receive a harmless empty translation.
        payload = kwargs.get("json") or {}
        source_text = str(payload.get("text", "")) if isinstance(payload, dict) else ""
        return _make_mock_m2m100_response(_simulate_translation(source_text))

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = fake_post

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        # Glossary enforcement inside translate() calls extract_terms() → BAML.
        # Mock the BAML client with THIS case's expected terms so the always-run
        # mock suite never reaches a live LLM (would flake on credits/auth —
        # 401/402 — in CI) AND so enforcement applies the terms consistently
        # across pages (required by multi_page_consistency cases, e.g. TC-024).
        patch(
            "app.services.glossary_service._get_baml_client",
            return_value=_baml_mock_from_expected(
                tc.expected_terms, tc.source_lang, tc.target_lang
            ),
        ),
    ):
        job = await translation_service.translate(
            document_id=f"test-{tc.id}",
            source_language=tc.source_lang,
            target_language=tc.target_lang,
            pages=tc.input_pages,
        )

    assert job.status == "done", f"Job failed: {job.error}"

    finding = _run_suite_checks(tc, tc.input_pages, job.translated_pages)

    if not finding.passed:
        failure_summary = "; ".join(finding.failures)
        score_summary = ", ".join(f"{k}={v:.2f}" for k, v in finding.scores.items())
        pytest.fail(f"{tc.id} ({tc.category}): FAILED — {failure_summary} [{score_summary}]")


def test_generate_findings_report() -> None:
    """Validate YAML structure and generate a findings report template."""
    cases = load_translation_test_cases()
    assert len(cases) == 30, f"Expected 30 test cases, got {len(cases)}"

    categories: dict[str, int] = {}
    for tc in cases:
        categories[tc.category] = categories.get(tc.category, 0) + 1

    expected_categories = {
        "legal_terminology",
        "administrative",
        "table_formatting",
        "compound_words",
        "false_friends",
        "multi_page_consistency",
        "glossary_enforcement",
    }
    actual_categories = set(categories.keys())
    missing = expected_categories - actual_categories
    assert not missing, f"Missing categories: {missing}"

    report_lines = [
        "# Translation Accuracy Findings Report",
        "",
        "**Generated:** 2026-06-19",
        f"**Test Cases:** {len(cases)}",
        f"**Categories:** {len(categories)}",
        "",
        "## Category Distribution",
        "",
    ]
    for cat, count in sorted(categories.items()):
        report_lines.append(f"- **{cat}**: {count} cases")
    report_lines.extend(
        [
            "",
            "## Quality Threshold Defaults",
            "",
            "| Metric | Default |",
            "|--------|---------|",
            "| term_accuracy | 0.80 |",
            "| structural_pres | 0.90 |",
            "| completeness | 0.95 |",
            "| consistency | 0.90 |",
            "",
            "## Per-Case Results",
            "",
            "| ID | Category | Checks | Thresholds | Status |",
            "|----|----------|--------|------------|--------|",
        ]
    )
    for tc in cases:
        checks_str = ", ".join(tc.checks)
        thresholds_str = ", ".join(f"{k}={v:.0%}" for k, v in vars(tc.quality_thresholds).items())
        report_lines.append(
            f"| {tc.id} | {tc.category} | {checks_str} | {thresholds_str} | ⏳ Pending |"
        )

    report_lines.extend(
        [
            "",
            "## Top Issues (to be filled after review)",
            "",
            "1. _[German legal terminology accuracy]_",
            "2. _[Table formatting in DE→EN translations]_",
            "3. _[Compound word decomposition quality]_",
            "",
            "---",
            "",
            "_Traceability: ADR-005 (Glossary & Terminology Management)_",
        ]
    )

    report_text = "\
".join(report_lines)
    assert "legal_terminology" in report_text
    assert "glossary_enforcement" in report_text


# ---------------------------------------------------------------------------
# Real-model integration tests (gated by TRANSLATION_INTEGRATION_TESTS)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("TRANSLATION_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="Real m2m100 integration tests require TRANSLATION_INTEGRATION_TESTS=true",
)
class TestTranslationAccuracyRealModel:
    """Run the same YAML cases against the live Cloudflare Workers AI m2m100 model.

    These tests exercise the full service stack, apply casefold-aware checks, and
    classify failures as service bugs, model limitations, or stale test cases.
    """

    @pytest.fixture(scope="session")
    async def real_translation_service(self) -> TranslationService:
        return TranslationService()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tc", _test_cases, ids=_case_id)
    async def test_real_model_translation(
        self,
        tc: TranslationTestCase,
        real_translation_service: TranslationService,
    ) -> None:
        delay_s = float(os.getenv("TRANSLATION_TEST_DELAY_S", "0.5"))

        try:
            translated_pages: list[dict[str, object]] = []
            for page in tc.input_pages:
                page_num = page.get("page", 0)
                text = str(page.get("text", "")).strip()
                if not text:
                    translated_pages.append({"page": page_num, "text": ""})
                    continue

                translated_text = await real_translation_service.translate_text(
                    text=text,
                    source_lang=tc.source_lang,
                    target_lang=tc.target_lang,
                )
                translated_pages.append({"page": page_num, "text": translated_text})

                if delay_s > 0:
                    await asyncio.sleep(delay_s)
        except Exception as exc:
            classification = self._classify_failure(tc, exc, "", [str(exc)])
            pytest.fail(f"{tc.id} ({tc.category}) FAILED — {classification}: {exc}")

        finding = _run_suite_checks(tc, tc.input_pages, translated_pages)

        if not finding.passed:
            all_translated_text = " ".join(str(p.get("text", "")) for p in translated_pages)
            classification = self._classify_failure(tc, None, all_translated_text, finding.failures)
            failure_summary = "; ".join(finding.failures)
            score_summary = ", ".join(f"{k}={v:.2f}" for k, v in finding.scores.items())
            pytest.fail(
                f"{tc.id} ({tc.category}): FAILED — {classification}: {failure_summary} "
                f"[{score_summary}]"
            )

    def _classify_failure(
        self,
        tc: TranslationTestCase,
        exception: Exception | None,
        translated_text: str,
        failures: list[str],
    ) -> str:
        """Classify a real-model failure for triage.

        SERVICE_BUG:     TranslationService raised or returned a failed job.
        TEST_CASE_STALE: Source term leaked into the output untranslated;
                         the expected target may be wrong or the input phrasing
                         may need updating.
        MODEL_LIMITATION: Translation was produced but expected/forbidden term
                          checks failed — likely a model quality issue.
        """
        if exception is not None:
            return "SERVICE_BUG"

        normalized_output = normalize_for_comparison(translated_text)
        for et in tc.expected_terms:
            normalized_source = normalize_for_comparison(et.source)
            if normalized_source and normalized_source in normalized_output:
                return "TEST_CASE_STALE"

        return "MODEL_LIMITATION"
