from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.glossary import GlossaryTermRecord

GDPR_HEADERS = {"X-GDPR-Consent": "test-token"}


def _make_record() -> GlossaryTermRecord:
    return GlossaryTermRecord(
        id="term-1",
        term_en="residence permit",
        term_de="Aufenthaltstitel",
        term_fr="titre de séjour",
        mistranslations='["Aufenthaltserlaubnis"]',
        definition="A legal authorization to reside in a country.",
        source_doc_id="doc-1",
        source_lang="en",
        confidence=0.92,
        created_at="2026-06-19T00:00:00+00:00",
        updated_at="2026-06-19T00:00:00+00:00",
    )


def test_lookup_glossary_returns_terms() -> None:
    client = TestClient(app)
    record = _make_record()

    with patch(
        "app.repositories.glossary_repo.GlossaryRepo.get_all_terms",
        new=AsyncMock(return_value=[record]),
    ):
        response = client.get("/api/v1/glossary", headers=GDPR_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["domain"] == "legal"
    assert body["count"] == 1
    assert body["terms"][0]["term_en"] == "residence permit"


def test_lookup_glossary_searches_when_query_present() -> None:
    client = TestClient(app)
    record = _make_record()

    with patch(
        "app.repositories.glossary_repo.GlossaryRepo.search_terms",
        new=AsyncMock(return_value=[record]),
    ):
        response = client.get(
            "/api/v1/glossary?q=permit&source=en&target=de",
            headers=GDPR_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "permit"
    assert body["source"] == "en"
    assert body["target"] == "de"
    assert body["count"] == 1


def test_lookup_glossary_rejects_unknown_domain() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/glossary?domain=medical", headers=GDPR_HEADERS)

    assert response.status_code == 422


def test_search_glossary_route_uses_query() -> None:
    client = TestClient(app)
    record = _make_record()

    with patch(
        "app.repositories.glossary_repo.GlossaryRepo.search_terms",
        new=AsyncMock(return_value=[record]),
    ):
        response = client.get("/api/v1/glossary/search?q=permit&source=en", headers=GDPR_HEADERS)

    assert response.status_code == 200
    assert response.json()["query"] == "permit"


def test_extract_glossary_route_persists_terms() -> None:
    client = TestClient(app)
    extracted = [
        type(
            "Term",
            (),
            {
                "term_en": "residence permit",
                "term_de": "Aufenthaltstitel",
                "term_fr": "titre de séjour",
                "definition": "A legal authorization to reside in a country.",
                "confidence": 1.0,
            },
        )()
    ]

    with (
        patch("app.api.v1.endpoints.glossary.extract_terms", return_value=extracted),
        patch(
            "app.api.v1.endpoints.glossary.insert_terms",
            new=AsyncMock(return_value=[{"id": "seed-1"}]),
        ),
    ):
        response = client.post(
            "/api/v1/glossary/extract",
            headers=GDPR_HEADERS,
            json={
                "text": "Applicants need a residence permit.",
                "source_lang": "en",
                "doc_id": "doc-1",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_count"] == 1
    assert body["persisted_count"] == 1
    assert body["terms"][0]["term_en"] == "residence permit"
