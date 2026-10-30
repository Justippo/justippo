"""
Benchmark test configuration — shared fixtures for performance tests.

This conftest makes the queries.json fixture available to any pytest-based
benchmark tests (e.g., micro-benchmarks of SSE serialization).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

QUERIES_PATH = Path(__file__).parent / "queries.json"


@pytest.fixture(scope="session")
def perf_queries() -> list[dict[str, Any]]:
    """Load shared performance test query fixtures."""
    with QUERIES_PATH.open() as f:
        data = json.load(f)
    return data["queries"]


@pytest.fixture(scope="session")
def perf_queries_by_category(perf_queries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group queries by category for targeted benchmarks."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for q in perf_queries:
        grouped.setdefault(q["category"], []).append(q)
    return grouped
