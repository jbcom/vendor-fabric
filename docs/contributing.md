---
title: Contributing and release workflow
description: Make an auditable change that preserves the package boundaries and release history.
---

Use an upstream topic branch, make Conventional Commits, and open a pull request. Do not push directly to `main`, force-push shared history, or use squash/rebase merging.

```bash
uv sync --all-packages --all-extras --dev
tox -e lint,typecheck,py311,py312,py313,py314,plugin,providers,docs,build
```

Changes follow **docs → tests → code**. Preserve the six design pillars, redact diagnostics, and make optional dependencies discoverable.

`release-please` owns versions, changelogs, tags, and GitHub releases. A release is then validated and published by the trusted delivery workflow using PyPI OIDC; documentation is rebuilt from trusted tagged source and deployed to GitHub Pages.

Repository-root `AGENTS.md` is operational guidance for contributors and coding agents. The generated `llms.txt` and `llms-full.txt` in a Sourcey build are public documentation-context exports; they are not a second set of repository instructions.
