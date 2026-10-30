"""
constants.py — Shared constants for EvidenceEU RAG evaluation suite.

Single source of truth for metric names, Hindsight config, and language mappings.
Imported by run_eval.py and evidence_eu_model.py.
"""

from __future__ import annotations

import os

# ── Retrieval metric names ───────────────────────────────────────────────────
METRIC_RECALL_AT_K = "recall@k"
METRIC_MRR = "mrr"
METRIC_NDCG = "ndcg"

# ── Hindsight config ────────────────────────────────────────────────────────
HINDSIGHT_URL: str = os.getenv("HINDSIGHT_API_URL", "http://localhost:8600")
HINDSIGHT_BANK_ID: str = os.getenv("HINDSIGHT_BANK_ID", "evidence-eu-docs")

# ── Backend config ──────────────────────────────────────────────────────────
DEFAULT_BASE_URL: str = "http://localhost:8000"
DEFAULT_TIMEOUT: int = 15

# ── Language -> task mapping ────────────────────────────────────────────────
LANGUAGES: dict[str, str] = {
    "en": "rag_eval_en",
    "de": "rag_eval_de",
    "fr": "rag_eval_fr",
}

# ── Evaluation defaults ─────────────────────────────────────────────────────
DEFAULT_TOP_K: int = 10
