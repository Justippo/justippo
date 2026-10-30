# SPDX-License-Identifier: AGPL-3.0-or-later
"""
BabelDOC Sidecar Adapter — HTTP client for layout-preserving PDF translation.

Architecture: BabelDOC runs as an external Docker sidecar (AGPL-3.0 isolated).
This adapter communicates over HTTP only — BabelDOC is NEVER imported as a
Python module. See ADR-012 for the authoritative API contract.

AGPL Isolation: The HTTP boundary is what keeps AGPL from propagating to
EvidenceEU's MIT codebase. Do NOT import babeldoc or any of its submodules.

Pyodide-safe: Uses httpx (already a dependency) with async patterns compatible
with Cloudflare Python Workers. No threading, no socket, no subprocess.

DRY: Reuses retry/backoff patterns from http_forwarder.py where applicable.
The key difference: this adapter WAITS for a response (not fire-and-forget),
so it implements its own retry loop with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data contracts (mirrors ADR-012 sidecar API contract)
# ---------------------------------------------------------------------------


@dataclass
class BabelDocRequest:
    """Request payload for the BabelDOC sidecar translation endpoint."""

    source_lang: str
    target_lang: str
    document_b64: str
    preserve_layout: bool = True
    timeout_seconds: int = 120
    glossary_csv_b64: str | None = None
    options: dict[str, object] = field(default_factory=dict)


@dataclass
class BabelDocResponse:
    """Successful response from the BabelDOC sidecar."""

    translated_b64: str
    source_lang: str
    target_lang: str
    detected_lang: str
    processing_time_ms: float
    layout_preserved: bool
    pages_processed: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class BabelDocError:
    """Error envelope from the BabelDOC sidecar."""

    error_code: str
    message: str
    retryable: bool
    details: str | None = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BabelDocSidecarError(Exception):
    """Raised when the BabelDOC sidecar returns an error or is unreachable."""

    def __init__(self, error: BabelDocError) -> None:
        self.error = error
        super().__init__(f"BabelDOC sidecar error [{error.error_code}]: {error.message}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_RETRY_DELAYS = [2.0, 4.0, 8.0]  # Exponential backoff: 2s, 4s, 8s
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = {503, 504}


def _get_sidecar_url() -> str:
    """Read BABELDOC_URL from environment (or BABELDOC_SIDECAR_URL for backward compatibility)."""
    url = os.environ.get("BABELDOC_URL", os.environ.get("BABELDOC_SIDECAR_URL", "")).strip()
    if not url:
        raise RuntimeError(
            "BabelDOC sidecar not configured — set BABELDOC_URL env var (or BABELDOC_SIDECAR_URL for backward compatibility). "
            "See ADR-012 for deployment requirements."
        )
    return url.rstrip("/")


def _is_enabled() -> bool:
    """Check if BabelDOC is enabled via feature flag."""
    return os.environ.get("BABELDOC_ENABLED", "false").lower() in ("true", "1", "yes")


def _get_auth_headers() -> dict[str, str]:
    """Build the Authorization header when BABELDOC_AUTH_TOKEN is configured.

    No-op-safe: returns an empty dict when the token is unset, matching the
    sidecar's own no-op contract — local dev without a token continues to work.
    """
    token = os.environ.get("BABELDOC_AUTH_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def is_babeldoc_ready() -> bool:
    """Return whether production routing may offer layout-preserved translation.

    This is a configuration capability check, not a network health check. The
    deployment gate still requires the hosted sidecar readiness test before the
    feature flag is enabled.
    """
    return _is_enabled() and bool(
        os.environ.get("BABELDOC_URL", os.environ.get("BABELDOC_SIDECAR_URL", "")).strip()
    )


# ---------------------------------------------------------------------------
# Main translation function
# ---------------------------------------------------------------------------


async def translate(request: BabelDocRequest) -> BabelDocResponse:
    """Translate a PDF document via the BabelDOC sidecar.

    Implements exponential backoff retry on 503/504 (sidecar cold start or
    overload). Raises NotImplementedError if BABELDOC_ENABLED=false.
    Raises RuntimeError if BABELDOC_URL (or BABELDOC_SIDECAR_URL for backward compatibility) is not set.
    Raises BabelDocSidecarError on non-retryable errors.

    Args:
        request: Translation request with source/target language and PDF bytes.

    Returns:
        BabelDocResponse with translated PDF and metadata.
    """
    # Feature flag guard — same pattern as other integrations
    if not _is_enabled():
        raise NotImplementedError(
            "BabelDOC translation is disabled (BABELDOC_ENABLED=false). "
            "Enable it and configure BABELDOC_URL to use layout-preserving translation."
        )

    sidecar_url = _get_sidecar_url()
    endpoint = f"{sidecar_url}/translate"

    payload = {
        "source_lang": request.source_lang,
        "target_lang": request.target_lang,
        "document_b64": request.document_b64,
        "preserve_layout": request.preserve_layout,
        "glossary_csv_b64": request.glossary_csv_b64,
        "options": request.options,
    }

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx is a hard dependency; never absent
        raise RuntimeError("httpx is required for BabelDOC adapter") from exc

    last_error: BabelDocError | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                start = time.perf_counter()
                resp = await client.post(endpoint, json=payload, headers=_get_auth_headers())
                elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status_code == 200:
                data = resp.json()
                response_source = data.get("source_lang")
                response_target = data.get("target_lang")
                warnings = list(data.get("warnings", []))
                if response_source is None or response_target is None:
                    # Keep rolling deployments compatible while making the
                    # missing correlation metadata visible to the caller.
                    response_source = request.source_lang
                    response_target = request.target_lang
                    warnings.append("SIDECAR_LANGUAGE_PAIR_UNVERIFIED")
                if response_source != request.source_lang or response_target != request.target_lang:
                    raise BabelDocSidecarError(
                        BabelDocError(
                            error_code="INVALID_RESPONSE",
                            message="Sidecar returned a mismatched language pair",
                            retryable=True,
                        )
                    )
                return BabelDocResponse(
                    translated_b64=data["translated_b64"],
                    source_lang=response_source,
                    target_lang=response_target,
                    detected_lang=data.get("detected_lang", request.source_lang),
                    processing_time_ms=data.get("processing_time_ms", elapsed_ms),
                    layout_preserved=data.get("layout_preserved", True),
                    pages_processed=data.get("pages_processed", 0),
                    warnings=warnings,
                )

            # Parse error envelope
            if resp.status_code in _RETRYABLE_STATUS_CODES:
                last_error = BabelDocError(
                    error_code="SERVICE_UNAVAILABLE" if resp.status_code == 503 else "TIMEOUT",
                    message=f"Sidecar returned {resp.status_code} (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                    retryable=True,
                )
                if attempt < _MAX_ATTEMPTS - 1:
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "BabelDOC sidecar returned %d, retrying in %.1fs (attempt %d/%d)",
                        resp.status_code,
                        delay,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Last attempt exhausted — break with retryable error
                break

            # Non-retryable error
            try:
                error_data = resp.json().get("error", {})
                last_error = BabelDocError(
                    error_code=error_data.get("code", "UNKNOWN"),
                    message=error_data.get("message", resp.text[:200]),
                    retryable=error_data.get("retryable", False),
                    details=error_data.get("details"),
                )
            except Exception:
                last_error = BabelDocError(
                    error_code="UNKNOWN",
                    message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    retryable=False,
                )
            break

        except httpx.TimeoutException:
            last_error = BabelDocError(
                error_code="TIMEOUT",
                message=f"Request timed out after {request.timeout_seconds}s (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                retryable=True,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "BabelDOC request timed out, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue
        except httpx.ConnectError:
            last_error = BabelDocError(
                error_code="SERVICE_UNAVAILABLE",
                message=f"Cannot connect to BabelDOC sidecar at {sidecar_url} (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                retryable=True,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "BabelDOC sidecar unreachable, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue

    # All retries exhausted or non-retryable error
    assert last_error is not None
    raise BabelDocSidecarError(last_error)
