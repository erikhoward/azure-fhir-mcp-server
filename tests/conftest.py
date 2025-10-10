#!/usr/bin/env python3
"""Shared pytest configuration and fixtures."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Ensure the src directory is importable from all tests.
_SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

_DEFAULT_ENV_VARS: dict[str, str] = {
    "fhirUrl": "https://mock-fhir-server.example.com",
    "tenantId": "mock-tenant-id",
    "clientId": "mock-client-id",
    "clientSecret": "mock-client-secret",
    "USE_FAST_MCP_OAUTH_PROXY": "false",
    "HTTP_TRANSPORT": "false",
    "FASTMCP_HTTP_PORT": "9002",
}


@pytest.fixture
def mock_env_vars() -> Iterator[dict[str, str]]:
    """Patch environment variables with default FHIR settings."""
    env_vars = dict(_DEFAULT_ENV_VARS)
    with patch.dict(os.environ, env_vars, clear=True):
        yield env_vars


@pytest.fixture
def mock_fastmcp_context() -> Mock:
    """Provide a mock FastMCP context with async logging helpers."""
    context = Mock()
    context.info = AsyncMock()
    context.error = AsyncMock()
    return context
