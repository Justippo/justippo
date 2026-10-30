"""
evidence_eu_model.py — Standalone SSE client for EvidenceEU RAG endpoint

Queries the EvidenceEU FastAPI SSE search endpoint and returns retrieved
document IDs for retrieval-quality evaluation (recall@k, MRR, NDCG).

No lm-eval-harness dependency. Uses only stdlib + requests.

Usage:
    from evidence_eu_model import query_search_endpoint
    doc_ids = query_search_endpoint("http://localhost:8000", "health insurance card", top_k=5)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import quote

try:
    import requests
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_DEFAULT_TOP_K = 5


def _extract_doc_id(chunk_id: str, bank_id: str = "evidence-eu-docs") -> str:
    """
    Extract document ID from Hindsight chunk_id.

    Chunk ID format: {bank_id}_{doc_id}_{chunk_index}
    Example: "evidence-eu-docs_eurlex-32004R0883_0" → "eurlex-32004R0883"
    """
    if not chunk_id:
        return ""
    # Remove bank prefix: "evidence-eu-docs_eurlex-32004R0883_0" → "eurlex-32004R0883_0"
    prefix = f"{bank_id}_"
    if chunk_id.startswith(prefix):
        chunk_id = chunk_id[len(prefix):]
    # Remove trailing chunk index: "eurlex-32004R0883_0" → "eurlex-32004R0883"
    parts = chunk_id.rsplit("_", 1)
    return parts[0] if len(parts) == 2 else chunk_id


def query_search_endpoint(
    base_url: str,
    query: str,
    top_k: int = _DEFAULT_TOP_K,
    timeout: int = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """
    Query the EvidenceEU SSE search endpoint and return parsed results.

    Args:
        base_url: FastAPI base URL (e.g. "http://localhost:8000")
        query: Natural-language search query
        top_k: Maximum number of results to return
        timeout: Per-query timeout in seconds

    Returns:
        List of dicts with keys: document_id, text, rank, chunk_id, entities
        Empty list on error or no results.
    """
    if requests is None:
        raise ModuleNotFoundError(
            "The 'requests' package is required. Install via `pip install requests`."
        )

    url = f"{base_url}/api/v1/search/?q={quote(query)}&top_k={top_k}"
    headers = {
        "Accept": "text/event-stream",
        "X-GDPR-Consent": "true",
    }

    start = time.time()
    results: list[dict[str, Any]] = []
    current_event = ""

    try:
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # Parse SSE format: event: <type>\ndata: <json>\n\n
                if line.startswith(":"):
                    continue  # comment (keepalive ping)
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                if current_event != "result":
                    continue

                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    continue

                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if isinstance(data, dict):
                    chunk_id = data.get("chunk_id", "")
                    document_id = _extract_doc_id(chunk_id)
                    results.append({
                        "document_id": document_id,
                        "text": data.get("text", ""),
                        "rank": data.get("rank", len(results) + 1),
                        "chunk_id": chunk_id,
                        "entities": data.get("entities", []),
                    })

    except requests.exceptions.Timeout:
        logger.warning("SSE request timed out after %s s for query: %.60s...", timeout, query)
    except requests.exceptions.RequestException as exc:
        logger.error("SSE request failed: %s", exc)

    latency = time.time() - start
    if latency > timeout * 0.8:
        logger.warning("SSE request took %.2f s (close to timeout)", latency)

    return results
