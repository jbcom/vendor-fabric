"""Tests for SecretSync configuration models."""

from __future__ import annotations

import pytest

from vendor_fabric.secrets_sync.models import (
    DynamicTarget,
    SecretSyncConfig,
    Target,
    TargetDiff,
    redacted_error,
)


def test_config_from_file_expands_env_and_applies_overrides(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config files should expand auth env vars and explicit env overrides."""
    config_path = tmp_path / "secrets-sync.yaml"
    config_path.write_text(
        """
vault:
  address: https://vault.from-file.example.com
  auth:
    approle:
      role_id: ${ROLE_ID}
      secret_id: ${SECRET_ID}
aws:
  region: us-west-2
  control_tower:
    enabled: true
    execution_role:
      name: SyncRole
      path: service-role
targets:
  prod:
    account_id: "123456789012"
    imports:
      - base
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ROLE_ID", "role-id")
    monkeypatch.setenv("SECRET_ID", "secret-id")
    monkeypatch.setenv("SECRETS_SYNC_LOG_LEVEL", "debug")
    monkeypatch.setenv("SECRETS_SYNC_AWS_REGION", "us-east-2")
    monkeypatch.setenv("SECRETS_SYNC_VAULT_ADDRESS", "https://vault.from-env.example.com")

    config = SecretSyncConfig.from_file(config_path)

    assert config.vault.auth.approle is not None
    assert config.vault.auth.approle.role_id == "role-id"
    assert config.vault.auth.approle.secret_id == "secret-id"
    assert config.log.level == "debug"
    assert config.aws.region == "us-east-2"
    assert config.vault.address == "https://vault.from-env.example.com"
    assert config.merge_store.vault is not None
    assert config.sources["base"].vault.mount == "base"
    assert config.role_arn_for_target(config.targets["prod"]) == "arn:aws:iam::123456789012:role/service-role/SyncRole"


def test_config_from_file_can_skip_environment_auto_detection(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """auto_detect=False should avoid environment overrides and auto merge-store setup."""
    config_path = tmp_path / "secrets-sync.yaml"
    config_path.write_text(
        """
vault:
  address: https://vault.from-file.example.com
targets:
  prod:
    imports:
      - base
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SECRETS_SYNC_VAULT_ADDRESS", "https://vault.from-env.example.com")

    config = SecretSyncConfig.from_file(config_path, auto_detect=False)

    assert config.vault.address == "https://vault.from-file.example.com"
    assert config.merge_store.vault is not None


def test_config_from_file_rejects_non_mapping_yaml(tmp_path) -> None:
    """SecretSync config files must decode to a mapping."""
    config_path = tmp_path / "secrets-sync.yaml"
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(TypeError, match="must be a mapping"):
        SecretSyncConfig.from_file(config_path)


def test_config_validation_errors_are_explicit() -> None:
    """Validation should reject missing targets, bad merge stores, account ids, and cycles."""
    with pytest.raises(ValueError, match="at least one target"):
        SecretSyncConfig.from_mapping({}).validate()

    with pytest.raises(ValueError, match=r"merge_store\.s3\.bucket"):
        SecretSyncConfig.from_mapping(
            {"merge_store": {"s3": {"prefix": "bundles"}}, "targets": {"prod": ["base"]}}
        ).validate()

    with pytest.raises(ValueError, match="invalid account_id"):
        SecretSyncConfig.from_mapping({"targets": {"prod": {"account_id": "not-an-account"}}}).validate()

    with pytest.raises(ValueError, match="self-reference"):
        SecretSyncConfig.from_mapping({"targets": {"prod": {"imports": ["prod"]}}}).validate()

    with pytest.raises(ValueError, match="a -> b -> a"):
        SecretSyncConfig.from_mapping({"targets": {"a": {"imports": ["b"]}, "b": {"imports": ["a"]}}}).validate()


def test_config_parses_optional_sections_and_source_paths() -> None:
    """Config parsing should cover dynamic targets, source paths, and role fallbacks."""
    config = SecretSyncConfig.from_mapping(
        {
            "log": {"format": "json"},
            "vault": {
                "namespace": "admin",
                "auth": {"token": {"token": "raw"}, "kubernetes": {"role": "sync"}},
                "max_traversal_depth": "3",
            },
            "aws": {
                "execution_context": {
                    "custom_role_pattern": "arn:aws:iam::{{.AccountID}}:role/CustomSync",
                }
            },
            "sources": {
                "vaulted": {"vault": {"mount": "secret", "paths": ("app", "shared")}},
                "awsed": {"aws": {"account_id": "123456789012", "tags": {"team": "platform"}}},
            },
            "merge_store": {"vault": {"mount": "merged"}},
            "targets": {
                "shared": ["vaulted"],
                "prod": {"account_id": "210987654321", "imports": "shared"},
            },
            "dynamic_targets": {
                "accounts": {
                    "imports": ["shared"],
                    "exclude": ["sandbox"],
                    "account_name_patterns": [{"pattern": "prod-*", "target": "prod"}],
                    "discovery": {"source": "organizations"},
                }
            },
            "pipeline": {"merge": {"parallel": "2"}, "sync": {"parallel": "3", "delete_orphans": True}},
        }
    )

    assert config.log.format == "json"
    assert config.vault.auth.token is not None
    assert config.vault.auth.kubernetes is not None
    assert config.vault.max_traversal_depth == 3
    assert config.sources["vaulted"].vault.paths == ["app", "shared"]
    assert config.sources["awsed"].aws.tags == {"team": "platform"}
    assert config.get_source_path("vaulted") == "secret"
    assert config.get_source_path("awsed") == "123456789012"
    assert config.get_source_path("shared") == "merged/targets/shared"
    assert config.get_source_path("missing") == "missing"
    assert config.role_arn_for_target(Target(account_id="210987654321")) == "arn:aws:iam::210987654321:role/CustomSync"
    assert config.pipeline.merge.parallel == 2
    assert config.pipeline.sync.parallel == 3
    assert config.pipeline.sync.delete_orphans is True
    assert isinstance(config.dynamic_targets["accounts"], DynamicTarget)
    assert config.dynamic_targets["accounts"].account_name_patterns[0].target == "prod"
    assert config.info().to_dict()["has_merge_store"] is True


def test_config_role_arn_explicit_and_empty_branches() -> None:
    """Explicit role ARNs should win and targets without account ids should be empty."""
    config = SecretSyncConfig.from_mapping({"targets": {"prod": {"imports": []}}})

    assert config.role_arn_for_target(Target(role_arn="arn:explicit")) == "arn:explicit"
    assert config.role_arn_for_target(Target()) == ""
    assert config.role_arn_for_target(Target(account_id="123456789012")) == ""


def test_target_diff_and_redacted_errors() -> None:
    """Small result helpers should expose change status and redact diagnostics."""
    assert TargetDiff("prod", "sync").has_changes is False
    assert TargetDiff("prod", "sync", added=["db"]).has_changes is True
    assert "hunter2" not in redacted_error(RuntimeError("password=hunter2 Authorization: Bearer raw"))
