# Cloud Connectors

`cloud-connectors` is the optional vendor integration layer for the
Extended Data Python stack. It depends on `extended-data` for primitives,
containers, file IO, inputs, logging, and workflow utilities, then adds
adapter-registered API clients for external systems.

```bash
pip install cloud-connectors
pip install "cloud-connectors[github,slack]"
pip install "cloud-connectors[aws,google,vault]"
```

The base install keeps vendor SDKs out of the environment. Connector metadata
is available even when an optional SDK is absent:

```python
from cloud_connectors import get_connector_info, list_connector_info

print(get_connector_info("github")["available"])
print(list_connector_info(include_unavailable=True))
```

Construct connectors through the registry or `ConnectorFabric`:

```python
from cloud_connectors import ConnectorFabric

fabric = ConnectorFabric(inputs={"GITHUB_TOKEN": "..."})
github = fabric.get_connector("github")
```

Unavailable features report install guidance instead of requiring callers to
wrap their own imports.
