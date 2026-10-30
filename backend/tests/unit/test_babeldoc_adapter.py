"""
Unit tests for BabelDOC sidecar adapter.

Tests verify:
- Successful translation flow with mocked httpx
- Retry logic on 503 (exponential backoff, 3 attempts)
- RuntimeError when BABELDOC_SIDECAR_URL is not set
- NotImplementedError when BABELDOC_ENABLED=false
- AST check: babeldoc is never imported in any service file
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.babeldoc_adapter import (
    BabelDocRequest,
    BabelDocResponse,
    BabelDocSidecarError,
    is_babeldoc_ready,
    translate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_request() -> BabelDocRequest:
    """A minimal valid translation request."""
    return BabelDocRequest(
        source_lang="en",
        target_lang="de",
        document_b64="dGVzdCBwZGYgY29udGVudA==",  # base64("test pdf content")
        preserve_layout=True,
        timeout_seconds=30,
    )


@pytest.fixture
def mock_success_response() -> dict:
    """Mock sidecar success response payload."""
    return {
        "translated_b64": "dHJhbnNsYXRlZCBjb250ZW50",
        "source_lang": "en",
        "target_lang": "de",
        "detected_lang": "en",
        "processing_time_ms": 1234.5,
        "layout_preserved": True,
        "pages_processed": 3,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBabelDocTranslateSuccess:
    """Test successful translation flow."""

    @pytest.mark.asyncio
    async def test_translate_success(
        self, sample_request: BabelDocRequest, mock_success_response: dict
    ) -> None:
        """Mock httpx POST returns 200 with valid response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_success_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = ConnectionError

        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "http://localhost:8700", "BABELDOC_ENABLED": "true"},
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
        ):
            result = await translate(sample_request)

        assert isinstance(result, BabelDocResponse)
        assert result.translated_b64 == "dHJhbnNsYXRlZCBjb250ZW50"
        assert result.source_lang == "en"
        assert result.target_lang == "de"
        assert result.detected_lang == "en"
        assert result.processing_time_ms == 1234.5
        assert result.layout_preserved is True
        assert result.pages_processed == 3

        # Verify correct request shape was sent
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == "http://localhost:8700/translate"
        payload = call_kwargs[1]["json"]
        assert payload["source_lang"] == "en"
        assert payload["target_lang"] == "de"
        assert payload["preserve_layout"] is True

    @pytest.mark.asyncio
    async def test_translate_rejects_mismatched_response_language_pair(
        self, sample_request: BabelDocRequest, mock_success_response: dict
    ) -> None:
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            **mock_success_response,
            "target_lang": "fr",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_httpx.ConnectError = httpx.ConnectError

        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "http://localhost:8700", "BABELDOC_ENABLED": "true"},
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            pytest.raises(BabelDocSidecarError) as exc_info,
        ):
            await translate(sample_request)

        assert exc_info.value.error.error_code == "INVALID_RESPONSE"


class TestBabelDocRetryOn503:
    """Test exponential backoff retry on 503."""

    @pytest.mark.asyncio
    async def test_translate_retry_on_503(self, sample_request: BabelDocRequest) -> None:
        """Assert 3 attempts before raising BabelDocSidecarError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = ConnectionError

        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "http://localhost:8700", "BABELDOC_ENABLED": "true"},
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "app.integrations.babeldoc_adapter.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            pytest.raises(BabelDocSidecarError) as exc_info,
        ):
            await translate(sample_request)

        assert exc_info.value.error.error_code == "SERVICE_UNAVAILABLE"
        assert exc_info.value.error.retryable is True

        # Should have attempted 3 times (2 retries after first attempt)
        assert mock_client.post.call_count == 3

        # Should have slept twice (between attempts 1→2 and 2→3)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(4.0)


class TestBabelDocSidecarUrlNotSet:
    """Test RuntimeError when BABELDOC_SIDECAR_URL is not set."""

    @pytest.mark.asyncio
    async def test_translate_sidecar_url_not_set(self, sample_request: BabelDocRequest) -> None:
        """Assert RuntimeError with clear message."""
        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "", "BABELDOC_ENABLED": "true"},
                clear=False,
            ),
            pytest.raises(RuntimeError, match="BabelDOC sidecar not configured"),
        ):
            await translate(sample_request)


class TestBabelDocDisabledFlag:
    """Test NotImplementedError when BABELDOC_ENABLED=false."""

    @pytest.mark.asyncio
    async def test_translate_disabled_flag(self, sample_request: BabelDocRequest) -> None:
        """Assert NotImplementedError when feature flag is off."""
        with (
            patch.dict("os.environ", {"BABELDOC_ENABLED": "false"}, clear=False),
            pytest.raises(NotImplementedError, match="BabelDOC translation is disabled"),
        ):
            await translate(sample_request)

    @pytest.mark.asyncio
    async def test_translate_disabled_flag_unset(self, sample_request: BabelDocRequest) -> None:
        """Assert NotImplementedError when env var is missing (default=false)."""
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(NotImplementedError),
        ):
            await translate(sample_request)

    def test_readiness_requires_flag_and_url(self) -> None:
        """Only advertise layout translation when both settings are present."""
        with patch.dict(
            "os.environ",
            {
                "BABELDOC_ENABLED": "true",
                "BABELDOC_SIDECAR_URL": "https://babeldoc.example",
            },
            clear=False,
        ):
            assert is_babeldoc_ready() is True

        with patch.dict(
            "os.environ",
            {"BABELDOC_ENABLED": "false", "BABELDOC_SIDECAR_URL": ""},
            clear=False,
        ):
            assert is_babeldoc_ready() is False


class TestBabelDocTimeoutRetry:
    """Test retry on httpx.TimeoutException."""

    @pytest.mark.asyncio
    async def test_translate_retry_on_timeout(self, sample_request: BabelDocRequest) -> None:
        """Assert 3 attempts on timeout before raising BabelDocSidecarError."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_httpx.ConnectError = httpx.ConnectError

        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "http://localhost:8700", "BABELDOC_ENABLED": "true"},
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "app.integrations.babeldoc_adapter.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            pytest.raises(BabelDocSidecarError) as exc_info,
        ):
            await translate(sample_request)

        assert exc_info.value.error.error_code == "TIMEOUT"
        assert exc_info.value.error.retryable is True
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2


class TestBabelDocConnectError:
    """Test retry on httpx.ConnectError."""

    @pytest.mark.asyncio
    async def test_translate_retry_on_connect_error(self, sample_request: BabelDocRequest) -> None:
        """Assert 3 attempts on connect error before raising."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_httpx.ConnectError = httpx.ConnectError

        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "http://localhost:8700", "BABELDOC_ENABLED": "true"},
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "app.integrations.babeldoc_adapter.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            pytest.raises(BabelDocSidecarError) as exc_info,
        ):
            await translate(sample_request)

        assert exc_info.value.error.error_code == "SERVICE_UNAVAILABLE"
        assert exc_info.value.error.retryable is True
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2


class TestBabelDocNonRetryableError:
    """Test non-retryable error (e.g. 400 Bad Request)."""

    @pytest.mark.asyncio
    async def test_translate_non_retryable_error(self, sample_request: BabelDocRequest) -> None:
        """Assert immediate failure on 400 with error envelope parsing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_resp.json.return_value = {
            "error": {
                "code": "INVALID_INPUT",
                "message": "Unsupported source language: xx",
                "retryable": False,
                "details": None,
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = ConnectionError

        with (
            patch.dict(
                "os.environ",
                {"BABELDOC_SIDECAR_URL": "http://localhost:8700", "BABELDOC_ENABLED": "true"},
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            pytest.raises(BabelDocSidecarError) as exc_info,
        ):
            await translate(sample_request)

        assert exc_info.value.error.error_code == "INVALID_INPUT"
        assert exc_info.value.error.retryable is False
        assert exc_info.value.error.message == "Unsupported source language: xx"
        # Should NOT retry — only 1 attempt
        assert mock_client.post.call_count == 1


class TestBabelDocNotImportedInServices:
    """AST check: babeldoc is never imported directly in any service file.

    Mirrors the Reducto AST test pattern from run_ocr_benchmark.py.
    The HTTP boundary is what isolates AGPL — direct imports would violate it.
    """

    def test_babeldoc_not_imported_in_services(self) -> None:
        """Reject direct BabelDOC imports while allowing the HTTP adapter."""
        services_dir = Path(__file__).resolve().parents[2] / "app" / "services"
        api_dir = Path(__file__).resolve().parents[2] / "app" / "api"
        allowed_adapter = "app.integrations.babeldoc_adapter"

        violations: list[str] = []
        for directory in [services_dir, api_dir]:
            if not directory.exists():
                continue
            for py_file in directory.rglob("*.py"):
                source = py_file.read_text()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if "babeldoc" in alias.name.lower() and alias.name != allowed_adapter:
                                violations.append(f"{py_file.name}: import {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if "babeldoc" in module.lower() and module != allowed_adapter:
                            violations.append(f"{py_file.name}: from {module} import ...")

        assert not violations, (
            f"AGPL violation: BabelDOC must NEVER be imported directly in services/API code. "
            f"Use app/integrations/babeldoc_adapter.py (HTTP boundary) instead.\n"
            f"Found: {violations}"
        )
