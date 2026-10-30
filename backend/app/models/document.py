from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> str:
    """Return current UTC timestamp as ISO-8601 string (D1-compatible)."""
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


class DocumentRecord(SQLModel, table=True):
    """Canonical document record persisted in D1."""

    __tablename__ = "documents"

    id: str = Field(primary_key=True)
    filename: str = Field(nullable=False)
    mime_type: str = Field(nullable=False)
    page_count: int = Field(default=0, nullable=False)
    detected_language: str = Field(default="", nullable=False)
    status: str = Field(default="processed", nullable=False)
    created_at: str = Field(default_factory=_utcnow, nullable=False)
    expires_at: str | None = Field(default=None)


class TranslationJobRecord(SQLModel, table=True):
    __tablename__ = "translation_jobs"

    job_id: str = Field(primary_key=True)
    document_id: str = Field(nullable=False)
    source_language: str = Field(nullable=False)
    target_language: str = Field(nullable=False)
    status: str = Field(default="queued", nullable=False)
    error: str | None = Field(default=None)
    output_key: str | None = Field(default=None)
    created_at: str = Field(default_factory=_utcnow, nullable=False)
    updated_at: str = Field(default_factory=_utcnow, nullable=False)


class TranslationPageRecord(SQLModel, table=True):
    __tablename__ = "translation_pages"

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(nullable=False, foreign_key="translation_jobs.job_id")
    page_number: int = Field(nullable=False)
    text: str = Field(default="", nullable=False)
