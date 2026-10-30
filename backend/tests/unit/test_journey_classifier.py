"""Unit tests for the JourneyClassifierService."""

from __future__ import annotations

from app.models.journey_classifier import JourneyClassification
from app.services.journey_classifier import JourneyClassifierService


def _classify(message: str, language: str = "en") -> JourneyClassification:
    return JourneyClassifierService().classify(message, language)


# ── Journey type detection ───────────────────────────────────────────────────


def test_classify_work_in_germany_detected() -> None:
    result = _classify("I want to work in Germany as an engineer")
    assert result.journey_type == "work"
    assert result.jurisdiction == "DE"
    assert result.confidence in ("high", "medium")


def test_classify_work_in_germany_german() -> None:
    result = _classify("Ich mochte in Deutschland arbeiten")
    assert result.journey_type == "work"
    assert result.jurisdiction == "DE"


def test_classify_blue_card_detected() -> None:
    result = _classify("How do I get an EU Blue Card for Germany?")
    assert result.journey_type == "work"


def test_classify_relocate_germany_detected() -> None:
    result = _classify("I want to move to Germany. How do I get a residence permit?")
    assert result.journey_type == "relocate"
    assert result.jurisdiction == "DE"


def test_classify_relocate_german() -> None:
    result = _classify("Ich mochte nach Deutschland umziehen, brauche eine Aufenthaltserlaubnis")
    assert result.journey_type == "relocate"


def test_classify_study_germany_detected() -> None:
    result = _classify("I want to study at a German university")
    assert result.journey_type == "study"
    assert result.jurisdiction == "DE"


def test_classify_study_german() -> None:
    result = _classify("Ich mochte in Deutschland studieren")
    assert result.journey_type == "study"


def test_classify_ausbildung_detected() -> None:
    result = _classify("Ich suche eine Ausbildung in Deutschland")
    assert result.journey_type == "study"


def test_classify_maintain_register_detected() -> None:
    result = _classify("How do I register my address in Germany?")
    assert result.journey_type == "maintain"
    assert result.jurisdiction == "DE"


def test_classify_maintain_renew_detected() -> None:
    result = _classify("How do I renew my social security in France?")
    assert result.journey_type == "maintain"
    assert result.jurisdiction == "FR"


def test_classify_maintain_bank_account_detected() -> None:
    result = _classify("How do I open a bank account in Austria?")
    assert result.journey_type == "maintain"
    assert result.jurisdiction == "AT"


def test_classify_maintain_family_detected() -> None:
    result = _classify("I need to change my registered address in Germany")
    assert result.journey_type == "maintain"
    assert result.jurisdiction == "DE"


def test_classify_generic_question_returns_other() -> None:
    result = _classify("What is the EU Charter of Fundamental Rights?")
    assert result.journey_type is None
    assert result.jurisdiction is None


def test_classify_generic_question_french() -> None:
    result = _classify("Qu'est-ce que la Charte des droits fondamentaux de l'UE?")
    assert result.journey_type is None
    assert result.jurisdiction is None


# ── Citizenship detection ────────────────────────────────────────────────────


def test_classify_eu_citizen_detected() -> None:
    result = _classify("I am an EU citizen and want to work in Germany")
    assert result.citizenship_group == "eu_citizen"
    assert result.journey_type == "work"
    assert result.jurisdiction == "DE"


def test_classify_eu_citizen_german() -> None:
    result = _classify("Ich bin EU-Burger und mochte in Deutschland arbeiten")
    assert result.citizenship_group == "eu_citizen"


def test_classify_non_eu_detected() -> None:
    result = _classify("I am a non-EU citizen with a job offer in Germany")
    assert result.citizenship_group == "non_eu"
    assert result.journey_type == "work"


def test_classify_non_eu_third_country() -> None:
    result = _classify("Third-country national seeking residence permit in Germany")
    assert result.citizenship_group == "non_eu"


def test_classify_citizenship_unknown() -> None:
    result = _classify("How do I move to Germany?")
    assert result.citizenship_group == "unknown"


# ── Jurisdiction detection ───────────────────────────────────────────────────


def test_classify_jurisdiction_france() -> None:
    result = _classify("I want to work in France")
    assert result.jurisdiction == "FR"


def test_classify_jurisdiction_french() -> None:
    result = _classify("Je veux travailler en France")
    assert result.jurisdiction == "FR"


def test_classify_jurisdiction_austria() -> None:
    result = _classify("I want to study in Austria")
    assert result.jurisdiction == "AT"
    assert result.journey_type == "study"


def test_classify_jurisdiction_austria_german() -> None:
    result = _classify("Ich mochte in Osterreich studieren")
    assert result.jurisdiction == "AT"


def test_classify_jurisdiction_spain() -> None:
    result = _classify("Move to Spain for work")
    assert result.jurisdiction == "ES"


def test_classify_jurisdiction_switzerland() -> None:
    result = _classify("Work permit in Switzerland")
    assert result.jurisdiction == "CH"


def test_classify_jurisdiction_italy() -> None:
    result = _classify("Residence permit in Italy")
    assert result.jurisdiction == "IT"


def test_classify_jurisdiction_no_match() -> None:
    result = _classify("What are the rules for remote work?")
    assert result.jurisdiction is None


# ── Confidence scoring ───────────────────────────────────────────────────────


def test_confidence_high_all_signals() -> None:
    result = _classify("I am an EU citizen with a job offer in Germany")
    assert result.confidence == "high"
    assert result.journey_type == "work"
    assert result.citizenship_group == "eu_citizen"
    assert result.jurisdiction == "DE"


def test_confidence_medium_two_signals() -> None:
    result = _classify("I want to study at a university in Germany")
    assert result.confidence == "medium"


def test_confidence_low_jurisdiction_only() -> None:
    result = _classify("Tell me about Germany")
    assert result.confidence == "low"
    assert result.jurisdiction == "DE"
    assert result.journey_type is None
    assert result.citizenship_group == "unknown"


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_classify_empty_message() -> None:
    result = _classify("")
    assert result.journey_type is None
    assert result.citizenship_group == "unknown"
    assert result.jurisdiction is None
    assert result.confidence == "low"


def test_classify_whitespace_only() -> None:
    result = _classify("   ")
    assert result.journey_type is None
    assert result.citizenship_group == "unknown"
    assert result.jurisdiction is None


def test_classify_special_characters() -> None:
    result = _classify("!!! How do I get a job in Germany ???")
    assert result.journey_type == "work"
    assert result.jurisdiction == "DE"


def test_classify_case_insensitive() -> None:
    result = _classify("EU CITIZEN MOVING TO GERMANY FOR WORK")
    assert result.citizenship_group == "eu_citizen"
    assert result.journey_type == "work"
    assert result.jurisdiction == "DE"


def test_classify_model_is_frozen() -> None:
    result = _classify("I want to work in Germany")
    assert result.model_config.get("frozen") is True


# ── Language parameter ───────────────────────────────────────────────────────


def test_classify_french_language() -> None:
    result = _classify("Je suis citoyen de l'UE et je veux travailler en Allemagne", language="fr")
    assert result.journey_type == "work"
    assert result.citizenship_group == "eu_citizen"
    assert result.jurisdiction == "DE"
