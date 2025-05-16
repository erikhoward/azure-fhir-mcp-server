from fastmcp import FastMCP, Context
import os
import requests
import json
from typing import List, Dict, Any, Optional
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("FHIR MCP Server")

# Read environment variables
FHIR_URL = os.environ.get("fhirUrl")
CLIENT_ID = os.environ.get("clientId")
CLIENT_SECRET = os.environ.get("clientSecret")
TENANT_ID = os.environ.get("tenantId")

if not all([FHIR_URL, CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
    raise EnvironmentError("Missing required environment variables: fhirUrl, clientId, clientSecret, tenantId")

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

# OAuth2 token management
async def get_auth_token(ctx: Context = None) -> str:
    """Get OAuth2 token using client credentials flow."""
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/token"
    
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "resource": FHIR_URL
    }
    
    try:
        response = requests.post(token_url, data=payload)
        
        if response.status_code != 200:
            error_msg = f"Failed to obtain auth token: {response.status_code} - {response.text}"
            logger.error(error_msg)
            if ctx:
                await ctx.error(error_msg)
            raise Exception(error_msg)
        
        token_data = response.json()
        return token_data["access_token"]
    except Exception as e:
        error_msg = f"Error obtaining auth token: {str(e)}"
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
        token = await get_auth_token(ctx)
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

# Dynamically generate resource functions for all required FHIR resources
for resource_type in FHIR_RESOURCES:
    exec(f"""
@mcp.resource("fhir://{resource_type}/{{id}}")
async def get_{resource_type.lower()}(id: str, ctx: Context) -> Dict[str, Any]:
    \"""Get a specific {resource_type} resource by ID.\"""
    try:
        token = await get_auth_token(ctx)
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
    \"""Get a specific {resource_type} resource\"""
    try:
        token = await get_auth_token(ctx)
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
    logger.info("Starting FHIR MCP Server")
    mcp.run()

# Main execution
if __name__ == "__main__":
    main()