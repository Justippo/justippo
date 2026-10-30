"""Eurostat migration statistics endpoint (issue #232).

GET /api/v1/stats/migration
Returns cached migration statistics from Eurostat's migr_pop1ctz dataset.
Uses D1 cache with 24h TTL; falls back to last-known-good snapshot if
Eurostat is unreachable.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.d1_client import D1Client
from app.repositories.eurostat_repo import EurostatRepo

logger = logging.getLogger(__name__)

router = APIRouter()

_GEO_FILTERS = ["DE", "FR", "IT", "ES", "NL", "AT", "BE", "PL", "SE", "EL", "EU27_2020"]


def _build_query_params() -> str:
    """Build URL query params — Eurostat uses repeated geo params, not comma-separated."""
    parts = [
        "format=JSON",
        "freq=A",
        "citizen=FOR_STLS",
        "sex=T",
        "age=TOTAL",
        "unit=NR",
        "time=2023",
    ]
    for geo in _GEO_FILTERS:
        parts.append(f"geo={geo}")
    return "&".join(parts)


@router.get("/migration")
async def get_migration_stats(request: Request) -> JSONResponse:
    """Return migration statistics, cached in D1 with 24h TTL.

    Flow:
    1. Check D1 for a fresh snapshot (within TTL) -> return immediately
    2. If stale or missing, fetch from Eurostat API
    3. If Eurostat fetch fails, return last-known-good snapshot (graceful degradation)
    4. If no snapshot at all, return 503
    """
    db = D1Client.from_scope(request.scope)
    repo = EurostatRepo(db)

    # 1. Check D1 cache
    cached = await repo.get_fresh_snapshot()
    if cached is not None:
        return JSONResponse(status_code=200, content=cached)

    # 2. Fetch from Eurostat
    try:
        url = f"{settings.EUROSTAT_API_URL}?{_build_query_params()}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            logger.warning("Eurostat API returned %d", resp.status_code)
            raise httpx.HTTPStatusError("Eurostat error", request=resp.request, response=resp)

        data = resp.json()

        # 3. Cache the fresh response in D1
        await repo.save_snapshot(data)

        return JSONResponse(status_code=200, content=data)

    except Exception as exc:
        logger.warning("Eurostat fetch failed: %s", exc)

        # 4. Graceful degradation: return last-known-good snapshot
        fallback = await repo.get_last_snapshot()
        if fallback is not None:
            return JSONResponse(
                status_code=200,
                content={**fallback, "warning": "STALE_DATA"},
            )

        # 5. No data at all
        return JSONResponse(
            status_code=503,
            content={"error": "Migration statistics temporarily unavailable"},
        )
