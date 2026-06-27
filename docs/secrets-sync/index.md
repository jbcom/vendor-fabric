# Native SecretSync

`vendor_fabric.secrets_sync` is a native Python sync layer over Extended Data
and vendor connectors. It uses `extended-data` for generic merge, redaction,
export, `ExtendedData`, and local file sync behavior, then delegates provider IO
to vendor stores such as Vault, AWS Secrets Manager, and S3.

```bash
pip install "vendor-fabric[secrets-sync]"
```

```python
from vendor_fabric.secrets_sync import SecretSyncPipeline, SyncOptions

pipeline = SecretSyncPipeline.from_file("pipeline.yaml")
result = pipeline.run_extended(SyncOptions(dry_run=True, compute_diff=True))

assert "success" in result
```

The same implementation powers non-agentic Python calls, the
`vendor-fabric-secrets-sync` CLI, and agent framework tools under
`vendor_fabric.agentic.tools.secrets_sync`.

## Capability Boundary

- `extended-data>=8.3.0` owns generic data containers, `ExtendedData`, local sync
  primitives, redaction, file decoding, and workflow composition.
- `vendor-fabric` owns provider-backed stores and sync orchestration across
  Vault, AWS Secrets Manager, S3, and future vendors.
- Agent tools are adapters over this native Python API, not a separate bridge
  package.
