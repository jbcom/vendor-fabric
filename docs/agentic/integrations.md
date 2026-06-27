# Integrations

## SecretSync

Install native SecretSync support through the vendor extra:

```bash
pip install "vendor-fabric[secrets-sync]"
```

The tools live in `vendor_fabric.agentic.tools.secrets_sync` and adapt the
native `vendor_fabric.secrets_sync` API for LangChain, CrewAI, and Strands.

```python
from vendor_fabric.agentic.tools import get_secrets_sync_tools

tools = get_secrets_sync_tools("strands")
```

Registry aliases are available for YAML-configured crews:

- `secrets-sync://validate-config`
- `secrets-sync://run-pipeline`
- `secrets-sync://dry-run`
- `secrets-sync://config-info`
- `secrets-sync://targets`
- `secrets-sync://sources`

## Vendor Connectors

Vendor connector support is installed through explicit extras.

```bash
pip install "vendor-fabric[google]"
pip install "vendor-fabric[slack]"
pip install "vendor-fabric[aws]"
```

The initial vendor and framework extras are:

- `ai`
- `anthropic`
- `aws`
- `crewai`
- `cursor`
- `github`
- `google`
- `langchain`
- `langgraph`
- `mcp`
- `meshy`
- `secrets-sync`
- `slack`
- `strands`
- `vault`
- `vector`
- `webhooks`
- `zoom`
