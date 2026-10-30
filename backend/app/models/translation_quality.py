"""Deterministic quality signals for extracted-text translation."""

from typing import Literal

from pydantic import BaseModel, Field


class TranslationQualityCheck(BaseModel):
    """One deterministic translation quality check."""

    code: str
    status: Literal["pass", "warning"]
    message: str


class TranslationQualityReport(BaseModel):
    """Summary of translation completeness and preservation checks."""

    status: Literal["pass", "review"]
    terminology_review_status: Literal[
        "applied",
        "checked_no_changes",
        "not_checked",
    ] = "not_checked"
    source_section_count: int = Field(ge=0)
    translated_section_count: int = Field(ge=0)
    failed_section_count: int = Field(ge=0)
    checks: list[TranslationQualityCheck] = Field(default_factory=list)
