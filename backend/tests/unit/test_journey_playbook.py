"""Unit tests for the JourneyPlaybookService."""

from __future__ import annotations

from app.services.journey_playbook import JourneyPlaybookService


def _service() -> JourneyPlaybookService:
    return JourneyPlaybookService()


# ── work playbook ──────────────────────────────────────────────────────────


def test_work_initial_step() -> None:
    """No facts, no completed steps → first step (check_permit_type)."""
    progress = _service().compute_progress("work", {}, [])
    assert progress.current_step == "check_permit_type"
    assert progress.completed_steps == []


def test_work_advances_when_job_offer_present() -> None:
    """has_job_offer completes check_permit_type → next step is check_citizenship."""
    progress = _service().compute_progress("work", {"has_job_offer": True}, [])
    assert progress.current_step == "check_citizenship"
    assert progress.completed_steps == ["check_permit_type"]


def test_work_eu_citizen_shorter_playbook() -> None:
    """EU citizen: only check_permit_type + check_citizenship (freedom of movement)."""
    progress = _service().compute_progress(
        "work",
        {"has_job_offer": True, "citizenship_group": "eu_citizen"},
        [],
        "eu_citizen",
    )
    assert progress.current_step is None
    assert progress.completed_steps == ["check_permit_type", "check_citizenship"]


def test_work_non_eu_full_playbook() -> None:
    """Non-EU: full process with qualifications + language."""
    progress = _service().compute_progress(
        "work",
        {"has_job_offer": True, "citizenship_group": "non_eu"},
        [],
        "non_eu",
    )
    assert progress.current_step == "check_qualifications"
    assert progress.completed_steps == ["check_permit_type", "check_citizenship"]


def test_work_all_steps_complete_non_eu() -> None:
    """All facts present → current_step is None (journey complete)."""
    progress = _service().compute_progress(
        "work",
        {
            "has_job_offer": True,
            "citizenship_group": "non_eu",
            "qualification_recognized": True,
            "language_level": "B1",
        },
        [],
        "non_eu",
    )
    assert progress.current_step is None
    assert progress.completed_steps == [
        "check_permit_type",
        "check_citizenship",
        "check_qualifications",
        "check_language",
    ]


def test_work_partial_existing_completed() -> None:
    """Starting with some completed steps picks up at the right place."""
    progress = _service().compute_progress(
        "work",
        {"has_job_offer": True, "citizenship_group": "non_eu"},
        ["check_permit_type"],
        "non_eu",
    )
    assert progress.current_step == "check_qualifications"
    assert progress.completed_steps == ["check_permit_type", "check_citizenship"]


def test_work_fact_removed_regression() -> None:
    """If a fact is removed, the step reverts to incomplete."""
    progress = _service().compute_progress(
        "work",
        {},  # has_job_offer was previously set but now missing
        ["check_permit_type", "check_citizenship"],
    )
    assert progress.current_step == "check_permit_type"
    assert progress.completed_steps == []


def test_work_unknown_citizenship_uses_default() -> None:
    """Unknown citizenship falls back to the unknown playbook."""
    progress = _service().compute_progress(
        "work",
        {"has_job_offer": True},
        [],
        "unknown",
    )
    assert progress.current_step == "check_citizenship"
    assert progress.completed_steps == ["check_permit_type"]


# ── relocate playbook ──────────────────────────────────────────────────────


def test_relocate_initial_step() -> None:
    progress = _service().compute_progress("relocate", {}, [])
    assert progress.current_step == "check_purpose"


def test_relocate_advances_non_eu() -> None:
    """Non-EU: full process with financial + documents."""
    progress = _service().compute_progress(
        "relocate",
        {"relocation_purpose": "family_reunification", "citizenship_group": "non_eu"},
        [],
        "non_eu",
    )
    assert progress.current_step == "check_financial"
    assert progress.completed_steps == ["check_purpose", "check_citizenship"]


def test_relocate_eu_citizen_shorter_playbook() -> None:
    """EU citizen: only check_purpose + check_citizenship."""
    progress = _service().compute_progress(
        "relocate",
        {"relocation_purpose": "work", "citizenship_group": "eu_citizen"},
        [],
        "eu_citizen",
    )
    assert progress.current_step is None
    assert progress.completed_steps == ["check_purpose", "check_citizenship"]


def test_relocate_financial_and_documents_non_eu() -> None:
    """Non-EU: full completion with financial + documents."""
    progress = _service().compute_progress(
        "relocate",
        {
            "relocation_purpose": "work",
            "citizenship_group": "non_eu",
            "financial_means": True,
            "documents_ready": True,
        },
        [],
        "non_eu",
    )
    assert progress.current_step is None
    assert "check_documents" in progress.completed_steps


# ── study playbook ─────────────────────────────────────────────────────────


def test_study_initial_step() -> None:
    progress = _service().compute_progress("study", {}, [])
    assert progress.current_step == "check_citizenship"


def test_study_advances_non_eu() -> None:
    """Non-EU: full process with financial."""
    progress = _service().compute_progress(
        "study",
        {"citizenship_group": "non_eu", "admission_letter": True},
        [],
        "non_eu",
    )
    assert progress.current_step == "check_financial"


def test_study_eu_citizen_shorter_playbook() -> None:
    """EU citizen: no financial step needed."""
    progress = _service().compute_progress(
        "study",
        {"citizenship_group": "eu_citizen", "admission_letter": True},
        [],
        "eu_citizen",
    )
    assert progress.current_step == "check_health_insurance"


def test_study_eu_citizen_all_complete() -> None:
    """EU citizen: admission + insurance → complete."""
    progress = _service().compute_progress(
        "study",
        {
            "citizenship_group": "eu_citizen",
            "admission_letter": True,
            "health_insurance": True,
        },
        [],
        "eu_citizen",
    )
    assert progress.current_step is None
    assert progress.completed_steps == [
        "check_citizenship",
        "check_admission",
        "check_health_insurance",
    ]


def test_study_non_eu_all_complete() -> None:
    """Non-EU: admission + financial + insurance → complete."""
    progress = _service().compute_progress(
        "study",
        {
            "citizenship_group": "non_eu",
            "admission_letter": True,
            "financial_means": True,
            "health_insurance": True,
        },
        [],
        "non_eu",
    )
    assert progress.current_step is None
    assert progress.completed_steps == [
        "check_citizenship",
        "check_admission",
        "check_financial",
        "check_health_insurance",
    ]


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_none_journey_type_returns_empty() -> None:
    progress = _service().compute_progress(None, {}, [])
    assert progress.current_step is None
    assert progress.completed_steps == []


def test_unknown_journey_type_returns_empty() -> None:
    progress = _service().compute_progress("other", {}, [])
    assert progress.current_step is None
    assert progress.completed_steps == []


def test_empty_facts_no_crash() -> None:
    progress = _service().compute_progress("work", None, None)
    assert progress.current_step == "check_permit_type"
    assert progress.completed_steps == []


def test_model_is_frozen() -> None:
    progress = _service().compute_progress("work", {}, [])
    assert progress.model_config.get("frozen") is True


def test_get_playbook_steps_work_eu() -> None:
    steps = _service().get_playbook_steps("work", "eu_citizen")
    assert steps == ["check_permit_type", "check_citizenship"]


def test_maintain_eu_citizen_first_step() -> None:
    """EU citizen maintain: purpose + documents steps."""
    progress = _service().compute_progress(
        "maintain",
        {},
        [],
        "eu_citizen",
    )
    assert progress.current_step == "check_purpose"
    assert progress.completed_steps == []


def test_maintain_eu_citizen_all_complete() -> None:
    """EU citizen: purpose + documents → complete."""
    progress = _service().compute_progress(
        "maintain",
        {
            "relocation_purpose": "register_address",
            "documents_ready": True,
        },
        [],
        "eu_citizen",
    )
    assert progress.current_step is None
    assert progress.completed_steps == ["check_purpose", "check_documents"]


def test_maintain_non_eu_needs_authority() -> None:
    """Non-EU citizen maintain: requires authority identification."""
    progress = _service().compute_progress(
        "maintain",
        {
            "relocation_purpose": "renew_permit",
            "documents_ready": True,
        },
        [],
        "non_eu",
    )
    assert progress.current_step == "check_authority"
    assert progress.completed_steps == ["check_purpose", "check_documents"]


def test_maintain_non_eu_all_complete() -> None:
    """Non-EU: purpose + documents + authority → complete."""
    progress = _service().compute_progress(
        "maintain",
        {
            "relocation_purpose": "renew_permit",
            "documents_ready": True,
            "authority_identified": True,
        },
        [],
        "non_eu",
    )
    assert progress.current_step is None
    assert progress.completed_steps == [
        "check_purpose",
        "check_documents",
        "check_authority",
    ]


def test_get_playbook_steps_work_non_eu() -> None:
    steps = _service().get_playbook_steps("work", "non_eu")
    assert steps == [
        "check_permit_type",
        "check_citizenship",
        "check_qualifications",
        "check_language",
    ]


def test_get_playbook_steps_none() -> None:
    steps = _service().get_playbook_steps(None)
    assert steps == []


def test_get_playbook_steps_unknown() -> None:
    steps = _service().get_playbook_steps("other")
    assert steps == []


def test_get_playbook_steps_defaults_to_unknown() -> None:
    """Unknown citizenship falls back to the unknown playbook."""
    steps = _service().get_playbook_steps("work", None)
    assert steps == ["check_permit_type", "check_citizenship"]
