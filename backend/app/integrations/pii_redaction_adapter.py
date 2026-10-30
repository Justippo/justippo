# SPDX-License-Identifier: AGPL-3.0-or-later
"""
PII Redaction Adapter — HTTP client for the Presidio + spaCy sidecar.

Architecture: The PII redaction sidecar runs as an external Docker container
(same pattern as BabelDOC, ADR-012). This adapter communicates over HTTP only
— Presidio and spaCy are NEVER imported as Python modules in the backend.

Pyodide-safe: Uses httpx (already a dependency) with async patterns compatible
with Cloudflare Python Workers. No threading, no socket, no subprocess.

GDPR purpose: Redact personal data (names, addresses, dates, ID numbers) from
OCR-extracted text BEFORE it reaches external translation backends (CF Workers
AI, Mistral). This is GDPR Article 5(1)(c) data minimisation — PII never leaves
our infrastructure because the sidecar runs in our own Docker container.

DRY: Mirrors the structure of babeldoc_adapter.py (data contracts, exceptions,
retry/backoff, feature-flag guard). The key difference: redaction is a
pre-processing step that returns redacted text on success and falls back to
unredacted text on failure (translation should not be blocked by redaction
errors).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class PIIRedactionRequest:
    """Request payload for the PII redaction sidecar."""

    text: str
    language: str = "en"
    entities: list[str] | None = None
    timeout_seconds: int = 10


@dataclass
class PIIRedactionResult:
    """Successful response from the PII redaction sidecar."""

    redacted_text: str
    entity_count: int
    entity_types: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0


@dataclass
class PIIRedactionError:
    """Error envelope from the PII redaction sidecar."""

    error_code: str
    message: str
    retryable: bool
    details: str | None = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PIIRedactionSidecarError(Exception):
    """Raised when the PII redaction sidecar returns an error or is unreachable."""

    def __init__(self, error: PIIRedactionError) -> None:
        self.error = error
        super().__init__(f"PII redaction sidecar error [{error.error_code}]: {error.message}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_RETRY_DELAYS = [0.5, 1.0, 2.0]  # Shorter than BabelDOC — redaction should be fast
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = {503, 504}


def _get_sidecar_url() -> str:
    """Read PII_REDACTION_BASE_URL from environment."""
    url = os.environ.get("PII_REDACTION_BASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "PII redaction sidecar not configured — set PII_REDACTION_BASE_URL env var."
        )
    return url.rstrip("/")


def _is_enabled() -> bool:
    """Check if PII redaction is enabled via feature flag."""
    return os.environ.get("PII_REDACTION_ENABLED", "false").lower() in ("true", "1", "yes")


def is_redaction_ready() -> bool:
    """Return whether PII redaction is configured and enabled.

    This is a configuration capability check, not a network health check.
    """
    return _is_enabled() and bool(os.environ.get("PII_REDACTION_BASE_URL", "").strip())


# ---------------------------------------------------------------------------
# Main redaction function
# ---------------------------------------------------------------------------


async def redact(request: PIIRedactionRequest) -> PIIRedactionResult:
    """Redact PII from text via the sidecar.

    Implements exponential backoff retry on 503/504.
    Raises PIIRedactionSidecarError on non-retryable errors.

    Args:
        request: Redaction request with text, language, and optional entity list.

    Returns:
        PIIRedactionResult with redacted text and entity metadata.
    """
    if not _is_enabled():
        # When disabled, this function should not be called — the caller
        # (TranslationService) checks is_redaction_ready() first. But we guard
        # here as a safety net.
        raise NotImplementedError("PII redaction is disabled (PII_REDACTION_ENABLED=false).")

    sidecar_url = _get_sidecar_url()
    endpoint = f"{sidecar_url}/redact"

    payload: dict[str, object] = {
        "text": request.text,
        "language": request.language,
    }
    if request.entities is not None:
        payload["entities"] = request.entities

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx is a hard dependency; never absent
        raise RuntimeError("httpx is required for PII redaction adapter") from exc

    last_error: PIIRedactionError | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                start = time.perf_counter()
                resp = await client.post(endpoint, json=payload)
                elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status_code == 200:
                data = resp.json()
                return PIIRedactionResult(
                    redacted_text=data["redacted_text"],
                    entity_count=data.get("entity_count", 0),
                    entity_types=data.get("entity_types", []),
                    processing_time_ms=data.get("processing_time_ms", elapsed_ms),
                )

            if resp.status_code in _RETRYABLE_STATUS_CODES:
                last_error = PIIRedactionError(
                    error_code="SERVICE_UNAVAILABLE" if resp.status_code == 503 else "TIMEOUT",
                    message=f"Sidecar returned {resp.status_code} (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                    retryable=True,
                )
                if attempt < _MAX_ATTEMPTS - 1:
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "PII redaction sidecar returned %d, retrying in %.1fs (attempt %d/%d)",
                        resp.status_code,
                        delay,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    await asyncio.sleep(delay)
                    continue
                break

            # Non-retryable error
            try:
                error_data = resp.json().get("error", {})
                last_error = PIIRedactionError(
                    error_code=error_data.get("code", "UNKNOWN"),
                    message=error_data.get("message", resp.text[:200]),
                    retryable=error_data.get("retryable", False),
                    details=error_data.get("details"),
                )
            except Exception:
                last_error = PIIRedactionError(
                    error_code="UNKNOWN",
                    message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    retryable=False,
                )
            break

        except httpx.TimeoutException:
            last_error = PIIRedactionError(
                error_code="TIMEOUT",
                message=f"Request timed out after {request.timeout_seconds}s (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                retryable=True,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "PII redaction request timed out, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue
        except httpx.ConnectError:
            last_error = PIIRedactionError(
                error_code="SERVICE_UNAVAILABLE",
                message=f"Cannot connect to PII redaction sidecar at {sidecar_url} (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                retryable=True,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "PII redaction sidecar unreachable, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue

    assert last_error is not None
    raise PIIRedactionSidecarError(last_error)


async def redact_with_fallback(
    request: PIIRedactionRequest,
) -> tuple[str, bool, PIIRedactionResult | None]:
    """Redact PII from text, falling back to unredacted text on failure.

    This is the call TranslationService should use. It never raises — if the
    sidecar is unavailable, it returns the original text with a warning log.
    Translation (the user's primary intent) should not be blocked by redaction
    errors.

    Returns:
        Tuple of (redacted_or_original_text, redaction_succeeded, result_or_none).
    """
    try:
        result = await redact(request)
        return result.redacted_text, True, result
    except PIIRedactionSidecarError as exc:
        logger.warning(
            "PII redaction failed (%s), proceeding with unredacted text: %s",
            exc.error.error_code,
            exc.error.message,
        )
        return request.text, False, None
    except Exception as exc:
        logger.warning(
            "PII redaction failed unexpectedly (%s), proceeding with unredacted text",
            type(exc).__name__,
        )
        return request.text, False, None
