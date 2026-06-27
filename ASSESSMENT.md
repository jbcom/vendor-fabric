# vendor-fabric Completeness Assessment

Audited: source (`packages/vendor-fabric/src/`, 71 modules), tests (60+ test files),
docs (`docs/`), `pytest-vendor-fabric`, examples, CLI, and pyproject extras/entry-points.

## TL;DR

- **Source code: no stubs, no TODOs, no NotImplementedErrors, no partial implementations.**
  The single-reviewer-flagged items are two broad exception catches in meshy, not feature gaps.
- **The real gaps are in documentation (12 issues), tests (15 untested-symbol clusters),
  and examples (1 broken).** Plus 1 missing repo file (AGENTS.md).
- CLI, entry-points, registry specs, public API exports — all consistent and complete.

---

## A. Code completeness — CLEAN

Exhaustive scan across 18 categories (TODO/FIXME, NotImplementedError, `pass`/`...`
bodies, placeholders, pragma-no-cover, type-ignore, noqa, empty modules, dangling
abstract methods, `__getattr__`, silent ImportError degradation, "coming soon"
docstrings, empty-collection placeholder returns, RuntimeError-as-unsupported,
commented-out code).

**No stubs or partial features found.** Every `pass` is a TYPE_CHECKING block; every
`...` is a mixin type-stub; every Optional/empty return is a legitimate 404/not-found
path; every `try/except ImportError` re-raises with install guidance or sets an
explicit feature flag (`_HAS_VECTOR`, `is_binding_available`, `is_available`).
Abstract methods in `ConnectorAdapter` are implemented by both subclasses.

### Two review-grade (non-blocking) finds
1. `meshy/webhooks/handler.py:185-186` — `except Exception: return None` in
   `_download_glb_artifact` swallows all errors incl. programming errors.
   Narrow to `(httpx.HTTPError, OSError)`.
2. `meshy/jobs.py:141` — `except Exception: # noqa: S112` batch-continue.
   Intentional; add a debug log for the swallowed error.

---

## B. Test coverage gaps

The `tox -e providers` gate enforces ≥90% line coverage and passes, but line coverage
masks **symbol/reference gaps** — many symbols are exercised only structurally (via
parsing or incidental paths), never named in tests. Highest-risk clusters:

### B1. No dedicated test file (covered only incidentally)
| Module | Risk |
|---|---|
| `vendor_fabric/registry.py` | No `test_registry.py`. 15 internal helpers (`_normalize_*`, `_discover_connectors`, `_raise_*`, `_get_*`, `_class_connector_info`, `_builtin_connector_info`, `_missing_builtin_connector_info`) + `BuiltinConnectorSpec`/`ConnectorInfo`/adapter classes have 0 direct refs. Public API covered via connector tests, dispatch machinery is not. |
| `vendor_fabric/surface.py` | No `test_surface.py`. `return_annotation`, `annotation_includes_extended_payload` 0 refs. |
| `vendor_fabric/meshy/persistence/utils.py` | `canonicalize_spec` 0 refs anywhere; only `compute_spec_hash` exercised. |
| `vendor_fabric/meshy/{text3d,image3d,animate,rigging,retexture}.py` | All 5 covered only by `tests/meshy/test_task_ids.py`. Consolidated, not decomposed. |

### B2. Untested public symbols (never named in any test)
- `vendor_fabric.secrets_sync/models.py` — 21 of ~35 model classes (`VaultAuthAppRole`,
  `VaultAuthToken`, `VaultAuthKubernetes`, `ExecutionRoleConfig`, `ControlTowerConfig`,
  `MergeStoreVault`, `MergeStoreS3`, `AccountNamePattern`, `MergeSettings`,
  `SyncSettings`, `PipelineSettings`, `ResultDetails`, `OperationResult`, …). Parsed
  structurally via `SecretSyncConfig.from_file`; a renamed field/class wouldn't break a test.
- `vendor_fabric.secrets_sync/graph.py` — `NodeType`, `Node` 0 refs (only `Graph`).
- `vendor_fabric.secrets_sync/stores.py` — `WriteSummary`, `SecretTreeStore` (Protocol),
  `_decode_secret_payload` 0 refs.
- `vendor_fabric.secrets_sync/pipeline.py` — `diff_trees` 0 refs (only `format_diff`).
- `vendor_fabric.secrets_sync/_binding.py` — ~10 private conversion helpers 0 direct refs.
- `vendor_fabric/secrets_sync/cli.py` — `cmd_validate`, `cmd_info`, `cmd_pipeline`,
  `build_parser`, `_write_stdout`, `_write_stderr` 0 direct refs (only `main` named).

### B3. All Pydantic `*Schema` classes (every `tools.py`) — never directly tested
Across aws, google, github, slack, zoom, vault, cursor, anthropic, meshy, secrets_sync.
Exercise happens only implicitly via tool-function calls. Field renames / dropped
validators slip through unless a tool test happens to hit that field.

### B4. Private redaction/diagnostic helpers
Per provider, only `_iter_diagnostic_values` + one `safe_*` variant is directly tested.
Untested: `safe_aws_text`, `safe_aws_ref`, `safe_google_text`, `safe_github_ref`,
`_safe_zoom_text`, `_safe_log_text`, `_safe_ref_text`, `_slack_response_payload`,
`_load_aws_sdk`, `_load_google_sdk`, `_load_slack_sdk`, `_load_hvac`.

### B5. Misc 0-ref symbols
- `AnthropicRateLimitError`, `CursorConnector.LaunchOptions`,
  `vendor_data._index_capabilities`/`_coerce_support_spec`/`_public_method_supports`.
- `cli.py` private helpers (`_json_output`, `_parse_arg_value`, `_format_list`,
  `_write_stdout`, `_write_stderr`, `_filter_connector_info`).
- `connectors.py` `_is_sensitive_cache_field`, `_cache_safe_value` (redaction path).
- `pytest-vendor-fabric/plugin.py` `pytest_addoption`, `pytest_configure` — likely
  import-only refs, not behavior assertions.

### B6. E2E suite
`tests/e2e/meshy/test_meshy_provider.py` is the sole E2E file — opt-in via `--e2e`.
No E2E tests exist for aws, google, github, slack, vault, zoom, anthropic, cursor,
or the secrets-sync binding facade. The CLI is unit-tested but not exercised end-to-end.

---

## C. Documentation issues (12)

### Critical ( fabricated/stale APIs the reader will hit AttributeError on)
1. **`architecture.rst:69` — `data.sync_secret("vault", "aws", name="prod/api")`** is
   fabricated. No `sync_secret` method or capability exists anywhere in source.
2. **`architecture.rst:68` — `data.get_file("github", owner=..., repo=..., path=...)`** is
   fabricated. `GitHubConnector.get_repository_file(file_path)` takes a single path; owner/repo
   are constructor args. Same for the `s3://bucket/key.json` URI form — `get_object(bucket, key)`
   doesn't parse URIs.
3. **`architecture.rst:30-69` — `VendorData` code block is out of date.** Omits
   `capabilities`/`**fabric_kwargs` params; uses `self.logger`/`self.active_provider`
   instead of `self.logging`/`self._active_provider`; omits fabric fallback and all
   capability-index state.

### Wrong identifiers / direct contradictions
4. **`architecture.rst` claims `__dir__` exists on VendorData** — it does not.
5. **`architecture.rst` forbids `__SUPPORTS__`-style dunders while `vendor_data.py`
   implements and reads `__supports__`** — direct self-contradiction.
6. **`architecture.rst` names the capability attribute `_capability_spec`**; code uses
   `_vendor_capabilities`.
7. **`architecture.rst:79` claims `typing.Protocol` for provider contracts** — no such
   Protocol exists for provider contracts (only `SecretTreeStore(Protocol)` in stores.py,
   unrelated).
8. **`connectors.rst:26` — `SlackConnector(slack_bot_token="...")`** — wrong kwarg.
   Actual: `bot_token=`.

### Orphaned apidocs (RST generated but unreachable from navigation toctree)
9. `vendor_fabric._optional` — central infra (every connector's `require_extra`); RST
   exists, not in `vendor_fabric.rst` Submodules toctree.
10. `vendor_fabric.secrets_sync._binding` — the entire binding facade (350 lines); RST
    exists, not in `secrets_sync.rst` Submodules toctree.
11. `vendor_fabric.secrets_sync.__main__` — minor (3-line entry shim) but RST orphaned.

### Ownership-map omissions
12. `ownership-map.rst` omits 5 real modules: `vendor_data`, `capabilities`, `surface`,
    `cloud_params`, `_optional`.

### testing.rst understates the plugin
`testing.rst` documents 2 of 7 plugin fixtures (`base_connector_kwargs`, `check_api_key`).
Missing: `mock_logger`, `skip_without_anthropic`, `check_aws_credentials`,
`anthropic_api_key`, `pytest_collection_modifyitems` behavior. `architecture.rst`
overstates with "mocked provider responses / registry assertions" which the plugin
doesn't ship.

### apidocs completeness
Every `.py` module has a generated `.rst` — no missing API docs at the file level. The
gaps are toctree linkage (items C9-C11), not generation.

---

## D. CLI, entry-points, extras — CONSISTENT

- **CLI commands:** all 4 `vendor-fabric` subcommands (`list`, `methods`, `info`, `call`)
  and all 3 `vendor-fabric-secrets-sync` subcommands (`validate`, `info`, `pipeline`)
  have complete handlers, no stubs, no unwired parsers.
- **Entry-points:** 2 scripts + 10 connector entry-points all resolve to existing symbols.
- **Extras:** all referenced extras exist in `pyproject.toml`. Two verification asks:
  - `vector` extra (`sqlite-vec`) — confirm the consuming code path or remove the dep.
  - `meshy/webhooks/` ↔ `webhooks` extra — verify meshy webhooks don't import
    fastapi/starlette without the `webhooks` extra installed (undeclared cross-extra dep).

### Capability matrix observation (not a bug)
6 of 10 connectors (google, slack, zoom, anthropic, cursor, meshy) declare catalog
capabilities but have **zero `@capability`-decorated methods** — they're invisible to the
`@capability` facade dispatch path. By design (catalog = discovery metadata; `@capability`
= facade routing), but worth confirming the intent is "the generic
`ConnectorFabric.get_connector(name, **kw)` path is the only way in for those six."

---

## E. Examples — 1 BROKEN

| File | Status |
|---|---|
| `basic_aws.py` | ✅ Works — calls `list_s3_buckets()` and `get_accounts()`. |
| `basic_google.py` | ✅ Works — calls `list_projects()` and `list_users()`. |
| `basic_meshy.py` | ❌ Broken — passes `mode="preview"` to `text3d.generate` (no such param; signature is `generate(prompt, *, art_style, negative_prompt, target_polycount, enable_pbr, wait)`), uses `result.id`/`.status`/`.task_error` attribute access on an `ExtendedDict` return, and calls nonexistent `text3d.get`. Stale vs. the current functional API. Needs full rewrite. |

No example filename is referenced from docs, so the breakage doesn't affect the docs build.

---

## F. Missing repo file

- **`AGENTS.md`** — required by CLAUDE.md (standard-repo profile) for extended operating
  protocols/architecture/patterns. Confirmed absent.

---

## G. Prioritized remediation list

| # | Severity | Item |
|---|---|---|
| 1 | Critical | Fix `architecture.rst` fabricated APIs (`sync_secret`, `get_file` kwarg shapes) |
| 2 | Critical | Rewrite `examples/basic_meshy.py` against current `text3d` API |
| 3 | Critical | Update `architecture.rst` `VendorData` code block to match real `__init__` |
| 4 | High | Fix `architecture.rst` `__dir__`/`__SUPPORTS__`/`_capability_spec`/`Protocol` claims |
| 5 | High | Fix `connectors.rst` `SlackConnector(slack_bot_token=…)` → `bot_token=` |
| 6 | High | Add `test_registry.py` covering adapters, spec/info classes, internal helpers |
| 7 | High | Link `_optional.rst` and `secrets_sync/_binding.rst` into apidocs toctrees |
| 8 | High | Write `AGENTS.md` |
| 9 | Med | Add targeted tests for secrets-sync model classes (21 under-named classes) |
| 10 | Med | Add tests for `surface.py` (`return_annotation`, `annotation_includes_extended_payload`) |
| 11 | Med | Add tests for `meshy/persistence/utils.py::canonicalize_spec` |
| 12 | Med | Expand `testing.rst` to cover all 7 plugin fixtures |
| 13 | Med | Add ownership-map rows for `vendor_data`, `capabilities`, `surface`, `cloud_params`, `_optional` |
| 14 | Low | Narrow `meshy/webhooks/handler.py:185` exception catch |
| 15 | Low | Verify `vector` extra and `meshy/webhooks` ↔ `webhooks` extra dependency edges — **verified clean**: `vector` consumed by `vector_store.py` (guarded by `_HAS_VECTOR`); `webhooks` is a convenience bundle for users serving the handler via fastapi/uvicorn/pyngrok, intentionally not imported by package code |
| 16 | Low | Add E2E tests for non-meshy connectors and secrets-sync binding facade |
| 17 | Low | Confirm intent: 6/10 connectors bypass `@capability` facade dispatch — **confirmed intentional**: catalog capabilities are discovery metadata, `@capability` is facade routing; the generic `ConnectorFabric.get_connector(name, **kw)` path covers the 6 |