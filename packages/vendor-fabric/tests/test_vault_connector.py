# ruff: noqa: I001
"""Tests for VaultConnector."""

from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("hvac")

from hvac.exceptions import VaultError

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from vendor_fabric.vault import VaultConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


class TestVaultConnector:
    """Test suite for VaultConnector."""

    def test_init(self, base_connector_kwargs):
        """Test initialization."""
        connector = VaultConnector(
            vault_url="https://vault.example.com",
            vault_namespace="test-namespace",
            vault_token="test-token",
            **base_connector_kwargs,
        )

        assert connector.vault_url == "https://vault.example.com"
        assert connector.vault_namespace == "test-namespace"
        assert connector.vault_token == "test-token"
        assert connector._vault_client is None

    @patch("vendor_fabric.vault.hvac.Client")
    def test_vault_client_with_token(self, mock_hvac_class, base_connector_kwargs):
        """Test getting vault client with token authentication."""
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.auth.token.lookup_self.return_value = {"data": {"expire_time": "2024-12-31T23:59:59Z"}}
        mock_hvac_class.return_value = mock_client

        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        client = connector.vault_client
        assert client == mock_client
        mock_hvac_class.assert_called()

    @patch("vendor_fabric.vault.hvac.Client")
    def test_vault_client_token_failure_redacts_without_traceback(self, mock_hvac_class, base_connector_kwargs):
        """Token client initialization failures should avoid traceback diagnostics."""
        mock_hvac_class.side_effect = VaultError("token failure test-token Authorization: Bearer raw_token")
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        with pytest.raises(RuntimeError, match="Vault authentication failed"):
            _ = connector.vault_client

        logs = _logged_text(connector.logger)
        assert "test-token" not in logs
        assert "raw_token" not in logs
        assert "[REDACTED]" in logs
        connector.logger.exception.assert_not_called()
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    @patch("vendor_fabric.vault.hvac.Client")
    def test_vault_client_approle_failure_redacts_without_raw_cause(self, mock_hvac_class, base_connector_kwargs):
        """AppRole authentication failures should raise a redacted RuntimeError."""
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        mock_client.auth.approle.login.side_effect = VaultError("approle failed role-raw secret-raw token=raw-token")
        mock_hvac_class.return_value = mock_client

        connector = VaultConnector(vault_url="https://vault.example.com", **base_connector_kwargs)

        def get_input(name, **kwargs):
            values = {
                "VAULT_NAMESPACE": None,
                "VAULT_TOKEN": None,
                "VAULT_APPROLE_PATH": "approle",
                "VAULT_ROLE_ID": "role-raw",
                "VAULT_SECRET_ID": "secret-raw",
            }
            return values.get(name, kwargs.get("default"))

        connector.get_input = MagicMock(side_effect=get_input)

        with pytest.raises(RuntimeError) as exc_info:
            _ = connector.vault_client

        diagnostics = _logged_text(connector.logger) + str(exc_info.value)
        assert "role-raw" not in diagnostics
        assert "secret-raw" not in diagnostics
        assert "raw-token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        connector.logger.exception.assert_not_called()
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    def test_is_token_valid(self, base_connector_kwargs):
        """Test token validity check."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        # No expiration set
        assert connector._is_token_valid() is False

        # Set future expiration
        connector._vault_token_expiration = datetime(2099, 12, 31, 23, 59, 59, tzinfo=UTC)
        assert connector._is_token_valid() is True

        # Set past expiration
        connector._vault_token_expiration = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert connector._is_token_valid() is False

    @patch("vendor_fabric.vault.hvac.Client")
    def test_get_vault_client_classmethod(self, mock_hvac_class, base_connector_kwargs):
        """Test class method for getting vault client."""
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.auth.token.lookup_self.return_value = {"data": {"expire_time": "2024-12-31T23:59:59Z"}}
        mock_hvac_class.return_value = mock_client

        client = VaultConnector.get_vault_client(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        assert client == mock_client

    def test_list_secrets_recurses_directories(self, base_connector_kwargs):
        """List secrets should traverse nested directories from root."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        kv_v2 = mock_client.secrets.kv.v2

        def list_side_effect(path, mount_point):
            listings = {
                "": {"data": {"keys": ["finance/", "shared"]}},
                "finance/": {"data": {"keys": ["prod/", "dev"]}},
                "finance/prod/": {"data": {"keys": ["db"]}},
            }
            return listings.get(path, {"data": {"keys": []}})

        kv_v2.list_secrets.side_effect = list_side_effect

        def read_side_effect(path, mount_point):
            data_map = {
                "shared": {"data": {"data": {"value": "shared"}}},
                "finance/dev": {"data": {"data": {"value": "dev"}}},
                "finance/prod/db": {"data": {"data": {"value": "db"}}},
            }
            if path not in data_map:
                raise VaultError(f"missing {path}")
            return data_map[path]

        kv_v2.read_secret_version.side_effect = read_side_effect

        secrets = connector.list_secrets()

        assert isinstance(secrets, ExtendedDict)
        assert isinstance(secrets["shared"], ExtendedDict)
        assert isinstance(secrets["shared"]["value"], ExtendedString)
        assert secrets == {
            "shared": {"value": "shared"},
            "finance/dev": {"value": "dev"},
            "finance/prod/db": {"value": "db"},
        }
        assert kv_v2.list_secrets.call_args_list[0].kwargs["path"] == ""

    def test_list_secrets_handles_invalid_root(self, base_connector_kwargs):
        """Invalid root paths should return an empty dict instead of raising."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.kv.v2.list_secrets.side_effect = VaultError("invalid")

        secrets = connector.list_secrets(root_path="does/not/exist")

        assert isinstance(secrets, ExtendedDict)
        assert secrets == {}
        mock_client.secrets.kv.v2.list_secrets.assert_called_once_with(
            path="does/not/exist",
            mount_point="secret",
        )

    def test_list_secrets_redacts_vault_error_logs(self, base_connector_kwargs):
        """Vault list failures should not log raw secret-bearing exception text."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)
        mock_client.secrets.kv.v2.list_secrets.side_effect = VaultError(
            "denied password=hunter2 Authorization: Bearer raw_token"
        )

        secrets = connector.list_secrets(root_path="does/not/exist")

        logs = _logged_text(connector.logger)
        assert secrets == {}
        assert "does/not/exist" not in logs
        assert "hunter2" not in logs
        assert "raw_token" not in logs
        assert "[REDACTED]" in logs

    def test_list_secrets_rejects_path_traversal(self, base_connector_kwargs):
        """Ensure list_secrets rejects path traversal in root_path."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        # Should reject path traversal attempts
        with pytest.raises(ValueError, match="invalid characters"):
            connector.list_secrets(root_path="../../../etc/passwd")

        with pytest.raises(ValueError, match="invalid characters"):
            connector.list_secrets(root_path="secrets/../admin")

        # Should reject null bytes
        with pytest.raises(ValueError, match="invalid characters"):
            connector.list_secrets(root_path="secrets\x00admin")

    def test_list_aws_iam_roles_filters_prefix(self, base_connector_kwargs):
        """Ensure AWS IAM roles can be listed and filtered by prefix."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.aws.list_roles.return_value = {"data": {"keys": ["prod-sync", "dev-sync"]}}

        roles = connector.list_aws_iam_roles(prefix="prod")

        assert isinstance(roles, ExtendedList)
        assert isinstance(roles[0], ExtendedString)
        assert roles == ["prod-sync"]
        mock_client.secrets.aws.list_roles.assert_called_once_with(mount_point="aws")

    def test_list_aws_iam_roles_does_not_preserve_name_prefix_alias(self, base_connector_kwargs):
        """Clean major-version surface should not preserve the old name_prefix keyword."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        with pytest.raises(TypeError, match="name_prefix"):
            connector.list_aws_iam_roles(name_prefix="prod")  # type: ignore[call-arg]

    def test_list_aws_iam_roles_handles_errors(self, base_connector_kwargs):
        """Vault errors while listing roles should return an empty list."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.aws.list_roles.side_effect = VaultError("boom")

        roles = connector.list_aws_iam_roles()

        assert isinstance(roles, ExtendedList)
        assert roles == []

    def test_get_aws_iam_role_returns_data(self, base_connector_kwargs):
        """get_aws_iam_role should fetch role metadata."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.aws.read_role.return_value = {"data": {"arn": "arn:aws:iam::123:role/prod"}}

        role_data = connector.get_aws_iam_role(role_name="prod")

        assert isinstance(role_data, ExtendedDict)
        assert isinstance(role_data["arn"], ExtendedString)
        assert role_data == {"arn": "arn:aws:iam::123:role/prod"}
        mock_client.secrets.aws.read_role.assert_called_once_with(name="prod", mount_point="aws")

    def test_get_aws_iam_role_handles_errors(self, base_connector_kwargs):
        """Vault failures when fetching role metadata should return None."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.aws.read_role.side_effect = VaultError("missing")

        assert connector.get_aws_iam_role(role_name="missing") is None

    def test_get_secret_matcher_logs_redact_secret_values(self, base_connector_kwargs):
        """Matcher-success logs should not expose matched Vault secret values."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)
        connector.list_secrets = MagicMock(return_value=extend_data({"prod/db": {}}))  # type: ignore[method-assign]
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"password": "hunter2", "username": "admin"}}
        }

        secret = connector.get_secret(path="prod", matchers={"password": "hunter2"})

        logs = _logged_text(connector.logger)
        assert secret == {"password": "hunter2", "username": "admin"}
        assert "prod/db" not in logs
        assert "hunter2" not in logs
        assert "Matched [REDACTED] on matcher password" in logs

    def test_generate_aws_credentials_success(self, base_connector_kwargs):
        """generate_aws_credentials should return the generated credential payload."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.aws.generate_credentials.return_value = {
            "data": {"access_key": "AKIA", "secret_key": "SECRET", "security_token": "TOKEN"}
        }

        credentials = connector.generate_aws_credentials(role_name="prod", ttl="1h", credential_type="sts")

        assert isinstance(credentials, ExtendedDict)
        assert isinstance(credentials["access_key"], ExtendedString)
        assert credentials["access_key"] == "AKIA"
        mock_client.secrets.aws.generate_credentials.assert_called_once_with(
            name="prod",
            mount_point="aws",
            ttl="1h",
            type="sts",
        )

    def test_generate_aws_credentials_error(self, base_connector_kwargs):
        """Vault errors while generating credentials should raise RuntimeError."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)

        mock_client.secrets.aws.generate_credentials.side_effect = VaultError("boom")

        with pytest.raises(RuntimeError):
            connector.generate_aws_credentials(role_name="prod")

    def test_write_secret_failure_redacts_without_traceback(self, base_connector_kwargs):
        """Vault write failures should not expose paths, values, or tracebacks."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)
        mock_client.secrets.kv.v2.create_or_update_secret.side_effect = VaultError(
            "write failed at prod/db password=hunter2 token=raw-token"
        )

        assert connector.write_secret("prod/db", {"password": "hunter2"}) is False

        logs = _logged_text(connector.logger)
        assert "prod/db" not in logs
        assert "hunter2" not in logs
        assert "raw-token" not in logs
        assert "[REDACTED]" in logs
        connector.logger.exception.assert_not_called()
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    def test_generate_aws_credentials_redacts_error_diagnostics(self, base_connector_kwargs):
        """Vault credential failures should redact role names and exception payloads."""
        connector = VaultConnector(
            vault_url="https://vault.example.com", vault_token="test-token", **base_connector_kwargs
        )

        mock_client = MagicMock()
        connector._vault_client = mock_client
        connector._vault_token_expiration = datetime(2099, 1, 1, tzinfo=UTC)
        mock_client.secrets.aws.generate_credentials.side_effect = VaultError(
            "denied api_key=key_123 Authorization: Bearer raw_token"
        )

        with pytest.raises(RuntimeError) as exc_info:
            connector.generate_aws_credentials(role_name="prod password=hunter2")

        logs = _logged_text(connector.logger)
        message = str(exc_info.value)
        assert "hunter2" not in logs
        assert "key_123" not in logs
        assert "raw_token" not in logs
        assert "hunter2" not in message
        assert "[REDACTED]" in logs
        assert "[REDACTED]" in message
        assert exc_info.value.__cause__ is None
        connector.logger.exception.assert_not_called()
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)
