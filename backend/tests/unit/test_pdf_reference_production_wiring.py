"""Production configuration checks for the PDF reference Azure adapter."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
_AZURE_ENDPOINT = "https://evidenceeu-docintel-km-2026.cognitiveservices.azure.com"


def test_production_wrangler_enables_f0_azure_resource() -> None:
    """Production uses the approved EU F0 resource and never commits its key."""
    config = tomllib.loads((_REPO_ROOT / "backend" / "wrangler.toml").read_text())
    variables = config["vars"]

    assert variables["AZURE_DOCUMENT_INTELLIGENCE_ENABLED"] == "true"
    assert variables["AZURE_DOCUMENT_INTELLIGENCE_TIER"] == "F0"
    assert variables["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"] == _AZURE_ENDPOINT
    assert "AZURE_DOCUMENT_INTELLIGENCE_KEY" not in variables


def test_ci_delivers_azure_key_as_worker_secret() -> None:
    """GitHub Actions is the source of truth for the encrypted runtime key."""
    workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "wrangler secret put AZURE_DOCUMENT_INTELLIGENCE_KEY --name evidence-eu-api" in workflow
    assert (
        "AZURE_DOCUMENT_INTELLIGENCE_KEY: "
        "${{ secrets.AZURE_DOCUMENT_INTELLIGENCE_KEY }}" in workflow
    )


def test_ci_delivers_babeldoc_sidecar_url_as_worker_secret() -> None:
    """Deployments inject a configured URL and auth token as Worker secrets.

    BABELDOC_ENABLED is now 'true' — the sidecar is deployed on Modal (eu-west)
    and the GitHub secrets BABELDOC_SIDECAR_URL + BABELDOC_AUTH_TOKEN are set.
    The test verifies the CI workflow wiring is in place to inject them.
    """
    config = tomllib.loads((_REPO_ROOT / "backend" / "wrangler.toml").read_text())
    workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert config["vars"]["BABELDOC_ENABLED"] == "true"
    assert 'if [ -n "${BABELDOC_SIDECAR_URL:-}" ]; then' in workflow
    assert "wrangler secret put BABELDOC_SIDECAR_URL --name evidence-eu-api" in workflow
    assert "wrangler secret put BABELDOC_AUTH_TOKEN --name evidence-eu-api" in workflow
    assert "BabelDOC sidecar URL missing" not in workflow
