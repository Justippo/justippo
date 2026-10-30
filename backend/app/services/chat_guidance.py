# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic, verified next-step guidance for empty chat retrievals.

Linus DEC-0059 adaptation: enforce_citation_grounding() provides claim-level
citation validation against known D1 documents. Soft refusal via guidance
fallback (not hard error) — product can escalate to hard refusal later.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict

# ── Grounding gate (Linus DEC-0059 adaptation) ────────────────────────────────


class GroundedClaim(TypedDict):
    claim: str
    grounded: bool
    matched_doc_ids: list[str]
    matched_entities: list[str]
    reason: str


class GroundingVerdict(TypedDict):
    verdict: Literal["pass", "partial", "fail"]
    claims: list[GroundedClaim]
    ungrounded_count: int
    total_claims: int


@dataclass
class GroundingConfig:
    enabled: bool = False
    min_confidence: float = 0.5
    soft_refusal: bool = True


_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


# ── VERIFIED LEGAL THRESHOLDS (single source of truth) ──────────────────────
# These figures are served as authoritative fact because guidance answers bypass
# RAG grounding. They are verified against official/authoritative sources for the
# 2026 calendar year and MUST be reviewed every January (they drift annually).
# Update procedure: bump VALID_FROM, replace the values, update SOURCES URLs,
# then run tests/unit/test_chat_guidance.py::test_legal_thresholds_current.
@dataclass(frozen=True)
class _LegalThresholds:
    valid_from: str
    de_blue_card_general: int  # €/year, EU Blue Card Germany (general)
    de_blue_card_shortage: int  # €/year, EU Blue Card Germany (shortage occupations)
    de_opportunity_card_blocked_pm: int  # €/month, Chancenkarte blocked account
    de_student_blocked_pm: int  # €/month, student visa blocked account
    de_gkv_threshold: int  # €/year, public health insurance compulsory threshold
    es_blue_card_general: float  # €/year, EU Blue Card Spain (general)
    es_blue_card_reduced: float  # €/year, EU Blue Card Spain (shortage/recent grads)
    es_digital_nomad_main_pm: int  # €/month, digital nomad (main applicant)
    es_digital_nomad_dep1_pm: int  # €/month, digital nomad (+1st dependent)
    es_digital_nomad_dep_extra_pm: int  # €/month, digital nomad (each additional dependent)
    es_non_lucrative_main: int  # €/year, non-lucrative visa (main applicant)
    es_non_lucrative_dep: int  # €/year, non-lucrative visa (per dependent)
    sources: dict[str, str]


LEGAL_THRESHOLDS_2026 = _LegalThresholds(
    valid_from="2026-01-01",
    de_blue_card_general=50_700,
    de_blue_card_shortage=45_934,
    de_opportunity_card_blocked_pm=1_091,
    de_student_blocked_pm=992,
    de_gkv_threshold=77_400,
    es_blue_card_general=41_356.36,
    es_blue_card_reduced=33_085.09,
    es_digital_nomad_main_pm=2_849,
    es_digital_nomad_dep1_pm=1_069,
    es_digital_nomad_dep_extra_pm=357,
    es_non_lucrative_main=28_800,
    es_non_lucrative_dep=7_200,
    sources={
        "de_blue_card": "https://www.make-it-in-germany.com/en/visa/living-permanently/blue-card",
        "de_blocked_account": "https://www.bankdaten.de/en/guide/blocked-account-germany.html",
        "de_gkv": "https://www.bundesgesundheitsministerium.de/",
        "es_blue_card": "https://www.inclusion.gob.es/ (Orden PJC/44/2026)",
        "es_digital_nomad": "https://www.inclusion.gob.es/ (Real Decreto 126/2026, SMI)",
        "es_non_lucrative": "https://www.inclusion.gob.es/ (IPREM 2026 = €600/month)",
    },
)


# Human-readable formatting helpers (DRY: used by every guidance string below).
def _eur(value: float) -> str:
    return (
        f"€{value:,.0f}".replace(",", " ")
        if value == int(value)
        else f"€{value:,.2f}".replace(",", " ")
    )


def extract_known_doc_ids(results: list[dict[str, Any]]) -> set[str]:
    return {
        str(r.get("document_id") or r.get("id", ""))
        for r in results
        if r.get("document_id") or r.get("id")
    }


def build_grounding_verdict(
    full_answer: str,
    results: list[dict[str, Any]],
    config: GroundingConfig,
    entity_mentions: set[str] | None = None,
) -> GroundingVerdict:
    known_ids = extract_known_doc_ids(results)
    return enforce_citation_grounding(
        full_answer,
        known_doc_ids=known_ids,
        entity_mentions=entity_mentions,
        config=config,
    )


def enforce_citation_grounding(
    claim_text: str,
    known_doc_ids: set[str] | None = None,
    entity_mentions: set[str] | None = None,
    config: GroundingConfig | None = None,
) -> GroundingVerdict:
    """Split output into claims and validate each against known sources.

    Linus DEC-0059 adaptation: soft refusal only (returns guidance fallback
    signal, never a hard error). Cross-run confidence calibration deferred.

    Args:
        claim_text: The LLM-generated answer text to validate.
        known_doc_ids: Document IDs returned by the RAG query.
        entity_mentions: Entity names detected in the user query.
        config: Grounding configuration (feature-flagged by default).

    Returns:
        GroundingVerdict with per-claim grounding status and overall verdict.
    """
    cfg = config or GroundingConfig()
    if not cfg.enabled or not claim_text:
        return {
            "verdict": "pass",
            "claims": [],
            "ungrounded_count": 0,
            "total_claims": 0,
        }

    known_ids = known_doc_ids or set()
    entities = entity_mentions or set()
    sentences = [s.strip() for s in _CLAIM_SPLIT_RE.split(claim_text) if s.strip()]
    claims: list[GroundedClaim] = []
    ungrounded = 0

    for sentence in sentences:
        lowered = sentence.lower()
        matched_docs = [d for d in known_ids if d.lower() in lowered]
        matched_ents = [e for e in entities if e.lower() in lowered]
        if matched_docs or matched_ents:
            claims.append(
                {
                    "claim": sentence,
                    "grounded": True,
                    "matched_doc_ids": matched_docs,
                    "matched_entities": matched_ents,
                    "reason": "supported_by_sources",
                }
            )
        else:
            ungrounded += 1
            claims.append(
                {
                    "claim": sentence,
                    "grounded": False,
                    "matched_doc_ids": [],
                    "matched_entities": [],
                    "reason": "no_matching_source",
                }
            )

    if ungrounded == 0:
        verdict: Literal["pass", "partial", "fail"] = "pass"
    elif ungrounded < len(sentences):
        verdict = "partial"
    else:
        verdict = "fail"

    return {
        "verdict": verdict,
        "claims": claims,
        "ungrounded_count": ungrounded,
        "total_claims": len(sentences),
    }


# ── Existing guidance types (unchanged) ───────────────────────────────────────


class GuidanceOption(TypedDict):
    label: str
    action: Literal["submit", "compose"]
    query: NotRequired[str]
    prompt: NotRequired[str]


class GuidanceReference(TypedDict):
    title: str
    url: str


class ChatGuidance(TypedDict):
    reason: str
    message: str
    question: str
    options: list[GuidanceOption]
    references: list[GuidanceReference]


_SPAN_MARKERS = ("spain", "spanish", "españa", "espana")
_TAX_MARKERS = ("tax", "taxation", "taxes", "fiscal", "income")
_IMMIGRATION_MARKERS = ("immigration", "migrant", "migration", "policy", "policies")
_STUDENT_VISA_MARKERS = (
    "student visa",
    "student visas",
    "study visa",
    "study visas",
    "study in",
    "university",
    "erasmus",
)
_GERMANY_MARKERS = ("germany", "german", "deutschland")
_WORK_PERMIT_MARKERS = (
    "work permit",
    "work visa",
    "employment permit",
    "work in",
    "residence permit",
    "residence card",
    "residence title",
    "job offer",
)


def _contains_any(query: str, markers: tuple[str, ...]) -> bool:
    return any(marker in query for marker in markers)


def _is_followup_answer(query: str) -> bool:
    """Detect if the query is a personal status declaration (answer to clarification).

    Matches answers like:
    - "I have a German job offer."
    - "My nationality is Brazilian."

    Does NOT match goal/questions like:
    - "I want to work in Germany" (goal)
    - "I need a residence permit" (need)
    - "How do I get a work permit?" (question)

    Structural guard: any query that resolves via the dispatch table (i.e. is a
    known guidance option or its paraphrase) is by definition NOT a follow-up
    answer, so it is exempted here. This prevents option strings that read as
    personal-status declarations (e.g. "I am a non-EU citizen and already have a
    job offer in Germany.") from being wrongly classified as answers.
    """
    normalized = query.strip().casefold()
    for _triggers, _handler_name in _GUIDANCE_INTENTS:
        if any(t in normalized for t in _triggers):
            return False

    normalized = query.casefold()

    # Questions (what, how, which, what are, what is, etc.) are NOT followup answers
    if normalized.startswith(
        ("what ", "how ", "which ", "why ", "when ", "where ", "who ", "can ", "do ", "does ")
    ):
        return False

    # Guidance option queries contain goals/intents - these are NEW questions, not answers
    goal_phrases = (
        "want to",
        "need to",
        "looking for",
        "wish to",
        "plan to",
        "intend to",
        "would like to",
        "hope to",
    )
    if any(gp in normalized for gp in goal_phrases):
        return False

    # Personal status declarations - answers to "what is your status?" type questions
    status_starts = (
        "i am a ",
        "i am an ",
        "i am ",
        "i have a ",
        "i have ",
        "my ",
        "i hold ",
        "i possess ",
        "i'm a ",
        "i'm an ",
    )

    # Must start with status declaration AND contain status-related keywords
    for start in status_starts:
        if normalized.startswith(start):
            # Check for status keywords
            status_keywords = (
                "citizen",
                "national",
                "resident",
                "passport",
                "nationality",
                "job offer",
                "job-offer",
                "employment",
                "work permit",
                "visa",
                "eu",
                "eea",
                "swiss",
                "non-eu",
                "third country",
            )
            if any(kw in normalized for kw in status_keywords):
                return True
            # Also match if it's a short personal statement (likely an answer)
            words = normalized.split()
            if len(words) <= 12:  # short answers like "I am an EU citizen"
                return True

    return False


# ── GUIDANCE DISPATCH TABLE ─────────────────────────────────────────────────
# Single source of truth mapping normalized trigger substrings -> handler.
# Auto-seeded from every emitted option `query` (so no clickable button can be
# dead) plus curated free-text paraphrases. Adding a topic = one tuple here.
# Substring match is used (not exact), so partial phrasings resolve too.
# ── GUIDANCE DISPATCH TABLE ─────────────────────────────────────────────────
# Single source of truth mapping normalized trigger substrings -> handler.
# Auto-seeded from EVERY option `query` emitted by all _*_guidance functions
# (first- AND second-level buttons), so no clickable button can be dead,
# plus curated free-text paraphrases. Adding a topic = one tuple here.
# Substring match is used (not exact), so partial phrasings resolve too.
_GUIDANCE_INTENTS = (
    (("anmeldung",), "_germany_address_registration_guidance"),
    (("ausbildung germany",), "_germany_vocational_training_guidance"),
    (("blue card germany",), "_germany_blue_card_guidance"),
    (("blue card spain",), "_spain_blue_card_guidance"),
    (("bring my family to germany",), "_germany_family_reunification_eu_guidance"),
    (("burgeramt",), "_germany_address_registration_guidance"),
    (
        ("can i apply for nie at a spanish consulate before moving to spain?",),
        "_spain_nie_consulate_guidance",
    ),
    (
        ("can i come to germany for vocational training as a non-eu citizen?",),
        "_germany_vocational_training_guidance",
    ),
    (
        ("can i work on a spanish student visa and what are the limits?",),
        "_spain_student_visa_work_guidance",
    ),
    (("can my family join me on spain's digital nomad visa?",), "_spain_dn_family_guidance"),
    (("chancenkarte",), "_germany_opportunity_card_guidance"),
    (("digital nomad spain",), "_spain_digital_nomad_guidance"),
    (
        ("does my non-eu spouse need a visa to enter germany for family reunification?",),
        "_germany_family_spouse_visa_guidance",
    ),
    (("entrepreneur spain",), "_spain_entrepreneur_visa_guidance"),
    (("family reunification germany",), "_germany_family_reunification_eu_guidance"),
    (("freelance germany",), "_germany_self_employment_guidance"),
    (("health insurance eu citizen germany",), "_germany_eu_health_insurance_guidance"),
    (("health insurance eu citizen spain",), "_spain_eu_health_insurance_guidance"),
    (("highly qualified spain",), "_spain_highly_qualified_guidance"),
    (
        ("how do i access spanish public healthcare (sns) as a resident?",),
        "_spain_sns_access_guidance",
    ),
    (("how do i apply for a nie number in spain?",), "_spain_nie_apply_guidance"),
    (
        ("how do i book a bürgeramt appointment in germany?",),
        "_germany_address_burgeramt_guidance",
    ),
    (
        ("how do i calculate my points for germany's opportunity card?",),
        "_germany_opportunity_points_guidance",
    ),
    (
        ("how do i convert a job-seeker visa to a work permit in germany?",),
        "_germany_jobseeker_convert_guidance",
    ),
    (
        ("how do i extend the opportunity card after finding a job in germany?",),
        "_germany_opportunity_extend_guidance",
    ),
    (
        ("how do i find vocational training positions in germany?",),
        "_germany_vocational_find_guidance",
    ),
    (
        ("how do i get a german tax id (steueridentifikationsnummer) after registering?",),
        "_germany_tax_id_guidance",
    ),
    (
        ("how do i get my business plan endorsed for spain's entrepreneur visa?",),
        "_spain_entrepreneur_endorsement_guidance",
    ),
    (
        ("how do i get my foreign qualification recognized in germany?",),
        "_germany_skilled_recognition_guidance",
    ),
    (
        ("how do i get my qualifications recognized for working in germany?",),
        "_germany_qualification_recognition_guidance",
    ),
    (
        ("how do i get my university degree recognized for germany's blue card?",),
        "_germany_blue_card_degree_guidance",
    ),
    (
        ("how do i get permanent residence as a self-employed person in germany?",),
        "_germany_self_pr_guidance",
    ),
    (
        ("how do i get permanent residence in germany after eu family reunification?",),
        "_germany_family_pr_guidance",
    ),
    (
        ("how do i get permanent residence in spain after non-lucrative visa?",),
        "_spain_nl_pr_guidance",
    ),
    (("how do i prove income for spain's digital nomad visa?",), "_spain_dn_income_guidance"),
    (
        ("how do i prove my degree is equivalent for spain's blue card?",),
        "_spain_blue_degree_guidance",
    ),
    (("how do i register as an eu citizen in spain?",), "_spain_eu_register_guidance"),
    (
        ("how do i register my address in germany as an eu citizen?",),
        "_germany_eu_address_guidance",
    ),
    (
        ("how do i renew my spanish student visa after the first year?",),
        "_spain_student_visa_renewal_guidance",
    ),
    (
        ("how do i renew the highly qualified professional permit in spain?",),
        "_spain_hq_renewal_guidance",
    ),
    (
        ("how do i set up a blocked account (sperrkonto) for a german job-seeker visa?",),
        "_germany_jobseeker_sperrkonto_guidance",
    ),
    (
        ("how does an employer hire using the shortage occupation exemption in spain?",),
        "_spain_shortage_employer_guidance",
    ),
    (
        ("how does family reunification work for eu citizens in germany?",),
        "_germany_eu_family_guidance",
    ),
    (
        ("how does family reunification work for spain blue card holders?",),
        "_spain_blue_family_guidance",
    ),
    (
        ("how does health insurance work for eu citizens working in germany?",),
        "_germany_eu_health_guidance",
    ),
    (
        ("how does the 21-month permanent residence work for blue card holders?",),
        "_germany_blue_card_pr_guidance",
    ),
    (
        ("how does the a1 certificate work for posted workers in germany?",),
        "_germany_a1_certificate_guidance",
    ),
    (
        ("how does the beckham law work for digital nomads in spain?",),
        "_spain_dn_beckham_guidance",
    ),
    (("how is individual tax residency determined in spain?",), "_spain_tax_residency_guidance"),
    (
        ("how long until permanent residence on a skilled worker permit in germany?",),
        "_germany_skilled_pr_guidance",
    ),
    (
        ("how often is spain's shortage occupation list updated and who decides?",),
        "_spain_shortage_update_guidance",
    ),
    (
        ("how strictly must the job match my degree for spain's highly qualified permit?",),
        "_spain_hq_match_guidance",
    ),
    (("job seeker visa germany",), "_germany_jobseeker_visa_guidance"),
    (("nie spain",), "_spain_nie_application_guidance"),
    (("non lucrative spain",), "_spain_non_lucrative_visa_guidance"),
    (("non-lucrative spain",), "_spain_non_lucrative_visa_guidance"),
    (("opportunity card germany",), "_germany_opportunity_card_guidance"),
    (("qualification recognition germany",), "_germany_qualification_recognition_guidance"),
    (("recognize my degree germany",), "_germany_qualification_recognition_guidance"),
    (("register as eu citizen spain",), "_spain_eu_registration_guidance"),
    (("register in spain eu",), "_spain_eu_registration_guidance"),
    (("register my address in germany",), "_germany_address_registration_guidance"),
    (("registration requirements eu citizens in spain",), "_spain_eu_registration_guidance"),
    (("registration requirements for eu citizens in spain",), "_spain_eu_registration_guidance"),
    (("self employment germany",), "_germany_self_employment_guidance"),
    (("shortage occupation spain",), "_spain_shortage_occupations_guidance"),
    (("skilled worker germany",), "_germany_skilled_worker_guidance"),
    (("social security eu citizen germany",), "_germany_eu_health_insurance_guidance"),
    (("spanish tax",), "_spain_tax_guidance"),
    (("student visa spain",), "_spain_student_visa_guidance"),
    (("study in spain",), "_spain_student_visa_guidance"),
    (("tax residency spain",), "_spain_tax_guidance"),
    (("tax rules in spain",), "_spain_tax_guidance"),
    (("vocational training germany",), "_germany_vocational_training_guidance"),
    (
        ("what are compensatory measures if my qualification is partially recognized?",),
        "_germany_compensatory_measures_guidance",
    ),
    (
        ("what are the eu blue card requirements for germany?",),
        "_germany_blue_card_guidance",
    ),
    (("what are the eu blue card requirements for spain?",), "_spain_blue_card_guidance"),
    (
        ("what are the exact financial requirements for a spanish student visa?",),
        "_spain_student_visa_financial_guidance",
    ),
    (
        ("what are the exact requirements for private health insurance in spain?",),
        "_spain_private_health_guidance",
    ),
    (
        ("what are the pros and cons of public vs private health insurance in germany?",),
        "_germany_health_public_private_guidance",
    ),
    (
        ("what are the requirements for a self-employment residence permit in germany?",),
        "_germany_self_employment_guidance",
    ),
    (
        ("what are the requirements for germany's opportunity card?",),
        "_germany_opportunity_card_guidance",
    ),
    (
        ("what are the requirements for spain's digital nomad visa?",),
        "_spain_digital_nomad_guidance",
    ),
    (
        ("what are the requirements for spain's entrepreneur visa?",),
        "_spain_entrepreneur_visa_guidance",
    ),
    (
        ("what are the requirements for spain's non-lucrative residence visa?",),
        "_spain_non_lucrative_visa_guidance",
    ),
    (
        ("what are the requirements for the german job-seeker visa?",),
        "_germany_jobseeker_visa_guidance",
    ),
    (
        ("what are the requirements for the german skilled worker residence permit?",),
        "_germany_skilled_worker_guidance",
    ),
    (
        ("what are the requirements for the highly qualified professional permit in spain?",),
        "_spain_highly_qualified_guidance",
    ),
    (
        ("what are the steps to get my foreign degree recognized in germany?",),
        "_germany_recognition_steps_guidance",
    ),
    (("what are the student visa requirements for spain?",), "_spain_student_visa_guidance"),
    (
        ("what counts as passive income for spain's non-lucrative visa?",),
        "_spain_nl_passive_income_guidance",
    ),
    (
        ("what documents are needed for eu family reunification in germany?",),
        "_germany_family_docs_guidance",
    ),
    (
        ("what documents do i need for nie application in spain?",),
        "_spain_nie_docs_guidance",
    ),
    (
        ("what german level do i need for vocational training in germany?",),
        "_germany_vocational_german_guidance",
    ),
    (("what health insurance do eu citizens need in spain?",), "_spain_eu_health_guidance"),
    (
        ("what health insurance do eu students need in germany?",),
        "_germany_eu_student_health_guidance",
    ),
    (
        ("what health insurance requirements for spain non-lucrative visa?",),
        "_spain_nl_health_guidance",
    ),
    (
        ("what investment is needed for spain's entrepreneur visa?",),
        "_spain_entrepreneur_investment_guidance",
    ),
    (
        (
            "what is the difference between eu blue card and highly qualified professional permit in spain?",
        ),
        "_spain_hq_vs_blue_guidance",
    ),
    (
        ("what is the difference between freiberufler and gewerbe in germany?",),
        "_germany_freiberufler_gewerbe_guidance",
    ),
    (
        ("what is the difference between job-seeker visa and opportunity card in germany?",),
        "_germany_jobseeker_vs_opportunity_guidance",
    ),
    (("what is the difference between nie and tie in spain?",), "_spain_nie_vs_tie_guidance"),
    (
        ("what is the fast-track residence permit for entrepreneurs in spain?",),
        "_spain_entrepreneur_fasttrack_guidance",
    ),
    (
        ("what is the wohnungsgeberbestätigung and how do i get it?",),
        "_germany_wohnungsgeber_guidance",
    ),
    (
        ("what must a business plan include for german self-employment permit?",),
        "_germany_self_business_plan_guidance",
    ),
    (
        ("what part-time work is allowed on germany's opportunity card?",),
        "_germany_opportunity_work_guidance",
    ),
    (
        ("what residence permit can i get after completing ausbildung in germany?",),
        "_germany_vocational_after_guidance",
    ),
    (
        ("where can i find the current shortage occupation list for my spanish province?",),
        "_spain_shortage_find_guidance",
    ),
    (
        ("which eu rules affect a remote employee working from spain?",),
        "_spain_tax_remote_employee_guidance",
    ),
    (
        ("which eu rules affect a self-employed person working in spain?",),
        "_spain_tax_selfemployed_guidance",
    ),
    (
        ("which occupations are on germany's shortage occupation list for blue card?",),
        "_germany_blue_card_shortage_guidance",
    ),
    (
        ("which occupations are on spain's shortage occupation list for blue card?",),
        "_spain_blue_shortage_guidance",
    ),
    (
        ("which occupations are on spain's shortage occupation list?",),
        "_spain_shortage_occupations_guidance",
    ),
    (
        ("which occupations waive the labour market test in germany?",),
        "_germany_skilled_labour_test_guidance",
    ),
    (
        ("which professions are regulated in germany and require mandatory recognition?",),
        "_germany_regulated_professions_guidance",
    ),
    (
        ("why is ehic not enough for spanish residence registration?",),
        "_spain_ehic_guidance",
    ),
    # Non-EU status-declaration options emitted by the inline marker-routed blocks.
    # These read as personal answers to _is_followup_answer, so they MUST be in the
    # table BEFORE that check (and the table membership also exempts them in
    # _is_followup_answer), making them resolvable rather than dead.
    (
        ("i am a non-eu citizen and already have a job offer in germany.",),
        "_germany_non_eu_job_offer_guidance",
    ),
    (
        ("i am a non-eu citizen and do not yet have a job offer in germany.",),
        "_germany_non_eu_no_job_guidance",
    ),
    (
        ("i am a non-eu citizen and already have a job offer in spain.",),
        "_spain_non_eu_job_offer_guidance",
    ),
    (
        ("i am a non-eu citizen and do not yet have a job offer in spain.",),
        "_spain_non_eu_no_job_guidance",
    ),
    # EU/EEA/Swiss citizens have freedom of movement — no work/residence permit needed.
    # These must route to the EU-citizen handler, NOT the generic work-permit block.
    (
        ("i am an eu, eea, or swiss citizen and want to work in germany.",),
        "_germany_eu_citizen_guidance",
    ),
    (
        ("i am an eu, eea, or swiss citizen and want to work in spain.",),
        "_spain_eu_registration_guidance",
    ),
)


def _spain_tax_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "I could not find a verified EUR-Lex source that directly answers this question. "
            "Spanish tax obligations are primarily governed by national law and depend on "
            "your residency and source of income."
        ),
        "question": "Which part would you like to explore next?",
        "options": [
            {
                "label": "Tax residency",
                "action": "submit",
                "query": "How is individual tax residency determined in Spain?",
            },
            {
                "label": "Remote employment",
                "action": "submit",
                "query": "Which EU rules affect a remote employee working from Spain?",
            },
            {
                "label": "Self-employment",
                "action": "submit",
                "query": "Which EU rules affect a self-employed person working in Spain?",
            },
        ],
        "references": [
            {
                "title": "Spanish Tax Agency — tax residency",
                "url": (
                    "https://sede.agenciatributaria.gob.es/Sede/en_gb/no-residentes/"
                    "residencia-personas-fisicas-juridicas.html"
                ),
            }
        ],
    }


def build_empty_result_guidance(query: str) -> ChatGuidance:
    """Return safe next steps without asking a model to invent facts or URLs."""
    query = query.strip()[:1_800]
    normalized = query.casefold()

    # ── CORPUS-INTENT GUARD ──────────────────────────────────────────────────
    # If the user is asking about THEIR OWN uploaded documents (summarize / what
    # does my file say / the PDF I uploaded), curated general-law guidance must
    # yield to RAG, which actually searches the corpus. Without this, a query like
    # "Summarize the document I uploaded about German residence permits" would hit
    # the generic DE guidance and never reach the user's document. Curated
    # guidance is a supplement for general law, never a replacement for the corpus.
    _CORPUS_INTENT_MARKERS = (
        "upload",
        "my document",
        "my file",
        "my pdf",
        "the pdf",
        "the document i",
        "summar",
        "what does this",
        "what does the",
        "extract from",
        "in the file",
        "in my file",
    )
    if any(marker in normalized for marker in _CORPUS_INTENT_MARKERS):
        return {
            "reason": "no_verified_source",
            "message": (
                "I can answer this from general EU law knowledge, but I could not find "
                "specific documents in your uploaded files or the public corpus that "
                "directly answer it. The answer may depend on national law or details "
                "that are not yet specific enough."
            ),
            "question": "What would you like to clarify?",
            "options": [],
            "references": [],
        }

    # ── DISPATCH TABLE (option clicks + free-text paraphrases) ──
    # Seeded from the emitted option `query` values themselves, so every clickable
    # button resolves to its curated handler. Non-EU option strings that read as
    # personal-status answers are caught here BEFORE _is_followup_answer, which is
    # what makes the two-tier guidance loop-safe.
    # Matching is SPECIFIC-FIRST: when several triggers match, the longest trigger
    # wins. This prevents a broad substring (e.g. "germany" + "work") from swallowing
    # a specific question (e.g. "what are the eu blue card requirements for germany?").
    import sys as _sys

    _MOD = _sys.modules[__name__]
    _HANDLERS: dict[str, Callable[[], ChatGuidance]] = {
        name: getattr(_MOD, name)
        for name in dir(_MOD)
        if name.endswith("_guidance")
        and name != "build_empty_result_guidance"
        and callable(getattr(_MOD, name))
    }
    _best: tuple[int, str] | None = None  # (trigger_length, handler_name)
    for triggers, handler_name in _GUIDANCE_INTENTS:
        for t in triggers:
            if (
                t in normalized
                and handler_name in _HANDLERS
                and (_best is None or len(t) > _best[0])
            ):
                _best = (len(t), handler_name)
    if _best is not None:
        return _HANDLERS[_best[1]]()

    # Skip guidance for genuine follow-up answers (e.g., "I am an EU citizen...",
    # "I have a job offer..."). These are specific queries that should go to
    # RAG/LLM, not trigger generic guidance again.
    if _is_followup_answer(query):
        return {
            "reason": "followup_answer",
            "message": "",
            "question": "",
            "options": [],
            "references": [],
        }

    if _contains_any(normalized, _SPAN_MARKERS) and _contains_any(normalized, _TAX_MARKERS):
        return _spain_tax_guidance()

    if _contains_any(normalized, _SPAN_MARKERS) and _contains_any(normalized, _IMMIGRATION_MARKERS):
        return {
            "reason": "national_law",
            "message": (
                "Spanish immigration and residency policy is primarily governed by national law "
                "(Ley de Extranjería), not EU regulations. The specific requirements depend on "
                "your citizenship, purpose of stay, and length of residence."
            ),
            "question": "Which aspect of Spanish immigration would you like to explore?",
            "options": [
                {
                    "label": "Work permits",
                    "action": "submit",
                    "query": "What are the work permit requirements for Spain?",
                },
                {
                    "label": "Student visas",
                    "action": "submit",
                    "query": "What are the student visa requirements for Spain?",
                },
                {
                    "label": "Family reunification",
                    "action": "submit",
                    "query": "How does family reunification work in Spain?",
                },
                {
                    "label": "EU citizen registration",
                    "action": "submit",
                    "query": "What are the registration requirements for EU citizens in Spain?",
                },
            ],
            "references": [],
        }

    if _contains_any(normalized, _SPAN_MARKERS) and _contains_any(
        normalized, _STUDENT_VISA_MARKERS
    ):
        return {
            "reason": "national_law",
            "message": (
                "Spanish student visa requirements are governed by national law. "
                "Non-EU students typically need a student visa (Visado de Estudiante) "
                "for stays over 90 days. Requirements include university admission, "
                "proof of financial means, and health insurance. "
                "EU/EEA/Swiss citizens only need to register after 3 months."
            ),
            "question": "Which aspect of studying in Spain would you like to explore?",
            "options": [
                {
                    "label": "Student visa requirements",
                    "action": "submit",
                    "query": "What are the student visa requirements for Spain?",
                },
                {
                    "label": "Erasmus+ program",
                    "action": "submit",
                    "query": "How does the Erasmus+ program work for studying in Spain?",
                },
                {
                    "label": "University admission",
                    "action": "submit",
                    "query": "What are the university admission requirements for Spain?",
                },
            ],
            "references": [
                {
                    "title": "Spanish Ministry of Universities",
                    "url": "https://www.universidades.gob.es/",
                }
            ],
        }

    if _contains_any(normalized, _SPAN_MARKERS) and _contains_any(normalized, _WORK_PERMIT_MARKERS):
        return {
            "reason": "national_law",
            "message": (
                "Spanish work permit requirements are governed by national law and depend on "
                "your citizenship, the type of work, and whether you have a job offer. "
                "EU/EEA/Swiss citizens have freedom of movement; non-EU citizens need a work permit."
            ),
            "question": "Which situation applies to you?",
            "options": [
                {
                    "label": "EU/EEA/Swiss citizen",
                    "action": "submit",
                    "query": "I am an EU, EEA, or Swiss citizen and want to work in Spain.",
                },
                {
                    "label": "Non-EU with job offer",
                    "action": "submit",
                    "query": "I am a non-EU citizen and already have a job offer in Spain.",
                },
                {
                    "label": "Non-EU without job offer",
                    "action": "submit",
                    "query": "I am a non-EU citizen and do not yet have a job offer in Spain.",
                },
            ],
            "references": [],
        }

    if _contains_any(normalized, _GERMANY_MARKERS) and _contains_any(
        normalized, _WORK_PERMIT_MARKERS
    ):
        return {
            "reason": "national_law",
            "message": (
                "I can help you understand the process based on EU freedom of movement rules "
                "and German implementation law. The applicable route depends on your "
                "citizenship and employment situation."
            ),
            "question": "Tell me which situation applies to you:",
            "options": [
                {
                    "label": "Add my status",
                    "action": "compose",
                    "prompt": (
                        "Describe your citizenship, where you currently live, whether you have "
                        "a German job offer, and the type of work or stay you plan."
                    ),
                },
                {
                    "label": "EU/EEA/Swiss citizen",
                    "action": "submit",
                    "query": "I am an EU, EEA, or Swiss citizen and want to work in Germany.",
                },
                {
                    "label": "Non-EU with job offer",
                    "action": "submit",
                    "query": "I am a non-EU citizen and already have a job offer in Germany.",
                },
                {
                    "label": "Non-EU without job offer",
                    "action": "submit",
                    "query": "I am a non-EU citizen and do not yet have a job offer in Germany.",
                },
            ],
            "references": [],
        }

    return {
        "reason": "no_verified_source",
        "message": (
            "I can answer this from general EU law knowledge, but I could not find specific "
            "documents in your uploaded files or the public corpus that directly answer it. "
            "The answer may depend on national law or details that are not yet specific enough."
        ),
        "question": "What would you like to clarify?",
        "options": [
            {
                "label": "Add my status",
                "action": "compose",
                "prompt": (
                    "Add the country, your citizenship or residence status, and the outcome "
                    "you want."
                ),
            },
            {
                "label": "Focus on EU law",
                "action": "submit",
                "query": f"Which EU rules apply to: {query}",
            },
            {
                "label": "Identify the authority",
                "action": "submit",
                "query": f"Which authority handles: {query}",
            },
        ],
        "references": [],
    }


# ── SPECIFIC GUIDANCE FOR OPTION SELECTIONS (prevents loops) ─────────────────────


def _germany_eu_citizen_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "As an EU/EEA/Swiss citizen, you have freedom of movement to work in Germany "
            "without a work permit. You only need to register your address (Anmeldung) at "
            "the local registration office (Bürgeramt) within 14 days of moving in. "
            "You may also need a registration certificate (Anmeldebescheinigung) for opening "
            "a bank account, getting a phone contract, or dealing with authorities. "
            "No residence permit or work visa is required. Your family members (even if "
            "non-EU) also get derived freedom of movement rights."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Address registration (Anmeldung)",
                "action": "submit",
                "query": "How do I register my address in Germany as an EU citizen?",
            },
            {
                "label": "Family reunification for EU citizens",
                "action": "submit",
                "query": "How does family reunification work for EU citizens in Germany?",
            },
            {
                "label": "Social security & health insurance",
                "action": "submit",
                "query": "How does health insurance work for EU citizens working in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Ministry of the Interior — Freedom of movement",
                "url": "https://www.bmi.bund.de/EN/topics/migration/freedom-of-movement/freedom-of-movement-node.html",
            },
        ],
    }


def _germany_non_eu_job_offer_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "With a concrete job offer from a German employer, you need a residence title "
            "for employment. The main paths are: (1) EU Blue Card — for university graduates "
            "with a job offer meeting the salary threshold "
            f"({_eur(LEGAL_THRESHOLDS_2026.de_blue_card_general)} in 2026, "
            f"{_eur(LEGAL_THRESHOLDS_2026.de_blue_card_shortage)} for "
            "shortage occupations like IT, engineering, healthcare); (2) Skilled worker "
            "residence permit (§18b AufenthG) — for qualified professionals with recognized "
            "qualifications; (3) ICT Card — for intra-corporate transfers. Your employer "
            "must confirm the job offer. Labour market test is waived for Blue Card and "
            "shortage occupations. Processing typically takes 4–8 weeks."
        ),
        "question": "Which permit type fits your situation?",
        "options": [
            {
                "label": "EU Blue Card",
                "action": "submit",
                "query": "What are the EU Blue Card requirements for Germany?",
            },
            {
                "label": "Skilled worker permit (§18b)",
                "action": "submit",
                "query": "What are the requirements for the German skilled worker residence permit?",
            },
            {
                "label": "Qualification recognition",
                "action": "submit",
                "query": "How do I get my qualifications recognized for working in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Office for Migration and Refugees — Skilled Immigration",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/skilled-immigration/skilled-immigration-node.html",
            },
        ],
    }


def _germany_non_eu_no_job_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Without a job offer, options include: (1) Job-seeker visa (§20 AufenthG) — if you "
            "have a recognized university degree and sufficient funds (~€992/month) "
            "to support yourself for up to 6 months while searching for work; (2) Vocational "
            "training permit — if you have a recognized vocational qualification and a training "
            "contract; (3) Self-employment residence permit (§21 AufenthG) — if your business "
            "benefits the German economy and you have a viable business plan; (4) Opportunity "
            "card (Chancenkarte) — new points-based system for skilled workers without job offer "
            "who meet criteria (qualification, language, age, work experience)."
        ),
        "question": "Which path interests you?",
        "options": [
            {
                "label": "Job-seeker visa (§20)",
                "action": "submit",
                "query": "What are the requirements for the German job-seeker visa?",
            },
            {
                "label": "Opportunity card (Chancenkarte)",
                "action": "submit",
                "query": "What are the requirements for Germany's opportunity card?",
            },
            {
                "label": "Self-employment permit",
                "action": "submit",
                "query": "What are the requirements for a self-employment residence permit in Germany?",
            },
            {
                "label": "Vocational training",
                "action": "submit",
                "query": "Can I come to Germany for vocational training as a non-EU citizen?",
            },
        ],
        "references": [
            {
                "title": "Federal Foreign Office — Job-seeker visa",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198",
            },
        ],
    }


def _germany_address_registration_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "All residents in Germany must register their address (Anmeldung) at the local "
            "registration office (Bürgeramt) within 14 days of moving in. This applies to "
            "EU/EEA/Swiss citizens too. You need: (1) Completed registration form "
            "(Anmeldeformular); (2) Valid passport/ID; (3) Rental contract or confirmation "
            "from landlord (Wohnungsgeberbestätigung); (4) Marriage certificate if applicable. "
            "You receive a registration certificate (Anmeldebescheinigung) immediately. "
            "This is required for: opening a bank account, getting a phone contract, "
            "registering a vehicle, applying for a tax ID, and dealing with authorities. "
            "Failure to register can result in fines up to €1,000. "
            "Some Bürgerämter require appointments booked online weeks in advance."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Finding a Bürgeramt appointment",
                "action": "submit",
                "query": "How do I book a Bürgeramt appointment in Germany?",
            },
            {
                "label": "Wohnungsgeberbestätigung details",
                "action": "submit",
                "query": "What is the Wohnungsgeberbestätigung and how do I get it?",
            },
            {
                "label": "Tax ID after registration",
                "action": "submit",
                "query": "How do I get a German tax ID (Steueridentifikationsnummer) after registering?",
            },
        ],
        "references": [
            {
                "title": "Federal Ministry of the Interior — Anmeldung",
                "url": "https://www.bmi.bund.de/EN/topics/migration/registration/registration-node.html",
            },
        ],
    }


def _germany_family_reunification_eu_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "EU/EEA/Swiss citizens exercising free movement rights in Germany can bring "
            "family members regardless of their nationality. Covered family members: "
            "(1) Spouse/registered partner; (2) Children/grandchildren under 21 or dependent; "
            "(3) Dependent parents/grandparents. Non-EU family members get an "
            "EU family member residence card (Aufenthaltskarte für Familienangehörige von "
            "Unionsbürgern) valid 5 years. Requirements: (1) EU citizen exercises treaty "
            "rights (work, study, self-sufficient); (2) Family relationship proven; "
            "(3) Sufficient health insurance; (4) Sufficient resources (no social assistance). "
            "Apply at local Foreigners' Authority (Ausländerbehörde). No visa required for entry "
            "if family member has valid passport; visa may be needed depending on nationality. "
            "Processing: usually 4–8 weeks. After 5 years, eligible for permanent residence."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Required documents",
                "action": "submit",
                "query": "What documents are needed for EU family reunification in Germany?",
            },
            {
                "label": "Non-EU family member visa",
                "action": "submit",
                "query": "Does my non-EU spouse need a visa to enter Germany for family reunification?",
            },
            {
                "label": "Permanent residence after 5 years",
                "action": "submit",
                "query": "How do I get permanent residence in Germany after EU family reunification?",
            },
        ],
        "references": [
            {
                "title": "Federal Office for Migration — EU family reunification",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/family-reunification/family-reunification-node.html",
            },
        ],
    }


def _germany_eu_health_insurance_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "EU/EEA/Swiss citizens working in Germany are generally subject to German social "
            "security law. Health insurance is mandatory. Options: "
            "(1) Public health insurance (GKV) — if employed with income "
            f"≤{_eur(LEGAL_THRESHOLDS_2026.de_gkv_threshold)}/year (2026); "
            "employer pays half, employee half (~14.6% + supplemental contribution). "
            "Covers dependents at no extra cost. (2) Private health insurance (PKV) — "
            f"if income >{_eur(LEGAL_THRESHOLDS_2026.de_gkv_threshold)}, self-employed, or civil servants; premiums based on "
            "age/health, not income; dependents need separate contracts. "
            "European Health Insurance Card (EHIC) covers only temporary stays, not residence. "
            "If posted from another EU country (<24 months), may stay in home country system "
            "(A1 certificate required). Students from EU/EEA/Switzerland can use EHIC or "
            "home country student insurance if recognized. "
            "Switching between public/private has restrictions (Entlastungsbeitrag, age limits)."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Public vs private comparison",
                "action": "submit",
                "query": "What are the pros and cons of public vs private health insurance in Germany?",
            },
            {
                "label": "A1 certificate for posted workers",
                "action": "submit",
                "query": "How does the A1 certificate work for posted workers in Germany?",
            },
            {
                "label": "Student health insurance",
                "action": "submit",
                "query": "What health insurance do EU students need in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Ministry of Health — Health insurance",
                "url": "https://www.bundesgesundheitsministerium.de/service/begriffe-von-a-z/k/krankenversicherung.html",
            },
        ],
    }


def _germany_blue_card_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The EU Blue Card Germany (§18g AufenthG) is for university graduates with a "
            "qualifying job offer. Requirements (2026): "
            "(1) Recognized university degree (German or foreign, comparable to German degree); "
            f"(2) Job offer with gross annual salary ≥{_eur(LEGAL_THRESHOLDS_2026.de_blue_card_general)} "
            f"(or {_eur(LEGAL_THRESHOLDS_2026.de_blue_card_shortage)} for shortage "
            "occupations: IT, engineering, math, science, doctors, nurses); "
            "(3) Employment matches qualification. "
            "Benefits: Fast-track permanent residence after 21 months (B1 German) or "
            "27 months (no German); intra-EU mobility after 18 months; "
            "family reunification with immediate work rights; no labour market test. "
            "Apply at Foreigners' Authority (Ausländerbehörde) or German embassy/consulate. "
            "Processing: 4–8 weeks. Valid up to 4 years (or contract duration + 3 months)."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Shortage occupations list",
                "action": "submit",
                "query": "Which occupations are on Germany's shortage occupation list for Blue Card?",
            },
            {
                "label": "Degree recognition",
                "action": "submit",
                "query": "How do I get my university degree recognized for Germany's Blue Card?",
            },
            {
                "label": "Fast-track permanent residence",
                "action": "submit",
                "query": "How does the 21-month permanent residence work for Blue Card holders?",
            },
        ],
        "references": [
            {
                "title": "Federal Office for Migration — EU Blue Card",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/blue-card/blue-card-node.html",
            },
        ],
    }


def _germany_skilled_worker_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The skilled worker residence permit (§18b AufenthG) is for qualified professionals "
            "with recognized vocational training or university degree. Requirements: "
            "(1) Recognized qualification (German or foreign equivalent); "
            "(2) Job offer matching the qualification; "
            "(3) Salary meets standard for the occupation (no fixed minimum, but must be "
            "sufficient for livelihood); "
            "(4) Labour market test (priority check) unless waived (shortage occupations, "
            "graduates of German universities, ICT). "
            "Benefits: Valid up to 4 years; path to permanent residence after 4 years "
            "(or 3 years with B1 German); family reunification; can change employers "
            "with new job offer matching qualification. "
            "Apply at Foreigners' Authority or German embassy/consulate. "
            "Processing: 4–8 weeks. No salary threshold like Blue Card."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Qualification recognition",
                "action": "submit",
                "query": "How do I get my foreign qualification recognized in Germany?",
            },
            {
                "label": "Shortage occupations waiver",
                "action": "submit",
                "query": "Which occupations waive the labour market test in Germany?",
            },
            {
                "label": "Permanent residence timeline",
                "action": "submit",
                "query": "How long until permanent residence on a skilled worker permit in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Office for Migration — Skilled workers",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/skilled-immigration/skilled-immigration-node.html",
            },
        ],
    }


def _germany_qualification_recognition_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Getting foreign qualifications recognized in Germany depends on the profession: "
            "(1) Regulated professions (doctors, nurses, teachers, engineers, crafts) — "
            "mandatory recognition via central bodies (ZAB for academic, IHK/HWK for vocational); "
            "(2) Non-regulated professions — voluntary recognition via ZAB (academic) or "
            "IHK FOSA (vocational); (3) EU professional qualifications — automatic recognition "
            "under Directive 2005/36/EC for certain professions. "
            "Process: Submit application + documents (degree, transcripts, curriculum, "
            "work experience proof, translations). Assessment compares to German equivalent. "
            "Outcomes: Full equivalence, partial equivalence (compensatory measures needed), "
            "or no equivalence. Compensatory measures: adaptation period (up to 3 years), "
            "aptitude test, or additional training. Costs: €200–€600+ depending on profession. "
            "Processing: 3–6 months. Start early — can apply from abroad."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Regulated vs non-regulated",
                "action": "submit",
                "query": "Which professions are regulated in Germany and require mandatory recognition?",
            },
            {
                "label": "Recognition process steps",
                "action": "submit",
                "query": "What are the steps to get my foreign degree recognized in Germany?",
            },
            {
                "label": "Compensatory measures",
                "action": "submit",
                "query": "What are compensatory measures if my qualification is partially recognized?",
            },
        ],
        "references": [
            {
                "title": "Recognition in Germany — Federal portal",
                "url": "https://www.anerkennung-in-deutschland.de/",
            },
        ],
    }


def _germany_jobseeker_visa_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The German job-seeker visa (§20 AufenthG) allows university graduates to enter "
            "Germany for up to 6 months to search for employment. Requirements: "
            "(1) Recognized university degree (German or foreign equivalent); "
            "(2) Sufficient funds: "
            f"~{_eur(LEGAL_THRESHOLDS_2026.de_opportunity_card_blocked_pm)}/month × 6 months = "
            f"~{_eur(LEGAL_THRESHOLDS_2026.de_opportunity_card_blocked_pm * 6)} total, "
            "blocked account (Sperrkonto) or declaration of commitment (Verpflichtungserklärung); "
            "(3) Health insurance valid in Germany; "
            "(4) Clean criminal record. "
            "Benefits: Can enter Germany and search for any qualified employment; "
            "once job found, convert to residence permit (§18b or Blue Card) without leaving; "
            "family members can join (separate visa). "
            "Restrictions: No work allowed during search period (except trial work up to "
            "10 hrs/week with approval); visa cannot be extended beyond 6 months. "
            "Apply at German embassy/consulate in country of residence. "
            "Processing: 4–12 weeks. Alternative: Opportunity Card (Chancenkarte) for "
            "points-based entry without job offer."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Blocked account setup",
                "action": "submit",
                "query": "How do I set up a blocked account (Sperrkonto) for a German job-seeker visa?",
            },
            {
                "label": "Converting to work permit",
                "action": "submit",
                "query": "How do I convert a job-seeker visa to a work permit in Germany?",
            },
            {
                "label": "Opportunity Card comparison",
                "action": "submit",
                "query": "What is the difference between job-seeker visa and Opportunity Card in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Foreign Office — Job-seeker visa",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198",
            },
        ],
    }


def _germany_opportunity_card_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Germany's Opportunity Card (Chancenkarte, §20a AufenthG) is a points-based system "
            "for skilled workers without a job offer (since June 2024). Requirements: "
            "(1) Recognized qualification (university degree or 2+ years vocational training); "
            "(2) Minimum 6 points from criteria: qualification (4 pts for recognized degree, "
            "3 for partial), German language (3 for B2, 2 for B1, 1 for A2), "
            "English (1 for C1), age (2 if ≤35, 1 if ≤40), work experience (3 for 5+ yrs, "
            "2 for 2+ yrs), previous stay in Germany (1 for 6+ months); "
            "(3) Sufficient funds: "
            f"~{_eur(LEGAL_THRESHOLDS_2026.de_opportunity_card_blocked_pm)}/month (blocked account or part-time work up to "
            "20 hrs/week allowed). "
            "Benefits: 1-year residence permit to search for work or start business; "
            "can work part-time (20 hrs/week) or do 2-week trial jobs; "
            "convert to skilled worker permit (§18b) or Blue Card when job found; "
            "extendable by 2 years if in qualified employment. "
            "Apply at German embassy/consulate or Foreigners' Authority if already in Germany. "
            "Processing: 4–8 weeks."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Points calculator",
                "action": "submit",
                "query": "How do I calculate my points for Germany's Opportunity Card?",
            },
            {
                "label": "Part-time work rules",
                "action": "submit",
                "query": "What part-time work is allowed on Germany's Opportunity Card?",
            },
            {
                "label": "Extension after job found",
                "action": "submit",
                "query": "How do I extend the Opportunity Card after finding a job in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Foreign Office — Opportunity Card",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198/2638926",
            },
        ],
    }


def _germany_self_employment_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The self-employment residence permit (§21 AufenthG) allows non-EU citizens to "
            "start a business or work as a freelancer in Germany. Requirements: "
            "(1) Business idea with economic benefit for Germany (innovation, jobs, "
            "regional development, import/export); "
            "(2) Viable business plan with financial projections; "
            "(3) Sufficient funding (own capital or committed financing); "
            "(4) Professional qualification/experience for the activity; "
            "(5) Health insurance; (6) Sufficient livelihood; (7) Clean criminal record. "
            "Freelancers (Freiberufler: doctors, lawyers, architects, engineers, artists, "
            "journalists, etc.) have easier access — no business plan requirement, "
            "but must prove professional qualification. "
            "Permit: initially 3 years, extendable. Path to permanent residence after 3 years "
            "if business successful (B1 German, livelihood secured). "
            "Apply at Foreigners' Authority. Involves Chamber of Commerce (IHK) or "
            "Chamber of Crafts (HWK) opinion. Processing: 2–4 months."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Business plan requirements",
                "action": "submit",
                "query": "What must a business plan include for German self-employment permit?",
            },
            {
                "label": "Freelancer vs trade",
                "action": "submit",
                "query": "What is the difference between Freiberufler and Gewerbe in Germany?",
            },
            {
                "label": "Permanent residence path",
                "action": "submit",
                "query": "How do I get permanent residence as a self-employed person in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Ministry of Economics — Self-employment",
                "url": "https://www.bmwk.de/Redaktion/EN/Artikel/Self-employment.html",
            },
        ],
    }


def _germany_vocational_training_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Non-EU citizens can come to Germany for vocational training (Ausbildung) "
            "with a residence permit (§16a AufenthG). Requirements: "
            "(1) Signed training contract with a German company; "
            "(2) Training occupation is state-recognized (350+ occupations); "
            "(3) Sufficient German language (usually B1/B2 depending on occupation); "
            "(4) Sufficient funds for livelihood (~€992/month) or training allowance "
            "(Ausbildungsvergütung typically €800–€1,200/month); "
            "(5) Health insurance; (6) Clean criminal record. "
            "Benefits: Work permit included (training + up to 20 hrs/week other work); "
            "after successful completion, 18-month job-seeker residence permit to find "
            "qualified employment; path to skilled worker permit (§18b) and permanent residence. "
            "Apply at German embassy/consulate. Processing: 4–8 weeks. "
            "Popular dual system: 70% practical in company, 30% vocational school. "
            "High demand in: nursing, IT, crafts, hospitality, commerce."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Finding training positions",
                "action": "submit",
                "query": "How do I find vocational training positions in Germany?",
            },
            {
                "label": "Language requirements",
                "action": "submit",
                "query": "What German level do I need for vocational training in Germany?",
            },
            {
                "label": "After completion options",
                "action": "submit",
                "query": "What residence permit can I get after completing Ausbildung in Germany?",
            },
        ],
        "references": [
            {
                "title": "Federal Employment Agency — Vocational training",
                "url": "https://www.arbeitsagentur.de/en/jobseekers/training/vocational-training",
            },
        ],
    }


def _spain_eu_registration_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "As an EU/EEA/Swiss citizen, you have the right to work in Spain without a "
            "work permit. You must register as a resident (Certificado de Registro de "
            "Ciudadano de la UE) at the Foreigners' Office (Oficina de Extranjería) or "
            "police station within 3 months of arrival if staying longer than 3 months. "
            "You'll need your passport/ID, proof of employment/self-employment, health "
            "insurance, and proof of sufficient resources. You'll also need a NIE (Número "
            "de Identidad de Extranjero) for tax and administrative purposes."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "EU citizen registration in Spain",
                "action": "submit",
                "query": "How do I register as an EU citizen in Spain?",
            },
            {
                "label": "NIE application",
                "action": "submit",
                "query": "How do I apply for a NIE number in Spain?",
            },
            {
                "label": "Health insurance requirements",
                "action": "submit",
                "query": "What health insurance do EU citizens need in Spain?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — EU citizen registration",
                "url": "https://www.inclusion.gob.es/extranjeria/ciudadanos-ue.htm",
            },
        ],
    }


def _spain_non_eu_job_offer_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "With a job offer, your employer must apply for a work authorization "
            "(Autorización de Trabajo y Residencia) at the Foreigners' Office. The main "
            "types: (1) General regime — employer must prove no suitable EU candidate "
            "(labour market test), waived for shortage occupations on the national "
            "catalogue; (2) Highly qualified professionals — simplified process for "
            "university graduates with job offers matching their qualifications; "
            "(3) EU Blue Card — for graduates with salary "
            f"≥{_eur(LEGAL_THRESHOLDS_2026.es_blue_card_general)}/year (2026); "
            "(4) Seasonal work — for temporary agricultural/tourism jobs. Processing "
            "takes 1–3 months. Once approved, you apply for the visa at the Spanish "
            "consulate in your country."
        ),
        "question": "Which permit type applies to you?",
        "options": [
            {
                "label": "EU Blue Card (Spain)",
                "action": "submit",
                "query": "What are the EU Blue Card requirements for Spain?",
            },
            {
                "label": "Highly qualified professional",
                "action": "submit",
                "query": "What are the requirements for the highly qualified professional permit in Spain?",
            },
            {
                "label": "Shortage occupations list",
                "action": "submit",
                "query": "Which occupations are on Spain's shortage occupation list?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Work permits",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena.htm",
            },
        ],
    }


def _spain_non_eu_no_job_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Without a job offer, options include: (1) Student visa — if admitted to a "
            "Spanish university; allows part-time work (up to 30 hrs/week); (2) "
            "Non-lucrative residence visa — for those with sufficient passive income "
            f"(~{_eur(LEGAL_THRESHOLDS_2026.es_non_lucrative_main)}/year in 2026) who won't work in Spain; (3) Entrepreneur/self-employed "
            "visa — requires viable business plan, investment, and job creation; "
            "(4) Family reunification — if you have a family member legally resident in "
            "Spain; (5) Digital nomad visa — new 2023 law allows remote work for foreign "
            "employers if you meet income requirements "
            f"(~{_eur(LEGAL_THRESHOLDS_2026.es_digital_nomad_main_pm)}/month in 2026)."
        ),
        "question": "Which option matches your situation?",
        "options": [
            {
                "label": "Student visa",
                "action": "submit",
                "query": "What are the student visa requirements for Spain?",
            },
            {
                "label": "Non-lucrative residence visa",
                "action": "submit",
                "query": "What are the requirements for Spain's non-lucrative residence visa?",
            },
            {
                "label": "Digital nomad visa",
                "action": "submit",
                "query": "What are the requirements for Spain's digital nomad visa?",
            },
            {
                "label": "Entrepreneur visa",
                "action": "submit",
                "query": "What are the requirements for Spain's entrepreneur visa?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Visas",
                "url": "https://www.inclusion.gob.es/extranjeria/visados.htm",
            },
        ],
    }


def _spain_student_visa_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Non-EU students need a student visa (Visado de Estudios) for stays over 90 days. "
            "Requirements: (1) Admission to a recognized Spanish educational institution; "
            "(2) Proof of sufficient financial means — 100% of IPREM (€600/month in 2026), "
            "so €7,200/year for the main applicant and the same rate per dependent; "
            "(3) Health insurance valid in Spain (public or "
            "private with no co-payments); (4) Clean criminal record certificate; "
            "(5) Medical certificate confirming no public health risk. "
            "The visa allows part-time work (up to 30 hrs/week) if it does not interfere with studies. "
            "Apply at the Spanish consulate in your country of residence. "
            "Processing takes 1–3 months. EU/EEA/Swiss citizens do not need a visa — only registration after 3 months."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Financial requirements details",
                "action": "submit",
                "query": "What are the exact financial requirements for a Spanish student visa?",
            },
            {
                "label": "Working while studying",
                "action": "submit",
                "query": "Can I work on a Spanish student visa and what are the limits?",
            },
            {
                "label": "Visa renewal",
                "action": "submit",
                "query": "How do I renew my Spanish student visa after the first year?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Student visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-estudios.htm",
            },
        ],
    }


def _spain_student_visa_financial_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Financial proof for a Spanish student visa (Visado de Estudios) is based on IPREM. "
            "You must show 100% of IPREM per month — €600/month in 2026, i.e. €7,200 for a "
            "12-month stay — for the main applicant, and the same rate for each dependent. "
            "Accepted evidence: bank statements, a scholarship/grant letter, or a financial "
            "guarantee from a Spanish resident. The funds must cover the full intended stay; "
            "shorter courses require the equivalent pro-rata amount. This is checked again at "
            "every renewal, so keep proof current."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Student visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-estudios.htm",
            },
        ],
    }


def _spain_student_visa_work_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "A Spanish student visa allows part-time work up to 30 hours per week (raised from "
            "20h in the 2022 reform), provided the work does not interfere with your studies. "
            "The contract must be compatible with your class schedule and cannot be your main "
            "source of income. Your employer submits the work authorization (Autorización de "
            "Trabajo) to the Oficina de Extranjería; no separate work permit is needed for you "
            "to accept it. After graduation you get up to 12 months to find a job and switch to "
            "a work authorization."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Student visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-estudios.htm",
            },
        ],
    }


def _spain_student_visa_renewal_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "To stay beyond your initial visa you must renew the TIE (Tarjeta de Identidad de "
            "Extranjero) — the student residence card — before it expires (apply for "
            "'renovación del TIE de estudiante' at the Oficina de Extranjería). You need: proof "
            "of continued enrolment, the same financial means as the first application (100% "
            "IPREM, €600/month in 2026), renewed health insurance, and a clean record. "
            "Renewals are typically granted for the remaining duration of your studies. Apply "
            "60 days before expiry, or within 90 days after (late, with a penalty)."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Student visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-estudios.htm",
            },
        ],
    }


def _spain_non_lucrative_visa_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The non-lucrative residence visa (Visado de Residencia No Lucrativa) is for non-EU "
            "citizens who want to live in Spain without working. Key requirements (2026): "
            f"(1) Sufficient passive income: ~{_eur(LEGAL_THRESHOLDS_2026.es_non_lucrative_main)}/year for the applicant, "
            f"+ ~{_eur(LEGAL_THRESHOLDS_2026.es_non_lucrative_dep)}/year per dependent (IPREM-based); "
            "(2) Private health insurance with full coverage in Spain (no co-payments, "
            "no waiting periods, repatriation coverage); "
            "(3) Clean criminal record from countries of residence (last 5 years); "
            "(4) Medical certificate; "
            "(5) Proof of accommodation in Spain. "
            "This visa does NOT allow any work or professional activity in Spain. "
            "Initial visa: 1 year. Renewable for 2 years, then 2 years. "
            "After 5 years, eligible for long-term EU residence permit. "
            "Apply at Spanish consulate in your country. Processing: 1–3 months."
        ),
        "question": "What would you like to explore further?",
        "options": [
            {
                "label": "Passive income proof",
                "action": "submit",
                "query": "What counts as passive income for Spain's non-lucrative visa?",
            },
            {
                "label": "Health insurance details",
                "action": "submit",
                "query": "What health insurance requirements for Spain non-lucrative visa?",
            },
            {
                "label": "Path to permanent residence",
                "action": "submit",
                "query": "How do I get permanent residence in Spain after non-lucrative visa?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Non-lucrative visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-residencia-no-lucrativa.htm",
            },
        ],
    }


def _spain_digital_nomad_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Spain's digital nomad visa (Visado para Teletrabajo Internacional) allows remote work "
            "for foreign employers/companies. Requirements (2026): "
            "(1) Work remotely for a company outside Spain (or ≤20% Spanish-sourced income); "
            "(2) Minimum 3 months employment relationship or self-employment track record; "
            "(3) University degree or 3 years professional experience; "
            "(4) Monthly income "
            f"≥{_eur(LEGAL_THRESHOLDS_2026.es_digital_nomad_main_pm)} (2x SMI 2026), "
            f"+{_eur(LEGAL_THRESHOLDS_2026.es_digital_nomad_dep1_pm)} per dependent; "
            "(5) Health insurance covering all risks in Spain; "
            "(6) Clean criminal record; (7) Tax residence in Spain (Beckham Law optional: "
            "24% flat tax on income ≤€600k for 6 years if not tax resident in Spain in "
            "previous 5 years). Visa valid 1 year (consulate) or 3 years (in Spain). "
            "Renewable for 2 years. Path to permanent residence after 5 years."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Beckham Law tax regime",
                "action": "submit",
                "query": "How does the Beckham Law work for digital nomads in Spain?",
            },
            {
                "label": "Income requirements proof",
                "action": "submit",
                "query": "How do I prove income for Spain's digital nomad visa?",
            },
            {
                "label": "Family members",
                "action": "submit",
                "query": "Can my family join me on Spain's digital nomad visa?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Digital nomad visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-teletrabajo.htm",
            },
        ],
    }


def _spain_entrepreneur_visa_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Spain's entrepreneur visa (Visado de Emprendedores) is for non-EU citizens starting "
            "an innovative business in Spain. Requirements: "
            "(1) Innovative business plan with economic/social impact in Spain "
            "(tech, R&D, job creation, strategic sectors); "
            "(2) Endorsement from a recognized Spanish entity (ENISA, accelerators, "
            "universities, business angels); "
            "(3) Sufficient investment funds (no fixed minimum, but plan must be viable); "
            "(4) Professional qualifications/experience to execute the plan; "
            "(5) Health insurance; (6) Clean criminal record. "
            "Visa: 1 year (consulate) or 3 years (in Spain). Renewable 2+2 years. "
            "Fast-track residence permit for highly innovative projects. "
            "Creates jobs and contributes to Spanish innovation ecosystem. "
            "Apply via UGE (Unidad de Grandes Empresas) or Spanish consulate."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Endorsement process",
                "action": "submit",
                "query": "How do I get my business plan endorsed for Spain's entrepreneur visa?",
            },
            {
                "label": "Investment requirements",
                "action": "submit",
                "query": "What investment is needed for Spain's entrepreneur visa?",
            },
            {
                "label": "Fast-track residence",
                "action": "submit",
                "query": "What is the fast-track residence permit for entrepreneurs in Spain?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Entrepreneur visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-emprendedores.htm",
            },
        ],
    }


def _spain_nie_application_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The NIE (Número de Identidad de Extranjero) is a tax identification number "
            "required for all foreigners in Spain for legal, financial, and administrative "
            "matters. EU/EEA/Swiss citizens get it automatically when registering as "
            "residents (Certificado de Registro). Non-EU citizens apply separately. "
            "How to apply: (1) In Spain: at the Foreigners' Office (Oficina de Extranjería) "
            "or designated police station with EX-15 form, passport, proof of reason "
            "(employment, study, property purchase, etc.), and fee (~€12); "
            "(2) At Spanish consulate abroad: before arriving in Spain. "
            "EU citizens: NIE issued same day with registration certificate. "
            "Non-EU: processing 1–4 weeks. The NIE is printed on a white A4 certificate "
            "(not a card for EU citizens). Non-EU residents get it on their TIE card "
            "(Tarjeta de Identidad de Extranjero). No expiry for EU citizens; "
            "for non-EU, tied to residence permit validity."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "NIE vs TIE difference",
                "action": "submit",
                "query": "What is the difference between NIE and TIE in Spain?",
            },
            {
                "label": "Applying from abroad",
                "action": "submit",
                "query": "Can I apply for NIE at a Spanish consulate before moving to Spain?",
            },
            {
                "label": "Documents needed",
                "action": "submit",
                "query": "What documents do I need for NIE application in Spain?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — NIE",
                "url": "https://www.inclusion.gob.es/extranjeria/nie.htm",
            },
        ],
    }


def _spain_eu_health_insurance_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "EU/EEA/Swiss citizens registering as residents in Spain need health insurance "
            "covering all risks in Spain. Options: (1) European Health Insurance Card (EHIC) — "
            "covers necessary healthcare during temporary stays, but NOT sufficient for "
            "residence registration (only for tourists/students <3 months); "
            "(2) Public Spanish healthcare (SNS) — available after registering as resident "
            "and obtaining social security number; contributions deducted from salary if "
            "employed, or voluntary contributions if self-employed/inactive; "
            "(3) Private health insurance — must have NO co-payments, NO waiting periods, "
            "full coverage in Spain, and repatriation. Minimum coverage: €30,000. "
            "Required for: non-lucrative visa, digital nomad visa, entrepreneur visa, "
            "and EU citizens registering without employment (self-sufficient). "
            "Students: EHIC or private student insurance accepted. "
            "Family members of EU workers: covered under worker's social security."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "EHIC limitations",
                "action": "submit",
                "query": "Why is EHIC not enough for Spanish residence registration?",
            },
            {
                "label": "Private insurance requirements",
                "action": "submit",
                "query": "What are the exact requirements for private health insurance in Spain?",
            },
            {
                "label": "Public healthcare access",
                "action": "submit",
                "query": "How do I access Spanish public healthcare (SNS) as a resident?",
            },
        ],
        "references": [
            {
                "title": "Spanish Social Security — Healthcare",
                "url": "https://www.seg-social.es/wps/portal/wss/internet/AtencionCiudadana/AsistenciaSanitaria",
            },
        ],
    }


def _spain_blue_card_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Spain's EU Blue Card is for highly qualified non-EU professionals. Requirements (2026): "
            "(1) University degree (3+ years) or 5+ years professional experience "
            "equivalent to degree level; "
            "(2) Job offer/contract for ≥1 year matching qualification; "
            "(3) Gross annual salary "
            f"≥{_eur(LEGAL_THRESHOLDS_2026.es_blue_card_general)} (2026), except shortage occupations "
            f"({_eur(LEGAL_THRESHOLDS_2026.es_blue_card_reduced)} for ICT, engineering, healthcare); "
            "(4) Employer registered in Spain. "
            "Benefits: Family reunification with immediate work rights; "
            "intra-EU mobility after 18 months; "
            "permanent EU residence after 5 years (or 2 years if B1 Spanish); "
            "no labour market test. Valid up to 3 years (+3 months). "
            "Apply: employer initiates at UGE (Unidad de Grandes Empresas) or "
            "Foreigners' Office. Processing: 20–30 days. "
            "Renewable. Can switch employers after 2 years (notify authorities)."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Shortage occupations list",
                "action": "submit",
                "query": "Which occupations are on Spain's shortage occupation list for Blue Card?",
            },
            {
                "label": "Family reunification",
                "action": "submit",
                "query": "How does family reunification work for Spain Blue Card holders?",
            },
            {
                "label": "Degree equivalence",
                "action": "submit",
                "query": "How do I prove my degree is equivalent for Spain's Blue Card?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — EU Blue Card",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/tarjeta-azul-ue.htm",
            },
        ],
    }


def _spain_highly_qualified_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The Highly Qualified Professional permit (Profesional Altamente Cualificado) "
            "is a simplified work permit for university graduates with a job offer "
            "matching their qualifications. Requirements: "
            "(1) University degree (3+ years) or higher vocational training; "
            "(2) Job offer for qualified position matching studies; "
            f"(3) Salary ≥{_eur(LEGAL_THRESHOLDS_2026.es_blue_card_general)}/year (same as Blue Card threshold); "
            "(4) No labour market test required. "
            "Difference from Blue Card: only valid in Spain (no EU mobility); "
            "no fast-track permanent residence; simpler process for employers. "
            "Valid 2 years, renewable. Apply at Foreigners' Office or UGE. "
            "Processing: ~1 month. Good option if you don't need EU mobility "
            "or salary is slightly below Blue Card threshold but meets this one."
        ),
        "question": "What would you like to explore?",
        "options": [
            {
                "label": "Blue Card vs Highly Qualified",
                "action": "submit",
                "query": "What is the difference between EU Blue Card and Highly Qualified Professional permit in Spain?",
            },
            {
                "label": "Qualification matching",
                "action": "submit",
                "query": "How strictly must the job match my degree for Spain's Highly Qualified permit?",
            },
            {
                "label": "Renewal process",
                "action": "submit",
                "query": "How do I renew the Highly Qualified Professional permit in Spain?",
            },
        ],
        "references": [
            {
                "title": "Spanish Ministry of Inclusion — Highly qualified professionals",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/profesionales-cualificados.htm",
            },
        ],
    }


def _spain_shortage_occupations_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Spain's shortage occupation list (Catálogo de Ocupaciones de Difícil Cobertura) "
            "exempts employers from the labour market test (proving no EU candidate available). "
            "Updated quarterly by province. Current common shortage sectors (2026): "
            "ICT/software developers, engineers (civil, industrial, telecom), "
            "healthcare (nurses, doctors, specialists), "
            "construction skilled trades (welders, electricians, plumbers), "
            "hospitality chefs, agricultural specialists, maritime workers. "
            "Check the latest list at SEPE (Servicio Público de Empleo Estatal) by province. "
            "If your occupation is listed: employer skips 2-week job posting, "
            "directly applies for work authorization. "
            "Applies to: general regime work permits, seasonal work, "
            "and reduces Blue Card salary threshold to €28,800."
        ),
        "question": "What would you like to know next?",
        "options": [
            {
                "label": "Current list by province",
                "action": "submit",
                "query": "Where can I find the current shortage occupation list for my Spanish province?",
            },
            {
                "label": "How list is updated",
                "action": "submit",
                "query": "How often is Spain's shortage occupation list updated and who decides?",
            },
            {
                "label": "Employer process",
                "action": "submit",
                "query": "How does an employer hire using the shortage occupation exemption in Spain?",
            },
        ],
        "references": [
            {
                "title": "SEPE — Shortage occupations catalogue",
                "url": "https://www.sepe.es/HomeSepe/Que-es-el-SEPE/Catalogo-Ocupaciones-Dificil-Cobertura.html",
            },
        ],
    }


# ── AUTO-GENERATED SUB-INTENT HANDLERS (focused follow-up answers) ──


def _germany_address_burgeramt_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "To register your address (Anmeldung) you must book an appointment at the local Bürgeramt (citizens' office) for the district where you live. Book online via your city's Bürgeramt portal — slots fill weeks ahead in large cities, so book as soon as you have a signed rental contract. Bring: passport/ID, the completed Anmeldeformular, and the Wohnungsgeberbestätigung from your landlord. The appointment takes a few minutes; you receive the Meldebescheinigung immediately. Register within 14 days of moving in."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Berlin Bürgeramt — Registration",
                "url": "https://service.berlin.de/dienstleistung/120686/",
            },
        ],
    }


def _germany_wohnungsgeber_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The Wohnungsgeberbestätigung (landlord confirmation) is a mandatory form your landlord must complete and sign, confirming you have moved into the flat at a given address and date. It's required for the Anmeldung. Ask your landlord for it when you sign the rental contract — many use the official template 'Wohnungsgeberbestätigung gemäß §19 BMG'. Without it the Bürgeramt rejects your registration. Landlords are legally obliged to provide it."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Ministry — Registration",
                "url": "https://www.bmi.bund.de/EN/topics/migration/integration/registration/registration-node.html",
            },
        ],
    }


def _germany_tax_id_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The Steueridentifikationsnummer (tax ID) is issued automatically by the Federal Central Tax Office (BZSt) a few weeks after your Anmeldung — you do NOT apply separately. It's a permanent 11-digit number valid for life, mailed to your registered address. You need it for employment, opening a bank account, and filing taxes. If lost, request a reissue (Mitteilung) from the BZSt."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BZSt — Tax ID",
                "url": "https://www.bzst.de/EN/Private_taxpayers/Tax_Identification_Number/tax_identification_number_node.html",
            },
        ],
    }


def _germany_blue_card_shortage_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The reduced Blue Card salary threshold (€45 934 in 2026) applies to shortage occupations (Mangelberufe): IT specialists, engineers, mathematicians and scientists, doctors, and nurses. The official list is the 'Positivliste' published by the Federal Employment Agency (BA). If your job title is on it, you qualify for the lower salary threshold and a faster process. The list is updated periodically; check the BA's current publication."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Employment Agency — Shortage occupations",
                "url": "https://www.arbeitsagentur.de/fuer-menschen-aus-dem-ausland/arbeiten-in-deutschland/berufe-auf-der-positivliste",
            },
        ],
    }


def _germany_blue_card_degree_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "For a Blue Card your degree must be recognized as equivalent to a German university degree. Check the anabin database (ZAB) — if your university and degree are 'H+' and 'entspricht', no further action is needed. If not, apply for a Statement of Comparability (ZAB). EU/EEA/Swiss degrees are recognized under Directive 2005/36/EC. Recognition is required before the employer submits the Blue Card application; start early."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Recognition in Germany — anabin",
                "url": "https://www.anabin.de/",
            },
        ],
    }


def _germany_blue_card_pr_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Blue Card holders get a fast-track to permanent residence (Niederlassungserlaubnis): after just 21 months with sufficient German (B1) and pension contributions, or after 27 months without German. You must still be employed in a qualifying role and have adequate living space. Once granted, it's unlimited and independent of the employer. Family members can also get permanent residence on the same timeline."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Office — Permanent residence",
                "url": "https://www.bamf.de/EN/Themen/MigrationAufenthalt/ZuwandererDrittstaaten/MigrationAsyl/BlauCard/blau-card-node.html",
            },
        ],
    }


def _germany_eu_address_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "As an EU/EEA/Swiss citizen you register your address through the normal Anmeldung at the Bürgeramt within 14 days. Separately, if you stay longer than 3 months, obtain the registration certificate (Anmeldebescheinigung) from the immigration office (Ausländerbehörde) as proof of free-movement rights — useful for banking, phone contracts, and authorities. No residence permit or work visa is required."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMI — Free movement",
                "url": "https://www.bmi.bund.de/EN/topics/migration/integration/registration/registration-node.html",
            },
        ],
    }


def _germany_eu_family_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "As an EU citizen exercising free movement, your non-EU family members join you under EU law, not the stricter national rules. They get the EU family member residence card (Aufenthaltskarte) valid 5 years. Covered: spouse/partner, children/grandchildren under 21 or dependent, and dependent parents/grandparents. They need only proof of the family tie, your treaty-rights exercise, health insurance, and sufficient resources. They also receive derived free-movement work rights."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BAMF — EU family reunification",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/family-reunification/family-reunification-node.html",
            },
        ],
    }


def _germany_eu_health_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "EU citizens working in Germany are covered by the German statutory system like anyone else: if employed with income ≤€77 400/year (2026) you join public insurance (GKV) with employer/employee splitting the ~14.6%+ contribution; above that, or if self-employed/civil servant, you can choose private (PKV). Your EHIC covers only temporary visits, not residence. If posted from another EU state for under 24 months, you may stay in your home scheme — your employer needs an A1 certificate."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMG — Health insurance",
                "url": "https://www.bundesgesundheitsministerium.de/service/begriffe-von-a-z/k/krankenversicherung.html",
            },
        ],
    }


def _germany_health_public_private_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Public (GKV): premium ~14.6% of income split with employer, covers dependents at no extra cost, no medical underwriting, but less choice of doctor/treatment and contributions rise with income. Private (PKV): premium based on age/health not income, faster specialist access, but dependents need separate contracts, premiums rise with age, and switching back to public is restricted (income cap, age limits). Employees with income >€77 400/year (2026) may choose; below that you stay public."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMG — Health insurance",
                "url": "https://www.bundesgesundheitsministerium.de/service/begriffe-von-a-z/k/krankenversicherung.html",
            },
        ],
    }


def _germany_a1_certificate_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The A1 certificate proves your social security (including health insurance) stays in your home EU country while you are temporarily posted to Germany (typically <24 months). Your employer in the home country applies for it before you travel. With a valid A1 you remain in the home scheme and are exempt from German social-security contributions — important for cross-border workers. Without it, German authorities may treat you as locally insured."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "European Commission — Posted workers",
                "url": "https://commission.europa.eu/employment-social-affairs-and-inclusion/labour-law-and-social-dialogue/posting-workers_en",
            },
        ],
    }


def _germany_eu_student_health_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "EU/EEA/Swiss students in Germany can use their EHIC or a recognized home-country student insurance policy for enrolment — public universities require proof of coverage. If you take up employment alongside studies, you must join German public insurance (GKV). Confirm with your university's enrolment office which proof they accept before arrival."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMG — Health insurance",
                "url": "https://www.bundesgesundheitsministerium.de/service/begriffe-von-a-z/k/krankenversicherung.html",
            },
        ],
    }


def _germany_family_docs_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "For the EU family member residence card (Aufenthaltskarte) you need: (1) valid passport/ID; (2) proof of the family relationship — marriage or birth certificate with certified translation; (3) proof you (the EU citizen) exercise treaty rights — employment contract, enrolment, or self-sufficiency; (4) health insurance; (5) proof of sufficient resources. Apply at the Ausländerbehörde; processing 4–8 weeks."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BAMF — EU family reunification",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/family-reunification/family-reunification-node.html",
            },
        ],
    }


def _germany_family_spouse_visa_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "A non-EU spouse of an EU citizen generally does NOT need a visa to enter Germany if they hold a valid passport — under EU free-movement law they can arrive and then apply for the residence card (Aufenthaltskarte). Some nationalities may need a visa depending on visa-liberalization agreements; in that case apply for a 'visa for family reunification with an EU citizen', processed quickly under simplified rules (no income/housing proof from the EU citizen)."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BAMF — EU family reunification",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/family-reunification/family-reunification-node.html",
            },
        ],
    }


def _germany_family_pr_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "After 5 years of continuous residence under EU free-movement law, your non-EU family members become eligible for a permanent right of residence (Daueraufenthaltsrecht) — no card renewal needed. It's granted automatically by law; you can request a confirmation certificate from the Ausländerbehörde. The 5 years count from when the EU citizen exercised treaty rights. Absences under 6 months (or 12 for important reasons) don't break continuity."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BAMF — EU family reunification",
                "url": "https://www.bamf.de/EN/Service/ServiceCenter/family-reunification/family-reunification-node.html",
            },
        ],
    }


def _germany_jobseeker_sperrkonto_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "A Sperrkonto (blocked account) proves you can fund your 6-month job search: ~€1 091/month × 6 = ~€6 546 in 2026, locked but released in monthly instalments. Open it with a German bank (e.g. Deutsche Bank, or a specialist like Fintiba/Expatrio) before your embassy appointment; submit the confirmation with the visa application. Alternatively a Verpflichtungserklärung (formal obligation from a German resident) is accepted instead."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Foreign Office — Job-seeker visa",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198",
            },
        ],
    }


def _germany_jobseeker_convert_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Once you receive a qualified job offer while on the job-seeker visa, you convert in-place — you do NOT need to leave Germany. Apply at the local Ausländerbehörde for a residence permit for employment (§18b skilled worker) or a Blue Card, submitting the signed contract, degree recognition proof, and health insurance. The switch is usually straightforward since you're already legally present; processing 4–8 weeks."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Foreign Office — Job-seeker visa",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198",
            },
        ],
    }


def _germany_jobseeker_vs_opportunity_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Both let you enter to look for work, but differ: the Job-seeker visa (§20) requires a recognized university degree and allows NO work during search (only trial work ≤10 hrs/week with approval), for up to 6 months. The Opportunity Card (Chancenkarte, §20a) is points-based (degree OR 2+ yrs vocational training) and lets you work part-time (20 hrs/week) or do 2-week trials while searching, for 1 year. Choose the Opportunity Card if you lack a degree but have vocational training/points."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Foreign Office — Opportunity Card",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198/2638926",
            },
        ],
    }


def _germany_opportunity_points_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "You need at least 6 points from: qualification (4 for a recognized degree, 3 for partial recognition), German (3 for B2, 2 for B1, 1 for A2), English (1 for C1), age (2 if ≤35, 1 if ≤40), work experience (3 for 5+ yrs, 2 for 2+ yrs), prior stay in Germany (1 for 6+ months). You must also have a recognized qualification and sufficient funds (~€1 091/month blocked account or part-time work). Reach 6 and you qualify; the embassy checks each criterion against your documents."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Foreign Office — Opportunity Card",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198/2638926",
            },
        ],
    }


def _germany_opportunity_work_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "While job-hunting on the Opportunity Card you may work part-time up to 20 hrs/week, or do two-week trial jobs (Probearbeit) with employers — both count as 'looking for qualified employment'. You may also start self-employment. Any income helps prove funds. Once you secure a qualified job, convert to a skilled-worker permit (§18b) or Blue Card; the part-time limit no longer applies."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Foreign Office — Opportunity Card",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198/2638926",
            },
        ],
    }


def _germany_opportunity_extend_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "If you find qualified employment within the 1-year Opportunity Card, you convert (not 'extend') to a residence permit for employment (§18b) or Blue Card at the Ausländerbehörde — no need to leave. If you're still searching but in qualified work, the card is extendable by up to 2 years while you remain in that employment. Apply before expiry with your contract and continued funds/insurance proof."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Foreign Office — Opportunity Card",
                "url": "https://www.auswaertiges-amt.de/en/visa-service/231198/2638926",
            },
        ],
    }


def _germany_regulated_professions_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Regulated professions require mandatory recognition before you can practice: doctors, nurses, dentists, pharmacists, teachers, lawyers, and most crafts (Meister). The central recognition bodies are ZAB (academic) and IHK/HWK (vocational). Non-regulated professions (e.g. most business, IT roles without a protected title) need only voluntary recognition, which can still help job prospects. EU qualifications are recognized under Directive 2005/36/EC with automatic equivalence for listed professions."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Recognition in Germany",
                "url": "https://www.anerkennung-in-deutschland.de/",
            },
        ],
    }


def _germany_recognition_steps_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Steps: (1) Identify the competent body — ZAB for academic degrees, IHK FOSA for vocational, or the relevant chamber for regulated professions. (2) Gather documents: degree certificate, transcripts, curriculum, work-experience proof, certified translations. (3) Submit the application (often online via anerkennung-in-deutschland.de or the chamber). (4) Wait for assessment (3–6 months) comparing to the German equivalent. (5) Receive outcome: full, partial, or no equivalence. You can apply from abroad."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Recognition in Germany",
                "url": "https://www.anerkennung-in-deutschland.de/",
            },
        ],
    }


def _germany_compensatory_measures_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "If your qualification is only partially recognized, Germany requires compensatory measures to close the gap: an adaptation period (Eignungszeit) of up to 3 years working under supervision, an aptitude test (Eignungsprüfung), or additional training courses. The competent body chooses the least burdensome option. Costs (€200–€600+ depending on profession) are yours. Completing the measure upgrades you to full equivalence."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Recognition in Germany",
                "url": "https://www.anerkennung-in-deutschland.de/",
            },
        ],
    }


def _germany_self_business_plan_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The business plan for a §21 self-employment permit must show economic benefit to Germany and viability: (1) a clear business idea with innovation/jobs/regional-development or import-export angle; (2) financial projections (revenue, costs, profitability over 3 years); (3) funding proof (own capital or committed financing); (4) your professional qualification/experience; (5) market analysis. The IHK/HWK reviews it and issues an opinion the authority weighs heavily."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMWK — Self-employment",
                "url": "https://www.bmwk.de/Redaktion/EN/Artikel/Self-employment.html",
            },
        ],
    }


def _germany_freiberufler_gewerbe_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Freiberufler (liberal professions — doctors, lawyers, architects, engineers, artists, journalists) need NO business plan or trade-office (Gewerbeamt) registration; they prove professional qualification and register only with the tax office (Finanzamt). Gewerbe (trade/commercial activity) requires Gewerbeanmeldung at the trade office and an IHK opinion for the visa. Freelancers have a lighter permit path but must show the activity is genuinely liberal-profession based."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMWK — Self-employment",
                "url": "https://www.bmwk.de/Redaktion/EN/Artikel/Self-employment.html",
            },
        ],
    }


def _germany_self_pr_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Self-employed residents can get permanent residence (Niederlassungserlaubnis) after 3 years if the business is successful (solid revenue, jobs created) and you have B1 German plus secured livelihood. The authority reviews tax returns, Chamber opinion, and economic impact. The initial permit (3 years, extendable) converts to unlimited residence on proof of success. Plan finances so the business shows viability by year 2."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BMWK — Self-employment",
                "url": "https://www.bmwk.de/Redaktion/EN/Artikel/Self-employment.html",
            },
        ],
    }


def _germany_skilled_recognition_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Skilled-worker status (§18b) requires a recognized qualification: a German or foreign degree comparable to a German one (via anabin/ZAB) or completed vocational training recognized as equivalent. For regulated professions, full recognition is mandatory. Start the recognition process before job-searching — it's a visa prerequisite and can take 3–6 months. EU qualifications benefit from automatic recognition under Directive 2005/36/EC."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Recognition in Germany",
                "url": "https://www.anerkennung-in-deutschland.de/",
            },
        ],
    }


def _germany_skilled_labour_test_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The labour-market test (priority check) is waived for: shortage occupations on the Positivliste (IT, engineering, doctors, nurses, maths/science); EU Blue Card and Highly Qualified holders; and recognized skilled workers with a degree in a related field. For other roles the employer must show no suitable German/EU candidate was found. Waivers speed up the permit from weeks to days."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Employment Agency — Skilled immigration",
                "url": "https://www.arbeitsagentur.de/fuer-menschen-aus-dem-ausland/arbeiten-in-deutschland",
            },
        ],
    }


def _germany_skilled_pr_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Skilled workers (§18b) can obtain permanent residence (Niederlassungserlaubnis) after 4 years of employment with contributions, or sooner with B1 German. Blue Card holders get it even faster — 21 months with B1, 27 without. You must have paid pension contributions, have adequate housing, and be in secure employment. Family members follow the same timeline."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "BAMF — Skilled immigration",
                "url": "https://www.bamf.de/EN/Themen/MigrationAufenthalt/ZuwandererDrittstaaten/MigrationAsyl/blaukarte/blau-card-node.html",
            },
        ],
    }


def _germany_vocational_find_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Find Ausbildung positions via: the Federal Employment Agency portal (arbeitsagentur.de, filter 'Ausbildung'), company career pages (especially nursing, IT, crafts, hospitality, commerce), and vocational-school partnerships. You need a signed training contract with a German company for the residence permit. Apply 6–12 months before the August/September start. Strong German (B1/B2) improves your chances significantly."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Employment Agency — Vocational training",
                "url": "https://www.arbeitsagentur.de/en/jobseekers/training/vocational-training",
            },
        ],
    }


def _germany_vocational_german_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Most Ausbildung occupations require German B1, with care/health and customer-facing roles often needing B2. The contract employer and the visa authority judge adequacy by occupation. Prove it with a Goethe/ÖSD/TELC certificate or school attestation. If your German is below B1, consider a preparatory language visa first. Language level also affects your livelihood-proof expectations."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Employment Agency — Vocational training",
                "url": "https://www.arbeitsagentur.de/en/jobseekers/training/vocational-training",
            },
        ],
    }


def _germany_vocational_after_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "After successfully finishing your Ausbildung you get an 18-month job-seeker residence permit (§20 Abs. 3 AufenthG) to find qualified employment in your trained occupation. Once employed, convert to a skilled-worker permit (§18b) or Blue Card. This path leads to permanent residence after the standard skilled-worker period. Completing the training in Germany eases the transition to employers."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Federal Employment Agency — Vocational training",
                "url": "https://www.arbeitsagentur.de/en/jobseekers/training/vocational-training",
            },
        ],
    }


def _spain_eu_register_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "As an EU/EEA/Swiss citizen staying over 3 months, register at the Oficina de Extranjería or police station for the Certificado de Registro de Ciudadano de la UE. Bring: passport/ID, proof of employment/self-employment (or sufficient resources + health insurance if not working), and the EX-18 form. You'll also be assigned a NIE. The certificate confirms your residence rights and is free (only the TIE card, if requested, has a fee). Do this within 3 months of arrival."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — EU registration",
                "url": "https://www.inclusion.gob.es/extranjeria/ciudadanos-ue.htm",
            },
        ],
    }


def _spain_nie_apply_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Apply for the NIE at the Oficina de Extranjería (EX-15 form) or a Spanish consulate abroad, with passport, proof of why you need it (job, study, property), and the ~€12 fee. EU citizens receive it automatically with their registration certificate (same day); non-EU citizens wait 1–4 weeks. You need the NIE for renting, buying property, banking, and taxes. Non-EU residents get it printed on their TIE card."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — NIE",
                "url": "https://www.inclusion.gob.es/extranjeria/nie.htm",
            },
        ],
    }


def _spain_eu_health_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "EU citizens registering as residents need health coverage for all risks in Spain. If employed, you're covered by the SNS (Spanish public healthcare) via social-security contributions. If self-sufficient/unemployed, you must hold private insurance with NO co-payments, NO waiting periods, full Spanish coverage, and repatriation (min €30,000). The EHIC alone is NOT enough for residence registration — it only covers temporary stays."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Social Security — Healthcare",
                "url": "https://www.seg-social.es/wps/portal/wss/internet/AtencionCiudadana/AsistenciaSanitaria",
            },
        ],
    }


def _spain_nl_passive_income_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Passive income for the non-lucrative visa means money you earn WITHOUT working in Spain: pensions, rental income, dividends, interest, royalties, or certain foreign-source income from before you moved. You must prove ~€28 800/year for the main applicant plus ~€7 200 per dependent (IPREM-based, 2026) via bank statements, property deeds, or pension letters. Crucially, the visa forbids ANY work or professional activity in Spain."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Non-lucrative visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-residencia-no-lucrativa.htm",
            },
        ],
    }


def _spain_nl_health_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Non-lucrative visa applicants must hold private health insurance covering ALL risks in Spain with: NO co-payments, NO waiting periods, full territorial coverage, and repatriation. Public Spanish healthcare (SNS) does NOT satisfy the requirement unless you're an EU citizen covered via the S1 form. The policy must be contracted with a Spanish-authorized insurer (not travel insurance). Present the policy certificate at the consulate."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Non-lucrative visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-residencia-no-lucrativa.htm",
            },
        ],
    }


def _spain_nl_pr_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The non-lucrative visa path: initial 1-year visa, then renewals of 2 + 2 years. After 5 years of continuous legal residence you qualify for the long-term (EU) residence permit (Autorización de residencia de larga duración), renewable every 5 years with near-equal rights to Spaniards. Continuity requires timely renewals; absences under 6 months per year (or 12 for important reasons) don't break it."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Non-lucrative visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-residencia-no-lucrativa.htm",
            },
        ],
    }


def _spain_dn_beckham_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The Beckham Law (special expat tax regime) lets new Spanish tax residents pay a flat 24% on income up to €600k (vs progressive rates to 47%) for up to 6 years. Digital nomads qualify if they weren't tax residents in Spain in the previous 5 years and apply within 6 months of registering. It taxes only Spanish-sourced income at the flat rate while foreign income stays taxable abroad — a big plus for remote workers. Opt in via Form 149."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Digital nomad visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-teletrabajo.htm",
            },
        ],
    }


def _spain_dn_income_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Prove monthly income ≥€2 849 (2× SMI 2026) for the main applicant plus €1 069 per dependent, via: 3 months of payslips, a client/employer letter confirming the remote relationship, or tax returns if self-employed. You also need ≥3 months with the current employer OR a solid freelance track record, plus a degree or 3 years' experience. Bank statements and a no-criminal-record certificate round out the package."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Digital nomad visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-teletrabajo.htm",
            },
        ],
    }


def _spain_dn_family_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Yes — family members (spouse/partner, children, dependent parents) can join on the digital nomad visa as dependents. You must show the extra income threshold (€1 069/month per dependent) and relationship proof. Each gets their own residence card. They may generally NOT work in Spain unless they obtain their own work authorization, but they're covered by the family's private health insurance requirement."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Digital nomad visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-teletrabajo.htm",
            },
        ],
    }


def _spain_entrepreneur_endorsement_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Endorsement is via ENISA (public innovation agency), accredited business accelerators, universities, or business-angels networks recognized by the Ministry. They assess innovation, economic/social impact, job creation, and viability. Submit your plan with financials and team CVs; a positive report (informe favorable) fast-tracks the visa. The UGE coordinates the final resolution. Strong R&D or strategic-sector focus improves odds."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Entrepreneur visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-emprendedores.htm",
            },
        ],
    }


def _spain_entrepreneur_investment_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "There's no fixed minimum investment for the entrepreneur visa — the plan's viability matters more than a set euro amount. You must show sufficient own or committed funding to execute it (investors, loans, personal capital). For the related investor residence routes, thresholds differ (e.g. €2M bonds / €1M company shares), but the entrepreneur track judges the project on innovation and impact, not a capital floor. Present realistic financial projections."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Entrepreneur visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-emprendedores.htm",
            },
        ],
    }


def _spain_entrepreneur_fasttrack_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Highly innovative projects get a fast-track residence permit under the Entrepreneur Law (Ley 14/2013): resolution within 20 business days once the business plan is endorsed. The permit is initially 1 year (from the consulate) or 3 years (if applied from Spain), renewable 2+2 years. The UGE handles the whole file end-to-end, cutting inter-department delays for qualifying ventures."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Entrepreneur visa",
                "url": "https://www.inclusion.gob.es/extranjeria/visados/visado-emprendedores.htm",
            },
        ],
    }


def _spain_nie_vs_tie_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The NIE (Número de Identidad de Extranjero) is your tax-identification NUMBER — needed for any legal/financial act, printed on a white A4 certificate for EU citizens (no expiry) and on the TIE for non-EU residents. The TIE (Tarjeta de Identidad de Extranjero) is the physical RESIDENCE CARD non-EU residents carry, showing their permit type and validity. In short: NIE = number (everyone), TIE = card (non-EU residents only)."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — NIE",
                "url": "https://www.inclusion.gob.es/extranjeria/nie.htm",
            },
        ],
    }


def _spain_nie_consulate_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Yes — non-EU citizens can apply for the NIE at a Spanish consulate in their home country before travelling, using the EX-15 form and proof of the purpose (job offer, property purchase, study). EU citizens usually get the NIE automatically when they register as residents in Spain, but can also request it via consulate if needed beforehand. Consulate processing is typically 1–4 weeks."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — NIE",
                "url": "https://www.inclusion.gob.es/extranjeria/nie.htm",
            },
        ],
    }


def _spain_nie_docs_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "At the Oficina de Extranjería in Spain: EX-15 form, valid passport (copy + original), passport photos if a TIE is issued, proof of the reason for the NIE (employment contract, university admission, property deed, or business activity), and the ~€12 fee receipt. EU citizens add their registration certificate; non-EU add their visa/residence permit. Processing 1–4 weeks for non-EU, same-day for EU registration."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — NIE",
                "url": "https://www.inclusion.gob.es/extranjeria/nie.htm",
            },
        ],
    }


def _spain_ehic_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The EHIC covers only NECESSARY healthcare during TEMPORARY stays (tourists/students <3 months) under your home country's system. It does NOT prove residence-level coverage. To register as a resident (or for non-lucrative/digital-nomad/entrepreneur visas) Spain requires either SNS affiliation (if employed) or private insurance with no co-payments, no waiting periods, full Spanish coverage, and repatriation. The EHIC simply doesn't meet that bar."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Social Security — Healthcare",
                "url": "https://www.seg-social.es/wps/portal/wss/internet/AtencionCiudadana/AsistenciaSanitaria",
            },
        ],
    }


def _spain_private_health_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Private health insurance for Spanish residence must: cover ALL risks in Spain, have NO co-payments (sin copagos), NO waiting periods (sin carencia), full territorial coverage, and repatriation. Minimum coverage is generally €30 000. It must be contracted with an insurer authorized in Spain (not travel insurance). Present the policy certificate — consulates and the Extranjería reject policies with co-payments or gaps."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Social Security — Healthcare",
                "url": "https://www.seg-social.es/wps/portal/wss/internet/AtencionCiudadana/AsistenciaSanitaria",
            },
        ],
    }


def _spain_sns_access_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "To use the SNS (Seguridad Social) you need a social-security affiliation number (NASS/AFPS). If employed, your employer affiliates you and deducts contributions; if self-employed, you register and pay autonomo contributions; if a non-working EU resident with the S1 form, you affiliate via your home country's coverage. Then register with your local health centre (Centro de Salud) to get a GP. EU workers' family members are covered under the worker's affiliation."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Spanish Social Security — Healthcare",
                "url": "https://www.seg-social.es/wps/portal/wss/internet/AtencionCiudadana/AsistenciaSanitaria",
            },
        ],
    }


def _spain_blue_shortage_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The reduced Blue Card salary threshold (€33 085.09 in 2026) applies to shortage occupations (ICT, engineering, healthcare professions) listed in Spain's national catalogue. If your role is on it, you qualify for the lower salary and faster processing. The list is maintained by the Ministry and updated for labour-market needs; check the current Catálogo for your occupation before applying."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — EU Blue Card",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/tarjeta-azul-ue.htm",
            },
        ],
    }


def _spain_blue_family_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Blue Card holders in Spain get family reunification with immediate work rights for spouse/partner, children, and dependent parents. You must show sufficient income and housing. Family members receive their own residence cards tied to your permit and may work without a separate authorization. After 5 years (or 2 with B1 Spanish) you can move to permanent EU residence, and family members follow the same timeline."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — EU Blue Card",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/tarjeta-azul-ue.htm",
            },
        ],
    }


def _spain_blue_degree_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "For Spain's Blue Card you need a university degree of 3+ years (or 5+ years' experience equivalent). Have your degree officially recognized: use the Hague Apostille on the certificate and a certified Spanish translation, then submit it with the job contract. For regulated professions, additional colegio recognition may apply. The employer initiates the process at the UGE/Foreigners' Office; processing is 20–30 days."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — EU Blue Card",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/tarjeta-azul-ue.htm",
            },
        ],
    }


def _spain_hq_vs_blue_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Both need a degree + job offer + salary ≥€41 356.36 (2026). Differences: the Blue Card grants EU-wide mobility after 18 months, fast-track permanent residence (5 yrs / 2 with B1 Spanish), and no labour-market test; the Highly Qualified Professional (HQP) permit is Spain-only (no EU mobility), has no fast-track PR, but offers a simpler employer-friendly process. HQP is ideal if you don't need mobility or your salary is near the threshold. HQP is valid 2 years, renewable."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Highly qualified",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/profesionales-cualificados.htm",
            },
        ],
    }


def _spain_hq_match_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The Highly Qualified Professional permit requires the job to match your qualification: a university degree (3+ years) or higher vocational training, and the position must be appropriately skilled for it. A loose match (e.g. a generic degree for a specialist role) can be rejected. The UGE checks that the role is 'qualified' and the salary meets the threshold. Keep your degree certificate and a clear job description handy."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Highly qualified",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/profesionales-cualificados.htm",
            },
        ],
    }


def _spain_hq_renewal_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The HQP permit is valid 2 years and renewable for further 2-year periods while you remain in qualified employment meeting the salary threshold. Apply for renewal before expiry at the UGE or Foreigners' Office with your continued contract, salary proof, and clean record. After 5 years you can switch to the long-term residence permit. The process is employer-supported and typically resolved within a month."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Highly qualified",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena/profesionales-cualificados.htm",
            },
        ],
    }


def _spain_shortage_find_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "Spain's shortage list is the 'Catálogo de Ocupaciones de Difícil Cobertura', published by the Servicio Público de Empleo Estatal (SEPE). Search it on the SEPE website by occupation code to see if your role qualifies for the labour-market-test waiver on work permits and the reduced Blue Card threshold. Employers also check it when filing a work-authorization application. The catalogue is updated periodically, so verify the current version."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "SEPE — Shortage occupations",
                "url": "https://www.sepe.es/HomeSepe/empleo/observatorio-mercado-trabajo/catalogo-ocupaciones-dificil-cobertura.html",
            },
        ],
    }


def _spain_shortage_update_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "The Catálogo de Ocupaciones de Difícil Cobertura is updated by SEPE as labour needs change, typically listing roles employers struggle to fill domestically — common in healthcare (nurses, elder care), IT, engineering, and hospitality. If your profession is listed, the employer's work-authorization faces no labour-market test. Always consult the latest published catalogue, since inclusions shift with the economy."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "SEPE — Shortage occupations",
                "url": "https://www.sepe.es/HomeSepe/empleo/observatorio-mercado-trabajo/catalogo-ocupaciones-dificil-cobertura.html",
            },
        ],
    }


def _spain_shortage_employer_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "When a role is on the shortage catalogue, the employer files a work authorization (Autorización de Trabajo) without the labour-market test — they don't have to prove no suitable EU candidate exists. The employer submits the contract and the occupation code to the Foreigners' Office/UGE; the exemption speeds approval to 1–3 months. This is a key route for non-EU hires in nursing, IT, and engineering. The employee then applies for the visa at the consulate."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Ministry of Inclusion — Work permits",
                "url": "https://www.inclusion.gob.es/extranjeria/trabajo-por-cuenta-ajena.htm",
            },
        ],
    }


def _spain_tax_residency_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "You're a Spanish tax resident if you spend >183 days in Spain in a calendar year (counting sporadic absences, except for treaty-defined tax-home cases), or if your economic centre/principal activities are in Spain. Residents are taxed on WORLDWIDE income at progressive rates (up to 47%); non-residents pay only on Spanish-source income (usually 24%). The 183-day rule is the main test — track your days carefully if you split time."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Agencia Tributaria — Tax residency",
                "url": "https://sede.agenciatributaria.gob.es/",
            },
        ],
    }


def _spain_tax_remote_employee_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "A remote employee working from Spain for an EU employer is still subject to Spanish tax residency if they exceed 183 days, and to Spanish labour/social-security rules for work performed in Spain. EU coordination rules (Regulation 883/2004) determine which state's social security applies — usually where you physically work. Double-tax treaties prevent double taxation. Digital nomads can use the Beckham Law to cap Spanish tax on foreign income at 24%."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Agencia Tributaria — Tax residency",
                "url": "https://sede.agenciatributaria.gob.es/",
            },
        ],
    }


def _spain_tax_selfemployed_guidance() -> ChatGuidance:
    return {
        "reason": "national_law",
        "message": (
            "A self-employed person (autónomo) in Spain is subject to Spanish tax residency (>183 days) and must register with the RETA social-security regime, paying autonomo contributions. EU Regulation 883/2004 allocates social security to where you work. The EU Services Directive eases cross-border provision of services. If you also invoice EU clients, double-tax treaties apply; the Beckham Law can simplify taxation for new residents."
        ),
        "question": "What else would you like to know?",
        "options": [],
        "references": [
            {
                "title": "Agencia Tributaria — Tax residency",
                "url": "https://sede.agenciatributaria.gob.es/",
            },
        ],
    }
