"""Comprehensive coverage boost for remaining gaps.

Targets all files below 100% coverage with focused unit tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/integrations/http_forwarder.py — ContextVar lifecycle + all paths
# ---------------------------------------------------------------------------


class TestHttpForwarder:
    def test_bind_and_reset_wait_until(self) -> None:
        from app.integrations.http_forwarder import (
            _wait_until,
            bind_wait_until,
            reset_wait_until,
        )

        callback = MagicMock()
        token = bind_wait_until(callback)
        assert _wait_until.get() is callback
        reset_wait_until(token)
        assert _wait_until.get() is None

    def test_bind_none_callback(self) -> None:
        from app.integrations.http_forwarder import _wait_until, bind_wait_until, reset_wait_until

        token = bind_wait_until(None)
        assert _wait_until.get() is None
        reset_wait_until(token)

    @pytest.mark.asyncio
    async def test_fire_and_forget_with_wait_until(self) -> None:
        from app.integrations.http_forwarder import (
            bind_wait_until,
            fire_and_forget,
            reset_wait_until,
        )

        callback = MagicMock()
        token = bind_wait_until(callback)
        try:
            with patch("app.integrations.http_forwarder._post", new_callable=AsyncMock):
                await fire_and_forget("http://test.com", {}, b"body")
            callback.assert_called_once()
        finally:
            reset_wait_until(token)

    @pytest.mark.asyncio
    async def test_fire_and_forget_wait_until_fails(self) -> None:
        from app.integrations.http_forwarder import (
            bind_wait_until,
            fire_and_forget,
            reset_wait_until,
        )

        callback = MagicMock(side_effect=RuntimeError("CF FFI error"))
        token = bind_wait_until(callback)
        try:
            with patch(
                "app.integrations.http_forwarder._post", new_callable=AsyncMock
            ) as mock_post:
                await fire_and_forget("http://test.com", {}, b"body")
            mock_post.assert_awaited_once()
        finally:
            reset_wait_until(token)

    @pytest.mark.asyncio
    async def test_fire_and_forget_no_loop(self) -> None:
        from app.integrations.http_forwarder import fire_and_forget

        with (
            patch("app.integrations.http_forwarder._post", new_callable=AsyncMock) as mock_post,
            patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")),
        ):
            await fire_and_forget("http://test.com", {}, b"body")
        mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fire_and_forget_dict_content(self) -> None:
        from app.integrations.http_forwarder import fire_and_forget

        with (
            patch("app.integrations.http_forwarder._post", new_callable=AsyncMock) as mock_post,
            patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")),
        ):
            await fire_and_forget("http://test.com", {}, {"key": "val"})
        args = mock_post.call_args
        assert isinstance(args[0][2], str)

    @pytest.mark.asyncio
    async def test_fire_and_forget_loop_create_task(self) -> None:
        from app.integrations.http_forwarder import fire_and_forget

        mock_loop = MagicMock()
        with (
            patch("app.integrations.http_forwarder._post", new_callable=AsyncMock),
            patch("asyncio.get_running_loop", return_value=mock_loop),
        ):
            await fire_and_forget("http://test.com", {}, b"body")
        mock_loop.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_fire_and_forget_general_exception(self) -> None:
        from app.integrations.http_forwarder import fire_and_forget

        with (
            patch("app.integrations.http_forwarder._post", new_callable=AsyncMock),
            patch("asyncio.get_running_loop", side_effect=Exception("weird")),
        ):
            await fire_and_forget("http://test.com", {}, b"body")

    @pytest.mark.asyncio
    async def test_post_now_dict_content(self) -> None:
        from app.integrations.http_forwarder import post_now

        with patch("app.integrations.http_forwarder._post", new_callable=AsyncMock) as mock_post:
            await post_now("http://test.com", {}, {"key": "val"})
        args = mock_post.call_args
        assert isinstance(args[0][2], str)

    @pytest.mark.asyncio
    async def test_post_now_calls_post(self) -> None:
        from app.integrations.http_forwarder import post_now

        with patch("app.integrations.http_forwarder._post", new_callable=AsyncMock) as mock_post:
            await post_now("http://test.com", {"h": "v"}, b"raw")
        mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_actual_httpx(self) -> None:
        from app.integrations.http_forwarder import _post

        mock_httpx = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = mock_client
        await _post("http://test.com", {}, b"body", 5.0, mock_httpx)
        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_exception_swallowed(self) -> None:
        from app.integrations.http_forwarder import _post

        mock_httpx = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=RuntimeError("network"))
        mock_httpx.AsyncClient.return_value = mock_client
        await _post("http://test.com", {}, b"body", 5.0, mock_httpx)


# ---------------------------------------------------------------------------
# app/integrations/llm/workers_ai_adapter.py
# ---------------------------------------------------------------------------


class TestWorkersAIAdapter:
    def test_is_enabled_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        monkeypatch.setattr(
            mod, "_get_settings", lambda: MagicMock(CF_WORKERS_AI_API_TOKEN="tok123")
        )
        assert mod.is_enabled() is True

    def test_is_enabled_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        monkeypatch.setattr(mod, "_get_settings", lambda: MagicMock(CF_WORKERS_AI_API_TOKEN=""))
        assert mod.is_enabled() is False

    def test_model_name_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        monkeypatch.setattr(mod, "is_enabled", lambda: True)
        assert mod.model_name() == mod._MODEL_FAST

    def test_model_name_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        monkeypatch.setattr(mod, "is_enabled", lambda: False)
        assert mod.model_name() is None

    def test_select_model_simple(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        assert mod._select_model("what is a residence permit?") == mod._MODEL_FAST

    def test_select_model_complex(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        assert mod._select_model("what are the penalties for violation?") == mod._MODEL_FRONTIER

    def test_select_model_for_prompt_none(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        assert mod.select_model_for_prompt(None) == mod._MODEL_FAST

    def test_select_model_for_prompt(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        assert mod.select_model_for_prompt("simple query") == mod._MODEL_FAST

    def test_extract_answer_openai_shape(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        data = {"choices": [{"message": {"content": "  hello world  "}}]}
        assert mod._extract_answer(data) == "hello world"

    def test_extract_answer_delta_shape(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        data = {"choices": [{"delta": {"content": "streaming text"}}]}
        assert mod._extract_answer(data) == "streaming text"

    def test_extract_answer_native_shape(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        data = {"result": {"response": "native answer"}}
        assert mod._extract_answer(data) == "native answer"

    def test_extract_answer_translated_shape(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        data = {"result": {"translated_text": "translated"}}
        assert mod._extract_answer(data) == "translated"

    def test_extract_answer_bare_shape(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        data = {"response": "bare response"}
        assert mod._extract_answer(data) == "bare response"

    def test_extract_answer_empty(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        assert mod._extract_answer({}) == ""

    def test_extract_answer_no_strip(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        data = {"choices": [{"message": {"content": "  text  "}}]}
        assert mod._extract_answer(data, strip=False) == "  text  "

    def test_get_neuron_budget_kv_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        monkeypatch.setattr(mod, "_get_settings", lambda: (_ for _ in ()).throw(RuntimeError("no")))
        assert mod._get_neuron_budget_kv() is None

    @pytest.mark.asyncio
    async def test_check_and_reserve_no_kv(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        allowed, model = await mod._check_and_reserve_neurons(mod._MODEL_FAST, None)
        assert allowed is True
        assert model is None

    @pytest.mark.asyncio
    async def test_check_and_reserve_within_budget(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="100")
        allowed, model = await mod._check_and_reserve_neurons(mod._MODEL_FAST, mock_kv)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_check_and_reserve_exceeded_downgrade(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        mock_kv = AsyncMock()
        # Use a value where frontier exceeds but fast fits (fast estimate = 150)
        mock_kv.get = AsyncMock(return_value=str(mod._DAILY_NEURON_BUDGET - 100))
        # Frontier estimate is 800, so used + 800 > budget, but used + 150 <= budget
        # Wait, _DAILY_NEURON_BUDGET - 100 + 150 = _DAILY_NEURON_BUDGET + 50 > budget
        # Need used + 150 <= budget => used <= budget - 150
        mock_kv.get = AsyncMock(return_value=str(mod._DAILY_NEURON_BUDGET - 200))
        # Frontier: used + 800 > budget (7800 + 800 = 8600 > 8000) ✓
        # Fast: used + 150 <= budget (7800 + 150 = 7950 <= 8000) ✓
        allowed, model = await mod._check_and_reserve_neurons(mod._MODEL_FRONTIER, mock_kv)
        assert allowed is True
        assert model == mod._MODEL_FAST

    @pytest.mark.asyncio
    async def test_check_and_reserve_exhausted(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value=str(mod._DAILY_NEURON_BUDGET + 1))
        allowed, model = await mod._check_and_reserve_neurons(mod._MODEL_FAST, mock_kv)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_record_neuron_usage_no_kv(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        await mod._record_neuron_usage(mod._MODEL_FAST, None)

    @pytest.mark.asyncio
    async def test_record_neuron_usage(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        mock_kv = AsyncMock()
        mock_kv.get = AsyncMock(return_value="100")
        await mod._record_neuron_usage(mod._MODEL_FAST, mock_kv)
        mock_kv.put.assert_awaited_once()

    def test_greeting_system_prompt(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        assert "EvidenceEU" in mod.greeting_system_prompt()

    def test_build_url(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        url = mod._build_url(mod._MODEL_FAST)
        assert "workers-ai" in url

    def test_build_headers(self) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        headers = mod._build_headers("test-token")
        assert headers["Authorization"] == "Bearer test-token"
        assert "Content-Type" in headers

    def test_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.workers_ai_adapter as mod

        mock_settings = MagicMock(RAG_LLM_MAX_TOKENS=1024)
        monkeypatch.setattr(mod, "_get_settings", lambda: mock_settings)
        p = mod._payload("test prompt", stream=False)
        assert p["stream"] is False
        assert p["max_tokens"] == 1024
        assert len(p["messages"]) == 2


# ---------------------------------------------------------------------------
# app/integrations/llm/answer_generation.py
# ---------------------------------------------------------------------------


class TestAnswerGeneration:
    def test_provider_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod.settings, "RAG_LLM_PROVIDER", "")
        assert mod._provider() == "workers-ai"

    def test_provider_huggingface(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod.settings, "RAG_LLM_PROVIDER", "HuggingFace")
        assert mod._provider() == "huggingface"

    def test_is_enabled_workers_ai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")
        with patch("app.integrations.llm.workers_ai_adapter.is_enabled", return_value=True):
            assert mod.is_enabled() is True

    def test_is_enabled_huggingface(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "huggingface")
        with patch("app.integrations.llm.apertus_adapter.is_enabled", return_value=True):
            assert mod.is_enabled() is True

    def test_display_name_apertus(self) -> None:
        import app.integrations.llm.answer_generation as mod

        assert mod._display_name("Apertus-8B") == "Apertus 8B"

    def test_display_name_llama4(self) -> None:
        import app.integrations.llm.answer_generation as mod

        assert mod._display_name("meta/llama-4-scout") == "Llama 4 Scout"

    def test_display_name_llama33(self) -> None:
        import app.integrations.llm.answer_generation as mod

        assert mod._display_name("llama-3.3-70b") == "Llama 3.3 70B"

    def test_display_name_llama31(self) -> None:
        import app.integrations.llm.answer_generation as mod

        assert mod._display_name("llama-3.1-8b") == "Llama 3.1 8B"

    def test_display_name_mistral(self) -> None:
        import app.integrations.llm.answer_generation as mod

        assert mod._display_name("mistral-large") == "Mistral"

    def test_display_name_unknown(self) -> None:
        import app.integrations.llm.answer_generation as mod

        assert mod._display_name("custom/model:v2") == "model"

    def test_answer_model_info_workers_ai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")
        with patch(
            "app.integrations.llm.workers_ai_adapter.model_name",
            return_value="@cf/meta/llama-3.1-8b-instruct-fp8",
        ):
            info = mod.active_model_info()
        assert info is not None
        assert info.provider == "cloudflare-workers-ai"

    def test_answer_model_info_workers_ai_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")
        with patch("app.integrations.llm.workers_ai_adapter.model_name", return_value=None):
            assert mod.active_model_info() is None

    def test_answer_model_info_huggingface(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "huggingface")
        with patch("app.integrations.llm.apertus_adapter.model_name", return_value="apertus-8b"):
            info = mod.active_model_info()
        assert info is not None
        assert info.provider == "public-ai"

    def test_answer_model_info_huggingface_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "huggingface")
        with patch("app.integrations.llm.apertus_adapter.model_name", return_value=None):
            assert mod.active_model_info() is None

    def test_answer_model_info_with_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")
        with patch(
            "app.integrations.llm.workers_ai_adapter.select_model_for_prompt",
            return_value="@cf/meta/llama-3.3-70b",
        ):
            info = mod.active_model_info(prompt="violation query")
        assert info is not None

    @pytest.mark.asyncio
    async def test_generate_answer_workers_ai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")
        mock_resp = MagicMock(answer="test", model="m", processing_time_ms=1.0)
        with patch(
            "app.integrations.llm.workers_ai_adapter.generate_answer",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await mod.generate_answer("test")
        assert result is mock_resp

    @pytest.mark.asyncio
    async def test_generate_answer_workers_ai_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")
        with patch(
            "app.integrations.llm.workers_ai_adapter.generate_answer",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await mod.generate_answer("test") is None

    @pytest.mark.asyncio
    async def test_generate_answer_huggingface(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "huggingface")
        mock_resp = MagicMock(answer="hf answer", model="apertus", processing_time_ms=2.0)
        with patch(
            "app.integrations.llm.apertus_adapter.generate_answer",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await mod.generate_answer("test")
        assert result.answer == "hf answer"

    @pytest.mark.asyncio
    async def test_generate_answer_huggingface_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "huggingface")
        with patch(
            "app.integrations.llm.apertus_adapter.generate_answer",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await mod.generate_answer("test") is None

    @pytest.mark.asyncio
    async def test_generate_answer_stream_workers_ai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "workers-ai")

        async def gen(*args, **kwargs):
            yield "token1"
            yield "token2"

        with patch(
            "app.integrations.llm.workers_ai_adapter.generate_answer_stream", side_effect=gen
        ):
            tokens = [t async for t in mod.generate_answer_stream("test")]
        assert tokens == ["token1", "token2"]

    @pytest.mark.asyncio
    async def test_generate_answer_stream_huggingface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.integrations.llm.answer_generation as mod

        monkeypatch.setattr(mod, "_provider", lambda: "huggingface")

        async def gen(*args, **kwargs):
            yield "hf1"

        with patch("app.integrations.llm.apertus_adapter.generate_answer_stream", side_effect=gen):
            tokens = [t async for t in mod.generate_answer_stream("test")]
        assert tokens == ["hf1"]

    @pytest.mark.asyncio
    async def test_generate_greeting_stream(self) -> None:
        import app.integrations.llm.answer_generation as mod

        async def gen(*args, **kwargs):
            yield "hi"

        with patch(
            "app.integrations.llm.workers_ai_adapter.generate_greeting_stream", side_effect=gen
        ):
            tokens = [t async for t in mod.generate_greeting_stream("hello")]
        assert tokens == ["hi"]


# ---------------------------------------------------------------------------
# app/services/journey_content.py — get_step_documents, get_authority_info, etc.
# ---------------------------------------------------------------------------


class TestJourneyContent:
    def test_get_step_documents_returns_none(self) -> None:
        from app.services.journey_content import get_step_documents

        result = get_step_documents("nonexistent-step-id")
        assert result is None

    def test_get_authority_info_returns_none(self) -> None:
        from app.services.journey_content import get_authority_info

        result = get_authority_info("nonexistent-authority")
        assert result is None

    def test_get_supported_jurisdictions(self) -> None:
        from app.services.journey_content import get_supported_jurisdictions

        result = get_supported_jurisdictions()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# app/api/v1/endpoints/stats.py — remaining lines 60, 86
# ---------------------------------------------------------------------------


class TestStatsEndpointRemaining:
    def test_cache_hit_returns_200(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        c = TestClient(app, headers={"X-GDPR-Consent": "test"}, raise_server_exceptions=False)
        with patch("app.api.v1.endpoints.stats.EurostatRepo") as MockRepo:
            instance = MockRepo.return_value
            instance.get_fresh_snapshot = AsyncMock(return_value={"value": {"DE": 50}})
            response = c.get("/api/v1/stats/migration")
        assert response.status_code == 200
        assert response.json()["value"]["DE"] == 50

    def test_fallback_with_warning(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        c = TestClient(app, headers={"X-GDPR-Consent": "test"}, raise_server_exceptions=False)
        with patch("app.api.v1.endpoints.stats.EurostatRepo") as MockRepo:
            instance = MockRepo.return_value
            instance.get_fresh_snapshot = AsyncMock(return_value=None)
            instance.get_last_snapshot = AsyncMock(return_value={"value": {"FR": 30}})
            instance.save_snapshot = AsyncMock(return_value=False)

            with patch("app.api.v1.endpoints.stats.httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_resp.request = MagicMock()
                mock_resp.raise_for_status = MagicMock(side_effect=Exception("err"))
                MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value.get = AsyncMock(return_value=mock_resp)

                response = c.get("/api/v1/stats/migration")
        assert response.status_code == 200
        assert response.json().get("warning") == "STALE_DATA"


# ---------------------------------------------------------------------------
# app/services/storage_service.py — line 79 (happy path get_file)
# ---------------------------------------------------------------------------


class TestStorageServiceHappy:
    @pytest.mark.asyncio
    async def test_get_file_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.storage_service import StorageService

        monkeypatch.setenv("R2_BUCKET_NAME", "b")
        monkeypatch.setenv("R2_ENDPOINT_URL", "https://r2.dev")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
        svc = StorageService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"file-data"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.storage_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc.get_file("doc.pdf")
        assert result == b"file-data"


# ---------------------------------------------------------------------------
# app/repositories/eurostat_repo.py — lines 99-100
# ---------------------------------------------------------------------------


class TestEurostatRepoRemaining:
    @pytest.mark.asyncio
    async def test_get_last_snapshot_empty_value(self) -> None:
        from app.repositories.eurostat_repo import EurostatRepo

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"data_json": '{"value": {}}'})
        repo = EurostatRepo(db=mock_db)
        result = await repo.get_last_snapshot()
        assert result is None
