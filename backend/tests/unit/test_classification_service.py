"""Unit tests for propella document classification service."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import documents
from app.main import app
from app.services import classification_service as svc
from app.services.classification_service import DocumentClassification
from app.services.ocr_service import OCRPage


class _Resp:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]


def _mock_client(response: object) -> AsyncMock:
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(side_effect=response if isinstance(response, Exception) else None)
    if not isinstance(response, Exception):
        client.post.return_value = response
    return client


@pytest.mark.asyncio
async def test_enabled_mock_propella_response_maps_fields() -> None:
    raw = {
        "content_type": ["legal_document", "transactional"],
        "language_code": "de",
        "content_quality": "good",
        "regional_relevance": ["european"],
        "country_relevance": ["Germany"],
        "content_safety": "safe",
        "pii_presence": "contains_pii",
        "confidence": 0.91,
    }
    mock_client = _mock_client(_Resp({"choices": [{"message": {"content": json.dumps(raw)}}]}))
    with (
        patch.object(svc.settings, "PROPELLA_ENABLED", True, create=True),
        patch.object(svc.settings, "PROPELLA_BASE_URL", "http://propella:8700", create=True),
        patch("app.services.classification_service.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await svc.classify_document("Dies ist eine Bescheinigung.", "application/pdf")
    assert result.document_type == "legal_document"
    assert result.language_code == "de"
    assert result.quality_score == 0.85
    assert result.geographic_relevance == ["Germany", "european"]
    assert result.safety_flags == ["contains_pii"]
    assert result.confidence == 0.91


@pytest.mark.asyncio
async def test_disabled_returns_sensible_default_no_crash() -> None:
    with patch.object(svc.settings, "PROPELLA_ENABLED", False, create=True):
        result = await svc.classify_document("Der Antrag und die Bescheinigung", "application/pdf")
    assert result.document_type == "unknown"
    assert result.language_code == "de"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_sidecar_timeout_returns_fallback_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_client = _mock_client(httpx.TimeoutException("slow"))
    with (
        patch.object(svc.settings, "PROPELLA_ENABLED", True, create=True),
        patch.object(svc.settings, "PROPELLA_BASE_URL", "http://propella:8700", create=True),
        patch("app.services.classification_service.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level("WARNING"),
    ):
        result = await svc.classify_document("The certificate application", "application/pdf")
    assert result.language_code == "en"
    assert "propella classification failed" in caplog.text


@pytest.mark.asyncio
async def test_sidecar_non_dict_response_raises_and_falls_back() -> None:
    # Real edge case: propella returns a JSON *array* (not an object). The
    # "choices" key is absent, so data becomes the raw list, and the
    # isinstance(data, dict) guard at classification_service.py:403-404 must
    # raise ValueError -> safe fallback (no crash).
    mock_client = _mock_client(_Resp(["not", "an", "object"]))
    with (
        patch.object(svc.settings, "PROPELLA_ENABLED", True, create=True),
        patch.object(svc.settings, "PROPELLA_BASE_URL", "http://propella:8700", create=True),
        patch("app.services.classification_service.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await svc.classify_document("Le certificat de séjour", "application/pdf")
    assert result.document_type == "unknown"
    assert result.language_code == "fr"


@pytest.mark.asyncio
async def test_local_sidecar_url_bypasses_gateway() -> None:
    mock_client = _mock_client(_Resp({"document_type": "reference", "language": "en"}))
    with (
        patch.object(svc.settings, "PROPELLA_ENABLED", True, create=True),
        patch.object(svc.settings, "PROPELLA_BASE_URL", "http://local:8700", create=True),
        patch("app.services.classification_service.get_gateway_url") as gateway,
        patch("app.services.classification_service.httpx.AsyncClient", return_value=mock_client),
    ):
        await svc.classify_document("The certificate application", "application/pdf")
    gateway.assert_not_called()
    mock_client.post.assert_awaited_once()
    assert mock_client.post.await_args.kwargs["headers"] == {}


@pytest.mark.asyncio
async def test_gateway_used_when_no_local_base_url() -> None:
    mock_client = _mock_client(_Resp({"document_type": "reference", "language": "en"}))
    with (
        patch.object(svc.settings, "PROPELLA_ENABLED", True, create=True),
        patch.object(svc.settings, "PROPELLA_BASE_URL", "", create=True),
        patch(
            "app.services.classification_service.get_gateway_url", return_value="https://gateway"
        ) as gateway,
        patch(
            "app.services.classification_service.get_gateway_auth_headers",
            return_value={"Authorization": "Bearer x"},
        ),
        patch("app.services.classification_service.httpx.AsyncClient", return_value=mock_client),
    ):
        await svc.classify_document("The certificate application", "application/pdf")
    gateway.assert_called_once()
    assert mock_client.post.await_args.args[0] == "https://gateway"
    assert mock_client.post.await_args.kwargs["headers"] == {"Authorization": "Bearer x"}


@pytest.mark.parametrize(
    "text, expected_lang, expected_quality",
    [
        ("Ein Antrag auf Aufenthalt", "de", 0.2),
        ("Der schnelle braune Fuchs " * 10 + "aufenthalt", "de", 0.5),
        ("Une attestation pour le titre de séjour avec les documents", "fr", 0.2),
        ("Le chat " * 15 + "séjour", "fr", 0.5),
        ("The certificate application", "en", 0.2),
        ("The quick brown fox " * 10 + "application", "en", 0.5),
        ("Just some random gibberish xyz abc", "und", 0.2),
        ("Lorem ipsum dolor sit amet " * 10, "und", 0.5),
    ],
)
def test_default_language_fallback(text: str, expected_lang: str, expected_quality: float) -> None:
    result = svc.default_classification(text)
    assert result.language_code == expected_lang
    assert result.quality_score == expected_quality


@pytest.mark.asyncio
async def test_upload_continues_and_stores_classification_metadata() -> None:
    rag = AsyncMock()
    classification = DocumentClassification(
        document_type="legal_document",
        language_code="de",
        quality_score=0.85,
        geographic_relevance=["european"],
        safety_flags=["contains_pii"],
        confidence=0.9,
    )
    documents._rag = rag
    try:
        with (
            patch("app.api.v1.endpoints.documents._ocr.process", new_callable=AsyncMock) as ocr,
            patch(
                "app.api.v1.endpoints.documents.classify_document", new_callable=AsyncMock
            ) as classify,
        ):
            ocr.return_value = [OCRPage(page=1, text="Deutscher Antrag", confidence=0.9)]
            classify.return_value = classification
            response = TestClient(app, headers={"X-GDPR-Consent": "test-token"}).post(
                "/api/v1/documents/",
                data={"target_lang": "de"},
                files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            )
    finally:
        documents._rag = None
    assert response.status_code == 200, response.text
    assert response.json()["classification"]["document_type"] == "legal_document"
    rag.ingest_document.assert_awaited_once()
    metadata = rag.ingest_document.await_args.kwargs["metadata"]
    assert metadata["doc_type"] == "legal_document"
    assert metadata["lang_code"] == "de"
    assert metadata["safety_flags"] == ["contains_pii"]
