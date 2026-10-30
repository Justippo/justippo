"""Azure Document Intelligence REST adapter for PDF structure analysis.

The adapter is Pyodide-safe: it uses the existing ``httpx`` dependency, keeps
document bytes in memory, and adds no Azure SDK. It submits the PDF directly to
the GA 2024-11-30 Analyze Document From Stream endpoint, polls the operation,
and makes a best-effort deletion request for the temporary Azure result.

Document content is returned to the caller but is never logged or included in
exceptions. Production activation remains disabled until the Azure endpoint,
key, EU region, and privacy notice are configured and approved.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_API_VERSION = "2024-11-30"
_DEFAULT_MODEL_ID = "prebuilt-layout"
_TERMINAL_SUCCESS = "succeeded"
_TERMINAL_FAILURES = {"failed", "canceled", "cancelled"}
_MODEL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._~-]{1,63}$")
_F0_MAX_BYTES = 4 * 1024 * 1024
_F0_MAX_PAGES = 2
_S0_MAX_BYTES = 500 * 1024 * 1024
_S0_MAX_PAGES = 2_000


@dataclass(frozen=True)
class AzureDocumentAnalysis:
    """Normalized structural output used by later orchestration phases."""

    model_id: str
    api_version: str
    content: str
    pages: list[dict[str, Any]] = field(default_factory=list)
    paragraphs: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    key_value_pairs: list[dict[str, Any]] = field(default_factory=list)
    languages: list[dict[str, Any]] = field(default_factory=list)
    styles: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AzureDocumentIntelligenceLimits:
    """Configured provider-tier limits used before billable analysis starts."""

    tier: str
    max_bytes: int
    max_pages: int


@dataclass(frozen=True)
class AzureDocumentIntelligenceErrorDetail:
    """Content-safe error information exposed to the orchestrator."""

    code: str
    message: str
    retryable: bool
    provider_status: int | None = None


class AzureDocumentIntelligenceError(Exception):
    """Raised when Azure analysis cannot produce a usable result."""

    def __init__(self, detail: AzureDocumentIntelligenceErrorDetail) -> None:
        self.detail = detail
        super().__init__(f"Azure Document Intelligence error [{detail.code}]: {detail.message}")


@dataclass(frozen=True)
class _AzureConfig:
    endpoint: str
    key: str
    api_version: str
    model_id: str
    timeout_s: float
    poll_interval_s: float
    max_polls: int


SUPPORTED_CONTENT_TYPES: frozenset[str] = frozenset({"application/pdf", "image/png", "image/jpeg"})
"""Media types the analyze endpoint accepts for a binary POST (WEBP/DOCX are not)."""


def _is_enabled() -> bool:
    return os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def is_enabled() -> bool:
    """Public feature-flag check so callers can skip work before any billable call."""
    return _is_enabled()


def get_analysis_limits() -> AzureDocumentIntelligenceLimits:
    """Return the configured Azure tier limits without loading any secret."""
    tier = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_TIER", "F0").strip().upper() or "F0"
    if tier == "F0":
        return AzureDocumentIntelligenceLimits(
            tier=tier,
            max_bytes=_F0_MAX_BYTES,
            max_pages=_F0_MAX_PAGES,
        )
    if tier == "S0":
        return AzureDocumentIntelligenceLimits(
            tier=tier,
            max_bytes=_S0_MAX_BYTES,
            max_pages=_S0_MAX_PAGES,
        )
    raise AzureDocumentIntelligenceError(
        AzureDocumentIntelligenceErrorDetail(
            code="INVALID_CONFIGURATION",
            message="Azure Document Intelligence tier must be F0 or S0",
            retryable=False,
        )
    )


def _load_config() -> _AzureConfig:
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").strip().rstrip("/")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY", "").strip()
    if not endpoint or not key:
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="Azure Document Intelligence is not configured",
                retryable=False,
            )
        )

    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_CONFIGURATION",
                message="Azure Document Intelligence endpoint must be an HTTPS service origin",
                retryable=False,
            )
        )

    try:
        timeout_s = float(os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S", "30"))
        poll_interval_s = float(os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_POLL_INTERVAL_S", "1"))
        max_polls = int(os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS", "120"))
    except ValueError as exc:
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_CONFIGURATION",
                message="Azure Document Intelligence timing configuration is invalid",
                retryable=False,
            )
        ) from exc

    if timeout_s <= 0 or poll_interval_s < 0 or max_polls < 1:
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_CONFIGURATION",
                message="Azure Document Intelligence timing configuration is invalid",
                retryable=False,
            )
        )

    model_id = (
        os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID", _DEFAULT_MODEL_ID).strip()
        or _DEFAULT_MODEL_ID
    )
    if not _MODEL_ID_PATTERN.fullmatch(model_id):
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_CONFIGURATION",
                message="Azure Document Intelligence model ID is invalid",
                retryable=False,
            )
        )

    return _AzureConfig(
        endpoint=endpoint,
        key=key,
        api_version=os.environ.get(
            "AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", _DEFAULT_API_VERSION
        ).strip()
        or _DEFAULT_API_VERSION,
        model_id=model_id,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        max_polls=max_polls,
    )


def _validate_operation_location(operation_url: str, endpoint: str) -> str:
    """Reject a provider-supplied polling URL outside the configured Azure origin."""
    operation = urlparse(operation_url)
    configured = urlparse(endpoint)
    expected_prefix = f"{configured.path.rstrip('/')}/documentintelligence/"
    if (
        operation.scheme != configured.scheme
        or operation.netloc != configured.netloc
        or not operation.path.startswith(expected_prefix)
    ):
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_PROVIDER_RESPONSE",
                message="Azure returned an invalid analysis operation location",
                retryable=False,
            )
        )
    return operation_url


def _provider_error(*, status_code: int, stage: str) -> AzureDocumentIntelligenceError:
    retryable = status_code == 429 or status_code >= 500
    return AzureDocumentIntelligenceError(
        AzureDocumentIntelligenceErrorDetail(
            code="AZURE_ANALYSIS_FAILED",
            message=f"Azure document {stage} failed",
            retryable=retryable,
            provider_status=status_code,
        )
    )


def _normalize_result(payload: dict[str, Any], config: _AzureConfig) -> AzureDocumentAnalysis:
    result = payload.get("analyzeResult")
    if not isinstance(result, dict):
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_PROVIDER_RESPONSE",
                message="Azure analysis completed without a structured result",
                retryable=False,
            )
        )

    def dictionaries(name: str) -> list[dict[str, Any]]:
        value = result.get(name, [])
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    content = result.get("content", "")
    return AzureDocumentAnalysis(
        model_id=str(result.get("modelId") or config.model_id),
        api_version=str(result.get("apiVersion") or config.api_version),
        content=content if isinstance(content, str) else "",
        pages=dictionaries("pages"),
        paragraphs=dictionaries("paragraphs"),
        tables=dictionaries("tables"),
        key_value_pairs=dictionaries("keyValuePairs"),
        languages=dictionaries("languages"),
        styles=dictionaries("styles"),
    )


async def _delete_result(
    client: httpx.AsyncClient,
    operation_url: str,
    key: str,
) -> None:
    """Best-effort privacy cleanup; never mask the primary analysis outcome."""
    try:
        response = await client.delete(
            operation_url,
            headers={"Ocp-Apim-Subscription-Key": key},
        )
        if response.status_code not in {204, 404}:
            logger.warning(
                "Azure analysis result cleanup returned status=%s",
                response.status_code,
            )
    except Exception:
        logger.warning("Azure analysis result cleanup failed", exc_info=False)


async def analyze_pdf(
    document_bytes: bytes,
    *,
    request_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    content_type: str = "application/pdf",
) -> AzureDocumentAnalysis:
    """Analyze document structure using Azure's prebuilt-layout model.

    Despite the name (kept to avoid churn), ``content_type`` may be any of
    ``SUPPORTED_CONTENT_TYPES`` so PNG/JPEG scans can be analysed too.

    No HTTP call is made unless the feature flag is enabled. The optional client
    is a test/orchestration seam; callers that provide it retain ownership.
    """
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_INPUT",
                message="Unsupported content type for Azure analysis",
                retryable=False,
            )
        )
    if not _is_enabled():
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="Azure Document Intelligence is disabled",
                retryable=False,
            )
        )
    if not document_bytes:
        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="INVALID_INPUT",
                message="A non-empty PDF is required for Azure analysis",
                retryable=False,
            )
        )

    config = _load_config()
    analyze_url = f"{config.endpoint}/documentintelligence/documentModels/{config.model_id}:analyze"
    params = {
        "api-version": config.api_version,
        "features": "keyValuePairs,languages",
        "outputContentFormat": "markdown",
    }
    headers = {
        "Content-Type": content_type,
        "Ocp-Apim-Subscription-Key": config.key,
    }
    if request_id:
        headers["x-ms-client-request-id"] = request_id

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=config.timeout_s)
    operation_url: str | None = None

    try:
        try:
            response = await active_client.post(
                analyze_url,
                params=params,
                headers=headers,
                content=document_bytes,
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise AzureDocumentIntelligenceError(
                AzureDocumentIntelligenceErrorDetail(
                    code="SERVICE_UNAVAILABLE",
                    message="Azure document submission is temporarily unavailable",
                    retryable=True,
                )
            ) from exc

        if response.status_code != 202:
            raise _provider_error(status_code=response.status_code, stage="submission")

        location = response.headers.get("Operation-Location", "").strip()
        if not location:
            raise AzureDocumentIntelligenceError(
                AzureDocumentIntelligenceErrorDetail(
                    code="INVALID_PROVIDER_RESPONSE",
                    message="Azure did not return an analysis operation location",
                    retryable=False,
                )
            )
        operation_url = _validate_operation_location(location, config.endpoint)

        for poll_number in range(config.max_polls):
            if poll_number > 0 or config.poll_interval_s > 0:
                await asyncio.sleep(config.poll_interval_s)

            try:
                poll_response = await active_client.get(
                    operation_url,
                    headers={"Ocp-Apim-Subscription-Key": config.key},
                )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                raise AzureDocumentIntelligenceError(
                    AzureDocumentIntelligenceErrorDetail(
                        code="SERVICE_UNAVAILABLE",
                        message="Azure document polling is temporarily unavailable",
                        retryable=True,
                    )
                ) from exc

            if poll_response.status_code != 200:
                raise _provider_error(status_code=poll_response.status_code, stage="polling")

            try:
                payload = poll_response.json()
            except ValueError as exc:
                raise AzureDocumentIntelligenceError(
                    AzureDocumentIntelligenceErrorDetail(
                        code="INVALID_PROVIDER_RESPONSE",
                        message="Azure returned an invalid analysis response",
                        retryable=False,
                    )
                ) from exc

            if not isinstance(payload, dict):
                raise AzureDocumentIntelligenceError(
                    AzureDocumentIntelligenceErrorDetail(
                        code="INVALID_PROVIDER_RESPONSE",
                        message="Azure returned an invalid analysis response",
                        retryable=False,
                    )
                )

            status = str(payload.get("status", "")).lower()
            if status == _TERMINAL_SUCCESS:
                return _normalize_result(payload, config)
            if status in _TERMINAL_FAILURES:
                raise AzureDocumentIntelligenceError(
                    AzureDocumentIntelligenceErrorDetail(
                        code="AZURE_ANALYSIS_FAILED",
                        message="Azure document analysis failed",
                        retryable=False,
                        provider_status=poll_response.status_code,
                    )
                )

        raise AzureDocumentIntelligenceError(
            AzureDocumentIntelligenceErrorDetail(
                code="PROCESSING_TIMEOUT",
                message="Azure document analysis exceeded the polling limit",
                retryable=True,
            )
        )
    finally:
        if operation_url is not None:
            await _delete_result(active_client, operation_url, config.key)
        if owns_client:
            await active_client.aclose()
