#!/usr/bin/env python3
# pylint: disable=protected-access
"""
FHIR API Integration Tests

Simple test suite for FHIR API integration.
"""

import importlib
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests


class TestFhirApiIntegration:
    """Test suite for FHIR API integration."""

    pytestmark = pytest.mark.usefixtures("mock_env_vars")

    @staticmethod
    def _server_module() -> Any:
        """Return the azure_fhir_mcp_server.server module."""
        return importlib.import_module("azure_fhir_mcp_server.server")

    @pytest.mark.asyncio
    async def test_fetch_fhir_resource_success(self, mock_fastmcp_context: Mock) -> None:
        """Test successful FHIR resource fetching."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resourceType": "Patient", "id": "test-patient"}

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'FHIR_URL', 'https://mock-fhir-server.example.com'):
                with patch.object(server, 'get_fhir_token', AsyncMock(return_value="test_token")):
                    with patch('requests.get', return_value=mock_response) as mock_get:
                        result = await server._fetch_fhir_resource("Patient", mock_fastmcp_context, "test-id")

        assert result == {"resourceType": "Patient", "id": "test-patient"}
        mock_get.assert_called_once_with(
            "https://mock-fhir-server.example.com/Patient/test-id",
            headers={"Authorization": "Bearer test_token"},
            timeout=30
        )

    @pytest.mark.asyncio
    async def test_fetch_fhir_resource_404_error(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR resource fetching with 404 error."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 404

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'FHIR_URL', 'https://mock-fhir-server.example.com'):
                with patch.object(server, 'get_fhir_token', AsyncMock(return_value="test_token")):
                    with patch('requests.get', return_value=mock_response):
                        result = await server._fetch_fhir_resource("Patient", mock_fastmcp_context, "nonexistent-id")

        assert result == {}
        mock_fastmcp_context.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_handling(self, mock_fastmcp_context: Mock) -> None:
        """Test FHIR resource fetching with network error."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'FHIR_URL', 'https://mock-fhir-server.example.com'):
                with patch.object(server, 'get_fhir_token', AsyncMock(return_value="test_token")):
                    with patch('requests.get', side_effect=requests.RequestException("Network error")):
                        result = await server._fetch_fhir_resource("Patient", mock_fastmcp_context)

        assert result == {}
        mock_fastmcp_context.error.assert_called_once()
