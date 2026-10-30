"""Provider-agnostic answer model metadata tests."""

from unittest.mock import patch

from app.integrations.llm.answer_generation import active_model_info


def test_active_model_info_reports_apertus_runtime() -> None:
    with (
        patch("app.integrations.llm.answer_generation._provider", return_value="huggingface"),
        patch(
            "app.integrations.llm.apertus_adapter.model_name",
            return_value="swiss-ai/apertus-8b-instruct",
        ),
    ):
        info = active_model_info()

    assert info is not None
    assert info.display_name == "Apertus 8B"
    assert info.provider_display == "Public AI"


def test_active_model_info_reports_workers_ai_runtime() -> None:
    with (
        patch("app.integrations.llm.answer_generation._provider", return_value="workers-ai"),
        patch(
            "app.integrations.llm.workers_ai_adapter.model_name",
            return_value="@cf/meta/llama-3.1-8b-instruct",
        ),
    ):
        info = active_model_info()

    assert info is not None
    assert info.display_name == "Llama 3.1 8B"
    assert info.provider_display == "Cloudflare Workers AI"


def test_active_model_info_selects_frontier_for_complex_prompt() -> None:
    with (
        patch("app.integrations.llm.answer_generation._provider", return_value="workers-ai"),
        patch(
            "app.integrations.llm.workers_ai_adapter.select_model_for_prompt",
            return_value="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        ),
    ):
        info = active_model_info("What are the penalties for non-compliance?")

    assert info is not None
    assert info.model == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert info.display_name == "Llama 3.3 70B"


def test_active_model_info_does_not_claim_disabled_model() -> None:
    with (
        patch("app.integrations.llm.answer_generation._provider", return_value="workers-ai"),
        patch("app.integrations.llm.workers_ai_adapter.model_name", return_value=None),
    ):
        assert active_model_info() is None
