# Ownership Map

`cloud-connectors` owns external API connector integrations for the Extended
Data stack. It is the destination for vendor code that previously lived beside
the base data primitives.

## In This Package

| Surface | Current owner |
| --- | --- |
| Connector registry and adapter metadata | `cloud_connectors.registry` |
| Shared connector base classes | `cloud_connectors.base` |
| Connector fabric | `cloud_connectors.connectors` |
| Vendor CLI | `cloud_connectors.cli` |
| MCP bridge | `cloud_connectors.mcp` |
| AWS, Google, GitHub, Slack, Vault, Zoom, Anthropic, Cursor, and Meshy clients | `cloud_connectors.*` |
| Vendor tool adapters | `cloud_connectors.*.tools` |

## Outside This Package

| Surface | Current repository | Install target |
| --- | --- | --- |
| Base data primitives, containers, inputs, logging, and workflows | `jbcom/extended-data` | `extended-data` |
| SecretSync Python bridge | `jbcom/secrets-sync` | `secrets-sync-bridge` |
| SecretSync agent tools | `jbcom/agent-orchestration` | `agentic-crew[secrets-sync]` |
| Agent framework orchestration | `jbcom/agent-orchestration` | `agentic-crew[...]` |

SecretSync is not a vendor connector. Agent framework packages are not required
for base connector usage; they belong in the agentic layer or in optional
framework-specific installs.
