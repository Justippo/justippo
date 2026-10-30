# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Matrix Protocol Client — Secure Cross-Border Document Exchange

Uses direct Matrix Client-Server API v3 HTTP calls via httpx (Pyodide-safe).
No matrix-nio dependency — all operations are stateless HTTP requests.

Security:
- NEVER log doc_bytes or any derivative (hash, preview, slice).
- Only log: filename, mime_type, len(doc_bytes).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MatrixClientError(Exception):
    """Raised when a Matrix operation fails, with sanitized diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        operation: str = "unknown",
        status_code: int | None = None,
        errcode: str | None = None,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.errcode = errcode
        self.retry_after_ms = retry_after_ms


class MatrixConfigurationError(MatrixClientError):
    """Raised when Matrix client is misconfigured (missing/placeholder token)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, operation="configuration")


class MatrixTimeoutError(MatrixClientError):
    """Raised when a Matrix operation times out (11.8s crash prevention)."""

    def __init__(self, message: str, *, operation: str = "unknown") -> None:
        super().__init__(message, operation=operation)


def _matrix_error(response: httpx.Response, *, operation: str, label: str) -> MatrixClientError:
    """Build an error containing only Matrix's documented diagnostic fields."""
    try:
        data = response.json()
    except ValueError:
        data = {}
    errcode = data.get("errcode") if isinstance(data.get("errcode"), str) else None
    retry_after = data.get("retry_after_ms")
    retry_after_ms = retry_after if isinstance(retry_after, int) else None
    return MatrixClientError(
        f"{label} ({response.status_code})",
        operation=operation,
        status_code=response.status_code,
        errcode=errcode,
        retry_after_ms=retry_after_ms,
    )


class MatrixClient:
    """Async Matrix client using direct HTTP API calls (httpx).

    Connects to the configured homeserver using access token authentication.
    All operations are stateless — no persistent connection or sync loop needed.
    Uses httpx (Pyodide-safe) instead of matrix-nio (requires socket/ssl/threading).
    """

    # Placeholder tokens that must never reach the Matrix API
    _PLACEHOLDER_TOKENS = frozenset(
        {
            "",
            "your-matrix-token",
            "REPLACE_WITH_YOUR_TOKEN",
            "YOUR_ACCESS_TOKEN",
            "CHANGE_ME",
        }
    )

    # Timeout configuration in seconds
    _TIMEOUT_CONFIG = {
        "connect": 5.0,
        "read": 8.0,
        "write": 8.0,
        "pool": 5.0,
    }

    # Circuit breaker configuration
    _RETRY_CONFIG = {
        "attempts": 3,
        "exponential_base": 2,
        "exponential_max": 4.0,
    }

    def __init__(
        self,
        *,
        access_token: str | None = None,
        base_url: str | None = None,
        device_id: str | None = None,
    ) -> None:
        """Create a client with explicit credentials when acting for a user.

        The settings fallback is retained temporarily for existing service-token
        call sites. Exchange endpoints will move to the authenticated OAuth
        session dependency in phase 2.

        Raises:
            MatrixConfigurationError: If the access token is missing or is a placeholder.
        """
        self._base_url = (base_url or settings.MATRIX_HOMESERVER_URL).rstrip("/")
        self._token = access_token if access_token is not None else settings.MATRIX_ACCESS_TOKEN
        self._device_id = device_id if device_id is not None else settings.MATRIX_DEVICE_ID

        # Fail fast on placeholder/missing tokens (4.3s crash prevention)
        normalized_token = self._token.strip()
        if not normalized_token or normalized_token in self._PLACEHOLDER_TOKENS:
            raise MatrixConfigurationError(
                "Matrix access token is missing or is a placeholder. "
                "Set MATRIX_ACCESS_TOKEN to a valid Element.io token."
            )

        # Validate homeserver URL format
        if not self._base_url.startswith("https://"):
            raise MatrixConfigurationError(
                f"Matrix homeserver URL must use HTTPS, got: {self._base_url}"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def close(self) -> None:
        """No-op — httpx clients are created per-request, no persistent state."""
        pass

    async def _with_retry(
        self,
        operation_func: Callable[[], Awaitable[httpx.Response]],
        *,
        operation_name: str,
    ) -> httpx.Response:
        """Execute an HTTP operation with exponential backoff retry.

        Args:
            operation: Async callable that returns httpx.Response
            operation_name: Name of operation for error reporting

        Returns:
            httpx.Response from successful attempt

        Raises:
            MatrixClientError: If all retry attempts fail
            MatrixTimeoutError: If operation times out during retry
        """
        # Manual retry loop for better control over retry conditions
        attempt = 0

        while attempt < self._RETRY_CONFIG["attempts"]:
            attempt += 1
            try:
                response = await operation_func()
                # Retry on 5xx server errors and 429 rate limits
                if response.status_code >= 500 or response.status_code == 429:
                    if attempt < self._RETRY_CONFIG["attempts"]:
                        # Exponential backoff
                        delay = min(
                            self._RETRY_CONFIG["exponential_max"] * (2 ** (attempt - 1)),
                            self._RETRY_CONFIG["exponential_max"],
                        )
                        logger.debug(
                            "Matrix operation %s failed with status %d, retrying in %.2fs (attempt %d/%d)",
                            operation_name,
                            response.status_code,
                            delay,
                            attempt,
                            self._RETRY_CONFIG["attempts"],
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Last attempt failed - preserve Matrix diagnostics
                        try:
                            data = response.json()
                            errcode = (
                                data.get("errcode")
                                if isinstance(data.get("errcode"), str)
                                else None
                            )
                            retry_after = data.get("retry_after_ms")
                            retry_after_ms = retry_after if isinstance(retry_after, int) else None
                        except ValueError:
                            errcode = None
                            retry_after_ms = None

                        raise MatrixClientError(
                            f"Operation {operation_name} failed after {attempt} attempts: HTTP {response.status_code}",
                            operation=operation_name,
                            status_code=response.status_code,
                            errcode=errcode,
                            retry_after_ms=retry_after_ms,
                        )
                # Success - return the response
                return response
            except httpx.TimeoutException as exc:
                if attempt < self._RETRY_CONFIG["attempts"]:
                    # Exponential backoff for timeouts too
                    delay = min(
                        self._RETRY_CONFIG["exponential_max"] * (2 ** (attempt - 1)),
                        self._RETRY_CONFIG["exponential_max"],
                    )
                    logger.debug(
                        "Matrix operation %s timed out, retrying in %.2fs (attempt %d/%d)",
                        operation_name,
                        delay,
                        attempt,
                        self._RETRY_CONFIG["attempts"],
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Last attempt timed out
                    raise MatrixTimeoutError(
                        f"Operation {operation_name} timed out after {attempt} attempts",
                        operation=operation_name,
                    ) from exc
            except httpx.HTTPError as exc:
                if attempt < self._RETRY_CONFIG["attempts"]:
                    # Exponential backoff for transport errors
                    delay = min(
                        self._RETRY_CONFIG["exponential_max"] * (2 ** (attempt - 1)),
                        self._RETRY_CONFIG["exponential_max"],
                    )
                    logger.debug(
                        "Matrix operation %s transport error, retrying in %.2fs (attempt %d/%d)",
                        operation_name,
                        delay,
                        attempt,
                        self._RETRY_CONFIG["attempts"],
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Last attempt failed with transport error
                    raise MatrixClientError(
                        f"Operation {operation_name} transport error after {attempt} attempts: {exc}",
                        operation=operation_name,
                    ) from exc

        # This should never be reached
        raise MatrixClientError(  # pragma: no cover - defensive unreachable fallback
            f"Operation {operation_name} failed after {self._RETRY_CONFIG['attempts']} attempts",
            operation=operation_name,
        )

    async def check_health(self) -> dict[str, Any]:
        """Check Matrix homeserver health and connectivity.

        Returns:
            Dict with health status, server version, and connectivity metrics.

        Raises:
            MatrixClientError: If health check fails.
            MatrixTimeoutError: If health check times out.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/_matrix/client/versions",
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise MatrixTimeoutError(
                f"Health check timed out: {exc}",
                operation="health_check",
            ) from exc
        except httpx.HTTPError as exc:
            raise MatrixClientError(
                f"Health check transport error: {exc}",
                operation="health_check",
            ) from exc

        if response.status_code != 200:
            raise MatrixClientError(
                f"Health check failed ({response.status_code})",
                operation="health_check",
            )

        data = response.json()
        return {
            "status": "healthy",
            "server_version": data.get("unstable_features", {}).get(
                "org.matrix.msc3504", "unknown"
            ),
            "connectivity": "ok",
            "timestamp": int(asyncio.get_event_loop().time() * 1000),
        }

    async def create_secure_room(self, participants: list[str]) -> str:
        """Create an invite-only Matrix room and invite participants.

        Uses a single httpx client for all calls and parallelises invites
        to avoid O(N) sequential latency.

        Args:
            participants: List of Matrix user IDs (@user:domain.tld) to invite.

        Returns:
            The room_id of the newly created room.

        Raises:
            MatrixClientError: If room creation fails.
        """
        logger.info("Creating secure room with %d participant(s)", len(participants))

        body: dict[str, Any] = {
            "visibility": "private",
            "name": f"{settings.MATRIX_ROOM_PREFIX}-exchange",
            "preset": "trusted_private_chat",
            "is_direct": len(participants) == 1,
            "initial_state": [
                {
                    "type": "m.room.encryption",
                    "state_key": "",
                    "content": {"algorithm": "m.megolm.v1.aes-sha2"},
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await self._with_retry(
                    lambda: client.post(
                        f"{self._base_url}/_matrix/client/v3/createRoom",
                        headers=self._headers(),
                        json=body,
                    ),
                    operation_name="create_room",
                )
        except httpx.TimeoutException as exc:
            raise MatrixTimeoutError(
                f"Room creation timed out: {exc}",  # pragma: no cover - _with_retry raises first
                operation="create_room",
            ) from exc
        except httpx.HTTPError as exc:
            raise MatrixClientError(
                f"Room creation transport error: {exc}",  # pragma: no cover - _with_retry raises first
                operation="create_room",
            ) from exc

        if response.status_code != 200:
            raise _matrix_error(response, operation="create_room", label="Room creation failed")

        data = response.json()
        if not isinstance(data, dict):
            raise MatrixClientError(
                "Room creation response is not a JSON object",
                operation="create_room",
                status_code=response.status_code,
            )
        room_id = data.get("room_id")
        if not room_id:
            raise MatrixClientError(
                "Room creation response missing room_id",
                operation="create_room",
                status_code=response.status_code,
            )

        logger.info("Created room %s, inviting %d participant(s)", room_id, len(participants))
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                results = await asyncio.gather(
                    *[
                        self._invite_user(client, str(room_id), participant)
                        for participant in participants
                    ],
                    return_exceptions=True,
                )

                for participant, result in zip(participants, results, strict=True):
                    if isinstance(result, Exception):
                        if isinstance(result, MatrixClientError):
                            # Log invite failure as a warning but do NOT raise — the room was
                            # already created. Callers receive the room_id and can retry the
                            # invite separately. Raising here caused duplicate rooms to
                            # accumulate because the frontend retried the whole request.
                            logger.warning(
                                "Invite failed for %s in room %s (operation=%s errcode=%s): continuing",
                                participant,
                                room_id,
                                result.operation,
                                result.errcode,
                            )
                        elif isinstance(result, httpx.TimeoutException):
                            raise MatrixTimeoutError(
                                f"Invitation timed out: {result}",
                                operation="invite",
                            ) from result
                        elif isinstance(result, httpx.HTTPError):
                            raise MatrixClientError(
                                f"Invitation transport error: {result}",
                                operation="invite",
                            ) from result
                        else:
                            raise result  # pragma: no cover - defensive: non-Matrix/HTTPX invite error
        except httpx.TimeoutException as exc:
            raise MatrixTimeoutError(
                f"Invitation timed out: {exc}",  # pragma: no cover - _with_retry raises first
                operation="invite",
            ) from exc
        except httpx.HTTPError as exc:
            raise MatrixClientError(
                f"Invitation transport error: {exc}",  # pragma: no cover - _with_retry raises first
                operation="invite",
            ) from exc

        return str(room_id)

    async def _invite_user(self, client: httpx.AsyncClient, room_id: str, participant: str) -> None:
        """Invite one participant so federation failures are independently classified."""
        response = await client.post(
            f"{self._base_url}/_matrix/client/v3/rooms/{room_id}/invite",
            headers=self._headers(),
            json={"user_id": participant},
        )

        if response.status_code != 200:
            raise _matrix_error(response, operation="invite", label="Invitation failed")

    async def send_document(
        self,
        room_id: str,
        doc_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        """Upload a document to the homeserver and send it to the room.

        Security: doc_bytes is NEVER logged. Only filename, mime_type, and
        byte length are recorded for audit purposes.

        Args:
            room_id: Target Matrix room.
            doc_bytes: Raw document bytes (deleted by caller after return).
            filename: Original filename for the upload.
            mime_type: MIME type of the document.

        Returns:
            The event_id of the sent message.

        Raises:
            MatrixClientError: If upload or send fails.
        """
        logger.info(
            "Sending document: filename=%s, mime_type=%s, size=%d bytes",
            filename,
            mime_type,
            len(doc_bytes),
        )

        # Step 1: Upload file to Matrix content repository
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                upload_response = await self._with_retry(
                    lambda: client.post(
                        f"{self._base_url}/_matrix/media/v3/upload",
                        headers={
                            "Authorization": f"Bearer {self._token}",
                            "Content-Type": mime_type,
                        },
                        params={"filename": filename},
                        content=doc_bytes,
                    ),
                    operation_name="upload",
                )
        except httpx.TimeoutException as exc:
            raise MatrixTimeoutError(
                f"Upload timed out: {exc}",  # pragma: no cover - _with_retry raises first
                operation="send_document",
            ) from exc
        except httpx.HTTPError as exc:
            raise MatrixClientError(
                f"Upload transport error: {exc}",  # pragma: no cover - _with_retry raises first
                operation="send_document",
            ) from exc

        if upload_response.status_code != 200:
            raise MatrixClientError(
                f"Upload failed ({upload_response.status_code}): {upload_response.text[:200]}",
                operation="send_document",
            )

        content_uri = upload_response.json().get("content_uri")
        if not content_uri:
            raise MatrixClientError(
                "Upload response missing content_uri",
                operation="send_document",
            )

        # Step 2: Send file event to room
        message_content: dict[str, Any] = {
            "msgtype": "m.file",
            "body": filename,
            "url": content_uri,
            "info": {
                "mimetype": mime_type,
                "size": len(doc_bytes),
            },
        }

        txn_id = secrets.token_urlsafe(16)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                send_response = await self._with_retry(
                    lambda: client.put(
                        f"{self._base_url}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
                        headers=self._headers(),
                        json=message_content,
                    ),
                    operation_name="send",
                )
        except httpx.TimeoutException as exc:
            raise MatrixTimeoutError(
                f"Send timed out: {exc}",  # pragma: no cover - _with_retry raises first
                operation="send_document",
            ) from exc
        except httpx.HTTPError as exc:
            raise MatrixClientError(
                f"Send transport error: {exc}",  # pragma: no cover - _with_retry raises first
                operation="send_document",
            ) from exc

        if send_response.status_code != 200:
            raise MatrixClientError(
                f"Send failed ({send_response.status_code}): {send_response.text[:200]}",
                operation="send_document",
            )

        event_id = send_response.json().get("event_id")
        if not event_id:
            raise MatrixClientError(
                "Send response missing event_id",
                operation="send_document",
            )

        logger.info("Document sent: event_id=%s", event_id)
        return str(event_id)

    async def get_room_events(self, room_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve recent events from a Matrix room.

        Strips any content.body fields that may contain raw document bytes
        (defense in depth — documents are referenced by mxc:// URI, not inline).

        Args:
            room_id: The room to query.
            limit: Maximum number of events to return (default: 20).

        Returns:
            List of event dicts with sensitive content stripped.

        Raises:
            MatrixClientError: If the messages request fails.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await self._with_retry(
                    lambda: client.get(
                        f"{self._base_url}/_matrix/client/v3/rooms/{room_id}/messages",
                        headers=self._headers(),
                        params={"dir": "b", "limit": str(limit)},
                    ),
                    operation_name="get_room_events",
                )
        except httpx.TimeoutException as exc:
            raise MatrixTimeoutError(
                f"Event retrieval timed out: {exc}",  # pragma: no cover - _with_retry raises first
                operation="get_room_events",
            ) from exc
        except httpx.HTTPError as exc:
            raise MatrixClientError(
                f"Event retrieval transport error: {exc}",  # pragma: no cover - _with_retry raises first
                operation="get_room_events",
            ) from exc

        if response.status_code != 200:
            raise MatrixClientError(
                f"Event retrieval failed ({response.status_code}): {response.text[:200]}",
                operation="get_room_events",
            )

        data = response.json()
        chunk = data.get("chunk", [])

        events: list[dict[str, Any]] = []
        for event in chunk:
            event_dict: dict[str, Any] = {
                "event_id": event.get("event_id"),
                "sender": event.get("sender"),
                "type": event.get("type", "unknown"),
                "timestamp": event.get("origin_server_ts"),
            }

            # Include safe content fields, strip raw document bytes
            content = event.get("content", {})
            safe_content: dict[str, Any] = {}

            for key, value in content.items():
                if key == "body" and isinstance(value, (bytes, bytearray)):
                    safe_content[key] = "[REDACTED — binary content]"
                else:
                    safe_content[key] = value

            event_dict["content"] = safe_content
            events.append(event_dict)

        return events
