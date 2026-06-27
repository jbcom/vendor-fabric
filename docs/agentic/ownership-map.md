# Ownership Map

`vendor_fabric.agentic` owns agent orchestration and agent-facing tool adapters.
It is the destination for moved agent integration code from `~/src/jbcom/agentic`
and from agent-oriented surfaces in `~/src/jbcom/extended-data-library`.

The split is intentionally explicit:

- `extended-data` owns primitives, containers, IO helpers, input handling,
  redaction, logging, and workflow utilities.
- `vendor-fabric` owns vendor API clients, connector registries, vendor SDK
  dependency extras, native SecretSync, crew discovery, runner selection,
  framework adapters, and agent tool wrappers.

## Moved Surfaces

SecretSync agent tools live in `vendor_fabric.agentic.tools.secrets_sync`. They adapt the
native `vendor_fabric.secrets_sync` API and use `extended-data` primitives for
redaction, sync, and structured return payloads. They are loaded lazily through
`vendor_fabric.agentic.tools.registry`, so core imports do not require SecretSync or
vendor packages.

Vendor integrations remain domain-owned by `vendor-fabric`; agent wrappers are
part of that same package because they compose vendor capabilities.

Crew and runner code belongs under `vendor_fabric.agentic.core`, `vendor_fabric.agentic.runners`,
and `vendor_fabric.agentic.crews`. Remaining orchestration code in the old local
`agentic` checkout should move here before the source checkout is retired.

## Cleanup Rule

Do not delete old monorepo surfaces just because they are no longer desired in
place. First move the implementation to the owning package, add tests and docs
here, then remove the obsolete source after the destination is validated.
