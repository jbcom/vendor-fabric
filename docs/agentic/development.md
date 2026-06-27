# Development

Use tox for local validation:

```bash
tox -e lint
tox -e typecheck
tox -e py311
tox -e docs
tox -e build
```

Optional framework tests should be explicit about their dependencies and should
skip cleanly when the relevant extra is not installed.

Before moving code out of an old monorepo, first prove that the new repository
owns the code with tests, docs, package metadata, and release workflows.
