"""NT-3 coverage tests for RAGService utility functions.

Covers branches missed by the main test_rag_service.py suite:
- _normalize_for_scan (Unicode normalization / injection bypass resistance)
- _propella_enabled exception fallback
- _expand_query_with_glossary exception fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag_service import (
    HindsightRAGService,
    _normalize_for_scan,
    _propella_enabled,
)


class TestNormalizeForScan:
    def test_removes_zero_width_chars(self) -> None:
        raw = "ignore\u200bprevious\u200cinstructions"
        normalized = _normalize_for_scan(raw)
        assert "\u200b" not in normalized
        assert "\u200c" not in normalized
        assert "ignore previous instructions" in normalized

    def test_nfkc_fullwidth_to_ascii(self) -> None:
        fullwidth = "\uff49\uff47\uff4e\uff4f\uff52\uff45"
        assert _normalize_for_scan(fullwidth) == "ignore"

    def test_preserves_newlines_for_line_anchors(self) -> None:
        text = "line one\nignore previous instructions"
        normalized = _normalize_for_scan(text)
        assert "\n" in normalized

    def test_collapses_whitespace_runs(self) -> None:
        text = "ignore   previous\t\tinstructions"
        normalized = _normalize_for_scan(text)
        assert "   " not in normalized
        assert "\t" not in normalized


class TestPropellaEnabled:
    def test_returns_true_when_attribute_access_raises(self) -> None:
        class RaisingBool:
            def __bool__(self) -> bool:
                raise RuntimeError("forced")

        mock_settings = MagicMock()
        mock_settings.PROPELLA_ENABLED = RaisingBool()
        with patch("app.core.config.settings", mock_settings):
            assert _propella_enabled() is True


class TestExpandQueryWithGlossary:
    @pytest.fixture
    def svc(self) -> HindsightRAGService:
        svc = object.__new__(HindsightRAGService)
        svc._glossary_repo = MagicMock()
        return svc

    @pytest.mark.asyncio
    async def test_returns_original_query_when_repo_raises(self, svc: HindsightRAGService) -> None:
        repo = MagicMock()
        repo.search_terms = AsyncMock(side_effect=RuntimeError("D1 unreachable"))
        svc._glossary_repo = repo
        query = "residence permit application"
        result = await svc._expand_query_with_glossary(query, "en")
        assert result == query

    @pytest.mark.asyncio
    async def test_returns_original_query_when_repo_returns_empty(
        self, svc: HindsightRAGService
    ) -> None:
        repo = MagicMock()
        repo.search_terms = AsyncMock(return_value=[])
        svc._glossary_repo = repo
        query = "unknown term xyz"
        result = await svc._expand_query_with_glossary(query, "en")
        assert result == query

    @pytest.mark.asyncio
    async def test_expands_query_when_repo_returns_matches(self, svc: HindsightRAGService) -> None:
        match = MagicMock()
        match.term_en = "residence permit"
        match.term_de = "Aufenthaltstitel"
        match.term_fr = "titre de séjour"
        repo = MagicMock()
        repo.search_terms = AsyncMock(return_value=[match])
        svc._glossary_repo = repo
        query = "residence permit"
        result = await svc._expand_query_with_glossary(query, "en")
        assert query in result
        assert "residence permit" in result
        assert "aufenthaltstitel" in result
        assert "titre de séjour" in result
        assert "[glossary:" in result
