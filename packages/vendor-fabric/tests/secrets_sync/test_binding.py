"""Tests for the SecretSync gopy binding adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.secrets_sync import _binding
from vendor_fabric.secrets_sync.models import OutputFormat, SyncOperation, SyncOptions


class FakeBinding:
    """Small fake of the gopy-generated secrets_sync module."""

    def __init__(self) -> None:
        self.options = None

    def DefaultSyncOptions(self) -> SimpleNamespace:
        return SimpleNamespace(
            DryRun=False,
            Operation="pipeline",
            Targets="",
            ContinueOnError=True,
            Parallelism=4,
            ComputeDiff=False,
            OutputFormat="human",
        )

    def ValidateConfig(self, config_path: str) -> tuple[bool, str]:
        assert config_path == "pipeline.yaml"
        return False, "invalid password=hunter2"

    def GetConfigInfo(self, config_path: str) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        return SimpleNamespace(
            Valid=True,
            ErrorMessage="",
            SourceCount=2,
            TargetCount=1,
            Sources=["base", "env"],
            Targets=["prod"],
            HasMergeStore=True,
            VaultAddress="https://vault.example.com",
            AWSRegion="us-east-1",
        )

    def RunPipeline(self, config_path: str, options: object) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        self.options = options
        return SimpleNamespace(
            Success=True,
            TargetCount=1,
            SecretsProcessed=3,
            SecretsAdded=1,
            SecretsModified=2,
            SecretsRemoved=0,
            SecretsUnchanged=4,
            DurationMs=25,
            ErrorMessage="",
            ResultsJSON='[{"target":"prod","secret":"password=hunter2"}]',
            DiffOutput="changed token=tok_123",
        )

    def DryRun(self, config_path: str) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        return SimpleNamespace(Success=True, TargetCount=1, DiffOutput="diff")

    def Merge(self, config_path: str, dry_run: bool) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        assert dry_run is True
        return SimpleNamespace(Success=True, TargetCount=1)

    def Sync(self, config_path: str, dry_run: bool) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        assert dry_run is False
        return SimpleNamespace(Success=True, TargetCount=1)


class SnakeCaseBinding(FakeBinding):
    """Fake a binding that exposes generated snake_case field aliases."""

    def DefaultSyncOptions(self) -> SimpleNamespace:
        return SimpleNamespace(
            dry_run=False,
            operation="pipeline",
            targets="",
            continue_on_error=True,
            parallelism=4,
            compute_diff=False,
            output_format="human",
        )

    def RunPipeline(self, config_path: str, options: object) -> dict[str, object]:
        assert config_path == "pipeline.yaml"
        self.options = options
        return {
            "success": True,
            "target_count": 1,
            "secrets_processed": 2,
            "results_json": '{"not":"a-list"}',
        }

    def GetConfigInfo(self, config_path: str) -> dict[str, object]:
        assert config_path == "pipeline.yaml"
        return {
            "valid": True,
            "source_count": 1,
            "target_count": 0,
            "sources": None,
            "targets": ["dev"],
        }


def test_binding_adapter_converts_options_and_redacts_results(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBinding()
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: fake if name == "secrets_sync" else None)

    result = _binding.run_pipeline(
        "pipeline.yaml",
        SyncOptions(
            operation=SyncOperation.MERGE,
            dry_run=True,
            targets=["prod", "dev"],
            continue_on_error=False,
            parallelism=2,
            compute_diff=True,
            output_format=OutputFormat.HUMAN,
        ),
    )

    assert isinstance(result, ExtendedDict)
    assert result["success"] is True
    assert result["secrets_processed"] == 3
    assert "hunter2" not in result["results"][0]["secret"]
    assert "tok_123" not in result["diff_output"]
    assert fake.options.DryRun is True
    assert fake.options.Operation == "merge"
    assert fake.options.Targets == "prod,dev"
    assert fake.options.ContinueOnError is False
    assert fake.options.Parallelism == 2
    assert fake.options.ComputeDiff is True
    assert fake.options.OutputFormat == "human"


def test_binding_adapter_supports_snake_case_options_and_mapping_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = SnakeCaseBinding()
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: fake if name == "secrets_sync" else None)

    result = _binding.run_pipeline(
        "pipeline.yaml",
        SyncOptions(
            operation=SyncOperation.SYNC,
            dry_run=True,
            targets=["dev"],
            parallelism=1,
            output_format=OutputFormat.JSON,
        ),
    )
    info = _binding.get_config_info("pipeline.yaml")

    assert result["success"] is True
    assert result["results"] == []
    assert fake.options.dry_run is True
    assert fake.options.operation == "sync"
    assert fake.options.targets == "dev"
    assert fake.options.parallelism == 1
    assert fake.options.output_format == "json"
    assert info["sources"] == []
    assert info["targets"] == ["dev"]


def test_binding_adapter_exposes_validate_and_config_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: FakeBinding() if name == "secrets_sync" else None)

    validation = _binding.validate_config("pipeline.yaml")
    info = _binding.get_config_info("pipeline.yaml")

    assert validation["valid"] is False
    assert "hunter2" not in validation["message"]
    assert isinstance(info, ExtendedDict)
    assert isinstance(info["sources"], ExtendedList)
    assert isinstance(info["sources"][0], ExtendedString)
    assert info["has_merge_store"] is True


def test_binding_adapter_phase_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: FakeBinding() if name == "secrets_sync" else None)

    assert _binding.dry_run("pipeline.yaml")["success"] is True
    assert _binding.merge("pipeline.yaml", dry_run=True)["success"] is True
    assert _binding.sync("pipeline.yaml", dry_run=False)["success"] is True


def test_binding_availability_and_default_options(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBinding()
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: fake if name == "secrets_sync" else None)

    assert _binding.BINDING_MODULE == "secrets_sync"
    assert _binding.is_binding_available() is True
    assert _binding.run_pipeline("pipeline.yaml")["success"] is True
    assert fake.options.Operation == "pipeline"
    assert _binding._operation_value("merge") == "merge"


def test_binding_availability_reports_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(_binding.importlib, "import_module", missing)

    assert _binding.is_binding_available() is False


def test_binding_adapter_ignores_malformed_results_json() -> None:
    invalid = _binding._sync_result_to_dict({"success": True, "results_json": "{not-json"})
    not_a_list = _binding._sync_result_to_dict({"success": True, "results_json": '{"ok": true}'})

    assert invalid["success"] is True
    assert not_a_list["success"] is True
    assert invalid["results"] == []
    assert not_a_list["results"] == []


def test_missing_binding_reports_install_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(_binding.importlib, "import_module", missing)

    with pytest.raises(ImportError, match="jbcom/secrets-sync"):
        _binding.load_binding()
