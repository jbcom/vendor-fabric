# Vendor Fabric Workspace

This repository is a `uv` workspace for the Vendor Fabric Python stack.

Documentation: [jonbogaty.com/vendor-fabric](https://jonbogaty.com/vendor-fabric/)

## Packages

- `packages/vendor-fabric`: Extended Data-native vendor connectors and sync capabilities.
- `packages/pytest-vendor-fabric`: pytest fixtures and optional-runtime mocks for testing code built on Vendor Fabric.

## Common Commands

```bash
uv sync --all-packages
tox -e lint
tox -e typecheck
tox -e py311,py312,py313,py314
tox -e plugin
tox -e providers
tox -e docs
tox -e build
```

``providers`` installs the optional provider SDK extras used by AWS, Google,
GitHub, Slack, Vault, and MCP unit tests. Live E2E tests remain opt-in.

Live provider E2E tests are opt-in and may call paid provider APIs:

```bash
tox -e e2e -- --e2e
```

The test matrix intentionally does not skip missing Python interpreters. Python
3.11, 3.12, 3.13, and 3.14 are all part of the supported release contract.

`AGENTS.md` contains the active local migration plan for Codex sessions.
