"""Tests for the SecretSync binding facade CLI."""

from __future__ import annotations

import json

from unittest.mock import MagicMock, patch

from vendor_fabric.secrets_sync import cli
from vendor_fabric.secrets_sync.models import OutputFormat, SyncOperation, SyncOptions


def _stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_validate_command_writes_success_payload(capsys) -> None:
    """The validate subcommand should return zero for valid configs."""
    with patch.object(cli, "validate_config", return_value={"valid": True, "message": "ok"}) as validate:
        exit_code = cli.main(["validate", "--config", "config.yaml"])

    assert exit_code == 0
    assert _stdout_json(capsys)["valid"] is True
    validate.assert_called_once_with("config.yaml")


def test_validate_command_returns_validation_failure(capsys) -> None:
    """The validate subcommand should return two for invalid configs."""
    with patch.object(cli, "validate_config", return_value={"valid": False, "message": "bad"}):
        exit_code = cli.main(["validate", "--config", "config.yaml"])

    assert exit_code == 2
    assert _stdout_json(capsys)["message"] == "bad"


def test_info_command_writes_config_info(capsys) -> None:
    """The info subcommand should write the public config-info payload."""
    with patch.object(cli, "get_config_info", return_value={"valid": True, "sources": ["base"]}) as info:
        exit_code = cli.main(["info", "--config", "config.yaml"])

    assert exit_code == 0
    assert _stdout_json(capsys)["sources"] == ["base"]
    info.assert_called_once_with("config.yaml")


def test_pipeline_command_builds_sync_options(capsys) -> None:
    """The pipeline subcommand should translate CLI args into SyncOptions."""
    run_pipeline = MagicMock(return_value={"success": True})
    with patch.object(cli, "run_pipeline", run_pipeline):
        exit_code = cli.main(
            [
                "pipeline",
                "--config",
                "config.yaml",
                "--operation",
                "merge",
                "--target",
                "prod",
                "--target",
                "dev",
                "--dry-run",
                "--output",
                "human",
                "--parallelism",
                "2",
                "--no-continue-on-error",
            ]
        )

    assert exit_code == 0
    assert _stdout_json(capsys)["success"] is True
    options = run_pipeline.call_args.args[1]
    assert isinstance(options, SyncOptions)
    assert options.operation is SyncOperation.MERGE
    assert options.targets == ["prod", "dev"]
    assert options.dry_run is True
    assert options.compute_diff is True
    assert options.output_format is OutputFormat.HUMAN
    assert options.parallelism == 2
    assert options.continue_on_error is False


def test_pipeline_command_returns_failure_status(capsys) -> None:
    """The pipeline subcommand should return two when the run fails."""
    with patch.object(cli, "run_pipeline", return_value={"success": False, "error_message": "failed"}):
        exit_code = cli.main(["pipeline", "--config", "config.yaml"])

    assert exit_code == 2
    assert _stdout_json(capsys)["success"] is False


def test_main_redacts_unhandled_errors(capsys) -> None:
    """Unhandled CLI errors should be redacted before stderr output."""
    with patch.object(cli, "validate_config", side_effect=RuntimeError("password=hunter2 Authorization: Bearer raw")):
        exit_code = cli.main(["validate", "--config", "config.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "hunter2" not in captured.err
    assert "raw" not in captured.err
    assert "[REDACTED]" in captured.err


def test_module_entrypoint_reexports_main() -> None:
    """The module entrypoint should import the CLI main function."""
    import vendor_fabric.secrets_sync.__main__ as entrypoint

    assert entrypoint.main is cli.main
