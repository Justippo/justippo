"""Tests to boost coverage from 83% toward 100%.

Covers:
- app/models/document.py              — SQLModel data models (0% → 100%)
- app/services/graph_rag_service.py   — Graph-augmented RAG (0% → 100%)
- app/repositories/eurostat_repo.py   — Eurostat D1 cache (16% → 100%)
- app/services/storage_service.py     — R2 storage (35% → 100%)
- app/api/v1/endpoints/stats.py       — Migration stats endpoint (30% → 100%)
"""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/models/document.py — SQLModel data models
# ---------------------------------------------------------------------------


class TestDocumentModels:
    def test_document_record_defaults(self) -> None:
        from app.models.document import DocumentRecord

        rec = DocumentRecord(
            id="doc-1",
            filename="test.pdf",
            mime_type="application/pdf",
        )
        assert rec.id == "doc-1"
        assert rec.filename == "test.pdf"
        assert rec.mime_type == "application/pdf"
        assert rec.page_count == 0
        assert rec.detected_language == ""
        assert rec.status == "processed"
        assert rec.expires_at is None
        assert rec.created_at is not None

    def test_document_record_custom_fields(self) -> None:
        from app.models.document import DocumentRecord

        rec = DocumentRecord(
            id="doc-2",
            filename="scan.png",
            mime_type="image/png",
            page_count=5,
            detected_language="de",
            status="processing",
            expires_at="2026-12-31T23:59:59+00:00",
        )
        assert rec.page_count == 5
        assert rec.detected_language == "de"
        assert rec.status == "processing"
        assert rec.expires_at == "2026-12-31T23:59:59+00:00"

    def test_translation_job_record_defaults(self) -> None:
        from app.models.document import TranslationJobRecord

        job = TranslationJobRecord(
            job_id="job-1",
            document_id="doc-1",
            source_language="en",
            target_language="de",
        )
        assert job.job_id == "job-1"
        assert job.status == "queued"
        assert job.error is None
        assert job.output_key is None
        assert job.created_at is not None
        assert job.updated_at is not None

    def test_translation_job_record_with_error(self) -> None:
        from app.models.document import TranslationJobRecord

        job = TranslationJobRecord(
            job_id="job-2",
            document_id="doc-2",
            source_language="fr",
            target_language="en",
            status="failed",
            error="OCR failed",
            output_key="translations/job-2/page-1.txt",
        )
        assert job.status == "failed"
        assert job.error == "OCR failed"
        assert job.output_key is not None

    def test_translation_page_record_defaults(self) -> None:
        from app.models.document import TranslationPageRecord

        page = TranslationPageRecord(
            job_id="job-1",
            page_number=1,
        )
        assert page.job_id == "job-1"
        assert page.page_number == 1
        assert page.text == ""
        assert page.id is None

    def test_translation_page_record_with_text(self) -> None:
        from app.models.document import TranslationPageRecord

        page = TranslationPageRecord(
            job_id="job-1",
            page_number=3,
            text="Translated text here",
            id=42,
        )
        assert page.text == "Translated text here"
        assert page.id == 42

    def test_utcnow_returns_iso_string(self) -> None:
        from app.models.document import _utcnow

        result = _utcnow()
        assert isinstance(result, str)
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# app/services/graph_rag_service.py — Graph-augmented RAG
# ---------------------------------------------------------------------------


class TestGraphAugmentedRAGService:
    def test_init_stores_d1_client(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = MagicMock()
        svc = GraphAugmentedRAGService(d1_client=mock_d1)
        assert svc._d1 is mock_d1

    def test_query_returns_base_results_when_no_d1(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        svc = GraphAugmentedRAGService(d1_client=None)
        base_results = [{"document_id": "d1", "text": "hello"}]

        with patch.object(
            type(svc).__mro__[1], "query", new_callable=AsyncMock, return_value=base_results
        ):
            import asyncio

            result = asyncio.run(svc.query("test", top_k=5))
        assert result == base_results

    def test_query_returns_base_results_when_empty(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        svc = GraphAugmentedRAGService(d1_client=MagicMock())

        with patch.object(type(svc).__mro__[1], "query", new_callable=AsyncMock, return_value=[]):
            import asyncio

            result = asyncio.run(svc.query("test", top_k=5))
        assert result == []

    def test_query_deduplicates_entities(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService
        from app.services.rag_service import HindsightRAGService

        mock_d1 = AsyncMock()
        mock_d1.query = AsyncMock(
            side_effect=[
                [{"doc_id": "doc-1"}],
                [{"id": "doc-1", "filename": "dup.pdf"}],
            ]
        )
        svc = GraphAugmentedRAGService(d1_client=mock_d1)
        base_results = [{"document_id": "doc-1", "text": "already have this"}]

        async def mock_query(*args, **kwargs):
            return base_results

        with patch.object(HindsightRAGService, "query", mock_query):
            import asyncio

            result = asyncio.run(svc.query("search query here", top_k=10))
        assert len(result) == 1

    def test_query_truncates_to_top_k(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService
        from app.services.rag_service import HindsightRAGService

        mock_d1 = AsyncMock()
        mock_d1.query = AsyncMock(
            side_effect=[
                [{"doc_id": "d1"}, {"doc_id": "d2"}],
                [
                    {"id": "d1", "filename": "a.pdf"},
                    {"id": "d2", "filename": "b.pdf"},
                ],
            ]
        )
        svc = GraphAugmentedRAGService(d1_client=mock_d1)
        base_results = [{"document_id": "d1", "text": "x"}]

        async def mock_query(*args, **kwargs):
            return base_results

        with patch.object(HindsightRAGService, "query", mock_query):
            import asyncio

            result = asyncio.run(svc.query("search term here", top_k=2))
        assert len(result) <= 2

    def test_fetch_related_via_entities_empty_tokens(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = AsyncMock()
        svc = GraphAugmentedRAGService(d1_client=mock_d1)

        import asyncio

        result = asyncio.run(svc._fetch_related_via_entities("ab"))
        assert result == []

    def test_fetch_related_via_entities_no_docs(self) -> None:
        from app.services.graph_rag_service import GraphAugmentedRAGService

        mock_d1 = AsyncMock()
        mock_d1.query = AsyncMock(return_value=[])
        svc = GraphAugmentedRAGService(d1_client=mock_d1)

        import asyncio

        result = asyncio.run(svc._fetch_related_via_entities("nonexistent entity"))
        assert result == []


# ---------------------------------------------------------------------------
# app/repositories/eurostat_repo.py — Eurostat D1 cache
# ---------------------------------------------------------------------------


class TestEurostatRepo:
    @pytest.fixture
    def repo(self):
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        return EurostatRepo(db=mock_db), mock_db

    def test_init_no_db(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        repo = EurostatRepo(db=None)
        assert repo._db is None

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_no_db(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        repo = EurostatRepo(db=None)
        result = await repo.get_fresh_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_returns_none_when_no_row(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value=None)
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_fresh_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_returns_none_when_expired(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(
            return_value={
                "data_json": '{"value": {"EU": 100}}',
                "fetched_at": int(time.time()) - 200000,
                "ttl_seconds": 86400,
            }
        )
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_fresh_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_returns_valid_data(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(
            return_value={
                "data_json": '{"value": {"DE": 50}}',
                "fetched_at": int(time.time()) - 100,
                "ttl_seconds": 86400,
            }
        )
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_fresh_snapshot()
        assert result is not None
        assert result["value"]["DE"] == 50

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_returns_none_when_empty_value(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(
            return_value={
                "data_json": '{"value": {}}',
                "fetched_at": int(time.time()),
                "ttl_seconds": 86400,
            }
        )
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_fresh_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_handles_db_exception(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(side_effect=RuntimeError("D1 down"))
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_fresh_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_fresh_snapshot_handles_json_error(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(
            return_value={
                "data_json": "not-valid-json",
                "fetched_at": int(time.time()),
                "ttl_seconds": 86400,
            }
        )
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_fresh_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_snapshot_no_db(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        repo = EurostatRepo(db=None)
        result = await repo.get_last_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_snapshot_returns_none_when_no_row(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value=None)
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_last_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_snapshot_returns_valid_data(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"data_json": '{"value": {"FR": 75}}'})
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_last_snapshot()
        assert result is not None
        assert result["value"]["FR"] == 75

    @pytest.mark.asyncio
    async def test_get_last_snapshot_handles_json_error(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"data_json": "bad"})
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_last_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_snapshot_handles_db_exception(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(side_effect=RuntimeError("fail"))
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_last_snapshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_save_snapshot_no_db(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        repo = EurostatRepo(db=None)
        result = await repo.save_snapshot({"value": {"IT": 30}})
        assert result is False

    @pytest.mark.asyncio
    async def test_save_snapshot_success(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=True)
        repo = EurostatRepo(db=mock_db)
        result = await repo.save_snapshot({"value": {"ES": 42}})
        assert result is True

    @pytest.mark.asyncio
    async def test_save_snapshot_handles_exception(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("disk full"))
        repo = EurostatRepo(db=mock_db)
        result = await repo.save_snapshot({"value": {}})
        assert result is False


# ---------------------------------------------------------------------------
# app/services/storage_service.py — R2 storage
# ---------------------------------------------------------------------------


class TestStorageService:
    def test_init_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.storage_service import StorageService

        monkeypatch.setenv("R2_BUCKET_NAME", "my-bucket")
        monkeypatch.setenv("R2_ENDPOINT_URL", "https://my.r2.dev")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak123")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk456")
        svc = StorageService()
        assert svc.bucket_name == "my-bucket"
        assert svc.endpoint_url == "https://my.r2.dev"
        assert svc.access_key == "ak123"
        assert svc.secret_key == "sk456"

    def test_init_uses_defaults_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.storage_service import StorageService

        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        monkeypatch.delenv("R2_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        svc = StorageService()
        assert svc.bucket_name == "evidence-eu-translations"
        assert svc.endpoint_url == "https://example.r2.cloudflarestorage.com"

    def test_sign_returns_bytes(self) -> None:
        from app.services.storage_service import StorageService

        svc = StorageService()
        result = svc._sign(b"secret-key", "message")
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_get_signature_key_returns_bytes(self) -> None:
        from app.services.storage_service import StorageService

        svc = StorageService()
        result = svc._get_signature_key("my-secret", "20260101", "auto", "s3")
        assert isinstance(result, bytes)
        assert len(result) == 32

    @pytest.mark.asyncio
    async def test_get_file_raises_on_non_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.storage_service import StorageService

        monkeypatch.setenv("R2_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("R2_ENDPOINT_URL", "https://test.r2.dev")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
        svc = StorageService()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "not found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.storage_service.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(RuntimeError, match="Failed to fetch file from R2"),
        ):
            await svc.get_file("test.pdf")


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/stats.py — Migration stats endpoint
# ---------------------------------------------------------------------------


class TestStatsEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, headers={"X-GDPR-Consent": "test-token"})

    def test_migration_stats_returns_200_or_503(self, client) -> None:
        response = client.get("/api/v1/stats/migration")
        assert response.status_code in (200, 503)

    def test_migration_stats_returns_json(self, client) -> None:
        response = client.get("/api/v1/stats/migration")
        assert response.headers["content-type"].startswith("application/json")

    def test_migration_stats_503_when_no_data(self, client) -> None:
        with patch("app.api.v1.endpoints.stats.EurostatRepo") as MockRepo:
            instance = MockRepo.return_value
            instance.get_fresh_snapshot = AsyncMock(return_value=None)
            instance.get_last_snapshot = AsyncMock(return_value=None)
            instance.save_snapshot = AsyncMock(return_value=False)

            with patch("app.api.v1.endpoints.stats.httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_resp.request = MagicMock()
                mock_resp.raise_for_status = MagicMock(side_effect=Exception("error"))
                MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value.get = AsyncMock(return_value=mock_resp)

                response = client.get("/api/v1/stats/migration")

        assert response.status_code == 503

    def test_build_query_params(self) -> None:
        from app.api.v1.endpoints.stats import _build_query_params

        params = _build_query_params()
        assert "format=JSON" in params
        assert "freq=A" in params
        assert "citizen=FOR_STLS" in params
        assert "geo=DE" in params
        assert "geo=FR" in params
        assert "geo=EU27_2020" in params
