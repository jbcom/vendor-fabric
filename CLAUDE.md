<!-- profile: python-lib agent-state standard-repo v1 -->
# vendor-fabric

`uv` workspace for the Vendor Fabric Python stack — data-native vendor connectors and sync capabilities for the Extended Data stack, plus `pytest-vendor-fabric` fixtures.

## Profiles loaded

@/Users/jbogaty/.claude/profiles/python-lib.md
@/Users/jbogaty/.claude/profiles/agent-state.md
@/Users/jbogaty/.claude/profiles/standard-repo.md

## Repo-specific

Workspace root (`pyproject.toml` is `package = false`); packages live under `packages/vendor-fabric` and `packages/pytest-vendor-fabric`. All commands run from repo root.

- **Sync:** `uv sync --all-packages`
- **Test (matrix, py311–py314):** `tox -e py311,py312,py313,py314`
- **Test (pytest plugin pkg):** `tox -e plugin`
- **Test (providers + coverage ≥90):** `tox -e providers`
- **E2E (opt-in, paid APIs):** `tox -e e2e -- --e2e`
- **Lint:** `tox -e lint` (ruff check, `select=ALL` with curated ignores, line-length 120, target py311)
- **Typecheck:** `tox -e typecheck` (mypy strict)
- **Build (per-package wheels):** `tox -e build`
- **Docs:** `tox -e docs` (Sphinx `-W -E -b html docs docs/_build/html`)

`skip_missing_interpreters = false` — all of py311/312/313/314 are required; missing interpreters fail rather than skip.

## Notes

- **Pillars (`docs/pillars.rst`) are the project's non-negotiable design rules:**
  - Providers are data extensions of `ExtendedData`, not utility islands.
  - Capability-driven dispatch — providers declare capabilities once; facade routes generically; avoid hardcoded pass-throughs.
  - Optional means discoverable — missing extras surface via registry state + install guidance, never import failures in ordinary imports.
  - Sync (file + secret) is a first-class capability; compose `extended-data` primitives, delegate canonical SecretSync pipeline semantics to the `jbcom/secrets-sync` binding facade.
  - Agent runtime is out of scope — belongs in `agentic-fabric`. This package exposes capability functions/schemas/metadata only.
  - Tests define the public provider contract; `pytest-vendor-fabric` must make downstream testing straightforward.
- **Boundary (`docs/architecture.rst`):** `vendor-fabric` owns vendor behavior for the Extended Data stack (discovery, connector base classes, SDK adapters, capability dispatch, sync, SecretSync binding facade, pytest support). `extended-data` owns base data primitives; `agentic-fabric` owns agent runtime. `VendorData` extends `ExtendedData` with provider context.
- **Docs are Sphinx (.rst)** under `docs/` — `index.rst`, `architecture.rst`, `pillars.rst`, `integrations/`, `secrets-sync/` subdir, `testing.rst`, `ownership-map.rst`, `api/`. Build with `tox -e docs` (treats warnings as errors).
- **release-please-config.json** present; workflows: `ci.yml`, `release.yml`, `cd.yml`, `automerge.yml`.
- **AGENTS.md: missing** — standard-repo requires it for extended operating protocols/architecture/patterns. Flag as a gap to create; do not inline that content in CLAUDE.md.