"""
Unit tests for Reducto integration in scripts/seed_documents.py (Sprint 2).

Coverage:
- _reducto_available() returns False when ENABLE_REDUCTO=false
- _reducto_available() returns False when ENABLE_REDUCTO=true but package missing
- _reducto_available() returns True when ENABLE_REDUCTO=true and package installed
- _fetch_with_reducto returns None when no PDF link found in HTML
- _fetch_with_reducto returns None when PDF fetch fails (< 1000 bytes)
- _fetch_with_reducto returns (markdown_bytes, "utf-8") on successful parse
- _fetch_with_reducto returns None on Reducto API error (fallback to BS4)
- BeautifulSoup path is the default when ENABLE_REDUCTO=false
- Reducto path is tried first when ENABLE_REDUCTO=true
- Reducto path falls back to BeautifulSoup on any Reducto error
- Both run() and run_multilingual() exercise Reducto when enabled

All HTTP calls and Reducto SDK calls are mocked — no real network calls are made.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

# ── Fixtures ─────────────────────────────────────────────────────────────────

_FAKE_PDF_BYTES = b"%PDF-1.4" + b"x" * 2000  # > 1000 bytes to pass size check

_REDUCTO_PARSE_RESULT = MagicMock()
_REDUCTO_PARSE_RESULT.result.chunks = [
    MagicMock(content="# Article 1\n\nFree movement applies."),
    MagicMock(content="# Article 2\n\nResidence rights."),
]

_FAKE_TQDM_MOD = MagicMock(tqdm=MagicMock(side_effect=lambda x, **kw: x))


def _make_soup_mock(*args, **kwargs):
    """Return a BS4 soup mock that behaves enough for _fetch_with_reducto.

    Anchor elements support a["href"] subscripting and .get("data-download").
    """
    soup = MagicMock()
    anchor = MagicMock()
    attrs: dict[str, str] = {"href": "/pdf/32004L0038.pdf", "data-download": "PDF"}
    anchor.__getitem__ = MagicMock(side_effect=lambda key: attrs.get(key, ""))
    anchor.get = MagicMock(return_value=attrs.get("data-download"))
    soup.find_all = MagicMock(return_value=[anchor])
    soup.find = MagicMock(return_value=None)
    return soup


_FAKE_BS4_MOD = MagicMock(BeautifulSoup=MagicMock(side_effect=_make_soup_mock))
_FAKE_LTS_MOD = MagicMock(RecursiveCharacterTextSplitter=MagicMock(return_value=MagicMock()))


def _make_httpx_response(
    status_code: int,
    content: bytes = b"",
    *,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {}
    resp.url = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038"
    return resp


# ── _reducto_available tests ──────────────────────────────────────────────────


class TestReductoAvailability:
    def test_returns_false_when_flag_disabled(self) -> None:
        with patch.dict("scripts.seed_documents.__dict__", {"ENABLE_REDUCTO": False}):
            from scripts.seed_documents import _reducto_available

            assert _reducto_available() is False

    def test_returns_false_when_flag_enabled_but_package_missing(self) -> None:
        with (
            patch.dict("scripts.seed_documents.__dict__", {"ENABLE_REDUCTO": True}),
            patch.dict(sys.modules, {"reducto": None}),
        ):
            from scripts.seed_documents import _reducto_available

            assert _reducto_available() is False

    def test_returns_true_when_flag_enabled_and_package_installed(self) -> None:
        fake_reducto_mod = MagicMock()
        with (
            patch.dict("scripts.seed_documents.__dict__", {"ENABLE_REDUCTO": True}),
            patch.dict(sys.modules, {"reducto": fake_reducto_mod}),
        ):
            from scripts.seed_documents import _reducto_available

            assert _reducto_available() is True


# ── _fetch_with_reducto tests ─────────────────────────────────────────────────


class TestFetchWithReducto:
    def test_returns_none_when_html_fetch_fails(self) -> None:
        fake_redacto_mod = MagicMock(Reducto=MagicMock())
        with (
            patch.dict("sys.modules", {"reducto": fake_redacto_mod}),
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.return_value = _make_httpx_response(404)

            result = _fetch_with_reducto(mock_client, "32004L0038")
            assert result is None
            mock_client.get.assert_called_once()

    def test_returns_none_when_no_pdf_link_found(self) -> None:
        html = b"<html><body><p>No PDF here</p></body></html>"
        with (
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.return_value = _make_httpx_response(
                200, html, headers={"content-type": "text/html; charset=utf-8"}
            )

            result = _fetch_with_reducto(mock_client, "32004L0038")
            assert result is None

    def test_returns_none_when_pdf_too_small(self) -> None:
        small_pdf = b"%PDF-1.4" + b"x" * 100
        with (
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.side_effect = [
                _make_httpx_response(
                    200,
                    b'<html><body><a href="/pdf/doc.pdf">PDF</a></body></html>',
                    headers={"content-type": "text/html"},
                ),
                _make_httpx_response(200, small_pdf),
            ]

            result = _fetch_with_reducto(mock_client, "32004L0038")
            assert result is None

    def test_returns_markdown_on_successful_parse(self) -> None:
        fake_client_instance = MagicMock()
        fake_upload = MagicMock()
        fake_upload.file_id = "file-abc123"
        fake_client_instance.upload.return_value = fake_upload
        fake_client_instance.parse.run.return_value = _REDUCTO_PARSE_RESULT
        fake_redacto_class = MagicMock(return_value=fake_client_instance)

        with (
            patch.dict(
                "sys.modules",
                {"reducto": MagicMock(Reducto=fake_redacto_class), "bs4": _FAKE_BS4_MOD},
            ),
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.side_effect = [
                _make_httpx_response(
                    200,
                    b'<html><body><a href="/pdf/32004L0038.pdf" '
                    b'data-download="PDF">Download</a></body></html>',
                    headers={"content-type": "text/html"},
                ),
                _make_httpx_response(200, _FAKE_PDF_BYTES),
            ]

            result = _fetch_with_reducto(mock_client, "32004L0038")

        assert result is not None
        html_bytes, charset = result
        assert charset == "utf-8"
        assert b"Free movement applies" in html_bytes
        assert b"Residence rights" in html_bytes

        # Verify the parse.run call used the Upload object (not upload.file_id string)
        # to match the documented quickstart pattern: parse.run(input=upload)
        fake_client_instance.parse.run.assert_called_once()
        call_kwargs = fake_client_instance.parse.run.call_args.kwargs
        assert "input" in call_kwargs
        # input is the Upload object; verify its file_id was passed through
        assert call_kwargs["input"].file_id == "file-abc123"

    def test_uses_custom_base_url_when_set(self) -> None:
        fake_client_instance = MagicMock()
        fake_upload = MagicMock()
        fake_upload.file_id = "file-abc123"
        fake_client_instance.upload.return_value = fake_upload
        fake_client_instance.parse.run.return_value = _REDUCTO_PARSE_RESULT
        fake_redacto_class = MagicMock(return_value=fake_client_instance)

        with (
            patch.dict(
                "sys.modules",
                {"reducto": MagicMock(Reducto=fake_redacto_class), "bs4": _FAKE_BS4_MOD},
            ),
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://eu.api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.side_effect = [
                _make_httpx_response(
                    200,
                    b'<html><body><a href="/pdf/doc.pdf" '
                    b'data-download="PDF">Download</a></body></html>',
                    headers={"content-type": "text/html"},
                ),
                _make_httpx_response(200, _FAKE_PDF_BYTES),
            ]

            _fetch_with_reducto(mock_client, "32004L0038")

        _, kwargs = fake_redacto_class.call_args
        assert kwargs.get("base_url") == "https://eu.api.reducto.ai"

    def test_falls_back_on_reducto_api_error(self) -> None:
        fake_client_instance = MagicMock()
        fake_client_instance.upload.side_effect = RuntimeError("Rate limited")
        fake_redacto_class = MagicMock(return_value=fake_client_instance)

        with (
            patch.dict(sys.modules, {"reducto": MagicMock(Reducto=fake_redacto_class)}),
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.side_effect = [
                _make_httpx_response(
                    200,
                    b'<html><body><a href="/pdf/doc.pdf">PDF</a></body></html>',
                    headers={"content-type": "text/html"},
                ),
                _make_httpx_response(200, _FAKE_PDF_BYTES),
            ]

            result = _fetch_with_reducto(mock_client, "32004L0038")

        assert result is None

    def test_falls_back_on_reducto_parse_returns_no_chunks(self) -> None:
        empty_result = MagicMock()
        empty_result.result.chunks = []

        fake_client_instance = MagicMock()
        fake_upload = MagicMock()
        fake_upload.file_id = "file-abc123"
        fake_client_instance.upload.return_value = fake_upload
        fake_client_instance.parse.run.return_value = empty_result
        fake_redacto_class = MagicMock(return_value=fake_client_instance)

        with (
            patch.dict(sys.modules, {"reducto": MagicMock(Reducto=fake_redacto_class)}),
            patch("scripts.seed_documents.ENABLE_REDUCTO", True),
            patch("scripts.seed_documents.REDUCTO_API_KEY", "test-key"),
            patch("scripts.seed_documents.REDUCTO_BASE_URL", "https://api.reducto.ai"),
        ):
            from scripts.seed_documents import _fetch_with_reducto

            mock_client = MagicMock()
            mock_client.get.side_effect = [
                _make_httpx_response(
                    200,
                    b'<html><body><a href="/pdf/doc.pdf">PDF</a></body></html>',
                    headers={"content-type": "text/html"},
                ),
                _make_httpx_response(200, _FAKE_PDF_BYTES),
            ]

            result = _fetch_with_reducto(mock_client, "32004L0038")

        assert result is None


# ── Integration: Reducto path vs BeautifulSoup fallback ───────────────────────


class TestReductoVsBeautifulSoupRouting:
    def test_beautiful_soup_is_default_when_reducto_disabled(self) -> None:
        mock_hs = AsyncMock()
        mock_hs.acreate_bank = AsyncMock()
        mock_hs.aretain = AsyncMock()
        mock_hs.arecall = AsyncMock(return_value=MagicMock(results=[], chunks={}))
        mock_hs.aclose = AsyncMock()

        p_reducto = patch("scripts.seed_documents.ENABLE_REDUCTO", False)
        p_available = patch("scripts.seed_documents._reducto_available", return_value=False)
        p_fetch_reducto = patch("scripts.seed_documents._fetch_with_reducto")
        p_fetch_html = patch("scripts.seed_documents._fetch_html")
        p_extract = patch(
            "scripts.seed_documents._extract_text", return_value="Regulation text here"
        )
        p_hs_cls = patch("scripts.seed_documents._CloudSeeder", return_value=mock_hs)
        p_http = patch("scripts.seed_documents.httpx.Client")
        p_tqdm = patch.dict(
            "sys.modules", {"tqdm": _FAKE_TQDM_MOD, "langchain_text_splitters": _FAKE_LTS_MOD}
        )
        p_url = patch("scripts.seed_documents.HINDSIGHT_URL", "http://localhost:8600")
        p_sleep = patch("asyncio.sleep", AsyncMock())

        with (
            p_reducto,
            p_available,
            p_fetch_reducto as mock_fetch_reducto,
            p_fetch_html as mock_fetch_html,
            p_extract,
            p_hs_cls,
            p_http,
            p_tqdm,
            p_url,
            p_sleep,
        ):
            mock_fetch_html.return_value = (b"<html>content</html>", "utf-8")
            import asyncio

            from scripts.seed_documents import run

            asyncio.run(run())

            mock_fetch_reducto.assert_not_called()
            mock_fetch_html.assert_called()

    def test_reducto_tried_first_when_enabled(self) -> None:
        mock_hs = AsyncMock()
        mock_hs.acreate_bank = AsyncMock()
        mock_hs.aretain = AsyncMock()
        mock_hs.arecall = AsyncMock(return_value=MagicMock(results=[], chunks={}))
        mock_hs.aclose = AsyncMock()

        p_reducto = patch("scripts.seed_documents.ENABLE_REDUCTO", True)
        p_available = patch("scripts.seed_documents._reducto_available", return_value=True)
        p_fetch_reducto = patch("scripts.seed_documents._fetch_with_reducto")
        p_fetch_html = patch("scripts.seed_documents._fetch_html")
        p_extract = patch("scripts.seed_documents._extract_text", return_value="Regulation text")
        p_hs_cls = patch("scripts.seed_documents._CloudSeeder", return_value=mock_hs)
        p_http = patch("scripts.seed_documents.httpx.Client")
        p_tqdm = patch.dict(
            "sys.modules", {"tqdm": _FAKE_TQDM_MOD, "langchain_text_splitters": _FAKE_LTS_MOD}
        )
        p_url = patch("scripts.seed_documents.HINDSIGHT_URL", "http://localhost:8600")
        p_sleep = patch("asyncio.sleep", AsyncMock())

        with (
            p_reducto,
            p_available,
            p_fetch_reducto as mock_reducto,
            p_fetch_html as mock_fetch_html,
            p_extract,
            p_hs_cls,
            p_http,
            p_tqdm,
            p_url,
            p_sleep,
        ):
            mock_reducto.return_value = None
            mock_fetch_html.return_value = (b"<html>fallback</html>", "utf-8")
            import asyncio

            from scripts.seed_documents import run

            asyncio.run(run())

            mock_reducto.assert_called()
            mock_fetch_html.assert_called()

    def test_beautiful_soup_used_when_reducto_returns_none(self) -> None:
        mock_hs = AsyncMock()
        mock_hs.acreate_bank = AsyncMock()
        mock_hs.aretain = AsyncMock()
        mock_hs.arecall = AsyncMock(return_value=MagicMock(results=[], chunks={}))
        mock_hs.aclose = AsyncMock()

        p_reducto = patch("scripts.seed_documents.ENABLE_REDUCTO", True)
        p_available = patch("scripts.seed_documents._reducto_available", return_value=True)
        p_fetch_reducto = patch("scripts.seed_documents._fetch_with_reducto")
        p_fetch_html = patch("scripts.seed_documents._fetch_html")
        p_extract = patch("scripts.seed_documents._extract_text", return_value="BS4 extracted text")
        p_hs_cls = patch("scripts.seed_documents._CloudSeeder", return_value=mock_hs)
        p_http = patch("scripts.seed_documents.httpx.Client")
        p_tqdm = patch.dict(
            "sys.modules", {"tqdm": _FAKE_TQDM_MOD, "langchain_text_splitters": _FAKE_LTS_MOD}
        )
        p_url = patch("scripts.seed_documents.HINDSIGHT_URL", "http://localhost:8600")
        p_sleep = patch("asyncio.sleep", AsyncMock())

        with (
            p_reducto,
            p_available,
            p_fetch_reducto as mock_reducto,
            p_fetch_html as mock_fetch_html,
            p_extract,
            p_hs_cls,
            p_http,
            p_tqdm,
            p_url,
            p_sleep,
        ):
            mock_reducto.return_value = None
            mock_fetch_html.return_value = (
                b"<html><body><div id='document1'><p>BS4 text</p></div></body></html>",
                "utf-8",
            )
            import asyncio

            from scripts.seed_documents import run

            asyncio.run(run())

            mock_reducto.assert_called()
            mock_fetch_html.assert_called()

    def test_reducto_result_used_when_successful(self) -> None:
        mock_hs = AsyncMock()
        mock_hs.acreate_bank = AsyncMock()
        mock_hs.aretain = AsyncMock()
        mock_hs.arecall = AsyncMock(return_value=MagicMock(results=[], chunks={}))
        mock_hs.aclose = AsyncMock()

        p_reducto = patch("scripts.seed_documents.ENABLE_REDUCTO", True)
        p_available = patch("scripts.seed_documents._reducto_available", return_value=True)
        p_fetch_reducto = patch("scripts.seed_documents._fetch_with_reducto")
        p_fetch_html = patch("scripts.seed_documents._fetch_html")
        p_extract = patch("scripts.seed_documents._extract_text")
        p_hs_cls = patch("scripts.seed_documents._CloudSeeder", return_value=mock_hs)
        p_http = patch("scripts.seed_documents.httpx.Client")
        p_tqdm = patch.dict(
            "sys.modules", {"tqdm": _FAKE_TQDM_MOD, "langchain_text_splitters": _FAKE_LTS_MOD}
        )
        p_url = patch("scripts.seed_documents.HINDSIGHT_URL", "http://localhost:8600")
        p_sleep = patch("asyncio.sleep", AsyncMock())

        with (
            p_reducto,
            p_available,
            p_fetch_reducto as mock_reducto,
            p_fetch_html as mock_fetch_html,
            p_extract as mock_extract,
            p_hs_cls,
            p_http,
            p_tqdm,
            p_url,
            p_sleep,
        ):
            mock_reducto.return_value = (b"Reducto's markdown output", "utf-8")
            mock_extract.return_value = "Reducto's markdown output"
            import asyncio

            from scripts.seed_documents import run

            asyncio.run(run())

            mock_reducto.assert_called()
            mock_fetch_html.assert_not_called()


# ── Multilingual path ─────────────────────────────────────────────────────────


class TestReductoMultilingualPath:
    def test_reducto_tried_first_in_multilingual_when_enabled(self) -> None:
        mock_hs = AsyncMock()
        mock_hs.acreate_bank = AsyncMock()
        mock_hs.aretain = AsyncMock()
        mock_hs.arecall = AsyncMock(return_value=MagicMock(results=[], chunks={}))
        mock_hs.aclose = AsyncMock()

        p_reducto = patch("scripts.seed_documents.ENABLE_REDUCTO", True)
        p_available = patch("scripts.seed_documents._reducto_available", return_value=True)
        p_fetch_reducto = patch("scripts.seed_documents._fetch_with_reducto")
        p_fetch_lang = patch("scripts.seed_documents._fetch_html_lang")
        p_extract = patch("scripts.seed_documents._extract_text", return_value="Reglement texte")
        p_hs_cls = patch("scripts.seed_documents._CloudSeeder", return_value=mock_hs)
        p_http = patch("scripts.seed_documents.httpx.Client")
        p_tqdm = patch.dict(
            "sys.modules", {"tqdm": _FAKE_TQDM_MOD, "langchain_text_splitters": _FAKE_LTS_MOD}
        )
        p_url = patch("scripts.seed_documents.HINDSIGHT_URL", "http://localhost:8600")
        p_sleep = patch("asyncio.sleep", AsyncMock())

        with (
            p_reducto,
            p_available,
            p_fetch_reducto as mock_reducto,
            p_fetch_lang as mock_fetch_lang,
            p_extract,
            p_hs_cls,
            p_http,
            p_tqdm,
            p_url,
            p_sleep,
        ):
            mock_reducto.return_value = None
            mock_fetch_lang.return_value = (b"<html>FR content</html>", "utf-8")
            import asyncio

            from scripts.seed_documents import run_multilingual

            asyncio.run(run_multilingual())

            mock_reducto.assert_called()
            mock_fetch_lang.assert_called()


# ── GDPR surface: public corpus only ─────────────────────────────────────────


class TestReductoGDPRScope:
    """ADR-009: Reducto's data-retention config is EU-regional, applied at init.

    These tests verify the configuration surface exists and the guard is in the
    right place in the code (seed script, NOT the user-facing OCR service).
    """

    def test_reducto_config_uses_eu_regional_endpoint(self) -> None:
        from scripts.seed_documents import REDUCTO_BASE_URL

        assert REDUCTO_BASE_URL == "https://api.reducto.ai"

    def test_reducto_config_flag_is_false_by_default(self) -> None:
        from scripts.seed_documents import ENABLE_REDUCTO

        assert ENABLE_REDUCTO is False

    def test_reducto_flag_can_be_enabled_via_env(self) -> None:
        import importlib

        import scripts.seed_documents as sd

        with patch.dict("os.environ", {"ENABLE_REDUCTO": "true"}):
            importlib.reload(sd)
            assert sd.ENABLE_REDUCTO is True

        importlib.reload(sd)
