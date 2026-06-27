# Vendor Fabric

`vendor-fabric` is the optional vendor integration package for the
Extended Data stack. It depends on `extended-data` for primitives,
containers, file sync, inputs, logging, and workflow helpers, then adds API
clients, native vendor sync capabilities, and agentic workflow adapters.

```bash
pip install vendor-fabric
pip install "vendor-fabric[github,slack]"
pip install "vendor-fabric[aws,google,vault,secrets-sync]"
pip install "vendor-fabric[crewai]"
```

The base install exposes the connector and agentic catalogs without requiring
every vendor SDK. Optional connectors report availability and install guidance
through the registry.

Native SecretSync capabilities live in `vendor_fabric.secrets_sync`. They use
Extended Data merge, redaction, export, and sync primitives while delegating
provider IO to Vault, AWS, S3, and future vendor stores.

```{toctree}
:maxdepth: 2

integrations/connectors
secrets-sync/index
agentic/index
ownership-map
api/index
```
