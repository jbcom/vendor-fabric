"""Tests for SecretSync store adapters and dependency graphs."""

from __future__ import annotations

import json

from unittest.mock import MagicMock

import pytest

from vendor_fabric.secrets_sync import SecretSyncConfig
from vendor_fabric.secrets_sync.graph import Graph
from vendor_fabric.secrets_sync.stores import (
    AWSSecretsManagerStore,
    InMemorySecretStore,
    S3SecretStore,
    VaultSecretStore,
    join_secret_path,
    normalize_secret_payload,
    relative_secret_path,
)


def test_secret_path_helpers_normalize_slashes_and_payloads() -> None:
    """Store helpers should normalize paths and scalar connector values."""
    assert join_secret_path("/base/", "", "db/") == "base/db"
    assert relative_secret_path("base/db/password", "base") == "db/password"
    assert relative_secret_path("base", "base") == ""
    assert relative_secret_path("other/db", "base") == "other/db"
    assert normalize_secret_payload(None) == {}
    assert normalize_secret_payload("raw") == {"value": "raw"}
    assert normalize_secret_payload({"port": 5432}) == {"port": 5432}


def test_in_memory_store_filters_roots_and_tracks_write_summary() -> None:
    """InMemorySecretStore should report added, modified, and unchanged writes."""
    store = InMemorySecretStore({"app/db": {"host": "db"}, "other/cache": {"host": "cache"}})

    assert store.read_tree("app") == {"db": {"host": "db"}}

    summary = store.write_tree(
        {
            "db": {"host": "db"},
            "api": {"host": "api"},
        },
        root="app",
    )

    assert summary.processed == 2
    assert summary.unchanged == 1
    assert summary.added == 1
    assert store.read_tree("app") == {"db": {"host": "db"}, "api": {"host": "api"}}

    dry_run = store.write_tree({"db": {"host": "new"}}, root="app", dry_run=True)
    assert dry_run.modified == 1
    assert store.read_tree("app")["db"] == {"host": "db"}


def test_vault_secret_store_reads_and_writes_relative_paths() -> None:
    """VaultSecretStore should call the connector with normalized paths."""
    connector = MagicMock()
    connector.list_secrets.return_value = {
        "app/db": {"password": "old"},
    }
    store = VaultSecretStore(connector, mount="kv")

    assert store.read_tree("app") == {"db": {"password": "old"}}

    summary = store.write_tree(
        {
            "db": {"password": "old"},
            "api": {"password": "new"},
        },
        root="app",
    )

    assert summary.processed == 2
    assert summary.unchanged == 1
    assert summary.added == 1
    connector.write_secret.assert_called_once_with(path="app/api", data={"password": "new"}, mount_point="kv")


def test_aws_secrets_manager_store_decodes_and_writes_json_values() -> None:
    """AWSSecretsManagerStore should decode JSON strings and create/update changes."""
    connector = MagicMock()
    connector.list_secrets.return_value = {
        "prod/db": '{"password":"old"}',
        "prod/raw": "plain",
    }
    store = AWSSecretsManagerStore(
        connector,
        prefix="prod",
        execution_role_arn="arn:aws:iam::123456789012:role/Sync",
        role_session_name="test-session",
    )

    assert store.read_tree() == {"db": {"password": "old"}, "raw": {"value": "plain"}}

    summary = store.write_tree({"db": {"password": "new"}, "api": {"password": "created"}})

    assert summary.processed == 2
    assert summary.modified == 1
    assert summary.added == 1
    connector.update_secret.assert_called_once()
    assert connector.update_secret.call_args.kwargs["secret_id"] == "prod/db"
    assert json.loads(connector.update_secret.call_args.kwargs["secret_value"]) == {"password": "new"}
    connector.create_secret.assert_called_once()
    assert connector.create_secret.call_args.kwargs["name"] == "prod/api"


def test_aws_secrets_manager_store_dry_run_avoids_writes() -> None:
    """AWSSecretsManagerStore dry-runs should classify changes without writes."""
    connector = MagicMock()
    connector.list_secrets.return_value = {"prod/db": '{"password":"old"}'}
    store = AWSSecretsManagerStore(connector, prefix="prod")

    summary = store.write_tree({"db": {"password": "new"}, "api": {"password": "created"}}, dry_run=True)

    assert summary.modified == 1
    assert summary.added == 1
    connector.update_secret.assert_not_called()
    connector.create_secret.assert_not_called()


def test_s3_secret_store_reads_mapping_and_writes_bundle() -> None:
    """S3SecretStore should read and write one JSON bundle object."""
    connector = MagicMock()
    connector.get_json_object.return_value = {"db": {"password": "old"}}
    store = S3SecretStore(
        connector,
        bucket="bucket",
        prefix="bundles",
        execution_role_arn="arn:aws:iam::123456789012:role/Sync",
    )

    assert store.read_tree("prod") == {"db": {"password": "old"}}

    summary = store.write_tree({"db": {"password": "old"}, "api": {"password": "new"}}, root="prod")

    assert summary.processed == 2
    assert summary.unchanged == 1
    assert summary.added == 1
    connector.put_json_object.assert_called_once_with(
        bucket="bucket",
        key="bundles/prod.json",
        data={"db": {"password": "old"}, "api": {"password": "new"}},
        execution_role_arn="arn:aws:iam::123456789012:role/Sync",
    )


def test_s3_secret_store_ignores_non_mapping_payloads_and_supports_dry_run() -> None:
    """S3SecretStore should treat non-mapping bundle payloads as empty."""
    connector = MagicMock()
    connector.get_json_object.return_value = ["not", "a", "mapping"]
    store = S3SecretStore(connector, bucket="bucket")

    assert store.read_tree("prod") == {}

    summary = store.write_tree({"db": {"password": "new"}}, root="prod", dry_run=True)

    assert summary.added == 1
    connector.put_json_object.assert_not_called()


def test_graph_orders_targets_and_includes_target_dependencies() -> None:
    """Graph should topologically order targets and expand target dependencies."""
    config = SecretSyncConfig.from_mapping(
        {
            "sources": {"base": {"vault": {"mount": "base"}}},
            "targets": {
                "shared": {"imports": ["base"]},
                "prod": {"imports": ["shared"]},
                "dev": {"imports": ["base"]},
            },
        }
    )

    graph = Graph.from_config(config)

    assert graph.topological_order() == ["dev", "shared", "prod"]
    assert graph.include_dependencies(["prod"]) == ["shared", "prod"]
    assert graph.group_by_level() == [[], ["dev", "shared"], ["prod"]]
    rendered = graph.render()
    assert "Dependency Graph:" in rendered
    assert "prod <- ['shared']" in rendered


def test_graph_rejects_unknown_imports_and_cycles() -> None:
    """Graph should reject missing dependencies and circular target chains."""
    unknown = SecretSyncConfig.from_mapping({"targets": {"prod": {"imports": ["missing"]}}})
    unknown.sources.pop("missing")
    with pytest.raises(ValueError, match='target "prod" imports unknown'):
        Graph.from_config(unknown)

    cyclic = SecretSyncConfig.from_mapping({"targets": {"a": {"imports": ["b"]}, "b": {"imports": ["a"]}}})
    with pytest.raises(ValueError, match="circular dependency"):
        Graph.from_config(cyclic)
