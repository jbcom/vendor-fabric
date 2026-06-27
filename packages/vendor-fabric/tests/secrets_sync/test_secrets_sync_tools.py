"""Tests for SecretSync provider tool adapters."""

from __future__ import annotations

import importlib

from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("extended_data")
pytest.importorskip("vendor_fabric.secrets_sync")

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data

from vendor_fabric.secrets_sync import ConfigInfo, SyncOptions, SyncResult
from vendor_fabric.secrets_sync.tools import (
    TOOL_DEFINITIONS,
    RunPipelineSchema,
    build_langchain_tools,
    dry_run,
    get_config_info,
    get_crewai_tool_decorator,
    get_crewai_tools,
    get_langchain_tools,
    get_sources,
    get_strands_tools,
    get_targets,
    get_tools,
    is_available,
    raise_unknown_tool_framework,
    run_pipeline,
    validate_config,
)


@patch("vendor_fabric.secrets_sync.tools.native_run_pipeline")
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


@patch("vendor_fabric.secrets_sync.tools.native_run_pipeline")
def test_run_pipeline_tool_can_disable_continue_on_error(mock_run_pipeline: MagicMock) -> None:
    mock_run_pipeline.return_value = SyncResult(success=True).to_dict()

    run_pipeline("config.yaml", continue_on_error=False)

    options = mock_run_pipeline.call_args.args[1]
    assert isinstance(options, SyncOptions)
    assert options.continue_on_error is False


def test_run_pipeline_schema_default_continue_on_error_matches_cli() -> None:
    schema = RunPipelineSchema(config_path="config.yaml")

    assert schema.continue_on_error is True


@patch("vendor_fabric.secrets_sync.tools.native_validate_config")
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


@patch("vendor_fabric.secrets_sync.tools.native_validate_config")
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


@patch("vendor_fabric.secrets_sync.tools.native_dry_run")
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


@patch("vendor_fabric.secrets_sync.tools.native_run_pipeline")
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


@patch("vendor_fabric.secrets_sync.tools.native_dry_run")
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


@patch("vendor_fabric.secrets_sync.tools.native_get_config_info")
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


@patch("vendor_fabric.secrets_sync.tools.SecretSyncConfig.from_file")
def test_get_targets_tool_returns_extended_payload(mock_from_file: MagicMock) -> None:
    mock_from_file.return_value = MagicMock(targets={"prod": object(), "dev": object()})

    result = get_targets("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["targets"], ExtendedList)
    assert isinstance(result["targets"][0], ExtendedString)
    assert result["count"] == 2


@patch("vendor_fabric.secrets_sync.tools.SecretSyncConfig.from_file")
def test_get_sources_tool_returns_extended_payload(mock_from_file: MagicMock) -> None:
    mock_from_file.return_value = MagicMock(sources={"vault/prod": object()})

    result = get_sources("config.yaml")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["sources"], ExtendedList)
    assert isinstance(result["sources"][0], ExtendedString)
    assert result["count"] == 1


def test_tools_redact_errors_when_listing_targets_or_sources() -> None:
    """Target/source helper errors should be redacted in payloads."""
    with patch(
        "vendor_fabric.secrets_sync.tools.SecretSyncConfig.from_file",
        side_effect=RuntimeError("password=hunter2 Authorization: Bearer raw"),
    ):
        targets = get_targets("config.yaml")
        sources = get_sources("config.yaml")

    assert targets["targets"] == []
    assert sources["sources"] == []
    assert "hunter2" not in targets["error_message"]
    assert "raw" not in sources["error_message"]
    assert "[REDACTED]" in targets["error_message"]
    assert "[REDACTED]" in sources["error_message"]


def test_is_available_reports_importability(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_available should translate import errors into false."""
    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "missing_package":
            raise ImportError(name)
        return real_import_module("json")

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.importlib.import_module", fake_import_module)

    assert is_available("json") is True
    assert is_available("missing_package") is False


def test_build_langchain_tools_requires_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    """LangChain tool building should provide install guidance when unavailable."""

    def missing_langchain(name: str):
        if name == "langchain_core.tools":
            raise ImportError(name)
        return importlib.import_module(name)

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.importlib.import_module", missing_langchain)

    with pytest.raises(ImportError, match=r"vendor-fabric\[langchain,secrets-sync\]"):
        build_langchain_tools(TOOL_DEFINITIONS)


def test_get_crewai_tool_decorator_requires_crewai(monkeypatch: pytest.MonkeyPatch) -> None:
    """CrewAI imports should fail with actionable install guidance."""

    def missing_crewai(name: str):
        if name == "crewai.tools":
            raise ImportError(name)
        return importlib.import_module(name)

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.importlib.import_module", missing_crewai)

    with pytest.raises(ImportError, match=r"vendor-fabric\[crewai,secrets-sync\]"):
        get_crewai_tool_decorator()


def test_get_crewai_tool_decorator_requires_tool_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    """CrewAI modules without a tool decorator should fail clearly."""
    monkeypatch.setattr(
        "vendor_fabric.secrets_sync.tools.importlib.import_module",
        lambda name: MagicMock(spec=[]),
    )

    with pytest.raises(ImportError, match="does not expose it"):
        get_crewai_tool_decorator()


def test_crewai_tools_attach_description_and_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """CrewAI wrappers should retain description and args schema metadata."""

    class WrappedTool:
        pass

    def fake_tool(name: str):
        def decorate(func):
            wrapped = WrappedTool()
            wrapped.name = name
            wrapped.func = func
            return wrapped

        return decorate

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.get_crewai_tool_decorator", lambda: fake_tool)

    tools = get_crewai_tools()

    assert len(tools) == len(TOOL_DEFINITIONS)
    assert tools[0].name == TOOL_DEFINITIONS[0]["name"]
    assert tools[0].description == TOOL_DEFINITIONS[0]["description"]
    assert tools[0].args_schema is TOOL_DEFINITIONS[0]["schema"]


def test_framework_tool_getters_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tool factories should dispatch explicit and auto-selected frameworks."""
    langchain_tools = [object()]
    crewai_tools = [object()]
    strands_tools = get_strands_tools()

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.get_langchain_tools", lambda: langchain_tools)
    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.get_crewai_tools", lambda: crewai_tools)
    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.is_available", lambda package: package == "crewai")

    assert get_tools("strands") == strands_tools
    assert get_tools("langchain") is langchain_tools
    assert get_tools("crewai") is crewai_tools
    assert get_tools("auto") is crewai_tools

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.is_available", lambda package: package == "langchain_core")
    assert get_tools("auto") is langchain_tools

    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.is_available", lambda package: False)
    assert get_tools("auto") == strands_tools


def test_unknown_framework_errors_are_redacted() -> None:
    """Unknown framework diagnostics should not echo secret-looking values."""
    with pytest.raises(ValueError) as exc_info:
        raise_unknown_tool_framework("password=hunter2 Authorization: Bearer raw")

    message = str(exc_info.value)
    assert "hunter2" not in message
    assert "raw" not in message
    assert "[REDACTED]" in message


def test_get_langchain_tools_delegates_to_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_langchain_tools should pass public definitions to the builder."""
    expected = [object()]
    build = MagicMock(return_value=expected)
    monkeypatch.setattr("vendor_fabric.secrets_sync.tools.build_langchain_tools", build)

    assert get_langchain_tools() is expected
    build.assert_called_once_with(TOOL_DEFINITIONS)
