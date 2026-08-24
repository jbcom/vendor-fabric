---
title: Connectors and capabilities
description: Discover connector availability before importing optional provider SDKs.
---

`ConnectorFabric` is the catalog and construction boundary. Known built-ins remain discoverable even when their extras are not installed.

```python
from vendor_fabric import ConnectorFabric

fabric = ConnectorFabric()
print(fabric.list_connector_categories())
print(fabric.list_connectors_by_capability("repositories"))

info = fabric.get_connector_info("github")
if info.available:
    github = fabric.get_connector("github", github_owner="jbcom", github_token="...")
else:
    print(info.install)
```

Direct construction is also available when it is clearer:

```python
from vendor_fabric import GitHubConnector, SlackConnector

github = GitHubConnector(github_owner="jbcom", github_token="...")
slack = SlackConnector(bot_token="xoxb-...")
```

Connector methods promote decoded payloads to the `ExtendedData` family (`ExtendedDict`, `ExtendedList`, or `ExtendedString`) at the public boundary.

## Generic dispatch

Providers declare capability metadata through `@capability`. `VendorData` uses that metadata to select an opened provider or to route an explicit provider id.

```python
from vendor_fabric.vendor_data import VendorData

data = VendorData({"resource": "config"})
data.open("aws")
result = data.call("get_object", "aws", bucket="my-bucket", key="config.json")
```

Do not add a hard-coded facade method when a provider capability and `VendorData.call` express the same contract.
