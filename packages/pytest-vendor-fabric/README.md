# pytest-vendor-fabric

`pytest-vendor-fabric` provides reusable pytest fixtures for projects that test
code built on `vendor-fabric`.

```bash
pip install pytest-vendor-fabric
```

The plugin registers:

- E2E controls: `--e2e` and `--framework`
- Connector fixtures: `mock_logger` and `base_connector_kwargs`
- Credential guards: `check_api_key` and `check_aws_credentials`

Live E2E tests remain opt-in. They are skipped unless `--e2e` is passed and
their credential fixtures find the required environment variables.

Agent runtime fixtures live in `pytest-agentic-fabric`; this package stays
focused on provider-facing tests.
