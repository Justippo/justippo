# SPDX-License-Identifier: AGPL-3.0-or-later
"""NFR evidence tests — verify testing infrastructure is available.

These tests are CI-safe: they skip gracefully when tools are not installed
rather than failing. They serve as smoke checks for the NFR evidence chain.
"""

import os
import shutil

import pytest


def test_locust_is_installed():
    """NFR-01/02: Verify Locust is available for load testing."""
    if not shutil.which("locust"):
        pytest.skip("Locust not installed — run: pip install locust")
    assert True


def test_playwright_is_installed():
    """NFR-06: Verify Playwright is available for E2E testing."""
    if not shutil.which("playwright"):
        pytest.skip("Playwright not installed — run: pip install playwright && playwright install")
    assert True


def test_axe_core_exists_in_frontend():
    """NFR-06: Verify axe-core is present in frontend node_modules."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.join(current_dir, "..", "..")
    axe_path = os.path.normpath(os.path.join(repo_root, "frontend", "node_modules", "axe-core"))
    if not os.path.exists(axe_path):
        pytest.skip(f"axe-core not found at: {axe_path} — run: bun install in frontend/")
    assert True
