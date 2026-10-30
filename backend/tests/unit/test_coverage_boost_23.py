"""Coverage boost batch 23 — glossary + stats (eurostat) D1-backed branches via fake D1.

DRY: reuses ``tests.unit.d1_fakes.InMemoryD1Binding`` to drive the REAL
``D1Client``/``GlossaryRepo``/``EurostatRepo`` code paths (the production
branches unreachable without a D1 binding). Confirms Cloudflare's documented
constraint: D1 state is only assertable inside the Workers runtime.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request

from app.api.v1.endpoints import glossary as glossary_ep
from app.api.v1.endpoints import stats as stats_ep
from tests.unit.d1_fakes import InMemoryD1Binding


def _request_with_d1(binding: InMemoryD1Binding) -> Request:
    scope: dict[str, object] = {
        "type": "http",
        "headers": [],
        "env": SimpleNamespace(DB=binding),
    }
    return Request(scope)


# ─── glossary endpoint (GlossaryRepo D1 branches) ─────────────────


class TestGlossaryD1:
    async def test_lookup_all_terms_reads_d1(self) -> None:
        binding = InMemoryD1Binding()
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(binding)
        await repo.upsert_terms(
            [{"term_en": "residence permit", "definition": "auth to reside"}],
            doc_id="doc-1",
            lang="en",
        )
        request = _request_with_d1(binding)
        resp = await glossary_ep._lookup_terms(request, "legal", None, None, None, 50)
        assert resp.count == 1
        assert resp.terms[0].term_en == "residence permit"

    async def test_search_terms_reads_d1(self) -> None:
        binding = InMemoryD1Binding()
        from app.repositories.glossary_repo import GlossaryRepo

        repo = GlossaryRepo(binding)
        await repo.upsert_terms(
            [{"term_en": "work permit", "definition": "auth to work"}],
            doc_id="doc-2",
            lang="en",
        )
        request = _request_with_d1(binding)
        resp = await glossary_ep._lookup_terms(request, "legal", "en", None, "work", 50)
        assert resp.count == 1
        assert resp.terms[0].term_en == "work permit"

    async def test_search_terms_no_match_returns_empty(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        resp = await glossary_ep._lookup_terms(request, "legal", "en", None, "zzznomatch", 50)
        assert resp.count == 0

    async def test_extract_persists_to_d1(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        from app.api.v1.endpoints.glossary import GlossaryExtractRequest

        # The extraction step uses the live BAML/AI Gateway LLM; mock it so the
        # D1 persist path (insert_terms -> GlossaryRepo.upsert_terms) is exercised.
        canned = [
            SimpleNamespace(
                term_en="residence permit",
                term_de="",
                term_fr="",
                definition="x",
                mistranslations=None,
                confidence=1.0,
            )
        ]
        with patch("app.api.v1.endpoints.glossary.extract_terms", return_value=canned):
            payload = GlossaryExtractRequest(
                text="You need a residence permit to live here.",
                source_lang="en",
                doc_id="doc-3",
                persist=True,
            )
            resp = await glossary_ep.extract_glossary_terms(request, payload)
        assert resp.extracted_count >= 1
        assert "glossary_terms" in binding._tables
        assert len(binding._tables["glossary_terms"]) >= 1

    async def test_invalid_domain_raises_422(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        with pytest.raises(HTTPException) as exc_info:
            await glossary_ep._lookup_terms(request, "medical", None, None, None, 50)
        assert exc_info.value.status_code == 422


# ─── stats / eurostat endpoint (EurostatRepo D1 branches) ────────


class TestStatsEurostatD1:
    async def test_fresh_snapshot_served_from_d1(self) -> None:
        binding = InMemoryD1Binding()
        from app.repositories.eurostat_repo import EurostatRepo

        snapshot = {"value": {"DE": 100}}
        repo = EurostatRepo(binding)
        await repo.save_snapshot(snapshot)
        request = _request_with_d1(binding)
        resp = await stats_ep.get_migration_stats(request)
        assert resp.status_code == 200
        assert json.loads(bytes(resp.body))["value"] == {"DE": 100}

    async def test_stale_snapshot_triggers_eurostat_fetch(self) -> None:
        binding = InMemoryD1Binding()
        from app.repositories.eurostat_repo import EurostatRepo

        # Save a snapshot with a valid shape but an expired TTL (old fetched_at).
        repo = EurostatRepo(binding)
        await repo.save_snapshot({"value": {"FR": 5}}, ttl_seconds=86400)
        key = next(iter(binding._tables["eurostat_snapshots"]))
        binding._tables["eurostat_snapshots"][key]["fetched_at"] = int(time.time()) - 200000

        fresh = {"value": {"DE": 999}}
        request = _request_with_d1(binding)
        with patch("app.api.v1.endpoints.stats.httpx.AsyncClient") as mock_client:
            mock_resp = mock_client.return_value.__aenter__.return_value.get.return_value
            mock_resp.status_code = 200
            mock_resp.json = lambda: fresh
            resp = await stats_ep.get_migration_stats(request)
        assert resp.status_code == 200
        assert json.loads(bytes(resp.body))["value"] == {"DE": 999}

    async def test_eurostat_fetch_failure_falls_back_to_last_snapshot(self) -> None:
        binding = InMemoryD1Binding()
        from app.repositories.eurostat_repo import EurostatRepo

        repo = EurostatRepo(binding)
        await repo.save_snapshot({"value": {"IT": 42}}, ttl_seconds=86400)
        key = next(iter(binding._tables["eurostat_snapshots"]))
        binding._tables["eurostat_snapshots"][key]["fetched_at"] = int(time.time()) - 200000
        request = _request_with_d1(binding)
        with patch("app.api.v1.endpoints.stats.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = RuntimeError(
                "network down"
            )
            resp = await stats_ep.get_migration_stats(request)
        assert resp.status_code == 200
        body = json.loads(bytes(resp.body))
        assert body["value"] == {"IT": 42}
        assert body["warning"] == "STALE_DATA"

    async def test_no_snapshot_and_fetch_fails_returns_503(self) -> None:
        binding = InMemoryD1Binding()
        request = _request_with_d1(binding)
        with patch("app.api.v1.endpoints.stats.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = RuntimeError(
                "network down"
            )
            resp = await stats_ep.get_migration_stats(request)
        assert resp.status_code == 503
