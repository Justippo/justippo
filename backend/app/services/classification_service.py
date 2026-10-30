# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Document Classification Service — propella-1-0.6B sidecar integration.

Pipeline position: Upload → OCR → classification → metadata enrichment → RAG.
All processing is in-memory and optional; failures degrade to a deterministic
fallback so document upload never blocks on the classifier.

Prompt and JSON schema derived from upstream propella.py (ellamind/propella-1-0.6b,
Apache-2.0). Country relevance uses string arrays instead of the 249-value ISO enum
to keep the schema compact for llguidance constrained decoding.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.lang_detect import detect_language
from app.integrations.cloudflare.gateway import get_gateway_auth_headers, get_gateway_url

logger = logging.getLogger(__name__)

_PROPELLA_TIMEOUT_SECONDS = 5.0
_PROPELLA_MODEL = "ellamind/propella-1-0.6b"

# ── Upstream SYSTEM_PROMPT (propella.py) ─────────────────────────────────────
# Lists all 18 properties with exact enum values for constrained decoding.
_SYSTEM_PROMPT = """Annotate the document. Any language; assess quality within its linguistic norms. Respond with a JSON object:
content_integrity: technical completeness (complete|mostly_complete|fragment|severely_degraded)
content_ratio: content vs navigation/boilerplate ratio (complete_content|mostly_content|mixed_content|mostly_navigation|minimal_content)
content_length: substantive words (substantial 2k+|moderate 500-2k|brief 100-500|minimal <100)
one_sentence_description: neutral ~10 word summary in English
content_type[]: functional purpose (analytical|instructional|reference|procedural|qa_structured|conversational|creative|transactional|boilerplate|news_report|opinion_editorial|review_critique|technical_documentation|specification_standard|legal_document|press_release|structured_data|source_code)
business_sector[]: industry domain (academic_research|education_sector|technology_software|hardware_electronics|healthcare_medical|pharmaceutical_biotech|financial_services|legal_services|government_public|manufacturing_industrial|mining_resources|chemicals_materials|energy_utilities|retail_commerce|wholesale_distribution|real_estate_construction|transportation_logistics|automotive_industry|telecommunications|media_entertainment|advertising_marketing|hospitality_tourism|agriculture_food|environmental_services|aerospace_defense|insurance_industry|nonprofit_ngo|consulting_professional|human_resources|security_cyber|gaming_industry|gambling_betting|travel_aviation|food_beverage_hospitality|consumer_goods|general_interest|other)
technical_content[]: specialized knowledge (code_heavy|math_heavy|scientific|data_heavy|engineering|basic_technical|non_technical)
content_quality: writing/presentation quality (excellent|good|adequate|poor|unacceptable)
information_density: signal vs padding (dense|adequate|moderate|thin|empty)
educational_value: teaching potential (high|moderate|basic|minimal|none)
reasoning_indicators: logical analysis depth (analytical|explanatory|basic_reasoning|minimal|none)
audience_level: assumed background (expert|advanced|general|beginner|youth|children)
commercial_bias: promotional influence (none|minimal|moderate|heavy|pure_marketing)
time_sensitivity: temporal decay (evergreen|slowly_changing|regularly_updating|time_sensitive)
content_safety: harmful content (safe|mild_concerns|nsfw|harmful|illegal)
pii_presence: private individual data (no_pii|contains_pii)
regional_relevance[]: geographic/cultural context (european|north_american|east_asian|south_asian|southeast_asian|middle_eastern|sub_saharan_african|latin_american|oceanian|central_asian|russian_sphere|global|culturally_neutral|indeterminate)
country_relevance[]: specific countries as ISO names, or supranational|none
"""

# ── JSON Schema for llguidance constrained decoding ──────────────────────────
# Derived from propella.py get_annotation_response_schema(flatten=True,
# use_country_enum=False). Country relevance uses free-form strings instead of
# the 249-value ISO enum to keep the schema compact.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_integrity": {
            "type": "string",
            "enum": ["complete", "mostly_complete", "fragment", "severely_degraded"],
        },
        "content_ratio": {
            "type": "string",
            "enum": [
                "complete_content",
                "mostly_content",
                "mixed_content",
                "mostly_navigation",
                "minimal_content",
            ],
        },
        "content_length": {
            "type": "string",
            "enum": ["substantial", "moderate", "brief", "minimal"],
        },
        "one_sentence_description": {"type": "string", "maxLength": 200},
        "content_type": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "analytical",
                    "instructional",
                    "reference",
                    "procedural",
                    "qa_structured",
                    "conversational",
                    "creative",
                    "transactional",
                    "boilerplate",
                    "news_report",
                    "opinion_editorial",
                    "review_critique",
                    "technical_documentation",
                    "specification_standard",
                    "legal_document",
                    "press_release",
                    "structured_data",
                    "source_code",
                ],
            },
            "minItems": 1,
            "maxItems": 5,
        },
        "business_sector": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "academic_research",
                    "education_sector",
                    "technology_software",
                    "hardware_electronics",
                    "healthcare_medical",
                    "pharmaceutical_biotech",
                    "financial_services",
                    "legal_services",
                    "government_public",
                    "manufacturing_industrial",
                    "mining_resources",
                    "chemicals_materials",
                    "energy_utilities",
                    "retail_commerce",
                    "wholesale_distribution",
                    "real_estate_construction",
                    "transportation_logistics",
                    "automotive_industry",
                    "telecommunications",
                    "media_entertainment",
                    "advertising_marketing",
                    "hospitality_tourism",
                    "agriculture_food",
                    "environmental_services",
                    "aerospace_defense",
                    "insurance_industry",
                    "nonprofit_ngo",
                    "consulting_professional",
                    "human_resources",
                    "security_cyber",
                    "gaming_industry",
                    "gambling_betting",
                    "travel_aviation",
                    "food_beverage_hospitality",
                    "consumer_goods",
                    "general_interest",
                    "other",
                ],
            },
            "minItems": 1,
            "maxItems": 10,
        },
        "technical_content": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "code_heavy",
                    "math_heavy",
                    "scientific",
                    "data_heavy",
                    "engineering",
                    "basic_technical",
                    "non_technical",
                ],
            },
            "minItems": 1,
        },
        "information_density": {
            "type": "string",
            "enum": ["dense", "adequate", "moderate", "thin", "empty"],
        },
        "content_quality": {
            "type": "string",
            "enum": ["excellent", "good", "adequate", "poor", "unacceptable"],
        },
        "educational_value": {
            "type": "string",
            "enum": ["high", "moderate", "basic", "minimal", "none"],
        },
        "reasoning_indicators": {
            "type": "string",
            "enum": ["analytical", "explanatory", "basic_reasoning", "minimal", "none"],
        },
        "audience_level": {
            "type": "string",
            "enum": ["expert", "advanced", "general", "beginner", "youth", "children"],
        },
        "commercial_bias": {
            "type": "string",
            "enum": ["none", "minimal", "moderate", "heavy", "pure_marketing"],
        },
        "time_sensitivity": {
            "type": "string",
            "enum": ["evergreen", "slowly_changing", "regularly_updating", "time_sensitive"],
        },
        "content_safety": {
            "type": "string",
            "enum": ["safe", "mild_concerns", "nsfw", "harmful", "illegal"],
        },
        "pii_presence": {
            "type": "string",
            "enum": ["no_pii", "contains_pii"],
        },
        "regional_relevance": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "european",
                    "north_american",
                    "east_asian",
                    "south_asian",
                    "southeast_asian",
                    "middle_eastern",
                    "sub_saharan_african",
                    "latin_american",
                    "oceanian",
                    "central_asian",
                    "russian_sphere",
                    "global",
                    "culturally_neutral",
                    "indeterminate",
                ],
            },
            "minItems": 1,
            "maxItems": 3,
        },
        "country_relevance": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 10,
        },
    },
    "required": [
        "content_integrity",
        "content_ratio",
        "content_length",
        "one_sentence_description",
        "content_type",
        "business_sector",
        "technical_content",
        "information_density",
        "content_quality",
        "educational_value",
        "reasoning_indicators",
        "audience_level",
        "commercial_bias",
        "time_sensitivity",
        "content_safety",
        "pii_presence",
        "regional_relevance",
        "country_relevance",
    ],
    "additionalProperties": False,
    "x-guidance": {"whitespace_flexible": False},
}


class DocumentClassification(BaseModel):
    """EvidenceEU subset of propella-1 annotations used by upload/RAG metadata."""

    document_type: str = "unknown"
    language_code: str = "und"
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    geographic_relevance: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _settings_bool(name: str, default: bool) -> bool:
    return bool(getattr(settings, name, default))


def _settings_str(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _detect_language_fallback(text: str) -> str:
    """Tiny dependency-free EN/DE/FR fallback for disabled/unavailable propella."""
    return detect_language(text)


def default_classification(text: str = "") -> DocumentClassification:
    """Return a sensible non-null default used for graceful degradation."""
    words = len(re.findall(r"\w+", text, flags=re.UNICODE))
    quality = 0.2 if words < 20 else 0.5
    return DocumentClassification(
        document_type="unknown",
        language_code=_detect_language_fallback(text),
        quality_score=quality,
        geographic_relevance=[],
        safety_flags=[],
        confidence=0.0,
    )


def _quality_to_score(data: dict[str, Any]) -> float:
    quality = str(data.get("content_quality", "")).lower()
    integrity = str(data.get("content_integrity", "")).lower()
    mapping = {"excellent": 1.0, "good": 0.85, "adequate": 0.65, "poor": 0.35, "unacceptable": 0.1}
    score = mapping.get(quality, 0.5)
    if integrity in {"fragment", "severely_degraded"}:
        score = min(score, 0.35 if integrity == "fragment" else 0.15)
    return max(0.0, min(1.0, float(score)))


def _language_from_response(data: dict[str, Any], text: str) -> str:
    for key in ("language_code", "language", "detected_language"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()[:2]
    return _detect_language_fallback(text)


def _map_response(data: dict[str, Any], text: str) -> DocumentClassification:
    content_type = data.get("content_type") or data.get("document_type") or []
    if isinstance(content_type, str):
        document_type = content_type
    elif isinstance(content_type, list) and content_type:
        document_type = str(content_type[0])
    else:
        document_type = "unknown"

    geography: list[str] = []
    for key in ("regional_relevance", "country_relevance", "geographic_relevance"):
        value = data.get(key, [])
        if isinstance(value, str):
            geography.append(value)
        elif isinstance(value, list):
            geography.extend(str(item) for item in value if item)

    safety_flags: list[str] = []
    content_safety = str(data.get("content_safety", "safe"))
    pii_presence = str(data.get("pii_presence", "no_pii"))
    if content_safety and content_safety != "safe":
        safety_flags.append(content_safety)
    if pii_presence == "contains_pii":
        safety_flags.append("contains_pii")

    confidence = data.get("confidence", data.get("annotation_confidence", 0.8))
    return DocumentClassification(
        document_type=document_type,
        language_code=_language_from_response(data, text),
        quality_score=_quality_to_score(data),
        geographic_relevance=sorted(set(geography)),
        safety_flags=sorted(set(safety_flags)),
        confidence=max(0.0, min(1.0, float(confidence or 0.0))),
    )


async def classify_document(text: str, mime_type: str) -> DocumentClassification:
    """Classify OCR text with propella-1, falling back safely on disable/failure."""
    if not _settings_bool("PROPELLA_ENABLED", True):
        return default_classification(text)

    if not text.strip():
        return default_classification(text)

    payload = {
        "model": _PROPELLA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"<start_of_document>\n{text[:50000]}\n<end_of_document>"},
        ],
        "mime_type": mime_type,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "AnnotationResponse",
                "schema": _RESPONSE_SCHEMA,
                "strict": True,
            },
        },
        "temperature": 0,
    }

    base_url = _settings_str("PROPELLA_BASE_URL")
    if base_url:
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        headers: dict[str, str] = {}
    else:
        # Dead code: propella-1 is not in CF Workers AI catalog.
        # Kept for future compatibility — uncomment when catalogued.
        url = get_gateway_url("workers-ai", _PROPELLA_MODEL)
        headers = get_gateway_auth_headers()

    try:
        async with httpx.AsyncClient(timeout=_PROPELLA_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        raw = response.json()
        if "choices" in raw:
            content = raw["choices"][0]["message"]["content"]
            data = json.loads(content) if isinstance(content, str) else content
        else:
            data = raw
        if not isinstance(data, dict):
            raise ValueError("propella response was not a JSON object")
        return _map_response(data, text)
    except Exception as exc:
        logger.warning(
            "propella classification failed; using fallback (%s: %s)", type(exc).__name__, exc
        )
        return default_classification(text)
