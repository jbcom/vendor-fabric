---
title: Vendor Fabric
description: Data-native vendor connectors and synchronization capabilities for Extended Data.
---

![A woven data fabric connecting vendor services](assets/vendor-fabric-hero.png)

Vendor Fabric is the optional integration layer for the Extended Data stack. It keeps provider SDKs optional, exposes a discoverable connector catalog, and returns `ExtendedData`-shaped results so vendor data composes with the rest of the stack.

::card{title="Install only what you use" icon="package"}
The base package exposes the catalog without installing every vendor SDK. Extras add the providers you select.
::

::card{title="Route by capability" icon="route"}
Providers declare capabilities once; `VendorData` and `ConnectorFabric` discover and dispatch them consistently.
::

::card{title="Keep sync native" icon="refresh-cw"}
The SecretSync facade shapes Python results and credentials while preserving the canonical SecretSync runtime boundary.
::

## What belongs here

- Vendor discovery, connector adapters, provider SDK integration, capability dispatch, and provider-backed sync.
- `VendorData`, the public provider-aware data facade.
- `pytest-vendor-fabric`, the companion plugin for mocked provider tests and opt-in live E2E tests.

`extended-data` owns generic data primitives. `agentic-fabric` owns runtime orchestration and framework-facing agent tooling.

## Fast path

```bash
python -m pip install "vendor-fabric[github,slack]"
```

```python
from vendor_fabric import ConnectorFabric

fabric = ConnectorFabric()
info = fabric.get_connector_info("github")
if info.available:
    github = fabric.get_connector("github", github_owner="jbcom", github_token="...")
```

Continue with [installation](installation.md), then learn the [connector catalog](connectors.md).
