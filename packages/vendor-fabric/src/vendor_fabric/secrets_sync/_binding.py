"""Adapter for the SecretSync gopy binding package."""

from __future__ import annotations

import importlib
import json

from collections.abc import Mapping
from typing import Any

from extended_data.containers import ExtendedDict, extend_data
from extended_data.primitives.redaction import redact_sensitive_data, redact_sensitive_text

from vendor_fabric.secrets_sync.models import (
    ConfigInfo,
    ProviderSession,
    SyncOperation,
    SyncOptions,
    SyncResult,
)


BINDING_MODULE = "secrets_sync"
BINDING_INSTALL_GUIDANCE = (
    "SecretSync Python bindings are required for pipeline execution. "
    "Install secrets-sync-python-binding or build a wheel from jbcom/secrets-sync with `just python-build`."
)


def load_binding() -> Any:
    """Import the gopy-generated SecretSync binding module."""
    try:
        return importlib.import_module(BINDING_MODULE)
    except ImportError as exc:
        raise ImportError(BINDING_INSTALL_GUIDANCE) from exc


def is_binding_available() -> bool:
    """Return whether the SecretSync gopy binding can be imported."""
    try:
        load_binding()
    except ImportError:
        return False
    return True


def validate_config(config_path: str) -> ExtendedDict:
    """Validate a SecretSync config through the binding."""
    binding = load_binding()
    result = binding.ValidateConfig(config_path)
    valid, message = _validation_result(result)
    return extend_data(
        {
            "valid": bool(valid),
            "message": redact_sensitive_text(message),
            "error_message": redact_sensitive_text(message if not valid else ""),
            "config_path": config_path,
        }
    )


def get_config_info(config_path: str) -> ExtendedDict:
    """Return SecretSync config metadata through the binding."""
    binding = load_binding()
    return _config_info_to_dict(binding.GetConfigInfo(config_path))


def run_pipeline(
    config_path: str,
    options: SyncOptions | None = None,
    provider_session: ProviderSession | Mapping[str, Any] | None = None,
) -> ExtendedDict:
    """Run the SecretSync pipeline through the binding."""
    binding = load_binding()
    binding_options = _to_binding_options(binding, options)
    if provider_session is None:
        return _sync_result_to_dict(binding.RunPipeline(config_path, binding_options))
    return _sync_result_to_dict(
        binding.RunPipelineWithSession(
            config_path,
            binding_options,
            _to_binding_provider_session(binding, provider_session),
        )
    )


def dry_run(
    config_path: str,
    provider_session: ProviderSession | Mapping[str, Any] | None = None,
) -> ExtendedDict:
    """Run a SecretSync dry run through the binding."""
    binding = load_binding()
    if provider_session is not None:
        return _sync_result_to_dict(
            binding.DryRunWithSession(config_path, _to_binding_provider_session(binding, provider_session))
        )
    return _sync_result_to_dict(binding.DryRun(config_path))


def get_targets(config_path: str) -> ExtendedDict:
    """Return SecretSync target names through the binding."""
    binding = load_binding()
    return _name_list_to_dict(binding.GetTargets(config_path), "targets", config_path)


def get_sources(config_path: str) -> ExtendedDict:
    """Return SecretSync source names through the binding."""
    binding = load_binding()
    return _name_list_to_dict(binding.GetSources(config_path), "sources", config_path)


def merge(
    config_path: str,
    *,
    dry_run: bool = False,
    provider_session: ProviderSession | Mapping[str, Any] | None = None,
) -> ExtendedDict:
    """Run the SecretSync merge phase through the binding."""
    binding = load_binding()
    if provider_session is not None:
        return _sync_result_to_dict(
            binding.MergeWithSession(
                config_path,
                dry_run,
                _to_binding_provider_session(binding, provider_session),
            )
        )
    return _sync_result_to_dict(binding.Merge(config_path, dry_run))


def sync(
    config_path: str,
    *,
    dry_run: bool = False,
    provider_session: ProviderSession | Mapping[str, Any] | None = None,
) -> ExtendedDict:
    """Run the SecretSync sync phase through the binding."""
    binding = load_binding()
    if provider_session is not None:
        return _sync_result_to_dict(
            binding.SyncWithSession(
                config_path,
                dry_run,
                _to_binding_provider_session(binding, provider_session),
            )
        )
    return _sync_result_to_dict(binding.Sync(config_path, dry_run))


def _to_binding_options(binding: Any, options: SyncOptions | None) -> Any:
    """Convert local options into the gopy SyncOptions type."""
    binding_options = binding.DefaultSyncOptions()
    if options is None:
        return binding_options

    _set_binding_attr(binding_options, "DryRun", options.dry_run)
    _set_binding_attr(binding_options, "Operation", _operation_value(options.operation))
    _set_binding_attr(binding_options, "Targets", ",".join(str(target) for target in options.targets))
    _set_binding_attr(binding_options, "ContinueOnError", options.continue_on_error)
    _set_binding_attr(binding_options, "Parallelism", options.parallelism)
    _set_binding_attr(binding_options, "ComputeDiff", options.compute_diff)
    _set_binding_attr(binding_options, "OutputFormat", str(options.output_format.value))
    _set_binding_attr(binding_options, "ShowValues", options.show_values)
    return binding_options


def _set_binding_attr(value: Any, name: str, attr_value: Any) -> None:
    """Set a binding attribute, tolerating generated snake_case aliases."""
    if hasattr(value, name):
        setattr(value, name, attr_value)
        return
    snake_name = _camel_to_snake(name)
    setattr(value, snake_name, attr_value)


def _to_binding_provider_session(binding: Any, provider_session: ProviderSession | Mapping[str, Any]) -> Any:
    """Convert local provider session material into the gopy ProviderSession type."""
    binding_session = binding.NewProviderSession()
    for binding_name, local_name in (
        ("DelegateAuth", "delegate_auth"),
        ("VaultAddress", "vault_address"),
        ("VaultNamespace", "vault_namespace"),
        ("VaultToken", "vault_token"),
        ("AWSRegion", "aws_region"),
        ("AWSAccessKeyID", "aws_access_key_id"),
        ("AWSSecretAccessKey", "aws_secret_access_key"),
        ("AWSSessionToken", "aws_session_token"),
        ("AWSRoleARN", "aws_role_arn"),
        ("AWSEndpointURL", "aws_endpoint_url"),
    ):
        _set_binding_attr(
            binding_session,
            binding_name,
            _session_value(provider_session, local_name, binding_name),
        )
    return binding_session


def _session_value(provider_session: ProviderSession | Mapping[str, Any], local_name: str, binding_name: str) -> Any:
    """Read a provider-session field from a local model or mapping."""
    value = _attr(provider_session, local_name, binding_name, default=None)
    if value is None and binding_name.startswith("AWS"):
        value = _attr(provider_session, binding_name.replace("AWS", "Aws", 1), default=None)
    if value is None:
        return False if local_name == "delegate_auth" else ""
    return value


def _operation_value(operation: SyncOperation | str) -> str:
    if isinstance(operation, SyncOperation):
        return operation.value
    return str(operation)


def _config_info_to_dict(info: Any) -> ExtendedDict:
    """Convert a binding ConfigInfo value into the local payload contract."""
    return extend_data(
        redact_sensitive_data(
            ConfigInfo(
                valid=bool(_attr(info, "Valid", "valid", default=False)),
                error_message=redact_sensitive_text(_attr(info, "ErrorMessage", "error_message", default="")),
                source_count=int(_attr(info, "SourceCount", "source_count", default=0) or 0),
                target_count=int(_attr(info, "TargetCount", "target_count", default=0) or 0),
                sources=_list_attr(info, "Sources", "sources"),
                targets=_list_attr(info, "Targets", "targets"),
                has_merge_store=bool(_attr(info, "HasMergeStore", "has_merge_store", default=False)),
                vault_address=str(_attr(info, "VaultAddress", "vault_address", default="") or ""),
                aws_region=str(_attr(info, "AWSRegion", "aws_region", default="") or ""),
            ).to_dict()
        )
    )


def _validation_result(result: Any) -> tuple[bool, str]:
    """Normalize the SecretSync binding ValidationResult payload."""
    if isinstance(result, tuple) and len(result) == 2:
        valid, message = result
        return bool(valid), str(message or "")
    valid = bool(_attr(result, "Valid", "valid", default=False))
    if valid:
        message = _attr(result, "Message", "message", default="")
    else:
        message = _attr(result, "ErrorMessage", "error_message", "Message", "message", default="")
    if not message:
        message = _attr(result, "Message", "message", default="")
    return valid, str(message or "")


def _sync_result_to_dict(result: Any) -> ExtendedDict:
    """Convert a binding SyncResult value into the local payload contract."""
    payload = SyncResult(
        success=bool(_attr(result, "Success", "success", default=False)),
        target_count=int(_attr(result, "TargetCount", "target_count", default=0) or 0),
        secrets_processed=int(_attr(result, "SecretsProcessed", "secrets_processed", default=0) or 0),
        secrets_added=int(_attr(result, "SecretsAdded", "secrets_added", default=0) or 0),
        secrets_modified=int(_attr(result, "SecretsModified", "secrets_modified", default=0) or 0),
        secrets_removed=int(_attr(result, "SecretsRemoved", "secrets_removed", default=0) or 0),
        secrets_unchanged=int(_attr(result, "SecretsUnchanged", "secrets_unchanged", default=0) or 0),
        duration_ms=int(_attr(result, "DurationMs", "duration_ms", default=0) or 0),
        error_message=redact_sensitive_text(_attr(result, "ErrorMessage", "error_message", default="")),
        diff_output=redact_sensitive_text(_attr(result, "DiffOutput", "diff_output", default="")),
    ).to_dict()
    results_json = _attr(result, "ResultsJSON", "results_json", default="")
    parsed_results = _parse_results_json(results_json)
    if parsed_results is not None:
        payload["results"] = extend_data(redact_sensitive_data(parsed_results))
    return payload


def _name_list_to_dict(result: Any, key: str, config_path: str) -> ExtendedDict:
    names, message = _name_list_result(result, key)
    message = redact_sensitive_text(message)
    return extend_data(
        redact_sensitive_data(
            {
                "valid": not bool(message),
                key: sorted(str(item) for item in names),
                "count": len(names),
                "error_message": message,
                "config_path": config_path,
            }
        )
    )


def _name_list_result(result: Any, key: str) -> tuple[list[str], str]:
    if isinstance(result, tuple) and len(result) == 2:
        names, message = result
        return _coerce_name_list(names), str(message or "")
    names = _attr(result, key, key.capitalize(), "Values", "values", default=None)
    if names is not None:
        return (
            _coerce_name_list(names),
            str(_attr(result, "ErrorMessage", "error_message", "Message", "message", default="") or ""),
        )
    return _coerce_name_list(result), ""


def _coerce_name_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]
    except TypeError:
        return [str(value)]


def _parse_results_json(value: Any) -> list[Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    return None


def _attr(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _list_attr(value: Any, *names: str) -> list[str]:
    attr_value = _attr(value, *names, default=[])
    if attr_value is None:
        return []
    return [str(item) for item in attr_value]


def _camel_to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
