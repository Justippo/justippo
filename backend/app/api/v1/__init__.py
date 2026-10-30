# SPDX-License-Identifier: AGPL-3.0-or-later
"""
API v1 — Router Registration

Wires all endpoint modules into a single v1 router.
Feature-flagged routes use the require_feature() dependency — the router
is always registered so tests can exercise the 403 path without import tricks.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    chat,
    documents,
    exchange,
    glossary,
    health,
    matrix_auth,
    search,
    stats,
    translate,
)
from app.core.config import settings

router = APIRouter()

router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(translate.router, prefix="/translate", tags=["translate"])
router.include_router(glossary.router, prefix="/glossary", tags=["glossary"])
router.include_router(stats.router, prefix="/stats", tags=["stats"])

# Sprint 3 — Matrix cross-border exchange (gated by require_feature dependency)
router.include_router(exchange.router, prefix="/exchange", tags=["exchange"])

# Matrix OAuth authentication. The router stays registered so clients can query
# its false-by-default status; all state-changing endpoints enforce their own flag.
router.include_router(matrix_auth.router, prefix="/auth", tags=["auth"])

# Phase 2 — Healthcare endpoints (never enabled during capstone)
if settings.ENABLE_HEALTHCARE_PHASE2:
    from app.api.v1.endpoints import healthcare

    router.include_router(healthcare.router, prefix="/healthcare", tags=["healthcare"])
