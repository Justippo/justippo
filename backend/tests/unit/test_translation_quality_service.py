"""Tests for deterministic translation quality reporting."""

from app.services.translation_quality_service import build_translation_quality_report


def _page(source: str, translated: str) -> dict[str, object]:
    return {
        "page": 1,
        "text": translated,
        "status": "translated",
        "sections": [
            {
                "index": 0,
                "source_text": source,
                "translated_text": translated,
                "status": "translated",
                "attempts": 1,
                "error_code": None,
            }
        ],
    }


def test_quality_report_passes_preserved_references_and_names() -> None:
    report = build_translation_quality_report(
        [
            _page(
                "Anna Schmidt filed case 2026/14 on 17.07.2026.",
                "Anna Schmidt reichte Fall 2026/14 am 17.07.2026 ein.",
            )
        ],
        terminology_review_status="checked_no_changes",
    )

    assert report.status == "pass"
    assert report.terminology_review_status == "checked_no_changes"
    assert report.failed_section_count == 0
    assert all(check.status == "pass" for check in report.checks)


def test_quality_report_flags_leakage_and_missing_reference() -> None:
    report = build_translation_quality_report([_page("Reference 2026/14", "Reference 2026/14")])

    assert report.status == "review"
    assert (
        next(check for check in report.checks if check.code == "SOURCE_TEXT_LEAKAGE").status
        == "warning"
    )


def test_quality_report_flags_missing_numeric_token() -> None:
    report = build_translation_quality_report(
        [_page("Submit before 17.07.2026.", "Soumettre avant la date indiquée.")]
    )

    reference_check = next(
        check for check in report.checks if check.code == "REFERENCE_PRESERVATION"
    )
    assert reference_check.status == "warning"
    assert "17.07.2026" in reference_check.message


def test_quality_report_flags_empty_translation() -> None:
    report = build_translation_quality_report([_page("Required text", "")])

    empty_check = next(check for check in report.checks if check.code == "EMPTY_TRANSLATION")
    assert empty_check.status == "warning"
    assert report.translated_section_count == 0
