"""Native Python secret and file sync capabilities for vendor-fabric."""

from __future__ import annotations


try:
    from importlib.metadata import version
except ImportError:  # pragma: no cover
    version = None  # type: ignore[assignment]

from vendor_fabric.secrets_sync.files import FileSyncResult, LocalFileStore, S3FileStore, sync_mapping_to_file
from vendor_fabric.secrets_sync.models import (
    ConfigInfo,
    OutputFormat,
    SecretSyncConfig,
    SyncOperation,
    SyncOptions,
    SyncResult,
)
from vendor_fabric.secrets_sync.pipeline import (
    SecretSyncPipeline,
    dry_run,
    get_config_info,
    merge,
    run_pipeline,
    sync,
    validate_config,
)
from vendor_fabric.secrets_sync.stores import (
    AWSSecretsManagerStore,
    InMemorySecretStore,
    S3SecretStore,
    StoreRegistry,
    VaultSecretStore,
)


if version is None:  # pragma: no cover
    __version__ = "0.0.0"
else:
    try:
        __version__ = version("vendor-fabric")
    except Exception:  # pragma: no cover
        __version__ = "0.0.0"


__all__ = [
    "AWSSecretsManagerStore",
    "ConfigInfo",
    "FileSyncResult",
    "InMemorySecretStore",
    "LocalFileStore",
    "OutputFormat",
    "S3FileStore",
    "S3SecretStore",
    "SecretSyncConfig",
    "SecretSyncPipeline",
    "StoreRegistry",
    "SyncOperation",
    "SyncOptions",
    "SyncResult",
    "VaultSecretStore",
    "__version__",
    "dry_run",
    "get_config_info",
    "merge",
    "run_pipeline",
    "sync",
    "sync_mapping_to_file",
    "validate_config",
]
