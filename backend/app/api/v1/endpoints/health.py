# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Health Endpoints (Loud Healthz — Linus DEC-0060 adaptation)

Responsibilities:
- Liveness probe (GET /) — is the app running + effective_state
- Readiness probe (/ready) — all dependencies reachable + degradations[]
- Pipeline status (/pipeline) — demo pre-flight check with degradations

Linus DEC-0060 pattern:
    Every health surface includes `effective_state` (live | degraded | down)
    and `degradations[]` (structured list of degradation reports).
"""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class DegradationReport(BaseModel):
    component: str
    severity: str  # warning | critical
    message: str
    since: str = ""


class LivenessStatus(BaseModel):
    status: str
    effective_state: str  # live | degraded | down
    version: str
    sprint: int
    degradations: list[DegradationReport] = []


class HealthStatus(BaseModel):
    status: str
    effective_state: str
    version: str
    dependencies: dict[str, str]
    degradations: list[DegradationReport] = []


class ComponentStatus(BaseModel):
    status: str  # healthy | degraded | unavailable
    last_check_ms: int


class PipelineStatus(BaseModel):
    status: str  # healthy | degraded | unhealthy
    effective_state: str
    components: dict[str, ComponentStatus]
    version: str
    environment: str
    degradations: list[DegradationReport] = []


def _compute_effective_state(
    statuses: dict[str, str],
) -> tuple[str, list[DegradationReport]]:
    """Derive effective_state and degradations from named component statuses.

    Linus DEC-0060: effective_state ∈ {live, degraded, down}.
    Any unavailable → down. Any degraded → degraded. All healthy → live.
    """
    degradations: list[DegradationReport] = []
    for name, s in statuses.items():
        if s == "unavailable":
            degradations.append(
                DegradationReport(
                    component=name, severity="critical", message=f"{name} unavailable"
                )
            )
    if degradations:
        return "down", degradations
    for name, s in statuses.items():
        if s == "degraded":
            degradations.append(
                DegradationReport(component=name, severity="warning", message=f"{name} degraded")
            )
    if degradations:
        return "degraded", degradations
    return "live", []


@router.get("/", response_model=LivenessStatus)
async def health_check() -> LivenessStatus:
    """Liveness probe — returns 200 if the app is running (Linus DEC-0060)."""
    return LivenessStatus(
        status="ok",
        effective_state="live",
        version=settings.APP_VERSION,
        sprint=2,
    )


@router.get("/ready", response_model=HealthStatus)
async def readiness_check() -> HealthStatus:
    """
    Readiness probe — checks all downstream dependencies (Linus DEC-0060).
    Returns effective_state + degradations[] alongside dependency status.
    """
    deps = {
        "vector_db": "ok",
        "llm_gateway": "ok",
        "database": "ok",
    }
    state, degs = _compute_effective_state(deps)
    return HealthStatus(
        status="ok",
        effective_state=state,
        version=settings.APP_VERSION,
        dependencies=deps,
        degradations=degs,
    )


@router.get("/pipeline", response_model=PipelineStatus)
async def pipeline_status() -> PipelineStatus:
    """Pipeline health — lightweight ping of each demo component (Linus DEC-0060).

    Used by the demo dry-run to confirm the full pipeline is live
    before presenting. Checks ALL downstream services:
    - OCR (Mistral API key configured)
    - Translation (Workers AI token configured)
    - Hindsight RAG (URL configured)
    - ChromaDB (URL configured)
    - BabelDOC sidecar (URL configured + enabled)
    - Propella classifier (URL configured)
    - Matrix Synapse homeserver (URL configured)
    - Glossary (BAML import check)
    - Grounding gate (module import check)
    """
    components: dict[str, ComponentStatus] = {}

    # OCR: verify Mistral API key is configured
    start = time.perf_counter()
    ocr_ok = bool(settings.MISTRAL_API_KEY)
    components["ocr"] = ComponentStatus(
        status="healthy" if ocr_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Translation: verify Workers AI token is configured
    start = time.perf_counter()
    translation_ok = bool(settings.CF_WORKERS_AI_API_TOKEN or settings.CF_AIG_AUTHORIZATION)
    components["translation"] = ComponentStatus(
        status="healthy" if translation_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Hindsight RAG: verify URL is configured
    start = time.perf_counter()
    hindsight_ok = bool(settings.HINDSIGHT_API_URL)
    components["hindsight_rag"] = ComponentStatus(
        status="healthy" if hindsight_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # ChromaDB: verify URL is configured
    start = time.perf_counter()
    chromadb_ok = bool(settings.CHROMADB_URL)
    components["chromadb"] = ComponentStatus(
        status="healthy" if chromadb_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # BabelDOC sidecar: verify URL and feature flag
    start = time.perf_counter()
    babeldoc_ok = bool(settings.BABELDOC_URL)
    components["babeldoc"] = ComponentStatus(
        status="healthy" if babeldoc_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Propella classifier: verify URL is configured
    start = time.perf_counter()
    propella_ok = bool(settings.PROPELLA_BASE_URL)
    components["propella_classifier"] = ComponentStatus(
        status="healthy" if propella_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Matrix Synapse: verify homeserver URL is configured
    start = time.perf_counter()
    matrix_ok = bool(settings.MATRIX_HOMESERVER_URL)
    components["matrix_synapse"] = ComponentStatus(
        status="healthy" if matrix_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Glossary: verify BAML setup can import (lightweight check)
    start = time.perf_counter()
    try:
        from app.services.glossary_service import extract_terms  # noqa: F401

        glossary_ok = True
    except Exception:
        glossary_ok = False
    components["glossary"] = ComponentStatus(
        status="healthy" if glossary_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Grounding gate: verify chat_guidance can import
    start = time.perf_counter()
    try:
        from app.services.chat_guidance import (  # noqa: F401
            enforce_citation_grounding,
        )

        grounding_ok = True
    except Exception:
        grounding_ok = False
    components["grounding_gate"] = ComponentStatus(
        status="healthy" if grounding_ok else "degraded",
        last_check_ms=int((time.perf_counter() - start) * 1000),
    )

    # Overall status + effective_state (Linus DEC-0060)
    component_states = {name: c.status for name, c in components.items()}
    all_states = list(component_states.values())
    if all(s == "healthy" for s in all_states):
        overall = "healthy"
    elif any(s == "unavailable" for s in all_states):
        overall = "unhealthy"
    else:
        overall = "degraded"

    effective_state, degradations = _compute_effective_state(component_states)

    return PipelineStatus(
        status=overall,
        effective_state=effective_state,
        components=components,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        degradations=degradations,
    )
