---
title: Ownership map
description: A practical map of which repository owns each surface in the Extended Data stack.
---

| Surface | Owner |
| --- | --- |
| Connector registry and adapter metadata | `vendor_fabric.registry` |
| Optional-extra guidance and availability probes | `vendor_fabric._optional` |
| Connector base classes | `vendor_fabric.base` |
| Capability decorator and provider mixin | `vendor_fabric.capabilities` |
| Connector construction | `vendor_fabric.connectors` |
| Provider-aware data facade | `vendor_fabric.vendor_data` |
| Vendor CLI and cloud parameters | `vendor_fabric.cli`, `vendor_fabric.cloud_params` |
| Provider clients and provider tool metadata | `vendor_fabric.*` |
| Python SecretSync binding facade | `vendor_fabric.secrets_sync` |
| Generic data primitives and local workflows | `jbcom/extended-data` (`extended-data`) |
| Agent orchestration and framework tool factories | `agentic-fabric` |
| Canonical SecretSync engine, Go CLI, and binding source | `jbcom/secrets-sync` |

MCP bridges are agent-facing transports and therefore belong in `agentic-fabric`, not in this provider-integration package.
