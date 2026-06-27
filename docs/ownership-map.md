# Ownership Map

`vendor-fabric` owns external API connector integrations, vendor-backed sync
capabilities, and agentic composition for the Extended Data stack. It is the
destination for vendor and agent workflow code that previously lived beside
the base data primitives in `~/src/jbcom/extended-data-library`.

## In This Package

| Surface | Current owner |
| --- | --- |
| Connector registry and adapter metadata | `vendor_fabric.registry` |
| Shared connector base classes | `vendor_fabric.base` |
| Connector fabric | `vendor_fabric.connectors` |
| Vendor CLI | `vendor_fabric.cli` |
| MCP bridge | `vendor_fabric.mcp` |
| AWS, Google, GitHub, Slack, Vault, Zoom, Anthropic, Cursor, and Meshy clients | `vendor_fabric.*` |
| Vendor tool adapters | `vendor_fabric.*.tools` |
| Native vendor secret and file sync | `vendor_fabric.secrets_sync` |
| Agentic workflow runners and tool adapters | `vendor_fabric.agentic` |
| SecretSync agent tool wrappers | `vendor_fabric.agentic.tools.secrets_sync` |

## Outside This Package

| Surface | Current repository | Install target |
| --- | --- | --- |
| Base data primitives, generic containers, local file sync, inputs, logging, and workflows | `jbcom/extended-data` | `extended-data` |
| Standalone Go SecretSync binary, if retained | `jbcom/secrets-sync` | `go install github.com/jbcom/secrets-sync/cmd/secrets-sync@latest` |

SecretSync for Python belongs here because its useful Python shape is a
vendor-backed sync capability over Vault, AWS, S3, and future providers.
Agent framework packages are optional extras of this package because the agents
compose vendor capabilities rather than owning a separate domain.
