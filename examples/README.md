# Connector Examples

This directory contains working examples for `cloud_connectors` and the
registered integrations that hang off `ConnectorFabric`.

Connector examples assume the major-version `extended-data` contract: external
data payloads are promoted into Tier 2 containers at connector boundaries.
Callers can use `ExtendedDict`, `ExtendedList`, and `ExtendedString` methods on
decoded API, file, and SDK-shaped results, then call `to_builtin()` only when a
plain Python payload is needed for serialization or SDK handoff.
The direct AI-tool functions follow that same payload contract; only the
framework factory helpers return plain framework tool objects.

## Quick Start

Install cloud-connectors with the extras you need:

```bash
# Install with all connectors
pip install "cloud-connectors[all]"

# Or install specific connectors
pip install "cloud-connectors[aws,google,meshy]"

# For AI framework integration
pip install "cloud-connectors[langchain]"

# CrewAI adapters require a user-managed CrewAI install. cloud-connectors does not
# currently publish a CrewAI extra because current CrewAI releases pull
# vulnerable chromadb versions transitively.

# For the Meshy MCP server
pip install "cloud-connectors[meshy,mcp]"
```

## Examples

### Basic Connectors

- [`basic_aws.py`](basic_aws.py) - AWS connector with Organizations and S3
- [`basic_google.py`](basic_google.py) - Google Cloud connector with Workspace and Billing
- [`basic_meshy.py`](basic_meshy.py) - Meshy AI 3D generation

### AI Agent Integration

- [`langchain_tools.py`](langchain_tools.py) - Using Meshy tools with LangChain agents
- [`mcp_server.py`](mcp_server.py) - Running the MCP server for Claude integration

## Environment Variables

Most examples require API keys set as environment variables:

```bash
# AWS
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"

# Google Cloud
export GOOGLE_SERVICE_ACCOUNT='{"type": "service_account", ...}'

# Meshy AI
export MESHY_API_KEY="msy_your_key"

# For LangChain examples
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Running Examples

```bash
# Run any example
uv run python examples/connectors/basic_meshy.py

# Run with debug logging
LOGLEVEL=DEBUG uv run python examples/connectors/basic_meshy.py
```

SecretSync examples live in `jbcom/secrets-sync` for bridge/runtime usage and
`jbcom/agent-orchestration` for agent framework tools.
