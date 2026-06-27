# Architecture

`vendor_fabric.agentic` has three layers:

1. Core discovery and configuration loading.
2. Runner adapters for optional agent frameworks.
3. Tool adapters for optional external capabilities.

Core imports must stay lightweight. Frameworks and vendor packages are imported
only when a runner, tool, or registry entry is resolved.

## Optional Integrations

Optional integrations belong here when their purpose is agent execution or tool
adaptation. Domain boundaries remain explicit:

- `extended-data`: data primitives, input handling, logging, and workflows.
- `vendor-fabric`: vendor API connectors, SDK-specific dependencies, native
  SecretSync, and agent-facing tool adapters.

The `vendor-fabric-agent` command is a CLI entry point inside `vendor-fabric`,
not a separate package.
