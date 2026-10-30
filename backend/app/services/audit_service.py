# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Audit Service — GDPR Article 30 compliant audit trail.

DRY principles applied:
- Reuses D1Client pattern (graceful degradation, no exceptions)
- Single responsibility: log audit events, query by actor, delete by actor
- Configurable via AUDIT_LOG_ENABLED (already in Settings)
- No PII in logs — opaque user IDs only (Article 5(1)(c))

Usage:
    from app.services.audit_service import AuditService
    from app.db.d1_client import D1Client

    audit = AuditService(d1_client, jurisdiction="EU")
    await audit.log_event(
        actor_id="@alice:matrix.org",
        action=AuditAction.DOCUMENT_SEND,
        resource_type="document",
        resource_id="$room_id",
        metadata={"filename": "contract.pdf", "mime_type": "application/pdf"},
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.db.d1_client import D1Client
from app.models.audit import AuditAction, AuditEvent, AuditLogEntry

logger = logging.getLogger(__name__)

# DDL for audit_logs table — idempotent (IF NOT EXISTS)
_AUDIT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    jurisdiction TEXT NOT NULL DEFAULT 'EU',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
"""


class AuditService:
    """GDPR Article 30 audit logging service.

    Graceful degradation: if D1 is unavailable, events are logged
    to Python logger as warnings. Callers never depend on audit
    availability for correctness.
    """

    def __init__(self, d1: D1Client | None, jurisdiction: str = "EU") -> None:
        self._d1 = d1
        self._jurisdiction = jurisdiction

    async def ensure_table(self) -> bool:
        """Create audit_logs table if it doesn't exist. Idempotent."""
        if self._d1 is None:
            return False
        return await self._d1.execute(_AUDIT_TABLE_DDL)

    async def log_event(
        self,
        actor_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent | None:
        """Log an audit event to D1.

        Returns the AuditEvent on success, None on failure.
        Never raises — graceful degradation.
        """
        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            jurisdiction=self._jurisdiction,
        )

        entry = AuditLogEntry(
            event_id=event.event_id,
            timestamp=event.timestamp,
            actor_id=event.actor_id,
            action=event.action.value,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            metadata_json=json.dumps(event.metadata),
            jurisdiction=event.jurisdiction,
        )

        if self._d1 is None:
            logger.warning(
                "Audit event not persisted (D1 unavailable): action=%s actor=%s resource=%s",
                event.action.value,
                event.actor_id,
                event.resource_id,
            )
            return event

        sql = """
            INSERT INTO audit_logs (id, event_id, timestamp, actor_id, action,
                                    resource_type, resource_id, metadata_json,
                                    jurisdiction, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            entry.id,
            entry.event_id,
            entry.timestamp,
            entry.actor_id,
            entry.action,
            entry.resource_type,
            entry.resource_id,
            entry.metadata_json,
            entry.jurisdiction,
            entry.created_at,
        ]

        success = await self._d1.execute(sql, params)
        if not success:
            logger.warning(
                "Audit event D1 write failed: action=%s actor=%s",
                event.action.value,
                event.actor_id,
            )

        return event

    async def get_events_by_actor(
        self,
        actor_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve audit events for a specific actor (Article 15 SAR support)."""
        if self._d1 is None:
            return []

        sql = """
            SELECT * FROM audit_logs
            WHERE actor_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        return await self._d1.fetch_all(sql, [actor_id, limit])

    async def delete_by_actor(self, actor_id: str) -> int:
        """Delete all audit events for an actor (Article 17 right to erasure).

        Uses pseudonymization: replaces actor_id with '[REDACTED]'
        instead of deleting rows, preserving audit chain integrity.

        Returns number of affected rows.
        """
        if self._d1 is None:
            return 0

        # Pseudonymize rather than delete (preserves hash chain integrity)
        sql = """
            UPDATE audit_logs
            SET actor_id = '[REDACTED]', metadata_json = '{}'
            WHERE actor_id = ?
        """
        success = await self._d1.execute(sql, [actor_id])
        if not success:
            logger.warning("Audit pseudonymization failed for actor=%s", actor_id)
            return 0

        # Return count of affected rows
        count_sql = "SELECT COUNT(*) as cnt FROM audit_logs WHERE actor_id = '[REDACTED]'"
        result = await self._d1.fetch_one(count_sql)
        return result.get("cnt", 0) if result else 0

    async def get_events_by_action(
        self,
        action: AuditAction,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve audit events filtered by action type."""
        if self._d1 is None:
            return []

        sql = """
            SELECT * FROM audit_logs
            WHERE action = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        return await self._d1.fetch_all(sql, [action.value, limit])
