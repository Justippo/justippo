"""
Unit Tests — Health Endpoints

Tests that the /health and /api/v1/health/ready endpoints return
the correct shape and status codes.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_check_returns_200(client: TestClient) -> None:
    """Root health endpoint must return 200 with status=ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_readiness_check_returns_200(client: TestClient) -> None:
    """Readiness endpoint must return 200 (even as not_implemented skeleton)."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "dependencies" in data
