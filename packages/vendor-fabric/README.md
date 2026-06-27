# Vendor Fabric

`vendor-fabric` is the optional vendor integration layer for the
Extended Data Python stack. It depends on `extended-data>=8.4.0` for the
polymorphic `ExtendedData` root, concrete containers, local file sync, inputs,
logging, and workflow utilities, then adds
adapter-registered API clients and vendor-backed sync capabilities.

Documentation: [jonbogaty.com/vendor-fabric](https://jonbogaty.com/vendor-fabric/)

```bash
pip install vendor-fabric
pip install "vendor-fabric[github,slack]"
pip install "vendor-fabric[aws,google,vault,secrets-sync]"
pip install secrets-sync-python-binding
pip install pytest-vendor-fabric
```

The base install keeps vendor SDKs out of the environment. Connector metadata
is available even when an optional SDK is absent:

```python
from vendor_fabric import get_connector_info, list_connector_info

print(get_connector_info("github")["available"])
print(list_connector_info(include_unavailable=True))
```

Construct connectors through the registry or `ConnectorFabric`:

```python
from vendor_fabric import ConnectorFabric

fabric = ConnectorFabric(inputs={"GITHUB_TOKEN": "..."})
github = fabric.get_connector("github")
```

Unavailable features report install guidance instead of requiring callers to
wrap their own imports.

SecretSync access is exposed through a binding-backed facade:

```python
from vendor_fabric.secrets_sync import SyncOptions, run_pipeline

result = run_pipeline("pipeline.yaml", SyncOptions(dry_run=True))

print(result["success"])
```

`vendor-fabric` consumes the `secrets_sync` import from
`secrets-sync-python-binding` and shapes those payloads into Extended Data
values. The canonical SecretSync runtime, CLI, pipeline semantics, and gopy
binding source live in `jbcom/secrets-sync`.

Connector and sync payloads are `ExtendedData` values at the boundary. Dict,
list, string, tuple, and set payloads are concrete extended subclasses, so code
can use normal container operations and extended-data methods without import
juggling.

Testing support lives in the separately published `pytest-vendor-fabric`
package. It provides connector fixtures, E2E controls, and credential guards
without forcing test-only dependencies into the runtime package.
