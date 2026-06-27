"""Tests for transitional SecretSync Python helpers and binding delegation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedData, ExtendedDict

from vendor_fabric.secrets_sync import (
    InMemorySecretStore,
    OutputFormat,
    SecretSyncConfig,
    SecretSyncPipeline,
    StoreRegistry,
    SyncOperation,
    SyncOptions,
    get_config_info,
    merge,
    run_pipeline,
    sync,
    sync_mapping_to_file,
    validate_config,
)
from vendor_fabric.secrets_sync.models import TargetDiff
from vendor_fabric.secrets_sync.pipeline import format_diff


def test_native_pipeline_merges_sources_and_syncs_target_store() -> None:
    config = SecretSyncConfig.from_mapping(
        {
            "sources": {
                "base": {"vault": {"mount": "base"}},
                "env": {"vault": {"mount": "env"}},
            },
            "targets": {
                "prod": {
                    "account_id": "123456789012",
                    "imports": ["base", "env"],
                    "secret_prefix": "app/prod",
                }
            },
        }
    )
    target_store = InMemorySecretStore()
    pipeline = SecretSyncPipeline(
        config,
        stores=StoreRegistry(
            sources={
                "base": InMemorySecretStore({"base/db": {"host": "db", "ports": [5432]}}),
                "env": InMemorySecretStore({"env/db": {"password": "raw", "ports": [6432]}}),
            },
            targets={"prod": target_store},
            merge_store=InMemorySecretStore(),
        ),
    )

    result = pipeline.run(SyncOptions(dry_run=False))

    assert result.success is True
    assert result.target_count == 1
    assert result.secrets_processed == 2
    assert target_store.read_tree("app/prod") == {
        "db": {"host": "db", "password": "raw", "ports": [5432, 6432]},
    }


def test_native_pipeline_dry_run_does_not_write_target_store() -> None:
    config = SecretSyncConfig.from_mapping(
        {
            "sources": {"base": {"vault": {"mount": "base"}}},
            "targets": {"prod": {"account_id": "123456789012", "imports": ["base"]}},
        }
    )
    target_store = InMemorySecretStore()
    pipeline = SecretSyncPipeline(
        config,
        stores=StoreRegistry(
            sources={"base": InMemorySecretStore({"base/db": {"password": "raw"}})},
            targets={"prod": target_store},
            merge_store=InMemorySecretStore(),
        ),
    )

    result = pipeline.run(SyncOptions(dry_run=True, compute_diff=True))

    assert result.success is True
    assert result.diff_output
    assert target_store.read_tree() == {}


def test_pipeline_result_can_be_wrapped_as_extended_data() -> None:
    config = SecretSyncConfig.from_mapping(
        {
            "sources": {"base": {"vault": {"mount": "base"}}},
            "targets": {"prod": {"account_id": "123456789012", "imports": ["base"]}},
        }
    )
    pipeline = SecretSyncPipeline(
        config,
        stores=StoreRegistry(
            sources={"base": InMemorySecretStore({"base/db": {"password": "raw"}})},
            targets={"prod": InMemorySecretStore()},
            merge_store=InMemorySecretStore(),
        ),
    )

    result = pipeline.run_extended(SyncOptions(operation=SyncOperation.MERGE))

    assert isinstance(result, ExtendedData)
    assert result["success"] is True


def test_sync_mapping_to_file_uses_extended_data_sync_primitive(tmp_path: Path) -> None:
    result = sync_mapping_to_file({"service": "api"}, tmp_path / "payload.json")

    assert isinstance(result, ExtendedDict)
    assert result["changed"] is True
    assert (tmp_path / "payload.json").exists()


def test_module_wrappers_delegate_to_binding_adapter(tmp_path: Path) -> None:
    """Module-level wrappers should delegate execution to the SecretSync binding adapter."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("targets:\n  prod:\n    imports: []\n", encoding="utf-8")

    with (
        patch("vendor_fabric.secrets_sync.pipeline._binding.run_pipeline", return_value={"success": True}) as binding_run,
        patch("vendor_fabric.secrets_sync.pipeline._binding.merge", return_value={"success": True}) as binding_merge,
        patch("vendor_fabric.secrets_sync.pipeline._binding.sync", return_value={"success": True}) as binding_sync,
    ):
        assert run_pipeline(str(config_path)) == {"success": True}
        dry_merge = merge(str(config_path), dry_run=True)
        dry_sync = sync(str(config_path), dry_run=True)

    assert dry_merge == {"success": True}
    assert dry_sync == {"success": True}
    binding_run.assert_called_once_with(str(config_path), None)
    binding_merge.assert_called_once_with(str(config_path), dry_run=True)
    binding_sync.assert_called_once_with(str(config_path), dry_run=True)


def test_validate_and_info_wrappers_report_failures(tmp_path: Path) -> None:
    """Validation and info helpers should return redacted failure payloads."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- not\n- mapping\n", encoding="utf-8")

    with (
        patch(
            "vendor_fabric.secrets_sync.pipeline._binding.validate_config",
            return_value={"valid": False, "message": "SecretSync config must be a mapping"},
        ),
        patch(
            "vendor_fabric.secrets_sync.pipeline._binding.get_config_info",
            return_value={"valid": False, "error_message": "SecretSync config must be a mapping"},
        ),
    ):
        validation = validate_config(str(config_path))
        info = get_config_info(str(config_path))

    assert validation["valid"] is False
    assert "must be a mapping" in validation["message"]
    assert info["valid"] is False
    assert "must be a mapping" in info["error_message"]


def test_pipeline_run_records_errors_when_continue_on_error() -> None:
    """Pipeline execution should aggregate redacted errors when continuing."""
    pipeline = SecretSyncPipeline(SecretSyncConfig.from_mapping({"targets": {"prod": {"imports": []}}}))
    with patch.object(pipeline, "merge_target", side_effect=RuntimeError("password=hunter2 Authorization: Bearer raw")):
        result = pipeline.run(SyncOptions(operation=SyncOperation.MERGE, continue_on_error=True))

    assert result.success is True
    assert "hunter2" not in result.error_message
    assert "[REDACTED]" in result.error_message


def test_pipeline_run_reraises_when_continue_on_error_is_false() -> None:
    """Pipeline execution should re-raise operation errors when requested."""
    pipeline = SecretSyncPipeline(SecretSyncConfig.from_mapping({"targets": {"prod": {"imports": []}}}))
    with patch.object(pipeline, "merge_target", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            pipeline.run(SyncOptions(operation=SyncOperation.MERGE, continue_on_error=False))


def test_pipeline_validate_config_failure_and_target_resolution() -> None:
    """Pipeline instance helpers should expose validation and target dependency behavior."""
    config = SecretSyncConfig.from_mapping(
        {
            "sources": {"base": {"vault": {"mount": "base"}}},
            "targets": {
                "shared": {"imports": ["base"]},
                "prod": {"imports": ["shared"]},
            },
        }
    )
    pipeline = SecretSyncPipeline(config)
    config.targets["prod"].account_id = "bad"

    assert pipeline.validate_config()["valid"] is False
    assert pipeline.config_info().target_count == 2
    assert pipeline.resolve_targets(["prod"]) == ["shared", "prod"]


def test_pipeline_private_store_selection_branches() -> None:
    """Pipeline should select injected and configured stores before defaults."""
    source_store = MagicMock()
    target_store = MagicMock()
    merge_store = MagicMock()
    pipeline = SecretSyncPipeline(
        SecretSyncConfig.from_mapping(
            {
                "sources": {"base": {"vault": {"mount": "base"}}},
                "targets": {"prod": {"imports": ["base"]}},
            }
        ),
        stores=StoreRegistry(sources={"base": source_store}, targets={"prod": target_store}, merge_store=merge_store),
    )

    assert pipeline._source_store("base", pipeline.config.sources["base"]) is source_store
    assert pipeline._target_store("prod", pipeline.config.targets["prod"]) is target_store
    assert pipeline._merge_store() is merge_store
    with pytest.raises(ValueError, match="target not found"):
        pipeline.bundle_path_for_target("missing")


def test_format_diff_human_output() -> None:
    """Human diff output should include populated sections only."""
    rendered = format_diff(
        [
            TargetDiff(
                target="prod",
                phase="sync",
                added=["db"],
                modified=["api"],
                removed=["old"],
                unchanged=["cache"],
            )
        ],
        output_format=OutputFormat.HUMAN,
    )

    assert "sync:prod" in rendered
    assert "added: db" in rendered
    assert "modified: api" in rendered
    assert "removed: old" in rendered
    assert "unchanged: cache" in rendered
