# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Audit Event Model — GDPR Article 30 compliant audit trail.

Design principles (DRY):
- Reuses D1Client pattern for storage (graceful degradation)
- Opaque user IDs only (no PII in logs — Article 5(1)(c))
- Configurable retention via AUDIT_LOG_RETENTION_DAYS
- Right-to-erasure support via delete_by_actor (Article 17)

Audit events capture:
- Who (actor_id — Matrix user ID, not email/name)
- When (timestamp)
- What (action + resource)
- Where (jurisdiction)
"""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLModelField
from sqlmodel import SQLModel


class AuditAction(StrEnum):
    """Audit event actions — extensible, DRY naming convention."""

    DOCUMENT_SEND = "document.send"
    ROOM_CREATE = "room.create"
    ROOM_EVENTS_READ = "room.events.read"
    OAUTH_LOGIN = "oauth.login"
    OAUTH_CALLBACK = "oauth.callback"
    OAUTH_LOGOUT = "oauth.logout"
    RIGHT_TO_ERASURE = "right_to_erasure"
    TRANSLATION_REDACTED = "translation.redacted"


class AuditEvent(BaseModel):
    """GDPR Article 30 compliant audit event.

    Fields map to Article 30(1)(a)-(g):
    - actor_id → (a) name and contact details of controller
    - action → (b) purposes of processing
    - resource_type/resource_id → (c) categories of data subjects
    - timestamp → (f) time limits for erasure
    - jurisdiction → (g) technical security measures
    """

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    actor_id: str = Field(description="Matrix user ID (@user:domain.tld) — opaque, no PII")
    action: AuditAction
    resource_type: str = Field(description="Resource category: 'document' | 'room' | 'session'")
    resource_id: str = Field(description="Room ID, event ID, or session identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Context: filename, mime_type, participant_count"
    )
    jurisdiction: str = Field(default="EU", description="Data residency region from config")


class AuditLogEntry(BaseModel):
    """Stored audit log row — maps to D1 audit_logs table."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_id: str
    timestamp: int
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    metadata_json: str = Field(description="JSON-serialized metadata")
    jurisdiction: str
    created_at: int = Field(default_factory=lambda: int(time.time()))


class AuditLogRecord(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: int | None = SQLModelField(default=None, primary_key=True)
    timestamp: str = SQLModelField(nullable=False)
    method: str = SQLModelField(nullable=False)
    path: str = SQLModelField(nullable=False)
    status_code: int = SQLModelField(nullable=False)
    duration_ms: int | None = SQLModelField(default=None)
    request_id_hash: str | None = SQLModelField(default=None)
    mime_type: str | None = SQLModelField(default=None)
    target_lang: str | None = SQLModelField(default=None)
