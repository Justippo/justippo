# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Tests — Audit Model & Service (GDPR Article 30)

Covers:
- AuditEvent creation and defaults
- AuditAction enum values
- AuditLogEntry serialization
- AuditService with mocked D1Client
- Graceful degradation when D1 is None
- Right-to-erasure pseudonymization
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.audit import AuditAction, AuditEvent, AuditLogEntry
from app.services.audit_service import AuditService

# ─── AuditAction Enum ────────────────────────────────────────────────────────


class TestAuditAction:
    def test_action_values(self) -> None:
        assert AuditAction.DOCUMENT_SEND.value == "document.send"
        assert AuditAction.ROOM_CREATE.value == "room.create"
        assert AuditAction.ROOM_EVENTS_READ.value == "room.events.read"
        assert AuditAction.OAUTH_LOGIN.value == "oauth.login"
        assert AuditAction.OAUTH_CALLBACK.value == "oauth.callback"
        assert AuditAction.OAUTH_LOGOUT.value == "oauth.logout"
        assert AuditAction.RIGHT_TO_ERASURE.value == "right_to_erasure"

    def test_action_is_string(self) -> None:
        assert isinstance(AuditAction.DOCUMENT_SEND, str)


# ─── AuditEvent Model ────────────────────────────────────────────────────────


class TestAuditEvent:
    def test_creates_with_defaults(self) -> None:
        event = AuditEvent(
            actor_id="@alice:matrix.org",
            action=AuditAction.DOCUMENT_SEND,
            resource_type="document",
            resource_id="$event123",
        )
        assert event.actor_id == "@alice:matrix.org"
        assert event.action == AuditAction.DOCUMENT_SEND
        assert event.resource_type == "document"
        assert event.resource_id == "$event123"
        assert event.jurisdiction == "EU"
        assert event.metadata == {}
        assert len(event.event_id) == 32  # UUID hex
        assert event.timestamp > 0

    def test_custom_metadata(self) -> None:
        meta = {"filename": "test.pdf", "mime_type": "application/pdf"}
        event = AuditEvent(
            actor_id="@bob:matrix.org",
            action=AuditAction.ROOM_CREATE,
            resource_type="room",
            resource_id="!room:matrix.org",
            metadata=meta,
        )
        assert event.metadata == meta

    def test_custom_jurisdiction(self) -> None:
        event = AuditEvent(
            actor_id="@charlie:matrix.org",
            action=AuditAction.ROOM_EVENTS_READ,
            resource_type="room",
            resource_id="!room:matrix.org",
            jurisdiction="DE",
        )
        assert event.jurisdiction == "DE"


# ─── AuditLogEntry Model ─────────────────────────────────────────────────────


class TestAuditLogEntry:
    def test_creates_from_event(self) -> None:
        event = AuditEvent(
            actor_id="@alice:matrix.org",
            action=AuditAction.DOCUMENT_SEND,
            resource_type="document",
            resource_id="$event123",
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
        assert entry.event_id == event.event_id
        assert entry.action == "document.send"
        assert entry.metadata_json == "{}"
        assert len(entry.id) == 32  # UUID hex


# ─── AuditService ────────────────────────────────────────────────────────────


class TestAuditService:
    def test_init_with_d1(self) -> None:
        mock_d1 = MagicMock()
        service = AuditService(d1=mock_d1, jurisdiction="DE")
        assert service._d1 is mock_d1
        assert service._jurisdiction == "DE"

    def test_init_without_d1(self) -> None:
        service = AuditService(d1=None)
        assert service._d1 is None
        assert service._jurisdiction == "EU"


class TestAuditServiceLogEvent:
    @pytest.mark.asyncio
    async def test_log_event_with_d1(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.execute = AsyncMock(return_value=True)
        service = AuditService(d1=mock_d1, jurisdiction="EU")

        event = await service.log_event(
            actor_id="@alice:matrix.org",
            action=AuditAction.DOCUMENT_SEND,
            resource_type="document",
            resource_id="$event123",
            metadata={"filename": "test.pdf"},
        )

        assert event is not None
        assert event.actor_id == "@alice:matrix.org"
        assert event.action == AuditAction.DOCUMENT_SEND
        mock_d1.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_without_d1(self) -> None:
        service = AuditService(d1=None)

        event = await service.log_event(
            actor_id="@alice:matrix.org",
            action=AuditAction.ROOM_CREATE,
            resource_type="room",
            resource_id="!room:matrix.org",
        )

        assert event is not None
        assert event.actor_id == "@alice:matrix.org"

    @pytest.mark.asyncio
    async def test_log_event_d1_failure(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.execute = AsyncMock(return_value=False)
        service = AuditService(d1=mock_d1)

        event = await service.log_event(
            actor_id="@alice:matrix.org",
            action=AuditAction.DOCUMENT_SEND,
            resource_type="document",
            resource_id="$event123",
        )

        assert event is not None  # Returns event even on D1 failure


class TestAuditServiceQueries:
    @pytest.mark.asyncio
    async def test_get_events_by_actor_with_d1(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.fetch_all = AsyncMock(return_value=[{"event_id": "abc"}])
        service = AuditService(d1=mock_d1)

        events = await service.get_events_by_actor("@alice:matrix.org", limit=50)

        assert len(events) == 1
        mock_d1.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_events_by_actor_without_d1(self) -> None:
        service = AuditService(d1=None)
        events = await service.get_events_by_actor("@alice:matrix.org")
        assert events == []

    @pytest.mark.asyncio
    async def test_delete_by_actor_with_d1(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.execute = AsyncMock(return_value=True)
        mock_d1.fetch_one = AsyncMock(return_value={"cnt": 3})
        service = AuditService(d1=mock_d1)

        count = await service.delete_by_actor("@alice:matrix.org")

        assert count == 3
        mock_d1.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_actor_without_d1(self) -> None:
        service = AuditService(d1=None)
        count = await service.delete_by_actor("@alice:matrix.org")
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_by_actor_d1_failure(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.execute = AsyncMock(return_value=False)
        service = AuditService(d1=mock_d1)

        count = await service.delete_by_actor("@alice:matrix.org")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_events_by_action_with_d1(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.fetch_all = AsyncMock(return_value=[{"action": "document.send"}])
        service = AuditService(d1=mock_d1)

        events = await service.get_events_by_action(AuditAction.DOCUMENT_SEND)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_get_events_by_action_without_d1(self) -> None:
        service = AuditService(d1=None)
        events = await service.get_events_by_action(AuditAction.DOCUMENT_SEND)
        assert events == []


class TestAuditServiceEnsureTable:
    @pytest.mark.asyncio
    async def test_ensure_table_with_d1(self) -> None:
        mock_d1 = MagicMock()
        mock_d1.execute = AsyncMock(return_value=True)
        service = AuditService(d1=mock_d1)

        result = await service.ensure_table()
        assert result is True
        mock_d1.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_table_without_d1(self) -> None:
        service = AuditService(d1=None)
        result = await service.ensure_table()
        assert result is False
