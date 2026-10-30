"""
Country-specific content overrides for journey steps.

Provides jurisdiction-aware document names, descriptions, and authority
information that supplement the generic step metadata in chat.py.

Usage in chat endpoint:
    from app.services.journey_content import get_step_documents, get_authority_info
    docs = get_step_documents("check_language", jurisdiction="DE")
    authority = get_authority_info("DE")
"""

from __future__ import annotations

from app.models.journey_events import DocumentItem

# ── Authority / responsible office per jurisdiction ──────────────────────────

_AUTHORITY_INFO: dict[str, dict[str, str]] = {
    "DE": {
        "name": "Ausländerbehörde",
        "english_name": "Foreigners' Registration Office",
        "url": "https://www.bamf.de/EN/Themen/MigrationAufenthalt/ZuwsachsZuwsachs-node.html",
    },
    "FR": {
        "name": "Préfecture",
        "english_name": "Prefecture (local immigration office)",
        "url": "https://www.service-public.fr/particuliers/vosdroits/N106",
    },
    "AT": {
        "name": "Magistrat / Fremdenpolizei",
        "english_name": "Immigration Police (municipal authority)",
        "url": "https://www.oesterreich.gv.at/en/themen/leben-in-oesterreich-aufenthalt-und-einreise.html",
    },
    "CH": {
        "name": "Migrationsamt",
        "english_name": "State Migration Office (cantonal)",
        "url": "https://www.sem.admin.ch/sem/en/home.html",
    },
    "ES": {
        "name": "Oficina de Extranjería",
        "english_name": "Immigration Office",
        "url": "https://www.inclusion.gob.es/es/detalle/extranjeria",
    },
    "IT": {
        "name": "Questura",
        "english_name": "Immigration Office (police headquarters)",
        "url": "https://www.interno.it/it/servizi-immigrazione",
    },
}


# ── Country-specific document overrides per (step_id, jurisdiction) ──────────
# When a jurisdiction entry exists for a step, it REPLACES the default docs.
# When absent, the generic default docs from chat.py are used.

_STEP_DOCS_OVERRIDES: dict[str, dict[str, list[DocumentItem]]] = {
    "check_language": {
        "DE": [
            DocumentItem(
                name="German language certificate",
                description="Goethe-Zertifikat, TestDaF, or telc (typically B1 or B2)",
                required=True,
            ),
        ],
        "FR": [
            DocumentItem(
                name="French language certificate",
                description="DELF, DELF B2, or TCF (typically B1 or B2)",
                required=True,
            ),
        ],
        "AT": [
            DocumentItem(
                name="German language certificate",
                description="ÖSD, Goethe-Zertifikat, or telc (typically A1 or B1 depending on permit)",
                required=True,
            ),
        ],
        "CH": [
            DocumentItem(
                name="German / French / Italian language certificate",
                description="Depends on canton: Goethe (DE), DELF (FR), or CILS (IT)",
                required=True,
            ),
        ],
        "ES": [
            DocumentItem(
                name="Spanish language certificate",
                description="DELE or SIELE certificate (typically A2 or B1)",
                required=True,
            ),
        ],
        "IT": [
            DocumentItem(
                name="Italian language certificate",
                description="CILS, PLIDA, or Roma Tre certificate (typically A2 or B1)",
                required=True,
            ),
        ],
    },
    "check_permit_type": {
        "DE": [
            DocumentItem(
                name="Employment contract",
                description="Signed contract from your German employer",
                required=True,
            ),
        ],
        "FR": [
            DocumentItem(
                name="Employment contract or promise",
                description="Signed CDI/CDD contract or promesse d'embauche from a French employer",
                required=True,
            ),
        ],
        "AT": [
            DocumentItem(
                name="Employment contract",
                description="Signed contract from your Austrian employer (Rot-Weiß-Rot Karte)",
                required=True,
            ),
        ],
        "CH": [
            DocumentItem(
                name="Employment contract",
                description="Signed contract from your Swiss employer (B-permit or L-permit)",
                required=True,
            ),
        ],
        "ES": [
            DocumentItem(
                name="Employment contract",
                description="Signed contract from your Spanish employer",
                required=True,
            ),
        ],
        "IT": [
            DocumentItem(
                name="Employment contract",
                description="Signed contract from your Italian employer (Nulla Osta)",
                required=True,
            ),
        ],
    },
    "check_documents": {
        "DE": [
            DocumentItem(
                name="Completed application forms",
                description="Official forms for your specific permit type (Antrag auf Aufenthaltserlaubnis)",
                required=True,
            ),
            DocumentItem(
                name="Recent biometric photos",
                description="Passport-style photos meeting German visa specifications",
                required=True,
            ),
        ],
        "FR": [
            DocumentItem(
                name="Completed application forms",
                description="CERFA forms relevant to your permit type",
                required=True,
            ),
            DocumentItem(
                name="Recent identity photos",
                description="Photos meeting French identity document specifications",
                required=True,
            ),
        ],
        "AT": [
            DocumentItem(
                name="Completed application forms",
                description="Formular 'Antrag auf Erteilung eines Aufenthaltstitels'",
                required=True,
            ),
            DocumentItem(
                name="Recent biometric photos",
                description="Passport-style photos meeting Austrian specifications",
                required=True,
            ),
        ],
        "CH": [
            DocumentItem(
                name="Completed application forms",
                description="Cantonal migration office application form",
                required=True,
            ),
            DocumentItem(
                name="Biometric photos",
                description="Photos meeting Swiss identity document specifications",
                required=True,
            ),
        ],
        "ES": [
            DocumentItem(
                name="Completed application forms",
                description="EX-15 or EX-18 form (depending on permit type)",
                required=True,
            ),
            DocumentItem(
                name="Tasa 790-052 payment receipt",
                description="Proof of payment of the immigration fee",
                required=True,
            ),
        ],
        "IT": [
            DocumentItem(
                name="Completed application forms",
                description="Nulla Osta application and kit mail forms",
                required=True,
            ),
            DocumentItem(
                name="Recent passport-style photos",
                description="Photos meeting Italian document specifications",
                required=True,
            ),
        ],
    },
    "check_financial": {
        "DE": [
            DocumentItem(
                name="Bank statements or blocked account (Sperrkonto)",
                description="Proof of sufficient financial resources (approx. EUR 11,208/year for students)",
                required=True,
            ),
        ],
        "FR": [
            DocumentItem(
                name="Bank statements",
                description="Proof of sufficient financial resources (approx. EUR 615/month for students)",
                required=True,
            ),
        ],
        "AT": [
            DocumentItem(
                name="Bank statements or commitment letter",
                description="Proof of sufficient financial resources (approx. EUR 10,000/year for students)",
                required=True,
            ),
        ],
        "CH": [
            DocumentItem(
                name="Bank statements",
                description="Proof of sufficient financial resources (varies by canton)",
                required=True,
            ),
        ],
        "ES": [
            DocumentItem(
                name="Bank statements",
                description="Proof of sufficient financial resources (approx. EUR 2,151/month for non-workers)",
                required=True,
            ),
        ],
        "IT": [
            DocumentItem(
                name="Bank statements or sponsorship letter",
                description="Proof of sufficient financial resources (approx. EUR 450/month)",
                required=True,
            ),
        ],
    },
    "check_health_insurance": {
        "DE": [
            DocumentItem(
                name="Health insurance certificate",
                description="Proof of statutory (gesetzliche) or private health insurance in Germany",
                required=True,
            ),
        ],
        "FR": [
            DocumentItem(
                name="Health insurance proof",
                description="Coverage via employer, PUMA, or private insurance accepted in France",
                required=True,
            ),
        ],
        "AT": [
            DocumentItem(
                name="Health insurance certificate",
                description="Proof of Austrian social insurance or equivalent private coverage",
                required=True,
            ),
        ],
        "CH": [
            DocumentItem(
                name="Health insurance confirmation",
                description="Proof of Swiss health insurance (Grundversicherung) within 3 months of arrival",
                required=True,
            ),
        ],
        "ES": [
            DocumentItem(
                name="Health insurance certificate",
                description="Proof of public or private health insurance accepted in Spain",
                required=True,
            ),
        ],
        "IT": [
            DocumentItem(
                name="Health insurance certificate",
                description="Proof of Italian SSN registration or private coverage",
                required=True,
            ),
        ],
    },
}


def get_step_documents(step_id: str, jurisdiction: str | None = None) -> list[DocumentItem] | None:
    """Return country-specific documents for a step, or None if no override exists.

    When jurisdiction is None or has no override, returns None so the caller
    falls back to the generic default documents.
    """
    if jurisdiction is None:
        return None
    overrides = _STEP_DOCS_OVERRIDES.get(step_id, {})
    return overrides.get(jurisdiction)


def get_authority_info(jurisdiction: str | None) -> dict[str, str] | None:
    """Return authority/office info for a jurisdiction, or None if unknown."""
    if jurisdiction is None:
        return None
    return _AUTHORITY_INFO.get(jurisdiction)


def get_supported_jurisdictions() -> list[str]:
    """Return list of jurisdiction codes with full content overrides."""
    return sorted(_AUTHORITY_INFO.keys())
