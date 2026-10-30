"""Coverage boost batch 24 — azure_document_intelligence validation/error
branches + workers_ai neuron-budget KV branches.

DRY:
* azure: pure-Python, fully pytest-reachable via ``httpx.MockTransport`` and
  direct calls to the validation helpers (no Worker runtime, no network).
* workers_ai: reuses ``tests.unit.d1_fakes.InMemoryKVBinding`` to drive the
  real ``_check_and_reserve_neurons`` / ``_record_neuron_usage`` branches.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations import azure_document_intelligence as azure
from app.integrations.llm import workers_ai_adapter as wai
from tests.unit.d1_fakes import InMemoryKVBinding

# ─── azure_document_intelligence validation / error branches ──────


class TestAzureValidation:
    def test_get_analysis_limits_f0(self) -> None:
        with patch.dict(os.environ, {"AZURE_DOCUMENT_INTELLIGENCE_TIER": "F0"}):
            lim = azure.get_analysis_limits()
        assert lim.tier == "F0"
        assert lim.max_bytes == azure._F0_MAX_BYTES

    def test_get_analysis_limits_s0(self) -> None:
        with patch.dict(os.environ, {"AZURE_DOCUMENT_INTELLIGENCE_TIER": "S0"}):
            lim = azure.get_analysis_limits()
        assert lim.tier == "S0"
        assert lim.max_bytes == azure._S0_MAX_BYTES

    def test_get_analysis_limits_invalid_tier_raises(self) -> None:
        with (
            patch.dict(os.environ, {"AZURE_DOCUMENT_INTELLIGENCE_TIER": "X9"}),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure.get_analysis_limits()
        assert exc.value.detail.code == "INVALID_CONFIGURATION"

    def test_load_config_missing_endpoint_key(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure._load_config()
        assert exc.value.detail.code == "SERVICE_UNAVAILABLE"

    def test_load_config_bad_scheme(self) -> None:
        env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "http://example.com",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure._load_config()
        assert exc.value.detail.code == "INVALID_CONFIGURATION"

    def test_load_config_bad_path(self) -> None:
        env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.com/extra",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure._load_config()
        assert exc.value.detail.code == "INVALID_CONFIGURATION"

    def test_load_config_bad_timing(self) -> None:
        env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.com",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
            "AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S": "not-a-number",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure._load_config()
        assert exc.value.detail.code == "INVALID_CONFIGURATION"

    def test_load_config_nonpositive_timing(self) -> None:
        env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.com",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
            "AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_S": "-5",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure._load_config()
        assert exc.value.detail.code == "INVALID_CONFIGURATION"

    def test_load_config_bad_model_id(self) -> None:
        env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.com",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
            "AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID": "bad model id!",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            azure._load_config()
        assert exc.value.detail.code == "INVALID_CONFIGURATION"

    def test_validate_operation_location_mismatch(self) -> None:
        with pytest.raises(azure.AzureDocumentIntelligenceError) as exc:
            azure._validate_operation_location(
                "https://evil.com/documentintelligence/op", "https://example.com"
            )
        assert exc.value.detail.code == "INVALID_PROVIDER_RESPONSE"

    def test_validate_operation_location_ok(self) -> None:
        url = "https://example.com/documentintelligence/op/123"
        assert azure._validate_operation_location(url, "https://example.com") == url

    def test_provider_error_retryable_429(self) -> None:
        err = azure._provider_error(status_code=429, stage="submission")
        assert err.detail.retryable is True
        assert err.detail.provider_status == 429

    def test_provider_error_non_retryable_400(self) -> None:
        err = azure._provider_error(status_code=400, stage="polling")
        assert err.detail.retryable is False

    def test_normalize_result_missing_analyze(self) -> None:
        with pytest.raises(azure.AzureDocumentIntelligenceError) as exc:
            azure._normalize_result({"foo": "bar"}, MagicMock())
        assert exc.value.detail.code == "INVALID_PROVIDER_RESPONSE"

    def test_normalize_result_non_list_field(self) -> None:
        payload = {"analyzeResult": {"content": "x", "pages": "not-a-list"}}
        result = azure._normalize_result(payload, MagicMock())
        assert result.pages == []

    def test_analyze_pdf_disabled(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            asyncio.run(azure.analyze_pdf(b"%PDF-1.4"))
        assert exc.value.detail.code == "SERVICE_UNAVAILABLE"

    def test_analyze_pdf_empty_bytes(self) -> None:
        with (
            patch.dict(os.environ, {"AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "true"}),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            asyncio.run(azure.analyze_pdf(b""))
        assert exc.value.detail.code == "INVALID_INPUT"

    def test_analyze_pdf_non_202_submission(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        with (
            patch.dict(
                os.environ,
                {
                    "AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "true",
                    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.com",
                    "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
                    "AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS": "1",
                },
                clear=True,
            ),
            pytest.raises(azure.AzureDocumentIntelligenceError) as exc,
        ):
            transport = httpx.MockTransport(handler)
            asyncio.run(
                azure.analyze_pdf(b"%PDF-1.4", client=httpx.AsyncClient(transport=transport))
            )
        assert exc.value.detail.code == "AZURE_ANALYSIS_FAILED"

    def test_analyze_pdf_success_cleans_up(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    202,
                    headers={"Operation-Location": "https://example.com/documentintelligence/op/1"},
                )
            return httpx.Response(
                200,
                json={
                    "status": "succeeded",
                    "analyzeResult": {"content": "hello", "pages": [{"pageNumber": 1}]},
                },
            )

        with patch.dict(
            os.environ,
            {
                "AZURE_DOCUMENT_INTELLIGENCE_ENABLED": "true",
                "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.com",
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": "k",
                "AZURE_DOCUMENT_INTELLIGENCE_MAX_POLLS": "1",
            },
            clear=True,
        ):
            transport = httpx.MockTransport(handler)
            result = asyncio.run(
                azure.analyze_pdf(b"%PDF-1.4", client=httpx.AsyncClient(transport=transport))
            )
        assert result.content == "hello"
        assert result.pages == [{"pageNumber": 1}]


# ─── workers_ai neuron-budget KV branches ─────────────────────────


class TestWorkersAiNeuronBudget:
    async def test_reserve_no_kv_allows(self) -> None:
        allowed, down = await wai._check_and_reserve_neurons("some-model", None)
        assert allowed is True
        assert down is None

    async def test_reserve_under_budget(self) -> None:
        key = f"{wai._NEURON_BUDGET_KV_KEY_PREFIX}{date.today().isoformat()}"
        kv = InMemoryKVBinding({key: "100"})
        allowed, down = await wai._check_and_reserve_neurons("some-model", kv)
        assert allowed is True
        assert down is None

    async def test_reserve_over_budget_downgrades_to_fast(self) -> None:
        near = str(wai._DAILY_NEURON_BUDGET - wai._NEURON_ESTIMATES.get(wai._MODEL_FAST, 150) - 10)
        key = f"{wai._NEURON_BUDGET_KV_KEY_PREFIX}{date.today().isoformat()}"
        kv = InMemoryKVBinding({key: near})
        allowed, down = await wai._check_and_reserve_neurons("some-big-model", kv)
        assert allowed is True
        assert down == wai._MODEL_FAST

    async def test_reserve_over_budget_blocks(self) -> None:
        key = f"{wai._NEURON_BUDGET_KV_KEY_PREFIX}{date.today().isoformat()}"
        kv = InMemoryKVBinding({key: str(wai._DAILY_NEURON_BUDGET)})
        allowed, down = await wai._check_and_reserve_neurons(wai._MODEL_FAST, kv)
        assert allowed is False
        assert down is None

    async def test_record_usage_writes_to_kv(self) -> None:
        kv = InMemoryKVBinding()
        await wai._record_neuron_usage("some-model", kv)
        assert len(kv.put_calls) == 1
        key, value, _ = kv.put_calls[0]
        assert key.startswith(wai._NEURON_BUDGET_KV_KEY_PREFIX)
        assert int(value) == wai._NEURON_ESTIMATES.get("some-model", 400)

    async def test_record_usage_no_kv_noop(self) -> None:
        await wai._record_neuron_usage("some-model", None)

    async def test_get_neuron_budget_kv_via_settings(self) -> None:
        kv = InMemoryKVBinding()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.NEURON_BUDGET_KV = kv
            result = wai._get_neuron_budget_kv()
        assert result is kv
