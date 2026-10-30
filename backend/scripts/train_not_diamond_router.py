# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Train a Not Diamond custom router using EvidenceEU's translation test cases.

Generates a CSV evaluation dataset by running 30 translation test cases
(docs/testing/translation-test-cases.yaml) through 3 candidate models:
  1. m2m100-1.2b (CF Workers AI — cheap)
  2. Apertus 8B (HuggingFace — sovereign European)
  3. Mistral Large (Mistral AI — European frontier)

Each translation is scored using the existing term-accuracy framework
(tests/translation_accuracy_utils.py). The CSV is then POSTed to Not Diamond's
/pzn/trainCustomRouter endpoint, which trains a custom router (5-15 min async)
and returns a preference_id.

Usage:
  cd backend && uv run python scripts/train_not_diamond_router.py

Requires env vars: MISTRAL_API_KEY, CF_WORKERS_AI_API_TOKEN, HF_API_TOKEN,
                   NOT_DIAMOND_API_KEY, CF_AIG_AUTHORIZATION (for gateway)
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from pathlib import Path

import aiofiles
import httpx
import yaml

# Ensure app imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.cloudflare.gateway import (  # noqa: E402
    get_gateway_auth_headers,
    get_gateway_url,
)
from tests.translation_accuracy_utils import normalize_for_comparison, term_present  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEST_CASES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "testing"
    / "translation-test-cases.yaml"
)
OUTPUT_CSV = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "testing"
    / "not_diamond_training_data.csv"
)
NOT_DIAMOND_API_URL = "https://api.notdiamond.ai/v2/pzn/trainCustomRouter"
GATEWAY_TIMEOUT = 60

# Candidate models for the custom router — must be is_custom=true per ND docs
CANDIDATES = [
    {
        "provider": "evidence-eu",
        "model": "m2m100-1.2b",
        "is_custom": True,
        "context_length": 1536,
        "input_price": 0.01,
        "output_price": 0.01,
        "latency": 0.5,
    },
    {
        "provider": "evidence-eu",
        "model": "apertus-8b",
        "is_custom": True,
        "context_length": 8192,
        "input_price": 0.5,
        "output_price": 0.5,
        "latency": 2.0,
    },
    {
        "provider": "evidence-eu",
        "model": "mistral-large",
        "is_custom": True,
        "context_length": 128000,
        "input_price": 2.0,
        "output_price": 6.0,
        "latency": 1.5,
    },
]

# ---------------------------------------------------------------------------
# Translation calls (via CF AI Gateway — no direct URLs)
# ---------------------------------------------------------------------------


async def translate_m2m100(client: httpx.AsyncClient, text: str, src: str, tgt: str) -> str:
    """Translate via CF Workers AI m2m100-1.2b."""
    url = get_gateway_url("workers-ai", "@cf/meta/m2m100-1.2b")
    headers = {
        "Authorization": f"Bearer {os.environ.get('CF_WORKERS_AI_API_TOKEN', '')}",
        "Content-Type": "application/json",
    }
    headers.update(get_gateway_auth_headers())
    payload = {"text": text, "source_lang": src if src != "auto" else "en", "target_lang": tgt}
    resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        return f"[ERROR m2m100 HTTP {resp.status_code}]"
    data = resp.json()
    result = data.get("result", {})
    return str(result.get("translated_text", ""))


async def translate_apertus(client: httpx.AsyncClient, text: str, src: str, tgt: str) -> str:
    """Translate via Apertus 8B running locally on Ollama (free, no API credits).

    Uses the local Ollama OpenAI-compatible endpoint at localhost:11434.
    Model: MichelRosselli/apertus:latest (Q4_K_M quantization of
    swiss-ai/Apertus-8B-Instruct-2509). Runs on Apple Silicon (M1 Max 32GB).

    This replaces the paid HuggingFace Router API which returned HTTP 402
    (monthly free credits depleted). Local inference is free and unlimited."""
    _LANG_NAMES = {"en": "English", "de": "German", "fr": "French"}
    src_name = _LANG_NAMES.get(src, src)
    tgt_name = _LANG_NAMES.get(tgt, tgt)

    url = "http://localhost:11434/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "MichelRosselli/apertus:latest",
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are a professional legal translator. "
                    f"Translate from {src_name} to {tgt_name}. "
                    f"Output only the translation."
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        return f"[ERROR Apertus HTTP {resp.status_code}]"
    data = resp.json()
    choices = data.get("choices", [])
    if choices:
        return str(choices[0].get("message", {}).get("content", ""))
    return "[ERROR no choices]"


async def translate_mistral_large(client: httpx.AsyncClient, text: str, src: str, tgt: str) -> str:
    """Translate via Mistral Large chat completion."""
    _LANG_NAMES = {"en": "English", "de": "German", "fr": "French"}
    src_name = _LANG_NAMES.get(src, src)
    tgt_name = _LANG_NAMES.get(tgt, tgt)
    url = get_gateway_url("mistral", "v1/chat/completions")
    headers = {
        "Authorization": f"Bearer {os.environ.get('MISTRAL_API_KEY', '')}",
        "Content-Type": "application/json",
    }
    headers.update(get_gateway_auth_headers())
    payload = {
        "model": "mistral-large-latest",
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are a professional legal translator. "
                    f"Translate from {src_name} to {tgt_name}. "
                    f"Output only the translation."
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        return f"[ERROR Mistral HTTP {resp.status_code}]"
    data = resp.json()
    choices = data.get("choices", [])
    if choices:
        return str(choices[0].get("message", {}).get("content", ""))
    return "[ERROR no choices]"


# ---------------------------------------------------------------------------
# Scoring (reuses the existing term-accuracy framework)
# ---------------------------------------------------------------------------


def score_translation(
    translated_text: str, expected_terms: list[dict], forbidden_terms: list[str]
) -> float:
    """Score a translation 0.0–1.0 based on term accuracy + forbidden term check."""
    if not translated_text or translated_text.startswith("[ERROR"):
        return 0.0
    normalized = normalize_for_comparison(translated_text)
    # Term accuracy: fraction of expected terms present
    if not expected_terms:
        return 1.0
    hits = 0
    for term in expected_terms:
        target = normalize_for_comparison(term.get("target", ""))
        if target and term_present(target, normalized):
            hits += 1
    term_score = hits / len(expected_terms)
    # Penalize forbidden terms
    for forbidden in forbidden_terms:
        if term_present(normalize_for_comparison(forbidden), normalized):
            term_score *= 0.5
    return round(term_score, 3)


# ---------------------------------------------------------------------------
# Main: generate CSV + train router
# ---------------------------------------------------------------------------


async def generate_training_data() -> list[dict[str, str]]:
    """Run all 30 test cases through 3 models, score, return CSV rows."""
    async with aiofiles.open(TEST_CASES_PATH) as f:
        content = await f.read()
        yaml_data = yaml.safe_load(content)
    test_cases = yaml_data.get("test_cases", [])
    print(f"Loaded {len(test_cases)} test cases from {TEST_CASES_PATH.name}")

    rows: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        for i, tc in enumerate(test_cases, 1):
            tc_id = tc.get("id", f"TC-{i:03d}")
            src = tc.get("source_lang", "en")
            tgt = tc.get("target_lang", "de")
            pages = tc.get("input_pages", [])
            text = " ".join(p.get("text", "") for p in pages)
            expected = tc.get("expected_terms", [])
            forbidden = tc.get("forbidden_terms", [])

            print(f"  [{i}/{len(test_cases)}] {tc_id} ({src}→{tgt})...", end=" ", flush=True)

            # Run all 3 models (Mistral has rate limits — add delay after)
            m2m_result = await translate_m2m100(client, text, src, tgt)
            apertus_result = await translate_apertus(client, text, src, tgt)
            mistral_result = await translate_mistral_large(client, text, src, tgt)
            # Rate-limit delay: Mistral free tier allows ~1 req/s.
            # Without this, 17/30 calls hit HTTP 429 in the previous run.
            await asyncio.sleep(1.5)

            # Score each
            m2m_score = score_translation(m2m_result, expected, forbidden)
            apertus_score = score_translation(apertus_result, expected, forbidden)
            mistral_score = score_translation(mistral_result, expected, forbidden)

            print(f"m2m={m2m_score} apertus={apertus_score} mistral={mistral_score}")

            rows.append(
                {
                    "prompt": f"Task: translation | language_pair={src}-{tgt} | text_length_bucket=medium | doc_type={tc.get('category', '')}",
                    "evidence-eu/m2m100-1.2b/response": m2m_result[:2000],
                    "evidence-eu/m2m100-1.2b/score": str(m2m_score),
                    "evidence-eu/apertus-8b/response": apertus_result[:2000],
                    "evidence-eu/apertus-8b/score": str(apertus_score),
                    "evidence-eu/mistral-large/response": mistral_result[:2000],
                    "evidence-eu/mistral-large/score": str(mistral_score),
                }
            )

    return rows


def write_csv(rows: list[dict[str, str]]) -> Path:
    """Write training data to CSV."""
    fieldnames = [
        "prompt",
        "evidence-eu/m2m100-1.2b/response",
        "evidence-eu/m2m100-1.2b/score",
        "evidence-eu/apertus-8b/response",
        "evidence-eu/apertus-8b/score",
        "evidence-eu/mistral-large/response",
        "evidence-eu/mistral-large/score",
    ]
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV written to {OUTPUT_CSV} ({len(rows)} rows)")
    return OUTPUT_CSV


async def train_router(csv_path: Path) -> str:
    """POST the CSV to Not Diamond's trainCustomRouter endpoint."""
    api_key = os.environ.get("NOT_DIAMOND_API_KEY", "")
    if not api_key:
        print("ERROR: NOT_DIAMOND_API_KEY not set — skipping training")
        return ""

    candidates_json = json.dumps(CANDIDATES)
    async with aiofiles.open(csv_path, "rb") as f:
        file_content = await f.read()

    files = {"dataset_file": ("training_data.csv", file_content, "text/csv")}
    data = {
        "language": "multilingual",
        "llm_providers": candidates_json,
        "prompt_column": "prompt",
        "maximize": "true",
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    print("\nTraining custom router on Not Diamond (5-15 min async)...")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(NOT_DIAMOND_API_URL, files=files, data=data, headers=headers)

    if resp.status_code >= 400:
        print(f"ERROR: Training failed (HTTP {resp.status_code}): {resp.text}")
        return ""

    result = resp.json()
    preference_id = result.get("preference_id", "")
    print(f"✅ Custom router trained! preference_id: {preference_id}")
    print(f"   Add to .env: NOT_DIAMOND_PREFERENCE_ID={preference_id}")
    return preference_id


async def main() -> None:
    print("=== Not Diamond Custom Router Training ===")
    print(f"Test cases: {TEST_CASES_PATH}")
    print(f"Output CSV: {OUTPUT_CSV}")
    print()

    rows = await generate_training_data()
    csv_path = write_csv(rows)

    preference_id = await train_router(csv_path)
    if preference_id:
        print(f"\n✅ Done! preference_id: {preference_id}")
    else:
        print("\n⚠️  CSV generated but training not completed. Run train_router manually.")


if __name__ == "__main__":
    asyncio.run(main())
