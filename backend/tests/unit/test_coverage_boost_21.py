"""Coverage boost batch 21 — matrix_auth pure helpers, error paths, discovery flows."""

from __future__ import annotations

import hashlib
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import matrix_auth as ma
from app.core.config import settings as app_settings

# ─── pure helpers ───────────────────────────────────────────────


class TestMatrixAuthHelpers:
    def test_state_hash_is_sha256_hex(self) -> None:
        state = "abc123"
        expected = hashlib.sha256(state.encode()).hexdigest()
        assert ma._state_hash(state) == expected

    def test_pkce_challenge_matches_rfc7636(self) -> None:
        verifier = "test-verifier-string"
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = urlsafe_b64encode(digest).decode().rstrip("=")
        assert ma._pkce_challenge(verifier) == expected

    def test_has_env_token_reads_settings(self) -> None:
        with patch.object(app_settings, "MATRIX_ACCESS_TOKEN", "tok"):
            assert ma._has_env_token() is True
        with patch.object(app_settings, "MATRIX_ACCESS_TOKEN", ""):
            assert ma._has_env_token() is False

    def test_require_enabled_raises_when_disabled(self) -> None:
        with patch.object(app_settings, "ENABLE_MATRIX_AUTH", False):
            with pytest.raises(HTTPException) as exc_info:
                ma._require_enabled()
            assert exc_info.value.status_code == 403

    def test_require_enabled_passes_when_enabled(self) -> None:
        with patch.object(app_settings, "ENABLE_MATRIX_AUTH", True):
            # Should not raise when enabled
            ma._require_enabled()

    def test_json_object_to_python_uses_to_py(self) -> None:
        fake = MagicMock()
        fake.to_py.return_value = {"a": 1}
        assert ma._json_object_to_python(fake) == {"a": 1}

    def test_json_object_to_python_passthrough_dict(self) -> None:
        assert ma._json_object_to_python({"b": 2}) == {"b": 2}

    def test_json_object_to_python_rejects_non_dict(self) -> None:
        with pytest.raises(TypeError):
            ma._json_object_to_python(["not", "an", "object"])


# ─── error classes ──────────────────────────────────────────────


class TestMatrixAuthErrors:
    def test_discovery_error_is_http_exception(self) -> None:
        err = ma.MatrixDiscoveryError("unsupported", "not supported")
        assert isinstance(err, HTTPException)
        assert err.status_code == 503
        assert err.detail == "not supported"
        assert err.reason == "unsupported"

    def test_provider_transport_error(self) -> None:
        err = ma.MatrixProviderTransportError("boom")
        assert isinstance(err, Exception)
        assert str(err) == "boom"


# ─── discovery transport paths ──────────────────────────────────


class TestMatrixDiscovery:
    async def test_fetch_metadata_workers_unavailable_returns_none(self) -> None:
        # `workers` import fails outside Pyodide → None
        result = await ma._fetch_metadata_with_workers("https://example/.well-known")
        assert result is None

    async def test_fetch_metadata_httpx_transport_error(self) -> None:
        with patch("app.api.v1.endpoints.matrix_auth.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.ConnectError(
                "down"
            )
            with pytest.raises(ma.MatrixDiscoveryError):
                await ma._fetch_metadata_with_httpx("https://example/metadata")

    async def test_discover_metadata_unsupported_404(self) -> None:
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=False)),
            patch.object(ma, "_fetch_metadata_with_httpx", new=AsyncMock(return_value=(404, {}))),
            pytest.raises(ma.MatrixDiscoveryError) as exc_info,
        ):
            await ma._discover_metadata()
        assert exc_info.value.detail == "Matrix OAuth is not supported"

    async def test_discover_metadata_unexpected_status(self) -> None:
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=False)),
            patch.object(ma, "_fetch_metadata_with_httpx", new=AsyncMock(return_value=(500, {}))),
            pytest.raises(ma.MatrixDiscoveryError) as exc_info,
        ):
            await ma._discover_metadata()
        assert exc_info.value.detail == "Matrix authentication is unavailable"

    async def test_discover_metadata_incomplete(self) -> None:
        metadata = {
            "authorization_endpoint": "https://a",
            "token_endpoint": "https://t",
            # missing revocation + registration endpoints and S256
        }
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=False)),
            patch.object(
                ma, "_fetch_metadata_with_httpx", new=AsyncMock(return_value=(200, metadata))
            ),
            pytest.raises(ma.MatrixDiscoveryError) as exc_info,
        ):
            await ma._discover_metadata()
        assert exc_info.value.detail == "Matrix OAuth metadata is incomplete"

    async def test_discover_metadata_success(self) -> None:
        metadata = {
            "authorization_endpoint": "https://a",
            "token_endpoint": "https://t",
            "revocation_endpoint": "https://r",
            "registration_endpoint": "https://reg",
            "code_challenge_methods_supported": ["S256"],
        }
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=False)),
            patch.object(
                ma, "_fetch_metadata_with_httpx", new=AsyncMock(return_value=(200, metadata))
            ),
        ):
            result = await ma._discover_metadata()
            assert result == metadata


# ─── provider request dispatch ──────────────────────────────────


class TestMatrixProviderRequest:
    async def test_provider_request_production_unavailable_raises(self) -> None:
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=True)),
            patch.object(ma, "_provider_request_with_workers", new=AsyncMock(return_value=None)),
            pytest.raises(ma.MatrixProviderTransportError),
        ):
            await ma._provider_request("https://p/token", method="POST", form={})

    async def test_provider_request_production_success(self) -> None:
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=True)),
            patch.object(
                ma,
                "_provider_request_with_workers",
                new=AsyncMock(return_value=(200, {"ok": True})),
            ),
        ):
            status, payload = await ma._provider_request("https://p/token")
            assert status == 200
            assert payload == {"ok": True}

    async def test_provider_request_non_production_uses_httpx(self) -> None:
        with (
            patch.object(type(app_settings), "is_production", PropertyMock(return_value=False)),
            patch.object(
                ma,
                "_provider_request_with_httpx",
                new=AsyncMock(return_value=(200, {"x": 1})),
            ),
        ):
            status, payload = await ma._provider_request("https://p/token")
            assert status == 200
            assert payload == {"x": 1}
