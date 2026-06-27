"""Tests for ConnectorFabric main class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from cloud_connectors import registry
from cloud_connectors.base import ConnectorBase
from cloud_connectors.connectors import ConnectorFabric


# Helper to check if optional dependencies are available
def _has_module(name: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


# Skip markers for optional dependencies
requires_boto3 = pytest.mark.skipif(not _has_module("boto3"), reason="boto3 not installed")
requires_google = pytest.mark.skipif(
    not _has_module("googleapiclient"), reason="google-api-python-client not installed"
)
requires_github = pytest.mark.skipif(not _has_module("github"), reason="github not installed")
requires_slack = pytest.mark.skipif(not _has_module("slack_sdk"), reason="slack-sdk not installed")
requires_vault = pytest.mark.skipif(not _has_module("hvac"), reason="hvac not installed")


class TestConnectorFabric:
    """Tests for ConnectorFabric class."""

    def test_init(self):
        """Test ConnectorFabric initialization."""
        vc = ConnectorFabric()
        assert vc.logger is not None
        assert vc._client_cache is not None

    def test_init_with_logger(self):
        """Test ConnectorFabric initialization with custom logger."""
        mock_logger = MagicMock()
        vc = ConnectorFabric(logger=mock_logger)
        assert vc.logging == mock_logger
        assert vc.logger is not None  # Logger is extracted from logging

    def test_get_cache_key(self):
        """Test cache key generation."""
        vc = ConnectorFabric()
        key1 = vc._get_cache_key(param1="value1", param2="value2")
        key2 = vc._get_cache_key(param1="value1", param2="value2")
        key3 = vc._get_cache_key(param1="value1", param2="different")

        assert key1 == key2
        assert key1 != key3

    def test_get_cache_key_hashes_sensitive_values(self):
        """Sensitive cache-key fields should not expose raw credentials."""
        vc = ConnectorFabric(from_environment=False)

        key1 = vc._get_cache_key(github_token="ghp_raw_token", client_secret="zoom-secret", normal="public")
        key2 = vc._get_cache_key(github_token="ghp_raw_token", client_secret="zoom-secret", normal="public")
        key3 = vc._get_cache_key(github_token="ghp_other_token", client_secret="zoom-secret", normal="public")

        assert key1 == key2
        assert key1 != key3
        rendered = repr(key1)
        assert "ghp_raw_token" not in rendered
        assert "zoom-secret" not in rendered
        assert "sha256" in rendered
        assert "public" in rendered

    def test_cache_client(self):
        """Test caching and retrieving clients."""
        vc = ConnectorFabric()
        mock_client = MagicMock()

        # Set cache
        vc._set_cached_client("test_type", mock_client, param="value")

        # Get from cache
        cached = vc._get_cached_client("test_type", param="value")
        assert cached == mock_client

        # Different params should return None
        cached = vc._get_cached_client("test_type", param="different")
        assert cached is None

    @patch("cloud_connectors.connectors.get_connector_class")
    def test_get_connector_uses_registry_with_shared_context(self, mock_get_connector_class):
        """Generic connector lookup injects shared fabric inputs and logging."""

        class DummyConnector:
            def __init__(self, *, logger, inputs, token):
                self.logger = logger
                self.inputs = inputs
                self.token = token

        vc = ConnectorFabric(inputs={"TOKEN": "from-inputs"}, from_environment=False)
        mock_get_connector_class.return_value = DummyConnector

        connector = vc.get_connector(" dummy ", token="direct-token")

        assert isinstance(connector, DummyConnector)
        assert connector.logger is vc.logging
        assert connector.inputs is vc.inputs
        assert connector.token == "direct-token"
        mock_get_connector_class.assert_called_once_with("dummy")

    @patch("cloud_connectors.connectors.get_connector_class")
    def test_get_connector_preserves_explicit_context_overrides(self, mock_get_connector_class):
        """Generic connector lookup lets callers override injected fabric context."""

        class DummyConnector:
            def __init__(self, *, logger, inputs):
                self.logger = logger
                self.inputs = inputs

        custom_logger = MagicMock()
        custom_inputs = {"TOKEN": "custom"}
        vc = ConnectorFabric(inputs={"TOKEN": "fabric"}, from_environment=False)
        mock_get_connector_class.return_value = DummyConnector

        connector = vc.get_connector("dummy", logger=custom_logger, inputs=custom_inputs)

        assert connector.logger is custom_logger
        assert connector.inputs is custom_inputs

    @patch("cloud_connectors.connectors.get_connector_class")
    def test_get_connector_caches_by_name_and_kwargs(self, mock_get_connector_class):
        """Generic connectors are cached independently by name and constructor args."""

        class DummyConnector:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        vc = ConnectorFabric(from_environment=False)
        mock_get_connector_class.return_value = DummyConnector

        first = vc.get_connector("dummy", token="one")
        second = vc.get_connector(" DUMMY ", token="one")
        third = vc.get_connector("dummy", token="two")

        assert first is second
        assert third is not first
        assert mock_get_connector_class.call_count == 2

    @patch("cloud_connectors.connectors.get_connector_class")
    def test_get_connector_cache_does_not_store_raw_sensitive_kwargs(self, mock_get_connector_class):
        """Generic connector caching hashes secret-like constructor arguments."""

        class DummyConnector:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        vc = ConnectorFabric(from_environment=False)
        mock_get_connector_class.return_value = DummyConnector

        first = vc.get_connector("dummy", api_key="key_123", password="hunter2")
        second = vc.get_connector("dummy", api_key="key_123", password="hunter2")

        assert first is second
        assert mock_get_connector_class.call_count == 1
        rendered_cache = repr(vc._client_cache)
        assert "key_123" not in rendered_cache
        assert "hunter2" not in rendered_cache
        assert "sha256" in rendered_cache

    def test_connector_fabric_exposes_catalog_info(self):
        """ConnectorFabric exposes registry-backed catalog metadata."""
        vc = ConnectorFabric(from_environment=False)

        adapter = vc.get_connector_adapter("github")
        info = vc.list_connector_info()
        names = {connector["name"] for connector in info}

        assert isinstance(adapter, registry.ConnectorAdapter)
        assert adapter.name == "github"
        assert isinstance(info, ExtendedList)
        assert isinstance(info[0], ExtendedDict)
        assert isinstance(info[0]["name"], ExtendedString)
        assert "cursor" in names
        assert "github" in names
        github_info = vc.get_connector_info(" github ")
        categories = vc.list_connector_categories()
        capabilities = vc.list_connector_capabilities()
        cloud_connectors = vc.list_connectors_by_category("cloud")
        repository_connectors = vc.list_connectors_by_capability("repositories")
        connector_names = vc.list_connectors()
        available_connector_names = vc.list_available_connectors()
        assert isinstance(github_info, ExtendedDict)
        assert github_info["name"] == "github"
        assert github_info["category"] == "development"
        assert "repositories" in github_info["capabilities"]
        assert isinstance(github_info["capabilities"], ExtendedList)
        assert isinstance(github_info["capabilities"][0], ExtendedString)
        assert isinstance(categories, ExtendedList)
        assert isinstance(categories[0], ExtendedString)
        assert "ai" in categories
        assert "cloud" in categories
        assert isinstance(capabilities, ExtendedList)
        assert isinstance(capabilities[0], ExtendedString)
        assert "repositories" in capabilities
        assert isinstance(cloud_connectors, ExtendedList)
        assert all(isinstance(connector, ExtendedDict) for connector in cloud_connectors)
        assert {"aws", "google"} <= {connector["name"] for connector in cloud_connectors}
        assert isinstance(repository_connectors, ExtendedList)
        assert "github" in {connector["name"] for connector in repository_connectors}
        assert isinstance(connector_names, ExtendedList)
        assert isinstance(connector_names[0], ExtendedString)
        assert "cursor" in connector_names
        assert "github" in connector_names
        assert isinstance(available_connector_names, ExtendedList)
        assert "cursor" in available_connector_names
        assert set(available_connector_names) <= set(connector_names)
        assert ("github" in available_connector_names) is github_info["available"]

    def test_external_connector_metadata_uses_base_class_catalog_contract(self, monkeypatch):
        """Entry-point connectors can publish category and capability metadata."""

        class CustomConnector(ConnectorBase):
            CONNECTOR_CATEGORY = "Data_Warehouse"
            CONNECTOR_CAPABILITIES = ("SQL", "Files", "sql")

        monkeypatch.setattr(registry, "_connector_cache", {"custom": CustomConnector})
        monkeypatch.setattr(registry, "_missing_builtin_connectors", {})

        info = registry.get_connector_info("custom")
        categories = registry.list_connector_categories()
        capabilities = registry.list_connector_capabilities()
        warehouse_connectors = registry.list_connectors_by_category("data_warehouse")
        sql_connectors = registry.list_connectors_by_capability("sql")

        assert info["source"] == "entry_point"
        assert info["category"] == "data-warehouse"
        assert info["capabilities"] == ["sql", "files"]
        assert "data-warehouse" in categories
        assert "sql" in capabilities
        assert warehouse_connectors[0]["name"] == "custom"
        assert sql_connectors[0]["name"] == "custom"

    @requires_boto3
    @patch("cloud_connectors.aws.AWSConnector")
    def test_get_aws_connector(self, mock_aws):
        """Test getting AWS connector."""
        vc = ConnectorFabric()
        mock_connector = MagicMock()
        mock_aws.return_value = mock_connector

        result = vc.get_aws_connector(execution_role_arn="arn:aws:iam::123456789012:role/TestRole")

        assert result == mock_connector
        mock_aws.assert_called_once()

    @requires_boto3
    @patch("cloud_connectors.aws.AWSConnector")
    def test_get_aws_connector_caching(self, mock_aws):
        """Test AWS connector caching."""
        vc = ConnectorFabric()
        mock_connector = MagicMock()
        mock_aws.return_value = mock_connector

        # First call
        result1 = vc.get_aws_connector(execution_role_arn="arn:aws:iam::123456789012:role/TestRole")
        # Second call with same params
        result2 = vc.get_aws_connector(execution_role_arn="arn:aws:iam::123456789012:role/TestRole")

        assert result1 == result2
        # Should only create connector once
        mock_aws.assert_called_once()

    @requires_boto3
    @patch("cloud_connectors.aws.AWSConnector")
    def test_get_aws_client(self, mock_aws):
        """Test getting AWS client."""
        vc = ConnectorFabric()
        mock_connector = MagicMock()
        mock_client = MagicMock()
        mock_connector.get_aws_client.return_value = mock_client
        mock_aws.return_value = mock_connector

        result = vc.get_aws_client("s3")

        assert result == mock_client
        mock_connector.get_aws_client.assert_called_once()

    @requires_boto3
    @patch("cloud_connectors.aws.AWSConnector")
    def test_get_aws_resource(self, mock_aws):
        """Test getting AWS resource."""
        vc = ConnectorFabric()
        mock_connector = MagicMock()
        mock_resource = MagicMock()
        mock_connector.get_aws_resource.return_value = mock_resource
        mock_aws.return_value = mock_connector

        result = vc.get_aws_resource("s3")

        assert result == mock_resource
        mock_connector.get_aws_resource.assert_called_once()

    @requires_google
    @patch("cloud_connectors.google.GoogleConnector")
    def test_get_google_client(self, mock_google):
        """Test getting Google client."""
        vc = ConnectorFabric(
            inputs={"GOOGLE_SERVICE_ACCOUNT": '{"type": "service_account"}', "GOOGLE_PROJECT_ID": "test-project"}
        )
        mock_connector = MagicMock()
        mock_client = MagicMock()
        mock_connector.get_service.return_value = mock_client
        mock_google.return_value = mock_connector

        result = vc.get_google_client()

        assert result == mock_connector

    @requires_google
    @patch("cloud_connectors.google.GoogleConnector")
    def test_get_google_client_cache_separates_scopes(self, mock_google):
        """Google connector cache keys include requested OAuth scopes."""
        vc = ConnectorFabric(
            inputs={"GOOGLE_SERVICE_ACCOUNT": '{"type": "service_account"}'},
            from_environment=False,
        )
        first_connector = MagicMock()
        second_connector = MagicMock()
        mock_google.side_effect = [first_connector, second_connector]

        first = vc.get_google_client(scopes=["scope-a"])
        second = vc.get_google_client(scopes=["scope-b"])
        third = vc.get_google_client(scopes=["scope-a"])

        assert first is first_connector
        assert second is second_connector
        assert third is first_connector
        assert mock_google.call_count == 2

    @requires_github
    @patch("cloud_connectors.github.GitHubConnector")
    def test_get_github_client(self, mock_github):
        """Test getting GitHub client."""
        vc = ConnectorFabric(inputs={"GITHUB_OWNER": "test-org", "GITHUB_TOKEN": "ghp_test123"})
        mock_connector = MagicMock()
        mock_github.return_value = mock_connector

        result = vc.get_github_client()

        assert result == mock_connector

    @requires_slack
    @patch("cloud_connectors.slack.SlackConnector")
    def test_get_slack_client(self, mock_slack):
        """Test getting Slack client."""
        vc = ConnectorFabric(inputs={"SLACK_TOKEN": "xoxp-test123", "SLACK_BOT_TOKEN": "xoxb-test123"})
        mock_connector = MagicMock()
        mock_slack.return_value = mock_connector

        result = vc.get_slack_client()

        assert result == mock_connector

    @requires_vault
    @patch("cloud_connectors.vault.VaultConnector")
    def test_get_vault_connector(self, mock_vault):
        """Test getting Vault connector."""
        vc = ConnectorFabric()
        mock_connector = MagicMock()
        mock_vault.return_value = mock_connector

        result = vc.get_vault_connector(vault_token="hvs.test123")

        assert result == mock_connector

    @patch("cloud_connectors.connectors.ZoomConnector")
    def test_get_zoom_client(self, mock_zoom):
        """Test getting Zoom client."""
        vc = ConnectorFabric(
            inputs={
                "ZOOM_CLIENT_ID": "test-client-id",
                "ZOOM_CLIENT_SECRET": "test-secret",
                "ZOOM_ACCOUNT_ID": "test-account",
            }
        )
        mock_connector = MagicMock()
        mock_zoom.return_value = mock_connector

        result = vc.get_zoom_client()

        assert result == mock_connector

    @requires_vault
    @patch("cloud_connectors.vault.VaultConnector")
    def test_get_vault_client(self, mock_vault):
        """Test getting Vault client."""
        vc = ConnectorFabric()
        mock_connector = MagicMock()
        mock_client = MagicMock()
        mock_connector.vault_client = mock_client
        mock_vault.return_value = mock_connector

        result = vc.get_vault_client(vault_token="hvs.test123")

        assert result == mock_client

    @requires_boto3
    @requires_slack
    def test_multiple_connector_types_cached_separately(self):
        """Test that different connector types are cached separately."""
        with (
            patch("cloud_connectors.aws.AWSConnector") as mock_aws,
            patch("cloud_connectors.slack.SlackConnector") as mock_slack,
        ):
            vc = ConnectorFabric(inputs={"SLACK_TOKEN": "xoxp-test123", "SLACK_BOT_TOKEN": "xoxb-test123"})
            mock_aws_connector = MagicMock()
            mock_slack_connector = MagicMock()
            mock_aws.return_value = mock_aws_connector
            mock_slack.return_value = mock_slack_connector

            aws1 = vc.get_aws_connector()
            slack1 = vc.get_slack_client()
            _aws2 = vc.get_aws_connector()
            _slack2 = vc.get_slack_client()

            # Each connector type should only be created once
            mock_aws.assert_called_once()
            mock_slack.assert_called_once()

            # But they should be different objects
            assert aws1 != slack1

    def test_get_aws_connector_without_boto3(self):
        """Test that get_aws_connector raises ImportError without boto3."""
        # This test runs even without boto3 to verify error handling
        vc = ConnectorFabric()
        if not _has_module("boto3"):
            with pytest.raises(ImportError, match="boto3"):
                vc.get_aws_connector()

    def test_get_github_client_without_pygithub(self):
        """Test that get_github_client raises ImportError without github."""
        vc = ConnectorFabric(inputs={"GITHUB_OWNER": "test-org", "GITHUB_TOKEN": "ghp_test123"})
        if not _has_module("github"):
            with pytest.raises(ImportError, match="github"):
                vc.get_github_client()

    def test_get_connector_class_known_missing_builtin_has_install_hint(self, monkeypatch):
        """Registry raises install guidance when a known built-in extra is missing."""
        monkeypatch.setattr(registry, "_connector_cache", {})
        monkeypatch.setattr(
            registry,
            "get_missing_connector_requirements",
            lambda name: ExtendedList(["github"]) if name == "github" else ExtendedList(),
        )

        with pytest.raises(ImportError, match=r"cloud-connectors\[github\]") as exc_info:
            registry.get_connector_class(" github ")

        message = str(exc_info.value)
        assert "Missing packages: github" in message

    def test_get_connector_info_includes_known_missing_builtin(self, monkeypatch):
        """Registry metadata includes unavailable known connectors."""
        monkeypatch.setattr(registry, "_connector_cache", {})
        monkeypatch.setattr(
            registry,
            "get_missing_connector_requirements",
            lambda name: ExtendedList(["github"]) if name == "github" else ExtendedList(),
        )
        monkeypatch.setitem(
            registry._missing_builtin_connectors,
            "github",
            ImportError("No module named 'github' password=hunter2 Authorization: Bearer raw_token"),
        )

        info = registry.get_connector_info(" github ")

        assert isinstance(info, ExtendedDict)
        assert isinstance(info["name"], ExtendedString)
        assert info["name"] == "github"
        assert info["available"] is False
        assert info["extra"] == "github"
        assert info["install"] == "pip install cloud-connectors[github]"
        assert info["class"] == "GitHubConnector"
        assert info["missing"] == ["github"]
        assert "hunter2" not in info["error"]
        assert "raw_token" not in info["error"]
        assert "[REDACTED]" in info["error"]

    def test_get_connector_class_redacts_unknown_connector_name(self, monkeypatch):
        """Unknown connector diagnostics should not echo secret-bearing names."""
        monkeypatch.setattr(registry, "_connector_cache", {})
        monkeypatch.setattr(registry, "_missing_builtin_connectors", {})

        with pytest.raises(ValueError) as exc_info:
            registry.get_connector_class("password=hunter2 Authorization: Bearer raw_token")

        message = str(exc_info.value)
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message

    def test_builtin_adapter_loads_known_connector_without_entry_point_cache(self, monkeypatch):
        """Built-in adapters are authoritative even before entry-point discovery."""
        monkeypatch.setattr(registry, "_connector_cache", {})
        monkeypatch.setattr(registry, "_missing_builtin_connectors", {})
        monkeypatch.setattr(registry, "get_missing_connector_requirements", lambda name: ExtendedList())

        cls = registry.get_connector_class(" cursor ")

        assert cls.__name__ == "CursorConnector"

    def test_get_connector_adapter_wraps_entry_point_connectors(self, monkeypatch):
        """External entry-point classes are exposed through the same adapter contract."""

        class CustomConnector(ConnectorBase):
            CONNECTOR_CATEGORY = "warehouse"

        monkeypatch.setattr(registry, "_connector_cache", {})
        monkeypatch.setattr(registry, "_missing_builtin_connectors", {})
        monkeypatch.setattr(registry, "_connector_cache", {"custom": CustomConnector})

        adapter = registry.get_connector_adapter(" custom ")
        info = adapter.as_dict()

        assert isinstance(adapter, registry.ConnectorAdapter)
        assert adapter.name == "custom"
        assert adapter.load_class() is CustomConnector
        assert info["name"] == "custom"
        assert info["source"] == "entry_point"
        assert info["category"] == "warehouse"

    def test_builtin_with_missing_requirements_is_unavailable(self):
        """Entry-point registered built-ins report unavailable when extras are missing."""
        registry.clear_cache()

        if not _has_module("boto3"):
            info = registry.get_connector_info("aws")

            assert isinstance(info, ExtendedDict)
            assert isinstance(info["missing"], ExtendedList)
            assert info["available"] is False
            assert info["missing"] == ["boto3"]

            with pytest.raises(ImportError, match=r"cloud-connectors\[aws\]"):
                registry.get_connector_class("aws")

    def test_available_only_catalog_filters_missing_builtins(self):
        """Available-only metadata excludes built-ins with missing extras."""
        registry.clear_cache()

        info = registry.list_connector_info(include_unavailable=False)

        assert isinstance(info, ExtendedList)
        assert all(connector["available"] for connector in info)

    def test_list_connectors_reports_catalog_names_and_available_names_explicitly(self, monkeypatch):
        """Connector catalog names and runtime-available names are separate APIs."""

        class CursorConnector:
            pass

        class GitHubConnector:
            pass

        monkeypatch.setattr(
            registry,
            "_connector_cache",
            {
                "cursor": CursorConnector,
                "github": GitHubConnector,
            },
        )
        monkeypatch.setattr(registry, "_missing_builtin_connectors", {})
        monkeypatch.setattr(
            registry,
            "get_missing_connector_requirements",
            lambda name: ExtendedList(["github"]) if name == "github" else ExtendedList(),
        )

        catalog_names = registry.list_connectors()
        available_names = registry.list_available_connectors()

        assert isinstance(catalog_names, ExtendedList)
        assert "cursor" in catalog_names
        assert "github" in catalog_names
        assert isinstance(available_names, ExtendedList)
        assert "cursor" in available_names
        assert "github" not in available_names
