"""
Unit tests for PII redaction sidecar adapter.

Tests verify:
- Successful redaction flow with mocked httpx
- Retry logic on 503 (exponential backoff, 3 attempts)
- RuntimeError when PII_REDACTION_BASE_URL is not set
- NotImplementedError when PII_REDACTION_ENABLED=false
- Non-retryable error (400) fails immediately
- redact_with_fallback returns unredacted text on failure
- AST check: presidio/spacy never imported in any service/api file
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.pii_redaction_adapter import (
    PIIRedactionRequest,
    PIIRedactionResult,
    PIIRedactionSidecarError,
    is_redaction_ready,
    redact,
    redact_with_fallback,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_request() -> PIIRedactionRequest:
    """A minimal valid redaction request."""
    return PIIRedactionRequest(
        text="John Smith lives at 123 Main St, Berlin.",
        language="en",
        timeout_seconds=10,
    )


@pytest.fixture
def mock_success_response() -> dict:
    """Mock sidecar success response payload."""
    return {
        "redacted_text": "[PERSON] lives at [LOCATION], [LOCATION].",
        "entity_count": 3,
        "entity_types": ["LOCATION", "PERSON"],
        "processing_time_ms": 45.2,
    }


def _make_mock_httpx(mock_resp: MagicMock | None = None, side_effect=None) -> MagicMock:
    """Build a mock httpx module with AsyncClient."""
    mock_client = AsyncMock()
    if side_effect:
        mock_client.post = AsyncMock(side_effect=side_effect)
    else:
        mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient.return_value = mock_client
    mock_httpx.TimeoutException = Exception
    mock_httpx.ConnectError = ConnectionError
    return mock_httpx


# ---------------------------------------------------------------------------
# Tests: successful redaction
# ---------------------------------------------------------------------------


class TestRedactSuccess:
    """Test successful redaction flow."""

    @pytest.mark.asyncio
    async def test_redact_success(
        self, sample_request: PIIRedactionRequest, mock_success_response: dict
    ) -> None:
        """Mock httpx POST returns 200 with valid response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_success_response

        mock_httpx = _make_mock_httpx(mock_resp)

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
        ):
            result = await redact(sample_request)

        assert isinstance(result, PIIRedactionResult)
        assert result.redacted_text == "[PERSON] lives at [LOCATION], [LOCATION]."
        assert result.entity_count == 3
        assert "PERSON" in result.entity_types
        assert "LOCATION" in result.entity_types

        # Verify correct request shape
        call_kwargs = mock_httpx.AsyncClient.return_value.post.call_args
        assert call_kwargs[0][0] == "http://localhost:8760/redact"
        payload = call_kwargs[1]["json"]
        assert payload["text"] == "John Smith lives at 123 Main St, Berlin."
        assert payload["language"] == "en"


# ---------------------------------------------------------------------------
# Tests: retry logic
# ---------------------------------------------------------------------------


class TestRedactRetryOn503:
    """Test exponential backoff retry on 503."""

    @pytest.mark.asyncio
    async def test_redact_retry_on_503(self, sample_request: PIIRedactionRequest) -> None:
        """Assert 3 attempts before raising PIIRedactionSidecarError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        mock_httpx = _make_mock_httpx(mock_resp)

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "app.integrations.pii_redaction_adapter.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            pytest.raises(PIIRedactionSidecarError) as exc_info,
        ):
            await redact(sample_request)

        assert exc_info.value.error.error_code == "SERVICE_UNAVAILABLE"
        assert exc_info.value.error.retryable is True
        assert mock_httpx.AsyncClient.return_value.post.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.5)
        mock_sleep.assert_any_call(1.0)


# ---------------------------------------------------------------------------
# Tests: configuration errors
# ---------------------------------------------------------------------------


class TestRedactConfigErrors:
    """Test RuntimeError and NotImplementedError for misconfiguration."""

    @pytest.mark.asyncio
    async def test_redact_base_url_not_set(self, sample_request: PIIRedactionRequest) -> None:
        """Assert RuntimeError when PII_REDACTION_BASE_URL is empty."""
        with (
            patch.dict(
                "os.environ",
                {"PII_REDACTION_BASE_URL": "", "PII_REDACTION_ENABLED": "true"},
                clear=False,
            ),
            pytest.raises(RuntimeError, match="PII redaction sidecar not configured"),
        ):
            await redact(sample_request)

    @pytest.mark.asyncio
    async def test_redact_disabled_flag(self, sample_request: PIIRedactionRequest) -> None:
        """Assert NotImplementedError when feature flag is off."""
        with (
            patch.dict("os.environ", {"PII_REDACTION_ENABLED": "false"}, clear=False),
            pytest.raises(NotImplementedError, match="PII redaction is disabled"),
        ):
            await redact(sample_request)

    def test_readiness_requires_flag_and_url(self) -> None:
        """Only ready when both flag and URL are set."""
        with patch.dict(
            "os.environ",
            {"PII_REDACTION_ENABLED": "true", "PII_REDACTION_BASE_URL": "http://pii-redactor:8760"},
            clear=False,
        ):
            assert is_redaction_ready() is True

        with patch.dict(
            "os.environ",
            {"PII_REDACTION_ENABLED": "false", "PII_REDACTION_BASE_URL": ""},
            clear=False,
        ):
            assert is_redaction_ready() is False


# ---------------------------------------------------------------------------
# Tests: non-retryable error
# ---------------------------------------------------------------------------


class TestRedactNonRetryableError:
    """Test non-retryable error (e.g. 400 Bad Request)."""

    @pytest.mark.asyncio
    async def test_redact_non_retryable_error(self, sample_request: PIIRedactionRequest) -> None:
        """Assert immediate failure on 400 with error envelope parsing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_resp.json.return_value = {
            "error": {
                "code": "INVALID_INPUT",
                "message": "Text too long",
                "retryable": False,
                "details": None,
            }
        }

        mock_httpx = _make_mock_httpx(mock_resp)

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            pytest.raises(PIIRedactionSidecarError) as exc_info,
        ):
            await redact(sample_request)

        assert exc_info.value.error.error_code == "INVALID_INPUT"
        assert exc_info.value.error.retryable is False
        # Should NOT retry — only 1 attempt
        assert mock_httpx.AsyncClient.return_value.post.call_count == 1


# ---------------------------------------------------------------------------
# Tests: timeout and connect error retries
# ---------------------------------------------------------------------------


class TestRedactTimeoutRetry:
    """Test retry on httpx.TimeoutException."""

    @pytest.mark.asyncio
    async def test_redact_retry_on_timeout(self, sample_request: PIIRedactionRequest) -> None:
        """Assert 3 attempts on timeout before raising."""
        import httpx

        mock_httpx = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_httpx.ConnectError = httpx.ConnectError

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "app.integrations.pii_redaction_adapter.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            pytest.raises(PIIRedactionSidecarError) as exc_info,
        ):
            await redact(sample_request)

        assert exc_info.value.error.error_code == "TIMEOUT"
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2


class TestRedactConnectError:
    """Test retry on httpx.ConnectError."""

    @pytest.mark.asyncio
    async def test_redact_retry_on_connect_error(self, sample_request: PIIRedactionRequest) -> None:
        """Assert 3 attempts on connect error before raising."""
        import httpx

        mock_httpx = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_httpx.ConnectError = httpx.ConnectError

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "app.integrations.pii_redaction_adapter.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            pytest.raises(PIIRedactionSidecarError) as exc_info,
        ):
            await redact(sample_request)

        assert exc_info.value.error.error_code == "SERVICE_UNAVAILABLE"
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# Tests: redact_with_fallback
# ---------------------------------------------------------------------------


class TestRedactWithFallback:
    """Test the fallback wrapper used by TranslationService."""

    @pytest.mark.asyncio
    async def test_fallback_success(
        self, sample_request: PIIRedactionRequest, mock_success_response: dict
    ) -> None:
        """Returns redacted text, True, and result on success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_success_response

        mock_httpx = _make_mock_httpx(mock_resp)

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
        ):
            text, succeeded, result = await redact_with_fallback(sample_request)

        assert succeeded is True
        assert result is not None
        assert text == "[PERSON] lives at [LOCATION], [LOCATION]."
        assert result.entity_count == 3

    @pytest.mark.asyncio
    async def test_fallback_on_sidecar_error(self, sample_request: PIIRedactionRequest) -> None:
        """Returns original text and False when sidecar fails."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        mock_httpx = _make_mock_httpx(mock_resp)

        with (
            patch.dict(
                "os.environ",
                {
                    "PII_REDACTION_BASE_URL": "http://localhost:8760",
                    "PII_REDACTION_ENABLED": "true",
                },
            ),
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch("app.integrations.pii_redaction_adapter.asyncio.sleep", new_callable=AsyncMock),
        ):
            text, succeeded, result = await redact_with_fallback(sample_request)

        assert succeeded is False
        assert result is None
        assert text == "John Smith lives at 123 Main St, Berlin."

    @pytest.mark.asyncio
    async def test_fallback_on_unexpected_error(self, sample_request: PIIRedactionRequest) -> None:
        """Returns original text and False on unexpected exception."""
        with (
            patch.dict(
                "os.environ",
                {"PII_REDACTION_BASE_URL": "", "PII_REDACTION_ENABLED": "true"},
                clear=False,
            ),
        ):
            text, succeeded, result = await redact_with_fallback(sample_request)

        assert succeeded is False
        assert result is None
        assert text == "John Smith lives at 123 Main St, Berlin."


# ---------------------------------------------------------------------------
# AST check: presidio/spacy never imported in services/API
# ---------------------------------------------------------------------------


class TestPresidioNotImportedInServices:
    """AST check: presidio and spacy are never imported in services/API code.

    Mirrors the BabelDOC AST test pattern. The HTTP boundary is what keeps
    Presidio's native deps out of the Pyodide backend — direct imports
    would break the Worker runtime.
    """

    def test_presidio_not_imported_in_services_or_api(self) -> None:
        """Reject direct presidio/spacy imports while allowing the HTTP adapter."""
        services_dir = Path(__file__).resolve().parents[2] / "app" / "services"
        api_dir = Path(__file__).resolve().parents[2] / "app" / "api"
        allowed_adapter = "app.integrations.pii_redaction_adapter"
        forbidden_modules = {"presidio", "spacy"}

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
                            top_level = alias.name.split(".")[0]
                            if top_level in forbidden_modules:
                                violations.append(f"{py_file.name}: import {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        top_level = module.split(".")[0]
                        if top_level in forbidden_modules and module != allowed_adapter:
                            violations.append(f"{py_file.name}: from {module} import ...")

        assert not violations, (
            f"Pyodide violation: presidio/spacy must NEVER be imported directly in services/API code. "
            f"Use app/integrations/pii_redaction_adapter.py (HTTP boundary) instead.\\n"
            f"Found: {violations}"
        )
