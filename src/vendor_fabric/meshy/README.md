# Meshy Connector

Meshy support is part of `vendor-fabric` and lives under
`vendor_fabric.meshy`. It provides functional API helpers, a
`MeshyConnector` fabric integration, job orchestration, webhook handling, AI tool
adapters, and an MCP server.

## Install

```bash
pip install "vendor-fabric[meshy]"
```

Install the MCP extra too when running `meshy-mcp` or wiring Meshy tools into an
MCP client:

```bash
pip install "vendor-fabric[meshy,mcp]"
```

Use the `vector` extra only when you need local vector search over generated
asset metadata:

```bash
pip install "vendor-fabric[meshy,vector]"
```

The `vector` extra installs `sqlite-vec` for local similarity search.
Embedding generation through `get_embedding()` uses `sentence-transformers`
only when users install it independently after reviewing its `torch` dependency
tree.

## Functional API

```python
from vendor_fabric.meshy import text3d
from vendor_fabric.meshy.models import ArtStyle, Text3DRequest

task_id = text3d.create(
    Text3DRequest(
        mode="preview",
        prompt="game-ready low-poly wooden crate with metal bands",
        art_style=ArtStyle.REALISTIC,
        target_polycount=5000,
        enable_pbr=True,
    )
)

result = text3d.poll(task_id)
print(result["status"])
```

The package also exposes `image3d`, `rigging`, `animate`, and `retexture`
modules from `vendor_fabric.meshy`.

## Connector Fabric

```python
from vendor_fabric import ConnectorFabric
from vendor_fabric.meshy import create_meshy_logger

fabric = ConnectorFabric(inputs={"MESHY_API_KEY": "..."}, from_environment=False)
meshy = fabric.get_connector("meshy")
logger = create_meshy_logger(default_storage_marker="asset-generation")
```

Meshy logging helpers return the same `extended_data.logging.Logging` type as
the rest of the package; they do not configure global Python logging at import
time.

## Job Orchestration

```python
from vendor_fabric.meshy.jobs import AssetGenerator, example_character_spec

generator = AssetGenerator(output_root="client/public")
manifest = generator.generate_model(example_character_spec(), wait=True)

print(manifest["model_path"])
```

Built-in example specs are available as:

- `example_character_spec()`
- `example_prop_spec()`
- `example_environment_spec()`

## Webhooks

`WebhookHandler` can verify raw request bodies before parsing or mutating task
state. Configure a shared secret and pass the raw body plus the signature header
value to `handle_signed_webhook()`:

```python
from vendor_fabric.meshy.webhooks import WebhookHandler

handler = WebhookHandler(repository=repo, webhook_secret="shared-secret")
result = handler.handle_signed_webhook(raw_body, request.headers["X-Webhook-Signature"])
```

Signatures are HMAC-SHA256 over the raw payload bytes. Hex, Base64, URL-safe
Base64, and `sha256=`-prefixed values are accepted. If you do not configure a
secret, `verify_signature()` returns `False` instead of accepting unsigned
payloads.

## Tools And MCP

```python
from vendor_fabric.meshy.tools import get_langchain_tools, get_strands_tools, get_tools

tool_definitions = get_tools()
langchain_tools = get_langchain_tools()
strands_tools = get_strands_tools()
```

Run the Meshy MCP server with:

```bash
meshy-mcp
```
