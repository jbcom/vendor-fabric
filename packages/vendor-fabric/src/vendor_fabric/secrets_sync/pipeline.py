"""Native Python SecretSync pipeline orchestration."""

from __future__ import annotations

import time

from collections.abc import Mapping
from typing import Any

from extended_data.containers import ExtendedData, ExtendedDict, extend_data
from extended_data.logging import Logging
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.aws import AWSConnector
from vendor_fabric.secrets_sync.bundles import target_bundle_path
from vendor_fabric.secrets_sync.deepmerge import deep_merge
from vendor_fabric.secrets_sync.graph import Graph
from vendor_fabric.secrets_sync.models import (
    ConfigInfo,
    OperationResult,
    OutputFormat,
    ResultDetails,
    SecretSyncConfig,
    Source,
    SyncOperation,
    SyncOptions,
    SyncResult,
    Target,
    TargetDiff,
    redacted_error,
)
from vendor_fabric.secrets_sync.stores import (
    AWSSecretsManagerStore,
    InMemorySecretStore,
    S3SecretStore,
    SecretTree,
    SecretTreeStore,
    StoreRegistry,
    VaultSecretStore,
)
from vendor_fabric.vault import VaultConnector


class SecretSyncPipeline:
    """Native Python pipeline for merging and syncing vendor secrets."""

    def __init__(
        self,
        config: SecretSyncConfig,
        *,
        stores: StoreRegistry | None = None,
        logger: Logging | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.graph = Graph.from_config(config)
        self.stores = stores or StoreRegistry()
        self.logger = logger or Logging(logger_name="vendor-fabric.secrets-sync", enable_console=False, enable_file=False)
        self._default_merge_store = InMemorySecretStore()
        self._bundles: dict[str, SecretTree] = {}
        self._last_results: list[OperationResult] = []

    @classmethod
    def from_file(
        cls,
        config_path: str,
        *,
        stores: StoreRegistry | None = None,
        logger: Logging | None = None,
    ) -> SecretSyncPipeline:
        """Create a pipeline from a YAML config path."""
        return cls(SecretSyncConfig.from_file(config_path), stores=stores, logger=logger)

    def run(self, options: SyncOptions | None = None) -> SyncResult:
        """Execute the configured pipeline."""
        start = time.monotonic()
        options = options or SyncOptions(
            dry_run=self.config.pipeline.dry_run,
            continue_on_error=self.config.pipeline.continue_on_error,
        )
        targets = self.resolve_targets(options.targets)
        results: list[OperationResult] = []
        error_message = ""

        try:
            if options.operation in {SyncOperation.MERGE, SyncOperation.PIPELINE}:
                results.extend(self._execute_merge_phase(targets, options))
            if options.operation in {SyncOperation.SYNC, SyncOperation.PIPELINE}:
                results.extend(self._execute_sync_phase(targets, options))
        except Exception as exc:
            error_message = redacted_error(exc)
            if not options.continue_on_error:
                raise

        self._last_results = results
        aggregate = self._aggregate(results)
        aggregate.duration_ms = int((time.monotonic() - start) * 1000)
        aggregate.error_message = error_message or aggregate.error_message
        if options.compute_diff or options.dry_run:
            aggregate.diff_output = format_diff(
                [result.diff for result in results if result.diff],
                output_format=options.output_format,
            )
        return aggregate

    def run_extended(self, options: SyncOptions | None = None) -> ExtendedData:
        """Execute the pipeline and wrap the result in a generic ExtendedData facade."""
        return ExtendedData(self.run(options).to_dict())

    def validate_config(self) -> ExtendedDict:
        """Return a validation result payload."""
        try:
            self.config.validate()
        except Exception as exc:
            return extend_data({"valid": False, "message": redacted_error(exc)})
        return extend_data({"valid": True, "message": "Configuration is valid"})

    def config_info(self) -> ConfigInfo:
        """Return public configuration info."""
        return self.config.info()

    def resolve_targets(self, requested: list[str] | None = None) -> list[str]:
        """Resolve requested targets and their target dependencies."""
        if requested:
            return self.graph.include_dependencies(requested)
        return self.graph.topological_order()

    def merge_target(self, target_name: str, *, dry_run: bool = False) -> OperationResult:
        """Merge sources for one target into the merge store."""
        start = time.monotonic()
        target = self._require_target(target_name)
        source_paths: list[str] = []
        merged: SecretTree = {}
        failed_imports: list[str] = []

        for import_name in target.imports:
            try:
                source_tree = self._read_import_tree(import_name)
                source_paths.append(self.config.get_source_path(import_name))
                for secret_path, payload in source_tree.items():
                    merged[secret_path] = deep_merge(merged.get(secret_path), payload)
            except Exception as exc:
                failed_imports.append(import_name)
                self.logger.logged_statement(
                    f"Failed to read SecretSync import {redact_sensitive_text(import_name)}: {redacted_error(exc)}",
                    log_level="warning",
                )

        bundle_path = self.bundle_path_for_target(target_name)
        self._bundles[target_name] = merged
        summary = self._merge_store().write_tree(merged, bundle_path, dry_run=dry_run)

        success = not failed_imports
        return OperationResult(
            target=target_name,
            phase="merge",
            operation=SyncOperation.MERGE.value,
            success=success,
            error_message=f"failed imports: {', '.join(failed_imports)}" if failed_imports else "",
            duration_ms=int((time.monotonic() - start) * 1000),
            details=ResultDetails(
                secrets_processed=summary.processed,
                secrets_added=summary.added,
                secrets_modified=summary.modified,
                secrets_unchanged=summary.unchanged,
                source_paths=source_paths,
                destination_path=bundle_path,
                failed_imports=failed_imports,
            ),
            diff=TargetDiff(
                target=target_name,
                phase="merge",
                added=list(merged),
                unchanged=[] if dry_run else list(merged),
            ),
        )

    def sync_target(self, target_name: str, *, dry_run: bool = False) -> OperationResult:
        """Sync one target bundle into its target store."""
        start = time.monotonic()
        target = self._require_target(target_name)
        bundle_path = self.bundle_path_for_target(target_name)
        secrets = self._bundles.get(target_name) or self._merge_store().read_tree(bundle_path)
        target_store = self._target_store(target_name, target)
        current = target_store.read_tree(target.secret_prefix)
        diff = diff_trees(target_name, "sync", current, secrets)
        summary = target_store.write_tree(secrets, target.secret_prefix, dry_run=dry_run)
        role_arn = self.config.role_arn_for_target(target)

        return OperationResult(
            target=target_name,
            phase="sync",
            operation=SyncOperation.SYNC.value,
            success=True,
            duration_ms=int((time.monotonic() - start) * 1000),
            details=ResultDetails(
                secrets_processed=summary.processed,
                secrets_added=summary.added,
                secrets_modified=summary.modified,
                secrets_removed=summary.removed,
                secrets_unchanged=summary.unchanged,
                source_paths=[bundle_path],
                destination_path=f"aws://{target.account_id}" if target.account_id else target_name,
                role_arn=role_arn,
            ),
            diff=diff,
        )

    def bundle_path_for_target(self, target_name: str) -> str:
        """Return the deterministic merge-store path for a target."""
        target = self._require_target(target_name)
        source_paths = [self.config.get_source_path(import_name) for import_name in target.imports]
        mount = self.config.merge_store.vault.mount if self.config.merge_store.vault else "memory"
        return target_bundle_path(mount, target_name, source_paths)

    def _execute_merge_phase(self, targets: list[str], options: SyncOptions) -> list[OperationResult]:
        results: list[OperationResult] = []
        for level in self.graph.group_by_level():
            for target_name in [target for target in level if target in targets]:
                result = self.merge_target(target_name, dry_run=options.dry_run)
                results.append(result)
                if not result.success and not options.continue_on_error:
                    return results
        return results

    def _execute_sync_phase(self, targets: list[str], options: SyncOptions) -> list[OperationResult]:
        results: list[OperationResult] = []
        for target_name in targets:
            result = self.sync_target(target_name, dry_run=options.dry_run)
            results.append(result)
            if not result.success and not options.continue_on_error:
                return results
        return results

    def _read_import_tree(self, import_name: str) -> SecretTree:
        if import_name in self.config.targets:
            return self._bundles.get(import_name) or self._merge_store().read_tree(self.bundle_path_for_target(import_name))
        source = self.config.sources.get(import_name)
        if source is None:
            msg = f"unknown source or target import: {import_name}"
            raise ValueError(msg)
        return self._source_store(import_name, source).read_tree(self.config.get_source_path(import_name))

    def _source_store(self, source_name: str, source: Source) -> SecretTreeStore:
        if source_name in self.stores.sources:
            return self.stores.sources[source_name]
        if source.vault:
            connector = VaultConnector(
                vault_url=source.vault.address or self.config.vault.address or None,
                vault_namespace=source.vault.namespace or self.config.vault.namespace or None,
            )
            return VaultSecretStore(connector, mount=source.vault.mount or source_name)
        if source.aws:
            role_arn = source.aws.role_arn or self.config.role_arn_for_target(
                Target(account_id=source.aws.account_id, region=source.aws.region)
            )
            return AWSSecretsManagerStore(
                AWSConnector(execution_role_arn=role_arn or None),
                prefix=source.aws.prefix,
                execution_role_arn=role_arn or None,
            )
        msg = f"source {source_name!r} has no supported vendor store"
        raise ValueError(msg)

    def _target_store(self, target_name: str, target: Target) -> SecretTreeStore:
        if target_name in self.stores.targets:
            return self.stores.targets[target_name]
        role_arn = self.config.role_arn_for_target(target)
        return AWSSecretsManagerStore(
            AWSConnector(execution_role_arn=role_arn or None),
            prefix=target.secret_prefix,
            execution_role_arn=role_arn or None,
        )

    def _merge_store(self) -> SecretTreeStore:
        if self.stores.merge_store is not None:
            return self.stores.merge_store
        if self.config.merge_store.vault:
            return VaultSecretStore(mount=self.config.merge_store.vault.mount)
        if self.config.merge_store.s3:
            return S3SecretStore(
                bucket=self.config.merge_store.s3.bucket,
                prefix=self.config.merge_store.s3.prefix,
            )
        return self._default_merge_store

    def _require_target(self, target_name: str) -> Target:
        try:
            return self.config.targets[target_name]
        except KeyError as exc:
            msg = f"target not found: {target_name}"
            raise ValueError(msg) from exc

    @staticmethod
    def _aggregate(results: list[OperationResult]) -> SyncResult:
        target_names = {result.target for result in results}
        success = all(result.success for result in results)
        errors = [result.error_message for result in results if result.error_message]
        aggregate = SyncResult(
            success=success,
            target_count=len(target_names),
            error_message="; ".join(errors),
            results=results,
        )
        for result in results:
            aggregate.secrets_processed += result.details.secrets_processed
            aggregate.secrets_added += result.details.secrets_added
            aggregate.secrets_modified += result.details.secrets_modified
            aggregate.secrets_removed += result.details.secrets_removed
            aggregate.secrets_unchanged += result.details.secrets_unchanged
        return aggregate


def validate_config(config_path: str) -> ExtendedDict:
    """Validate a config file and return an Extended Data payload."""
    try:
        config = SecretSyncConfig.from_file(config_path)
        config.validate()
    except Exception as exc:
        return extend_data({"valid": False, "message": redacted_error(exc), "config_path": config_path})
    return extend_data({"valid": True, "message": "Configuration is valid", "config_path": config_path})


def get_config_info(config_path: str) -> ExtendedDict:
    """Return public configuration info for a config file."""
    try:
        config = SecretSyncConfig.from_file(config_path)
        return config.info().to_dict()
    except Exception as exc:
        return ConfigInfo(error_message=redacted_error(exc)).to_dict()


def run_pipeline(config_path: str, options: SyncOptions | None = None) -> ExtendedDict:
    """Run a SecretSync config file and return an Extended Data payload."""
    return SecretSyncPipeline.from_file(config_path).run(options).to_dict()


def dry_run(config_path: str) -> ExtendedDict:
    """Run a dry-run pipeline."""
    return run_pipeline(config_path, SyncOptions(dry_run=True, compute_diff=True))


def merge(config_path: str, *, dry_run: bool = False) -> ExtendedDict:
    """Run only the merge phase."""
    return run_pipeline(config_path, SyncOptions(operation=SyncOperation.MERGE, dry_run=dry_run, compute_diff=dry_run))


def sync(config_path: str, *, dry_run: bool = False) -> ExtendedDict:
    """Run only the sync phase."""
    return run_pipeline(config_path, SyncOptions(operation=SyncOperation.SYNC, dry_run=dry_run, compute_diff=dry_run))


def diff_trees(target: str, phase: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> TargetDiff:
    """Return a diff summary for two secret trees."""
    added: list[str] = []
    modified: list[str] = []
    removed: list[str] = []
    unchanged: list[str] = []

    before_keys = set(before)
    after_keys = set(after)
    for key in sorted(after_keys - before_keys):
        added.append(key)
    for key in sorted(before_keys - after_keys):
        removed.append(key)
    for key in sorted(before_keys & after_keys):
        if deep_merge({}, before[key]) == deep_merge({}, after[key]):
            unchanged.append(key)
        else:
            modified.append(key)
    return TargetDiff(target=target, phase=phase, added=added, modified=modified, removed=removed, unchanged=unchanged)


def format_diff(diffs: list[TargetDiff], *, output_format: OutputFormat = OutputFormat.JSON) -> str:
    """Format target diffs for CLI and agent diagnostics."""
    payload = [
        {
            "target": diff.target,
            "phase": diff.phase,
            "added": diff.added,
            "modified": diff.modified,
            "removed": diff.removed,
            "unchanged": diff.unchanged,
        }
        for diff in diffs
    ]
    if output_format is OutputFormat.JSON:
        return ExtendedDict({"diffs": payload}).wrap_for_export("json")
    lines: list[str] = []
    for diff in diffs:
        lines.append(f"{diff.phase}:{diff.target}")
        for label, values in [
            ("added", diff.added),
            ("modified", diff.modified),
            ("removed", diff.removed),
            ("unchanged", diff.unchanged),
        ]:
            if values:
                lines.append(f"  {label}: {', '.join(values)}")
    return "\n".join(lines)
