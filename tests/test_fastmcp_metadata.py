#!/usr/bin/env python3
# pylint: disable=protected-access
"""
FastMCP Metadata Validation Tests

This test suite validates that FastMCP discovers metadata correctly and that it matches
the definitions in catalog.yaml.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, cast

import pytest
import pytest_asyncio
import yaml

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestFastMCPMetadata:
    """Test suite for validating FastMCP metadata consistency with catalog.yaml."""

    @pytest.fixture
    def catalog(self) -> Dict[str, Any]:
        """Load and return the catalog.yaml configuration."""
        catalog_path = Path(__file__).parent.parent / "src" / \
            "azure_fhir_mcp_server" / "config" / "catalog.yaml"

        with open(catalog_path, 'r', encoding='utf-8') as f:
            catalog_data = yaml.safe_load(f)

        assert catalog_data is not None, "Failed to load catalog.yaml"
        catalog = cast(Dict[str, Any], catalog_data)
        assert "tools" in catalog, "catalog.yaml missing 'tools' section"
        assert "resources" in catalog, "catalog.yaml missing 'resources' section"

        return catalog

    @pytest_asyncio.fixture
    async def mcp_server(self) -> Dict[str, Any]:
        """Create and return a FastMCP server instance for testing."""
        try:
            # Import the server module
            from azure_fhir_mcp_server.server import (
                RESOURCE_METADATA,
                TOOL_METADATA,
                mcp,
            )

            return {
                "mcp": mcp,
                "tool_metadata": TOOL_METADATA,
                "resource_metadata": RESOURCE_METADATA
            }
        except ImportError as e:
            pytest.skip(f"Cannot import server module: {e}")

    def test_catalog_structure(self, catalog: Dict[str, Any]) -> None:
        """Test that catalog.yaml has the expected structure and content."""
        # Validate tools section
        assert isinstance(catalog["tools"],
                          list), "catalog.yaml tools must be a list"
        tools_list = cast(List[Dict[str, Any]], catalog["tools"])
        assert len(tools_list) > 0, "catalog.yaml must define at least one tool"

        for i, tool in enumerate(tools_list):
            assert isinstance(tool, dict), f"Tool {i} must be a dictionary"
            assert "name" in tool, f"Tool {i} missing 'name' field"
            assert "description" in tool, f"Tool {i} missing 'description' field"
            assert "inputSchema" in tool, f"Tool {i} missing 'inputSchema' field"

        # Validate resources section
        assert isinstance(catalog["resources"],
                          list), "catalog.yaml resources must be a list"
        resources_list = cast(List[Dict[str, Any]], catalog["resources"])
        assert len(
            resources_list) > 0, "catalog.yaml must define at least one resource"

        for i, resource in enumerate(resources_list):
            assert isinstance(
                resource, dict), f"Resource {i} must be a dictionary"
            assert "name" in resource, f"Resource {i} missing 'name' field"
            assert "description" in resource, f"Resource {i} missing 'description' field"
            assert "uri" in resource, f"Resource {i} missing 'uri' field"

    @pytest.mark.asyncio
    async def test_tool_metadata_consistency(self, catalog: Dict[str, Any], mcp_server: Dict[str, Any]) -> None:
        """Test that tool metadata in server matches catalog definitions."""
        tool_metadata: Dict[str, Any] = mcp_server["tool_metadata"]
        tools_list = cast(List[Dict[str, Any]], catalog["tools"])
        catalog_tools: Dict[str, Any] = {
            tool["name"]: tool for tool in tools_list}

        # Check that all catalog tools have corresponding metadata
        for tool_name, catalog_tool in catalog_tools.items():
            assert tool_name in tool_metadata, f"Missing tool metadata for '{tool_name}'"

            metadata = tool_metadata[tool_name]
            assert metadata["name"] == catalog_tool["name"]
            assert metadata["description"] == catalog_tool["description"]
            assert metadata["inputSchema"] == catalog_tool["inputSchema"]

    @pytest.mark.asyncio
    async def test_resource_metadata_consistency(self, catalog: Dict[str, Any], mcp_server: Dict[str, Any]) -> None:
        """Test that resource metadata in server matches catalog definitions."""
        resource_metadata_list: List[Dict[str, Any]
                                     ] = mcp_server["resource_metadata"]
        # Convert list to dict keyed by name for easier lookup
        resource_metadata: Dict[str, Any] = {
            item["name"]: item for item in resource_metadata_list}
        resources_list = cast(List[Dict[str, Any]], catalog["resources"])
        catalog_resources: Dict[str, Any] = {
            resource["name"]: resource for resource in resources_list}

        # Check that all catalog resources have corresponding metadata
        for resource_name, catalog_resource in catalog_resources.items():
            assert resource_name in resource_metadata, f"Missing resource metadata for '{resource_name}'"

            metadata = resource_metadata[resource_name]
            assert metadata["name"] == catalog_resource["name"]
            assert metadata["description"] == catalog_resource["description"]
            assert metadata["uri"] == catalog_resource["uri"]

    @pytest.mark.asyncio
    async def test_fastmcp_server_discovery(self, catalog: Dict[str, Any], mcp_server: Dict[str, Any]) -> None:
        """Test that FastMCP server discovery methods match catalog definitions."""
        mcp: Any = mcp_server["mcp"]

        # Test tool discovery using FastMCP methods
        try:
            discovered_tools_dict: Any = await mcp.get_tools()
            discovered_tool_names = set(discovered_tools_dict.keys())
            tools_list = cast(List[Dict[str, Any]], catalog["tools"])
            catalog_tool_names = {tool.get("name")
                                  for tool in tools_list if tool.get("name")}

            # Note: FastMCP may include additional built-in tools like 'get_user_info'
            # We check that all catalog tools are present, but allow extra ones
            for tool_name in catalog_tool_names:
                assert tool_name in discovered_tool_names, (
                    f"Catalog tool '{tool_name}' not found in FastMCP discovered tools {sorted(discovered_tool_names)}"
                )

            # Validate our main tool details from FastMCP discovery
            for tool_name, tool_obj in discovered_tools_dict.items():
                if tool_name == "search_fhir":
                    assert tool_obj.description is not None
                    assert ("FHIR Search" in str(tool_obj.description) or
                            "Azure FHIR search capabilities" in str(tool_obj.description) or
                            "Search FHIR resources" in str(tool_obj.description))
                    assert hasattr(tool_obj, 'name')
                    assert tool_obj.name == "search_fhir"

        except (AttributeError, TypeError, ValueError) as e:
            pytest.fail(f"FastMCP tool discovery failed: {e}")

        # Test resource templates discovery - this is where FastMCP exposes resource patterns
        try:
            discovered_templates_dict: Any = await mcp.get_resource_templates()
            discovered_template_uris = set(discovered_templates_dict.keys())

            # Resource templates should match the URI patterns from catalog
            resources_list = cast(List[Dict[str, Any]], catalog["resources"])
            catalog_uri_templates = {resource.get(
                "uri") for resource in resources_list if resource.get("uri")}

            assert discovered_template_uris == catalog_uri_templates, (
                f"FastMCP discovered {len(discovered_template_uris)} templates != "
                f"catalog {len(catalog_uri_templates)} URI patterns"
            )

            # Validate template details
            for template_uri, template_obj in discovered_templates_dict.items():
                assert template_uri.startswith("fhir://")
                assert "{" in template_uri and "}" in template_uri
                assert hasattr(template_obj, 'name')
                assert template_obj.name is not None

        except (AttributeError, TypeError, ValueError) as e:
            pytest.fail(f"FastMCP resource template discovery failed: {e}")

    @pytest.mark.asyncio
    async def test_fastmcp_server_metadata_attachment(self, mcp_server: Dict[str, Any]) -> None:
        """Test that FastMCP metadata attachment works correctly."""
        mcp: Any = mcp_server["mcp"]

        try:
            # Test getting server info which should include metadata
            if hasattr(mcp, 'get_server_info'):
                server_info = await mcp.get_server_info()
                assert server_info is not None

            # Test that we can introspect the server
            discovered_tools = await mcp.get_tools()
            assert len(
                discovered_tools) > 0, "FastMCP should discover at least one tool"

            discovered_templates = await mcp.get_resource_templates()
            assert len(
                discovered_templates) > 0, "FastMCP should discover resource templates"

        except (AttributeError, TypeError, ValueError) as e:
            pytest.fail(f"FastMCP metadata attachment test failed: {e}")

    @pytest.mark.asyncio
    async def test_output_detailed_metadata(self, catalog: Dict[str, Any], mcp_server: Dict[str, Any]) -> None:
        """Output detailed metadata discovered by FastMCP."""
        print("\n" + "="*60)
        print("DETAILED FASTMCP METADATA DISCOVERY")
        print("="*60)

        print("\nCATALOG SUMMARY:")
        print(f"  Tools: {len(catalog['tools'])}")
        print(f"  Resources: {len(catalog['resources'])}")

        print("\nTOOL METADATA:")
        tool_metadata: Dict[str, Any] = mcp_server["tool_metadata"]
        for tool_name, metadata in tool_metadata.items():
            print(f"  {tool_name}:")
            print(f"    Description: {metadata['description'][:100]}...")
            print(
                f"    Schema properties: {len(metadata.get('inputSchema', {}).get('properties', {}))}")

        print("\nRESOURCE METADATA:")
        resource_metadata_list: List[Dict[str, Any]
                                     ] = mcp_server["resource_metadata"]
        resource_types: Dict[str, int] = {}
        for resource_item in resource_metadata_list:
            # Extract from fhir://resource_type/...
            resource_type = resource_item['uri'].split('/')[2]
            if resource_type not in resource_types:
                resource_types[resource_type] = 0
            resource_types[resource_type] += 1

        print(f"  Total resources: {len(resource_metadata_list)}")
        print(f"  Resource types: {len(resource_types)}")
        print("  Top 10 resource types:")
        for rtype, count in sorted(resource_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {rtype}: {count}")

        # Test FastMCP Discovery and output results
        print("\nFASTMCP DISCOVERY RESULTS:")
        mcp: Any = mcp_server["mcp"]

        try:
            discovered_tools = await mcp.get_tools()
            print(f"  Tools discovered: {list(discovered_tools.keys())}")

            discovered_templates = await mcp.get_resource_templates()
            print(
                f"  Resource templates discovered: {len(discovered_templates)}")

            # Show sample template
            if discovered_templates:
                first_uri = list(discovered_templates.keys())[0]
                first_template = discovered_templates[first_uri]
                print(f"  Sample template: {first_uri}")
                print(f"    Template name: {first_template.name}")
                print(f"    Template type: {type(first_template)}")

        except (AttributeError, TypeError, ValueError, ImportError) as e:
            print(f"  FastMCP discovery failed: {e}")


if __name__ == "__main__":
    # Run this specific test file
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "-s"],
                            cwd="/workspaces/azure-fhir-mcp-server-marrobi",
                            check=False)
    sys.exit(result.returncode)
