---
title: Testing integrations
description: Test provider code locally while keeping paid API calls explicitly opt-in.
---

`pytest-vendor-fabric` is the supported plugin for projects that test code built on Vendor Fabric.

```bash
python -m pip install pytest-vendor-fabric
```

It provides `mock_logger`, `base_connector_kwargs`, `anthropic_api_key`, `skip_without_anthropic`, `check_api_key`, and `check_aws_credentials`, registers the `e2e` marker, and skips marked live tests unless `--e2e` is explicit.

```python
def test_connector(base_connector_kwargs):
    assert base_connector_kwargs["from_environment"] is False


def test_mocked_connector(mock_logger):
    assert mock_logger.logger is not None
```

```bash
# Provider SDK unit tests with the coverage gate.
tox -e providers

# Paid/live provider tests: credentials and explicit opt-in are both required.
tox -e e2e -- --e2e
```

The release-quality matrix includes lint, strict mypy, Python 3.11–3.14, plugin tests, provider coverage of at least 90%, Sourcey documentation, and package builds.
