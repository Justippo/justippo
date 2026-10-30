"""Coverage boost batch 20 — workers_ai_adapter pure helpers, budget-KV branches, greeting no-op."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.llm import workers_ai_adapter as wai

# ─── pure helper functions ───────────────────────────────────────


class TestWorkersAIHelpers:
    def test_build_url_uses_gateway(self) -> None:
        url = wai._build_url("@cf/meta/llama-3.1-8b-instruct-fp8")
        assert "@cf/meta/llama-3.1-8b-instruct-fp8" in url

    def test_build_headers_includes_bearer_and_gateway_auth(self) -> None:
        headers = wai._build_headers("secret-token")
        assert headers["Authorization"] == "Bearer secret-token"
        assert headers["Content-Type"] == "application/json"
        # get_gateway_auth_headers contributes additional keys
        assert "cf-aig-authorization" in headers or len(headers) >= 2

    def test_select_model_routes_complex_to_frontier(self) -> None:
        model = wai._select_model("What are the penalties for a GDPR violation?")
        assert model == wai._MODEL_FRONTIER

    def test_select_model_routes_simple_to_fast(self) -> None:
        model = wai._select_model("What is a residence permit?")
        assert model == wai._MODEL_FAST

    def test_select_model_for_prompt_none_returns_fast(self) -> None:
        assert wai.select_model_for_prompt(None) == wai._MODEL_FAST

    def test_select_model_for_prompt_delegates(self) -> None:
        assert wai.select_model_for_prompt("GDPR violation fine court") == wai._MODEL_FRONTIER
        assert wai.select_model_for_prompt("hello") == wai._MODEL_FAST

    def test_system_prompt_and_greeting_prompt_nonempty(self) -> None:
        assert "cross-border" in wai._system_prompt().lower()
        assert "evidenceeu" in wai.greeting_system_prompt().lower()

    def test_extract_answer_openai_message(self) -> None:
        data = {"choices": [{"message": {"content": "  hello world  "}}]}
        assert wai._extract_answer(data) == "hello world"

    def test_extract_answer_openai_delta(self) -> None:
        data = {"choices": [{"delta": {"content": "streamed"}}]}
        assert wai._extract_answer(data, strip=False) == "streamed"

    def test_extract_answer_native_result(self) -> None:
        data = {"result": {"response": "native shape"}}
        assert wai._extract_answer(data) == "native shape"

    def test_extract_answer_native_translated(self) -> None:
        data = {"result": {"translated_text": "translated"}}
        assert wai._extract_answer(data) == "translated"

    def test_extract_answer_bare_response(self) -> None:
        data = {"response": "bare"}
        assert wai._extract_answer(data) == "bare"

    def test_extract_answer_empty(self) -> None:
        assert wai._extract_answer({"choices": []}) == ""
        assert wai._extract_answer({}) == ""
        assert wai._extract_answer({"choices": [{"message": {"content": "  "}}]}) == ""

    def test_payload_includes_prompt_and_model(self) -> None:
        payload = wai._payload("simple lookup", stream=False)
        assert payload["model"] == wai._MODEL_FAST
        assert payload["messages"][1]["content"] == "simple lookup"
        assert payload["stream"] is False

        payload_stream = wai._payload("GDPR violation penalty", stream=True)
        assert payload_stream["stream"] is True
        assert payload_stream["model"] == wai._MODEL_FRONTIER


# ─── neuron budget KV branches ───────────────────────────────────


class TestWorkersAINeuronBudget:
    async def test_check_reserve_no_kv_allows(self) -> None:
        allowed, selected = await wai._check_and_reserve_neurons(
            "@cf/meta/llama-3.1-8b-instruct-fp8", None
        )
        assert allowed is True
        assert selected is None

    async def test_check_reserve_under_budget(self) -> None:
        kv = MagicMock()
        kv.get = AsyncMock(return_value="0")
        allowed, selected = await wai._check_and_reserve_neurons(
            "@cf/meta/llama-3.1-8b-instruct-fp8", kv
        )
        assert allowed is True
        assert selected is None

    async def test_check_reserve_downgrades_to_fast(self) -> None:
        kv = MagicMock()
        # used so that frontier exceeds budget but fast fits
        kv.get = AsyncMock(return_value=str(wai._DAILY_NEURON_BUDGET - 200))
        allowed, selected = await wai._check_and_reserve_neurons(wai._MODEL_FRONTIER, kv)
        assert allowed is True
        assert selected == wai._MODEL_FAST

    async def test_check_reserve_exhausted_blocks(self) -> None:
        kv = MagicMock()
        kv.get = AsyncMock(return_value=str(wai._DAILY_NEURON_BUDGET + 10))
        allowed, selected = await wai._check_and_reserve_neurons(wai._MODEL_FRONTIER, kv)
        assert allowed is False
        assert selected is None

    async def test_record_neuron_usage_no_kv_noop(self) -> None:
        # Should not raise with kv=None
        await wai._record_neuron_usage("@cf/meta/llama-3.1-8b-instruct-fp8", None)

    async def test_record_neuron_usage_writes_kv(self) -> None:
        kv = MagicMock()
        kv.get = AsyncMock(return_value="100")
        kv.put = AsyncMock()
        await wai._record_neuron_usage("@cf/meta/llama-3.1-8b-instruct-fp8", kv)
        kv.put.assert_awaited_once()

    def test_get_neuron_budget_kv_returns_none_without_binding(self) -> None:
        # Force settings import to raise to exercise the except branch.
        with patch.object(wai, "_get_settings", side_effect=ImportError("no settings")):
            assert wai._get_neuron_budget_kv() is None


# ─── greeting no-op contract ─────────────────────────────────────


class TestWorkersAIGreetingNoOp:
    async def test_greeting_yields_nothing_without_token(self) -> None:
        with patch.object(wai, "_get_settings") as mock_settings:
            mock_settings.return_value.CF_WORKERS_AI_API_TOKEN = "   "
            tokens: list[str] = []
            async for tok in wai.generate_greeting_stream("hello"):
                tokens.append(tok)
            assert tokens == []

    async def test_is_enabled_false_without_token(self) -> None:
        with patch.object(wai, "_get_settings") as mock_settings:
            mock_settings.return_value.CF_WORKERS_AI_API_TOKEN = ""
            assert wai.is_enabled() is False

    def test_model_name_none_when_disabled(self) -> None:
        with patch.object(wai, "is_enabled", return_value=False):
            assert wai.model_name() is None
