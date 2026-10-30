"""Mocked contract tests for the Azure Document Intelligence adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.integrations.azure_document_intelligence import (
    AzureDocumentIntelligenceError,
    analyze_pdf,
    get_analysis_limits,
)

_ENDPOINT = "https://evidenceeu-docs.cognitiveservices.azure.com"
_OPERATION = (
    f"{_ENDPOINT}/documentintelligence/documentModels/prebuilt-layout/"
    "analyzeResults/3b31320d-8bab-4f88-b19c-2322a7f11034?api-version=2024-11-30"
)
_CONFIG = {
    "AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "true",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": _ENDPOINT,
    "AZURE_DOCUMENT_INTELLIGENCE_KEY": "test-secret-key",
    "AZURE_DOCUMENT_INTELLIGENCE_POLL_INTERVAL_S": "0",
    "AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS": "3",
}


def _response(status_code: int, *, json: object | None = None) -> httpx.Response:
    request = httpx.Request("GET", _OPERATION)
    if json is None:
        return httpx.Response(status_code, request=request)
    return httpx.Response(status_code, request=request, json=json)


def test_analysis_limits_default_to_f0_and_support_explicit_s0() -> None:
    with patch.dict("os.environ", {}, clear=True):
        f0 = get_analysis_limits()
    with patch.dict("os.environ", {"AZURE_DOCUMENT_INTELLIGENCE_TIER": "S0"}, clear=True):
        s0 = get_analysis_limits()

    assert (f0.tier, f0.max_pages, f0.max_bytes) == ("F0", 2, 4 * 1024 * 1024)
    assert (s0.tier, s0.max_pages, s0.max_bytes) == ("S0", 2_000, 500 * 1024 * 1024)


@pytest.mark.asyncio
async def test_disabled_adapter_makes_no_http_call() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)

    with (
        patch.dict("os.environ", {"AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "false"}, clear=True),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"%PDF-1.7", client=client)

    assert exc_info.value.detail.code == "SERVICE_UNAVAILABLE"
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_enabled_adapter_requires_endpoint_and_key() -> None:
    with (
        patch.dict(
            "os.environ",
            {"AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "true"},
            clear=True,
        ),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"%PDF-1.7")

    assert exc_info.value.detail.code == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_analyze_pdf_returns_normalized_structure_and_deletes_result() -> None:
    submit = _response(202)
    submit.headers["Operation-Location"] = _OPERATION
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = submit
    client.get.side_effect = [
        _response(200, json={"status": "running"}),
        _response(
            200,
            json={
                "status": "succeeded",
                "analyzeResult": {
                    "modelId": "prebuilt-layout",
                    "apiVersion": "2024-11-30",
                    "content": "Application requirements",
                    "pages": [{"pageNumber": 1, "selectionMarks": []}],
                    "paragraphs": [{"content": "Application requirements"}],
                    "tables": [{"rowCount": 2, "columnCount": 2}],
                    "keyValuePairs": [{"key": {"content": "Name"}}],
                    "languages": [{"locale": "en", "confidence": 0.99}],
                },
            },
        ),
    ]
    client.delete.return_value = _response(204)

    with patch.dict("os.environ", _CONFIG, clear=True):
        result = await analyze_pdf(
            b"%PDF-1.7 private bytes", request_id="request-123", client=client
        )

    assert result.content == "Application requirements"
    assert result.pages[0]["pageNumber"] == 1
    assert result.tables[0]["rowCount"] == 2
    assert result.key_value_pairs[0]["key"]["content"] == "Name"
    assert result.languages[0]["locale"] == "en"

    post = client.post.await_args
    assert post.args[0].endswith("/documentModels/prebuilt-layout:analyze")
    assert post.kwargs["content"] == b"%PDF-1.7 private bytes"
    assert post.kwargs["headers"]["Content-Type"] == "application/pdf"
    assert post.kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "test-secret-key"
    assert post.kwargs["headers"]["x-ms-client-request-id"] == "request-123"
    assert post.kwargs["params"]["features"] == "keyValuePairs,languages"
    client.delete.assert_awaited_once_with(
        _OPERATION,
        headers={"Ocp-Apim-Subscription-Key": "test-secret-key"},
    )


@pytest.mark.asyncio
async def test_failed_analysis_is_typed_and_result_is_deleted() -> None:
    submit = _response(202)
    submit.headers["Operation-Location"] = _OPERATION
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = submit
    client.get.return_value = _response(
        200,
        json={"status": "failed", "error": {"message": "private provider detail"}},
    )
    client.delete.return_value = _response(204)

    with (
        patch.dict("os.environ", _CONFIG, clear=True),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"%PDF-1.7 private bytes", client=client)

    assert exc_info.value.detail.code == "AZURE_ANALYSIS_FAILED"
    assert "private provider detail" not in str(exc_info.value)
    client.delete.assert_awaited_once_with(
        _OPERATION,
        headers={"Ocp-Apim-Subscription-Key": "test-secret-key"},
    )


@pytest.mark.asyncio
async def test_polling_limit_returns_retryable_timeout_and_deletes_result() -> None:
    submit = _response(202)
    submit.headers["Operation-Location"] = _OPERATION
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = submit
    client.get.return_value = _response(200, json={"status": "running"})
    client.delete.return_value = _response(204)

    with (
        patch.dict(
            "os.environ", _CONFIG | {"AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS": "2"}, clear=True
        ),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"%PDF-1.7", client=client)

    assert exc_info.value.detail.code == "PROCESSING_TIMEOUT"
    assert exc_info.value.detail.retryable is True
    assert client.get.await_count == 2
    client.delete.assert_awaited_once_with(
        _OPERATION,
        headers={"Ocp-Apim-Subscription-Key": "test-secret-key"},
    )


@pytest.mark.asyncio
async def test_rejects_cross_origin_operation_location() -> None:
    submit = _response(202)
    submit.headers["Operation-Location"] = "https://attacker.example/analyzeResults/secret"
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = submit

    with (
        patch.dict("os.environ", _CONFIG, clear=True),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"%PDF-1.7", client=client)

    assert exc_info.value.detail.code == "INVALID_PROVIDER_RESPONSE"
    client.get.assert_not_awaited()
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_error_does_not_expose_response_body_or_secret() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = httpx.Response(
        400,
        request=httpx.Request("POST", _ENDPOINT),
        json={"error": {"message": "document text and test-secret-key"}},
    )

    with (
        patch.dict("os.environ", _CONFIG, clear=True),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"%PDF-1.7 private bytes", client=client)

    rendered = str(exc_info.value)
    assert "document text" not in rendered
    assert "test-secret-key" not in rendered
    assert exc_info.value.detail.provider_status == 400


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_success() -> None:
    submit = _response(202)
    submit.headers["Operation-Location"] = _OPERATION
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = submit
    client.get.return_value = _response(
        200,
        json={"status": "succeeded", "analyzeResult": {"content": "ok"}},
    )
    client.delete.side_effect = httpx.ConnectError("cleanup unavailable")

    with patch.dict("os.environ", _CONFIG, clear=True):
        result = await analyze_pdf(b"%PDF-1.7", client=client)

    assert result.content == "ok"


@pytest.mark.asyncio
async def test_analyze_accepts_image_content_type_and_sends_it() -> None:
    submit = _response(202)
    submit.headers["Operation-Location"] = _OPERATION
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = submit
    client.get.return_value = _response(
        200, json={"status": "succeeded", "analyzeResult": {"content": "scan text"}}
    )
    client.delete.return_value = _response(204)

    with patch.dict("os.environ", _CONFIG, clear=True):
        result = await analyze_pdf(b"\x89PNG bytes", client=client, content_type="image/png")

    assert result.content == "scan text"
    assert client.post.await_args.kwargs["headers"]["Content-Type"] == "image/png"


@pytest.mark.asyncio
async def test_analyze_rejects_unsupported_content_type_without_http_call() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)

    with (
        patch.dict("os.environ", _CONFIG, clear=True),
        pytest.raises(AzureDocumentIntelligenceError) as exc_info,
    ):
        await analyze_pdf(b"RIFF", client=client, content_type="image/webp")

    assert exc_info.value.detail.code == "INVALID_INPUT"
    client.post.assert_not_awaited()
