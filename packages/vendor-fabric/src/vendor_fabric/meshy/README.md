# Meshy Connector

Meshy support is part of `vendor-fabric` and lives under
`vendor_fabric.meshy`. It provides functional API helpers for 2D and 3D
generation, a
`MeshyConnector` fabric integration, job orchestration, webhook handling, and
provider capability metadata.

## Install

```bash
pip install "vendor-fabric[meshy]"
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

### Text to image

```python
from vendor_fabric.meshy import base, text2image

result = text2image.generate(
    "hand-painted forest shrine, orthographic game background",
    ai_model="nano-banana",
    aspect_ratio="16:9",
)

base.download(result["image_urls"][0], "art/forest-shrine.png")
```

`text2image.generate(..., wait=False)` returns the submitted task ID. With the
default `wait=True`, it polls `GET /openapi/v1/text-to-image/{id}` until the
task succeeds and returns the complete extended task payload. Failed,
canceled, and expired tasks raise a redacted `RuntimeError`; HTTP errors use
`MeshyAPIError`. HTTP 429 honors `Retry-After`, and 429, 5xx, and timeout
failures enter the shared five-attempt exponential retry policy through
`RateLimitError`.

For a persisted sidecar manifest plus automatic download of
`image_urls[0]`, use the job helper:

```python
from vendor_fabric.meshy.jobs import ImageGenerator

generator = ImageGenerator(output_root="client/public")
manifest = generator.generate_image(
    "hand-painted forest shrine, orthographic game background",
    output_path="art/forest-shrine.png",
)
print(manifest["image_path"])
```

The package also exposes `image2image`, `image3d`, `multiimage3d`, `remesh`,
`rigging`, `animate`, and `retexture` modules from `vendor_fabric.meshy`.
The image-to-image, multi-image-to-3D, and remesh modules use the same
`create` / `get` / `poll` / high-level helper pattern as the original 3D
modules. Task families documented by Meshy with collection and deletion
operations also expose `list_tasks` and `delete`.

## API Coverage

The connector covers Meshy's general generation pipeline: text-to-image,
image-to-image, text-to-3D, image-to-3D, multi-image-to-3D, remesh, retexture,
rigging, and animation. The account balance endpoint and specialized Convert,
Resize, UV Unwrap, Multi-Color Print, Analyze Printability, Repair Printability,
and product-scoped Creative Lab APIs are deliberately outside this generation
connector pass. Streaming endpoints are also deferred because this connector's
established task contract is polling plus webhooks; adding an SSE transport
would be a distinct public API rather than another task module.

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

## Capability Metadata

```python
from vendor_fabric.meshy.tools import TOOL_DEFINITIONS, text3d_generate

tool_names = [definition["name"] for definition in TOOL_DEFINITIONS]
result = text3d_generate("game-ready low-poly wooden crate with metal bands")
```

Agent-facing tool transports, including MCP wrappers, live in
`agentic-fabric` and should consume this capability metadata.
