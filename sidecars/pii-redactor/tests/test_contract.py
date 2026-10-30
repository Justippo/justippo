"""Contract tests for the PII redaction sidecar HTTP API.

These tests verify the HTTP contract documented in the sidecar README:
- GET /health returns 200 with status/service/version
- POST /redact returns 200 with redacted_text/entity_count/entity_types
- POST /redact returns 400 on invalid input (empty text)
- POST /redact returns 422 on missing required fields

Run with: cd sidecars/pii-redactor && python -m pytest tests/ -v
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """GET /health contract."""

    def test_health_returns_200(self) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_required_fields(self) -> None:
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "pii-redactor"
        assert "version" in data


class TestRedactEndpoint:
    """POST /redact contract."""

    def test_redact_returns_200(self) -> None:
        resp = client.post(
            "/redact",
            json={"text": "Contact John Smith at john@example.com", "language": "en"},
        )
        assert resp.status_code == 200

    def test_redact_response_shape(self) -> None:
        resp = client.post(
            "/redact",
            json={"text": "Contact John Smith at john@example.com", "language": "en"},
        )
        data = resp.json()
        assert "redacted_text" in data
        assert "entity_count" in data
        assert "entity_types" in data
        assert "processing_time_ms" in data
        assert isinstance(data["entity_count"], int)
        assert isinstance(data["entity_types"], list)
        assert isinstance(data["processing_time_ms"], (int, float))

    def test_redact_replaces_person(self) -> None:
        resp = client.post(
            "/redact",
            json={"text": "John Smith signed the document", "language": "en"},
        )
        data = resp.json()
        # PERSON entity should be redacted
        assert "John Smith" not in data["redacted_text"]
        assert "[PERSON]" in data["redacted_text"]

    def test_redact_replaces_email(self) -> None:
        resp = client.post(
            "/redact",
            json={"text": "Email me at test@example.com", "language": "en"},
        )
        data = resp.json()
        assert "test@example.com" not in data["redacted_text"]

    def test_redact_empty_text_returns_400(self) -> None:
        resp = client.post("/redact", json={"text": "", "language": "en"})
        assert resp.status_code == 400

    def test_redact_missing_text_returns_400(self) -> None:
        """Missing required 'text' field returns 400 (custom validation handler)."""
        resp = client.post("/redact", json={"language": "en"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "INVALID_INPUT"

    def test_redact_default_language(self) -> None:
        """language field is optional — defaults to 'en'."""
        resp = client.post("/redact", json={"text": "John Smith was here"})
        assert resp.status_code == 200

    def test_redact_no_pii_returns_original(self) -> None:
        """Text without PII should be returned unchanged."""
        text = "The regulation applies to all member states."
        resp = client.post("/redact", json={"text": text, "language": "en"})
        data = resp.json()
        assert data["redacted_text"] == text
        assert data["entity_count"] == 0