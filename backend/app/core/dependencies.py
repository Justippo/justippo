# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Core Dependencies — Reusable FastAPI dependencies.

Responsibilities:
- Feature flag gating via require_feature()
- Shared auth/security dependencies (future)
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings


def require_feature(flag: str) -> Any:
    """Create a FastAPI dependency that gates an endpoint behind a feature flag.

    Usage:
        @router.post("/endpoint", dependencies=[Depends(require_feature("ENABLE_X"))])
        async def endpoint(): ...

    Raises HTTP 403 with {"detail": "feature not enabled", "flag": <flag>}
    if the flag is falsy on the settings object.
    """

    async def _dependency() -> None:
        value = getattr(settings, flag, False)
        if not value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"detail": "feature not enabled", "flag": flag},
            )

    return _dependency
