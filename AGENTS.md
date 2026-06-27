---
title: Agent Operating Protocols
updated: 2026-06-27
status: current
domain: technical
---

# AGENTS.md — vendor-fabric

Extended operating protocols for AI agents working in this repository.
The companion `CLAUDE.md` is the thin entry point (identity, commands,
repo-specific notes); this file holds the architecture, patterns, and
non-negotiables that every change must respect.

## Architecture at a glance

`vendor-fabric` is the optional vendor integration package for the
Extended Data stack. Two packages live in this `uv` workspace:

- **`packages/vendor-fabric`** — connector catalog, capability
  dispatch, SecretSync binding facade, vendor CLI.
- **`packages/pytest-vendor-fabric`** — pytest fixtures, credential
  guards, and the `--e2e` opt-in control for downstream test suites.

### Boundary

`vendor-fabric` owns vendor behavior: discovery, connector base
classes, SDK adapters, capability dispatch, sync, the SecretSync
binding facade, and pytest support. `extended-data` owns base data
primitives (`ExtendedData`, containers, inputs, logging, files,
workflows). `agentic-fabric` owns agent runtime orchestration. Full
boundary in `docs/architecture.rst` and `docs/ownership-map.rst`.

### Data flow

```
caller
  └─ VendorData(fabric=ConnectorFabric())
       └─ ConnectorFabric.get_connector(name, **kwargs)
            └─ registry.get_connector_adapter(name)
                 └─ BuiltinConnectorAdapter.load_class()
                      └─ ConnectorBase subclass (aws/google/github/...)
                           └─ @capability-decorated method
                                └─ extend_result() -> ExtendedData payload
```

The capability registry (`vendor_fabric.capabilities`) lets providers
declare operations once; `VendorData.call(operation, provider_id, ...)`
routes generically. The catalog metadata (`BUILTIN_CONNECTORS`) drives
`list_connectors_by_capability` / `list_connectors_by_category` for
discovery without instantiation.

## Non-negotiables

These come from `docs/pillars.rst`. Every change must keep them true.

1. **Providers are data extensions of `ExtendedData`**, not utility
   islands. Provider inputs and outputs promote into extended
   containers (`ExtendedDict`/`ExtendedList`/`ExtendedString`).
2. **Capability-driven dispatch.** Providers declare capabilities once;
   the facade routes generically. Avoid hardcoded pass-through methods
   when a `@capability` decorator + `VendorData.call` works.
3. **Optional means discoverable.** Missing extras surface via registry
   state + install guidance (`_optional.require_extra` re-raises with
   `pip install vendor-fabric[extra]`), never via import failures in
   ordinary package imports.
4. **Sync is a first-class capability.** Compose `extended-data`
   primitives; delegate canonical SecretSync pipeline semantics to the
   `secrets_sync` binding facade (`vendor_fabric.secrets_sync._binding`).
5. **Agent runtime is out of scope.** This package exposes capability
   functions/schemas/metadata only. Agent orchestration belongs in
   `agentic-fabric`.
6. **Tests define the public provider contract.** `pytest-vendor-fabric`
   must make downstream testing straightforward.

## Patterns

### Optional dependencies

Every connector that needs a third-party SDK follows the same pattern:

```python
# In the connector module
from vendor_fabric._optional import require_extra

def _load_sdk():
    return require_extra("aws", "boto3")  # re-raises ImportError with install hint
```

The fallback exception shims (`ClientError`, `VaultError`, etc.) at the
top of connector modules keep `import vendor_fabric.aws` working without
the SDK installed. The registry reports the connector as unavailable
with install guidance, not as an import failure.

### Capability declaration

```python
from vendor_fabric.capabilities import capability

class AWSConnector(ConnectorBase):
    @capability("get_file", kind="files", aliases=("read_file",))
    def get_object(self, bucket: str, key: str, *, decode: bool = True) -> ExtendedDict:
        ...
```

`CapabilityProviderMixin.__init_subclass__` collects `_vendor_capabilities`
across the MRO. `VendorData.call("get_file", "aws", bucket=..., key=...)`
resolves the route and dispatches.

### Diagnostics / redaction

Every connector ships a `_diagnostics.py` (or inline `_safe_*` helpers)
that redacts sensitive values from error messages and tracebacks. The
`noqa: TRY400` suppressions on logger calls are intentional —
tracebacks can expose raw credentials. Never remove them without a
replacement redaction path.

### Secrets-sync binding facade

`vendor_fabric.secrets_sync._binding` delegates to the
`secrets_sync` import from `secrets-sync-python-binding`. The
module-level functions in `pipeline.py` are thin wrappers. The native
Python helpers (`stores.py`, `graph.py`, `files.py`) are transitional
compatibility scaffolding — do not grow them into a second pipeline
implementation.

## Commands

All commands run from the repo root.

| Task | Command |
|------|---------|
| Sync workspace | `uv sync --all-packages` |
| Lint | `tox -e lint` (ruff `select=ALL`, line-length 120, target py311) |
| Typecheck | `tox -e typecheck` (mypy strict) |
| Test matrix | `tox -e py311,py312,py313,py314` |
| Plugin tests | `tox -e plugin` |
| Providers + coverage ≥90 | `tox -e providers` |
| E2E (opt-in, paid APIs) | `tox -e e2e -- --e2e` |
| Docs (warnings-as-errors) | `tox -e docs` |
| Build wheels | `tox -e build` |

`skip_missing_interpreters = false` — all of py311/312/313/314 are
required; missing interpreters fail rather than skip.

## Definition of done for any change

1. **Docs → Tests → Code.** Document behavior, write the failing test,
   implement. Spec wrong? Revise spec → test → resume.
2. **Lint + typecheck + tests pass** for the affected tox environments.
3. **Docs build clean** (`tox -e docs` with `-W`).
4. **Coverage gate**: `tox -e providers` must stay ≥90%.
5. **Pillars intact**: the change does not violate any of the six
   pillars above.
6. **No stubs**: no `TODO`/`FIXME`/`pass`/`...`/`NotImplementedError`/
   `as any`/`it.todo`/`# stub`/`# placeholder`. These are bugs.
7. **One commit per issue**, Conventional Commits (`feat:`/`fix:`/
   `chore:`/`docs:`/`refactor:`/`test:`/`perf:`/`build:`/`ci:`).

## Release

`release-please-config.json` is present; versioning is release-please's
job. Workflows: `ci.yml`, `release.yml`, `cd.yml`, `automerge.yml`. Do
not pick versions, gate directives on version milestones, or encode
versions in commit messages — the Conventional Commits prefix is the
only version-shaping input.

## Files agents should know

| File | Purpose |
|------|---------|
| `docs/pillars.rst` | The six non-negotiable design rules |
| `docs/architecture.rst` | Boundary, VendorData, capability registry, sync |
| `docs/ownership-map.rst` | What belongs here vs. `extended-data`/`agentic-fabric` |
| `docs/integrations/connectors.rst` | Connector usage examples |
| `docs/secrets-sync/index.rst` | SecretSync binding facade usage |
| `docs/testing.rst` | pytest-vendor-fabric fixture inventory |
| `docs/api/internal.rst` | Orphaned-but-reachable internal modules (`_optional`, `_binding`) |
| `tox.ini` | All test/lint/build/docs environments |
| `pyproject.toml` | Workspace config, ruff/mypy/coverage settings |
| `packages/vendor-fabric/pyproject.toml` | Extras, entry-points, package metadata |
| `.agent-state/directive.md` | The active work queue (this file drives continuous work) |
| `ASSESSMENT.md` | The completeness audit that produced the current remediation queue |