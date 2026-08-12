Meshy text-to-image
===================

``vendor_fabric.meshy`` is the sole Meshy transport for downstream declarative
generators. ``text2image`` uses the connector's shared credentials, rate limit,
redacted errors and five-attempt exponential retry policy. The generic
``generate_image`` capability routes through the selected connector instance,
so direct ``inputs`` credentials never fall back to unrelated module-global
state. ``ImageGenerator`` rejects absolute or traversing output paths before
task creation, then persists a pending sidecar
before polling, downloads ``image_urls[0]`` and then persists the completed
local path and source URL.

The higher-level standalone ``meshy-content-generator`` package depends on this
boundary and must not recreate HTTP, authentication, polling or downloads.
Its credit-free dry run does not import the provider at all.
