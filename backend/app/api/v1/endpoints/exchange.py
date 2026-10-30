# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Exchange Endpoints — Cross-Border Document Exchange via Matrix Protocol (Sprint 3)

Responsibilities:
- POST /api/v1/exchange/send — send document to a Matrix room
- POST /api/v1/exchange/rooms — create a secure Matrix room
- GET /api/v1/exchange/rooms/{room_id}/events — retrieve room events

All endpoints gated by require_feature("ENABLE_MATRIX_EXCHANGE") dependency.
GDPR NFR-04: file bytes are deleted immediately after sending.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from app.api.v1.endpoints.matrix_auth import (
    AuthenticatedMatrixSession,
    require_authenticated_matrix_session,
)
from app.core.config import settings
from app.core.dependencies import require_feature
from app.integrations.matrix.client import (
    MatrixClient,
    MatrixClientError,
    MatrixConfigurationError,
    MatrixTimeoutError,
)
from app.integrations.posthog import capture_event
from app.models.audit import AuditAction
from app.services.audit_service import AuditService

router = APIRouter()
logger = logging.getLogger(__name__)
MatrixSession = Annotated[
    AuthenticatedMatrixSession,
    Depends(require_authenticated_matrix_session),
]

# Matrix user ID format: @localpart:domain.tld
# Spec (v1.11 §Appendices): localpart MUST contain only a-z, 0-9, ., _, =, -, /
# We also accept A-Z (lenient) because some homeservers allow uppercase at registration.
# Domain must be a valid FQDN with TLD (rejects localhost / bare IPs — intentional for
# cross-border exchange where federation requires proper DNS).
_MATRIX_USER_ID_RE = re.compile(r"\A@[a-zA-Z0-9._=\/\-]+:[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\Z")


def _validate_matrix_user_ids(participants: list[str]) -> None:
    """Validate that all participant strings are well-formed Matrix user IDs.

    Raises HTTP 422 if malformed or empty.
    """
    if not participants:
        raise HTTPException(
            status_code=422,
            detail="participants list must not be empty",
        )
    for uid in participants:
        if not _MATRIX_USER_ID_RE.match(uid):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid Matrix user ID format: {uid!r}. Expected @localpart:domain.tld",
            )


def _matrix_upstream_error(code: str, message: str) -> HTTPException:
    """Return a stable public error without exposing Matrix response content."""
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": code, "message": message},
    )


def _classified_room_error(exc: MatrixClientError) -> HTTPException:
    """Map safe Matrix diagnostics to actionable public errors."""
    logger.warning(
        "Matrix exchange failed: operation=%s status=%s errcode=%s retry_after_ms=%s",
        exc.operation,
        exc.status_code,
        exc.errcode,
        exc.retry_after_ms,
    )
    # Handle configuration errors (4.3s crash prevention)
    if isinstance(exc, MatrixConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "matrix_configuration_error",
                "message": "Matrix service is not configured. Contact your administrator.",
            },
        )
    # Handle timeout errors (11.8s crash prevention)
    if isinstance(exc, MatrixTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "code": "matrix_timeout",
                "message": "Matrix service is taking too long. Please try again.",
            },
        )
    if exc.errcode in {"M_UNKNOWN_TOKEN", "M_MISSING_TOKEN"}:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "matrix_authentication_required",
                "message": "Your Matrix session has expired. Sign in again.",
            },
        )
    if exc.errcode == "M_LIMIT_EXCEEDED" or exc.status_code == 429:
        detail: dict[str, Any] = {
            "code": "matrix_rate_limited",
            "message": "Matrix is limiting room requests. Please wait and try again.",
        }
        if exc.retry_after_ms is not None and exc.retry_after_ms > 0:
            detail["retry_after_ms"] = exc.retry_after_ms
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )
    if exc.operation == "invite":
        if exc.errcode == "M_NOT_FOUND":
            code = "matrix_participant_not_found"
            message = "The Matrix participant could not be found."
        elif exc.errcode == "M_FORBIDDEN" or exc.status_code == 403:
            code = "matrix_invitation_forbidden"
            message = "The participant's Matrix server rejected the invitation."
        else:
            code = "matrix_invitation_failed"
            message = "The room was created, but the participant could not be invited."
        return _matrix_upstream_error(code, message)
    if exc.errcode == "M_FORBIDDEN" or exc.status_code == 403:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "matrix_room_forbidden",
                "message": "Your Matrix account is not permitted to create rooms.",
            },
        )
    return _matrix_upstream_error(
        "matrix_room_creation_failed",
        "The Matrix room could not be created.",
    )


@router.post(
    "/send",
    dependencies=[Depends(require_feature("ENABLE_MATRIX_EXCHANGE"))],
)
async def send_document(
    request: Request,
    matrix_session: MatrixSession,
    room_id: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, Any]:
    """Send a document to a Matrix room.

    Validates feature flag (403 if off). Uploads file to Matrix homeserver
    and sends file event to the specified room. Deletes file bytes reference
    before returning (GDPR NFR-04).

    Returns {"event_id": str, "room_id": str, "ephemeral": true}.
    """
    # Read file bytes into memory
    doc_bytes: bytes = await file.read()
    filename: str = file.filename or "document"
    mime_type: str = file.content_type or "application/octet-stream"

    if not doc_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    client = MatrixClient(
        access_token=matrix_session.access_token,
        device_id=matrix_session.device_id,
    )
    audit = AuditService(d1=None, jurisdiction=settings.DATA_RESIDENCY_REGION)
    try:
        event_id = await client.send_document(
            room_id=room_id,
            doc_bytes=doc_bytes,
            filename=filename,
            mime_type=mime_type,
        )
        # GDPR Article 30: log document access event
        await audit.log_event(
            actor_id=matrix_session.user_id,
            action=AuditAction.DOCUMENT_SEND,
            resource_type="document",
            resource_id=event_id,
            metadata={"filename": filename, "mime_type": mime_type, "room_id": room_id},
        )
    except MatrixClientError as exc:
        raise _matrix_upstream_error(
            "matrix_send_failed",
            "The document could not be sent through Matrix.",
        ) from exc
    except Exception as exc:
        raise _matrix_upstream_error(
            "matrix_upstream_error",
            "The Matrix service is temporarily unavailable.",
        ) from exc
    finally:
        # GDPR NFR-04: delete file bytes reference immediately
        del doc_bytes
        await client.close()

    # PostHog: exchange_document_shared event (no room IDs, user IDs, or content)
    await capture_event(
        "exchange_document_shared",
        distinct_id=getattr(request.state, "posthog_distinct_id", ""),
        properties={"protocol": "matrix", "direction": "send"},
        session_id=getattr(request.state, "posthog_session_id", None),
    )

    return {"event_id": event_id, "room_id": room_id, "ephemeral": True}


class RoomCreateRequest(BaseModel):
    """Request body for creating a Matrix exchange room."""

    participants: list[str]


@router.post(
    "/rooms",
    dependencies=[Depends(require_feature("ENABLE_MATRIX_EXCHANGE"))],
)
async def create_room(
    request: RoomCreateRequest,
    matrix_session: MatrixSession,
) -> dict[str, str]:
    """Create a secure Matrix room as the authenticated Matrix user."""
    _validate_matrix_user_ids(request.participants)

    client = MatrixClient(
        access_token=matrix_session.access_token,
        device_id=matrix_session.device_id,
    )
    audit = AuditService(d1=None, jurisdiction=settings.DATA_RESIDENCY_REGION)
    try:
        room_id = await client.create_secure_room(request.participants)
        # GDPR Article 30: log room creation event
        await audit.log_event(
            actor_id=matrix_session.user_id,
            action=AuditAction.ROOM_CREATE,
            resource_type="room",
            resource_id=room_id,
            metadata={"participant_count": len(request.participants)},
        )
    except MatrixClientError as exc:
        raise _classified_room_error(exc) from exc
    except Exception as exc:
        raise _matrix_upstream_error(
            "matrix_upstream_error",
            "The Matrix service is temporarily unavailable.",
        ) from exc
    finally:
        await client.close()

    return {"room_id": room_id}


@router.get(
    "/health",
    dependencies=[Depends(require_feature("ENABLE_MATRIX_EXCHANGE"))],
)
async def check_matrix_health() -> dict[str, Any]:
    """Check Matrix homeserver health and connectivity.

    Returns:
        Health status including server version and connectivity metrics.
    """
    try:
        # Create client with minimal configuration for health check
        client = MatrixClient()
        health_data = await client.check_health()
        return {
            "status": "healthy",
            "matrix": health_data,
            "timestamp": int(asyncio.get_event_loop().time() * 1000),
        }
    except MatrixConfigurationError:
        logger.warning("Matrix health check failed: configuration error", exc_info=True)
        return {
            "status": "degraded",
            "matrix": {
                "error": "configuration_error",
                "message": "Matrix service is not configured",
            },
            "timestamp": int(asyncio.get_event_loop().time() * 1000),
        }
    except MatrixTimeoutError:
        logger.warning("Matrix health check failed: timeout", exc_info=True)
        return {
            "status": "degraded",
            "matrix": {
                "error": "timeout",
                "message": "Matrix service is not responding",
            },
            "timestamp": int(asyncio.get_event_loop().time() * 1000),
        }
    except Exception as exc:
        logger.error("Matrix health check failed: unexpected error", exc_info=True)
        return {
            "status": "unhealthy",
            "matrix": {
                "error": "unknown",
                "message": f"Matrix health check failed: {exc}",
            },
            "timestamp": int(asyncio.get_event_loop().time() * 1000),
        }
    finally:
        if "client" in locals():
            await client.close()


@router.get(
    "/rooms/{room_id}/events",
    dependencies=[Depends(require_feature("ENABLE_MATRIX_EXCHANGE"))],
)
async def get_room_events(
    room_id: str,
    matrix_session: MatrixSession,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve recent events from a Matrix room.

    Strips any content.body fields containing raw document bytes.
    """
    # Cap limit to prevent abuse
    limit = min(max(limit, 1), 100)

    client = MatrixClient(
        access_token=matrix_session.access_token,
        device_id=matrix_session.device_id,
    )
    audit = AuditService(d1=None, jurisdiction=settings.DATA_RESIDENCY_REGION)
    try:
        events = await client.get_room_events(room_id=room_id, limit=limit)
        # GDPR Article 30: log event retrieval for audit trail
        await audit.log_event(
            actor_id=matrix_session.user_id,
            action=AuditAction.ROOM_EVENTS_READ,
            resource_type="room",
            resource_id=room_id,
            metadata={"event_count": len(events), "limit": limit},
        )
    except MatrixClientError as exc:
        raise _matrix_upstream_error(
            "matrix_events_failed",
            "Matrix room activity could not be loaded.",
        ) from exc
    except Exception as exc:
        raise _matrix_upstream_error(
            "matrix_upstream_error",
            "The Matrix service is temporarily unavailable.",
        ) from exc
    finally:
        await client.close()

    return events
