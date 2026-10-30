"""Grounded explanation of PDF requirements and related EU-law context.

Phase 5 consumes normalized Azure structure but remains independent from the
provider orchestration layer. Requirement extraction is deterministic. Legal
retrieval uses only document type, geography, and field labels; it never sends
field values or the full document as the Hindsight search query. Generated
narrative is allowed only when at least one verified official EU source exists.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from app.integrations.azure_document_intelligence import AzureDocumentAnalysis
from app.integrations.llm.answer_generation import generate_answer
from app.models.document_explanation import (
    DocumentExplanation,
    DocumentRequirement,
    EULawCitation,
)
from app.services.classification_service import DocumentClassification
from app.services.rag_service import (
    _EXPLANATION_GUIDANCE_INSTRUCTION,
    HindsightRAGService,
    build_rag_prompt,
    trusted_eu_source_url,
)

logger = logging.getLogger(__name__)


def _coerce_page_number(value: object) -> int:
    """Return a safe page number from untrusted extracted-page metadata."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def analysis_from_extracted_pages(
    pages: list[dict[str, object]],
) -> AzureDocumentAnalysis:
    """Build the explanation input from already-extracted, ephemeral pages."""
    paragraphs = [
        {
            "content": str(page.get("text", "")),
            "boundingRegions": [{"pageNumber": _coerce_page_number(page.get("page", 0))}],
        }
        for page in pages
        if str(page.get("text", "")).strip()
    ]
    return AzureDocumentAnalysis(
        model_id="extracted-text",
        api_version="local",
        content="\n\n".join(str(paragraph["content"]) for paragraph in paragraphs),
        pages=[{"pageNumber": _coerce_page_number(page.get("page", 0))} for page in pages],
        paragraphs=paragraphs,
    )


_MAX_REQUIREMENTS = 20
_MAX_REQUIREMENT_CHARS = 240
_MAX_QUERY_CHARS = 600
_MAX_QUERY_TERM_CHARS = 80
_MAX_DOCUMENT_EVIDENCE_CHARS = 6000
_MAX_LEGAL_EXCERPT_CHARS = 1200
_MAX_EXPLANATION_CHARS = 2500
_SUPPORTED_LANGUAGES = {"en", "de", "fr"}
_INSTRUCTION_PATTERN = re.compile(
    r"\b(?:must|required|provide|submit|attach|complete|bring|"
    r"muss|müssen|erforderlich|einreichen|vorlegen|beifügen|ausfüllen|"
    r"devez|doit|doivent|requis|fournir|soumettre|joindre|remplir)\b",
    flags=re.IGNORECASE,
)
_LEGAL_QUERY_PREFIX = {
    "en": "EU law requirements rights obligations official source",
    "de": "EU-Recht Anforderungen Rechte Pflichten amtliche Quelle",
    "fr": "droit de l'Union européenne exigences droits obligations source officielle",
}
_SOURCE_REFERENCE_PATTERN = re.compile(r"\[SOURCE\s+(\d+)\]", flags=re.IGNORECASE)

# ── National document type → EU directive keyword mapping ────────────────────
# Many EU member state documents implement EU directives but never mention the
# directive by CELEX number.  When these keywords appear in the document text or
# classification, we inject the corresponding EU directive search terms so
# Hindsight can retrieve the correct official sources.
#
# Keys are lowercased surface forms that may appear in extracted OCR text.
# Values are space-separated search terms that include the directive number,
# its subject matter, and the concept the national document implements.
_EU_DIRECTIVE_KEYWORDS: dict[str, str] = {
    # ── Registration / residence (Directive 2004/38/EC — Citizens' Rights) ───
    # DE
    "meldebescheinigung": "Directive 2004/38 registration certificate free movement residence Anmeldung",
    "anmeldung": "Directive 2004/38 registration certificate free movement residence",
    "wohnsitzanmeldung": "Directive 2004/38 registration certificate free movement residence",
    # EN
    "registration certificate": "Directive 2004/38 registration certificate free movement",
    "certificate of residence": "Directive 2004/38 registration certificate residence",
    "residence registration": "Directive 2004/38 registration certificate free movement",
    # FR
    "attestation d'inscription": "Directive 2004/38 attestation d'inscription résidence libre circulation",
    "certificat de résidence": "Directive 2004/38 certificat de résidence libre circulation",
    "inscription de résidence": "Directive 2004/38 inscription de résidence libre circulation",
    "attestation de domicile": "Directive 2004/38 attestation domicile résidence libre circulation",
    # ── Residence permits (Directive 2004/38/EC + Directive 2003/109/EC) ────
    # DE
    "aufenthaltstitel": "Directive 2004/38 residence permit long-term resident Directive 2003/109",
    "aufenthaltserlaubnis": "Directive 2004/38 residence permit temporary stay",
    "niederlassungserlaubnis": "Directive 2003/109 long-term resident permanent residence",
    # EN
    "residence permit": "Directive 2004/38 residence permit long-term resident Directive 2003/109",
    "permanent residence": "Directive 2003/109 long-term resident permanent residence",
    # FR
    "titre de séjour": "Directive 2004/38 titre de séjour résident longue durée Directive 2003/109",
    "carte de séjour": "Directive 2004/38 carte de séjour résident Directive 2003/109",
    "résident de longue durée": "Directive 2003/109 résident longue durée résidence permanente",
    "séjour permanent": "Directive 2003/109 séjour permanent résident longue durée",
    # ── Employment / posted workers (Directive 96/71/EC + Directive 2018/957/EU)
    # DE
    "arbeitsvertrag": "Directive 96/71 posted workers employment conditions Directive 2018/957",
    "arbeitnehmer": "Directive 96/71 posted workers employee rights Directive 2018/957",
    "entsandter": "Directive 96/71 posted workers employment conditions Directive 2018/957",
    "Arbeitnehmerüberlassung": "Directive 96/71 temporary agency work posting Directive 2018/957",
    # EN
    "employment contract": "Directive 96/71 posted workers employment conditions Directive 2018/957",
    "posted worker": "Directive 96/71 posted workers employment conditions Directive 2018/957",
    # FR
    "contrat de travail": "Directive 96/71 travailleur détaché conditions emploi Directive 2018/957",
    "travailleurs détachés": "Directive 96/71 travailleur détaché conditions emploi Directive 2018/957",
    "détachement de travailleurs": "Directive 96/71 détachement travailleurs conditions emploi Directive 2018/957",
    # ── Social security coordination (Regulation (EC) 883/2004) ─────────────
    # DE
    "sozialversicherung": "Regulation 883/2004 social security coordination entitlements",
    "krankenversicherung": "Regulation 883/2004 social security health insurance coordination",
    # EN
    "social security": "Regulation 883/2004 social security coordination entitlements",
    "health insurance": "Regulation 883/2004 social security health insurance coordination",
    "AHIC": "Regulation 883/2004 European Health Insurance Card social security",
    "European Health Insurance Card": "Regulation 883/2004 EHIC social security coordination",
    # FR
    "sécurité sociale": "Regulation 883/2004 sécurité sociale coordination droits",
    "assurance maladie": "Regulation 883/2004 assurance maladie coordination sécurité sociale",
    "carte européenne d'assurance maladie": "Regulation 883/2004 CEAM sécurité sociale coordination",
    # ── Professional qualifications (Directive 2005/36/EC) ───────────────────
    # DE
    "berufsanerkennung": "Directive 2005/36 professional qualifications recognition",
    "berufsqualifikation": "Directive 2005/36 professional qualifications recognition",
    # EN
    "professional qualification": "Directive 2005/36 professional qualifications recognition",
    "qualification recognition": "Directive 2005/36 professional qualifications recognition",
    # FR
    "reconnaissance des qualifications": "Directive 2005/36 reconnaissance qualifications professionnelles",
    "qualification professionnelle": "Directive 2005/36 qualification professionnelle reconnaissance",
    # ── Family reunification (Directive 2003/86/EC) ─────────────────────────
    # DE
    "familiennachzug": "Directive 2003/86 family reunification right",
    # EN
    "family reunification": "Directive 2003/86 family reunification right",
    # FR
    "regroupement familial": "Directive 2003/86 regroupement familial droit",
    # ── Tax / fiscal documents ──────────────────────────────────────────────
    # DE
    "steuerbescheinigung": "Directive 2003/486 taxation savings income EU coordination",
    # EN
    "tax certificate": "Directive 2003/486 taxation savings income EU coordination",
    # FR
    "attestation fiscale": "Directive 2003/486 imposition épargne revenus coordination européenne",
    "certificat fiscal": "Directive 2003/486 imposition épargne revenus coordination européenne",
    # ── Vehicle registration (Directive 1999/37/EC) ─────────────────────────
    # DE
    "fahrzeugbrief": "Directive 1999/37 vehicle registration documents EU",
    "Zulassungsbescheinigung": "Directive 1999/37 vehicle registration documents EU",
    # EN
    "vehicle registration": "Directive 1999/37 vehicle registration documents EU",
    "vehicle certificate": "Directive 1999/37 vehicle registration documents EU",
    # FR
    "certificat d'immatriculation": "Directive 1999/37 certificat immatriculation véhicule UE",
    "carte grise": "Directive 1999/37 certificat immatriculation véhicule UE",
    # ── Driving licence (Directive 2006/126/EC) ─────────────────────────────
    # DE
    "führerschein": "Directive 2006/126 driving licence EU recognition",
    # EN
    "driving licence": "Directive 2006/126 driving licence EU recognition",
    "driving license": "Directive 2006/126 driving licence EU recognition",
    # FR
    "permis de conduire": "Directive 2006/126 permis de conduire reconnaissance UE",
}


def _bounded_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    return normalized[:limit]


def _page_number(node: object) -> int | None:
    if not isinstance(node, dict):
        return None
    regions = node.get("boundingRegions")
    if not isinstance(regions, list):
        return None
    for region in regions:
        if not isinstance(region, dict):
            continue
        page = region.get("pageNumber")
        if isinstance(page, int) and page > 0:
            return page
    return None


def _key_content(pair: object) -> tuple[str, int | None]:
    if not isinstance(pair, dict):
        return "", None
    key = pair.get("key")
    if not isinstance(key, dict):
        return "", None
    return _bounded_text(key.get("content"), _MAX_REQUIREMENT_CHARS), _page_number(key)


def extract_document_requirements(
    analysis: AzureDocumentAnalysis,
) -> list[DocumentRequirement]:
    """Extract field labels and explicit obligation sentences, never values."""
    requirements: list[DocumentRequirement] = []
    seen: set[str] = set()

    def append(
        text: str,
        kind: Literal["field", "instruction"],
        page_number: int | None,
    ) -> None:
        normalized = text.casefold()
        if not text or normalized in seen or len(requirements) >= _MAX_REQUIREMENTS:
            return
        seen.add(normalized)
        requirements.append(
            DocumentRequirement(
                text=text,
                kind=kind,
                page_number=page_number,
            )
        )

    for pair in analysis.key_value_pairs:
        text, page_number = _key_content(pair)
        append(text, "field", page_number)

    for paragraph in analysis.paragraphs:
        if len(requirements) >= _MAX_REQUIREMENTS:
            break
        text = _bounded_text(paragraph.get("content"), _MAX_REQUIREMENT_CHARS)
        if text and _INSTRUCTION_PATTERN.search(text):
            append(text, "instruction", _page_number(paragraph))

    return requirements


def _query_term(value: object) -> str:
    text = _bounded_text(value, _MAX_QUERY_TERM_CHARS).replace("_", " ")
    # Query terms are metadata/labels only. Remove prompt delimiters and control
    # punctuation while preserving Unicode letters, digits, spaces, and hyphens.
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _detect_directive_keywords(
    analysis: AzureDocumentAnalysis,
    classification: DocumentClassification,
) -> list[str]:
    """Detect national document keywords and return matching EU directive search terms.

    Scans the document content, key-value pair labels, and classification metadata
    for known national document type surface forms.  When a match is found, the
    corresponding EU directive search terms are returned so they can be injected
    into the RAG retrieval query.

    This bridges the gap between national implementation documents (e.g.
    Meldebescheinigung) and the EU directives they implement (e.g. Directive
    2004/38/EC), which is where EUR-Lex citations live.
    """
    searchable_parts: list[str] = []

    # Document content (truncated to avoid scanning huge docs)
    if analysis.content:
        searchable_parts.append(analysis.content[:_MAX_QUERY_CHARS])

    # Key-value pair labels
    for pair in analysis.key_value_pairs[:12]:
        key_text, _ = _key_content(pair)
        if key_text:
            searchable_parts.append(key_text)

    # Classification metadata
    if classification.document_type:
        searchable_parts.append(classification.document_type)
    for geo in classification.geographic_relevance[:5]:
        searchable_parts.append(geo)

    combined = " ".join(searchable_parts).casefold()

    matched_directives: list[str] = []
    seen_terms: set[str] = set()
    for keyword, directive_terms in _EU_DIRECTIVE_KEYWORDS.items():
        if keyword in combined and directive_terms not in seen_terms:
            matched_directives.append(directive_terms)
            seen_terms.add(directive_terms)

    return matched_directives


def build_legal_retrieval_query(
    analysis: AzureDocumentAnalysis,
    classification: DocumentClassification,
    language: str,
) -> str:
    """Build a bounded retrieval query without document prose or field values."""
    resolved_language = language if language in _SUPPORTED_LANGUAGES else "en"
    terms: list[str] = [_LEGAL_QUERY_PREFIX[resolved_language]]

    document_type = _query_term(classification.document_type)
    if document_type and document_type != "unknown":
        terms.append(document_type)

    for geography in classification.geographic_relevance[:5]:
        term = _query_term(geography)
        if term:
            terms.append(term)

    for pair in analysis.key_value_pairs[:12]:
        key, _ = _key_content(pair)
        term = _query_term(key)
        if term:
            terms.append(term)

    # Inject EU directive keywords when national document types are detected.
    # This bridges national implementation documents to their EUR-Lex sources.
    directive_terms = _detect_directive_keywords(analysis, classification)
    for directive_term in directive_terms:
        terms.append(directive_term)

    deduplicated = list(dict.fromkeys(term.casefold() for term in terms))
    return " ".join(deduplicated)[:_MAX_QUERY_CHARS].strip()


def _official_citations(
    results: list[dict[str, Any]],
    language: str,
) -> tuple[list[EULawCitation], list[dict[str, Any]]]:
    citations: list[EULawCitation] = []
    prompt_chunks: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for result in results:
        url = trusted_eu_source_url(result.get("source_url"))
        excerpt = _bounded_text(result.get("text"), _MAX_LEGAL_EXCERPT_CHARS)
        if not url or not excerpt or url in seen_urls:
            continue
        seen_urls.add(url)
        title = _bounded_text(
            result.get("source_title") or result.get("document_id") or "Official EU source",
            200,
        )
        source_number = len(citations) + 1
        citations.append(
            EULawCitation(
                source_number=source_number,
                title=title,
                url=url,
                excerpt=excerpt,
                language=_bounded_text(result.get("source_language"), 8) or language,
                document_id=_bounded_text(result.get("document_id"), 100) or None,
            )
        )
        prompt_chunks.append(
            {
                "text": excerpt,
                "source_title": title,
                "document_id": result.get("document_id"),
            }
        )

    return citations, prompt_chunks


def _document_evidence(
    analysis: AzureDocumentAnalysis,
    requirements: list[DocumentRequirement],
) -> str:
    requirement_lines = [f"- {requirement.text}" for requirement in requirements]
    content = analysis.content.strip()[:_MAX_DOCUMENT_EVIDENCE_CHARS]
    parts = []
    if requirement_lines:
        parts.append("Extracted stated requirements:\n" + "\n".join(requirement_lines))
    if content:
        parts.append("Uploaded document text:\n" + content)
    return "\n\n".join(parts)[:_MAX_DOCUMENT_EVIDENCE_CHARS]


def _explanation_question(language: str, document_source_number: int) -> str:
    return (
        "Using the official EU sources above, explain the relevant EU directives and regulations "
        f"that apply to the type of document shown in Source {document_source_number}. "
        "Focus on: (1) what the EU directives require or establish, (2) the purpose of the "
        "uploaded document in the context of those directives, and (3) cite each official "
        "source as [SOURCE N]. "
        "Do not reference any personal data (names, addresses, dates, or specific values) "
        "found in the uploaded document. "
        "If the retrieved context is insufficient to identify applicable EU law, say so explicitly. "
        f"Respond in {language}."
    )


async def explain_document(
    analysis: AzureDocumentAnalysis,
    classification: DocumentClassification,
    *,
    language: str | None = None,
    rag_service: HindsightRAGService | None = None,
    answer_generator: Callable[[str], Awaitable[Any]] | None = None,
    top_k: int = 5,
) -> DocumentExplanation:
    """Return stated requirements plus citation-grounded EU-law context."""
    resolved_language = language or classification.language_code
    if resolved_language not in _SUPPORTED_LANGUAGES:
        resolved_language = "en"
    requirements = extract_document_requirements(analysis)
    query = build_legal_retrieval_query(analysis, classification, resolved_language)
    rag = rag_service or HindsightRAGService()

    # Log the query being built for debugging
    logger.info(
        "Building legal retrieval query: type=%s lang=%s query_preview=%.100s",
        classification.document_type,
        resolved_language,
        query,
    )

    try:
        results = await rag.query(q=query, top_k=top_k, lang=resolved_language)
        logger.info("Legal retrieval returned %d results", len(results) if results else 0)
    except Exception as exc:
        logger.warning(
            "Document legal-context retrieval failed: %s: %s",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        return DocumentExplanation(
            document_type=classification.document_type,
            language=resolved_language,
            requirements=requirements,
            legal_context_status="unavailable",
            citations=[],
            warnings=["LEGAL_RETRIEVAL_UNAVAILABLE"],
        )

    if not isinstance(results, list):
        results = []

    citations, prompt_chunks = _official_citations(results, resolved_language)
    if not citations:
        return DocumentExplanation(
            document_type=classification.document_type,
            language=resolved_language,
            requirements=requirements,
            legal_context_status="not_found",
            citations=[],
            warnings=["NO_VERIFIED_EU_LAW_SOURCE"],
        )

    document_evidence = _document_evidence(analysis, requirements)
    document_source_number = len(prompt_chunks) + 1
    prompt_chunks.append(
        {
            "text": document_evidence or "No readable document evidence was extracted.",
            "source_title": "Uploaded document (user-provided; not legal authority)",
            "document_id": "uploaded-document",
        }
    )
    prompt = build_rag_prompt(
        _explanation_question(resolved_language, document_source_number),
        prompt_chunks,
        guidance=True,
        guidance_instruction=_EXPLANATION_GUIDANCE_INSTRUCTION,
    )
    generator = answer_generator or generate_answer

    try:
        generated = await generator(prompt)
    except Exception:
        logger.warning("Grounded document explanation generation failed", exc_info=False)
        generated = None

    explanation = getattr(generated, "answer", None) if generated is not None else None
    if not isinstance(explanation, str) or not explanation.strip():
        return DocumentExplanation(
            document_type=classification.document_type,
            language=resolved_language,
            requirements=requirements,
            legal_context_status="sources_only",
            citations=citations,
            warnings=["EXPLANATION_GENERATION_UNAVAILABLE"],
        )

    explanation = explanation.strip()

    cited_numbers = {int(match) for match in _SOURCE_REFERENCE_PATTERN.findall(explanation)}
    official_source_numbers = set(range(1, len(citations) + 1))
    if not cited_numbers.intersection(official_source_numbers) or any(
        source_number < 1 or source_number > document_source_number
        for source_number in cited_numbers
    ):
        return DocumentExplanation(
            document_type=classification.document_type,
            language=resolved_language,
            requirements=requirements,
            legal_context_status="sources_only",
            citations=citations,
            warnings=["GENERATED_CITATIONS_UNVERIFIED"],
        )

    if len(explanation) > _MAX_EXPLANATION_CHARS:
        explanation = explanation[:_MAX_EXPLANATION_CHARS].rsplit(" ", 1)[0]

    return DocumentExplanation(
        document_type=classification.document_type,
        language=resolved_language,
        requirements=requirements,
        explanation=explanation,
        legal_context_status="grounded",
        citations=citations,
    )
