"""Tests for Vault AI tools."""

from __future__ import annotations

import importlib.util

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data


# Patch target for VaultConnector - must patch where it's used (in tools.py), not where it's defined
VAULT_CONNECTOR_PATCH = "vendor_fabric.vault.VaultConnector"


def test_vault_connector_requires_hvac_when_constructed_without_extra() -> None:
    """Vault tool metadata imports without hvac, but the connector still requires the extra."""
    if importlib.util.find_spec("hvac") is not None:
        pytest.skip("hvac is installed")

    from vendor_fabric.vault import VaultConnector

    with pytest.raises(ImportError, match=r"vendor-fabric\[vault\]"):
        VaultConnector(from_environment=False)


class TestVaultToolDefinitions:
    """Test tool definitions and metadata."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS is populated."""
        from vendor_fabric.vault.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all tools have name, description, and func."""
        from vendor_fabric.vault.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Tool missing 'name': {defn}"
            assert "description" in defn, f"Tool missing 'description': {defn}"
            assert "func" in defn, f"Tool missing 'func': {defn}"
            assert callable(defn["func"]), f"Tool func not callable: {defn['name']}"

    def test_tool_names_prefixed(self):
        """Test that all tool names are prefixed with 'vault_'."""
        from vendor_fabric.vault.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("vault_"), f"Tool name not prefixed: {defn['name']}"


class TestListSecrets:
    """Tests for list_secrets tool."""

    @patch(VAULT_CONNECTOR_PATCH)
    def test_list_secrets_basic(self, mock_connector_class):
        """Test basic list_secrets functionality."""
        from vendor_fabric.vault.tools import list_secrets

        mock_connector = MagicMock()
        mock_connector.list_secrets.return_value = extend_data(
            {
                "app/db-password": {"username": "admin", "password": "secret123"},
                "app/api-key": {"key": "abc123xyz"},
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_secrets()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["path"], ExtendedString)
        assert isinstance(result[0]["data"], ExtendedDict)
        assert len(result) == 2
        assert result[0]["path"] == "app/db-password"
        assert result[0]["mount_point"] == "secret"
        assert result[0]["data"]["username"] == "admin"
        assert result[0]["key_count"] == 2
        assert result[1]["path"] == "app/api-key"
        assert result[1]["key_count"] == 1

    @patch(VAULT_CONNECTOR_PATCH)
    def test_list_secrets_with_custom_path(self, mock_connector_class):
        """Test list_secrets with custom root path."""
        from vendor_fabric.vault.tools import list_secrets

        mock_connector = MagicMock()
        mock_connector.list_secrets.return_value = {
            "prod/db": {"host": "db.example.com"},
        }
        mock_connector_class.return_value = mock_connector

        result = list_secrets(root_path="prod/", mount_point="kv")

        mock_connector.list_secrets.assert_called_once_with(
            root_path="prod/",
            mount_point="kv",
            max_depth=10,
        )
        assert len(result) == 1
        assert result[0]["path"] == "prod/db"
        assert result[0]["mount_point"] == "kv"

    @patch(VAULT_CONNECTOR_PATCH)
    def test_list_secrets_empty(self, mock_connector_class):
        """Test list_secrets with no secrets found."""
        from vendor_fabric.vault.tools import list_secrets

        mock_connector = MagicMock()
        mock_connector.list_secrets.return_value = {}
        mock_connector_class.return_value = mock_connector

        result = list_secrets()

        assert len(result) == 0

    @patch(VAULT_CONNECTOR_PATCH)
    def test_list_secrets_with_max_depth(self, mock_connector_class):
        """Test list_secrets with max_depth parameter."""
        from vendor_fabric.vault.tools import list_secrets

        mock_connector = MagicMock()
        mock_connector.list_secrets.return_value = {}
        mock_connector_class.return_value = mock_connector

        list_secrets(max_depth=3)

        mock_connector.list_secrets.assert_called_once_with(
            root_path="/",
            mount_point="secret",
            max_depth=3,
        )


class TestReadSecret:
    """Tests for read_secret tool."""

    @patch(VAULT_CONNECTOR_PATCH)
    def test_read_secret_found(self, mock_connector_class):
        """Test read_secret when secret exists."""
        from vendor_fabric.vault.tools import read_secret

        mock_connector = MagicMock()
        mock_connector.read_secret.return_value = {
            "username": "admin",
            "password": "secret123",
        }
        mock_connector_class.return_value = mock_connector

        result = read_secret("app/db-password")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["path"], ExtendedString)
        assert isinstance(result["data"], ExtendedDict)
        assert result["path"] == "app/db-password"
        assert result["mount_point"] == "secret"
        assert result["data"]["username"] == "admin"
        assert result["data"]["password"] == "secret123"
        assert result["found"] is True

    @patch(VAULT_CONNECTOR_PATCH)
    def test_read_secret_not_found(self, mock_connector_class):
        """Test read_secret when secret does not exist."""
        from vendor_fabric.vault.tools import read_secret

        mock_connector = MagicMock()
        mock_connector.read_secret.return_value = None
        mock_connector_class.return_value = mock_connector

        result = read_secret("app/missing-secret")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["data"], ExtendedDict)
        assert result["path"] == "app/missing-secret"
        assert result["mount_point"] == "secret"
        assert result["data"] == {}
        assert result["found"] is False

    @patch(VAULT_CONNECTOR_PATCH)
    def test_read_secret_custom_mount(self, mock_connector_class):
        """Test read_secret with custom mount point."""
        from vendor_fabric.vault.tools import read_secret

        mock_connector = MagicMock()
        mock_connector.read_secret.return_value = {"key": "value"}
        mock_connector_class.return_value = mock_connector

        result = read_secret("my-secret", mount_point="kv")

        mock_connector.read_secret.assert_called_once_with(
            path="my-secret",
            mount_point="kv",
        )
        assert result["mount_point"] == "kv"
