# Connectors

Vendor connectors are not a separate product in this major version. They are
first-class Tier 3 data integrations under `cloud_connectors`.

```python
from cloud_connectors import ConnectorFabric, GitHubConnector, SlackConnector

fabric = ConnectorFabric()
print(fabric.list_connector_categories())
print(fabric.list_connectors_by_capability("repositories"))

github_info = fabric.get_connector_info("github")
if github_info.available:
    github = fabric.get_connector("github", github_owner="jbcom", github_token="...")
else:
    print(github_info.install)
```

Direct construction is available when it is clearer:

```python
github = GitHubConnector(github_owner="jbcom", github_token="...")
slack = SlackConnector(slack_bot_token="xoxb-...")
```

## Catalog Metadata

Connector adapters describe install extras, category, capabilities, module,
class, and runtime availability. Known built-ins stay visible even when their
optional SDKs are not installed.

```python
info = fabric.get_connector_info("github")
print(info.extra)
print(info.category)
print(info.capabilities)
print(info.available)

adapter = fabric.get_connector_adapter("github")
print(adapter.available)
```

Connector methods return promoted data payloads at the boundary. Decoded API,
SDK, GraphQL, and webhook maps can use `ExtendedDict`, `ExtendedList`, and
`ExtendedString` methods immediately.
