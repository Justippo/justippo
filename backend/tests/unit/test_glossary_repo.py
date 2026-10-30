from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.glossary_repo import GlossaryRepo


def _make_row() -> dict[str, object]:
    return {
        "id": "term-1",
        "term_en": "residence permit",
        "term_de": "Aufenthaltstitel",
        "term_fr": "titre de séjour",
        "mistranslations": '["Aufenthaltserlaubnis"]',
        "definition": "A legal authorization to reside in a country.",
        "source_doc_id": "doc-1",
        "source_lang": "en",
        "confidence": 0.92,
        "created_at": "2026-06-19T00:00:00+00:00",
        "updated_at": "2026-06-19T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_upsert_terms_serializes_and_executes() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=True)
    repo = GlossaryRepo(db)

    result = await repo.upsert_terms(
        [
            {
                "term_en": "residence permit",
                "term_de": "Aufenthaltstitel",
                "term_fr": "titre de séjour",
                "mistranslations": ["Aufenthaltserlaubnis"],
                "definition": "A legal authorization to reside in a country.",
                "confidence": 0.92,
            }
        ],
        doc_id="doc-1",
        lang="en",
    )

    assert len(result) == 1
    assert db.execute.await_count == 1
    sql, params = db.execute.await_args.args
    assert "INSERT OR REPLACE INTO glossary_terms" in sql
    assert params[1] == "residence permit"
    assert params[4] == '["Aufenthaltserlaubnis"]'
    assert params[6] == "doc-1"
    assert params[7] == "en"


@pytest.mark.asyncio
async def test_search_terms_uses_language_filter() -> None:
    db = MagicMock()
    db.fetch_all = AsyncMock(return_value=[_make_row()])
    repo = GlossaryRepo(db)

    result = await repo.search_terms("permit", lang="en")

    assert len(result) == 1
    assert result[0].term_de == "Aufenthaltstitel"
    sql, params = db.fetch_all.await_args.args
    assert "LOWER(term_en) LIKE ?" in sql
    assert params == ["%permit%"]


@pytest.mark.asyncio
async def test_get_all_terms_returns_records() -> None:
    db = MagicMock()
    db.fetch_all = AsyncMock(return_value=[_make_row()])
    repo = GlossaryRepo(db)

    result = await repo.get_all_terms(lang=None)

    assert len(result) == 1
    assert result[0].term_fr == "titre de séjour"
