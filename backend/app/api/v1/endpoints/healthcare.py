# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Healthcare Endpoints — Phase 2 Only (never enabled during capstone)

This module is intentionally minimal. All endpoints here are gated by
the ENABLE_HEALTHCARE_PHASE2 feature flag which defaults to False.
Included so the api/v1 router can import it without AttributeError.
"""

from fastapi import APIRouter

router = APIRouter()
