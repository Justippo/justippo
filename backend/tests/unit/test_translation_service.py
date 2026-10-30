"""
Unit tests for TranslationService (Sprint 2)

Coverage:
- translate() happy path — mocked CF Workers AI m2m100 response
- translate() with unsupported target language → status="failed"
- translate() with unsupported source language → status="failed"
- translate() with no pages → status="done", empty translated_pages
- translate() with empty page text → empty text passthrough
- translate() with CF Workers AI 500 → status="failed"
- translate() with CF Workers AI errors array → status="failed"
- get_job() returns correct job after translate()
- get_job() returns None for unknown job_id
- get_supported_language_pairs() returns all 6 EN/DE/FR pairs
- _call_m2m100 "auto" source defaults to "en"

All HTTP calls are mocked — no real network calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.translation_service import (
    TranslationService,
    _normalize_for_matching,
    _split_translation_sections,
    _term_appears,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _patch_not_diamond() -> patch:
    mock_nd = MagicMock()
    mock_nd.return_value.route = AsyncMock(return_value="@cf/meta/m2m100-1.2b")
    return patch(
        "app.integrations.routing.not_diamond.NotDiamondRouter",
        mock_nd,
    )


_MOCK_NOT_DIAMOND = _patch_not_diamond()


_PAGES_EN: list[dict[str, object]] = [
    {"page": 1, "text": "Hello world", "confidence": 0.98},
    {"page": 2, "text": "Second page content", "confidence": 0.95},
]

_M2M100_SUCCESS: dict[str, Any] = {
    "success": True,
    "result": {"translated_text": "Hallo Welt"},
    "errors": [],
}

_M2M100_SUCCESS_P2: dict[str, Any] = {
    "success": True,
    "result": {"translated_text": "Inhalt der zweiten Seite"},
    "errors": [],
}


def _mock_m2m100_response(payload: dict[str, Any]) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# translate() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolation: force Not Diamond + glossary extraction off regardless of any
    # local .env overrides, so this unit test never depends on live network
    # credentials/credits (mirrors the pattern already used by sibling tests
    # that patch app.services.translation_service.extract_terms below).
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "NOT_DIAMOND_ENABLED", False)

    svc = TranslationService()
    call_count = 0

    async def fake_post(url: str, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return _mock_m2m100_response(_M2M100_SUCCESS if call_count == 1 else _M2M100_SUCCESS_P2)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = fake_post

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        patch("app.services.translation_service.extract_terms", return_value=[]),
    ):
        job = await svc.translate(
            document_id="doc-001",
            source_language="en",
            target_language="de",
            pages=_PAGES_EN,
        )

    assert job.status == "done"
    assert job.error is None
    assert len(job.translated_pages) == 2
    assert job.translated_pages[0]["text"] == "Hallo Welt"
    assert job.translated_pages[1]["text"] == "Inhalt der zweiten Seite"
    assert job.translated_pages[0]["sections"] == [
        {
            "index": 0,
            "source_text": "Hello world",
            "translated_text": "Hallo Welt",
            "status": "translated",
            "attempts": 1,
            "error_code": None,
        }
    ]
    assert job.quality_report is not None
    assert job.quality_report.failed_section_count == 0
    assert job.quality_report.terminology_review_status == "checked_no_changes"
    assert job.glossary_terms_applied == 0
    assert call_count == 2


def test_split_translation_sections_preserves_paragraph_boundaries() -> None:
    text = "Heading\n\nFirst paragraph.\n\nSecond paragraph."
    assert _split_translation_sections(text) == [
        "Heading",
        "First paragraph.",
        "Second paragraph.",
    ]


def test_split_translation_sections_bounds_large_blocks() -> None:
    sections = _split_translation_sections("word " * 500, max_chars=120)
    assert len(sections) > 1
    assert all(len(section) <= 120 for section in sections)


def test_split_translation_sections_preserves_content_rows_and_ignores_table_borders() -> None:
    text = "| Requirement | Document |\n|---|---|\n| Permit | Passport |"
    assert _split_translation_sections(text) == [
        "| Requirement | Document |",
        "| Permit | Passport |",
    ]


def test_split_translation_sections_ignores_page_markers_without_dropping_other_numbers() -> None:
    text = "Seite 1\n\n- 1 -\n\n1\n\nReference 1"
    assert _split_translation_sections(text, page_number=1) == ["Reference 1"]
    assert _split_translation_sections("2", page_number=1) == ["2"]


@pytest.mark.asyncio
async def test_translate_preserves_form_rows_and_uses_neutral_canonical_cells() -> None:
    svc = TranslationService()
    translated_by_model = {
        "Raphaella Karen": "Raphaella Karen",
        "Ich bin Kundin/Kunde der Arbeitsvermittlung.": (
            "I am a customer of the employment agency."
        ),
        "Die Aussage trifft zu.": "The statement applies.",
    }

    async def translate_cell(text: str, *_args: object, **_kwargs: object) -> str:
        return translated_by_model[text]

    with (
        patch.object(svc, "_call_m2m100", side_effect=translate_cell) as mock_translate,
        patch("app.services.translation_service.extract_terms", return_value=[]),
    ):
        job = await svc.translate(
            document_id="doc-form-rows",
            source_language="de",
            target_language="en",
            pages=[
                {
                    "page": 1,
                    "text": (
                        "| --- | --- |\n\n"
                        "| Vorname | Raphaella Karen |\n\n"
                        "| Ich bin Kundin/Kunde der Arbeitsvermittlung. | Ja |\n\n"
                        "| Die Aussage trifft zu. | Nein |"
                    ),
                }
            ],
        )

    assert job.status == "done"
    sections = job.translated_pages[0]["sections"]
    assert isinstance(sections, list)
    assert [section["source_text"] for section in sections] == [
        "| Vorname | Raphaella Karen |",
        "| Ich bin Kundin/Kunde der Arbeitsvermittlung. | Ja |",
        "| Die Aussage trifft zu. | Nein |",
    ]
    assert [section["translated_text"] for section in sections] == [
        "| First name | Raphaella Karen |",
        "| I am a customer of the employment agency. | Yes |",
        "| The statement applies. | No |",
    ]
    assert [call.kwargs["text"] for call in mock_translate.call_args_list] == [
        "Raphaella Karen",
        "Ich bin Kundin/Kunde der Arbeitsvermittlung.",
        "Die Aussage trifft zu.",
    ]


@pytest.mark.asyncio
async def test_translate_reconstructs_generic_table_rows_instead_of_creating_prose() -> None:
    svc = TranslationService()
    translations = {
        "Anforderung": "Requirement",
        "Dokument": "Document",
    }

    async def translate_cell(text: str, *_args: object, **_kwargs: object) -> str:
        return translations[text]

    with (
        patch.object(svc, "_call_m2m100", side_effect=translate_cell),
        patch("app.services.translation_service.extract_terms", return_value=[]),
    ):
        job = await svc.translate(
            document_id="doc-table",
            source_language="de",
            target_language="en",
            pages=[{"page": 1, "text": "| Anforderung | Dokument |"}],
        )

    sections = job.translated_pages[0]["sections"]
    assert isinstance(sections, list)
    assert sections[0]["translated_text"] == "| Requirement | Document |"


@pytest.mark.asyncio
async def test_translate_keeps_sections_aligned_without_glossary_prompt_contamination() -> None:
    svc = TranslationService()
    source_sections = ["Heading", "First paragraph.", "Second paragraph."]

    async def translate_block(text: str, *_args: object, **_kwargs: object) -> str:
        return f"translated:{text}"

    with (
        patch.object(svc, "_call_m2m100", side_effect=translate_block) as mock_translate,
        patch("app.services.translation_service.extract_terms", return_value=[]),
    ):
        job = await svc.translate(
            document_id="doc-sections",
            source_language="de",
            target_language="en",
            pages=[{"page": 1, "text": "\n\n".join(source_sections)}],
            glossary_repo=object(),
        )

    sections = job.translated_pages[0]["sections"]
    assert isinstance(sections, list)
    assert [section["source_text"] for section in sections] == source_sections
    assert [section["translated_text"] for section in sections] == [
        f"translated:{section}" for section in source_sections
    ]
    assert all(
        "glossary" not in str(call.kwargs["text"]).lower() for call in mock_translate.call_args_list
    )


@pytest.mark.asyncio
async def test_translate_retries_only_failed_section() -> None:
    svc = TranslationService()
    attempts: dict[str, int] = {}

    async def translate_block(text: str, *_args: object, **_kwargs: object) -> str:
        attempts[text] = attempts.get(text, 0) + 1
        if text == "Retry me" and attempts[text] == 1:
            raise RuntimeError("temporary")
        return f"translated:{text}"

    with (
        patch.object(svc, "_call_m2m100", side_effect=translate_block),
        patch("app.services.translation_service.extract_terms", return_value=[]),
    ):
        job = await svc.translate(
            document_id="doc-retry",
            source_language="en",
            target_language="de",
            pages=[{"page": 1, "text": "Stable\n\nRetry me"}],
        )

    assert job.status == "done"
    assert attempts == {"Stable": 1, "Retry me": 2}
    sections = job.translated_pages[0]["sections"]
    assert isinstance(sections, list)
    assert sections[1]["attempts"] == 2
    assert sections[1]["status"] == "translated"


@pytest.mark.asyncio
async def test_translate_returns_partial_result_after_bounded_retries() -> None:
    svc = TranslationService()

    async def translate_block(text: str, *_args: object, **_kwargs: object) -> str:
        if text == "Always fails":
            raise RuntimeError("provider unavailable")
        return f"translated:{text}"

    with (
        patch.object(svc, "_call_m2m100", side_effect=translate_block),
        patch("app.services.translation_service.extract_terms", return_value=[]),
    ):
        job = await svc.translate(
            document_id="doc-partial",
            source_language="en",
            target_language="fr",
            pages=[{"page": 1, "text": "Stable\n\nAlways fails"}],
        )

    assert job.status == "partial"
    assert job.error == "1 translation sections require review after 2 attempts."
    sections = job.translated_pages[0]["sections"]
    assert isinstance(sections, list)
    assert sections[1] == {
        "index": 1,
        "source_text": "Always fails",
        "translated_text": "",
        "status": "failed",
        "attempts": 2,
        "error_code": "TRANSLATION_SECTION_FAILED",
    }
    assert job.quality_report is not None
    assert job.quality_report.status == "review"
    assert job.quality_report.failed_section_count == 1


# ---------------------------------------------------------------------------
# translate() — language validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_unsupported_target_language() -> None:
    svc = TranslationService()
    job = await svc.translate(
        document_id="doc-002",
        source_language="en",
        target_language="es",  # not supported in MVP
        pages=_PAGES_EN,
    )
    assert job.status == "failed"
    assert "es" in (job.error or "")


@pytest.mark.asyncio
async def test_translate_unsupported_source_language() -> None:
    svc = TranslationService()
    job = await svc.translate(
        document_id="doc-003",
        source_language="zh",  # not supported
        target_language="de",
        pages=_PAGES_EN,
    )
    assert job.status == "failed"
    assert "zh" in (job.error or "")


@pytest.mark.asyncio
async def test_translate_auto_source_language_is_accepted() -> None:
    """source_language='auto' should bypass source validation and succeed."""
    svc = TranslationService()

    mock_resp = _mock_m2m100_response(_M2M100_SUCCESS)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        patch("app.services.translation_service.extract_terms", return_value=[]),
        _MOCK_NOT_DIAMOND,
    ):
        job = await svc.translate(
            document_id="doc-auto",
            source_language="auto",
            target_language="de",
            pages=[{"page": 1, "text": "Hello"}],
        )

    assert job.status == "done"


# ---------------------------------------------------------------------------
# translate() — empty / None pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_no_pages_returns_done() -> None:
    svc = TranslationService()
    job = await svc.translate(
        document_id="doc-004",
        source_language="en",
        target_language="fr",
        pages=None,
    )
    assert job.status == "done"
    assert job.translated_pages == []
    assert job.error is None


@pytest.mark.asyncio
async def test_translate_empty_page_text_passthrough() -> None:
    """Pages with empty text should appear in output with empty string, no API call."""
    svc = TranslationService()
    pages = [{"page": 1, "text": "   "}]  # whitespace only

    with (
        patch("app.services.translation_service.httpx.AsyncClient") as mock_cls,
        _MOCK_NOT_DIAMOND,
    ):
        mock_cls.return_value.__aenter__ = AsyncMock()
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        job = await svc.translate(
            document_id="doc-005",
            source_language="en",
            target_language="de",
            pages=pages,
        )

    assert job.status == "done"
    assert job.translated_pages[0]["text"] == ""
    # No HTTP call should have been made for empty text
    mock_cls.return_value.__aenter__.return_value.post.assert_not_called()


# ---------------------------------------------------------------------------
# translate() — CF Workers AI error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_api_500_sets_failed() -> None:
    svc = TranslationService()

    error_resp = MagicMock(spec=httpx.Response)
    error_resp.status_code = 500
    error_resp.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=error_resp)

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        patch("app.services.translation_service.extract_terms", return_value=[]),
        _MOCK_NOT_DIAMOND,
    ):
        job = await svc.translate(
            document_id="doc-006",
            source_language="en",
            target_language="de",
            pages=[{"page": 1, "text": "Hello"}],
        )

    assert job.status == "failed"
    assert job.error == "All translation sections failed after 2 attempts."
    assert mock_client.post.await_count == 2


@pytest.mark.asyncio
async def test_translate_api_errors_array_sets_failed() -> None:
    svc = TranslationService()

    error_payload = {"success": False, "result": {}, "errors": [{"message": "quota exceeded"}]}
    mock_resp = _mock_m2m100_response(error_payload)
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        _MOCK_NOT_DIAMOND,
    ):
        job = await svc.translate(
            document_id="doc-007",
            source_language="en",
            target_language="de",
            pages=[{"page": 1, "text": "Hello"}],
        )

    assert job.status == "failed"
    assert job.error is not None


# ---------------------------------------------------------------------------
# get_job()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_returns_correct_job() -> None:
    svc = TranslationService()

    mock_resp = _mock_m2m100_response(_M2M100_SUCCESS)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        patch("app.services.translation_service.extract_terms", return_value=[]),
        _MOCK_NOT_DIAMOND,
    ):
        job = await svc.translate(
            document_id="doc-008",
            source_language="en",
            target_language="fr",
            pages=[{"page": 1, "text": "Hello"}],
        )

    retrieved = await svc.get_job(job.job_id)
    assert retrieved is not None
    assert retrieved.job_id == job.job_id
    assert retrieved.status == "done"


@pytest.mark.asyncio
async def test_get_job_unknown_id_returns_none() -> None:
    svc = TranslationService()
    result = await svc.get_job("non-existent-job-id")
    assert result is None


# ---------------------------------------------------------------------------
# get_supported_language_pairs()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supported_language_pairs_count() -> None:
    svc = TranslationService()
    pairs = await svc.get_supported_language_pairs()
    # 3 languages × 2 directions = 6 pairs
    assert len(pairs) == 6
    langs = {p["source"] for p in pairs} | {p["target"] for p in pairs}
    assert langs == {"en", "de", "fr"}


@pytest.mark.asyncio
async def test_supported_language_pairs_no_self_pairs() -> None:
    svc = TranslationService()
    pairs = await svc.get_supported_language_pairs()
    for pair in pairs:
        assert pair["source"] != pair["target"]


# ---------------------------------------------------------------------------
# _call_m2m100 — auto source defaults to "en"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_m2m100_auto_source_defaults_to_en(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolation: force Not Diamond off regardless of any local .env overrides —
    # this unit test must never make a real routing API call. See
    # test_translate_happy_path above for the same rationale.
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "NOT_DIAMOND_ENABLED", False)

    svc = TranslationService()
    captured: list[dict[str, object]] = []

    async def fake_post(url: str, json: dict[str, object], **kwargs: Any) -> MagicMock:
        captured.append(json)
        return _mock_m2m100_response(_M2M100_SUCCESS)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = fake_post

    with patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client):
        await svc._call_m2m100(text="Hello", source_lang="auto", target_lang="de")

    assert len(captured) == 1
    # "auto" maps to "en" ISO code per Cloudflare Workers AI schema
    assert captured[0]["source_lang"] == "en"


# ---------------------------------------------------------------------------
# _call_m2m100 — unexpected result shape raises TranslationError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_m2m100_unexpected_result_shape_raises() -> None:
    """When CF Workers AI returns result that is not a dict, raise TranslationError."""
    from app.services.translation_service import TranslationError

    svc = TranslationService()

    bad_payload = {"success": True, "result": "not-a-dict", "errors": []}
    mock_resp = _mock_m2m100_response(bad_payload)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(TranslationError, match="Unexpected CF Workers AI response shape"),
    ):
        await svc._call_m2m100(text="Hello", source_lang="en", target_lang="de")


# ---------------------------------------------------------------------------
# Glossary enforcement - post-editing replacement
# ---------------------------------------------------------------------------


def _make_glossary_term(
    term_en: str,
    term_de: str,
    term_fr: str,
    mistranslations: list[str] | None = None,
) -> MagicMock:
    return MagicMock(
        term_en=term_en,
        term_de=term_de,
        term_fr=term_fr,
        mistranslations=mistranslations,
    )


def test_normalize_for_matching_casefolds_and_strips_punctuation() -> None:
    assert _normalize_for_matching("Aufenthaltstitel!") == "aufenthaltstitel"
    assert _normalize_for_matching("C.E. 2003/109/CE") == "ce 2003 109 ce"


def test_term_appears_word_boundary() -> None:
    assert _term_appears("act", "We must act now.") is True
    assert _term_appears("act", "The contract is valid.") is False
    assert _term_appears("residence permit", "The residence permit is valid.") is True


@pytest.mark.asyncio
async def test_glossary_enforcement_replaces_mistranslation() -> None:
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The applicant needs a residence permit."}]
    translated_pages = [
        {"page": 1, "text": "Der Antragsteller benötigt einen Aufenthaltserlaubnis."}
    ]
    mock_term = _make_glossary_term(
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
        mistranslations=["Aufenthaltserlaubnis"],
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result[0]["text"] == "Der Antragsteller benötigt einen Aufenthaltstitel."


def test_glossary_enforcement_reports_applied_term_count() -> None:
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The applicant needs a residence permit."}]
    translated_pages = [
        {"page": 1, "text": "Der Antragsteller benötigt einen Aufenthaltserlaubnis."}
    ]
    mock_term = _make_glossary_term(
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
        mistranslations=["Aufenthaltserlaubnis"],
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement_result(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result.terms_applied == 1
    assert result.checked is True


@pytest.mark.asyncio
async def test_glossary_enforcement_preserves_structured_sections() -> None:
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The applicant needs a residence permit."}]
    translated_pages = [
        {
            "page": 1,
            "text": "Der Antragsteller benötigt einen Aufenthaltserlaubnis.",
            "sections": [
                {
                    "index": 0,
                    "source_text": "The applicant needs a residence permit.",
                    "translated_text": "Der Antragsteller benötigt einen Aufenthaltserlaubnis.",
                }
            ],
        }
    ]
    mock_term = _make_glossary_term(
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
        mistranslations=["Aufenthaltserlaubnis"],
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    sections = result[0]["sections"]
    assert isinstance(sections, list)
    assert sections[0]["translated_text"] == "Der Antragsteller benötigt einen Aufenthaltstitel."
    assert result[0]["text"] == sections[0]["translated_text"]


@pytest.mark.asyncio
async def test_glossary_enforcement_skips_when_source_term_absent() -> None:
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The applicant needs a work permit."}]
    translated_pages = [{"page": 1, "text": "Der Antragsteller benötigt eine Arbeitserlaubnis."}]
    mock_term = _make_glossary_term(
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
        mistranslations=["Aufenthaltserlaubnis"],
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result[0]["text"] == "Der Antragsteller benötigt eine Arbeitserlaubnis."


@pytest.mark.asyncio
async def test_glossary_enforcement_extraction_failure_is_non_fatal() -> None:
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The residence permit is valid."}]
    translated_pages = [{"page": 1, "text": "Der Aufenthaltstitel ist gültig."}]

    with patch(
        "app.services.translation_service.extract_terms",
        side_effect=RuntimeError("BAML unavailable"),
    ):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result[0]["text"] == "Der Aufenthaltstitel ist gültig."


@pytest.mark.asyncio
async def test_glossary_enforcement_leaves_correct_translation_unchanged() -> None:
    """If the canonical target term is already present, do not post-edit."""
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The residence permit is valid."}]
    translated_pages = [{"page": 1, "text": "Der Aufenthaltstitel ist gültig."}]
    mock_term = _make_glossary_term(
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
        mistranslations=["Aufenthaltserlaubnis"],
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result[0]["text"] == "Der Aufenthaltstitel ist gültig."


@pytest.mark.asyncio
async def test_glossary_enforcement_replaces_source_term_leakage() -> None:
    """Fallback path: source term leaked untranslated into target text."""
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "The residence permit is valid."}]
    translated_pages = [{"page": 1, "text": "Der residence permit ist gültig."}]
    mock_term = _make_glossary_term(
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result[0]["text"] == "Der Aufenthaltstitel ist gültig."


@pytest.mark.asyncio
async def test_glossary_enforcement_multi_word_mistranslation_replacement() -> None:
    svc = TranslationService()
    input_pages = [{"page": 1, "text": "Please show your identity card."}]
    translated_pages = [{"page": 1, "text": "Bitte zeigen Sie Ihren Personalausweis."}]
    mock_term = _make_glossary_term(
        term_en="identity card",
        term_de="Identitätskarte",
        term_fr="carte d'identité",
        mistranslations=["Personalausweis"],
    )

    with patch("app.services.translation_service.extract_terms", return_value=[mock_term]):
        result = svc._apply_glossary_enforcement(
            input_pages,
            translated_pages,
            source_lang="en",
            target_lang="de",
        )

    assert result[0]["text"] == "Bitte zeigen Sie Ihren Identitätskarte."


@pytest.mark.asyncio
async def test_translate_empty_page_text() -> None:
    svc = TranslationService()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client),
        _MOCK_NOT_DIAMOND,
    ):
        job = await svc.translate(
            document_id="doc-empty",
            source_language="en",
            target_language="de",
            pages=[{"page": 1, "text": "   "}],
        )

    assert job.status == "done"
    assert len(job.translated_pages) == 1
    assert job.translated_pages[0]["page"] == 1
    assert job.translated_pages[0]["text"] == ""
    # Ensure no network call was made
    mock_client.post.assert_not_called()
