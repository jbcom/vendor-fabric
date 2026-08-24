---
title: Installation
description: Install the core catalog and the provider extras your application needs.
---

## Base package

```bash
python -m pip install vendor-fabric
```

The base install is deliberately lightweight. It can inspect built-in connectors and reports a missing SDK as an unavailable connector with an install hint instead of failing a normal package import.

## Provider extras

```bash
python -m pip install "vendor-fabric[github,slack]"
python -m pip install "vendor-fabric[aws,google,vault,secrets-sync]"
python -m pip install "vendor-fabric[meshy]"
```

Use the smallest extra set that covers your integration. The current extras include `aws`, `google`, `github`, `slack`, `vault`, `anthropic`, `meshy`, `webhooks`, `vector`, and `secrets-sync`.

## Workspace development

This repository is a `uv` workspace with two distributions: `vendor-fabric` and `pytest-vendor-fabric`.

```bash
uv sync --all-packages --all-extras --dev
tox -e lint,typecheck,py311,py312,py313,py314,plugin,providers,docs,build
```

The supported Python contract is 3.11 through 3.14. Missing interpreters fail the matrix rather than silently skipping it.
