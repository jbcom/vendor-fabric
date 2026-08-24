# Contributing to Vendor Fabric

Start from an upstream topic branch and open a pull request against `main`.
Use meaningful Conventional Commits such as `feat:`, `fix:`, `docs:`, `test:`,
`ci:`, or `chore:`. Never push directly to `main`, force-push shared history,
or squash/rebase merge a pull request.

Run the complete local contract before marking a PR ready:

```bash
uv sync --all-packages --all-extras --dev
pre-commit run --all-files
tox -e lint,typecheck,py311,py312,py313,py314,plugin,providers,docs,build
```

Read `AGENTS.md` for architecture boundaries and provider-specific rules. The
repository uses Sourcey for documentation; use `npm run validate --prefix docs`
for its locked, subdirectory-aware build.

Live E2E tests can call paid provider APIs. They are intentionally not part of
the default suite: run `tox -e e2e -- --e2e` only with approved credentials.
