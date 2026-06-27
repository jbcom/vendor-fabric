"""File syncing capabilities built on Extended Data file workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extended_data.containers import ExtendedDict, extend_data
from extended_data.io import DataFile, wrap_raw_data_for_export
from extended_data.primitives.redaction import redact_sensitive_text
from extended_data.workflows import sync_value_to_file

from vendor_fabric.aws import AWSConnector


@dataclass(slots=True)
class FileSyncResult:
    """File sync operation result."""

    source: str
    destination: str
    changed: bool
    dry_run: bool = False
    bytes_written: int = 0
    error_message: str = ""

    def to_dict(self) -> ExtendedDict:
        """Return an Extended Data payload."""
        return extend_data(
            {
                "source": redact_sensitive_text(self.source, values=[self.source]),
                "destination": redact_sensitive_text(self.destination, values=[self.destination]),
                "changed": self.changed,
                "dry_run": self.dry_run,
                "bytes_written": self.bytes_written,
                "error_message": self.error_message,
            }
        )


class LocalFileStore:
    """Local file store using Extended Data decoding and export."""

    def read(self, path: str | Path, *, suffix: str | None = None) -> DataFile:
        """Read a local file."""
        return DataFile.read(str(path), suffix=suffix)

    def write(
        self,
        path: str | Path,
        data: Any,
        *,
        encoding: str | None = None,
        dry_run: bool = False,
    ) -> FileSyncResult:
        """Write a local file."""
        rendered = wrap_raw_data_for_export(data, allow_encoding=encoding or True)
        if dry_run:
            return FileSyncResult(source="memory", destination=str(path), changed=True, dry_run=True, bytes_written=len(rendered))
        Path(path).write_text(rendered, encoding="utf-8")
        return FileSyncResult(source="memory", destination=str(path), changed=True, bytes_written=len(rendered))


class S3FileStore:
    """S3 file store using the AWS connector."""

    def __init__(self, connector: AWSConnector | None = None, *, execution_role_arn: str | None = None) -> None:
        self.connector = connector or AWSConnector(execution_role_arn=execution_role_arn)
        self.execution_role_arn = execution_role_arn

    def read(self, bucket: str, key: str, *, suffix: str | None = None) -> DataFile:
        """Read an object from S3 into a DataFile."""
        data = self.connector.get_object(bucket=bucket, key=key, decode=False, execution_role_arn=self.execution_role_arn)
        if data is None:
            msg = f"S3 object not found: s3://{bucket}/{key}"
            raise FileNotFoundError(msg)
        return DataFile.decode(str(data) if not isinstance(data, bytes) else data, file_path=f"s3://{bucket}/{key}", suffix=suffix)

    def write(
        self,
        bucket: str,
        key: str,
        data: Any,
        *,
        encoding: str | None = None,
        dry_run: bool = False,
    ) -> FileSyncResult:
        """Write data to S3."""
        rendered = wrap_raw_data_for_export(data, allow_encoding=encoding or True)
        destination = f"s3://{bucket}/{key}"
        if dry_run:
            return FileSyncResult(source="memory", destination=destination, changed=True, dry_run=True, bytes_written=len(rendered))
        self.connector.put_object(
            bucket=bucket,
            key=key,
            body=rendered,
            execution_role_arn=self.execution_role_arn,
        )
        return FileSyncResult(source="memory", destination=destination, changed=True, bytes_written=len(rendered))


def sync_mapping_to_file(
    data: Mapping[str, Any],
    destination: str | Path,
    *,
    encoding: str | None = "json",
    dry_run: bool = False,
) -> ExtendedDict:
    """Sync a mapping to a local file through Extended Data export rules."""
    return sync_value_to_file(data, destination, encoding=encoding, dry_run=dry_run).to_dict()
