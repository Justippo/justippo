# SPDX-License-Identifier: AGPL-3.0-or-later
# === LIVE TESTING COMMANDS (once frontend is deployed) ===
# For local dev:
# pytest tests/e2e/test_accessibility.py --headed
#
# For staging environment:
# pytest tests/e2e/test_accessibility.py --headed --base-url https://your-staging-frontend.com
#
# To generate HTML report:
# pytest tests/e2e/test_accessibility.py --headed --html=reports/accessibility-report.html --self-contained-html

import json
import os

import pytest

pytest.importorskip(
    "playwright",
    reason="playwright not installed — run: pip install playwright && playwright install",
)

from playwright.sync_api import Page  # noqa: E402


def test_homepage_accessibility(page: Page):
    """NFR-06: Ensure homepage meets WCAG 2.1 AA standards."""

    # Navigate to your deployed frontend URL
    page.goto(os.environ.get("LIVE_FRONTEND_URL", "http://localhost:3000"))

    # Inject axe-core into the page
    page.add_script_tag(
        path=os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "frontend",
            "node_modules",
            "axe-core",
            "axe.min.js",
        )
    )

    # Run axe accessibility scan
    results = page.evaluate("""
        () => axe.run({
            runOnly: {
                type: 'tag',
                values: ['wcag2a', 'wcag2aa']
            }
        })
    """)

    # Assert no violations
    violations = results.get("violations", [])
    assert len(violations) == 0, json.dumps(violations, indent=2)
