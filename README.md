[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/erikhoward-azure-fhir-mcp-server-badge.png)](https://mseep.ai/app/erikhoward-azure-fhir-mcp-server)

# Azure AHDS FHIR MCP Server 🚀

A Model Context Protocol (MCP) server implementation for Azure Health Data Services FHIR (Fast Healthcare Interoperability Resources). This service provides a standardized interface for interacting with Azure FHIR servers, enabling healthcare data operations through MCP tools.

[![License](https://img.shields.io/github/license/erikhoward/azure-fhir-mcp-server)](https://opensource.org/licenses/MIT) [![Python Version](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/) [![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://github.com/modelcontextprotocol/spec)

## Setup 🛠️

### Installation 📦

Requires Python 3.13 or higher and `uv`.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.

### Configuration ⚙️

See the FastMCP guidance on `mcp.json` here: [https://gofastmcp.com/integrations/mcp-json-configuration](https://gofastmcp.com/integrations/mcp-json-configuration)

#### Client Credentials Flow (default):

- Used for service-to-service authentication
- Leave `USE_FAST_MCP_OAUTH_PROXY=false`
- Keep `HTTP_TRANSPORT=false` to use stdio transport
- Uses Azure AD client credentials flow

```json
{
    "mcpServers": {
        "fhir": {
            "type": "stdio",
            "command": "uvx",
            "args": [
                "azure-fhir-mcp-server"
            ],
            "env": {
                "fhirUrl": "https://your-fhir-server.azurehealthcareapis.com/fhir",
                "clientId": "your-client-id",
                "clientSecret": "your-client-secret",
                "tenantId": "your-tenant-id"
            }
        }
    }
}
```

#### OAuth On-Behalf-Of Flow:

##### Create the Azure App Registration

The OAuth on-behalf-of flow requires a confidential Azure AD application that represents the MCP server.

1. In the Azure portal, go to **Microsoft Entra ID ➜ App registrations ➜ New registration**. Give it a descriptive name such as `FHIR-MCP-Server`, set **Supported account types** to *Single tenant*, and leave the redirect URI unset for now.
2. After the app is created, capture the generated `Application (client) ID` and `Directory (tenant) ID` for later use.
3. Under **Expose an API**, select **Set** for the Application ID URI and accept the suggested value `api://{appId}`. Add a scope named `user_impersonation` with admin consent display/description also set to `user_impersonation`.
4. Under **Certificates & secrets**, create a **New client secret** (for example `FHIR-MCP-Secret-New`). Copy the secret value immediately; it is required for the MCP server `clientSecret` setting.
5. Under **Authentication**, add the following Web redirect URIs to support the FastMCP OAuth proxy:
    - `http://localhost:9002/auth/callback`
    Ensure **Default client type** remains *No* so the app stays confidential.
6. Under **API permissions**, choose **Add a permission ➜ APIs my organization uses**, search for your Azure Health Data Services FHIR server, and add the delegated scopes required for your scenario. Grant admin consent so the FastMCP proxy can request tokens without an interactive prompt.

- Environment variables:
    - Set `USE_FAST_MCP_OAUTH_PROXY=true`
    - Requires `HTTP_TRANSPORT=true`

- Start the MCP server with:

```bash
uv pip install -e .
uv run --env-file .env azure-fhir-mcp-server
```

- Update mcp.json:

```json
{
    "mcpServers": {
        "fhir": {
            "type": "http",
            "url": "http://localhost:9002/mcp"
        }
    }
}
```

The following is a table of available environment configuration variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `fhirUrl` | Azure FHIR server base URL (include `/fhir`) | - | Yes |
| `clientId` | Azure App registration client ID | - | Yes |
| `clientSecret` | Azure App registration client secret | - | Yes |
| `tenantId` | Azure AD tenant ID | - | Yes |
| `USE_FAST_MCP_OAUTH_PROXY` | Enable FastMCP Azure OAuth proxy integration | `false` | No |
| `HTTP_TRANSPORT` | Run the MCP server over HTTP transport (required for OAuth proxy) | `false` | No |
| `FASTMCP_HTTP_PORT` | Port exposed when `HTTP_TRANSPORT=true` | `9002` | No |
| `FHIR_SCOPE` | Override FHIR audience scope for the OBO flow (space-separated) | `{fhirUrl}/.default` | No |
| `FASTMCP_SERVER_AUTH_AZURE_BASE_URL` | Public base URL of your FastMCP server | `http://localhost:9002` | No |
| `FASTMCP_SERVER_AUTH_AZURE_REDIRECT_PATH` | OAuth callback path appended to the base URL | `/auth/callback` | No |
| `FASTMCP_SERVER_AUTH_AZURE_IDENTIFIER_URI` | Azure App registration Application ID URI | `api://{clientId}` | No |
| `FASTMCP_SERVER_AUTH_AZURE_REQUIRED_SCOPES` | Space-separated scopes requested by the Azure provider | `user_impersonation` | No |
| `FASTMCP_SERVER_AUTH_AZURE_ADDITIONAL_AUTHORIZE_SCOPES` | Optional space-separated scopes added to the authorize request | - | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |

### Available Tools 🔧

#### FHIR Resource Operations

* `search_fhir` - Search for FHIR resources based on a dictionary of search parameters
* `get_user_info` - (OAuth only) Returns information about the authenticated Azure user

#### Resource Access

The server provides access to all standard FHIR resources through the MCP resource protocol:

* `fhir://Patient/` - Access all Patient resources
* `fhir://Patient/{id}` - Access a specific Patient resource
* `fhir://Observation/` - Access all Observation resources
* `fhir://Observation/{id}` - Access a specific Observation resource
* `fhir://Medication/` - Access all Medication resources
* `fhir://Medication/{id}` - Access a specific Medication resource
* And many more...

## Development 💻

### Local Development Setup

1 - Clone the repository:

```bash
git clone https://github.com/erikhoward/azure-fhir-mcp-server.git
cd azure-fhir-mcp-server
```

2 - Create and activate virtual environment:

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

3 - Install dependencies:

```bash
pip install -e ".[dev]"
```

4 - Copy and configure environment variables:

```bash
cp .env.example .env
```

Edit .env with your settings:

```env
fhirUrl=https://your-fhir-server.azurehealthcareapis.com/fhir
clientId=your-client-id
clientSecret=your-client-secret
tenantId=your-tenant-id
```

5 - Claude Desktop Configuration

Open `claude_desktop_config.json` and add the following configuration.

On MacOs, the file is located here: `~/Library/Application Support/Claude Desktop/claude_desktop_config.json`.

On Windows, the file is located here: `%APPDATA%\Claude Desktop\claude_desktop_config.json`.

```json
{
    "mcpServers": {
        "fhir": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/azure-fhir-mcp-server/repo",
                "run",
                "azure_fhir_mcp_server"
            ],
            "env": {
                "LOG_LEVEL": "DEBUG",
                "fhirUrl": "https://your-fhir-server.azurehealthcareapis.com/fhir",
                "clientId": "your-client-id",
                "clientSecret": "your-client-secret",
                "tenantId": "your-tenant-id"
            }
        }
    }
}
```

6 - Restart Claude Desktop.

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/azure_fhir_mcp_server

# Run specific test
pytest tests/test_fastmcp_metadata.py::TestFastMCPMetadata::test_fastmcp_server_discovery -v

# Run with detailed output
pytest tests/test_fastmcp_metadata.py::TestFastMCPMetadata::test_output_detailed_metadata -v -s
```

## Contributions 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m '✨ Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License ⚖️

Licensed under MIT - see [LICENSE.md](LICENSE) file.

**This is not an official Microsoft or Azure product.**
