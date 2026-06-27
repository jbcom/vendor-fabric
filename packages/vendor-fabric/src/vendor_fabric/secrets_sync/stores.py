"""Secret tree stores used by native SecretSync pipelines."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from extended_data.containers import to_builtin
from extended_data.io import wrap_raw_data_for_export

from vendor_fabric.aws import AWSConnector
from vendor_fabric.secrets_sync.deepmerge import compare_secret_json, deep_equal
from vendor_fabric.vault import VaultConnector


SecretPayload = dict[str, Any]
SecretTree = dict[str, SecretPayload]


@dataclass(slots=True)
class WriteSummary:
    """Summary of a store write operation."""

    processed: int = 0
    added: int = 0
    modified: int = 0
    removed: int = 0
    unchanged: int = 0


class SecretTreeStore(Protocol):
    """Read/write interface for tree-shaped secret stores."""

    def read_tree(self, root: str = "") -> SecretTree:
        """Read secrets under a root path keyed by relative secret path."""

    def write_tree(self, secrets: Mapping[str, Mapping[str, Any]], root: str = "", *, dry_run: bool = False) -> WriteSummary:
        """Write a tree of secrets under a root path."""


def join_secret_path(*parts: str) -> str:
    """Join secret path parts without duplicate separators."""
    clean = [part.strip("/") for part in parts if part and part.strip("/")]
    return "/".join(clean)


def relative_secret_path(path: str, root: str) -> str:
    """Return ``path`` relative to ``root``."""
    clean_path = path.strip("/")
    clean_root = root.strip("/")
    if clean_root and clean_path.startswith(f"{clean_root}/"):
        return clean_path[len(clean_root) + 1 :]
    if clean_path == clean_root:
        return ""
    return clean_path


def normalize_secret_payload(value: Any) -> SecretPayload:
    """Return a dict payload from connector values."""
    builtin = to_builtin(value)
    if isinstance(builtin, Mapping):
        return {str(key): item for key, item in builtin.items()}
    if builtin is None:
        return {}
    return {"value": builtin}


class InMemorySecretStore:
    """In-memory secret tree store for dry-runs, tests, and ephemeral merges."""

    def __init__(self, secrets: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.secrets: dict[str, SecretPayload] = {
            key.strip("/"): normalize_secret_payload(value) for key, value in (secrets or {}).items()
        }

    def read_tree(self, root: str = "") -> SecretTree:
        """Read secrets under a root path."""
        clean_root = root.strip("/")
        tree: SecretTree = {}
        for path, payload in self.secrets.items():
            if clean_root and path != clean_root and not path.startswith(f"{clean_root}/"):
                continue
            rel_path = relative_secret_path(path, clean_root)
            if rel_path:
                tree[rel_path] = normalize_secret_payload(payload)
        return tree

    def write_tree(self, secrets: Mapping[str, Mapping[str, Any]], root: str = "", *, dry_run: bool = False) -> WriteSummary:
        """Write secrets under a root path."""
        summary = WriteSummary()
        for rel_path, payload in secrets.items():
            full_path = join_secret_path(root, rel_path)
            normalized = normalize_secret_payload(payload)
            existing = self.secrets.get(full_path)
            summary.processed += 1
            if existing is None:
                summary.added += 1
            elif deep_equal(existing, normalized):
                summary.unchanged += 1
            else:
                summary.modified += 1
            if not dry_run:
                self.secrets[full_path] = normalized
        return summary


class VaultSecretStore:
    """Vault KV2-backed secret tree store."""

    def __init__(self, connector: VaultConnector | None = None, *, mount: str = "secret") -> None:
        self.connector = connector or VaultConnector()
        self.mount = mount

    def read_tree(self, root: str = "") -> SecretTree:
        """Read secrets from Vault under ``root``."""
        secrets = self.connector.list_secrets(root_path=root or "/", mount_point=self.mount)
        tree: SecretTree = {}
        for path, payload in secrets.items():
            rel_path = relative_secret_path(str(path), root)
            if rel_path:
                tree[rel_path] = normalize_secret_payload(payload)
        return tree

    def write_tree(self, secrets: Mapping[str, Mapping[str, Any]], root: str = "", *, dry_run: bool = False) -> WriteSummary:
        """Write secrets to Vault under ``root``."""
        current = self.read_tree(root)
        summary = WriteSummary()
        for rel_path, payload in secrets.items():
            normalized = normalize_secret_payload(payload)
            existing = current.get(rel_path)
            summary.processed += 1
            if existing is None:
                summary.added += 1
            elif deep_equal(existing, normalized):
                summary.unchanged += 1
            else:
                summary.modified += 1
            if not dry_run:
                self.connector.write_secret(path=join_secret_path(root, rel_path), data=normalized, mount_point=self.mount)
        return summary


class AWSSecretsManagerStore:
    """AWS Secrets Manager tree store."""

    def __init__(
        self,
        connector: AWSConnector | None = None,
        *,
        prefix: str = "",
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
    ) -> None:
        self.connector = connector or AWSConnector(execution_role_arn=execution_role_arn)
        self.prefix = prefix.strip("/")
        self.execution_role_arn = execution_role_arn
        self.role_session_name = role_session_name

    def read_tree(self, root: str = "") -> SecretTree:
        """Read secrets under a prefix."""
        prefix = join_secret_path(self.prefix, root)
        secrets = self.connector.list_secrets(
            prefix=prefix or None,
            get_secret_values=True,
            skip_empty_secrets=True,
            execution_role_arn=self.execution_role_arn,
            role_session_name=self.role_session_name,
        )
        tree: SecretTree = {}
        for name, payload in secrets.items():
            rel_path = relative_secret_path(str(name), prefix)
            if rel_path:
                tree[rel_path] = normalize_secret_payload(_decode_secret_payload(payload))
        return tree

    def write_tree(self, secrets: Mapping[str, Mapping[str, Any]], root: str = "", *, dry_run: bool = False) -> WriteSummary:
        """Write JSON secret payloads to AWS Secrets Manager."""
        current = self.read_tree(root)
        summary = WriteSummary()
        for rel_path, payload in secrets.items():
            normalized = normalize_secret_payload(payload)
            secret_name = join_secret_path(self.prefix, root, rel_path)
            secret_value = wrap_raw_data_for_export(normalized, allow_encoding="json")
            existing = current.get(rel_path)
            summary.processed += 1
            if existing is None:
                summary.added += 1
                if not dry_run:
                    self.connector.create_secret(
                        name=secret_name,
                        secret_value=secret_value,
                        execution_role_arn=self.execution_role_arn,
                    )
            elif compare_secret_json(wrap_raw_data_for_export(existing, allow_encoding="json"), secret_value):
                summary.unchanged += 1
            else:
                summary.modified += 1
                if not dry_run:
                    self.connector.update_secret(
                        secret_id=secret_name,
                        secret_value=secret_value,
                        execution_role_arn=self.execution_role_arn,
                    )
        return summary


class S3SecretStore:
    """S3-backed JSON object store for merged secret bundles."""

    def __init__(
        self,
        connector: AWSConnector | None = None,
        *,
        bucket: str,
        prefix: str = "secrets-sync",
        execution_role_arn: str | None = None,
    ) -> None:
        self.connector = connector or AWSConnector(execution_role_arn=execution_role_arn)
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.execution_role_arn = execution_role_arn

    def _key(self, root: str) -> str:
        return f"{join_secret_path(self.prefix, root)}.json"

    def read_tree(self, root: str = "") -> SecretTree:
        """Read one JSON bundle object from S3."""
        payload = self.connector.get_json_object(
            bucket=self.bucket,
            key=self._key(root),
            execution_role_arn=self.execution_role_arn,
        )
        if not isinstance(payload, Mapping):
            return {}
        return {str(key): normalize_secret_payload(value) for key, value in to_builtin(payload).items()}

    def write_tree(self, secrets: Mapping[str, Mapping[str, Any]], root: str = "", *, dry_run: bool = False) -> WriteSummary:
        """Write one JSON bundle object to S3."""
        current = self.read_tree(root)
        summary = WriteSummary(processed=len(secrets))
        for key, payload in secrets.items():
            existing = current.get(key)
            normalized = normalize_secret_payload(payload)
            if existing is None:
                summary.added += 1
            elif deep_equal(existing, normalized):
                summary.unchanged += 1
            else:
                summary.modified += 1
        if not dry_run:
            self.connector.put_json_object(
                bucket=self.bucket,
                key=self._key(root),
                data={str(key): normalize_secret_payload(value) for key, value in secrets.items()},
                execution_role_arn=self.execution_role_arn,
            )
        return summary


@dataclass(slots=True)
class StoreRegistry:
    """Explicit store injection for tests and custom vendor wiring."""

    sources: MutableMapping[str, SecretTreeStore] = field(default_factory=dict)
    targets: MutableMapping[str, SecretTreeStore] = field(default_factory=dict)
    merge_store: SecretTreeStore | None = None


def _decode_secret_payload(payload: Any) -> Any:
    if not isinstance(payload, str):
        return payload
    stripped = payload.strip()
    if not stripped.startswith(("{", "[")):
        return {"value": payload}
    try:
        from extended_data.io.files import decode_file

        return decode_file(stripped, suffix="json", as_extended=False)
    except Exception:
        return {"value": payload}
