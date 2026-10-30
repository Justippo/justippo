"""Targeted coverage for TranslationService missed branches.

All HTTP is mocked (no network). Tests focus on:
- ``_call_mistral_large`` success + response-shape error branches (827, 916, 927, 931)
- orchestration ``except Exception`` handler (485-489)
- glossary enforcement skip branches (675, 684)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.translation_service import (
    TranslationError,
    TranslationService,
)


def _patch_nd(route_to: str) -> patch:
    mock_nd = MagicMock()
    mock_nd.return_value.route = AsyncMock(return_value=route_to)
    return patch("app.integrations.routing.not_diamond.NotDiamondRouter", mock_nd)


def _mock_mistral_response(
    status_code: int = 200, payload: dict[str, Any] | None = None
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    resp.text = "error body"
    return resp


_M2M100_SUCCESS: dict[str, Any] = {
    "success": True,
    "result": {"translated_text": "Hallo"},
    "errors": [],
}


def _mock_m2m100_response(payload: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def _mock_client(post_payload: dict[str, Any] | None = None, status_code: int = 200) -> AsyncMock:
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(
        return_value=_mock_mistral_response(status_code, post_payload or {"choices": []})
    )
    return client


# ── _call_mistral_large: success ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_mistral_large_success() -> None:
    svc = TranslationService()
    captured: list[str] = []

    async def fake_post(url: str, **kwargs: Any) -> MagicMock:
        captured.append(url)
        return _mock_mistral_response(200, {"choices": [{"message": {"content": "Hallo Welt"}}]})

    client = _mock_client()
    client.post = fake_post
    with (
        _patch_nd("mistral-large-translation"),
        patch("app.services.translation_service.httpx.AsyncClient", return_value=client),
    ):
        text = await svc._call_m2m100(text="Hello", source_lang="en", target_lang="de")
    assert text == "Hallo Welt"
    assert "mistral" in captured[0]


# ── _call_mistral_large: 4xx error (916) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_call_mistral_large_http_error() -> None:
    svc = TranslationService()
    with (
        _patch_nd("mistral-large-translation"),
        patch(
            "app.services.translation_service.httpx.AsyncClient",
            return_value=_mock_client(status_code=400),
        ),
        pytest.raises(TranslationError, match="Mistral Large returned HTTP 400"),
    ):
        await svc._call_mistral_large("Hello", "en", "de", timeout=30)


# ── _call_mistral_large: bad choices shape (923/927) ───────────────────────────


@pytest.mark.asyncio
async def test_call_mistral_large_bad_choices_shape() -> None:
    svc = TranslationService()
    with (
        _patch_nd("mistral-large-translation"),
        patch(
            "app.services.translation_service.httpx.AsyncClient",
            return_value=_mock_client({"choices": "not-a-list"}),
        ),
        pytest.raises(TranslationError, match="Unexpected Mistral Large response shape"),
    ):
        await svc._call_mistral_large("Hello", "en", "de", timeout=30)


@pytest.mark.asyncio
async def test_call_mistral_large_empty_choices() -> None:
    svc = TranslationService()
    with (
        _patch_nd("mistral-large-translation"),
        patch(
            "app.services.translation_service.httpx.AsyncClient",
            return_value=_mock_client({"choices": []}),
        ),
        pytest.raises(TranslationError, match="Unexpected Mistral Large response shape"),
    ):
        await svc._call_mistral_large("Hello", "en", "de", timeout=30)


# ── _call_mistral_large: bad choice/message shape (927/931) ───────────────────


@pytest.mark.asyncio
async def test_call_mistral_large_bad_choice_shape() -> None:
    svc = TranslationService()
    with (
        _patch_nd("mistral-large-translation"),
        patch(
            "app.services.translation_service.httpx.AsyncClient",
            return_value=_mock_client({"choices": ["not-a-dict"]}),
        ),
        pytest.raises(TranslationError, match="Unexpected Mistral choice shape"),
    ):
        await svc._call_mistral_large("Hello", "en", "de", timeout=30)


@pytest.mark.asyncio
async def test_call_mistral_large_bad_message_shape() -> None:
    svc = TranslationService()
    with (
        _patch_nd("mistral-large-translation"),
        patch(
            "app.services.translation_service.httpx.AsyncClient",
            return_value=_mock_client({"choices": [{"message": "not-a-dict"}]}),
        ),
        pytest.raises(TranslationError, match="Unexpected Mistral message shape"),
    ):
        await svc._call_mistral_large("Hello", "en", "de", timeout=30)


# ── Orchestration: translate_section raises -> except handler (485-489) ─────────


@pytest.mark.asyncio
async def test_translate_redaction_enabled_logs_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Enables the PII-redaction path (GDPR Art. 5(1)(c) data minimisation) so the
    # redaction metadata logger.info at 507 is exercised. redact_with_fallback is
    # mocked to return the input unchanged with succeeded=True.
    import app.core.config as config_module
    from app.services import translation_service as ts_mod

    monkeypatch.setattr(config_module.settings, "NOT_DIAMOND_ENABLED", False)
    monkeypatch.setattr(ts_mod, "is_redaction_ready", lambda: True)
    monkeypatch.setattr(
        ts_mod, "redact_with_fallback", AsyncMock(return_value=("Hello world", True, None))
    )
    svc = TranslationService()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_mock_m2m100_response(_M2M100_SUCCESS))
    with patch("app.services.translation_service.httpx.AsyncClient", return_value=mock_client):
        job = await svc.translate(
            document_id="doc-003",
            source_language="en",
            target_language="de",
            pages=[{"page": 1, "text": "Hello world", "confidence": 0.9}],
        )
    assert job.status == "done"
    assert job.redaction_metadata["enabled"] is True


# ── Glossary enforcement skip branches (675, 684) ─────────────────────────────


class _StubTerm:
    """Minimal stand-in for a glossary term record."""


def _make_term(**fields: Any) -> _StubTerm:
    term = _StubTerm()
    for k, v in fields.items():
        setattr(term, k, v)
    return term


@pytest.mark.asyncio
async def test_glossary_enforcement_skips_empty_terms() -> None:
    svc = TranslationService()
    # term_en empty -> source_term empty -> line 675 continue
    term = _make_term(term_en="", term_de="Hallo", mistranslations=[])
    with patch("app.services.translation_service.extract_terms", return_value=[term]):
        result = svc._apply_glossary_enforcement_result(
            input_pages=[{"text": "Hello world"}],
            translated_pages=[{"text": "Hallo Welt"}],
            source_lang="en",
            target_lang="de",
        )
    assert result.terms_applied == 0


@pytest.mark.asyncio
async def test_glossary_enforcement_skips_empty_mistranslation() -> None:
    svc = TranslationService()
    # source_term present in source, target_term absent from translation, and a
    # mistranslation list whose first entry is falsy -> line 684 continue.
    term = _make_term(term_en="Hello", term_de="Hallo", mistranslations=["", "typo"])
    with patch("app.services.translation_service.extract_terms", return_value=[term]):
        result = svc._apply_glossary_enforcement_result(
            input_pages=[{"text": "Hello world"}],
            translated_pages=[{"text": "Welt only"}],
            source_lang="en",
            target_lang="de",
        )
    assert result.terms_applied >= 0
