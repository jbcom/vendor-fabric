"""Configuration and result models for native SecretSync pipelines."""

from __future__ import annotations

import os
import re

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from extended_data.containers import ExtendedDict, extend_data
from extended_data.io import DataFile
from extended_data.primitives.redaction import redact_sensitive_data, redact_sensitive_text


AWS_ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
MAX_ENV_VALUE_LENGTH = 10_000


class SyncOperation(StrEnum):
    """Pipeline operation types."""

    MERGE = "merge"
    SYNC = "sync"
    PIPELINE = "pipeline"


class OutputFormat(StrEnum):
    """Diff output formats."""

    HUMAN = "human"
    JSON = "json"
    GITHUB = "github"
    COMPACT = "compact"
    SIDE_BY_SIDE = "side-by-side"


@dataclass(slots=True)
class SyncOptions:
    """Options for pipeline execution."""

    dry_run: bool = False
    operation: SyncOperation = SyncOperation.PIPELINE
    targets: list[str] = field(default_factory=list)
    continue_on_error: bool = True
    parallelism: int = 4
    compute_diff: bool = False
    output_format: OutputFormat = OutputFormat.JSON
    show_values: bool = False
    delete_orphans: bool = False


@dataclass(slots=True)
class LogConfig:
    """Logging configuration."""

    level: str = "info"
    format: str = "text"


@dataclass(slots=True)
class VaultAuthAppRole:
    """Vault AppRole authentication config."""

    mount: str = "approle"
    role_id: str = ""
    secret_id: str = ""


@dataclass(slots=True)
class VaultAuthToken:
    """Vault token authentication config."""

    token: str = ""


@dataclass(slots=True)
class VaultAuthKubernetes:
    """Vault Kubernetes authentication config."""

    role: str = ""
    mount_path: str = "kubernetes"


@dataclass(slots=True)
class VaultAuthConfig:
    """Vault authentication config."""

    approle: VaultAuthAppRole | None = None
    token: VaultAuthToken | None = None
    kubernetes: VaultAuthKubernetes | None = None


@dataclass(slots=True)
class VaultConfig:
    """Vault connection config."""

    address: str = ""
    namespace: str = ""
    auth: VaultAuthConfig = field(default_factory=VaultAuthConfig)
    max_traversal_depth: int | None = None
    max_secrets_per_mount: int | None = None
    queue_compaction_threshold: int | None = None


@dataclass(slots=True)
class ExecutionRoleConfig:
    """Control Tower execution role config."""

    name: str = "AWSControlTowerExecution"
    path: str = "/"


@dataclass(slots=True)
class ControlTowerConfig:
    """AWS Control Tower config."""

    enabled: bool = False
    execution_role: ExecutionRoleConfig = field(default_factory=ExecutionRoleConfig)


@dataclass(slots=True)
class ExecutionContextConfig:
    """AWS execution context config."""

    type: str = ""
    account_id: str = ""
    custom_role_pattern: str = ""


@dataclass(slots=True)
class AWSConfig:
    """AWS config."""

    region: str = "us-east-1"
    execution_context: ExecutionContextConfig = field(default_factory=ExecutionContextConfig)
    control_tower: ControlTowerConfig = field(default_factory=ControlTowerConfig)


@dataclass(slots=True)
class VaultSource:
    """Vault source config."""

    mount: str = ""
    paths: list[str] = field(default_factory=list)
    address: str = ""
    namespace: str = ""


@dataclass(slots=True)
class AWSSource:
    """AWS Secrets Manager source config."""

    account_id: str = ""
    region: str = ""
    prefix: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    role_arn: str = ""


@dataclass(slots=True)
class Source:
    """Source config."""

    vault: VaultSource | None = None
    aws: AWSSource | None = None


@dataclass(slots=True)
class MergeStoreVault:
    """Vault merge store config."""

    mount: str = "merged-secrets"


@dataclass(slots=True)
class MergeStoreS3:
    """S3 merge store config."""

    bucket: str = ""
    prefix: str = "secrets-sync"
    kms_key_id: str = ""


@dataclass(slots=True)
class MergeStoreConfig:
    """Merge store config."""

    vault: MergeStoreVault | None = None
    s3: MergeStoreS3 | None = None


@dataclass(slots=True)
class Target:
    """Sync destination target."""

    account_id: str = ""
    imports: list[str] = field(default_factory=list)
    region: str = ""
    secret_prefix: str = ""
    role_arn: str = ""


@dataclass(slots=True)
class AccountNamePattern:
    """Dynamic target account-name routing pattern."""

    pattern: str = ""
    target: str = ""


@dataclass(slots=True)
class DynamicTarget:
    """Runtime-discovered target config."""

    imports: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    account_name_patterns: list[AccountNamePattern] = field(default_factory=list)
    region: str = ""
    secret_prefix: str = ""
    role_arn: str = ""
    discovery: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MergeSettings:
    """Merge phase settings."""

    parallel: int = 4


@dataclass(slots=True)
class SyncSettings:
    """Sync phase settings."""

    parallel: int = 4
    delete_orphans: bool = False


@dataclass(slots=True)
class PipelineSettings:
    """Pipeline settings."""

    merge: MergeSettings = field(default_factory=MergeSettings)
    sync: SyncSettings = field(default_factory=SyncSettings)
    dry_run: bool = False
    continue_on_error: bool = True


@dataclass(slots=True)
class ConfigInfo:
    """Public configuration information."""

    valid: bool = False
    error_message: str = ""
    source_count: int = 0
    target_count: int = 0
    sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    has_merge_store: bool = False
    vault_address: str = ""
    aws_region: str = ""

    def to_dict(self) -> ExtendedDict:
        """Return an extended config info payload."""
        return extend_data(asdict(self))


@dataclass(slots=True)
class ResultDetails:
    """Operation detail counts."""

    secrets_processed: int = 0
    secrets_added: int = 0
    secrets_modified: int = 0
    secrets_removed: int = 0
    secrets_unchanged: int = 0
    source_paths: list[str] = field(default_factory=list)
    destination_path: str = ""
    role_arn: str = ""
    failed_imports: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TargetDiff:
    """Diff summary for one target."""

    target: str
    phase: str
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Return whether the target has changes."""
        return bool(self.added or self.modified or self.removed)


@dataclass(slots=True)
class OperationResult:
    """Outcome for one target and phase."""

    target: str
    phase: str
    operation: str
    success: bool = False
    error_message: str = ""
    duration_ms: int = 0
    details: ResultDetails = field(default_factory=ResultDetails)
    diff: TargetDiff | None = None


@dataclass(slots=True)
class SyncResult:
    """Aggregate pipeline result."""

    success: bool = False
    target_count: int = 0
    secrets_processed: int = 0
    secrets_added: int = 0
    secrets_modified: int = 0
    secrets_removed: int = 0
    secrets_unchanged: int = 0
    duration_ms: int = 0
    error_message: str = ""
    results: list[OperationResult] = field(default_factory=list)
    diff_output: str = ""

    def to_dict(self) -> ExtendedDict:
        """Return an extended result payload with redacted diagnostics."""
        return extend_data(redact_sensitive_data(asdict(self)))


@dataclass(slots=True)
class SecretSyncConfig:
    """SecretSync pipeline configuration."""

    log: LogConfig = field(default_factory=LogConfig)
    vault: VaultConfig = field(default_factory=VaultConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    sources: dict[str, Source] = field(default_factory=dict)
    merge_store: MergeStoreConfig = field(default_factory=MergeStoreConfig)
    targets: dict[str, Target] = field(default_factory=dict)
    dynamic_targets: dict[str, DynamicTarget] = field(default_factory=dict)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)

    @classmethod
    def from_file(cls, path: str | Path, *, auto_detect: bool = True) -> SecretSyncConfig:
        """Load a pipeline configuration from YAML."""
        payload = DataFile.read(str(path), suffix="yaml", as_extended=False).data
        if payload is None:
            payload = {}
        if not isinstance(payload, Mapping):
            msg = f"SecretSync config must be a mapping: {path}"
            raise TypeError(msg)
        config = cls.from_mapping(payload)
        config.expand_env_vars()
        if auto_detect:
            config.apply_environment_overrides()
            config.auto_configure()
        return config

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> SecretSyncConfig:
        """Build a config from a mapping."""
        data = dict(payload or {})
        config = cls(
            log=_log_config(data.get("log")),
            vault=_vault_config(data.get("vault")),
            aws=_aws_config(data.get("aws")),
            sources=_sources_config(data.get("sources")),
            merge_store=_merge_store_config(data.get("merge_store")),
            targets=_targets_config(data.get("targets")),
            dynamic_targets=_dynamic_targets_config(data.get("dynamic_targets")),
            pipeline=_pipeline_settings(data.get("pipeline")),
        )
        config.auto_configure()
        return config

    def validate(self) -> None:
        """Validate the configuration."""
        if not self.targets and not self.dynamic_targets:
            msg = "at least one target or dynamic_target is required"
            raise ValueError(msg)
        if self.merge_store.s3 and not self.merge_store.s3.bucket:
            msg = "merge_store.s3.bucket is required when using S3 merge store"
            raise ValueError(msg)
        for name, target in self.targets.items():
            if target.account_id and not AWS_ACCOUNT_ID_RE.match(target.account_id):
                msg = f'target "{name}": invalid account_id format "{target.account_id}"'
                raise ValueError(msg)
        self.validate_target_inheritance()

    def validate_target_inheritance(self) -> None:
        """Reject circular target inheritance chains."""
        visited: set[str] = set()
        in_stack: set[str] = set()

        def visit(target_name: str, path: list[str]) -> None:
            visited.add(target_name)
            in_stack.add(target_name)
            path.append(target_name)
            target = self.targets.get(target_name)
            if target:
                for imported in target.imports:
                    if imported not in self.targets:
                        continue
                    if imported == target_name:
                        msg = f"circular dependency detected: {target_name} -> {imported} (self-reference)"
                        raise ValueError(msg)
                    if imported not in visited:
                        visit(imported, path)
                    elif imported in in_stack:
                        cycle_start = path.index(imported) if imported in path else len(path) - 1
                        cycle = [*path[cycle_start:], imported]
                        msg = "circular dependency detected in target inheritance: " + " -> ".join(cycle)
                        raise ValueError(msg)
            in_stack.remove(target_name)
            path.pop()

        for name in self.targets:
            if name not in visited:
                visit(name, [])

    def auto_configure(self) -> None:
        """Apply safe defaults and create placeholder sources for imports."""
        if not self.merge_store.vault and not self.merge_store.s3 and self.vault.address:
            self.merge_store.vault = MergeStoreVault()
        for target in self.targets.values():
            for imported in target.imports:
                if imported not in self.targets and imported not in self.sources:
                    self.sources[imported] = Source(vault=VaultSource(mount=imported))

    def expand_env_vars(self) -> None:
        """Expand ``${VAR}`` placeholders in sensitive auth fields."""
        if self.vault.auth.approle:
            self.vault.auth.approle.role_id = _expand_env(self.vault.auth.approle.role_id)
            self.vault.auth.approle.secret_id = _expand_env(self.vault.auth.approle.secret_id)
        if self.vault.auth.token:
            self.vault.auth.token.token = _expand_env(self.vault.auth.token.token)

    def apply_environment_overrides(self) -> None:
        """Apply explicit SecretSync environment overrides."""
        if value := os.getenv("SECRETS_SYNC_LOG_LEVEL"):
            self.log.level = value
        if value := os.getenv("SECRETS_SYNC_AWS_REGION"):
            self.aws.region = value
        if value := os.getenv("SECRETS_SYNC_VAULT_ADDRESS"):
            self.vault.address = value

    def get_source_path(self, import_name: str) -> str:
        """Return the deterministic source path for an import."""
        if source := self.sources.get(import_name):
            if source.vault and source.vault.mount:
                return source.vault.mount
            if source.aws:
                return source.aws.prefix or source.aws.account_id or import_name
        if import_name in self.targets and self.merge_store.vault:
            return f"{self.merge_store.vault.mount}/targets/{import_name}"
        return import_name

    def role_arn_for_target(self, target: Target) -> str:
        """Return the AWS role ARN for a target."""
        if target.role_arn:
            return target.role_arn
        if not target.account_id:
            return ""
        if self.aws.control_tower.enabled:
            role = self.aws.control_tower.execution_role
            path = role.path or "/"
            if not path.startswith("/"):
                path = f"/{path}"
            if not path.endswith("/"):
                path = f"{path}/"
            return f"arn:aws:iam::{target.account_id}:role{path}{role.name}"
        if self.aws.execution_context.custom_role_pattern:
            return self.aws.execution_context.custom_role_pattern.replace("{{.AccountID}}", target.account_id)
        return ""

    def info(self) -> ConfigInfo:
        """Return public configuration info."""
        return ConfigInfo(
            valid=True,
            source_count=len(self.sources),
            target_count=len(self.targets),
            sources=sorted(self.sources),
            targets=sorted(self.targets),
            has_merge_store=bool(self.merge_store.vault or self.merge_store.s3),
            vault_address=self.vault.address,
            aws_region=self.aws.region,
        )


def _expand_env(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        env_value = os.getenv(match.group(1), "")
        if not env_value or len(env_value) > MAX_ENV_VALUE_LENGTH:
            return match.group(0)
        return env_value

    return ENV_PATTERN.sub(replace, value)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple | set):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _log_config(value: Any) -> LogConfig:
    data = _mapping(value)
    return LogConfig(level=str(data.get("level") or "info"), format=str(data.get("format") or "text"))


def _vault_config(value: Any) -> VaultConfig:
    data = _mapping(value)
    auth_data = _mapping(data.get("auth"))
    approle_data = _mapping(auth_data.get("approle"))
    token_data = _mapping(auth_data.get("token"))
    kubernetes_data = _mapping(auth_data.get("kubernetes"))
    return VaultConfig(
        address=str(data.get("address") or ""),
        namespace=str(data.get("namespace") or ""),
        auth=VaultAuthConfig(
            approle=VaultAuthAppRole(
                mount=str(approle_data.get("mount") or "approle"),
                role_id=str(approle_data.get("role_id") or ""),
                secret_id=str(approle_data.get("secret_id") or ""),
            )
            if approle_data
            else None,
            token=VaultAuthToken(token=str(token_data.get("token") or "")) if token_data else None,
            kubernetes=VaultAuthKubernetes(
                role=str(kubernetes_data.get("role") or ""),
                mount_path=str(kubernetes_data.get("mount_path") or "kubernetes"),
            )
            if kubernetes_data
            else None,
        ),
        max_traversal_depth=_optional_int(data.get("max_traversal_depth")),
        max_secrets_per_mount=_optional_int(data.get("max_secrets_per_mount")),
        queue_compaction_threshold=_optional_int(data.get("queue_compaction_threshold")),
    )


def _aws_config(value: Any) -> AWSConfig:
    data = _mapping(value)
    execution_context = _mapping(data.get("execution_context"))
    control_tower = _mapping(data.get("control_tower"))
    execution_role = _mapping(control_tower.get("execution_role"))
    return AWSConfig(
        region=str(data.get("region") or "us-east-1"),
        execution_context=ExecutionContextConfig(
            type=str(execution_context.get("type") or ""),
            account_id=str(execution_context.get("account_id") or ""),
            custom_role_pattern=str(execution_context.get("custom_role_pattern") or ""),
        ),
        control_tower=ControlTowerConfig(
            enabled=bool(control_tower.get("enabled", False)),
            execution_role=ExecutionRoleConfig(
                name=str(execution_role.get("name") or "AWSControlTowerExecution"),
                path=str(execution_role.get("path") or "/"),
            ),
        ),
    )


def _source_config(value: Any, name: str) -> Source:
    data = _mapping(value)
    vault_data = _mapping(data.get("vault"))
    aws_data = _mapping(data.get("aws"))
    return Source(
        vault=VaultSource(
            mount=str(vault_data.get("mount") or name),
            paths=_list(vault_data.get("paths") or ["/"]),
            address=str(vault_data.get("address") or ""),
            namespace=str(vault_data.get("namespace") or ""),
        )
        if vault_data
        else None,
        aws=AWSSource(
            account_id=str(aws_data.get("account_id") or ""),
            region=str(aws_data.get("region") or ""),
            prefix=str(aws_data.get("prefix") or ""),
            tags={str(key): str(item) for key, item in _mapping(aws_data.get("tags")).items()},
            role_arn=str(aws_data.get("role_arn") or ""),
        )
        if aws_data
        else None,
    )


def _sources_config(value: Any) -> dict[str, Source]:
    return {str(name): _source_config(source, str(name)) for name, source in _mapping(value).items()}


def _merge_store_config(value: Any) -> MergeStoreConfig:
    data = _mapping(value)
    vault_data = _mapping(data.get("vault"))
    s3_data = _mapping(data.get("s3"))
    return MergeStoreConfig(
        vault=MergeStoreVault(mount=str(vault_data.get("mount") or "merged-secrets")) if vault_data else None,
        s3=MergeStoreS3(
            bucket=str(s3_data.get("bucket") or ""),
            prefix=str(s3_data.get("prefix") or "secrets-sync"),
            kms_key_id=str(s3_data.get("kms_key_id") or ""),
        )
        if s3_data
        else None,
    )


def _target_config(value: Any) -> Target:
    if isinstance(value, list):
        return Target(imports=_list(value))
    data = _mapping(value)
    return Target(
        account_id=str(data.get("account_id") or ""),
        imports=_list(data.get("imports")),
        region=str(data.get("region") or ""),
        secret_prefix=str(data.get("secret_prefix") or ""),
        role_arn=str(data.get("role_arn") or ""),
    )


def _targets_config(value: Any) -> dict[str, Target]:
    return {str(name): _target_config(target) for name, target in _mapping(value).items()}


def _dynamic_targets_config(value: Any) -> dict[str, DynamicTarget]:
    result: dict[str, DynamicTarget] = {}
    for name, target in _mapping(value).items():
        data = _mapping(target)
        result[str(name)] = DynamicTarget(
            imports=_list(data.get("imports")),
            exclude=_list(data.get("exclude")),
            account_name_patterns=[
                AccountNamePattern(pattern=str(item.get("pattern") or ""), target=str(item.get("target") or ""))
                for item in data.get("account_name_patterns", [])
                if isinstance(item, Mapping)
            ],
            region=str(data.get("region") or ""),
            secret_prefix=str(data.get("secret_prefix") or ""),
            role_arn=str(data.get("role_arn") or ""),
            discovery=_mapping(data.get("discovery")),
        )
    return result


def _pipeline_settings(value: Any) -> PipelineSettings:
    data = _mapping(value)
    merge = _mapping(data.get("merge"))
    sync = _mapping(data.get("sync"))
    return PipelineSettings(
        merge=MergeSettings(parallel=int(merge.get("parallel") or 4)),
        sync=SyncSettings(
            parallel=int(sync.get("parallel") or 4),
            delete_orphans=bool(sync.get("delete_orphans", False)),
        ),
        dry_run=bool(data.get("dry_run", False)),
        continue_on_error=bool(data.get("continue_on_error", True)),
    )


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def redacted_error(exc: BaseException) -> str:
    """Return a redacted exception string."""
    return str(redact_sensitive_text(exc))
