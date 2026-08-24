---
title: Design pillars
description: Six non-negotiable rules for changes to Vendor Fabric.
---

1. **Providers are data extensions.** Inputs and outputs should promote into `ExtendedData` containers where that helps callers inspect, transform, redact, export, or sync data.
2. **Dispatch is capability-driven.** Providers declare capabilities once; avoid a duplicated facade-method matrix.
3. **Optional is discoverable.** Missing extras surface as registry availability and install guidance, never as ordinary-import failures.
4. **Sync is first-class.** File and secret synchronization compose `extended-data` primitives while canonical SecretSync pipeline behavior remains in the binding-backed runtime.
5. **Agent runtime is out of scope.** Vendor Fabric exports provider capabilities, schemas, and metadata; `agentic-fabric` owns runtime loops and framework tool factories.
6. **Tests define provider contracts.** Mocked, optional-dependency, and opt-in E2E testing belong to the public integration contract.
