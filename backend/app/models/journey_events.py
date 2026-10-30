"""Pydantic models for structured Chat response events — next step, clarification, checklist, action plan."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProgressSummary(BaseModel):
    """Summary of step progress through a playbook."""

    completed: int = Field(ge=0, description="Number of completed steps")
    total: int = Field(ge=0, description="Total steps in playbook")


class NextStepEvent(BaseModel):
    """SSE event emitted to indicate the current step and progress."""

    step: str = Field(description="Step identifier (e.g. 'check_permit_type')")
    label: str = Field(description="Human-readable step label")
    description: str = Field(description="What this step involves")
    progress: ProgressSummary

    model_config = {"frozen": True}


class ClarificationOption(BaseModel):
    """An option within a clarification question."""

    label: str = Field(description="Display text for the option")
    value: str = Field(description="Machine-readable value")


class ClarificationQuestionEvent(BaseModel):
    """SSE event emitted when a required fact is missing — asks the user a question."""

    question: str = Field(description="Question to ask the user")
    type: Literal["yes_no", "multiple_choice", "free_text"] = Field(
        description="How this question should be rendered"
    )
    options: list[ClarificationOption] = Field(
        default_factory=list,
        description="Choices (for yes_no or multiple_choice)",
    )

    model_config = {"frozen": True}


class DocumentItem(BaseModel):
    """A document the user may need for this journey step."""

    name: str = Field(description="Document name (e.g. 'Employment contract')")
    description: str = Field(description="What this document proves or is used for")
    required: bool = Field(description="Whether this document is mandatory")


class DocumentChecklistEvent(BaseModel):
    """SSE event listing documents relevant to the current step."""

    step: str = Field(description="The step these documents relate to")
    documents: list[DocumentItem]

    model_config = {"frozen": True}


class ActionPlanStep(BaseModel):
    """A single step in the action plan summary."""

    label: str = Field(description="Step label")
    status: Literal["completed", "current", "pending"] = Field(
        description="Whether this step is done, active, or not yet reached"
    )


class ActionPlanEvent(BaseModel):
    """SSE event with the full action plan overview."""

    journey_type: str = Field(description="Journey type identifier")
    steps: list[ActionPlanStep]

    model_config = {"frozen": True}
