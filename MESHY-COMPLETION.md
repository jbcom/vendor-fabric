# Meshy Connector Completion

## Added

- Added `vendor_fabric.meshy.text2image` for
  `POST /openapi/v1/text-to-image` and
  `GET /openapi/v1/text-to-image/{id}`, with the connector's established typed
  request/result, shared HTTP, retry/rate-limit, redacted error, polling, and
  extended-data contracts.
- Added text-to-image task listing and deletion, `wait=False` submission,
  `image_urls[0]` download support, `MeshyConnector.text2image_generate`, and a
  framework-neutral `text2image_generate` capability.
- Added `ImageGenerator` job orchestration. It persists a pending sidecar
  manifest immediately, polls when requested, downloads `image_urls[0]`, and
  updates the manifest with the successful image path and source URL.
- Fixed create-response task ID extraction for Meshy's real response variants:
  `result`, `id`, `task_id`, and nested `result.id`/`result.task_id`.
- Added `CANCELED` as a terminal task state rather than allowing canceled work
  to poll until timeout.
- Added the other general generation-pipeline gaps found in the official docs:
  `image2image`, `multiimage3d`, and `remesh`. Each follows the existing module
  pattern (`create`, `get`, `poll`, high-level helper), plus the documented list
  and delete operations and `MeshyConnector` facade methods.
- Updated Meshy exports, provider metadata, payload contracts, capability
  metadata, models, tests, and the connector README.

## Official API research

The current official endpoint index is <https://docs.meshy.ai/en/api>. The
implemented additions were checked against the current Text to Image,
Image to Image, Multi-Image to 3D, and Remesh pages:

- <https://docs.meshy.ai/en/api/text-to-image>
- <https://docs.meshy.ai/en/api/image-to-image>
- <https://docs.meshy.ai/en/api/multi-image-to-3d>
- <https://docs.meshy.ai/en/api/remesh>

The official index also lists general endpoints that remain outside this pass:

- Convert, Resize, and UV Unwrap: specialized post-processing APIs, not needed
  for the 2D fleet consolidation or the existing generation pipeline blocker.
- Multi-Color Print, Analyze Printability, and Repair Printability: specialized
  additive-manufacturing workflows with their own result contracts.
- Balance: account metadata rather than asset generation.
- Keychain, Fridge Magnet, Figure, Vinyl Figure, Brick Figure, Lamp, and Keycap:
  product-scoped Creative Lab APIs with separate, independently versioned
  prototype/build workflows.
- SSE stream routes: deliberately not added. This connector's established
  asynchronous contract is polling plus webhooks; introducing an SSE client is
  a separate transport design, not another matching endpoint module.
- Collection/deletion routes on older already-supported endpoint modules were
  not retrofitted because they are task administration, not a missing creation
  capability. The newly added v1 modules include them because their current
  contracts were being introduced from scratch.

## Verification

- Red phase: the new tests failed collection before the new modules, facade
  methods, and job helper existed.
- Mutation proof:
  - Removing `id`/`task_id` create-response support caused 2 of 4 task-ID-shape
    cases to fail.
  - Downloading the last image instead of `image_urls[0]` caused both the
    endpoint download test and persisted job test to fail.
  - Treating `CANCELED` as success caused the terminal-state polling test to
    fail.
  - Pointing multi-image-to-3D at the image-to-3D route caused its create and
    retrieve contract tests to fail.
- Focused Meshy/payload suite: 611 passed.
- Full provider suite: 1,483 passed, 6 skipped (the paid/credentialed Meshy E2E
  test and installed-extra branch tests).
- Python 3.11, 3.12, 3.13, and 3.14 full suites: 1,483 passed and 6 skipped in
  each environment. The existing `providers` environment supplied Python 3.14
  because the checkout's `py314` tox environment had no pytest executable.
- Coverage: 90.49%, satisfying the 90% provider gate.
- Ruff: passed.
- Mypy strict: passed for all 78 source files.
- Pytest plugin suite: 9 passed.
- Sphinx warnings-as-errors build: passed.
- Both workspace distributions built successfully as sdists and wheels through
  their configured Hatchling backend. A zip-import smoke from the built
  `vendor-fabric` wheel loaded all four new modules and the connector facade.
- `git diff --check`: passed.

## Next-agent notes

- The completed implementation is committed with message `feat(meshy):
  complete image generation pipeline`. It was not pushed and no PR was opened.
- The tox build command's uv 0.9.9 wrapper panicked in macOS
  `system-configuration` while network access was disabled, even with
  `--offline` and a writable temporary cache. Running the configured Hatchling
  backend directly from the existing build environment produced and verified
  both packages without network access.
- No live Meshy calls were made and no credits were consumed. The existing E2E
  remains opt-in via `--e2e` and requires a scoped `MESHY_API_KEY`.
