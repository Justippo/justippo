"""Structured output for reference-PDF requirements and EU-law context."""

from typing import Literal

from pydantic import BaseModel, Field


class DocumentRequirement(BaseModel):
    """One requirement stated by the uploaded document."""

    text: str
    kind: Literal["field", "instruction"]
    page_number: int | None = None


class EULawCitation(BaseModel):
    """Verified official source supporting generated EU-law context."""

    source_number: int = Field(ge=1)
    title: str
    url: str
    excerpt: str
    language: str
    document_id: str | None = None


class DocumentExplanation(BaseModel):
    """Reference-only explanation; never represents legal validation or advice."""

    document_type: str
    language: str
    requirements: list[DocumentRequirement]
    explanation: str | None = None
    legal_context_status: Literal[
        "grounded",
        "sources_only",
        "not_found",
        "unavailable",
    ]
    citations: list[EULawCitation]
    warnings: list[str] = Field(default_factory=list)
