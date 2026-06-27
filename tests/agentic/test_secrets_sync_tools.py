"""Tests for SecretSync agent tool adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("extended_data")
pytest.importorskip("vendor_fabric.secrets_sync")

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data

from vendor_fabric.agentic.tools.secrets_sync import (
    RunPipelineSchema,
    dry_run,
    get_config_info,
    get_sources,
    get_targets,
    run_pipeline,
    validate_config,
)
from vendor_fabric.secrets_sync import ConfigInfo, SyncOptions, SyncResult


@patch("vendor_fabric.agentic.tools.secrets_sync.native_run_pipeline")
def test_run_pipeline_tool_default_continue_on_error_matches_cli(mock_run_pipeline: MagicMock) -> None:
    mock_run_pipeline.return_value = SyncResult(success=True, secrets_processed=3).to_dict()

    result = run_pipeline("config.yaml")

    options = mock_run_pipeline.call_args.args[1]
    assert isinstance(options, SyncOptions)
    assert options.continue_on_error is True
    assert isinstance(result, ExtendedDict)
    assert isinstance(result["secrets_processed"], int)
    assert result["success"] is True
    assert result["secrets_processed"] == 3


@patch("vendor_fabric.agentic.tools.secrets_sync.native_run_pipeline")
def test_run_pipeline_tool_can_disable_continue_on_error(mock_run_pipeline: MagicMock) -> None:
    mock_run_pipeline.return_value = SyncResult(success=True).to_dict()

    run_pipeline("config.yaml", continue_on_error=False)

    options = mock_run_pipeline.call_args.args[1]
    assert isinstance(options, SyncOptions)
    assert options.continue_on_error is False


def test_run_pipeline_schema_default_continue_on_error_matches_cli() -> None:
    schema = RunPipelineSchema(config_path="config.yaml")

    assert schema.continue_on_error is True


@patch("vendor_fabric.agentic.tools.secrets_sync.native_validate_config")
def test_validate_config_tool_returns_extended_payload(mock_validate_config: MagicMock) -> None:
    mock_validate_config.return_value = extend_data(
        {
            "valid": True,
            "message": "valid config",
            "config_path": "config.yaml",
        }
    )

    result = validate_config("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["message"], ExtendedString)
    assert result["valid"] is True
    assert result["config_path"] == "config.yaml"


@patch("vendor_fabric.agentic.tools.secrets_sync.native_validate_config")
def test_validate_config_tool_redacts_native_payload(mock_validate_config: MagicMock) -> None:
    mock_validate_config.return_value = {
        "valid": False,
        "message": "invalid password=hunter2 Authorization: Bearer raw_token",
        "config_path": "config.yaml",
    }

    result = validate_config("config.yaml")

    assert result["valid"] is False
    assert "hunter2" not in result["message"]
    assert "raw_token" not in result["message"]
    assert "[REDACTED]" in result["message"]


@patch("vendor_fabric.agentic.tools.secrets_sync.native_dry_run")
def test_dry_run_tool_returns_extended_payload(mock_dry_run: MagicMock) -> None:
    mock_dry_run.return_value = SyncResult(
        success=True,
        target_count=2,
        secrets_added=1,
        secrets_modified=2,
        secrets_removed=0,
        secrets_unchanged=3,
        diff_output="diff",
    ).to_dict()

    result = dry_run("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["diff_output"], ExtendedString)
    assert result["secrets_would_add"] == 1


@patch("vendor_fabric.agentic.tools.secrets_sync.native_run_pipeline")
def test_run_pipeline_tool_redacts_native_payload_summary(mock_run_pipeline: MagicMock) -> None:
    mock_run_pipeline.return_value = {
        "success": False,
        "error_message": "pipeline failed password=hunter2 Authorization: Bearer raw_token",
        "diff_output": "changed token=tok_123",
    }

    result = run_pipeline("config.yaml", dry_run=True)

    assert result["success"] is False
    assert "hunter2" not in result["error_message"]
    assert "raw_token" not in result["error_message"]
    assert "tok_123" not in result["diff_output"]
    assert "[REDACTED]" in result["error_message"]
    assert "[REDACTED]" in result["diff_output"]


@patch("vendor_fabric.agentic.tools.secrets_sync.native_dry_run")
def test_dry_run_tool_redacts_native_payload_summary(mock_dry_run: MagicMock) -> None:
    mock_dry_run.return_value = {
        "success": False,
        "error_message": "dry run failed password=hunter2 Authorization: Bearer raw_token",
        "diff_output": "changed token=tok_123",
    }

    result = dry_run("config.yaml")

    assert result["success"] is False
    assert "hunter2" not in result["error_message"]
    assert "raw_token" not in result["error_message"]
    assert "tok_123" not in result["diff_output"]
    assert "[REDACTED]" in result["error_message"]
    assert "[REDACTED]" in result["diff_output"]


@patch("vendor_fabric.agentic.tools.secrets_sync.native_get_config_info")
def test_get_config_info_tool_returns_extended_payload(mock_get_config_info: MagicMock) -> None:
    mock_get_config_info.return_value = ConfigInfo(
        valid=True,
        source_count=1,
        target_count=1,
        sources=["vault/prod"],
        targets=["aws/prod"],
        has_merge_store=True,
        vault_address="https://vault.example.com",
        aws_region="us-east-1",
    ).to_dict()

    result = get_config_info("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["sources"], ExtendedList)
    assert isinstance(result["sources"][0], ExtendedString)
    assert result["targets"] == ["aws/prod"]


@patch("vendor_fabric.agentic.tools.secrets_sync.SecretSyncConfig.from_file")
def test_get_targets_tool_returns_extended_payload(mock_from_file: MagicMock) -> None:
    mock_from_file.return_value = MagicMock(targets={"prod": object(), "dev": object()})

    result = get_targets("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["targets"], ExtendedList)
    assert isinstance(result["targets"][0], ExtendedString)
    assert result["count"] == 2


@patch("vendor_fabric.agentic.tools.secrets_sync.SecretSyncConfig.from_file")
def test_get_sources_tool_returns_extended_payload(mock_from_file: MagicMock) -> None:
    mock_from_file.return_value = MagicMock(sources={"vault/prod": object()})

    result = get_sources("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["sources"], ExtendedList)
    assert isinstance(result["sources"][0], ExtendedString)
    assert result["count"] == 1
