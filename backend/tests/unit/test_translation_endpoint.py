from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.translate import router
from app.models.document_explanation import DocumentExplanation
from app.services.translation_service import TranslationJob


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/translate")
    return app


def _make_job(**overrides) -> TranslationJob:
    defaults = dict(
        job_id="job-1",
        document_id="550e8400-e29b-41d4-a716-446655440000",
        source_language="de",
        target_language="en",
        status="done",
        glossary_terms_applied=1,
        translated_pages=[
            {
                "page": 1,
                "text": "residence permit",
                "sections": [
                    {
                        "index": 0,
                        "source_text": "Aufenthaltstitel",
                        "translated_text": "residence permit",
                    }
                ],
            }
        ],
    )
    defaults.update(overrides)
    return TranslationJob(**defaults)


def test_translate_document_wires_glossary_repo() -> None:
    app = _make_app()
    job = TranslationJob(
        job_id="job-1",
        document_id="550e8400-e29b-41d4-a716-446655440000",
        source_language="de",
        target_language="en",
        status="done",
        glossary_terms_applied=1,
        translated_pages=[
            {
                "page": 1,
                "text": "residence permit",
                "sections": [
                    {
                        "index": 0,
                        "source_text": "Aufenthaltstitel",
                        "translated_text": "residence permit",
                    }
                ],
            }
        ],
    )
    mock_svc = MagicMock()
    mock_svc.translate = AsyncMock(return_value=job)

    with patch("app.api.v1.endpoints.translate._svc", mock_svc), TestClient(app) as client:
        response = client.post(
            "/api/v1/translate/",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_language": "de",
                "target_language": "en",
                "pages": [{"page": 1, "text": "Aufenthaltstitel"}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["translated_pages"][0]["text"] == "residence permit"
    assert payload["glossary_terms_applied"] == 1
    assert payload["translated_pages"][0]["sections"][0] == {
        "index": 0,
        "source_text": "Aufenthaltstitel",
        "translated_text": "residence permit",
        "status": "translated",
        "attempts": 1,
        "error_code": None,
    }
    _, kwargs = mock_svc.translate.await_args
    assert kwargs["document_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert kwargs["source_language"] == "de"
    assert kwargs["target_language"] == "en"
    assert kwargs["glossary_repo"] is not None


def test_translate_document_refreshes_explanation_in_target_language() -> None:
    app = _make_app()
    job = TranslationJob(
        job_id="job-2",
        document_id="550e8400-e29b-41d4-a716-446655440000",
        source_language="de",
        target_language="fr",
        status="done",
        translated_pages=[],
    )
    explanation = DocumentExplanation(
        document_type="residence_permit",
        language="fr",
        requirements=[],
        legal_context_status="unavailable",
        citations=[],
        warnings=[],
    )
    mock_svc = MagicMock()
    mock_svc.translate = AsyncMock(return_value=job)

    with (
        patch("app.api.v1.endpoints.translate._svc", mock_svc),
        patch(
            "app.api.v1.endpoints.translate.explain_document",
            new_callable=AsyncMock,
            return_value=explanation,
        ) as mock_explain,
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/translate/",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_language": "de",
                "target_language": "fr",
                "pages": [{"page": 1, "text": "Aufenthaltstitel"}],
                "classification": {
                    "document_type": "residence_permit",
                    "language_code": "de",
                },
                "include_document_explanation": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["document_explanation"]["language"] == "fr"
    assert mock_explain.await_args.kwargs["language"] == "fr"


def test_translate_response_includes_redaction_metadata_when_present() -> None:
    """API response must include redaction_metadata when the job has it."""
    app = _make_app()
    job = _make_job(
        redaction_metadata={
            "enabled": True,
            "total_entities": 3,
            "entity_types": ["PERSON", "EMAIL_ADDRESS", "DATE_TIME"],
            "succeeded": True,
        }
    )
    mock_svc = MagicMock()
    mock_svc.translate = AsyncMock(return_value=job)

    with (
        patch("app.api.v1.endpoints.translate._svc", mock_svc),
        patch("app.api.v1.endpoints.translate.AuditService") as mock_audit_cls,
        TestClient(app) as client,
    ):
        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock(return_value=None)
        mock_audit_cls.return_value = mock_audit

        response = client.post(
            "/api/v1/translate/",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_language": "en",
                "target_language": "de",
                "pages": [{"page": 1, "text": "John Smith signed."}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["redaction_metadata"] is not None
    assert payload["redaction_metadata"]["enabled"] is True
    assert payload["redaction_metadata"]["total_entities"] == 3
    assert "PERSON" in payload["redaction_metadata"]["entity_types"]
    assert payload["redaction_metadata"]["succeeded"] is True


def test_translate_response_redaction_metadata_null_when_disabled() -> None:
    """API response must have redaction_metadata with enabled=False when disabled."""
    app = _make_app()
    job = _make_job(
        redaction_metadata={
            "enabled": False,
            "total_entities": 0,
            "entity_types": [],
            "succeeded": True,
        }
    )
    mock_svc = MagicMock()
    mock_svc.translate = AsyncMock(return_value=job)

    with (
        patch("app.api.v1.endpoints.translate._svc", mock_svc),
        patch("app.api.v1.endpoints.translate.AuditService") as mock_audit_cls,
        TestClient(app) as client,
    ):
        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock(return_value=None)
        mock_audit_cls.return_value = mock_audit

        response = client.post(
            "/api/v1/translate/",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_language": "en",
                "target_language": "de",
                "pages": [{"page": 1, "text": "Hello world."}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    mock_audit.log_event.assert_not_called()
    assert payload["redaction_metadata"] is not None
    assert payload["redaction_metadata"]["enabled"] is False


def test_translate_calls_audit_log_when_redaction_enabled() -> None:
    """When redaction_metadata.enabled=True, AuditService.log_event must be called."""
    app = _make_app()
    job = _make_job(
        redaction_metadata={
            "enabled": True,
            "total_entities": 2,
            "entity_types": ["PERSON", "IBAN_CODE"],
            "succeeded": True,
        }
    )
    mock_svc = MagicMock()
    mock_svc.translate = AsyncMock(return_value=job)

    with (
        patch("app.api.v1.endpoints.translate._svc", mock_svc),
        patch("app.api.v1.endpoints.translate.AuditService") as mock_audit_cls,
        TestClient(app) as client,
    ):
        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock(return_value=None)
        mock_audit_cls.return_value = mock_audit

        response = client.post(
            "/api/v1/translate/",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_language": "en",
                "target_language": "de",
                "pages": [{"page": 1, "text": "John Smith IBAN DE89370400440532013000."}],
            },
            headers={"X-User-Id": "@alice:matrix.org"},
        )

    assert response.status_code == 200
    mock_audit.log_event.assert_called_once()
    _, kwargs = mock_audit.log_event.call_args
    assert kwargs["action"].value == "translation.redacted"
    assert kwargs["resource_type"] == "document"
    assert kwargs["resource_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert kwargs["actor_id"] == "@alice:matrix.org"
    metadata = kwargs["metadata"]
    assert metadata["entity_count"] == 2
    assert "PERSON" in metadata["entity_types"]
    assert "IBAN_CODE" in metadata["entity_types"]
    assert metadata["succeeded"] is True
