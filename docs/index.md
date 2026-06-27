# Cloud Connectors

`cloud-connectors` is the optional vendor integration package for the
Extended Data stack. It depends on `extended-data` for base data primitives,
inputs, logging, and workflow helpers, then adds API clients for external
systems through a central adapter registry.

```bash
pip install cloud-connectors
pip install "cloud-connectors[github,slack]"
pip install "cloud-connectors[aws,google,vault]"
```

The base install exposes the connector catalog without requiring every vendor
SDK. Optional connectors report availability and install guidance through the
registry.

SecretSync is owned by the standalone
[`jbcom/secrets-sync`](https://github.com/jbcom/secrets-sync) repository. Use
`secrets-sync-bridge` for Python bridge runtime access, and use
`agentic-crew[secrets-sync]` for agent framework tools.

```{toctree}
:maxdepth: 2

integrations/connectors
ownership-map
api/index
```
