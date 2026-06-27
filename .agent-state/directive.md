# Continuous Work Directive — vendor-fabric (assessment remediation)

**Status:** ACTIVE
**Owner:** Claude

## Work queue

Source: `ASSESSMENT.md` (full findings at bottom). Each item is one atomic commit.

### Phase 1 — Critical doc/example fixes
- [ ] #1 fix(docs): remove fabricated `sync_secret` API from architecture.rst
- [ ] #2 fix(docs): remove fabricated `get_file("github", owner/repo/path=...)` kwarg shape from architecture.rst; document real `get_repository_file(file_path)` + AWS `get_object(bucket, key)`
- [ ] #3 fix(examples): rewrite `basic_meshy.py` against current `text3d.generate` signature + return shape; remove `mode=`, attribute access, `text3d.get`
- [ ] #4 fix(docs): update `VendorData` code block in architecture.rst to match real `__init__` (capabilities/fabric_kwargs params, `logging` attr, `_active_provider`, fabric fallback)

### Phase 2 — Wrong-identifier / contradiction doc fixes
- [ ] #5 fix(docs): remove false `__dir__` claim from architecture.rst
- [ ] #6 fix(docs): resolve `__SUPPORTS__` contradiction in architecture.rst (code intentionally uses `__supports__`; update doc to reflect, not forbid)
- [ ] #7 fix(docs): fix `_capability_spec` → `_vendor_capabilities` in architecture.rst
- [ ] #8 fix(docs): remove false `typing.Protocol` provider-contracts claim from architecture.rst (or implement the Protocol if a real gap — investigate)
- [ ] #9 fix(docs): fix `connectors.rst` `SlackConnector(slack_bot_token=…)` → `bot_token=`

### Phase 3 — Apidocs toctree + ownership-map
- [ ] #10 docs(apidocs): link `vendor_fabric._optional.rst` into `vendor_fabric.rst` Submodules toctree
- [ ] #11 docs(apidocs): link `vendor_fabric.secrets_sync._binding.rst` into `secrets_sync.rst` Submodules toctree
- [ ] #12 docs(apidocs): link `vendor_fabric.secrets_sync.__main__.rst` into `secrets_sync.rst` Submodules toctree
- [ ] #13 docs(ownership): add ownership-map rows for `vendor_data`, `capabilities`, `surface`, `cloud_params`, `_optional`
- [ ] #14 docs(testing): expand `testing.rst` to cover all 7 plugin fixtures + `--e2e`/markers; trim overstated "mocked provider responses / registry assertions" claim

### Phase 4 — Test gap closures (high-priority)
- [ ] #15 test(registry): add `tests/test_registry.py` — adapters, `BuiltinConnectorSpec`/`ConnectorInfo`, internal helpers (`_normalize_*`, `_discover_connectors`, `_raise_*`, `_get_*`, `_class_connector_info`)
- [ ] #16 test(surface): add `tests/test_surface.py` — `return_annotation`, `annotation_includes_extended_payload`, `connector_data_methods`, `is_connector_data_method`
- [ ] #17 test(persistence): add direct tests for `canonicalize_spec` in meshy persistence utils

### Phase 5 — Repo file + polish
- [ ] #18 docs(repo): write `AGENTS.md` (operating protocols/architecture/patterns; standard-repo profile)
- [ ] #19 chore(meshy): narrow `webhooks/handler.py:185` `except Exception` → `(httpx.HTTPError, OSError)`; add debug log to `jobs.py:141`
- [ ] #20 build(extras): verify `vector` extra (`sqlite-vec`) consuming code path; verify `meshy/webhooks` ↔ `webhooks` extra edge — remove if unused, document if needed

### Deferred (low priority — log only, no commits in this pass)
- More targeted tests for 21 under-named secrets-sync model classes (#9 in ASSESSMENT)
- E2E tests for non-meshy connectors + binding facade (#16)
- Confirm intent of 6/10 connectors bypassing `@capability` facade (#17)

## Operating loop
while queue has [ ] items: implement → verify (lint+typecheck+docs/tests as applicable) → commit → mark [x] → next.

## Forbidden phrases
"deferred" | "v2+" | "out of scope" | "future work" | "tracked separately" | "follow-up"
"TODO" | "FIXME" | "stub" | "placeholder" | "mock for now"