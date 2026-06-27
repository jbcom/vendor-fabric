# Agentic Reinforcement

This repository creates the provider-aware superclass between `ExtendedData`
and `AgenticData`.

## VendorData Contract

- `VendorData` extends `ExtendedData`.
- Preserve the current facade allocation pattern:
  - `__new__` returns `object.__new__(cls)`
  - `__init__` stores `self._data = ExtendedData(value)`
- Do not collapse `VendorData` into the concrete `ExtendedData` subtype that
  the incoming value would normally promote to.
- Do not replace the internal extended value with raw built-ins just because a
  connector path is convenient.

## What This Repository Owns

- provider registry and availability reporting
- lazy provider activation
- connector capability metadata and dispatch
- the Python facade over SecretSync Go bindings
- credential handoff and data-shaping around SecretSync binding calls
- additive vendor coordination on top of the base `ExtendedData` layer

## What This Repository Does Not Own

- runtime selection
- agent orchestration
- framework runner behavior
- LangChain, CrewAI, LangGraph, Strands, or MCP wrapper factories
- deciding how provider capabilities should be exposed to AI frameworks
- the canonical SecretSync pipeline implementation itself
- the gopy binding source for SecretSync

## Hand-Off To Agentic Fabric

- `agentic-fabric` consumes the provider capabilities defined here.
- Provider modules may keep plain capability functions, schemas, and metadata.
- If a symbol exists only to satisfy an AI framework interface, it belongs in
  `agentic-fabric`, not here.
- The vendor layer exposes capabilities; the agent layer decides how those
  capabilities become tools, runners, and runtime-visible surfaces.
- SecretSync behavior here should wrap the Go/binding layer from
  `jbcom/secrets-sync`, not fork its merge/sync/diff semantics into a separate
  Python implementation.

## Superclass Role

- `VendorData` is the superclass `AgenticData` should extend.
- Keep behavior additive: vendor coordination on top of `ExtendedData`, not
  instead of `ExtendedData`.
- Regression tests should lock down the facade pattern so future edits do not
  silently "simplify" `VendorData` into a different type.
