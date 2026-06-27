"""Tests for native vendor-fabric SecretSync pipelines."""

from __future__ import annotations

from pathlib import Path

from extended_data.containers import ExtendedData, ExtendedDict

from vendor_fabric.secrets_sync import (
    InMemorySecretStore,
    SecretSyncConfig,
    SecretSyncPipeline,
    StoreRegistry,
    SyncOperation,
    SyncOptions,
    sync_mapping_to_file,
)


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
