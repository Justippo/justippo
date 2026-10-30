# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Matrix Real Server Integration Tests - Sprint 3

Note: These tests require:
1. Real Matrix homeserver (matrix.org or self-hosted)
2. Registered OAuth application
3. Valid client credentials

Run with: uv run pytest tests/integration/test_matrix_real_server.py --matrix-server=https://matrix.org
"""

import pytest

pytestmark = pytest.mark.skip(reason="Requires real Matrix server - Sprint 3")


@pytest.mark.asyncio
async def test_real_matrix_oauth_flow():
    """Test complete OAuth flow against real Matrix homeserver."""
    # This will be implemented in Sprint 3
    # Requires: MATRIX_HOMESERVER_URL, MATRIX_CLIENT_ID, MATRIX_CLIENT_SECRET
    pass


@pytest.mark.asyncio
async def test_real_token_refresh():
    """Test token refresh against real Matrix homeserver."""
    # This will be implemented in Sprint 3
    # Tests lines 168-175 (currently at 86% coverage)
    pass


@pytest.mark.asyncio
async def test_real_room_creation():
    """Test room creation with real Matrix server."""
    # This will be implemented in Sprint 3
    # Tests actual matrix-nio client interaction
    pass


@pytest.mark.asyncio
async def test_real_document_upload():
    """Test document upload with real Matrix server."""
    # This will be implemented in Sprint 3
    # Tests encrypted file transfer
    pass
