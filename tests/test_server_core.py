#!/usr/bin/env python3
# pylint: disable=protected-access
"""Core Server Tests.

Test suite for core server functionality including configuration loading,
validation, and basic initialization.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, cast
from unittest.mock import Mock, patch

import pytest
import yaml


class TestServerCore:
    """Test suite for core server functionality."""

    pytestmark = pytest.mark.usefixtures("mock_env_vars")

    @staticmethod
    def _server_module() -> Any:
        """Return the azure_fhir_mcp_server.server module."""
        return importlib.import_module("azure_fhir_mcp_server.server")

    @staticmethod
    def _reload_server() -> Any:
        """Reload the server module to apply environment changes."""
        module = importlib.import_module("azure_fhir_mcp_server.server")
        return importlib.reload(module)

    @staticmethod
    def _clear_server_module() -> None:
        """Remove the server module to force a clean import on next load."""
        import sys
        sys.modules.pop("azure_fhir_mcp_server.server", None)

    @pytest.fixture
    def temp_catalog(self) -> Path:
        """Create a temporary catalog.yaml for testing."""
        catalog_data: dict[str, Any] = {
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool description",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string"}
                        }
                    }
                }
            ],
            "resources": [
                {
                    "name": "test_patient",
                    "description": "Test patient resource",
                    "uri": "fhir://Patient/{id}",
                    "resourceType": "Patient",
                    "handler": "builtin_detail"
                },
                {
                    "name": "test_patient_collection",
                    "description": "Test patient collection",
                    "uri": "fhir://Patient/{filter}",
                    "resourceType": "Patient",
                    "handler": "builtin_collection"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as handle:
            yaml.safe_dump(catalog_data, handle)
            return Path(handle.name)

    def test_config_loading_success(self, temp_catalog: Path) -> None:
        """Test successful configuration loading."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', temp_catalog):
            config = cast(dict[str, Any], server._load_config())

        assert isinstance(config, dict)
        assert "tools" in config
        assert "resources" in config
        assert len(config["tools"]) == 1
        assert len(config["resources"]) == 2

    def test_config_loading_missing_file(self) -> None:
        """Test configuration loading with missing file."""
        server = self._server_module()
        missing_path = Path("/non/existent/path/catalog.yaml")

        with patch.object(server, 'TOOLS_CONFIG_PATH', missing_path):
            with pytest.raises(FileNotFoundError, match="Catalog config not found"):
                server._load_config()

    def test_config_loading_invalid_yaml(self) -> None:
        """Test configuration loading with invalid YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as handle:
            handle.write("invalid: yaml: content: [")
            invalid_path = Path(handle.name)

        try:
            server = self._server_module()
            with patch.object(server, 'TOOLS_CONFIG_PATH', invalid_path):
                with pytest.raises(ValueError, match="Failed to load catalog config"):
                    server._load_config()
        finally:
            invalid_path.unlink()

    def test_config_loading_non_dict_yaml(self) -> None:
        """Test configuration loading with non-dict YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as handle:
            yaml.safe_dump(["not", "a", "dict"], handle)
            list_path = Path(handle.name)

        try:
            server = self._server_module()
            with patch.object(server, 'TOOLS_CONFIG_PATH', list_path):
                with pytest.raises(ValueError, match="Catalog config must be a mapping"):
                    server._load_config()
        finally:
            list_path.unlink()

    def test_tool_indexing_success(self, temp_catalog: Path) -> None:
        """Test successful tool indexing."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', temp_catalog):
            config = cast(dict[str, Any], server._load_config())
            tools = server._index_tools(config)

        assert isinstance(tools, dict)
        assert "test_tool" in tools
        assert tools["test_tool"]["description"] == "Test tool description"

    def test_tool_indexing_missing_tools_section(self) -> None:
        """Test tool indexing with missing tools section."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with pytest.raises(ValueError, match="Catalog config must contain a 'tools' list"):
                server._index_tools({"resources": []})

    def test_tool_indexing_invalid_tools_section(self) -> None:
        """Test tool indexing with invalid tools section."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with pytest.raises(ValueError, match="Catalog config 'tools' entry must be a list"):
                server._index_tools({"tools": "not_a_list"})

    def test_resource_indexing_success(self, temp_catalog: Path) -> None:
        """Test successful resource indexing."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', temp_catalog):
            config = cast(dict[str, Any], server._load_config())
            resources = cast(list[dict[str, Any]],
                             server._index_resources(config))

        assert isinstance(resources, list)
        assert len(resources) == 2
        assert resources[0]["name"] == "test_patient"

    def test_resource_indexing_missing_resources_section(self) -> None:
        """Test resource indexing with missing resources section."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with pytest.raises(ValueError, match="Catalog config must contain a 'resources' list"):
                server._index_resources({"tools": []})

    def test_resource_indexing_invalid_resources_section(self) -> None:
        """Test resource indexing with invalid resources section."""
        server = self._server_module()

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with pytest.raises(ValueError, match="Catalog config 'resources' entry must be a list"):
                server._index_resources({"resources": "not_a_list"})

    def test_compute_resource_types_success(self) -> None:
        """Test successful resource type computation."""
        server = self._server_module()
        resources = [
            {"resourceType": "Patient", "name": "patient1"},
            {"resourceType": "Observation", "name": "obs1"},
            {"resourceType": "Patient", "name": "patient2"},
            {"resourceType": "Condition", "name": "cond1"},
        ]

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            types = server._compute_resource_types(resources)

        assert types == ["Patient", "Observation", "Condition"]

    def test_compute_resource_types_empty_list(self) -> None:
        """Test resource type computation with empty list."""
        server = self._server_module()
        resources: List[Dict[str, Any]] = []

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            with pytest.raises(ValueError, match="Catalog config 'resources' entries must declare resourceType"):
                server._compute_resource_types(resources)

    def test_compute_resource_types_missing_resource_type(self) -> None:
        """Test resource type computation with missing resourceType."""
        server = self._server_module()
        resources = [
            {"name": "patient1"},
            {"resourceType": "Observation", "name": "obs1"},
        ]

        with patch.object(server, 'TOOLS_CONFIG_PATH', Mock()):
            types = server._compute_resource_types(resources)

        assert types == ["Observation"]

    def test_environment_validation_invalid_port(self, mock_env_vars: Dict[str, str]) -> None:
        """Test environment validation with invalid port."""
        env_vars = dict(mock_env_vars)
        env_vars["FASTMCP_HTTP_PORT"] = "not_a_number"

        with patch.dict(os.environ, env_vars, clear=True):
            self._clear_server_module()
            with pytest.raises(ValueError, match="FASTMCP_HTTP_PORT must be a valid integer"):
                self._server_module()

        self._clear_server_module()
        self._reload_server()

    def test_environment_validation_oauth_without_http(self, mock_env_vars: Dict[str, str]) -> None:
        """Test environment validation with OAuth proxy but no HTTP transport."""
        env_vars = dict(mock_env_vars)
        env_vars["USE_FAST_MCP_OAUTH_PROXY"] = "true"
        env_vars["HTTP_TRANSPORT"] = "false"

        with patch.dict(os.environ, env_vars, clear=True):
            self._clear_server_module()
            with pytest.raises(ValueError, match="When USE_FAST_MCP_OAUTH_PROXY is true, HTTP_TRANSPORT must also be true"):
                self._server_module()

        self._clear_server_module()
        self._reload_server()

    def test_metadata_attachment_tool(self) -> None:
        """Test metadata attachment for tools."""
        server = self._server_module()
        mock_func = Mock()
        metadata: dict[str, Any] = {
            "name": "test_tool",
            "description": "Test description",
            "inputSchema": {"type": "object"},
        }

        with patch.object(server, 'TOOL_METADATA', {"test_tool": metadata}):
            server._attach_tool_metadata("test_tool", mock_func)

        assert hasattr(mock_func, "__mcp_tool_config__")
        assert mock_func.__mcp_tool_config__ == metadata

    def test_metadata_attachment_tool_not_found(self) -> None:
        """Test metadata attachment for non-existent tool."""
        server = self._server_module()
        mock_func = Mock()

        with patch.object(server, 'TOOL_METADATA', {}):
            server._attach_tool_metadata("non_existent_tool", mock_func)

        assert not hasattr(mock_func, "__mcp_tool_config__")

    def test_metadata_attachment_resource(self) -> None:
        """Test metadata attachment for resources."""
        server = self._server_module()
        mock_func = Mock()
        uri = "fhir://Patient/{id}"
        metadata = {
            "name": "test_patient",
            "description": "Test patient resource",
            "uri": uri,
        }

        with patch.object(server, 'RESOURCE_METADATA_BY_URI', {uri: metadata}):
            server._attach_resource_metadata(uri, mock_func)

        assert hasattr(mock_func, "__mcp_resource_config__")
        assert mock_func.__mcp_resource_config__ == metadata

    def test_metadata_attachment_resource_not_found(self) -> None:
        """Test metadata attachment for non-existent resource."""
        server = self._server_module()
        mock_func = Mock()

        with patch.object(server, 'RESOURCE_METADATA_BY_URI', {}):
            server._attach_resource_metadata(
                "fhir://NonExistent/{id}", mock_func)

        assert not hasattr(mock_func, "__mcp_resource_config__")

    def test_derive_default_scope_success(self) -> None:
        """Test deriving default scope from FHIR URL."""
        server = self._server_module()

        with patch.object(server, 'FHIR_URL', 'https://mock-fhir-server.example.com'):
            scope = server._derive_default_scope()

        assert scope == 'https://mock-fhir-server.example.com/.default'

    def test_derive_default_scope_with_trailing_slash(self) -> None:
        """Test deriving default scope with trailing slash in FHIR URL."""
        server = self._server_module()

        with patch.object(server, 'FHIR_URL', 'https://mock-fhir-server.example.com/'):
            scope = server._derive_default_scope()

        assert scope == 'https://mock-fhir-server.example.com/.default'

    def test_derive_default_scope_no_url(self) -> None:
        """Test deriving default scope with no FHIR URL."""
        server = self._server_module()

        with patch.object(server, 'FHIR_URL', None):
            with pytest.raises(ValueError, match="FHIR_URL is not configured"):
                server._derive_default_scope()

    def test_get_fhir_scopes_with_override(self) -> None:
        """Test getting FHIR scopes with override."""
        server = self._server_module()

        with patch.object(server, 'FHIR_SCOPE_OVERRIDE', 'scope1 scope2 scope3'):
            scopes = server._get_fhir_scopes()

        assert scopes == ['scope1', 'scope2', 'scope3']

    def test_get_fhir_scopes_without_override(self) -> None:
        """Test getting FHIR scopes without override."""
        server = self._server_module()

        with patch.object(server, 'FHIR_SCOPE_OVERRIDE', None):
            with patch.object(server, '_derive_default_scope', return_value='default_scope'):
                scopes = server._get_fhir_scopes()

        assert scopes == ['default_scope']

    def test_get_fhir_scopes_empty_override(self) -> None:
        """Test getting FHIR scopes with empty override."""
        server = self._server_module()

        with patch.object(server, 'FHIR_SCOPE_OVERRIDE', '   '):
            with patch.object(server, '_derive_default_scope', return_value='default_scope'):
                scopes = server._get_fhir_scopes()

        assert scopes == ['default_scope']

    def teardown_method(self, _method: Any) -> None:
        """Clean up temporary files created during tests."""
        for tmp_file in Path("/tmp").glob("tmp*.yaml"):
            try:
                tmp_file.unlink()
            except (OSError, FileNotFoundError):
                pass
