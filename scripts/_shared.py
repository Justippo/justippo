from __future__ import annotations

import os

import httpx

from scripts._colors import GREEN, RED, BOLD, DIM, CYAN, YELLOW, RESET, hr

D1_API_URL: str = os.getenv("D1_API_URL", "http://localhost:8787")
CF_AI_GATEWAY_URL: str = os.getenv(
    "CF_AI_GATEWAY_URL",
    "https://gateway.ai.cloudflare.com/v1/9f26393d5ba4186296b36e2af8714b1c/evidence-eu-gateway",
)
DRY_RUN: bool = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")


def fetch_documents(http: httpx.Client) -> list[dict]:
    resp = http.get(f"{D1_API_URL}/api/v1/documents/", timeout=30)
    resp.raise_for_status()
    return resp.json().get("documents", resp.json())
