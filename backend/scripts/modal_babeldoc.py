"""Deploy BabelDOC sidecar on Modal (EU region).

.. deprecated::
    Modal deployment was superseded on 2026-07-21 by local Docker + Cloudflare
    Tunnel (deploy/local/docker-compose.yml). This script is retained as a
    historical reference. See ADR-016 for the migration rationale.

Usage:
    modal deploy backend/scripts/modal_babeldoc.py

Requires Modal secrets:
    modal secret create babeldoc-config \\
        BABELDOC_OPENAI_BASE_URL=https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1 \\
        BABELDOC_OPENAI_API_KEY=<cloudflare-ai-gateway-token> \\
        BABELDOC_OPENAI_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast \\
        BABELDOC_AUTH_TOKEN=<generate-random-secret>

Architecture (mirrors Hindsight ADR-016 pattern):
    Cloudflare Worker -> babeldoc_adapter.py (httpx) -> Modal web_server -> BabelDOC CLI
    EU data residency: region="eu" (Dublin, Ireland)
    DRY: same modal.App + @modal.web_server pattern as modal_hindsight.py
"""

from __future__ import annotations

from pathlib import Path

import modal

app = modal.App("evidence-eu-babeldoc")

# Resolve sidecar path relative to this script (works locally during deploy).
# On Modal's runtime this path isn't used — add_local_file already baked the
# files into the image at build time.
try:
    sidecar_path = Path(__file__).resolve().parents[2] / "sidecars" / "babeldoc"
except IndexError:
    sidecar_path = Path("/app/sidecars/babeldoc")

# Build image: pip_install first, then add_local_file LAST (Modal requires this).
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("BabelDOC==0.6.3", "fastapi==0.115.6", "uvicorn[standard]==0.34.0")
    .workdir("/app")
    .add_local_file(str(sidecar_path / "app" / "main.py"), remote_path="/app/app/main.py")
    .add_local_file(str(sidecar_path / "app" / "runtime.py"), remote_path="/app/app/runtime.py")
    .add_local_file(str(sidecar_path / "app" / "__init__.py"), remote_path="/app/app/__init__.py")
)

# Persistent volume for BabelDOC's DocLayout-YOLO ONNX model cache (~500MB).
model_volume = modal.Volume.from_name("babeldoc-model-cache", create_if_missing=True)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("babeldoc-config")],
    cpu=2,
    memory=6144,
    timeout=3600,
    region="eu",
    min_containers=1,
    max_containers=1,
    scaledown_window=600,
    volumes={"/app/.cache": model_volume},
)
@modal.web_server(port=8750, startup_timeout=120)
def run_babeldoc():
    """Start the BabelDOC sidecar FastAPI server."""
    import subprocess

    subprocess.Popen(
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8750"],
    )
