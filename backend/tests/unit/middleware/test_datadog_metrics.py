import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, Response

from app.core.middleware import DatadogMetricsMiddleware
from app.integrations import datadog
from app.integrations.datadog import build_metric_series, build_search_stage_series


def test_request_metrics_use_datadog_v1_point_tuples():
    payload = build_metric_series(
        route="/api/v1/health/",
        method="GET",
        status=200,
        duration_ms=42.5,
        env="production",
    )

    duration, count = payload["series"]
    assert duration["points"][0][1] == 42.5
    assert count["points"][0][1] == 1
    assert all(isinstance(metric["points"][0], list) for metric in payload["series"])
    assert all(len(metric["points"][0]) == 2 for metric in payload["series"])


def test_search_stage_metric_contains_only_fixed_privacy_safe_tags():
    payload = build_search_stage_series(
        stage="hindsight_recall",
        outcome="success",
        duration_ms=123.4,
        env="production",
    )

    metric = payload["series"][0]
    assert metric["metric"] == "evidence_eu.search.stage.duration"
    assert metric["points"][0][1] == 123.4
    assert len(metric["points"][0]) == 2
    assert metric["tags"] == [
        "stage:hindsight_recall",
        "outcome:success",
        "env:production",
    ]
    assert "query" not in repr(payload).lower()


@pytest.mark.asyncio
async def test_search_stage_batch_flushes_both_stages_in_one_request():
    datadog.configure("test-api-key")
    token = datadog.begin_search_stage_batch()

    try:
        recall = build_search_stage_series(
            stage="hindsight_recall",
            outcome="success",
            duration_ms=123.4,
            env="production",
        )
        generation = build_search_stage_series(
            stage="answer_generation",
            outcome="success",
            duration_ms=456.7,
            env="production",
        )

        with patch.object(datadog, "post_now", new=AsyncMock()) as post:
            # The Hindsight recall metric is produced in the query task. A
            # child task receives the same mutable request-local batch.
            await asyncio.create_task(datadog.record_search_stage(recall))
            await datadog.record_search_stage(generation)
            await datadog.flush_search_stage_batch()

        post.assert_awaited_once()
        url, headers, payload = post.await_args.args
        assert url == "https://api.us5.datadoghq.com/api/v1/series"
        assert headers["DD-API-KEY"] == "test-api-key"
        assert post.await_args.kwargs == {"timeout": 5.0}
        assert len(payload["series"]) == 2
        assert {series["tags"][0] for series in payload["series"]} == {
            "stage:hindsight_recall",
            "stage:answer_generation",
        }
        assert all(
            series["metric"] == "evidence_eu.search.stage.duration" for series in payload["series"]
        )
        assert "query" not in json.dumps(payload).lower()
    finally:
        datadog.reset_search_stage_batch(token)
        datadog.configure(None)


@pytest.mark.asyncio
async def test_search_stage_outside_sse_uses_background_delivery():
    payload = build_search_stage_series(
        stage="hindsight_recall",
        outcome="success",
        duration_ms=1.0,
        env="test",
    )

    with patch.object(datadog, "ship_metrics", new=AsyncMock()) as ship:
        await datadog.record_search_stage(payload)

    ship.assert_awaited_once_with(payload)


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.url.path = "/test-endpoint"
    request.method = "GET"
    request.scope = {"type": "http"}
    return request


@pytest.mark.asyncio
async def test_datadog_metrics_middleware_success(mock_request):
    app = MagicMock()
    middleware = DatadogMetricsMiddleware(app)

    async def call_next_mock(req):
        return Response(status_code=200)

    with (
        patch("app.integrations.datadog.build_metric_series") as mock_build,
        patch("app.integrations.datadog.ship_metrics") as mock_ship,
    ):
        mock_build.return_value = [{"metric": "test"}]

        response = await middleware.dispatch(mock_request, call_next_mock)

        assert response.status_code == 200

        assert mock_build.call_count == 1
        assert mock_ship.call_count == 1

        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["status"] == 200


@pytest.mark.asyncio
async def test_datadog_metrics_middleware_exception(mock_request):
    app = MagicMock()
    middleware = DatadogMetricsMiddleware(app)

    async def call_next_mock(req):
        raise ValueError("Simulated Exception")

    with (
        patch("app.integrations.datadog.build_metric_series") as mock_build,
        patch("app.integrations.datadog.ship_metrics") as mock_ship,
    ):
        mock_build.return_value = [{"metric": "test"}]

        with pytest.raises(ValueError, match="Simulated Exception"):
            await middleware.dispatch(mock_request, call_next_mock)

        assert mock_build.call_count == 1
        assert mock_ship.call_count == 1

        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["status"] == 500
