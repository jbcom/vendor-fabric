"""Tests for SecretSync merge and file-store helpers."""

from __future__ import annotations

import json

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vendor_fabric.secrets_sync.deepmerge import compare_secret_json, deep_equal, deep_merge, normalize_for_compare
from vendor_fabric.secrets_sync.files import FileSyncResult, LocalFileStore, S3FileStore


def test_deep_merge_accepts_missing_inputs() -> None:
    """Secret payload merging should tolerate absent sides."""
    assert deep_merge(None, {"db": {"password": "secret"}}) == {"db": {"password": "secret"}}
    assert deep_merge({"db": {"host": "localhost"}}, None) == {"db": {"host": "localhost"}}


def test_compare_secret_json_normalizes_numbers_tuples_and_bytes() -> None:
    """JSON secret comparisons should normalize data before equality checks."""
    left = b'{"replicas": 1, "ports": [5432], "labels": {"env": "prod"}}'
    right = '{"replicas": 1.0, "ports": [5432.0], "labels": {"env": "prod"}}'

    assert compare_secret_json(left, right) is True
    assert normalize_for_compare(("a", 1, True)) == ["a", 1.0, True]
    assert deep_equal({"items": (1, 2)}, {"items": [1.0, 2.0]}) is True


def test_compare_secret_json_falls_back_to_raw_text() -> None:
    """Non-JSON secret comparisons should use raw string equality."""
    assert compare_secret_json("raw-secret", "raw-secret") is True
    assert compare_secret_json("raw-secret", "other-secret") is False


def test_file_sync_result_redacts_source_and_destination() -> None:
    """File sync result payloads should not echo full secret-bearing paths."""
    result = FileSyncResult(
        source="s3://bucket/password=hunter2",
        destination="/tmp/token=raw",
        changed=True,
        error_message="already redacted by caller",
    ).to_dict()

    assert "hunter2" not in result["source"]
    assert "token=raw" not in result["destination"]
    assert result["changed"] is True


def test_local_file_store_writes_and_reads_json(tmp_path: Path) -> None:
    """LocalFileStore should round-trip files through Extended Data IO."""
    path = tmp_path / "payload.json"
    store = LocalFileStore()

    write_result = store.write(path, {"service": "api"}, encoding="json")
    data_file = store.read(path)

    assert write_result.changed is True
    assert write_result.bytes_written == len(path.read_text(encoding="utf-8"))
    assert json.loads(path.read_text(encoding="utf-8")) == {"service": "api"}
    assert data_file.data == {"service": "api"}


def test_local_file_store_dry_run_does_not_write(tmp_path: Path) -> None:
    """LocalFileStore dry-run writes should report bytes without touching disk."""
    path = tmp_path / "payload.json"
    result = LocalFileStore().write(path, {"service": "api"}, encoding="json", dry_run=True)

    assert result.dry_run is True
    assert result.changed is True
    assert result.bytes_written > 0
    assert not path.exists()


def test_s3_file_store_reads_bytes_and_handles_missing_objects() -> None:
    """S3FileStore should decode object bytes and raise for missing keys."""
    connector = MagicMock()
    connector.get_object.return_value = b'{"service": "api"}'
    store = S3FileStore(connector)

    data_file = store.read("bucket", "path/payload.json")

    assert data_file.data == {"service": "api"}
    connector.get_object.assert_called_once_with(
        bucket="bucket",
        key="path/payload.json",
        decode=False,
        execution_role_arn=None,
    )

    connector.get_object.return_value = None
    with pytest.raises(FileNotFoundError, match=r"s3://bucket/missing\.json"):
        store.read("bucket", "missing.json")


def test_s3_file_store_writes_and_supports_dry_run() -> None:
    """S3FileStore writes should render payloads and honor dry-run."""
    connector = MagicMock()
    store = S3FileStore(connector, execution_role_arn="arn:aws:iam::123456789012:role/Sync")

    dry_run = store.write("bucket", "payload.json", {"service": "api"}, encoding="json", dry_run=True)
    actual = store.write("bucket", "payload.json", {"service": "api"}, encoding="json")

    assert dry_run.dry_run is True
    assert dry_run.destination == "s3://bucket/payload.json"
    connector.put_object.assert_called_once()
    assert connector.put_object.call_args.kwargs["bucket"] == "bucket"
    assert connector.put_object.call_args.kwargs["key"] == "payload.json"
    assert json.loads(connector.put_object.call_args.kwargs["body"]) == {"service": "api"}
    assert connector.put_object.call_args.kwargs["execution_role_arn"] == "arn:aws:iam::123456789012:role/Sync"
    assert actual.bytes_written > 0
