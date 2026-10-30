# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Per-Tool Network Policy — egress declaration and audit decorator.

Linus DEC-0061 adaptation: declares per-tool egress expectations,
captures audit log entries when tools make network requests.

Usage:
    @network_policy(allow_egress=True, audit_egress=True)
    async def my_tool(...):
        ...

The decorator stores policy metadata in the wrapped function's
_network_policy attribute for AuditLogMiddleware to inspect.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class NetworkPolicy:
    """Egress declaration for a single tool/endpoint.

    Attributes:
        allow_egress: Whether this tool is permitted to make external requests.
        audit_egress: Whether egress URLs should be logged (metadata only —
                      URL hashes, never full URLs with PII).
        allowed_domains: Optional list of allowed domain suffixes
                         (e.g. [\"gateway.ai.cloudflare.com\"]).
        disallowed_domains: Optional list of blocked domain suffixes.
        egress_urls: Populated at runtime by the decorator — list of URL
                     hashes this tool attempted to contact.
    """

    tool_name: str = ""
    allow_egress: bool = False
    audit_egress: bool = True
    allowed_domains: list[str] = field(default_factory=list)
    disallowed_domains: list[str] = field(default_factory=list)
    egress_urls: list[str] = field(default_factory=list)


def network_policy(
    allow_egress: bool = False,
    audit_egress: bool = True,
    allowed_domains: list[str] | None = None,
    disallowed_domains: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator that annotates a function with egress policy metadata.

    The decorator does NOT intercept network calls — it stores the policy on
    the function object for middleware inspection. Actual egress enforcement
    is the responsibility of the caller (AuditLogMiddleware, etc.).

    Args:
        allow_egress: Whether this tool may make external requests.
        audit_egress: Whether egress URLs should be logged.
        allowed_domains: Permitted domain suffixes.
        disallowed_domains: Blocked domain suffixes.

    Returns:
        The original function with _network_policy attribute attached.
    """

    def decorator(func: F) -> F:
        func._network_policy = NetworkPolicy(  # type: ignore[attr-defined]
            tool_name=func.__name__,
            allow_egress=allow_egress,
            audit_egress=audit_egress,
            allowed_domains=allowed_domains or [],
            disallowed_domains=disallowed_domains or [],
        )
        return func

    return decorator


def record_egress(
    func: Callable[..., Any],
    url: str,
) -> str | None:
    """Record an egress URL against a tool's network policy.

    Computes a SHA256 hash of the URL (PII-safe) and appends it to the
    policy's egress_urls list. Returns the hash for logging purposes,
    or None if the tool has no policy or egress is not allowed.

    Args:
        func: The tool/callable (must have _network_policy attribute).
        url: The full URL being requested.

    Returns:
        URL hash string, or None if egress not permitted.
    """
    policy: NetworkPolicy | None = getattr(func, "_network_policy", None)
    if policy is None:
        logger.debug("record_egress: no policy on %s — allowing by default", func.__name__)
        return None

    if not policy.allow_egress:
        logger.warning("Egress blocked by policy for %s: %s", policy.tool_name, url)
        return None

    # Check domain allow/deny lists
    for domain in policy.disallowed_domains:
        if domain in url:
            logger.warning(
                "Egress blocked by disallowed domain %s for %s: %s",
                domain,
                policy.tool_name,
                url,
            )
            return None

    if policy.allowed_domains and not any(domain in url for domain in policy.allowed_domains):
        logger.warning(
            "Egress blocked — %s not in allowed domains for %s: permitted=%s",
            url,
            policy.tool_name,
            policy.allowed_domains,
        )
        return None

    # Log URL hash (never the URL itself — GDPR Art. 5)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    if policy.audit_egress:
        policy.egress_urls.append(url_hash)

    return url_hash


def get_policy(func: Callable[..., Any]) -> NetworkPolicy | None:
    """Return the NetworkPolicy attached to a callable, if any."""
    return getattr(func, "_network_policy", None)
