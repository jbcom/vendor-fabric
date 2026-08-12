"""Tests for unified CLI."""

from __future__ import annotations

import argparse
import json
import os

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict

from vendor_fabric import cli as cli_module
from vendor_fabric.cli import cmd_call, cmd_info, cmd_list, cmd_methods, main


class ExampleConnector:
    """Tiny connector shell for CLI call-surface tests."""

    def fetch(
        self,
        enabled: bool = False,
        count: int = 0,
        metadata: dict[str, object] | None = None,
        email: str | None = None,
    ) -> ExtendedDict:
        """Fetch example data."""
        return ExtendedDict({"enabled": enabled, "count": count, "metadata": metadata, "email": email})

    def secrets(self) -> ExtendedDict:
        """Fetch example sensitive data."""
        return ExtendedDict(
            {
                "password": "hunter2",
                "access_token": "tok_123",
                "id_token": 12345,
                "nested": {"api_key": "key_456"},
                "ok": True,
            }
        )

    def update_password(self, password: str) -> ExtendedDict:
        """Update an example password."""
        return ExtendedDict({"updated": bool(password)})


def test_cli_list() -> None:
    """Test the list command."""
    args = argparse.Namespace(json=False, available_only=False, category=None, capability=None)
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_list(args)
        assert exit_code == 0
        mock_write.assert_called()
        # Verify it lists some connectors
        output = "".join(call.args[0] for call in mock_write.call_args_list if call.args)
        assert "aws" in output
        assert "google" in output
        assert "category" in output
        assert "capabilities" in output
        assert "cloud" in output


def test_cli_list_json() -> None:
    """List command can emit machine-readable connector metadata."""
    args = argparse.Namespace(json=True, available_only=False, category=None, capability=None)
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_list(args)

    assert exit_code == 0
    output = mock_write.call_args.args[0]
    assert '"name": "github"' in output
    assert '"available":' in output
    assert '"category": "development"' in output
    assert '"capabilities":' in output
    assert "api_key_env" not in output


def test_cli_list_filters_by_category() -> None:
    """List command can filter the connector catalog by category."""
    args = argparse.Namespace(json=False, available_only=False, category="cloud", capability=None)
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_list(args)

    assert exit_code == 0
    output = "".join(call.args[0] for call in mock_write.call_args_list if call.args)
    assert "aws" in output
    assert "google" in output
    assert "github" not in output


def test_cli_list_filters_by_capability_json() -> None:
    """List command can emit capability-filtered connector metadata."""
    args = argparse.Namespace(json=True, available_only=False, category=None, capability="repositories")
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_list(args)

    assert exit_code == 0
    entries = json.loads(mock_write.call_args.args[0])
    names = {entry["name"] for entry in entries}
    assert "github" in names
    assert "cursor" in names
    assert "aws" not in names


def test_cli_list_intersects_category_and_capability_filters() -> None:
    """Category and capability filters should narrow the same catalog result."""
    args = argparse.Namespace(json=True, available_only=False, category="ai", capability="repositories")
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_list(args)

    assert exit_code == 0
    entries = json.loads(mock_write.call_args.args[0])
    assert [entry["name"] for entry in entries] == ["cursor"]


def test_cli_info() -> None:
    """Info command prints connector metadata."""
    args = argparse.Namespace(connector=" github ", json=False)
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_info(args)

    assert exit_code == 0
    output = "".join(call.args[0] for call in mock_write.call_args_list if call.args)
    assert "name: github" in output
    assert "category: development" in output
    assert "capabilities: repositories, teams, files, graphql, workflows" in output
    assert "install: pip install vendor-fabric[github]" in output


def test_cli_methods_lists_public_methods() -> None:
    """Methods command prints public data methods with descriptions."""
    args = argparse.Namespace(connector="meshy")
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_methods(args)

    assert exit_code == 0
    output = "".join(call.args[0] for call in mock_write.call_args_list if call.args)
    assert "text3d_generate" in output
    assert "request_data" not in output
    assert "decode_response" not in output


def test_cli_methods_json_lists_public_methods() -> None:
    """Methods command can emit machine-readable data-method metadata."""
    args = argparse.Namespace(connector="meshy", json=True)
    with patch("sys.stdout.write") as mock_write:
        exit_code = cmd_methods(args)

    assert exit_code == 0
    methods = json.loads(mock_write.call_args.args[0])
    method_names = {method["name"] for method in methods}
    assert "text3d_generate" in method_names
    assert "request_data" not in method_names


def test_readme_documents_every_connector_command() -> None:
    """The package README should enumerate the complete CLI data surface."""
    readme_lines = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").splitlines()
    command_section = readme_lines[readme_lines.index("### Connector commands") :]

    for connector_name in sorted(cli_module.BUILTIN_CONNECTORS):
        row_prefix = f"| `{connector_name}` |"
        command_row = next(line for line in command_section if line.startswith(row_prefix))
        connector_class = cli_module._surface_connector_class(connector_name)
        missing = [
            method_name
            for method_name, _ in cli_module.connector_data_methods(connector_class)
            if f"`{method_name}`" not in command_row
        ]
        assert missing == [], f"{connector_name} commands missing from README: {missing}"


def test_cli_methods_include_argument_signatures_without_installed_extra(capsys) -> None:
    """Built-in method discovery should not require its optional SDK extra."""
    with patch("vendor_fabric.cli.get_connector_class", side_effect=ImportError("missing github SDK")):
        exit_code = main(["methods", "github", "--json"])

    assert exit_code == 0
    methods = json.loads(capsys.readouterr().out)
    list_repositories = next(method for method in methods if method["name"] == "list_repositories")
    assert "type_filter" in list_repositories["signature"]
    assert "include_branches" in list_repositories["signature"]


def test_cli_credentials_reports_names_without_values(monkeypatch, capsys) -> None:
    """Credential discovery should never inspect or print credential values."""
    monkeypatch.setenv("GITHUB_TOKEN", "private-token-value")
    monkeypatch.setenv("GITHUB_OWNER", "example-org")

    exit_code = main(["credentials", "github", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "connector": "github",
            "required": ["GITHUB_TOKEN", "GITHUB_OWNER"],
            "optional": ["GITHUB_REPO", "GITHUB_BRANCH"],
            "notes": [],
        }
    ]
    assert "private-token-value" not in json.dumps(payload)
    assert "example-org" not in json.dumps(payload)


def test_cli_credentials_lists_aws_default_chain(capsys) -> None:
    """AWS credential help should preserve the boto3 default-chain convention."""
    exit_code = main(["credentials", "aws", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["required"] == []
    assert payload[0]["optional"] == ["EXECUTION_ROLE_ARN", "ROLE_SESSION_NAME"]
    assert payload[0]["notes"] == ["Uses the standard boto3 credential and config chain."]


def test_cli_call_parses_dynamic_keyword_arguments() -> None:
    """Call command accepts documented --arg value pairs after the method."""
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}

    with (
        patch("sys.argv", ["vendor-fabric", "call", "example", "fetch", "--enabled", "true", "--count", "3"]),
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write") as mock_write,
    ):
        exit_code = main()

    assert exit_code == 0
    connector.fetch.assert_called_once_with(enabled=True, count=3)
    output = "".join(call.args[0] for call in mock_write.call_args_list if call.args)
    assert '"ok": true' in output


def test_cli_call_accepts_json_flag_after_method() -> None:
    """Call command treats trailing --json as a CLI flag, not a method kwarg."""
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}
    args = argparse.Namespace(connector="example", method="fetch", extra=["--json"], json=False)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    connector.fetch.assert_called_once_with()
    assert '"ok": true' in mock_write.call_args.args[0]


@pytest.mark.parametrize(
    "connector_name",
    ["anthropic", "aws", "cursor", "github", "google", "jules", "meshy", "slack", "vault", "zoom"],
)
def test_cli_provider_alias_calls_connector_method(connector_name, monkeypatch) -> None:
    """Each built-in connector name should be a direct alias for call."""
    monkeypatch.setenv("GITHUB_OWNER", "example-org")
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write") as mock_write,
    ):
        exit_code = main([connector_name, "fetch", "--enabled", "true"])

    assert exit_code == 0
    connector.fetch.assert_called_once_with(enabled=True)
    assert '"ok": true' in mock_write.call_args.args[0]


def test_cli_routes_secrets_sync_through_unified_entrypoint() -> None:
    """The unified CLI should delegate SecretSync arguments unchanged."""
    with patch("vendor_fabric.secrets_sync.cli.main", return_value=2) as secrets_main:
        exit_code = main(["secrets-sync", "pipeline", "--config", "pipeline.yaml", "--dry-run"])

    assert exit_code == 2
    secrets_main.assert_called_once_with(["pipeline", "--config", "pipeline.yaml", "--dry-run"])


def test_cli_routes_secrets_sync_help_through_standalone_parser() -> None:
    """Unified help should retain the standalone SecretSync command help."""
    with patch("vendor_fabric.secrets_sync.cli.main", return_value=0) as secrets_main:
        exit_code = main(["secrets-sync", "--help"])

    assert exit_code == 0
    secrets_main.assert_called_once_with(["--help"])


def test_cli_call_reads_argument_from_environment(monkeypatch) -> None:
    """Method payloads can be sourced from an environment variable."""
    monkeypatch.setenv("EXAMPLE_METADATA", '{"service":{"name":"api"}}')
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}
    args = argparse.Namespace(
        connector="example",
        method="fetch",
        extra=["--metadata-env", "EXAMPLE_METADATA"],
        json=False,
    )

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write"),
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    connector.fetch.assert_called_once_with(metadata={"service": {"name": "api"}})


def test_cli_call_reads_argument_from_file(tmp_path) -> None:
    """Method payloads can be sourced from a file."""
    payload_path = tmp_path / "metadata.json"
    payload_path.write_text('{"service":{"name":"api"}}')
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}
    args = argparse.Namespace(
        connector="example",
        method="fetch",
        extra=["--metadata-file", os.fspath(payload_path)],
        json=False,
    )

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write"),
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    connector.fetch.assert_called_once_with(metadata={"service": {"name": "api"}})


def test_cli_call_reads_sensitive_argument_from_stdin() -> None:
    """Sensitive values can be supplied without placing them in argv."""
    connector = MagicMock()
    connector.update_password.return_value = {"updated": True}
    args = argparse.Namespace(
        connector="example",
        method="update_password",
        extra=["--password-stdin"],
        json=False,
    )

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdin.read", return_value="safely-piped-value\n"),
        patch("sys.stdout.write"),
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    connector.update_password.assert_called_once_with(password="safely-piped-value")


def test_cli_call_rejects_sensitive_literal_argument() -> None:
    """Sensitive values must not be accepted directly from shell argv."""
    args = argparse.Namespace(
        connector="example",
        method="update_password",
        extra=["--password", "visible-in-history"],
        json=False,
    )

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector") as get_connector_mock,
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    get_connector_mock.assert_not_called()
    output = mock_write.call_args.args[0]
    assert "visible-in-history" not in output
    assert "--password-env" in output
    assert "--password-file" in output
    assert "--password-stdin" in output


def test_cli_call_rejects_unexpected_positional_argument() -> None:
    """Stray positional values should fail instead of being silently ignored."""
    args = argparse.Namespace(connector="example", method="fetch", extra=["unexpected"], json=False)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector") as get_connector_mock,
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    get_connector_mock.assert_not_called()
    assert "Unexpected positional argument" in mock_write.call_args.args[0]


def test_cli_call_validates_method_arguments_before_connector_creation() -> None:
    """Missing required method arguments should produce a CLI usage error."""
    args = argparse.Namespace(connector="example", method="update_password", extra=[], json=False)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector") as get_connector_mock,
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    get_connector_mock.assert_not_called()
    assert "password" in mock_write.call_args.args[0]


def test_cli_call_sources_github_connector_configuration_from_environment(monkeypatch) -> None:
    """GitHub's required owner should follow the existing fabric env pattern."""
    monkeypatch.setenv("GITHUB_OWNER", "example-org")
    monkeypatch.setenv("GITHUB_REPO", "example-repo")
    monkeypatch.setenv("GITHUB_BRANCH", "develop")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-be-forwarded")
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}
    args = argparse.Namespace(connector="github", method="fetch", extra=[], json=False)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector) as get_connector_mock,
        patch("sys.stdout.write"),
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    get_connector_mock.assert_called_once_with(
        "github",
        github_owner="example-org",
        github_repo="example-repo",
        github_branch="develop",
    )


def test_cli_call_requires_github_owner_environment(monkeypatch) -> None:
    """GitHub calls should explain the required non-secret connector context."""
    monkeypatch.delenv("GITHUB_OWNER", raising=False)
    args = argparse.Namespace(connector="github", method="fetch", extra=[], json=False)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector") as get_connector_mock,
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    get_connector_mock.assert_not_called()
    assert "GITHUB_OWNER" in mock_write.call_args.args[0]


def test_cli_call_serializes_extended_containers_as_data() -> None:
    """Call command renders Tier 2 containers as JSON data, not iterable keys."""
    connector = MagicMock()
    connector.fetch.return_value = ExtendedDict({"service": {"name": "api"}})
    args = argparse.Namespace(connector="example", method="fetch", extra=[], json=True)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch(
            "vendor_fabric.cli.wrap_raw_data_for_export", wraps=cli_module.wrap_raw_data_for_export
        ) as mock_wrap_for_export,
        patch("sys.stdout.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    assert json.loads(mock_write.call_args.args[0]) == {"service": {"name": "api"}}
    mock_wrap_for_export.assert_called_once()
    assert mock_wrap_for_export.call_args.kwargs == {"allow_encoding": "json", "indent_2": True, "default": str}


def test_cli_call_redacts_sensitive_json_output() -> None:
    """Call command should not write common secret fields to stdout."""
    connector = MagicMock()
    connector.secrets.return_value = ExampleConnector().secrets()
    args = argparse.Namespace(connector="example", method="secrets", extra=[], json=True)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    output = mock_write.call_args.args[0]
    assert "hunter2" not in output
    assert "tok_123" not in output
    assert "12345" not in output
    assert "key_456" not in output
    assert json.loads(output)["id_token"] == "[REDACTED]"
    assert '"password": "[REDACTED]"' in output
    assert '"access_token": "[REDACTED]"' in output
    assert '"api_key": "[REDACTED]"' in output


def test_cli_call_reports_missing_method() -> None:
    """Call command reports missing methods instead of failing silently."""
    args = argparse.Namespace(connector="example", method="missing", extra=[], json=False)
    connector = object()

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    assert "has no exposed data method" in mock_write.call_args.args[0]


def test_cli_call_rejects_raw_connector_helpers() -> None:
    """Call command should not expose raw/base helpers at the serialization boundary."""
    args = argparse.Namespace(connector="meshy", method="request_data", extra=[], json=False)

    with patch("sys.stderr.write") as mock_write:
        exit_code = cmd_call(args)

    assert exit_code == 1
    assert "has no exposed data method" in mock_write.call_args.args[0]


def test_cli_call_reports_connector_errors() -> None:
    """Call command writes connector errors to stderr."""
    args = argparse.Namespace(connector="example", method="fetch", extra=[], json=False)

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", side_effect=RuntimeError("boom")),
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    assert "boom" in mock_write.call_args.args[0]


def test_cli_call_redacts_sensitive_error_output() -> None:
    """Call command should sanitize common secret values in stderr."""
    args = argparse.Namespace(connector="example", method="fetch", extra=[], json=False)
    error = RuntimeError("failed password=hunter2 token: tok_123 Authorization: Bearer raw_token")

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", side_effect=error),
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    output = mock_write.call_args.args[0]
    assert "hunter2" not in output
    assert "tok_123" not in output
    assert "raw_token" not in output
    assert "password=[REDACTED]" in output
    assert "token: [REDACTED]" in output
    assert "Authorization: [REDACTED]" in output


def test_cli_call_redacts_explicit_argument_values_from_errors() -> None:
    """Call command should redact caller-provided resource context in stderr."""
    args = argparse.Namespace(
        connector="example",
        method="fetch",
        extra=[
            "--email",
            "private-user@example.com",
            "--metadata",
            '{"path": "/tmp/private/path", "prompt": "Fix login"}',
        ],
        json=False,
    )
    connector = MagicMock()
    connector.fetch.side_effect = RuntimeError(
        "failed for private-user@example.com at /tmp/private%2Fpath while handling Fix login"
    )

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = cmd_call(args)

    assert exit_code == 1
    connector.fetch.assert_called_once_with(
        email="private-user@example.com",
        metadata={"path": "/tmp/private/path", "prompt": "Fix login"},
    )
    output = mock_write.call_args.args[0]
    assert "private-user@example.com" not in output
    assert "/tmp/private%2Fpath" not in output
    assert "Fix login" not in output
    assert output.count("[REDACTED]") >= 3


@patch("vendor_fabric.cli.decode_file", wraps=cli_module.decode_file)
def test_cli_call_decodes_json_arguments_through_data_boundary(mock_decode_file: MagicMock) -> None:
    """Structured CLI method arguments should use the shared data decoder."""
    args = argparse.Namespace(
        connector="example",
        method="fetch",
        extra=["--metadata", '{"service": {"name": "api"}}'],
        json=False,
    )
    connector = MagicMock()
    connector.fetch.return_value = {"ok": True}

    with (
        patch("vendor_fabric.cli.get_connector_class", return_value=ExampleConnector),
        patch("vendor_fabric.cli.get_connector", return_value=connector),
        patch("sys.stdout.write"),
    ):
        exit_code = cmd_call(args)

    assert exit_code == 0
    connector.fetch.assert_called_once_with(metadata={"service": {"name": "api"}})
    mock_decode_file.assert_called_once_with('{"service": {"name": "api"}}', suffix="json", as_extended=False)


def test_cli_main_help() -> None:
    """Test main CLI entry point with help."""
    with patch("sys.argv", ["vendor-fabric", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


def test_cli_main_reports_unexpected_command_errors() -> None:
    """Connector CLI entrypoint should not collapse unexpected failures silently."""
    with (
        patch("sys.argv", ["vendor-fabric", "list"]),
        patch("vendor_fabric.cli.cmd_list", side_effect=RuntimeError("failed password=hunter2")),
        patch("sys.stderr.write") as mock_write,
    ):
        exit_code = main()

    assert exit_code == 1
    output = mock_write.call_args.args[0]
    assert "failed" in output
    assert "hunter2" not in output
    assert "password=[REDACTED]" in output
