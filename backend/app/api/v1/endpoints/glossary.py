# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Glossary Endpoint — domain glossary lookup and search.

Responsibilities:
- Expose glossary term lookup for the legal domain
- Support search by query string or full listing when no query is provided
- Read through the D1-backed glossary repository when available
- Gracefully degrade to an empty result set when D1 is unavailable
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.db.d1_client import D1Client
from app.models.glossary import GlossaryTermRead, parse_mistranslations
from app.repositories.glossary_repo import GlossaryRepo
from app.services.glossary_service import extract_terms, insert_terms

router = APIRouter()


class GlossaryLookupResponse(BaseModel):
    domain: str
    source: str | None = None
    target: str | None = None
    query: str | None = None
    count: int
    terms: list[GlossaryTermRead] = Field(default_factory=list)


class GlossaryExtractRequest(BaseModel):
    text: str
    source_lang: str
    doc_id: str | None = None
    persist: bool = True


class GlossaryExtractedTerm(BaseModel):
    term_en: str
    term_de: str
    term_fr: str
    definition: str
    source_lang: str | None = None
    confidence: float = 1.0


class GlossaryExtractResponse(BaseModel):
    source_lang: str
    extracted_count: int
    persisted_count: int
    terms: list[GlossaryExtractedTerm] = Field(default_factory=list)


def _to_read_model(term: object) -> GlossaryTermRead:
    return GlossaryTermRead(
        id=str(getattr(term, "id", "")),
        term_en=str(getattr(term, "term_en", "")),
        term_de=str(getattr(term, "term_de", "")),
        term_fr=str(getattr(term, "term_fr", "")),
        mistranslations=parse_mistranslations(term),
        definition=str(getattr(term, "definition", "")),
        source_lang=getattr(term, "source_lang", None),
        created_at=str(getattr(term, "created_at", "")),
        updated_at=str(getattr(term, "updated_at", "")),
    )


async def _lookup_terms(
    request: Request,
    domain: str,
    source: str | None,
    target: str | None,
    q: str | None,
    limit: int,
) -> GlossaryLookupResponse:
    if domain.lower().strip() != "legal":
        raise HTTPException(
            status_code=422, detail="Only the 'legal' glossary domain is available in MVP."
        )

    if source is not None:
        source = source.lower().strip()
        if source not in {"en", "de", "fr"}:
            raise HTTPException(status_code=422, detail="source must be en, de, or fr")

    if target is not None:
        target = target.lower().strip()
        if target not in {"en", "de", "fr"}:
            raise HTTPException(status_code=422, detail="target must be en, de, or fr")

    repo = GlossaryRepo(D1Client.from_scope(request.scope))
    if q and q.strip():
        records = await repo.search_terms(q.strip(), lang=source)
    else:
        records = await repo.get_all_terms(lang=source)

    terms = [_to_read_model(term) for term in records[:limit]]

    if q and q.strip():
        from app.integrations.posthog import get_client as _get_ph  # noqa: PLC0415

        if ph := _get_ph():
            ph.capture(
                "glossary_searched",
                properties={
                    "domain": domain.lower().strip(),
                    "language": source,
                    "result_count": len(terms),
                },
            )

    return GlossaryLookupResponse(
        domain=domain.lower().strip(),
        source=source,
        target=target,
        query=q.strip() if q else None,
        count=len(terms),
        terms=terms,
    )


@router.get("/", response_model=GlossaryLookupResponse)
async def lookup_glossary(
    request: Request,
    domain: str = Query("legal", description="Glossary domain; only 'legal' is supported in MVP"),
    source: str | None = Query(None, description="Optional source language filter (en, de, fr)"),
    target: str | None = Query(None, description="Optional target language hint (en, de, fr)"),
    q: str | None = Query(None, description="Optional search query"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of terms to return"),
) -> GlossaryLookupResponse:
    return await _lookup_terms(request, domain, source, target, q, limit)


@router.get("/search", response_model=GlossaryLookupResponse)
async def search_glossary(
    request: Request,
    domain: str = Query("legal", description="Glossary domain; only 'legal' is supported in MVP"),
    source: str | None = Query(None, description="Optional source language filter (en, de, fr)"),
    target: str | None = Query(None, description="Optional target language hint (en, de, fr)"),
    q: str = Query(..., description="Search query"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of terms to return"),
) -> GlossaryLookupResponse:
    return await _lookup_terms(request, domain, source, target, q, limit)


@router.post("/extract", response_model=GlossaryExtractResponse)
async def extract_glossary_terms(
    request: Request,
    payload: GlossaryExtractRequest,
) -> GlossaryExtractResponse:
    terms = extract_terms(payload.text, payload.source_lang)
    persisted: list[dict[str, object]] = []
    if payload.persist:
        persisted = await insert_terms(
            terms,
            doc_id=payload.doc_id,
            source_lang=payload.source_lang,
            db=D1Client.from_scope(request.scope),
        )

    from app.integrations.posthog import get_client as _get_ph  # noqa: PLC0415

    if ph := _get_ph():
        ph.capture(
            "glossary_terms_extracted",
            properties={
                "source_lang": payload.source_lang,
                "extracted_count": len(terms),
                "persisted_count": len(persisted),
                "persisted": payload.persist,
            },
        )

    return GlossaryExtractResponse(
        source_lang=payload.source_lang,
        extracted_count=len(terms),
        persisted_count=len(persisted),
        terms=[
            GlossaryExtractedTerm(
                term_en=str(getattr(term, "term_en", "")),
                term_de=str(getattr(term, "term_de", "")),
                term_fr=str(getattr(term, "term_fr", "")),
                definition=str(getattr(term, "definition", "")),
                source_lang=payload.source_lang,
                confidence=float(getattr(term, "confidence", 1.0) or 1.0),
            )
            for term in terms
        ],
    )
