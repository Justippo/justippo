#!/usr/bin/env python3
"""
run_eval.py — EvidenceEU Multilingual RAG Evaluation Runner

Evaluates retrieval quality of the EvidenceEU FastAPI SSE search endpoint
using standard IR metrics: recall@k, MRR, NDCG@k.

No lm-eval-harness dependency. Uses only stdlib + requests + rouge_score.

Usage::

    cd evidence-eu
    python docs/testing/eval/run_eval.py [--seed] [--seed-multilingual]

Environment:
    EVAL_BASE_URL  — FastAPI base URL (default: http://localhost:8000)
    EVAL_TIMEOUT   — per-query timeout in seconds (default: 30)
    EVAL_TOP_K     — top-k results to evaluate (default: 5)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from constants import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_TOP_K,
)
from evidence_eu_model import query_search_endpoint  # noqa: E402

_EMOJI_PASS = "\u2705"
_EMOJI_FAIL = "\u274c"
_EMOJI_WARN = "\u26a0\ufe0f"

logging.getLogger("urllib3").setLevel(logging.WARNING)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _check_backend_health(base_url: str, timeout: int = 5) -> bool:
    """Quick health check — returns True if backend is reachable."""
    import requests as _requests

    try:
        resp = _requests.get(f"{base_url}/api/v1/health/", timeout=timeout)
        return resp.status_code == 200
    except _requests.RequestException:
        return False


# ── Data loading ────────────────────────────────────────────────────────────


def _load_fixtures(lang: str) -> list[dict[str, Any]]:
    """Load QA fixtures for a language from JSONL."""
    fixture_path = _SCRIPT_DIR / "fixtures" / f"qa_{lang}.jsonl"
    items: list[dict[str, Any]] = []
    with open(fixture_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# ── IR Metrics (pure functions, no dependencies) ────────────────────────────


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of relevant documents found in top-k results."""
    if not relevant_ids:
        return 0.0
    hits = len(set(retrieved_ids[:k]) & relevant_ids)
    return hits / len(relevant_ids)


def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """Mean Reciprocal Rank — 1/rank of first relevant result, 0 if none."""
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Normalized Discounted Cumulative Gain (binary relevance)."""
    dcg = 0.0
    for i, doc_id in enumerate(retrieved_ids[:k]):
        if doc_id in relevant_ids:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because log2(1) = 0

    # Ideal DCG: all relevant docs at top positions
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    return dcg / idcg if idcg > 0 else 0.0


# ── Per-language evaluation ─────────────────────────────────────────────────


def evaluate_language(
    lang: str,
    base_url: str,
    top_k: int,
    timeout: int,
) -> dict[str, Any]:
    """Run all queries for a language and compute aggregate retrieval metrics."""
    fixtures = _load_fixtures(lang)

    per_query: list[dict[str, Any]] = []
    recall_scores: list[float] = []
    mrr_scores: list[float] = []
    ndcg_scores: list[float] = []

    for item in fixtures:
        query = item["query"]
        relevant_ids = set(item.get("relevant_doc_ids", []))
        if not relevant_ids and item.get("doc_id"):
            relevant_ids = {item["doc_id"]}

        results = query_search_endpoint(base_url, query, top_k=top_k, timeout=timeout)
        retrieved_ids = [r["document_id"] for r in results if r.get("document_id")]

        r_k = recall_at_k(retrieved_ids, relevant_ids, top_k)
        m = mrr(retrieved_ids, relevant_ids)
        n = ndcg_at_k(retrieved_ids, relevant_ids, top_k)

        recall_scores.append(r_k)
        mrr_scores.append(m)
        ndcg_scores.append(n)

        per_query.append({
            "query": query[:80],
            "relevant": sorted(relevant_ids),
            "retrieved": retrieved_ids[:top_k],
            "recall@k": r_k,
            "mrr": m,
            "ndcg@k": n,
        })

    n = len(fixtures) or 1
    return {
        "lang": lang,
        "n_queries": len(fixtures),
        "recall@k": sum(recall_scores) / n,
        "mrr": sum(mrr_scores) / n,
        "ndcg@k": sum(ndcg_scores) / n,
        "per_query": per_query,
    }


# ── Report builder ──────────────────────────────────────────────────────────


def build_report(
    base_url: str,
    top_k: int,
    timeout: int,
    results_map: dict[str, dict[str, Any]],
) -> str:
    """Build a Markdown report compatible with the existing docs/testing/ format."""
    lines: list[str] = [
        "# Multilingual RAG Retrieval Evaluation Report",
        "",
        f"**Date:** {_now()}  ",
        f"**Endpoint:** `{base_url}`  ",
        f"**Top-k:** {top_k}  ",
        f"**Timeout:** {timeout}s per query  ",
        "**Runner:** `docs/testing/eval/run_eval.py`  ",
        "",
        "## Test Environment",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| Backend | EvidenceEU FastAPI (SSE streaming) |",
        f"| Endpoint | `{base_url}/api/v1/search/?q=<query>&top_k={top_k}` |",
        f"| Timeout | {timeout}s |",
        f"| Top-k | {top_k} |",
        "| Metrics | recall@k, MRR, NDCG@k |",
        "| Dataset | 10 Q\u221fA pairs per language (cross-lingual) |",
        "",
        "## Results Summary",
        "",
        "| Language | Queries | recall@k | MRR | NDCG@k | Pass? |",
        "|----------|---------|----------|-----|--------|-------|",
    ]

    for lang in ["en", "de", "fr"]:
        data = results_map.get(lang, {})
        if not data:
            lines.append(f"| {lang.upper()} | 0 | - | - | - | {_EMOJI_WARN} No data |")
            continue

        r_k = data.get("recall@k", 0.0)
        m = data.get("mrr", 0.0)
        n = data.get("ndcg@k", 0.0)
        n_queries = data.get("n_queries", 0)

        # Pass criteria: recall@k >= 0.4 OR MRR >= 0.3
        passed = r_k >= 0.4 or m >= 0.3
        status = _EMOJI_PASS if passed else _EMOJI_FAIL

        lines.append(
            f"| {lang.upper()} | {n_queries} | {r_k:.3f} | {m:.3f} | {n:.3f} | {status} |"
        )

    # Per-language detail tables
    for lang in ["en", "de", "fr"]:
        data = results_map.get(lang, {})
        if not data or not data.get("per_query"):
            continue

        lines.extend([
            "",
            f"## {lang.upper()} Detail",
            "",
            "| # | Query | Retrieved (top-k) | recall@k | MRR | NDCG@k |",
            "|---|-------|-------------------|----------|-----|--------|",
        ])
        for i, pq in enumerate(data["per_query"], 1):
            q = pq["query"][:50]
            retrieved = ", ".join(r.split("-", 1)[-1][:18] for r in pq["retrieved"][:3])
            r_k = pq["recall@k"]
            m = pq["mrr"]
            n = pq["ndcg@k"]
            lines.append(f"| {i} | {q} | {retrieved} | {r_k:.3f} | {m:.3f} | {n:.3f} |")

    lines.extend([
        "",
        "## Pass Criteria",
        "",
        "- **recall@k \u2265 0.40** per language, OR **MRR \u2265 0.30**  ",
        "- All queries complete without timeout or HTTP error  ",
        "- No SSE stream parsing failures  ",
        "",
        "## Metric Definitions",
        "",
        "- **recall@k** \u2014 fraction of relevant documents found in top-k results.  ",
        "- **MRR** (Mean Reciprocal Rank) \u2014 1/rank of first relevant result.  ",
        "- **NDCG@k** (Normalized Discounted Cumulative Gain) \u2014 ranking quality with binary relevance.  ",
        "",
        "## Design Notes",
        "",
        "- Retrieval-only evaluation (no LLM synthesis). Measures whether the correct document appears in top-k results.  ",
        "- Document IDs matched against Hindsight `document_id` field in SSE response events.  ",
        "- Fixtures use real EUR-Lex CELEX IDs matching documents seeded by `scripts/seed_documents.py`.  ",
        "",
        "## Raw Output",
        "",
        "Full per-query results included in the detail tables above.",
        "",
        "---",
        "",
        "*This report is auto-generated by `run_eval.py` and fed directly into the "
        "Final D\u0026T document testing section.*",
    ])

    return "\n".join(lines)


# ── Seed helper ─────────────────────────────────────────────────────────────


def seed_hindsight(multilingual: bool = False) -> bool:
    """Seed Hindsight with EU documents via scripts/seed_documents.py."""
    seed_script = _REPO_ROOT / "scripts" / "seed_documents.py"
    if not seed_script.exists():
        print(f"[run_eval] Seed script not found: {seed_script}")
        return False

    cmd = [sys.executable, str(seed_script)]
    if multilingual:
        cmd.append("--multilingual")

    print(f"[run_eval] Seeding Hindsight: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            timeout=600,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[run_eval] Seed script failed (exit {result.returncode})")
            if result.stderr:
                print(f"[run_eval] stderr: {result.stderr[:500]}")
            return False
        print("[run_eval] Seeding complete")
        return True
    except subprocess.TimeoutExpired:
        print("[run_eval] Seed script timed out after 600s")
        return False
    except Exception as exc:
        print(f"[run_eval] Seed script error: {exc}")
        return False


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EvidenceEU Multilingual RAG Evaluation Runner"
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="Seed Hindsight with EN documents before running eval"
    )
    parser.add_argument(
        "--seed-multilingual", action="store_true",
        help="Seed Hindsight with EN+DE+FR documents before running eval"
    )
    parser.add_argument(
        "--base-url", default=None,
        help=f"FastAPI base URL (default: {DEFAULT_BASE_URL})"
    )
    parser.add_argument(
        "--timeout", type=int, default=None,
        help=f"Per-query timeout in seconds (default: {DEFAULT_TIMEOUT})"
    )
    parser.add_argument(
        "--top-k", type=int, default=None,
        help=f"Top-k results to evaluate (default: {DEFAULT_TOP_K})"
    )
    args = parser.parse_args()

    base_url = args.base_url or os.environ.get("EVAL_BASE_URL", DEFAULT_BASE_URL)
    timeout = args.timeout or int(os.environ.get("EVAL_TIMEOUT", DEFAULT_TIMEOUT))
    top_k = args.top_k or int(os.environ.get("EVAL_TOP_K", DEFAULT_TOP_K))

    # Health check
    print(f"[run_eval] Checking backend health at {base_url} ...")
    if not _check_backend_health(base_url):
        print(f"[run_eval] ERROR: Backend at {base_url} is unreachable.")
        print("           Start it with: cd backend && uv run uvicorn app.main:app --port 8000")
        return 1
    print("[run_eval] Backend OK")

    # Seed Hindsight if requested
    if args.seed or args.seed_multilingual or os.environ.get("EVAL_SEED") == "1":
        multilingual = args.seed_multilingual or os.environ.get("EVAL_SEED") == "1"
        if not seed_hindsight(multilingual=multilingual):
            print("[run_eval] WARNING: Seeding failed, proceeding with existing data")

    # Evaluate each language
    results_map: dict[str, dict[str, Any]] = {}
    for lang in ["en", "de", "fr"]:
        print(f"\n{'=' * 60}")
        print(f"Evaluating language: {lang.upper()}")
        print(f"{'=' * 60}")
        data = evaluate_language(lang, base_url, top_k, timeout)
        results_map[lang] = data
        print(
            f"  recall@{top_k}={data['recall@k']:.3f}  "
            f"MRR={data['mrr']:.3f}  "
            f"NDCG@{top_k}={data['ndcg@k']:.3f}"
        )

    # Build report
    report_md = build_report(base_url, top_k, timeout, results_map)
    report_path = Path("docs/testing/multilingual-eval-report.md")
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\n[run_eval] Report written to: {report_path}")

    # Print summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    all_pass = True
    for lang in ["en", "de", "fr"]:
        data = results_map.get(lang, {})
        r_k = data.get("recall@k", 0.0)
        m = data.get("mrr", 0.0)
        passed = r_k >= 0.4 or m >= 0.3
        status = "PASS" if passed else "FAIL"
        print(f"  {lang.upper()}: recall@{top_k}={r_k:.3f} MRR={m:.3f} [{status}]")
        if not passed:
            all_pass = False

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
