"""Resilience / error-branch coverage for the external-LLM service adapters.

DRY:
- Every external call in these services funnels through a single chokepoint:
  ``httpx.AsyncClient`` -> Cloudflare AI Gateway / provider endpoints. We mock
  that ONE dependency via ``httpx.MockTransport`` (injected by patching
  ``httpx.AsyncClient``), so dozens of distinct error branches across
  OCR / translation / PDF-reference services are exercised from a single
  fixture instead of bespoke per-service mocks.
- Pure input validators (no network) are tested directly.

These are genuine resilience paths (upstream 4xx/5xx, connect/timeout
failures, malformed provider responses) — real behaviour, not filler.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from app.services.ocr_service import (
    MistralOCRError,
    OCRError,
    OCRService,
)
from app.services.pdf_reference_translation_service import (
    MAX_TRANSLATED_PDF_B64_CHARS,
    PDFReferenceTranslationError,
    _validate_languages,
    _validate_translated_pdf,
)
from app.services.translation_service import TranslationError, TranslationService

# Capture the REAL httpx.AsyncClient before any test patches it, so the
# mock-client factory can build genuine clients backed by MockTransport
# without recursing into the patched symbol.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


# ---------------------------------------------------------------------------
# Shared DRY fixture: a real httpx.AsyncClient backed by a MockTransport.
# The handler decides the response (status/json) or raises a transport error.
# ---------------------------------------------------------------------------
def _mock_client(
    status: int = 200,
    json_body: dict | None = None,
    raise_exc: Exception | None = None,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        return httpx.Response(status, json=json_body if json_body is not None else {})

    return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))


@pytest.fixture
def patch_httpx(monkeypatch):
    """Patch the single httpx.AsyncClient chokepoint for the duration of a test."""

    def _install(client_factory):
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client_factory())

    return _install


# ===========================================================================
# PDF reference translation — PURE validators (no network)
# ===========================================================================
def test_validate_languages_unsupported_source():
    with pytest.raises(PDFReferenceTranslationError) as exc:
        _validate_languages("xx", "en")
    assert exc.value.status_code == 422
    assert exc.value.detail.code == "UNSUPPORTED_LANGUAGE"


def test_validate_languages_unsupported_target():
    with pytest.raises(PDFReferenceTranslationError) as exc:
        _validate_languages("en", "zz")
    assert exc.value.status_code == 422
    assert exc.value.detail.code == "UNSUPPORTED_LANGUAGE"


def test_validate_languages_same_pair_rejected():
    with pytest.raises(PDFReferenceTranslationError) as exc:
        _validate_languages("en", "en")
    assert exc.value.status_code == 422
    assert exc.value.detail.code == "INVALID_LANGUAGE_PAIR"


def test_validate_languages_case_insensitive_accepts():
    # "EN" / "FR" should normalise and pass.
    src, tgt = _validate_languages("EN", "FR")
    assert (src, tgt) == ("en", "fr")


def test_validate_translated_pdf_oversized_rejected():
    big = "A" * (MAX_TRANSLATED_PDF_B64_CHARS + 1)
    with pytest.raises(PDFReferenceTranslationError) as exc:
        _validate_translated_pdf(big)
    assert exc.value.status_code == 502
    assert exc.value.detail.code == "BABELDOC_TRANSLATION_FAILED"


def test_validate_translated_pdf_invalid_base64_rejected():
    # Not valid base64 -> decode error -> 502.
    with pytest.raises(PDFReferenceTranslationError) as exc:
        _validate_translated_pdf("!!!not-valid-base64!!!")
    assert exc.value.status_code == 502


def test_validate_translated_pdf_non_pdf_magic_rejected():
    # Valid base64 but content is not a PDF (%PDF marker missing).
    payload = base64.b64encode(b"hello world, not a pdf").decode()
    with pytest.raises(PDFReferenceTranslationError) as exc:
        _validate_translated_pdf(payload)
    assert exc.value.status_code == 502


def test_validate_translated_pdf_valid_returns_bytes():
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF"
    encoded = base64.b64encode(pdf).decode()
    result = _validate_translated_pdf(encoded)
    assert result == pdf


# ===========================================================================
# OCR (_process_mistral) — httpx error / status branches via MockTransport
# ===========================================================================
@pytest.mark.asyncio
async def test_mistral_4xx_raises_mistral_ocr_error(patch_httpx):
    patch_httpx(lambda: _mock_client(status=422, json_body={"error": "bad request"}))
    svc = OCRService()
    with pytest.raises(MistralOCRError) as exc:
        await svc._process_mistral(b"%PDF-1.4", "application/pdf")
    assert exc.value.status_code == 422
    assert isinstance(exc.value, OCRError)


def _sequence_client(statuses: list[int], headers: dict[str, str] | None = None):
    """Client whose Nth request returns statuses[N] (last one repeats); counts calls."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses[min(len(calls), len(statuses) - 1)]
        calls.append(status)
        body = {"pages": [{"index": 0, "markdown": "ok"}]} if status == 200 else {"e": "x"}
        return httpx.Response(status, json=body, headers=headers or {})

    return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler)), calls


@pytest.fixture
def no_sleep(monkeypatch):
    """Record asyncio.sleep delays instead of waiting (429 backoff)."""
    delays: list[float] = []

    async def _record(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.services.ocr_service.asyncio.sleep", _record)
    return delays


@pytest.mark.asyncio
async def test_mistral_429_retries_then_succeeds(patch_httpx, no_sleep):
    client, calls = _sequence_client([429, 200])
    patch_httpx(lambda: client)
    pages = await OCRService()._process_mistral(b"%PDF-1.4", "application/pdf")
    assert pages[0]["text"] == "ok"
    assert calls == [429, 200]
    assert no_sleep == [1.0]


@pytest.mark.asyncio
async def test_mistral_429_exhausted_raises_with_retry_after(patch_httpx, no_sleep):
    client, calls = _sequence_client([429], headers={"retry-after": "30"})
    patch_httpx(lambda: client)
    with pytest.raises(MistralOCRError) as exc:
        await OCRService()._process_mistral(b"%PDF-1.4", "application/pdf")
    assert exc.value.is_rate_limited
    assert exc.value.retry_after == 30.0
    assert len(calls) == 3  # 1 attempt + 2 retries
    assert no_sleep == [4.0, 4.0]  # Retry-After capped at _MISTRAL_429_MAX_DELAY_S


@pytest.mark.asyncio
async def test_mistral_other_4xx_is_not_retried(patch_httpx, no_sleep):
    client, calls = _sequence_client([401])
    patch_httpx(lambda: client)
    with pytest.raises(MistralOCRError) as exc:
        await OCRService()._process_mistral(b"%PDF-1.4", "application/pdf")
    assert not exc.value.is_rate_limited
    assert calls == [401]
    assert no_sleep == []


@pytest.mark.asyncio
async def test_mistral_5xx_raises_mistral_ocr_error(patch_httpx):
    patch_httpx(lambda: _mock_client(status=503, json_body={"error": "unavailable"}))
    svc = OCRService()
    with pytest.raises(MistralOCRError) as exc:
        await svc._process_mistral(b"%PDF-1.4", "application/pdf")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_mistral_connect_error_propagates(patch_httpx):
    patch_httpx(lambda: _mock_client(raise_exc=httpx.ConnectError("refused")))
    svc = OCRService()
    with pytest.raises(httpx.ConnectError):
        await svc._process_mistral(b"%PDF-1.4", "application/pdf")


@pytest.mark.asyncio
async def test_mistral_timeout_propagates(patch_httpx):
    patch_httpx(lambda: _mock_client(raise_exc=httpx.TimeoutException("timed out")))
    svc = OCRService()
    with pytest.raises(httpx.TimeoutException):
        await svc._process_mistral(b"%PDF-1.4", "application/pdf")


# ===========================================================================
# Translation (translate_text) — httpx error / bad-shape branches
# ===========================================================================
@pytest.mark.asyncio
async def test_translate_text_http_error_raises(patch_httpx):
    patch_httpx(lambda: _mock_client(status=502, json_body={"error": "boom"}))
    svc = TranslationService()
    with pytest.raises(TranslationError):
        await svc.translate_text("hello", "en", "fr")


@pytest.mark.asyncio
async def test_translate_text_provider_failure_flag_raises(patch_httpx):
    # 200 OK but the provider payload reports success=false.
    patch_httpx(
        lambda: _mock_client(
            status=200, json_body={"success": False, "errors": ["nope"], "result": {}}
        )
    )
    svc = TranslationService()
    with pytest.raises(TranslationError):
        await svc.translate_text("hello", "en", "fr")


@pytest.mark.asyncio
async def test_translate_text_unexpected_shape_raises(patch_httpx):
    # 200 OK but `result` is not a dict.
    patch_httpx(
        lambda: _mock_client(status=200, json_body={"success": True, "result": "not-a-dict"})
    )
    svc = TranslationService()
    with pytest.raises(TranslationError):
        await svc.translate_text("hello", "en", "fr")
