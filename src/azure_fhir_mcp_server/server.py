from fastmcp import FastMCP, Context
from fastmcp.server.auth.providers.azure import AzureProvider
import os
import requests
import json
from typing import List, Dict, Any, Optional
import logging
import time
import hashlib
import base64
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


# FHIR token management
_OBO_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


def _derive_default_scopes() -> str:
    # Derive a default scope string for AAD v2 endpoint; ensure no trailing slash duplication
    base = FHIR_URL.rstrip('/')
    return f"{base}/.default"


def _decode_jwt_claim(token: str, claim: str) -> Optional[Any]:
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + '==='  # pad
        padded = payload_b64.replace('-', '+').replace('_', '/')
        decoded = base64.b64decode(padded)
        data = json.loads(decoded)
        return data.get(claim)
    except Exception:
        return None


def _obo_cache_key(user_token: str, scopes: str) -> str:
    h = hashlib.sha256()
    h.update(user_token.encode('utf-8'))
    h.update(scopes.encode('utf-8'))
    return h.hexdigest()


def _get_valid_cached_obo_token(cache_key: str) -> Optional[str]:
    entry = _OBO_TOKEN_CACHE.get(cache_key)
    if not entry:
        return None
    if entry['expires_at'] - 30 > time.time():  # 30s grace
        return entry['access_token']
    return None


def _store_obo_token(cache_key: str, access_token: str, expires_in: int):
    _OBO_TOKEN_CACHE[cache_key] = {
        'access_token': access_token,
        'expires_at': time.time() + expires_in
    }


def _obo_exchange(user_token: str, ctx: Optional[Context]) -> str:
    tenant_id = os.environ.get("tenantId")
    client_id = os.environ.get("clientId")
    client_secret = os.environ.get("clientSecret")
    if not all([tenant_id, client_id, client_secret]):
        raise EnvironmentError("OBO flow requires tenantId, clientId, clientSecret env vars")

    scopes = FHIR_SCOPE_OVERRIDE if FHIR_SCOPE_OVERRIDE else _derive_default_scopes()
    cache_key = _obo_cache_key(user_token, scopes)
    cached = _get_valid_cached_obo_token(cache_key)
    if cached:
        logger.info("Using cached OBO token for FHIR access")
        return cached

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'requested_token_use': 'on_behalf_of',
        'assertion': user_token,
        'scope': scopes,
    }
    logger.info("Performing OBO token exchange for FHIR scopes: %s", scopes)
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        raise Exception(f"OBO token exchange failed: {response.status_code} - {response.text}")
    token_data = response.json()
    access_token = token_data['access_token']
    expires_in = token_data.get('expires_in', 3600)
    _store_obo_token(cache_key, access_token, expires_in)
    logger.info("Obtained new OBO token for FHIR access (expires_in=%s)", expires_in)
    return access_token


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
            token = _obo_exchange(raw_user_token, ctx)
            return token

        except Exception as e:
            error_msg = f"Error obtaining OAuth/OBO token: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            raise
    else:
        # Client credentials mode: Get service token for FHIR access (AAD v1 endpoint)
        client_id = os.environ.get("clientId")
        client_secret = os.environ.get("clientSecret")
        tenant_id = os.environ.get("tenantId")
        if not all([client_id, client_secret, tenant_id]):
            raise EnvironmentError("Missing client credentials: clientId, clientSecret, tenantId")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "resource": FHIR_URL
        }
        try:
            response = requests.post(token_url, data=payload)
            if response.status_code != 200:
                error_msg = f"Failed to obtain FHIR token: {response.status_code} - {response.text}"
                logger.error(error_msg)
                if ctx:
                    await ctx.error(error_msg)
                raise Exception(error_msg)
            token_data = response.json()
            logger.info("Successfully obtained FHIR token via client credentials")
            return token_data["access_token"]
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
