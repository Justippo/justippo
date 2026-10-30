"""Deploy self-hosted Hindsight RAG on Modal.

.. deprecated::
    Modal deployment was superseded on 2026-07-21 by local Docker + Cloudflare
    Tunnel (deploy/local/docker-compose.yml). This script is retained as a
    historical reference. See ADR-016 for the migration rationale.

Usage:
    modal deploy backend/scripts/modal_hindsight.py

Requires Modal secrets:
    modal secret create hindsight-auth HINDSIGHT_API_TENANT_API_KEY=<token>
    modal secret create hindsight-llm HINDSIGHT_API_LLM_API_KEY=<key>
"""

from __future__ import annotations

from pathlib import Path

import modal

# ── DRY: shared environment variables (non-secret config only) ──────────────
HINDSIGHT_ENV: dict[str, str] = {
    "HINDSIGHT_API_LLM_BASE_URL": "https://api.mistral.ai/v1",
    "HINDSIGHT_API_DB_POOL_MIN_SIZE": "2",
    "HINDSIGHT_API_DB_POOL_MAX_SIZE": "100",
    "HINDSIGHT_API_WORKER_POLL_INTERVAL_MS": "5000",
    "HINDSIGHT_API_EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
    "HINDSIGHT_API_EMBEDDING_DIMENSION": "384",
    "HINDSIGHT_API_RERANKER_MODEL": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "HINDSIGHT_API_LLM_MODEL": "mistral-small-latest",
    "HINDSIGHT_API_LLM_MAX_INPUT_TOKENS": "16000",
    "HINDSIGHT_API_LLM_MAX_OUTPUT_TOKENS": "2048",
    "HINDSIGHT_API_LLM_TEMPERATURE": "0.7",
    "HINDSIGHT_API_LLM_TRACE_ENABLED": "false",
    "HINDSIGHT_API_GRAPH_RETRIEVER": "link_expansion",
    "HINDSIGHT_API_EMBEDDING_PROVIDER": "voyage",
    "HINDSIGHT_API_EMBEDDING_MODEL_TYPE": "encoder",
    "HINDSIGHT_API_ADMIN_ENABLED": "false",
    "HINDSIGHT_API_SKIP_LLM_VERIFICATION": "false",
}

# ── Seed documents (excerpts of real EU regulations) ────────────────────────
# Single source of truth: backend/scripts/seed_hindsight.py defines DOCUMENTS.
# The canonical module is baked into the image at /root/seed_hindsight.py
# (see add_local_file below, copy=True), and loaded at *runtime* (inside the
# function, not at module import) so the local `modal deploy` pre-flight — which
# imports this script in the local interpreter — never tries to read the
# container-only path. This keeps one canonical document list with no inline copy.
_BANK_ID = "evidence-eu-docs"
_SEED_MODULE_PATH = "/root/seed_hindsight.py"


def _load_seed_documents() -> list[dict]:
    """Load DOCUMENTS from the baked-in seed_hindsight module (runtime only)."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("seed_hindsight", _SEED_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_hindsight"] = module
    spec.loader.exec_module(module)
    return list(module.DOCUMENTS)


BANK_ID = _BANK_ID

app = modal.App("evidence-eu-hindsight")

# Official Hindsight Docker image + gosu for privilege drop.
# The image runs as root; pg0's initdb refuses root.  We install gosu
# and create a non-root user so the server can start embedded PostgreSQL.
image = (
    modal.Image.from_registry("ghcr.io/vectorize-io/hindsight:latest")
    .apt_install("gosu")
    .run_commands("useradd -m -s /bin/bash hindsight || true")
    # Bake the canonical seed module into the image (copy=True) so it is
    # importable at a known path (/root/seed_hindsight.py) at container runtime.
    .add_local_file(
        str(Path(__file__).resolve().parent / "seed_hindsight.py"),
        remote_path="/root/seed_hindsight.py",
        copy=True,
    )
    .env(HINDSIGHT_ENV)
)


def _bank_has_data(auth_token: str) -> bool:
    """Return True if the bank already holds seeded nodes (idempotency guard)."""
    import json
    import urllib.request

    headers = {"Authorization": f"Bearer {auth_token}"}
    url = f"http://localhost:8600/v1/default/banks/{BANK_ID}/stats"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return int(data.get("total_nodes", 0)) > 0
    except Exception:
        return False


def _seed_bank() -> None:
    """Seed the evidence-eu-docs bank via the Hindsight REST API."""
    import json
    import os
    import time
    import urllib.error
    import urllib.request

    auth_token = os.environ.get("HINDSIGHT_API_TENANT_API_KEY", "")
    if not auth_token:
        return

    # Idempotency: never re-seed a bank that already holds data.  Ephemeral
    # pg0 is wiped on cold start, so this only skips redundant warm restarts.
    if _bank_has_data(auth_token):
        return

    url = f"http://localhost:8600/v1/default/banks/{BANK_ID}/memories"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    }

    total = 0
    for doc in _load_seed_documents():
        content = str(doc["content"])
        chunks = [content[i : i + 800] for i in range(0, len(content), 800)]
        metadata = {k: v for k, v in doc["metadata"].items() if k != "tags"}
        items = [
            {
                "content": chunk,
                "document_id": f"{doc['document_id']}-chunk-{i}",
                "metadata": metadata,
                "tags": doc["metadata"].get("tags", []),
            }
            for i, chunk in enumerate(chunks)
            if chunk.strip()
        ]
        if not items:
            continue
        payload = json.dumps({"items": items}).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status == 200:
                    total += len(items)
        except Exception:
            pass
        time.sleep(2)


def _await_consolidation(auth_token: str) -> None:
    """Block until Hindsight finishes consolidating seeded memories.

    The Live E2E test fails intermittently when it queries the bank before
    consolidation completes (nodes exist but recall returns nothing).  Poll
    the bank stats until pending consolidation settles and a new seed pass
    no longer changes the node count.
    """
    import json
    import time
    import urllib.request

    headers = {"Authorization": f"Bearer {auth_token}"}
    url = f"http://localhost:8600/v1/default/banks/{BANK_ID}/stats"
    stable_for = 0
    last_nodes = -1
    for _ in range(180):  # up to ~9 min
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=10
            ) as resp:
                data = json.loads(resp.read().decode())
                pending = int(data.get("pending_consolidation", 0)) + int(
                    data.get("pending_operations", 0)
                )
                nodes = int(data.get("total_nodes", 0))
                if pending == 0 and nodes == last_nodes:
                    stable_for += 1
                else:
                    stable_for = 0
                last_nodes = nodes
                if pending == 0 and stable_for >= 3:
                    return
        except Exception:
            pass
        time.sleep(3)


def _seed_after_ready() -> None:
    """Background thread: wait for Hindsight to be healthy, then seed."""
    import os
    import threading
    import time
    import urllib.request

    def _run() -> None:
        # Poll health endpoint until the server is ready.
        for _ in range(120):
            try:
                with urllib.request.urlopen("http://localhost:8600/health", timeout=5) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
            time.sleep(2)

        # Small additional delay for migrations and model loading.
        time.sleep(5)
        _seed_bank()
        # Wait for consolidation to finish so recall is queryable before the
        # container is considered warm (prevents intermittent E2E failures).
        _await_consolidation(os.environ.get("HINDSIGHT_API_TENANT_API_KEY", ""))

    threading.Thread(target=_run, daemon=True).start()


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("hindsight-auth"),
        modal.Secret.from_name("hindsight-llm"),
    ],
    cpu=2,
    memory=4096,
    timeout=3600,
    min_containers=0,
    max_containers=1,
    enable_memory_snapshot=False,
    scaledown_window=600,
)
@modal.web_server(port=8600, startup_timeout=300)
def run_hindsight():
    import os
    import subprocess

    # Start auto-seeding in background before launching the server.
    _seed_after_ready()

    # Drop from root to 'hindsight' so pg0's initdb can run.
    # gosu preserves environment variables.
    # Modal secrets inject HINDSIGHT_API_TENANT_API_KEY and
    # HINDSIGHT_API_LLM_API_KEY into os.environ at runtime.
    subprocess.Popen(
        ["gosu", "hindsight", "hindsight-api", "--host", "0.0.0.0", "--port", "8600"],
        env={**os.environ},
    )
