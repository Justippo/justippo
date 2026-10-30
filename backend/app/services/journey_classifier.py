"""
Journey Classifier Service — Deterministic intent detection from first chat message.

Pipeline position: Chat endpoint → JourneyClassifierService → SSE journey_state_update.

All detection is keyword/regex-based: no LLM call, no network IO, no additional latency.
"""

from __future__ import annotations

import logging
import re
from typing import cast

from app.models.journey_classifier import (
    CitizenshipGroup,
    Confidence,
    JourneyClassification,
    JourneyType,
)

logger = logging.getLogger(__name__)

# ── Jurisdiction mapping ─────────────────────────────────────────────────────
# Mapped countries: Germany, France, Austria, Switzerland, Spain, Italy,
# Netherlands, Belgium, Poland, Sweden, Denmark, Portugal, Ireland.
# Each entry provides lists of English, German, and French triggers.

_JURISDICTION_PATTERNS: dict[str, list[str]] = {
    "DE": [
        r"\bgermany\b",
        r"\bgerman\b",
        r"\bdeutschland\b",
        r"\bdeutsch(?:er|e|en|es)?\b",
        r"\ballemagne\b",
        r"\ballemand\b",
    ],
    "FR": [
        r"\bfrance\b",
        r"\bfrench\b",
        r"\bfrankreich\b",
        r"\bfranz.si(?:sch|sche|scher|sches)\b",
    ],
    "AT": [
        r"\baustria\b",
        r"\baustrian\b",
        r"\b.sterreich\b",
        r"\b.sterreicher\b",
        r"\bautriche\b",
    ],
    "CH": [
        r"\bswitzerland\b",
        r"\bswiss\b",
        r"\bschweiz\b",
        r"\bschweizer\b",
        r"\bsuisse\b",
    ],
    "ES": [
        r"\bspain\b",
        r"\bspanish\b",
        r"\bespaña\b",
        r"\bespanol\b",
        r"\bspanien\b",
        r"\bspanisch\b",
    ],
    "IT": [
        r"\bitaly\b",
        r"\bitalian\b",
        r"\bitalia\b",
        r"\bitalien\b",
        r"\bitalienisch\b",
    ],
}

# Compiled jurisdiction patterns
_COMPILED_JURISDICTION: dict[str, re.Pattern[str]] = {
    code: re.compile("|".join(patterns), re.IGNORECASE)
    for code, patterns in _JURISDICTION_PATTERNS.items()
}


# ── Journey type keyword scoring ─────────────────────────────────────────────

_JOURNEY_KW: dict[JourneyType, list[str]] = {
    "work": [
        "work",
        "job",
        "employment",
        "hired",
        "blue card",
        "employer",
        "employed",
        "arbeiten",
        "arbeit",
        "job",
        "stelle",
        "working",
        "travailler",
        "travail",
    ],
    "relocate": [
        "relocate",
        "move",
        "residence permit",
        "move to",
        "settlement",
        "aufenthalt",
        "umzug",
        "umziehen",
        "permit",
        "migrate",
        "immigrate",
        "immigration",
        "deménager",
        "emménager",
    ],
    "study": [
        "study",
        "student",
        "university",
        "studies",
        "ausbildung",
        "studium",
        "student",
        "studieren",
        "uni",
        "universität",
        "étudier",
        "université",
    ],
    "maintain": [
        "register",
        "registration",
        " anmeldung",
        "enregistrement",
        "renew",
        "renewal",
        "extend",
        "extension",
        "verlängern",
        "verlängerung",
        "renouveler",
        "bank account",
        "bankkonto",
        "compte bancaire",
        "social security",
        "sozialversicherung",
        "sécurité sociale",
        "tax id",
        "steuer-id",
        "numéro fiscal",
        "family reunification",
        "familiennachzug",
        "regroupement familial",
        "change employer",
        "arbeitgeber wechseln",
        "changer d'employeur",
        "address",
        "wohnsitz",
        "domicile",
    ],
    "other": [],  # default — never matched by keyword
}


# ── Citizenship keyword scoring ──────────────────────────────────────────────

# Citizenship keyword patterns as raw regex — non_eu patterns must be checked
# BEFORE eu_citizen patterns since "non-EU" contains "EU" as substring.
# We use a single pass: first check non_eu pattern, then eu_citizen pattern.
_CITIZENSHIP_KW: dict[CitizenshipGroup, list[str]] = {
    "eu_citizen": [
        r"\beuropean union\b",
        r"\beu citizen\b",
        r"\beu member\b",
        r"\beuropean citizen\b",
        r"\beu.bürger\b",
        r"\beu burger\b",
        r"\beu.burger\b",
        r"\bunion.européenne\b",
        r"\bcitoyen.{0,5}ue\b",
        r"\bl'ue\b",
    ],
    "non_eu": [
        r"\bnon.eu\b",
        r"\bnon eu\b",
        r"\bthird.countr",
        r"\boutside the eu\b",
        r"\bnot eu\b",
        r"\bnicht.eu\b",
        r"\bnon european\b",
        r"\bressortissant.pays.tiers\b",
    ],
    "unknown": [],  # default
}

# Compiled journey keyword patterns (case-insensitive word match)
_COMPILED_JOURNEY_KW: dict[str, re.Pattern[str]] = {
    key: re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for key, kws in _JOURNEY_KW.items()
    if kws
}

# Compiled citizenship patterns — raw regex, not re.escape'd
_COMPILED_CITIZENSHIP_KW: dict[str, re.Pattern[str]] = {
    key: re.compile("|".join(kws), re.IGNORECASE) for key, kws in _CITIZENSHIP_KW.items() if kws
}


def _detect_jurisdiction(text: str) -> tuple[str | None, str | None]:
    """Detect jurisdiction from text. Returns (country_code, match_text) or (None, None)."""
    # Priority: return the first matching jurisdiction
    for code, pattern in _COMPILED_JURISDICTION.items():
        match = pattern.search(text)
        if match:
            return code, match.group(0)
    return None, None


_KNOWN_JOURNEY_TYPES: frozenset[str] = frozenset(
    {
        "work",
        "relocate",
        "study",
        "maintain",
    }
)


def _score_journey_type(text: str) -> tuple[JourneyType | None, int]:
    """Score journey types by keyword matches. Returns (best_type, score)."""
    scores: dict[JourneyType, int] = {}
    for jtype, pattern in _COMPILED_JOURNEY_KW.items():
        matches = pattern.findall(text.lower())
        if matches and jtype in _KNOWN_JOURNEY_TYPES:
            scores[cast(JourneyType, jtype)] = len(matches)

    if not scores:
        return None, 0

    best = max(scores, key=scores.__getitem__)
    return best, scores[best]


def _detect_citizenship(text: str) -> CitizenshipGroup:
    """Detect citizenship group from text. Defaults to 'unknown'.

    non_eu is checked FIRST because patterns like "non-EU" contain "EU"
    as a substring; checking non_eu first avoids false eu_citizen matches.
    """
    if _COMPILED_CITIZENSHIP_KW.get("non_eu") and _COMPILED_CITIZENSHIP_KW["non_eu"].search(text):
        return "non_eu"
    if _COMPILED_CITIZENSHIP_KW.get("eu_citizen") and _COMPILED_CITIZENSHIP_KW["eu_citizen"].search(
        text
    ):
        return "eu_citizen"
    return "unknown"


def _compute_confidence(
    jurisdiction_detected: bool,
    journey_type_detected: bool,
    citizenship_detected: bool,
) -> Confidence:
    signals = sum([jurisdiction_detected, journey_type_detected, citizenship_detected])
    if signals >= 3:
        return "high"
    if signals >= 2:
        return "medium"
    return "low"


class JourneyClassifierService:
    """
    Deterministic classifier for journey type, citizenship, and jurisdiction.

    No LLM call, no network IO. Pure keyword/regex matching on the user's
    first chat message.
    """

    def classify(self, message: str, language: str = "en") -> JourneyClassification:
        """
        Classify a user's first message into journey type, citizenship, and jurisdiction.

        Args:
            message: The user's chat message (stripped, max 2000 chars from validation).
            language: ISO 639-1 language code (for future language-specific logic).

        Returns:
            JourneyClassification with detected intent fields.
        """
        text = message.strip()
        if not text:
            return JourneyClassification(
                journey_type=None,
                citizenship_group="unknown",
                jurisdiction=None,
                confidence="low",
            )

        jurisdiction_code, _ = _detect_jurisdiction(text)
        journey_type, journey_score = _score_journey_type(text)
        citizenship = _detect_citizenship(text)

        confidence = _compute_confidence(
            jurisdiction_detected=jurisdiction_code is not None,
            journey_type_detected=journey_type is not None,
            citizenship_detected=citizenship != "unknown",
        )

        return JourneyClassification(
            journey_type=journey_type,
            citizenship_group=citizenship,
            jurisdiction=jurisdiction_code,
            confidence=confidence,
        )
