# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production wiring contract for authenticated Matrix document exchange."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))


def test_backend_worker_enables_matrix_auth_and_exchange() -> None:
    config = tomllib.loads((_REPO_ROOT / "backend" / "wrangler.toml").read_text())

    assert config["vars"]["ENABLE_MATRIX_AUTH"] == "true"
    assert config["vars"]["ENABLE_MATRIX_EXCHANGE"] == "true"


def test_proxy_worker_enables_matrix_exchange_in_production() -> None:
    config = tomllib.loads((_REPO_ROOT / "worker" / "wrangler.toml").read_text())

    assert config["env"]["production"]["vars"]["ENABLE_MATRIX_EXCHANGE"] == "true"


def test_frontend_production_build_enables_matrix_oauth() -> None:
    workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert 'NEXT_PUBLIC_MATRIX_AUTH_PREVIEW_ENABLED: "true"' in workflow
