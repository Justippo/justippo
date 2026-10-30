# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Glossary SQLModel Schemas — Domain Glossary (ADR-005, ADR-010)

These models define the contract between the RAG engine, translation service,
and glossary repository.  the glossary_service.py consumes GlossaryTermCreate
and GlossaryTermRead; the repository layer maps between these Pydantic models
and D1 / SQLite storage.

Design note (Pyodide constraint):
    SQLModel table=True models cannot use SQLAlchemy's create_engine / session
    in Cloudflare Workers (no disk, no threads).  These schemas serve as
    *canonical type contracts* and documentation of the table shape.
    Actual CRUD goes through D1Client (app.db.d1_client) which wraps the
    Cloudflare D1 JS binding.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> str:
    """Return current UTC timestamp as ISO-8601 string (D1-compatible)."""
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017  # datetime.UTC breaks mypy on CI typeshed


# ── Database Record ────────────────────────────────────────────────────────────


class GlossaryTermRecord(SQLModel, table=True):
    """Canonical glossary term persisted in D1 / SQLite.

    The UNIQUE(term_en, term_de, term_fr) constraint is enforced at the
    D1 schema level (see 0003_glossary_terms.sql).  SQLModel's table_args
    are informational only and do NOT create the constraint in D1.
    """

    __tablename__ = "glossary_terms"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="UUID v4 primary key",
    )
    term_en: str = Field(description="Canonical English term")
    term_de: str = Field(description="Canonical German term")
    term_fr: str = Field(description="Canonical French term")
    mistranslations: str | None = Field(
        default=None,
        description="JSON-encoded list of known mistranslations for post-editing",
    )
    definition: str = Field(default="", description="Plain-English definition")
    source_doc_id: str | None = Field(
        default=None,
        foreign_key="documents.id",
        description="Soft reference to source document",
    )
    source_lang: str | None = Field(
        default=None,
        description="ISO 639-1 language of the source document",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="BAML extraction confidence score",
    )
    created_at: str = Field(default_factory=_utcnow, description="ISO-8601 creation timestamp")
    updated_at: str = Field(default_factory=_utcnow, description="ISO-8601 last-update timestamp")


# ── API Contracts ─────────────────────────────────────────────────────────────


class GlossaryTermCreate(SQLModel):
    """Input model for inserting / upserting a glossary term.

    Used by GlossaryService.insert_terms() → GlossaryRepo.upsert_terms().
    Validation rules in glossary_service.py.
    """

    term_en: str
    term_de: str
    term_fr: str
    mistranslations: list[str] | None = None
    definition: str = ""
    source_doc_id: str | None = None
    source_lang: str | None = None
    confidence: float = 1.0


class GlossaryTermRead(SQLModel):
    """Response model returned by GET /glossary endpoints.

    Mirrors GlossaryTermRecord but excludes internal fields (source_doc_id,
    confidence) unless the caller requests them explicitly.
    """

    id: str
    term_en: str
    term_de: str
    term_fr: str
    mistranslations: list[str] | None = None
    definition: str
    source_lang: str | None = None
    created_at: str
    updated_at: str


def parse_mistranslations(term: object) -> list[str]:
    """Return a list of mistranslations from a glossary term object.

    Handles JSON-encoded strings (DB records), plain lists (Pydantic models),
    and missing values gracefully.
    """
    raw = getattr(term, "mistranslations", None)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            return []
    return []
