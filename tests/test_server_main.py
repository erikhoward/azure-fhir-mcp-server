#!/usr/bin/env python3
# pylint: disable=protected-access
"""
Server Main and Initialization Tests

Test suite for server initialization, main function execution,
and HTTP/stdio transport configurations.
"""

import importlib
import os
import sys
from unittest.mock import Mock, patch

import pytest


class TestServerMain:
    """Test suite for server main functionality."""

    module_name = 'azure_fhir_mcp_server.server'
    pytestmark = pytest.mark.usefixtures("mock_env_vars")

    @classmethod
    def _get_server_module(cls):
        """Return the server module without reloading it."""
        return sys.modules.get(cls.module_name) or importlib.import_module(cls.module_name)

    @classmethod
    def _reload_server_module(cls):
        """Reload the server module to pick up patched environment variables."""
        module = cls._get_server_module()
        return importlib.reload(module)

    @pytest.fixture
    def mock_mcp_server(self) -> Mock:
        """Create a mock MCP server."""
        mock_mcp = Mock()
        mock_mcp.run = Mock()
        return mock_mcp

    def test_main_stdio_transport(self, mock_mcp_server: Mock) -> None:
        """Test main function with stdio transport."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server.HTTP_TRANSPORT', False):
                with patch('azure_fhir_mcp_server.server.mcp', mock_mcp_server):
                    server_module = self._get_server_module()

                    server_module.main()

                    mock_mcp_server.run.assert_called_once_with()

    def test_main_http_transport(self, mock_mcp_server: Mock) -> None:
        """Test main function with HTTP transport."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server.HTTP_TRANSPORT', True):
                with patch('azure_fhir_mcp_server.server.FASTMCP_HTTP_PORT', 9002):
                    with patch('azure_fhir_mcp_server.server.mcp', mock_mcp_server):
                        server_module = self._get_server_module()

                        server_module.main()

                        mock_mcp_server.run.assert_called_once_with(
                            transport="http",
                            port=9002
                        )

    def test_server_initialization_oauth_mode(self, mock_env_vars: dict[str, str]) -> None:
        """Test server initialization in OAuth mode."""
        env_vars = dict(mock_env_vars)
        env_vars["USE_FAST_MCP_OAUTH_PROXY"] = "true"
        env_vars["HTTP_TRANSPORT"] = "true"

        with patch.dict(os.environ, env_vars, clear=True):
            with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                with patch('fastmcp.server.auth.providers.azure.AzureProvider') as mock_azure_provider:
                    with patch('fastmcp.FastMCP') as mock_fastmcp:
                        mock_provider_instance = Mock()
                        mock_azure_provider.return_value = mock_provider_instance

                        # Import after setting up patches
                        self._reload_server_module()

                        mock_fastmcp.assert_called_once_with(
                            name="Azure FHIR MCP Server",
                            auth=mock_provider_instance
                        )

    def test_server_initialization_client_credentials_mode(self) -> None:
        """Test server initialization in client credentials mode."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('fastmcp.FastMCP') as mock_fastmcp:
                # Import after setting up patches
                self._reload_server_module()

                mock_fastmcp.assert_called_once_with("FHIR MCP Server")

    def test_azure_provider_configuration(self, mock_env_vars: dict[str, str]) -> None:
        """Test Azure provider configuration with all parameters."""
        env_vars = dict(mock_env_vars)
        env_vars.update({
            "USE_FAST_MCP_OAUTH_PROXY": "true",
            "HTTP_TRANSPORT": "true",
            "FASTMCP_SERVER_AUTH_AZURE_BASE_URL": "http://custom:8080",
            "FASTMCP_SERVER_AUTH_AZURE_REDIRECT_PATH": "/custom/callback",
            "FASTMCP_SERVER_AUTH_AZURE_IDENTIFIER_URI": "api://custom-client-id",
            "FASTMCP_SERVER_AUTH_AZURE_REQUIRED_SCOPES": "custom_scope access_scope",
            "FASTMCP_SERVER_AUTH_AZURE_ADDITIONAL_AUTHORIZE_SCOPES": "fhir_scope admin_scope"
        })

        with patch.dict(os.environ, env_vars, clear=True):
            with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                with patch('fastmcp.server.auth.providers.azure.AzureProvider') as mock_azure_provider:
                    with patch('fastmcp.FastMCP'):
                        # Import after setting up patches
                        self._reload_server_module()

                        mock_azure_provider.assert_called_once_with(
                            client_id="mock-client-id",
                            client_secret="mock-client-secret",
                            tenant_id="mock-tenant-id",
                            base_url="http://custom:8080",
                            redirect_path="/custom/callback",
                            identifier_uri="api://custom-client-id",
                            required_scopes=["custom_scope", "access_scope"],
                            additional_authorize_scopes=[
                                "fhir_scope", "admin_scope"]
                        )

    def test_azure_provider_default_configuration(self, mock_env_vars: dict[str, str]) -> None:
        """Test Azure provider configuration with default parameters."""
        env_vars = dict(mock_env_vars)
        env_vars.update({
            "USE_FAST_MCP_OAUTH_PROXY": "true",
            "HTTP_TRANSPORT": "true"
        })

        with patch.dict(os.environ, env_vars, clear=True):
            with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                with patch('fastmcp.server.auth.providers.azure.AzureProvider') as mock_azure_provider:
                    with patch('fastmcp.FastMCP'):
                        # Import after setting up patches
                        self._reload_server_module()

                        mock_azure_provider.assert_called_once_with(
                            client_id="mock-client-id",
                            client_secret="mock-client-secret",
                            tenant_id="mock-tenant-id",
                            base_url="http://localhost:9002",
                            redirect_path="/auth/callback",
                            identifier_uri="api://mock-client-id",
                            required_scopes=["user_impersonation"],
                            additional_authorize_scopes=None
                        )

    def test_server_logging_configuration(self) -> None:
        """Test that server logging is properly configured."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('logging.basicConfig') as mock_logging_config:
                # Import after setting up patches
                self._reload_server_module()

                mock_logging_config.assert_called_once()
                _, kwargs = mock_logging_config.call_args
                assert 'level' in kwargs
                assert 'format' in kwargs

    def test_msal_authority_configuration(self, mock_env_vars: dict[str, str]) -> None:
        """Test MSAL authority configuration with custom authority."""
        env_vars = dict(mock_env_vars)
        env_vars["MSAL_AUTHORITY"] = "https://login.microsoftonline.com/custom-tenant"

        with patch.dict(os.environ, env_vars, clear=True):
            with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                with patch('msal.ConfidentialClientApplication') as mock_msal:
                    server_module = self._reload_server_module()

                    server_module._get_confidential_client()

                    mock_msal.assert_called_once()
                    _, kwargs = mock_msal.call_args
                    assert kwargs['authority'] == "https://login.microsoftonline.com/custom-tenant"

    def test_msal_default_authority_configuration(self, mock_env_vars: dict[str, str]) -> None:
        """Test MSAL authority configuration with default authority."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._MSAL_APP', None):  # Reset global state
                with patch('msal.ConfidentialClientApplication') as mock_msal:
                    server_module = self._reload_server_module()

                    server_module._get_confidential_client()

                    mock_msal.assert_called_once()
                    _, kwargs = mock_msal.call_args
                    expected_authority = f"https://login.microsoftonline.com/{mock_env_vars['tenantId']}"
                    assert kwargs['authority'] == expected_authority

    def test_environment_variable_loading(self) -> None:
        """Test that environment variables are properly loaded."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            # Import after setting up patches
            server_module = self._reload_server_module()

            FASTMCP_HTTP_PORT = server_module.FASTMCP_HTTP_PORT
            FHIR_URL = server_module.FHIR_URL
            HTTP_TRANSPORT = server_module.HTTP_TRANSPORT
            USE_FAST_MCP_OAUTH_PROXY = server_module.USE_FAST_MCP_OAUTH_PROXY

            assert FHIR_URL == "https://mock-fhir-server.example.com"
            assert USE_FAST_MCP_OAUTH_PROXY is False
            assert HTTP_TRANSPORT is False
            assert FASTMCP_HTTP_PORT == 9002

    def test_boolean_environment_variable_parsing(self, mock_env_vars: dict[str, str]) -> None:
        """Test boolean environment variable parsing."""
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("", False),
            ("1", False),  # Should be False since it's not "true"
            ("yes", False)  # Should be False since it's not "true"
        ]

        for value, expected in test_cases:
            env_vars = dict(mock_env_vars)
            env_vars["HTTP_TRANSPORT"] = value

            with patch.dict(os.environ, env_vars, clear=True):
                with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                    # Import after setting up patches
                    server_module = self._reload_server_module()
                    actual_transport = server_module.HTTP_TRANSPORT
                    assert actual_transport == expected, (
                        f"Failed for value '{value}', expected {expected}, got {actual_transport}"
                    )

    def test_port_validation_edge_cases(self, mock_env_vars: dict[str, str]) -> None:
        """Test port validation with edge cases."""
        valid_ports = ["1", "80", "9002", "65535"]

        for port in valid_ports:
            env_vars = dict(mock_env_vars)
            env_vars["FASTMCP_HTTP_PORT"] = port

            with patch.dict(os.environ, env_vars, clear=True):
                with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                    # Import should succeed
                    server_module = self._reload_server_module()
                    assert server_module.FASTMCP_HTTP_PORT == int(port)

    def test_fhir_scope_override_parsing(self) -> None:
        """Test FHIR scope override parsing."""
        test_cases = [
            ("scope1", ["scope1"]),
            ("scope1 scope2", ["scope1", "scope2"]),
            ("scope1  scope2   scope3", [
             "scope1", "scope2", "scope3"]),  # Multiple spaces
            # Leading/trailing spaces
            ("   scope1   scope2   ", ["scope1", "scope2"]),
        ]

        for scope_override, expected in test_cases:
            with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                with patch('azure_fhir_mcp_server.server.FHIR_SCOPE_OVERRIDE', scope_override):
                    server_module = self._get_server_module()

                    scopes = server_module._get_fhir_scopes()
                    assert scopes == expected

        # Test empty/None cases that should use default
        empty_cases: list[str | None] = ["", "   ", None]
        for scope_override in empty_cases:
            with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
                with patch('azure_fhir_mcp_server.server.FHIR_SCOPE_OVERRIDE', scope_override):
                    server_module = self._get_server_module()

                    scopes = server_module._get_fhir_scopes()
                    assert len(scopes) == 1
                    assert scopes[0].endswith("/.default")
