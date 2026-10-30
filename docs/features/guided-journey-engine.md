# Guided Journey Engine

Architecture and design for the EvidenceEU guided-process chat engine. This enables the chat interface to detect what the user wants to do, track their progress through a step-by-step workflow, and prevent repetition.

## Motivation

Users often come to EvidenceEU not just to ask a question but to accomplish a task: "I want to work in Germany," "How do I get a residence permit?" etc. A plain RAG chat answers the question but doesn't understand that the user's real need is a multi-step process. The guided journey engine builds this context gradually across turns.

## Steps

| Step | Name | Description | Status |
|------|------|-------------|--------|
| 1 | Structured ephemeral state + repetition detection | JourneyState type, useJourneyState hook, helpers for detecting repeated questions/actions/sources/facts (PR #250) | Done |
| 2 | Journey classifier service | Backend deterministic classifier that detects journey type, citizenship, and jurisdiction from first message (PR #252) | Done |
| 3 | Multi-turn step progression | Backend state machine that advances through journey steps; frontend presents different guidance based on current step | Done |
| 4 | Citizen-specific playbooks | Different workflows for EU citizens vs non-EU, per journey type | Done |

## Module Layout

```
backend/
  app/
    services/
      journey_classifier.py       <- NEW: JourneyClassifierService
    models/
      journey_classifier.py       <- NEW: Pydantic models
    api/v1/endpoints/
      chat.py                     <- MODIFIED: added journey_state_update SSE event
frontend/
  src/
    lib/
      journey-state.ts            <- Shared types (JourneyState, JourneyType, etc.)
    hooks/
      useJourneyState.ts          <- Hook for managing journey state
    api/
      journey-types.ts            <- TypeScript port of backend models
```

## Data Flow

```
User first message
  -> chat_stream() endpoint
  -> JourneyClassifierService.classify() (deterministic, no LLM)
  -> SSE event: journey_state_update (on first turn only)
  -> Browser receives event
  -> useJourneyState.updateFromResponse() updates in-memory state
  -> journey_type, citizenship_group, jurisdiction set for rest of conversation
```

## Journey Classifier

Deterministic keyword/regex classifier -- no LLM call, no network IO, no additional latency.

### Detection Methods

**Jurisdiction:** Regex-based mapping of country names and demonyms in English, German, and French to ISO 3166-1 alpha-2 codes.

**Journey type:** Keyword scoring matrix (matches are counted, highest score wins):

| Journey type | Trigger keywords |
|---|---|
| work_in_germany | work, job, employment, hired, Blue Card, employer, employed, Arbeiten, arbeiten, Job, Stelle, Arbeit |
| relocate_to_germany | relocate, move, residence permit, move to, settlement, Aufenthalt, Umzug, umziehen, permit |
| study_in_germany | study, student, university, studies, Ausbildung, Studium, Student |
| other | None of the above (default when no keyword matches) |

**Citizenship group:** Keyword-based:

| Group | Trigger keywords |
|---|---|
| eu_citizen | EU, European Union, EU-Burger, EU citizen, EU member state, European citizen |
| non_eu | non-EU, third-country, non-EU citizen, outside the EU, not EU |
| unknown | Neither detected |

**Confidence:**
- high: jurisdiction + journey type + citizenship all detected
- medium: jurisdiction + at least one of journey type/citizenship detected
- low: only jurisdiction detected, no other signals

## SSE Events

### journey_state_update (Step 2 + Step 3)

Emitted on every chat turn when a journey type is classified. Includes playbook progression:

First turn (classification + initial step):
```
event: journey_state_update
data: {"journey_type": "work_in_germany", "citizenship_group": "eu_citizen", "jurisdiction": "DE", "current_step": "check_permit_type", "completed_steps": [], "confidence": "high"}
```

Subsequent turn (after job offer collected):
```
event: journey_state_update
data: {"journey_type": "work_in_germany", "citizenship_group": "eu_citizen", "jurisdiction": "DE", "current_step": "check_citizenship", "completed_steps": ["check_permit_type"], "confidence": "high"}
```

Emitted before RAG results on every turn where `journey_type` is set.

## Repetition Prevention (Step 1)

The JourneyState includes fields to prevent repeating the same question, action, source, or fact confirmation:

- `asked_questions`: questions the assistant has already asked
- `offered_actions`: actions already offered to the user
- `confirmed_facts`: facts the user has already confirmed
- `shown_sources`: references already presented

The four helpers (isQuestionRepeated, isActionOffered, isSourceShown, isFactConfirmed) check these lists before emitting new questions or actions.

## Multi-step Progression (Step 3)

The `JourneyPlaybookService` (`backend/app/services/journey_playbook.py`) advances through playbook steps on every chat turn:

1. Each journey type has a playbook (ordered list of steps):
   - `work_in_germany`: `[check_permit_type, check_citizenship, check_qualifications, check_language]`
   - `relocate_to_germany`: `[check_purpose, check_citizenship, check_financial, check_documents]`
   - `study_in_germany`: `[check_citizenship, check_admission, check_financial, check_health_insurance]`
2. Each step has a completion checker function that inspects `facts` (e.g., `has_job_offer` → `check_permit_type` complete)
3. `compute_progress()` returns `JourneyProgress(current_step, completed_steps)` — `current_step` is `None` when all steps done
4. `current_step` retrogresses if a fact is removed (facts change)
5. Frontend receives step updates via SSE `journey_state_update` on every turn and merges them via `useJourneyState.updateFromResponse()`

### Playbook Steps

| Step | Completion check | Triggers |
|------|-----------------|----------|
| `check_permit_type` | `has_job_offer` truthy | Job/Blue Card mention |
| `check_citizenship` | `citizenship_group` or `citizenship` truthy | EU/non-EU classification |
| `check_qualifications` | `qualification_recognized` or `profession_regulated` truthy | Regulated profession |
| `check_language` | `language_level` truthy | B1/C1 language cert |
| `check_purpose` | `relocation_purpose` or `permit_type` truthy | Family/work/study reunification |
| `check_financial` | `financial_means` truthy | Blocked account/salary |
| `check_documents` | `documents_ready` truthy | Passport/contract/forms |
| `check_admission` | `admission_letter` or `university_accepted` truthy | Uni acceptance |
| `check_health_insurance` | `health_insurance` truthy | EU card or German insurance |

### Tests

19 unit tests in `backend/tests/unit/test_journey_playbook.py` covering:
- All three playbooks: initial step, advancement, completion
- Edge cases: `None` journey type, unknown type, empty facts
- Fact removal regression (step reverts to incomplete)
- Frozen model contract

Chat integration test (`test_chat_emits_journey_state_on_subsequent_turns`) verifies SSE payload includes `current_step` and `completed_steps` on non-first-turn requests.

## Citizen-specific Playbooks (Step 5)

Playbooks are now keyed by `(journey_type, citizenship_group)`. EU citizens get shorter playbooks (freedom of movement), non-EU citizens get the full process.

### EU citizen playbooks (shorter)

| Journey type | Steps |
|---|---|
| work_in_germany | check_permit_type, check_citizenship |
| relocate_to_germany | check_purpose, check_citizenship |
| study_in_germany | check_citizenship, check_admission, check_health_insurance |

### Non-EU playbooks (full process)

| Journey type | Steps |
|---|---|
| work_in_germany | check_permit_type, check_citizenship, check_qualifications, check_language |
| relocate_to_germany | check_purpose, check_citizenship, check_financial, check_documents |
| study_in_germany | check_citizenship, check_admission, check_financial, check_health_insurance |

### Unknown citizenship

Falls back to the EU-length playbook (2-3 steps) — asks for citizenship first, then proceeds.

### Tests

26 unit tests in `backend/tests/unit/test_journey_playbook.py` covering all three citizenship groups per journey type.

## Testing

- 15+ unit tests in backend/tests/unit/test_journey_classifier.py covering all JourneyType x CitizenshipGroup combinations
- Integration test verifying SSE stream contains journey_state_update on first turn
- Edge cases: empty message, jurisdiction-only, generic questions
</details>
</write>
