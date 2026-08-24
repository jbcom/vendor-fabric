---
title: Architecture
description: The boundaries that keep vendor integration, data primitives, and agent runtime independent.
---

```text
caller
  -> VendorData(fabric=ConnectorFabric())
     -> registry.get_connector_adapter(name)
        -> ConnectorBase subclass
           -> capability-decorated provider method
              -> ExtendedData-shaped payload
```

## Ownership boundary

Vendor Fabric owns provider discovery, connector base classes, SDK adapters, capability metadata and dispatch, provider-backed sync, the Python SecretSync facade, and provider-test support.

`extended-data` owns generic containers, inputs, logging, files, and workflows. `agentic-fabric` owns agent runtime orchestration, crew discovery, runner selection, and framework-specific tools.

## VendorData

`VendorData` preserves the `ExtendedData` contract while carrying a lazily created `ConnectorFabric`, optional logging, declared capabilities, provider caches, and an active provider. Use `open(provider_id)` to establish a provider context and `call(operation, provider_id, **kwargs)` for generic dispatch.

The facade can inspect its routes with `capabilities()`, `capability_matrix()`, and `supports(provider, operation)`. It does not create a dynamic directory listing; ordinary static API inspection remains reliable.

## Optional dependencies

Connector modules use `require_extra(extra, module)` at the point an SDK is needed. Fallback exception shims keep imports usable without extras, while the registry supplies concrete install guidance.
