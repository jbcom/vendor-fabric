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

## Webhook safety

The optional Cursor connector accepts webhook callbacks only over HTTPS. Before a
webhook is used, it rejects loopback, private, link-local, unspecified, and
cloud-metadata addresses so a caller cannot use the connector to reach an
internal service.

## Steam sessions and redemption limits

The Steam connector implements Steam's `IAuthenticationService` login flow
directly over HTTPS, so no third-party Steam SDK is required. Only the RSA step
needs an extra: `pip install vendor-fabric[steam]`.

```python
from vendor_fabric import SteamConnector

with SteamConnector(account_name="user", password="...") as steam:
    steam.authenticate(steam_guard_code="ABCDE")
    owned = steam.list_owned_apps()
    outcome = steam.redeem_key("AAAAA-BBBBB-CCCCC")
```

Two behaviours are easy to get wrong and are handled explicitly:

- **Session ids are per-domain.** Steam issues a different `sessionid` cookie
  for `store.`, `help.`, and `steamcommunity.com`. Flattening the jar yields a
  token the store rejects, so `SteamSession.session_id(domain)` always takes the
  domain being posted to.
- **Failures are scarcer than successes.** Steam permits roughly 50 activations
  per hour but only 10 *failed* ones, and duplicates count as failures. Check
  ownership with `list_owned_apps()` before redeeming. `redeem_keys()` stops as
  soon as Steam reports `RedemptionResult.RATE_LIMITED`, because further
  attempts during a cooldown only extend it.

A missing `purchase_result_details` is reported as `RedemptionResult.UNKNOWN`
rather than being assumed to be a rate limit, so an unexpected failure surfaces
instead of turning into an unbounded retry.

Errors arrive in the `x-eresult` response header rather than the HTTP status or
body — a rejected password is an `HTTP 200` with an empty JSON body — so
responses are validated against that header.
