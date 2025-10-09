#!/usr/bin/env python3
# pylint: disable=protected-access
"""
FHIR Resource Handler Tests

Test suite for FHIR resource handlers including builtin collection and detail handlers,
custom handlers, and resource registration.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestResourceHandlers:
    """Test suite for FHIR resource handlers."""
    pytestmark = pytest.mark.usefixtures("mock_env_vars")

    @staticmethod
    def _server_module() -> Any:
        """Return the azure_fhir_mcp_server.server module."""
        return importlib.import_module("azure_fhir_mcp_server.server")

    @staticmethod
    def _identity(handler: Any) -> Any:
        """Return handler unchanged to mimic decorator behavior for mocks."""
        return handler

    @pytest.fixture
    def mock_fetch_fhir_resource(self):
        """Mock the _fetch_fhir_resource function."""
        return AsyncMock(return_value={"resourceType": "Patient", "id": "test-patient"})

    @pytest.fixture
    def mock_fetch_fhir_resource_with_search(self):
        """Mock the _fetch_fhir_resource_with_search function."""
        return AsyncMock(return_value={
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "patient1"}},
                {"resource": {"resourceType": "Patient", "id": "patient2"}}
            ]
        })

    def test_make_builtin_detail_handler_success(self) -> None:
        """Test successful creation of builtin detail handler."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()

            entry = {
                "name": "test_patient_detail",
                "description": "Test patient detail handler"
            }

            handler = server._make_builtin_resource_handler(
                "Patient", "detail", entry)

            assert callable(handler)
            assert handler.__name__ == "test_patient_detail"
            assert handler.__doc__ == "Test patient detail handler"

    def test_make_builtin_collection_handler_success(self) -> None:
        """Test successful creation of builtin collection handler."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()

            entry = {
                "name": "test_patient_collection",
                "description": "Test patient collection handler"
            }

            handler = server._make_builtin_resource_handler(
                "Patient", "collection", entry)

            assert callable(handler)
            assert handler.__name__ == "test_patient_collection"
            assert handler.__doc__ == "Test patient collection handler"

    def test_make_builtin_handler_missing_resource_type(self) -> None:
        """Test builtin handler creation with missing resource type."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()

            entry = {"name": "test_handler"}

            with pytest.raises(ValueError, match="resourceType is required for builtin resource handlers"):
                server._make_builtin_resource_handler("", "detail", entry)

    def test_make_builtin_handler_invalid_mode(self) -> None:
        """Test builtin handler creation with invalid mode."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()

            entry = {"name": "test_handler"}

            with pytest.raises(ValueError, match="Unknown builtin resource handler mode"):
                server._make_builtin_resource_handler(
                    "Patient", "invalid_mode", entry)

    def test_make_builtin_handler_default_name(self) -> None:
        """Test builtin handler creation with default name."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()

            entry = {}  # No name provided

            handler = server._make_builtin_resource_handler(
                "Patient", "detail", entry)

            assert handler.__name__ == "get_patient_detail"

    @pytest.mark.asyncio
    async def test_builtin_detail_handler_execution(self, mock_fastmcp_context: Mock, mock_fetch_fhir_resource: AsyncMock) -> None:
        """Test execution of builtin detail handler."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._fetch_fhir_resource', mock_fetch_fhir_resource):
                server = self._server_module()

                entry = {"name": "test_patient_detail"}
                handler = server._make_builtin_resource_handler(
                    "Patient", "detail", entry)

                result = await handler("test-id", mock_fastmcp_context)

                assert result == {
                    "resourceType": "Patient", "id": "test-patient"}
                mock_fetch_fhir_resource.assert_called_once_with(
                    "Patient", mock_fastmcp_context, resource_id="test-id")

    @pytest.mark.asyncio
    async def test_builtin_collection_handler_execution_no_filter(self, mock_fastmcp_context: Mock, mock_fetch_fhir_resource_with_search: AsyncMock) -> None:
        """Test execution of builtin collection handler without filter."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._fetch_fhir_resource_with_search', mock_fetch_fhir_resource_with_search):
                server = self._server_module()

                entry = {"name": "test_patient_collection"}
                handler = server._make_builtin_resource_handler(
                    "Patient", "collection", entry)

                result = await handler("", mock_fastmcp_context)

                expected_bundle: Dict[str, Any] = {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"resourceType": "Patient", "id": "patient1"}},
                        {"resource": {"resourceType": "Patient", "id": "patient2"}}
                    ]
                }
                assert result == expected_bundle
                mock_fetch_fhir_resource_with_search.assert_called_once_with(
                    "Patient", mock_fastmcp_context, {})

    @pytest.mark.asyncio
    async def test_builtin_collection_handler_execution_with_filter(self, mock_fastmcp_context: Mock, mock_fetch_fhir_resource_with_search: AsyncMock) -> None:
        """Test execution of builtin collection handler with filter."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._fetch_fhir_resource_with_search', mock_fetch_fhir_resource_with_search):
                server = self._server_module()

                entry = {"name": "test_patient_collection"}
                handler = server._make_builtin_resource_handler(
                    "Patient", "collection", entry)

                await handler("name=Smith&gender=male", mock_fastmcp_context)

                expected_params = {"name": "Smith", "gender": "male"}
                mock_fetch_fhir_resource_with_search.assert_called_once_with(
                    "Patient", mock_fastmcp_context, expected_params)

    @pytest.mark.asyncio
    async def test_builtin_collection_handler_simple_text_filter(self, mock_fastmcp_context: Mock, mock_fetch_fhir_resource_with_search: AsyncMock) -> None:
        """Test execution of builtin collection handler with simple text filter."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._fetch_fhir_resource_with_search', mock_fetch_fhir_resource_with_search):
                server = self._server_module()

                entry = {"name": "test_patient_collection"}
                handler = server._make_builtin_resource_handler(
                    "Patient", "collection", entry)

                await handler("Smith", mock_fastmcp_context)

                expected_params = {"name": "Smith"}
                mock_fetch_fhir_resource_with_search.assert_called_once_with(
                    "Patient", mock_fastmcp_context, expected_params)

    @pytest.mark.asyncio
    async def test_builtin_collection_handler_non_patient_text_filter(self, mock_fastmcp_context: Mock, mock_fetch_fhir_resource_with_search: AsyncMock) -> None:
        """Test execution of builtin collection handler with text filter for non-Patient resource."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._fetch_fhir_resource_with_search', mock_fetch_fhir_resource_with_search):
                server = self._server_module()

                entry = {"name": "test_observation_collection"}
                handler = server._make_builtin_resource_handler(
                    "Observation", "collection", entry)

                await handler("blood pressure", mock_fastmcp_context)

                expected_params = {"_text": "blood pressure"}
                mock_fetch_fhir_resource_with_search.assert_called_once_with(
                    "Observation", mock_fastmcp_context, expected_params)

    @pytest.mark.asyncio
    async def test_builtin_collection_handler_filter_parsing_error(self, mock_fastmcp_context: Mock, mock_fetch_fhir_resource_with_search: AsyncMock) -> None:
        """Test execution of builtin collection handler with filter parsing error."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            with patch('azure_fhir_mcp_server.server._fetch_fhir_resource_with_search', mock_fetch_fhir_resource_with_search):
                with patch('urllib.parse.parse_qs', side_effect=ValueError("Parse error")):
                    server = self._server_module()

                    entry = {"name": "test_patient_collection"}
                    handler = server._make_builtin_resource_handler(
                        "Patient", "collection", entry)

                    await handler("invalid=filter&", mock_fastmcp_context)

                    # Should fall back to simple text search
                    expected_params = {"_text": "invalid=filter&"}
                    mock_fetch_fhir_resource_with_search.assert_called_once_with(
                        "Patient", mock_fastmcp_context, expected_params)
                    mock_fastmcp_context.error.assert_called()

    def test_resolve_custom_handler_success(self) -> None:
        """Test successful custom handler resolution."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()
            # Create a mock module with a mock function
            mock_module = Mock()
            mock_function = Mock()
            mock_module.test_function = mock_function

            with patch('importlib.import_module', return_value=mock_module):
                handler = server._resolve_custom_resource_handler(
                    "test.module:test_function")

                assert handler == mock_function

    def test_resolve_custom_handler_invalid_path(self) -> None:
        """Test custom handler resolution with invalid path."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()

            with pytest.raises(ValueError, match="Invalid handler path"):
                server._resolve_custom_resource_handler("invalid_path")

    def test_resolve_custom_handler_missing_module(self) -> None:
        """Test custom handler resolution with missing module."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()
            with patch('importlib.import_module', side_effect=ModuleNotFoundError("Module not found")):
                with pytest.raises(ModuleNotFoundError):
                    server._resolve_custom_resource_handler(
                        "nonexistent.module:function")

    def test_resolve_custom_handler_missing_attribute(self) -> None:
        """Test custom handler resolution with missing attribute."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()
            mock_module = Mock()
            del mock_module.nonexistent_function  # Ensure it doesn't exist

            with patch('importlib.import_module', return_value=mock_module):
                with pytest.raises(AttributeError, match="Handler 'nonexistent_function' not found"):
                    server._resolve_custom_resource_handler(
                        "test.module:nonexistent_function")

    def test_resolve_custom_handler_not_callable(self) -> None:
        """Test custom handler resolution with non-callable attribute."""
        with patch('azure_fhir_mcp_server.server.TOOLS_CONFIG_PATH'):
            server = self._server_module()
            mock_module = Mock()
            mock_module.not_a_function = "not callable"

            with patch('importlib.import_module', return_value=mock_module):
                with pytest.raises(TypeError, match="Resolved handler .* is not callable"):
                    server._resolve_custom_resource_handler(
                        "test.module:not_a_function")

    def test_register_resource_handlers_success(self) -> None:
        """Test successful resource handler registration."""
        resource_metadata = [
            {
                "uri": "fhir://Patient/{id}",
                "resourceType": "Patient",
                "handler": "builtin_detail",
                "name": "patient_detail",
                "description": "Patient detail handler"
            },
            {
                "uri": "fhir://Patient/{filter}",
                "resourceType": "Patient",
                "handler": "builtin_collection",
                "name": "patient_collection",
                "description": "Patient collection handler"
            }
        ]

        mock_mcp = Mock()
        server = self._server_module()

        mock_mcp.resource.return_value = self._identity

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'RESOURCE_METADATA', resource_metadata):
                with patch.object(server, 'RESOURCE_METADATA_BY_URI', {
                    entry.get('uri'): entry for entry in resource_metadata if entry.get('uri')
                }):
                    with patch.object(server, 'mcp', mock_mcp):
                        with patch.object(server, '_attach_resource_metadata'):
                            server._register_fhir_resource_handlers()

                            # Should register 2 handlers
                            assert mock_mcp.resource.call_count == 2

    def test_register_resource_handlers_missing_uri(self) -> None:
        """Test resource handler registration with missing URI."""
        resource_metadata = [
            {
                "resourceType": "Patient",
                "handler": "builtin_detail",
                "name": "patient_detail"
            }
        ]

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'RESOURCE_METADATA', resource_metadata):
                with pytest.raises(ValueError, match="Catalog resource entry missing 'uri'"):
                    server._register_fhir_resource_handlers()

    def test_register_resource_handlers_missing_resource_type(self) -> None:
        """Test resource handler registration with missing resource type."""
        resource_metadata = [
            {
                "uri": "fhir://Patient/{id}",
                "handler": "builtin_detail",
                "name": "patient_detail"
            }
        ]

        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'RESOURCE_METADATA', resource_metadata):
                with pytest.raises(ValueError, match="Catalog resource .* missing 'resourceType'"):
                    server._register_fhir_resource_handlers()

    def test_register_resource_handlers_custom_handler(self) -> None:
        """Test resource handler registration with custom handler."""
        resource_metadata = [
            {
                "uri": "fhir://Patient/{id}",
                "resourceType": "Patient",
                "handler": "custom.module:custom_handler",
                "name": "custom_patient_handler"
            }
        ]

        server = self._server_module()

        mock_mcp = Mock()

        mock_mcp.resource.return_value = self._identity
        mock_custom_handler = Mock()
        mock_custom_handler.__name__ = "custom_patient_handler"

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'RESOURCE_METADATA', resource_metadata):
                with patch.object(server, 'RESOURCE_METADATA_BY_URI', {
                    entry.get('uri'): entry for entry in resource_metadata if entry.get('uri')
                }):
                    with patch.object(server, 'mcp', mock_mcp):
                        with patch.object(server, '_resolve_custom_resource_handler', return_value=mock_custom_handler):
                            with patch.object(server, '_attach_resource_metadata'):
                                server._register_fhir_resource_handlers()

                                mock_mcp.resource.assert_called_once_with(
                                    "fhir://Patient/{id}")

    def test_register_resource_handlers_default_handler(self) -> None:
        """Test resource handler registration with default handler."""
        resource_metadata = [
            {
                "uri": "fhir://Patient/{filter}",
                "resourceType": "Patient",
                "name": "patient_collection"
                # No handler specified, should default to builtin_collection
            }
        ]

        server = self._server_module()

        mock_mcp = Mock()

        mock_mcp.resource.return_value = self._identity

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with patch.object(server, 'RESOURCE_METADATA', resource_metadata):
                with patch.object(server, 'RESOURCE_METADATA_BY_URI', {
                    entry.get('uri'): entry for entry in resource_metadata if entry.get('uri')
                }):
                    with patch.object(server, 'mcp', mock_mcp):
                        with patch.object(server, '_attach_resource_metadata'):
                            server._register_fhir_resource_handlers()

                            mock_mcp.resource.assert_called_once_with(
                                "fhir://Patient/{filter}")

    def test_register_resource_handlers_default_handler_new(self) -> None:
        """Legacy duplicate retained for compatibility coverage."""
        self.test_register_resource_handlers_default_handler()
