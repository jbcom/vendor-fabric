"""Tests for the SecretSync gopy binding adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.secrets_sync import _binding
from vendor_fabric.secrets_sync.models import OutputFormat, ProviderSession, SyncOperation, SyncOptions


class FakeBinding:
    """Small fake of the gopy-generated secrets_sync module."""

    def __init__(self) -> None:
        self.method = ""
        self.options = None
        self.session = None

    def DefaultSyncOptions(self) -> SimpleNamespace:
        return SimpleNamespace(
            DryRun=False,
            Operation="pipeline",
            Targets="",
            ContinueOnError=True,
            Parallelism=4,
            ComputeDiff=False,
            OutputFormat="human",
            ShowValues=False,
        )

    def NewProviderSession(self) -> SimpleNamespace:
        return SimpleNamespace(
            DelegateAuth=False,
            VaultAddress="",
            VaultNamespace="",
            VaultToken="",
            AWSRegion="",
            AWSAccessKeyID="",
            AWSSecretAccessKey="",
            AWSSessionToken="",
            AWSRoleARN="",
            AWSEndpointURL="",
        )

    def ValidateConfig(self, config_path: str) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        return SimpleNamespace(Valid=False, Message="invalid password=hunter2", ErrorMessage="invalid password=hunter2")

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
        self.method = "RunPipeline"
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

    def RunPipelineWithSession(self, config_path: str, options: object, session: object) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        self.method = "RunPipelineWithSession"
        self.options = options
        self.session = session
        return SimpleNamespace(Success=True, TargetCount=1, ResultsJSON="[]")

    def GetTargets(self, config_path: str) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        return SimpleNamespace(Success=True, Values=["prod", "dev"], ErrorMessage="")

    def GetSources(self, config_path: str) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        return SimpleNamespace(Success=True, Values=["base"], ErrorMessage="")

    def DryRun(self, config_path: str) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        self.method = "DryRun"
        return SimpleNamespace(Success=True, TargetCount=1, DiffOutput="diff")

    def DryRunWithSession(self, config_path: str, session: object) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        self.method = "DryRunWithSession"
        self.session = session
        return SimpleNamespace(Success=True, TargetCount=1, DiffOutput="diff")

    def Merge(self, config_path: str, dry_run: bool) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        assert dry_run is True
        self.method = "Merge"
        return SimpleNamespace(Success=True, TargetCount=1)

    def MergeWithSession(self, config_path: str, dry_run: bool, session: object) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        assert dry_run is True
        self.method = "MergeWithSession"
        self.session = session
        return SimpleNamespace(Success=True, TargetCount=1)

    def Sync(self, config_path: str, dry_run: bool) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        assert dry_run is False
        self.method = "Sync"
        return SimpleNamespace(Success=True, TargetCount=1)

    def SyncWithSession(self, config_path: str, dry_run: bool, session: object) -> SimpleNamespace:
        assert config_path == "pipeline.yaml"
        assert dry_run is False
        self.method = "SyncWithSession"
        self.session = session
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
            show_values=False,
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

    def GetTargets(self, config_path: str) -> dict[str, object]:
        assert config_path == "pipeline.yaml"
        return {"targets": ["dev"], "error_message": ""}

    def GetSources(self, config_path: str) -> tuple[None, str]:
        assert config_path == "pipeline.yaml"
        return None, "failed password=hunter2"


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
            show_values=True,
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
    assert fake.options.ShowValues is True


def test_binding_adapter_passes_provider_session_to_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider-owned auth material should flow through the session-aware binding API."""
    fake = FakeBinding()
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: fake if name == "secrets_sync" else None)

    result = _binding.run_pipeline(
        "pipeline.yaml",
        SyncOptions(dry_run=True),
        ProviderSession(
            vault_address="https://vault.example.test",
            vault_namespace="platform",
            vault_token="vault-token-secret",
            aws_region="us-east-1",
            aws_access_key_id="AKIAEXAMPLE",
            aws_secret_access_key="aws-secret",
            aws_session_token="aws-session",
            aws_role_arn="arn:aws:iam::123456789012:role/SecretSync",
            aws_endpoint_url="http://localhost:4566",
        ),
    )

    assert result["success"] is True
    assert fake.method == "RunPipelineWithSession"
    assert fake.options.DryRun is True
    assert fake.session.VaultAddress == "https://vault.example.test"
    assert fake.session.VaultNamespace == "platform"
    assert fake.session.VaultToken == "vault-token-secret"
    assert fake.session.AWSRegion == "us-east-1"
    assert fake.session.AWSAccessKeyID == "AKIAEXAMPLE"
    assert fake.session.AWSSecretAccessKey == "aws-secret"
    assert fake.session.AWSSessionToken == "aws-session"
    assert fake.session.AWSRoleARN == "arn:aws:iam::123456789012:role/SecretSync"
    assert fake.session.AWSEndpointURL == "http://localhost:4566"


def test_binding_adapter_accepts_mapping_provider_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider session payloads may be supplied as redaction-safe mappings."""
    fake = FakeBinding()
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: fake if name == "secrets_sync" else None)

    result = _binding.dry_run(
        "pipeline.yaml",
        {
            "delegate_auth": True,
            "vault_address": "https://vault.example.test",
            "aws_region": "us-west-2",
        },
    )

    assert result["success"] is True
    assert fake.method == "DryRunWithSession"
    assert fake.session.DelegateAuth is True
    assert fake.session.VaultAddress == "https://vault.example.test"
    assert fake.session.AWSRegion == "us-west-2"


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
    assert fake.options.show_values is False
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


def test_binding_adapter_exposes_target_and_source_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: FakeBinding() if name == "secrets_sync" else None)

    targets = _binding.get_targets("pipeline.yaml")
    sources = _binding.get_sources("pipeline.yaml")

    assert targets["targets"] == ["dev", "prod"]
    assert targets["count"] == 2
    assert targets["valid"] is True
    assert sources["sources"] == ["base"]


def test_binding_adapter_redacts_target_source_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_binding.importlib, "import_module", lambda name: SnakeCaseBinding() if name == "secrets_sync" else None)

    targets = _binding.get_targets("pipeline.yaml")
    sources = _binding.get_sources("pipeline.yaml")

    assert targets["targets"] == ["dev"]
    assert sources["sources"] == []
    assert sources["valid"] is False
    assert "hunter2" not in sources["error_message"]
    assert "[REDACTED]" in sources["error_message"]


def test_binding_adapter_preserves_failure_only_name_list_errors() -> None:
    """Failure-only binding payloads should not be coerced into fake names."""
    mapping_payload = _binding._name_list_to_dict(
        {"success": False, "error_message": "failed password=hunter2"},
        "targets",
        "pipeline.yaml",
    )
    object_payload = _binding._name_list_to_dict(
        SimpleNamespace(Success=False, ErrorMessage="failed token=tok_123"),
        "sources",
        "pipeline.yaml",
    )

    assert mapping_payload["targets"] == []
    assert mapping_payload["valid"] is False
    assert "hunter2" not in mapping_payload["error_message"]
    assert object_payload["sources"] == []
    assert object_payload["valid"] is False
    assert "tok_123" not in object_payload["error_message"]


def test_binding_adapter_preserves_success_validation_message() -> None:
    valid, message = _binding._validation_result(SimpleNamespace(Valid=True, Message="configuration is valid"))

    assert valid is True
    assert message == "configuration is valid"


def test_binding_adapter_treats_plain_name_lists_as_names() -> None:
    payload = _binding._name_list_to_dict(["dev", "prod"], "targets", "pipeline.yaml")

    assert payload["targets"] == ["dev", "prod"]
    assert payload["valid"] is True
    assert payload["error_message"] == ""


def test_binding_adapter_coerces_scalar_name_results() -> None:
    string_payload = _binding._name_list_to_dict("prod", "targets", "pipeline.yaml")
    scalar_payload = _binding._name_list_to_dict(123, "sources", "pipeline.yaml")

    assert string_payload["targets"] == ["prod"]
    assert scalar_payload["sources"] == ["123"]


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
