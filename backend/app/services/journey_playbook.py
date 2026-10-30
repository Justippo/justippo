"""
Journey Playbook Service — State machine for multi-turn step progression.

Pipeline position: Chat endpoint → JourneyClassifierService (first turn)
                                              → JourneyPlaybookService (every turn) → SSE journey_state_update

Each journey type has a playbook (ordered list of steps). The service computes
the current step based on facts collected so far and steps already completed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import cast

from app.models.journey_playbook import JourneyProgress, PlaybookStep

logger = logging.getLogger(__name__)


# ── Playbook definitions ──────────────────────────────────────────────────────

# Each step maps to a completion-check function that inspects `facts`.
# If the check function returns True, the step is considered complete.

Playbook = list[PlaybookStep]
FactChecker = dict[str, bool]


def _has_job_offer(facts: dict[str, object]) -> bool:
    return bool(facts.get("has_job_offer"))


def _has_citizenship(facts: dict[str, object]) -> bool:
    return bool(facts.get("citizenship_group")) or bool(facts.get("citizenship"))


def _has_qualifications(facts: dict[str, object]) -> bool:
    return bool(facts.get("qualification_recognized")) or bool(facts.get("profession_regulated"))


def _has_language(facts: dict[str, object]) -> bool:
    return bool(facts.get("language_level"))


def _has_purpose(facts: dict[str, object]) -> bool:
    return bool(facts.get("relocation_purpose")) or bool(facts.get("permit_type"))


def _has_financial_means(facts: dict[str, object]) -> bool:
    return bool(facts.get("financial_means"))


def _has_documents(facts: dict[str, object]) -> bool:
    return bool(facts.get("documents_ready"))


def _has_admission(facts: dict[str, object]) -> bool:
    return bool(facts.get("admission_letter")) or bool(facts.get("university_accepted"))


def _has_health_insurance(facts: dict[str, object]) -> bool:
    return bool(facts.get("health_insurance"))


def _has_authority(facts: dict[str, object]) -> bool:
    return bool(facts.get("authority_identified")) or bool(facts.get("responsible_office"))


# Step → checker function mapping
_STEP_CHECKERS: dict[PlaybookStep, Callable[[dict[str, object]], bool]] = {
    "check_permit_type": _has_job_offer,
    "check_citizenship": _has_citizenship,
    "check_qualifications": _has_qualifications,
    "check_language": _has_language,
    "check_purpose": _has_purpose,
    "check_financial": _has_financial_means,
    "check_documents": _has_documents,
    "check_admission": _has_admission,
    "check_health_insurance": _has_health_insurance,
    "check_authority": _has_authority,
}

# Journey type → citizenship group → ordered playbook steps
# EU citizens get shorter playbooks (freedom of movement), non-EU get full process.
_PLAYBOOKS: dict[str, dict[str, Playbook]] = {
    "work": {
        "eu_citizen": [
            "check_permit_type",
            "check_citizenship",
        ],
        "non_eu": [
            "check_permit_type",
            "check_citizenship",
            "check_qualifications",
            "check_language",
        ],
        "unknown": [
            "check_permit_type",
            "check_citizenship",
        ],
    },
    "relocate": {
        "eu_citizen": [
            "check_purpose",
            "check_citizenship",
        ],
        "non_eu": [
            "check_purpose",
            "check_citizenship",
            "check_financial",
            "check_documents",
        ],
        "unknown": [
            "check_purpose",
            "check_citizenship",
        ],
    },
    "study": {
        "eu_citizen": [
            "check_citizenship",
            "check_admission",
            "check_health_insurance",
        ],
        "non_eu": [
            "check_citizenship",
            "check_admission",
            "check_financial",
            "check_health_insurance",
        ],
        "unknown": [
            "check_citizenship",
            "check_admission",
        ],
    },
    "maintain": {
        "eu_citizen": [
            "check_purpose",
            "check_documents",
        ],
        "non_eu": [
            "check_purpose",
            "check_documents",
            "check_authority",
        ],
        "unknown": [
            "check_purpose",
            "check_documents",
        ],
    },
}


def _is_step_complete(step: PlaybookStep, facts: dict[str, object]) -> bool:
    checker = _STEP_CHECKERS.get(step)
    if checker is None:
        return False
    return checker(facts)


class JourneyPlaybookService:
    """
    Computes journey progression based on journey type, facts, and completed steps.

    No LLM call, no network IO. Pure deterministic logic on the in-memory journey state.
    """

    def compute_progress(
        self,
        journey_type: str | None,
        facts: dict[str, object] | None,
        completed_steps: list[str] | None,
        citizenship_group: str | None = None,
    ) -> JourneyProgress:
        """
        Determine the current step and update completed steps.

        Args:
            journey_type: The classified journey type (e.g. 'work', 'relocate', 'study').
            facts: Key-value facts collected so far from conversation.
            completed_steps: Steps the backend has already marked complete.
            citizenship_group: Detected citizenship group ('eu_citizen', 'non_eu', 'unknown').

        Returns:
            JourneyProgress with current_step and updated completed_steps.
        """
        if journey_type is None or journey_type not in _PLAYBOOKS:
            return JourneyProgress(current_step=None, completed_steps=[])

        citizenship = citizenship_group or "unknown"
        journey_playbooks = _PLAYBOOKS[journey_type]
        playbook = journey_playbooks.get(citizenship, journey_playbooks["unknown"])

        facts = facts or {}
        completed = set(completed_steps or [])

        # Check each step in order — if not already completed, check if it's done now
        for step in playbook:
            if step not in completed and _is_step_complete(step, facts):
                completed.add(step)

        # Remove any completed steps that are no longer valid (facts changed)
        for step in playbook:
            if step in completed and not _is_step_complete(step, facts):
                completed.discard(step)

        # Determine current step: first uncompleted step, or None if all done
        current: PlaybookStep | None = None
        for step in playbook:
            if step not in completed:
                current = step
                break

        return JourneyProgress(
            current_step=current,
            completed_steps=cast(
                list[PlaybookStep],
                sorted(completed, key=lambda s: playbook.index(s) if s in playbook else 999),
            ),
        )

    def get_playbook_steps(
        self, journey_type: str | None, citizenship_group: str | None = None
    ) -> Playbook:
        """Return the ordered steps for a journey type and citizenship group, or empty list."""
        if journey_type is None:
            return []
        journey_playbooks = _PLAYBOOKS.get(journey_type, {})
        citizenship = citizenship_group or "unknown"
        return journey_playbooks.get(citizenship, journey_playbooks.get("unknown", []))
