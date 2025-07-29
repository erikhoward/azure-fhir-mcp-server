[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/erikhoward-azure-fhir-mcp-server-badge.png)](https://mseep.ai/app/erikhoward-azure-fhir-mcp-server)

# Azure AHDS FHIR MCP Server 🚀

A Model Context Protocol (MCP) server implementation for Azure Health Data Services FHIR (Fast Healthcare Interoperability Resources). This service provides a standardized interface for interacting with Azure FHIR servers, enabling healthcare data operations through MCP tools.

[![License](https://img.shields.io/github/license/erikhoward/azure-fhir-mcp-server)](https://opensource.org/licenses/MIT) [![Python Version](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/) [![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://github.com/modelcontextprotocol/spec)

## Setup 🛠️

### Installation 📦

Requires Python 3.13 or higher and `uv`.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.

### MCP Configuration ⚙️

#### Claude Desktop Configuration

1 - Edit Claude Desktop Configuration:

Open `claude_desktop_config.json` and add the following configuration.

On MacOs, the file is located here: `~/Library/Application Support/Claude Desktop/claude_desktop_config.json`.

On Windows, the file is located here: `%APPDATA%\Claude Desktop\claude_desktop_config.json`.

```json
{
    "mcpServers": {
        "fhir": {
            "command": "uvx",
            "args": [
                "azure-fhir-mcp-server"
            ],
            "env": {
                "LOG_LEVEL": "INFO",
                "fhirUrl": "https://your-fhir-server.azurehealthcareapis.com/fhir",
                "clientId": "your-client-id",
                "clientSecret": "your-client-secret",
                "tenantId": "your-tenant-id"
            }
        }
    }
}
```

The following is a table of available environment configuration variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `fhirUrl` | Azure FHIR server URL | Required |
| `clientId` | OAuth2 client ID | Required |
| `clientSecret` | OAuth2 client secret | Required |
| `tenantId` | Azure AD tenant ID | Required |

2 - Restart Claude Desktop.

### Available Tools 🔧

#### FHIR Resource Operations

* `search_fhir` - Search for FHIR resources based on a dictionary of search parameters

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
