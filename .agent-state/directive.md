# Continuous Work Directive — vendor-fabric (assessment remediation)

**Status:** RELEASED
**Owner:** Claude

All 20 remediation items complete. See ASSESSMENT.md for the original
findings and the git log on `fix/assessment-remediation` for the per-item
commits.

## Work queue

### Phase 1 — Critical doc/example fixes
- [x] #1 fix(docs): remove fabricated `sync_secret` API from architecture.rst
- [x] #2 fix(docs): remove fabricated `get_file("github", owner/repo/path=...)` kwarg shape from architecture.rst
- [x] #3 fix(examples): rewrite `basic_meshy.py` against current `text3d.generate` signature + return shape
- [x] #4 fix(docs): update `VendorData` code block in architecture.rst to match real `__init__`

### Phase 2 — Wrong-identifier / contradiction doc fixes
- [x] #5 fix(docs): remove false `__dir__` claim from architecture.rst
- [x] #6 fix(docs): resolve `__SUPPORTS__` contradiction in architecture.rst
- [x] #7 fix(docs): fix `_capability_spec` → `_vendor_capabilities` in architecture.rst
- [x] #8 fix(docs): remove false `typing.Protocol` provider-contracts claim from architecture.rst
- [x] #9 fix(docs): fix `connectors.rst` `SlackConnector(slack_bot_token=…)` → `bot_token=`

### Phase 3 — Apidocs toctree + ownership-map
- [x] #10 docs(apidocs): link `vendor_fabric._optional.rst` into toctree (via committed `docs/api/internal.rst`)
- [x] #11 docs(apidocs): link `vendor_fabric.secrets_sync._binding.rst` into toctree
- [x] #12 docs(apidocs): link `vendor_fabric.secrets_sync.__main__.rst` into toctree
- [x] #13 docs(ownership): add ownership-map rows for `vendor_data`, `capabilities`, `surface`, `cloud_params`, `_optional`
- [x] #14 docs(testing): expand `testing.rst` to cover all 7 plugin fixtures + `--e2e`/markers

### Phase 4 — Test gap closures (high-priority)
- [x] #15 test(registry): add `tests/test_registry.py` (76 tests)
- [x] #16 test(surface): add `tests/test_surface.py` (23 tests)
- [x] #17 test(persistence): add `tests/meshy/test_persistence_utils.py` (14 tests)

### Phase 5 — Repo file + polish
- [x] #18 docs(repo): write `AGENTS.md`
- [x] #19 chore(meshy): narrow `webhooks/handler.py:185` exception catch; add debug log to `jobs.py:141`
- [x] #20 build(extras): verified `vector` extra (consumed by `vector_store.py`); verified `webhooks` extra (convenience bundle, not imported by package code) — no changes needed

### Deferred (low priority — logged in ASSESSMENT.md, no commits in this pass)
- More targeted tests for 21 under-named secrets-sync model classes
- E2E tests for non-meshy connectors + binding facade
- (Confirmed intentional) 6/10 connectors bypass `@capability` facade dispatch