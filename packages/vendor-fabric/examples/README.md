# Connector Examples

This directory contains working examples for `vendor_fabric` and the
registered integrations that hang off `ConnectorFabric`.

Connector examples assume the `extended-data>=8.3.0` contract: external data
payloads are promoted through the `ExtendedData` root at connector boundaries.
Callers can use `ExtendedDict`, `ExtendedList`, and `ExtendedString` methods on
decoded API, file, and SDK-shaped results, then call `to_builtin()` only when a
plain Python payload is needed for serialization or SDK handoff.
The direct AI-tool functions follow that same payload contract; only the
framework factory helpers return plain framework tool objects.

## Quick Start

Install vendor-fabric with the extras you need:

```bash
# Install with all connectors
pip install "vendor-fabric[all]"

# Or install specific connectors
pip install "vendor-fabric[aws,google,meshy]"

# For AI framework integration
pip install "vendor-fabric[langchain]"

# For the Meshy MCP server
pip install "vendor-fabric[meshy,mcp]"
```

## Examples

### Basic Connectors

- [`basic_aws.py`](basic_aws.py) - AWS connector with Organizations and S3
- [`basic_google.py`](basic_google.py) - Google Vendor fabric with Workspace and Billing
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
uv run --package vendor-fabric python packages/vendor-fabric/examples/basic_meshy.py

# Run with debug logging
LOGLEVEL=DEBUG uv run --package vendor-fabric python packages/vendor-fabric/examples/basic_meshy.py
```

SecretSync examples live in this repository because that surface composes
vendor capabilities. Install `vendor-fabric[secrets-sync]` for vendor secret
sync. Agent runtime examples belong in `agentic-fabric`.
