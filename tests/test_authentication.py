#!/usr/bin/env python3
# pylint: disable=protected-access
"""
Authentication and Token Management Tests

Test suite for MSAL authentication, OAuth token handling, and FHIR token acquisition.
"""

from __future__ import annotations

import importlib
import os
from typing import Any
from unittest.mock import Mock, patch

import pytest


class TestAuthentication:
    """Test suite for authentication and token management."""

    pytestmark = pytest.mark.usefixtures("mock_env_vars")

    @staticmethod
    def _server_module() -> Any:
        """Return the azure_fhir_mcp_server.server module."""
        return importlib.import_module("azure_fhir_mcp_server.server")

    @pytest.fixture(autouse=True)
    def reset_msal_state(self):
        """Reset MSAL global state before each test."""
        server = self._server_module()

        with patch.object(server, '_MSAL_APP', None):
            yield

    @pytest.fixture
    def mock_msal_app(self):
        """Create a mock MSAL application."""
        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }
        mock_app.acquire_token_on_behalf_of.return_value = {
            "access_token": "test_obo_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }
        return mock_app

    def test_get_confidential_client_success(self) -> None:
        """Test successful MSAL confidential client creation."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, '_MSAL_APP', None):
                with patch('msal.ConfidentialClientApplication') as mock_msal_class:
                    mock_app = Mock()
                    mock_msal_class.return_value = mock_app

                    client = server._get_confidential_client()

                    assert client == mock_app
                    mock_msal_class.assert_called_once()

    def test_get_confidential_client_missing_env_vars(self, mock_env_vars: dict[str, str]) -> None:
        """Test MSAL client creation with missing environment variables."""
        # Remove required environment variables
        env_vars = dict(mock_env_vars)
        del env_vars["tenantId"]

        server = self._server_module()

        with patch.dict(os.environ, env_vars, clear=True):
            with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
                with pytest.raises(EnvironmentError, match="MSAL client requires tenantId, clientId, clientSecret env vars"):
                    server._get_confidential_client()

    def test_get_confidential_client_singleton(self) -> None:
        """Test that confidential client is a singleton."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, '_MSAL_APP', None):
                with patch('msal.ConfidentialClientApplication') as mock_msal_class:
                    mock_app = Mock()
                    mock_msal_class.return_value = mock_app

                    client1 = server._get_confidential_client()
                    client2 = server._get_confidential_client()

                    assert client1 == client2
                    assert mock_msal_class.call_count == 1

    def test_obo_exchange_success(self, mock_msal_app: Mock) -> None:
        """Test successful On-Behalf-Of token exchange."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, '_get_confidential_client', return_value=mock_msal_app):
                with patch.object(server, '_get_fhir_scopes', return_value=['test_scope']):
                    token = server._obo_exchange("user_token")

                    assert token == "test_obo_token"
                    mock_msal_app.acquire_token_on_behalf_of.assert_called_once_with(
                        user_assertion="user_token",
                        scopes=['test_scope']
                    )

    def test_obo_exchange_failure(self, mock_msal_app: Mock) -> None:
        """Test failed On-Behalf-Of token exchange."""
        mock_msal_app.acquire_token_on_behalf_of.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
            "correlation_id": "test-correlation-id"
        }

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, '_get_confidential_client', return_value=mock_msal_app):
                with patch.object(server, '_get_fhir_scopes', return_value=['test_scope']):
                    with pytest.raises(RuntimeError, match="OBO token exchange failed via MSAL"):
                        server._obo_exchange("user_token")

    @pytest.mark.asyncio
    async def test_get_fhir_token_client_credentials_success(self, mock_msal_app: Mock, mock_fastmcp_context: Mock) -> None:
        """Test successful FHIR token acquisition via client credentials."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', False):
                with patch.object(server, '_get_confidential_client', return_value=mock_msal_app):
                    with patch.object(server, '_get_fhir_scopes', return_value=['test_scope']):
                        token = await server.get_fhir_token(mock_fastmcp_context)

                        assert token == "test_access_token"
                        mock_msal_app.acquire_token_for_client.assert_called_once_with(
                            scopes=['test_scope']
                        )

    @pytest.mark.asyncio
    async def test_get_fhir_token_client_credentials_failure(self, mock_msal_app: Mock, mock_fastmcp_context: Mock) -> None:
        """Test failed FHIR token acquisition via client credentials."""
        mock_msal_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Client authentication failed"
        }

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', False):
                with patch.object(server, '_get_confidential_client', return_value=mock_msal_app):
                    with patch.object(server, '_get_fhir_scopes', return_value=['test_scope']):
                        with pytest.raises(RuntimeError, match="Failed to obtain FHIR token via MSAL client credentials"):
                            await server.get_fhir_token(mock_fastmcp_context)

    @pytest.mark.asyncio
    async def test_get_fhir_token_oauth_success(self, mock_fastmcp_context: Mock) -> None:
        """Test successful FHIR token acquisition via OAuth proxy."""
        mock_user_token = Mock()
        mock_user_token.token = "user_access_token"

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', True):
                with patch('fastmcp.server.dependencies.get_access_token', return_value=mock_user_token):
                    with patch.object(server, '_obo_exchange', return_value="obo_token"):
                        token = await server.get_fhir_token(mock_fastmcp_context)

                        assert token == "obo_token"
                        mock_fastmcp_context.info.assert_called_with(
                            "Using On-Behalf-Of (OBO) flow to obtain FHIR token"
                        )

    @pytest.mark.asyncio
    async def test_get_fhir_token_oauth_no_token(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR token acquisition with no OAuth token available."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', True):
                with patch('fastmcp.server.dependencies.get_access_token', return_value=None):
                    with pytest.raises(RuntimeError, match="No authentication token available"):
                        await server.get_fhir_token(mock_fastmcp_context)

                    mock_fastmcp_context.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_fhir_token_oauth_invalid_token(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR token acquisition with invalid OAuth token."""
        mock_user_token = Mock()
        mock_user_token.token = None

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', True):
                with patch('fastmcp.server.dependencies.get_access_token', return_value=mock_user_token):
                    with pytest.raises((ValueError, RuntimeError)):
                        await server.get_fhir_token(mock_fastmcp_context)

    @pytest.mark.asyncio
    async def test_get_fhir_token_oauth_string_token(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR token acquisition with string OAuth token."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', True):
                with patch('fastmcp.server.dependencies.get_access_token', return_value="string_token"):
                    with patch.object(server, '_obo_exchange', return_value="obo_token"):
                        token = await server.get_fhir_token(mock_fastmcp_context)

                        assert token == "obo_token"

    @pytest.mark.asyncio
    async def test_get_fhir_token_oauth_obo_failure(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR token acquisition with OBO exchange failure."""
        mock_user_token = Mock()
        mock_user_token.token = "user_access_token"

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', True):
                with patch('fastmcp.server.dependencies.get_access_token', return_value=mock_user_token):
                    with patch.object(server, '_obo_exchange', side_effect=RuntimeError("OBO failed")):
                        with pytest.raises(RuntimeError, match="OBO failed|Error obtaining OAuth/OBO token"):
                            await server.get_fhir_token(mock_fastmcp_context)

                        mock_fastmcp_context.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_fhir_token_oauth_import_error(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR token acquisition with import error for FastMCP dependencies."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', True):
                with patch('fastmcp.server.dependencies.get_access_token', side_effect=ImportError("FastMCP not available")):
                    with pytest.raises((RuntimeError, ImportError)):
                        await server.get_fhir_token(mock_fastmcp_context)

    @pytest.mark.asyncio
    async def test_get_fhir_token_client_credentials_exception(self, mock_msal_app: Mock, mock_fastmcp_context: Mock) -> None:
        """Test FHIR token acquisition with client credentials exception."""
        mock_msal_app.acquire_token_for_client.side_effect = Exception(
            "Network error")

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', False):
                with patch.object(server, '_get_confidential_client', return_value=mock_msal_app):
                    with patch.object(server, '_get_fhir_scopes', return_value=['test_scope']):
                        with pytest.raises((RuntimeError, Exception)):
                            await server.get_fhir_token(mock_fastmcp_context)

                        mock_fastmcp_context.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_fhir_token_without_context(self, mock_msal_app: Mock) -> None:
        """Test FHIR token acquisition without context."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'USE_FAST_MCP_OAUTH_PROXY', False):
                with patch.object(server, '_get_confidential_client', return_value=mock_msal_app):
                    with patch.object(server, '_get_fhir_scopes', return_value=['test_scope']):
                        token = await server.get_fhir_token(None)

                        assert token == "test_access_token"
