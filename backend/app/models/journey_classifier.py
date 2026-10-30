"""Pydantic models for journey classification — detected intent, citizenship, and jurisdiction."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JourneyType = Literal["work", "relocate", "study", "maintain", "other"]
CitizenshipGroup = Literal["eu_citizen", "non_eu", "unknown"]
Confidence = Literal["high", "medium", "low"]


class JourneyClassification(BaseModel):
    """Result of classifying a user's first message."""

    journey_type: JourneyType | None = Field(description="Detected journey type")
    citizenship_group: CitizenshipGroup = Field(
        default="unknown", description="Detected citizenship group"
    )
    jurisdiction: str | None = Field(
        default=None, description="Detected target country (ISO 3166-1 alpha-2)"
    )
    confidence: Confidence = Field(default="low", description="How many signal categories matched")

    model_config = {"frozen": True}
