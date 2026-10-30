# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Matrix health endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def test_matrix_health_endpoint_requires_feature_flag(client):
    """When ENABLE_MATRIX_EXCHANGE is False, the health endpoint returns 403."""
    with patch("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", False):
        response = client.get("/api/v1/exchange/health")
        assert response.status_code == 403


def test_matrix_health_endpoint_success(client):
    """When Matrix is healthy, return health status."""
    with (
        patch("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True),
        patch("app.api.v1.endpoints.exchange.MatrixClient") as mock_client_class,
    ):
        mock_client = MagicMock()
        mock_client.check_health = AsyncMock(
            return_value={
                "status": "healthy",
                "server_version": "v1.0",
                "connectivity": "ok",
            }
        )
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        response = client.get("/api/v1/exchange/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["matrix"]["status"] == "healthy"


def test_matrix_health_endpoint_configuration_error(client):
    """When Matrix is misconfigured, return degraded status."""
    with (
        patch("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True),
        patch("app.api.v1.endpoints.exchange.MatrixClient") as mock_client_class,
    ):
        from app.integrations.matrix.client import MatrixConfigurationError

        mock_client_class.side_effect = MatrixConfigurationError("token missing")

        response = client.get("/api/v1/exchange/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["matrix"]["error"] == "configuration_error"


def test_matrix_health_endpoint_timeout(client):
    """When Matrix times out, return degraded status."""
    with (
        patch("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True),
        patch("app.api.v1.endpoints.exchange.MatrixClient") as mock_client_class,
    ):
        from app.integrations.matrix.client import MatrixTimeoutError

        mock_client_class.side_effect = MatrixTimeoutError("timeout", operation="health_check")

        response = client.get("/api/v1/exchange/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["matrix"]["error"] == "timeout"


def test_matrix_health_endpoint_configuration_error_via_mock(client):
    """When MatrixClient mock throws Exception, return unhealthy status."""
    with (
        patch("app.core.config.settings.ENABLE_MATRIX_EXCHANGE", True),
        patch("app.api.v1.endpoints.exchange.MatrixClient") as mock_client_class,
    ):
        mock_client_class.side_effect = Exception("unexpected error")

        response = client.get("/api/v1/exchange/health")
        assert response.status_code == 200
        data = response.json()
        # Generic Exception is caught by the except Exception handler, returning
        # "unhealthy" status. Only MatrixConfigurationError returns "degraded".
        assert data["status"] == "unhealthy"
        assert data["matrix"]["error"] == "unknown"
