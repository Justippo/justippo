"""Pydantic models for journey playbook — step definitions and progression state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PlaybookStep = Literal[
    "check_permit_type",
    "check_citizenship",
    "check_qualifications",
    "check_language",
    "check_purpose",
    "check_financial",
    "check_documents",
    "check_admission",
    "check_health_insurance",
    "check_authority",
]


class JourneyProgress(BaseModel):
    """Computed progress through a journey playbook."""

    current_step: PlaybookStep | None = Field(
        default=None,
        description="The step the user is currently on (null if no journey or all done)",
    )
    completed_steps: list[PlaybookStep] = Field(
        default_factory=list,
        description="Steps completed so far",
    )

    model_config = {"frozen": True}
