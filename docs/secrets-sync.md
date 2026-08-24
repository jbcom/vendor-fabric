---
title: SecretSync facade
description: Use the binding-backed SecretSync integration without creating a second pipeline engine.
---

`vendor_fabric.secrets_sync` is a Python integration facade over the canonical SecretSync runtime owned by `jbcom/secrets-sync`. It adapts credentials and results to the Vendor Fabric boundary; it does not own a competing pipeline implementation.

```bash
python -m pip install "vendor-fabric[secrets-sync]"
python -m pip install secrets-sync-python-binding
```

```python
from vendor_fabric.secrets_sync import ProviderSession, SyncOptions, get_targets, run_pipeline

result = run_pipeline("pipeline.yaml", SyncOptions(dry_run=True, compute_diff=True))
targets = get_targets("pipeline.yaml")

session = ProviderSession(vault_address="https://vault.example.com", vault_token=vault_token)
session_result = run_pipeline("pipeline.yaml", SyncOptions(dry_run=True), provider_session=session)
```

When provider authentication is available, pass it through `ProviderSession`; do not log or persist raw credential values. The supported contract is the `secrets_sync` module from `secrets-sync-python-binding`.

The `vendor-fabric-secrets-sync` command uses the same facade. Agent runtime orchestration belongs to `agentic-fabric`; use `vendor_fabric.vendor_data.VendorData` as this package's capability facade.
