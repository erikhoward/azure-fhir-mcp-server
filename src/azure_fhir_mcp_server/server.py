from fastmcp import FastMCP, Context
from fastmcp.server.auth.providers.azure import AzureProvider
import os
import requests
from typing import List, Dict, Any, Optional
import logging
from threading import Lock
import msal
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Read environment variables
FHIR_URL = os.environ.get("fhirUrl")
USE_FAST_MCP_OAUTH_PROXY = os.environ.get("USE_FAST_MCP_OAUTH_PROXY", "false").lower() == "true"

# Explicit scope override (space-separated). If not provided we derive a default
# scope from the FHIR URL using the pattern: {FHIR_URL}/.default (AAD v2 format)
FHIR_SCOPE_OVERRIDE = os.environ.get("FHIR_SCOPE")

# Validate required environment variables
if not FHIR_URL:
    raise EnvironmentError("Missing required environment variable: fhirUrl")

HTTP_TRANSPORT = os.environ.get("HTTP_TRANSPORT", "false").lower() == "true"

if USE_FAST_MCP_OAUTH_PROXY and not HTTP_TRANSPORT:
    raise ValueError("When USE_FAST_MCP_OAUTH_PROXY is true, HTTP_TRANSPORT must also be true")

FASTMCP_HTTP_PORT = os.environ.get("FASTMCP_HTTP_PORT", "9002")
if not FASTMCP_HTTP_PORT.isdigit():
    raise ValueError("FASTMCP_HTTP_PORT must be a valid integer")
FASTMCP_HTTP_PORT = int(FASTMCP_HTTP_PORT)

# Initialize MCP server with explicit Azure provider configuration
if USE_FAST_MCP_OAUTH_PROXY:
    # The AzureProvider handles Azure's token format and validation
    auth_provider = AzureProvider(
        client_id=os.environ.get("clientId"),  # Your Azure App Client ID
        client_secret=os.environ.get("clientSecret"),  # Your Azure App Client Secret
        tenant_id=os.environ.get("tenantId"),  # Your Azure Tenant ID (REQUIRED)
        base_url=os.environ.get("FASTMCP_SERVER_AUTH_AZURE_BASE_URL", f"http://localhost:{FASTMCP_HTTP_PORT}"),  # Must match your App registration
        redirect_path=os.environ.get("FASTMCP_SERVER_AUTH_AZURE_REDIRECT_PATH", "/auth/callback"),  # Auth callback path
        identifier_uri=os.environ.get("FASTMCP_SERVER_AUTH_AZURE_IDENTIFIER_URI", f"api://{os.environ.get('clientId')}"),  # API identifier URI
        required_scopes=os.environ.get("FASTMCP_SERVER_AUTH_AZURE_REQUIRED_SCOPES", "user_impersonation").split(),  # Required scopes
        additional_authorize_scopes=os.environ.get("FASTMCP_SERVER_AUTH_AZURE_ADDITIONAL_AUTHORIZE_SCOPES", "").split() if os.environ.get("FASTMCP_SERVER_AUTH_AZURE_ADDITIONAL_AUTHORIZE_SCOPES") else None,  # Additional FHIR scopes
    )

    mcp = FastMCP(name="Azure FHIR MCP Server", auth=auth_provider)
    logger.info("FHIR MCP Server initialized with explicit Azure OAuth authentication")
else:
    # Client credentials mode: No authentication on MCP server
    mcp = FastMCP("FHIR MCP Server")
    logger.info("FHIR MCP Server initialized with client credentials authentication")

# Define FHIR Resources
FHIR_RESOURCES = [
    "AllergyIntolerance", "AdverseEvent", "Condition", "Procedure",
    "FamilyMemberHistory", "ClinicalImpression", "Observation", "Media",
    "DiagnosticReport", "Specimen", "BodyStructure", "ImagingStudy",
    "Questionnaire", "QuestionnaireResponse", "CarePlan", "CareTeam",
    "Goal", "ServiceRequest", "NutritionOrder", "VisionPrescription",
    "RiskAssessment", "RequestGroup", "Medication", "MedicationRequest",
    "MedicationAdministration", "MedicationDispense", "MedicationStatement",
    "Immunization", "ImmunizationRecommendation", "Patient", "RelatedPerson",
    "Person", "Group", "Practitioner", "PractitionerRole", "Organization",
    "Location", "HealthcareService", "Endpoint", "Device", "DeviceDefinition",
    "DeviceMetric", "Substance", "Task", "Appointment", "AppointmentResponse",
    "Schedule", "Slot", "Encounter", "EpisodeOfCare", "Communication",
    "CommunicationRequest", "ActivityDefinition", "PlanDefinition", "DeviceRequest",
    "DeviceUseStatement", "GuidanceResponse", "SupplyRequest", "SupplyDelivery",
    "Coverage", "CoverageEligibilityRequest", "CoverageEligibilityResponse",
    "EnrollmentRequest", "EnrollmentResponse", "Claim", "ClaimResponse", "Invoice",
    "PaymentNotice", "PaymentReconciliation", "Account", "ChargeItem",
    "ChargeItemDefinition", "Contract", "ExplanationOfBenefit", "InsurancePlan",
    "Composition", "DocumentManifest", "DocumentReference", "CatalogEntry",
    "MessageHeader", "List", "Basic", "Provenance", "AuditEvent", "Consent"
]


# MSAL confidential client
_MSAL_TOKEN_CACHE = msal.SerializableTokenCache()
_MSAL_APP: Optional[msal.ConfidentialClientApplication] = None
_MSAL_APP_LOCK = Lock()


def _derive_default_scope() -> str:
    # Derive a default scope string for AAD v2 endpoint; ensure no trailing slash duplication
    base = FHIR_URL.rstrip('/')
    return f"{base}/.default"


def _get_fhir_scopes() -> List[str]:
    if FHIR_SCOPE_OVERRIDE:
        scopes = [scope.strip() for scope in FHIR_SCOPE_OVERRIDE.split() if scope.strip()]
        if scopes:
            return scopes
    return [_derive_default_scope()]


def _get_confidential_client() -> msal.ConfidentialClientApplication:
    global _MSAL_APP
    with _MSAL_APP_LOCK:
        if _MSAL_APP:
            return _MSAL_APP

        tenant_id = os.environ.get("tenantId")
        client_id = os.environ.get("clientId")
        client_secret = os.environ.get("clientSecret")
        if not all([tenant_id, client_id, client_secret]):
            raise EnvironmentError("MSAL client requires tenantId, clientId, clientSecret env vars")

        authority = os.environ.get("MSAL_AUTHORITY", f"https://login.microsoftonline.com/{tenant_id}")
        _MSAL_APP = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
            token_cache=_MSAL_TOKEN_CACHE,
        )
        logger.info("Initialized MSAL confidential client for tenant %s", tenant_id)
        return _MSAL_APP


def _obo_exchange(user_token: str) -> str:
    app = _get_confidential_client()
    scopes = _get_fhir_scopes()
    logger.info("Performing MSAL OBO token exchange for FHIR scopes: %s", " ".join(scopes))

    result = app.acquire_token_on_behalf_of(user_assertion=user_token, scopes=scopes)
    if "access_token" in result:
        logger.info("Obtained OBO token for FHIR access (expires_in=%s)", result.get("expires_in"))
        return result["access_token"]

    error = result.get("error")
    description = result.get("error_description")
    correlation = result.get("correlation_id")
    detail = f"{error}: {description}" if error or description else "Unknown MSAL error"
    if correlation:
        detail = f"{detail} (correlation_id={correlation})"
    raise Exception(f"OBO token exchange failed via MSAL: {detail}")


async def get_fhir_token(ctx: Context = None) -> str:
    """Get token for FHIR API access.

    Modes:
      * USE_FAST_MCP_OAUTH_PROXY + FHIR_OBO_ENABLED: Exchange user token (Azure AD) for FHIR audience token (OBO).
      * USE_FAST_MCP_OAUTH_PROXY only: Pass through user token directly (legacy behaviour).
      * Client credentials: Service-to-service token.
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
                raise Exception(error_msg)
            # Extract raw token string
            raw_user_token = getattr(user_token_obj, 'token', None) or str(user_token_obj)
            if not raw_user_token or raw_user_token == 'None':
                raise Exception("Invalid user token format")

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
            result = app.acquire_token_for_client(scopes=scopes)
            if "access_token" not in result:
                error_msg = (
                    "Failed to obtain FHIR token via MSAL client credentials: "
                    f"{result.get('error')}: {result.get('error_description')}"
                )
                logger.error(error_msg)
                if ctx:
                    await ctx.error(error_msg)
                raise Exception(error_msg)
            logger.info("Successfully obtained FHIR token via MSAL client credentials")
            return result["access_token"]
        except Exception as e:
            error_msg = f"Error obtaining FHIR token: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            raise


# Define FHIR Search Tool
@mcp.tool()
async def search_fhir(resource_type: str, search_params: Optional[Dict[str, Any]] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """
    Search for FHIR resources based on search parameters.
    
    Args:
        resource_type: The FHIR resource type to search (e.g., 'Patient', 'Observation')
        search_params: Dictionary of search parameters to apply
        ctx: MCP Context for logging and progress reporting
    
    Returns:
        List of matching resources
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
        
        response = requests.get(url, headers=headers, params=search_params)
        
        if response.status_code != 200:
            error_msg = f"Search failed: {response.status_code} - {response.text}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            return []
        
        bundle = response.json()
        
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
            
    except Exception as e:
        error_msg = f"Error during search: {str(e)}"
        logger.error(error_msg)
        if ctx:
            await ctx.error(error_msg)
        return []


# OAuth user info tool (only available when USE_FAST_MCP_OAUTH_PROXY is True)
if USE_FAST_MCP_OAUTH_PROXY:
    @mcp.tool()
    async def get_user_info(ctx: Context = None) -> Dict[str, Any]:
        """Returns information about the authenticated Azure user (OAuth only)."""
        try:
            from fastmcp.server.dependencies import get_access_token
            
            token = get_access_token()
            # The AzureProvider stores user data in token claims
            user_info = {
                "azure_id": token.claims.get("sub"),
                "email": token.claims.get("email"),
                "name": token.claims.get("name")
            }
            
            if ctx:
                await ctx.info(f"Retrieved user info for: {user_info.get('email', 'Unknown')}")
            
            return user_info
        except Exception as e:
            error_msg = f"Error retrieving user info: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            return {"error": error_msg, "authentication_method": "OAuth"}


# Dynamically generate resource functions for all required FHIR resources
for resource_type in FHIR_RESOURCES:
    exec(f"""
@mcp.resource("fhir://{resource_type}/{{id}}")
async def get_{resource_type.lower()}(id: str, ctx: Context) -> Dict[str, Any]:
    \"\"\"Get a specific {resource_type} resource by ID.\"\"\"
    try:
        token = await get_fhir_token(ctx)
        headers = {{"Authorization": f"Bearer {{token}}"}}
        response = requests.get(f"{{FHIR_URL}}/{resource_type}/{{id}}", headers=headers)
        
        if response.status_code == 404:
            await ctx.error(f"{resource_type} with ID {{id}} not found")
            return {{}}
        elif response.status_code != 200:
            await ctx.error(f"Error retrieving {resource_type}: {{response.status_code}} - {{response.text}}")
            return {{}}
        
        return response.json()
    except Exception as e:
        error_msg = f"Error retrieving {resource_type} {{id}}: {{str(e)}}"
        logger.error(error_msg)
        if ctx:
            await ctx.error(error_msg)
        return {{}}
""")
    
    # Dynamically generate resource functions for all required FHIR resources
for resource_type in FHIR_RESOURCES:
    exec(f"""
@mcp.resource("fhir://{resource_type}")
async def get_{resource_type.lower()}(ctx: Context) -> Dict[str, Any]:
    \"\"\"Get a specific {resource_type} resource\"\"\"
    try:
        token = await get_fhir_token(ctx)
        headers = {{"Authorization": f"Bearer {{token}}"}}
        response = requests.get(f"{{FHIR_URL}}/{resource_type}", headers=headers)
        
        if response.status_code == 404:
            await ctx.error(f"{resource_type} with ID {{id}} not found")
            return {{}}
        elif response.status_code != 200:
            await ctx.error(f"Error retrieving {resource_type}: {{response.status_code}} - {{response.text}}")
            return {{}}
        
        return response.json()
    except Exception as e:
        error_msg = f"Error retrieving {resource_type} : {{str(e)}}"
        logger.error(error_msg)
        if ctx:
            await ctx.error(error_msg)
        return {{}}
""")


def main():
    if HTTP_TRANSPORT:
        logger.info("Starting FHIR MCP Server with HTTP transport")
        # OAuth requires HTTP transport
        logger.info(f"Starting server on port {FASTMCP_HTTP_PORT}")
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
