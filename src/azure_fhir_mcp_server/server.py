import importlib
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, cast

import msal  # type: ignore[import-untyped]
import requests
import yaml
from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.server.auth.providers.azure import AzureProvider

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Read environment variables
FHIR_URL = os.environ.get("fhirUrl")
USE_FAST_MCP_OAUTH_PROXY = os.environ.get(
    "USE_FAST_MCP_OAUTH_PROXY", "false").lower() == "true"

# Explicit scope override (space-separated). If not provided we derive a default
# scope from the FHIR URL using the pattern: {FHIR_URL}/.default (AAD v2 format)
FHIR_SCOPE_OVERRIDE = os.environ.get("FHIR_SCOPE")

# Validate required environment variables
if not FHIR_URL:
    raise EnvironmentError("Missing required environment variable: fhirUrl")

HTTP_TRANSPORT = os.environ.get("HTTP_TRANSPORT", "false").lower() == "true"

if USE_FAST_MCP_OAUTH_PROXY and not HTTP_TRANSPORT:
    raise ValueError(
        "When USE_FAST_MCP_OAUTH_PROXY is true, HTTP_TRANSPORT must also be true")

fastmcp_http_port_str = os.environ.get("FASTMCP_HTTP_PORT", "9002")
if not fastmcp_http_port_str.isdigit():
    raise ValueError("FASTMCP_HTTP_PORT must be a valid integer")
FASTMCP_HTTP_PORT = int(fastmcp_http_port_str)

# Initialize MCP server with explicit Azure provider configuration
if USE_FAST_MCP_OAUTH_PROXY:
    # The AzureProvider handles Azure's token format and validation
    client_id = os.environ.get("clientId") or ""
    client_secret = os.environ.get("clientSecret") or ""
    tenant_id = os.environ.get("tenantId") or ""

    auth_provider = AzureProvider(
        client_id=client_id,  # Your Azure App Client ID
        client_secret=client_secret,  # Your Azure App Client Secret
        tenant_id=tenant_id,  # Your Azure Tenant ID (REQUIRED)
        # Must match your App registration
        base_url=os.environ.get(
            "FASTMCP_SERVER_AUTH_AZURE_BASE_URL", f"http://localhost:{FASTMCP_HTTP_PORT}"),
        redirect_path=os.environ.get(
            "FASTMCP_SERVER_AUTH_AZURE_REDIRECT_PATH", "/auth/callback"),  # Auth callback path
        identifier_uri=os.environ.get(
            # API identifier URI
            "FASTMCP_SERVER_AUTH_AZURE_IDENTIFIER_URI", f"api://{client_id}"),
        required_scopes=os.environ.get(
            # Required scopes
            "FASTMCP_SERVER_AUTH_AZURE_REQUIRED_SCOPES", "user_impersonation").split(),
        additional_authorize_scopes=os.environ.get("FASTMCP_SERVER_AUTH_AZURE_ADDITIONAL_AUTHORIZE_SCOPES", "").split(
            # Additional FHIR scopes
        ) if os.environ.get("FASTMCP_SERVER_AUTH_AZURE_ADDITIONAL_AUTHORIZE_SCOPES") else None,
    )

    mcp = FastMCP(name="Azure FHIR MCP Server", auth=auth_provider)
    logger.info(
        "FHIR MCP Server initialized with explicit Azure OAuth authentication")
else:
    # Client credentials mode: No authentication on MCP server
    mcp = FastMCP("FHIR MCP Server")
    logger.info(
        "FHIR MCP Server initialized with client credentials authentication")

TOOLS_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "catalog.yaml"


def _load_config() -> Dict[str, Any]:
    """Load and validate the catalog configuration from YAML.

    Returns:
        Dict containing 'tools' and 'resources' sections from catalog.yaml

    Raises:
        FileNotFoundError: If catalog.yaml is missing
        ValueError: If YAML is invalid or not a dict at top level
    """
    if not TOOLS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Catalog config not found at {TOOLS_CONFIG_PATH}")

    try:
        with TOOLS_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except Exception as exc:
        raise ValueError(f"Failed to load catalog config: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Catalog config must be a mapping at the top level")

    return cast(Dict[str, Any], data)


CONFIG_DATA = _load_config()


def _index_tools(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract and index tool metadata by name from catalog config.

    Args:
        config: Loaded catalog configuration dict

    Returns:
        Dict mapping tool names to their metadata entries

    Raises:
        ValueError: If 'tools' section is missing or not a list
    """
    tools_section = config.get("tools")
    if tools_section is None:
        raise ValueError("Catalog config must contain a 'tools' list")
    if not isinstance(tools_section, list):
        raise ValueError("Catalog config 'tools' entry must be a list")

    tools_list = cast(List[Dict[str, Any]], tools_section)
    metadata: Dict[str, Dict[str, Any]] = {}
    for entry in tools_list:
        name = entry.get("name")
        if not name:
            continue
        metadata[name] = entry
    return metadata


def _index_resources(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract resource entries from catalog config.

    Args:
        config: Loaded catalog configuration dict

    Returns:
        List of resource metadata entries

    Raises:
        ValueError: If 'resources' section is missing or not a list
    """
    resources_section = config.get("resources")
    if resources_section is None:
        raise ValueError("Catalog config must contain a 'resources' list")
    if not isinstance(resources_section, list):
        raise ValueError("Catalog config 'resources' entry must be a list")
    return cast(List[Dict[str, Any]], resources_section)


TOOL_METADATA = _index_tools(CONFIG_DATA)
RESOURCE_METADATA = _index_resources(CONFIG_DATA)
RESOURCE_METADATA_BY_URI = {
    entry.get("uri"): entry for entry in RESOURCE_METADATA if entry.get("uri")
}

logger.info("Loaded %d resource definitions from catalog",
            len(RESOURCE_METADATA))
logger.info("Resource URIs: %s...", list(
    RESOURCE_METADATA_BY_URI.keys())[:5])  # Show first 5


def _attach_tool_metadata(tool_name: str, func: Any) -> None:
    """Attach catalog metadata to a tool function for MCP discovery.

    Args:
        tool_name: Name of the tool in the catalog
        func: Function object to attach metadata to
    """
    metadata = TOOL_METADATA.get(tool_name)
    if not metadata:
        return
    setattr(func, "__mcp_tool_config__", metadata)


def _attach_resource_metadata(uri: str, func: Any) -> None:
    """Attach catalog metadata to a resource handler for MCP discovery.

    Args:
        uri: Resource URI pattern (e.g., 'fhir://Patient/{id}')
        func: Handler function to attach metadata to
    """
    metadata = RESOURCE_METADATA_BY_URI.get(uri)
    if not metadata:
        return
    setattr(func, "__mcp_resource_config__", metadata)


def _compute_resource_types(resource_entries: List[Dict[str, Any]]) -> List[str]:
    """Extract unique FHIR resource types from catalog entries.

    Used for validating search_fhir requests against configured resources.

    Args:
        resource_entries: List of resource metadata from catalog

    Returns:
        Ordered list of unique FHIR resource type names

    Raises:
        ValueError: If no valid resourceType declarations found
    """
    ordered_types: List[str] = []
    for entry in resource_entries:
        resource_type = entry.get("resourceType")
        if resource_type and resource_type not in ordered_types:
            ordered_types.append(resource_type)

    if not ordered_types:
        raise ValueError(
            "Catalog config 'resources' entries must declare resourceType")

    return ordered_types


FHIR_RESOURCES = _compute_resource_types(RESOURCE_METADATA)


# MSAL confidential client
_MSAL_TOKEN_CACHE = msal.SerializableTokenCache()
_MSAL_APP: Optional[msal.ConfidentialClientApplication] = None
_MSAL_APP_LOCK = Lock()


def _derive_default_scope() -> str:
    # Derive a default scope string for AAD v2 endpoint; ensure no trailing slash duplication
    if FHIR_URL is None:
        raise ValueError("FHIR_URL is not configured")
    base = FHIR_URL.rstrip('/')
    return f"{base}/.default"


def _get_fhir_scopes() -> List[str]:
    if FHIR_SCOPE_OVERRIDE:
        scopes = [scope.strip()
                  for scope in FHIR_SCOPE_OVERRIDE.split() if scope.strip()]
        if scopes:
            return scopes
    return [_derive_default_scope()]


# type: ignore[name-defined]
def _get_confidential_client() -> msal.ConfidentialClientApplication:
    global _MSAL_APP  # pylint: disable=global-statement
    with _MSAL_APP_LOCK:
        if _MSAL_APP:
            return _MSAL_APP

        msal_tenant_id = os.environ.get("tenantId")
        msal_client_id = os.environ.get("clientId")
        msal_client_secret = os.environ.get("clientSecret")
        if not all([msal_tenant_id, msal_client_id, msal_client_secret]):
            raise EnvironmentError(
                "MSAL client requires tenantId, clientId, clientSecret env vars")

        authority = os.environ.get(
            "MSAL_AUTHORITY", f"https://login.microsoftonline.com/{msal_tenant_id}")
        _MSAL_APP = msal.ConfidentialClientApplication(  # type: ignore[assignment]
            client_id=msal_client_id,
            client_credential=msal_client_secret,
            authority=authority,
            token_cache=_MSAL_TOKEN_CACHE,
        )
        logger.info(
            "Initialized MSAL confidential client for tenant %s", msal_tenant_id)
        return _MSAL_APP


def _obo_exchange(user_token: str) -> str:
    app = _get_confidential_client()
    scopes = _get_fhir_scopes()
    logger.info(
        "Performing MSAL OBO token exchange for FHIR scopes: %s", " ".join(scopes))

    result = app.acquire_token_on_behalf_of(  # type: ignore[no-untyped-call]
        user_assertion=user_token, scopes=scopes)
    result_dict = cast(Dict[str, Any], result)

    if "access_token" in result_dict:
        logger.info("Obtained OBO token for FHIR access (expires_in=%s)",
                    result_dict.get("expires_in"))
        return cast(str, result_dict["access_token"])

    error = result_dict.get("error")
    description = result_dict.get("error_description")
    correlation = result_dict.get("correlation_id")
    detail = f"{error}: {description}" if error or description else "Unknown MSAL error"
    if correlation:
        detail = f"{detail} (correlation_id={correlation})"
    raise RuntimeError(f"OBO token exchange failed via MSAL: {detail}")


async def get_fhir_token(ctx: Optional[Context] = None) -> str:
    """Get token for FHIR API access.

    Modes:
        * USE_FAST_MCP_OAUTH_PROXY: Exchange user token (Azure AD) for FHIR audience token (OBO).
        * Client credentials (default): Service-to-service token.
    """
    if USE_FAST_MCP_OAUTH_PROXY:
        try:
            from fastmcp.server.dependencies import get_access_token
            user_token_obj = get_access_token()
            if user_token_obj is None:
                error_msg = "No authentication token available - please re-authenticate"
                logger.error(error_msg)
                if ctx:
                    await ctx.error(error_msg)
                raise RuntimeError(error_msg)
            # Extract raw token string
            raw_user_token = getattr(
                user_token_obj, 'token', None) or str(user_token_obj)
            if not raw_user_token or raw_user_token == 'None':
                raise ValueError("Invalid user token format")

            if ctx:
                await ctx.info("Using On-Behalf-Of (OBO) flow to obtain FHIR token")
            token = _obo_exchange(raw_user_token)
            return token

        except Exception as e:
            error_msg = f"Error obtaining OAuth/OBO token: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            raise
    else:
        # Client credentials mode: Acquire service token for FHIR access via MSAL
        try:
            app = _get_confidential_client()
            scopes = _get_fhir_scopes()
            result = app.acquire_token_for_client(  # type: ignore[no-untyped-call]
                scopes=scopes)
            result_dict = cast(Dict[str, Any], result)

            if "access_token" not in result_dict:
                error_msg = (
                    "Failed to obtain FHIR token via MSAL client credentials: "
                    f"{result_dict.get('error', 'Unknown error')}: "
                    f"{result_dict.get('error_description', 'No details available')}"
                )
                logger.error(error_msg)
                if ctx:
                    await ctx.error(error_msg)
                raise RuntimeError(error_msg)
            logger.info(
                "Successfully obtained FHIR token via MSAL client credentials")
            return cast(str, result_dict["access_token"])
        except Exception as e:
            error_msg = f"Error obtaining FHIR token: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            raise


async def _fetch_fhir_resource(resource_type: str, ctx: Optional[Context] = None, resource_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        token = await get_fhir_token(ctx)
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{FHIR_URL}/{resource_type}"
        if resource_id is not None:
            url = f"{url}/{resource_id}"

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 404:
            missing_target = f"{resource_type} with ID {resource_id}" if resource_id else resource_type
            message = f"{missing_target} not found"
            logger.error(message)
            if ctx:
                await ctx.error(message)
            return {}

        if response.status_code != 200:
            message = f"Error retrieving {resource_type}: {response.status_code} - {response.text}"
            logger.error(message)
            if ctx:
                await ctx.error(message)
            return {}

        return cast(Dict[str, Any], response.json())
    except (requests.RequestException, ValueError, KeyError) as exc:
        detail = f"Error retrieving {resource_type}"
        if resource_id:
            detail = f"{detail} {resource_id}"
        detail = f"{detail}: {str(exc)}"
        logger.error(detail)
        if ctx:
            await ctx.error(detail)
        return {}


async def _fetch_fhir_resource_with_search(resource_type: str, ctx: Optional[Context] = None, search_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch FHIR resources with optional search parameters.

    Args:
        resource_type: FHIR resource type (e.g., 'Patient')
        ctx: Optional MCP context for logging
        search_params: Optional dictionary of FHIR search parameters

    Returns:
        Dict containing FHIR Bundle with search results or empty dict on error
    """
    try:
        token = await get_fhir_token(ctx)
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{FHIR_URL}/{resource_type}"

        if search_params:
            response = requests.get(
                url, headers=headers, params=search_params, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 404:
            message = f"{resource_type} not found"
            logger.error(message)
            if ctx:
                await ctx.error(message)
            return {}

        if response.status_code != 200:
            message = f"Error retrieving {resource_type}: {response.status_code} - {response.text}"
            logger.error(message)
            if ctx:
                await ctx.error(message)
            return {}

        return cast(Dict[str, Any], response.json())
    except (requests.RequestException, ValueError, KeyError) as exc:
        detail = f"Error retrieving {resource_type}: {str(exc)}"
        logger.error(detail)
        if ctx:
            await ctx.error(detail)
        return {}


def _make_builtin_resource_handler(resource_type: str, mode: str, entry: Dict[str, Any]):
    """Create a builtin FHIR resource handler (collection or detail).

    Builtin handlers use the shared _fetch_fhir_resource function to retrieve
    data from the FHIR server using the configured authentication.

    Args:
        resource_type: FHIR resource type (e.g., 'Patient')
        mode: Either 'collection' (list resources) or 'detail' (get by ID)
        entry: Catalog metadata entry for naming and documentation

    Returns:
        Async function configured for the specified resource and mode

    Raises:
        ValueError: If resourceType is missing or mode is invalid
    """
    if not resource_type:
        raise ValueError(
            "resourceType is required for builtin resource handlers")

    entry_name = entry.get("name")
    description = entry.get("description")
    resource_lower = resource_type.lower()

    if mode == "detail":
        async def detail_handler(id: str, ctx: Context, _resource_type: str = resource_type) -> Dict[str, Any]:  # pylint: disable=redefined-builtin
            return await _fetch_fhir_resource(_resource_type, ctx, resource_id=id)

        handler = detail_handler
        default_name = f"get_{resource_lower}_detail"
    elif mode == "collection":
        async def collection_handler(filter: str = "", ctx: Optional[Context] = None, _resource_type: str = resource_type) -> Dict[str, Any]:  # pylint: disable=redefined-builtin
            # Parse filter parameter as FHIR search query string
            search_params: Dict[str, Any] = {}
            if filter:
                # Parse URL-style query parameters from filter string
                # e.g., "name=Smith&birthdate=gt1990-01-01&_count=10"
                try:
                    from urllib.parse import parse_qs

                    # Handle both URL-encoded and plain query strings
                    if '=' in filter:
                        parsed = parse_qs(filter, keep_blank_values=True)
                        # Convert list values to single values for FHIR API
                        search_params = {k: v[0] if len(v) == 1 else v
                                         for k, v in parsed.items()}
                    else:
                        # If no '=' found, treat as a simple text search parameter
                        # Default to searching by name or identifier for most resource types
                        if _resource_type.lower() == 'patient':
                            search_params['name'] = filter
                        else:
                            search_params['_text'] = filter
                except (ValueError, ImportError) as e:
                    if ctx:
                        await ctx.error(f"Error parsing filter parameter: {str(e)}")
                    # Fallback to simple text search
                    search_params['_text'] = filter

            return await _fetch_fhir_resource_with_search(_resource_type, ctx, search_params)

        handler = collection_handler
        default_name = f"get_{resource_lower}_collection"
    else:
        raise ValueError(f"Unknown builtin resource handler mode: {mode}")

    handler.__name__ = entry_name or default_name
    if description:
        handler.__doc__ = description

    return handler


def _resolve_custom_resource_handler(handler_path: str):
    """Dynamically import and validate a custom resource handler.

    Custom handlers allow extending the server with specialized logic
    beyond the builtin FHIR fetch operations.

    Args:
        handler_path: Import path in format 'module.path:function_name'

    Returns:
        Callable handler function from the specified module

    Raises:
        ValueError: If handler_path format is invalid
        AttributeError: If module or function not found
        TypeError: If resolved object is not callable
    """
    module_path, sep, attr_name = handler_path.partition(":")
    if not module_path or not sep or not attr_name:
        raise ValueError(
            f"Invalid handler path '{handler_path}'. Expected format 'module:attribute'.")

    module = importlib.import_module(module_path)
    try:
        handler = getattr(module, attr_name)
    except AttributeError as exc:
        raise AttributeError(
            f"Handler '{attr_name}' not found in module '{module_path}'") from exc

    if not callable(handler):
        raise TypeError(f"Resolved handler '{handler_path}' is not callable")

    return handler


def _register_fhir_resource_handlers() -> None:
    """Register all FHIR resource handlers from catalog configuration.

    Iterates through catalog resources and creates MCP resource handlers
    for each URI pattern. Supports builtin handlers (collection/detail)
    and custom handlers via dynamic import.

    Raises:
        ValueError: If resource entries are missing required fields
        Various exceptions from handler creation/import
    """
    logger.info("Registering %d resource handlers from catalog",
                len(RESOURCE_METADATA))

    for entry in RESOURCE_METADATA:
        uri = entry.get("uri")
        if not uri:
            raise ValueError("Catalog resource entry missing 'uri'")

        handler_spec = entry.get("handler", "builtin_collection")
        resource_type = entry.get("resourceType")

        if not resource_type:
            raise ValueError(
                f"Catalog resource '{uri}' missing 'resourceType'")

        if handler_spec == "builtin_collection":
            handler = _make_builtin_resource_handler(
                resource_type, "collection", entry)
        elif handler_spec == "builtin_detail":
            handler = _make_builtin_resource_handler(
                resource_type, "detail", entry)
        else:
            handler = _resolve_custom_resource_handler(handler_spec)

        logger.info("Registering resource handler: %s -> %s",
                    uri, handler.__name__)
        decorated_handler = mcp.resource(uri)(handler)
        _attach_resource_metadata(uri, decorated_handler)

    logger.info("Resource handler registration complete")


# Define FHIR Search Tool
@mcp.tool()
async def search_fhir(resource_type: str, search_params: Optional[Dict[str, Any]] = None, ctx: Optional[Context] = None) -> List[Dict[str, Any]]:
    """
    Search FHIR resources using comprehensive Azure FHIR search capabilities.

    Supports resource-specific and common search parameters, modifiers, prefixes, chained searches, 
    and result management. Returns paginated results in FHIR searchset bundles.

    Key Features:
    • Resource-specific and common search parameters (_id, _lastUpdated, _tag, etc.)
    • Search modifiers (:missing, :exact, :contains, :text, :not, etc.)
    • Prefixes for ordered parameters (gt, lt, ge, le, etc.)
    • Chained searches (e.g., Encounter?subject:Patient.name=Jane)
    • Reverse chained searches using _has parameter
    • Include and revinclude searches (_include, _revinclude)
    • Result parameters (_count, _sort, _elements, _summary, _total)
    • Composite search parameters for complex queries
    • Pagination support with configurable page sizes (max 1000)

    Args:
        resource_type: FHIR resource type to search (e.g., 'Patient', 'Observation', 'Condition')
        search_params: Dictionary of FHIR search parameters. Common examples:
            • {"name": "Smith", "_count": 50} - Search patients by name, limit 50 results
            • {"birthdate": "gt1990-01-01", "_sort": "birthdate"} - Patients born after 1990, sorted
            • {"identifier": "12345", "_include": "Patient:general-practitioner"} - Include GP
            • {"code": "77386006", "_include": "Observation:subject"} - Pregnancy observations with patients
            • {"_lastUpdated": "gt2024-01-01"} - Resources updated after date
        ctx: MCP Context for logging and progress reporting

    Returns:
        List of matching FHIR resources extracted from searchset Bundle
    """
    if search_params is None:
        search_params = {}

    if resource_type not in FHIR_RESOURCES:
        error_msg = f"Invalid resource type: {resource_type}"
        logger.error(error_msg)
        if ctx:
            await ctx.error(error_msg)
        return []

    try:
        token = await get_fhir_token(ctx)
        headers = {"Authorization": f"Bearer {token}"}

        # Build URL with search parameters
        url = f"{FHIR_URL}/{resource_type}"

        if ctx:
            await ctx.info(f"Searching {resource_type} with params: {search_params}")

        response = requests.get(url, headers=headers,
                                params=search_params, timeout=30)

        if response.status_code != 200:
            error_msg = f"Search failed: {response.status_code} - {response.text}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            return []

        bundle = cast(Dict[str, Any], response.json())

        # Extract resources from Bundle
        if "entry" in bundle:
            results = [entry["resource"] for entry in bundle["entry"]]
            if ctx:
                await ctx.info(f"Found {len(results)} {resource_type} resources")
            return results
        else:
            if ctx:
                await ctx.info(f"No {resource_type} resources found")
            return []

    except (requests.RequestException, ValueError, KeyError) as e:
        error_msg = f"Error during search: {str(e)}"
        logger.error(error_msg)
        if ctx:
            await ctx.error(error_msg)
        return []


_attach_tool_metadata("search_fhir", search_fhir)


# OAuth user info tool (only available when USE_FAST_MCP_OAUTH_PROXY is True)
if USE_FAST_MCP_OAUTH_PROXY:
    @mcp.tool()
    async def get_user_info(ctx: Optional[Context] = None) -> Dict[str, Any]:
        """Returns information about the authenticated Azure user (OAuth only)."""
        try:
            from fastmcp.server.dependencies import get_access_token

            token = get_access_token()
            if token is None:
                return {"error": "No authentication token available", "authentication_method": "OAuth"}

            # The AzureProvider stores user data in token claims
            user_info = {
                "azure_id": getattr(token, 'claims', {}).get("sub") if hasattr(token, 'claims') else None,
                "email": getattr(token, 'claims', {}).get("email") if hasattr(token, 'claims') else None,
                "name": getattr(token, 'claims', {}).get("name") if hasattr(token, 'claims') else None
            }

            if ctx:
                await ctx.info(f"Retrieved user info for: {user_info.get('email', 'Unknown')}")

            return user_info
        except (ImportError, AttributeError, ValueError) as e:
            error_msg = f"Error retrieving user info: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            return {"error": error_msg, "authentication_method": "OAuth"}

    _attach_tool_metadata("get_user_info", get_user_info)


_register_fhir_resource_handlers()


def main() -> None:
    if HTTP_TRANSPORT:
        logger.info("Starting FHIR MCP Server with HTTP transport")
        # OAuth requires HTTP transport
        logger.info("Starting server on port %d", FASTMCP_HTTP_PORT)
        mcp.run(
            transport="http",
            port=FASTMCP_HTTP_PORT
        )
    else:
        logger.info("Starting FHIR MCP Server with stdio transport")
        # Client credentials can use stdio transport
        mcp.run()


# Main execution
if __name__ == "__main__":
    main()
    main()
