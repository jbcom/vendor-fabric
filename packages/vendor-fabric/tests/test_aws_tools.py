"""Tests for AWS AI tools."""

from __future__ import annotations

import importlib.util

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data


# Patch where the tool functions instantiate the first-class connector.
AWS_CONNECTOR_PATCH = "vendor_fabric.aws.AWSConnector"


def test_aws_connector_requires_boto3_when_constructed_without_extra() -> None:
    """AWS tool metadata imports without boto3, but the connector still requires the extra."""
    if importlib.util.find_spec("boto3") is not None:
        pytest.skip("boto3 is installed")

    from vendor_fabric.aws import AWSConnector

    with pytest.raises(ImportError, match=r"vendor-fabric\[aws\]"):
        AWSConnector(from_environment=False)


class TestAWSToolDefinitions:
    """Test tool definitions and metadata."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS is populated."""
        from vendor_fabric.aws.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all tools have name, description, and func."""
        from vendor_fabric.aws.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Tool missing 'name': {defn}"
            assert "description" in defn, f"Tool missing 'description': {defn}"
            assert "func" in defn, f"Tool missing 'func': {defn}"
            assert callable(defn["func"]), f"Tool func not callable: {defn['name']}"

    def test_tool_names_prefixed(self):
        """Test that all tool names are prefixed with 'aws_'."""
        from vendor_fabric.aws.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("aws_"), f"Tool name not prefixed: {defn['name']}"


class TestGetCallerAccountId:
    """Tests for get_caller_account_id tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_get_caller_account_id(self, mock_connector_class):
        """Test account ID lookup."""
        from vendor_fabric.aws.tools import get_caller_account_id

        mock_connector = MagicMock()
        mock_connector.get_caller_account_id.return_value = "123456789012"
        mock_connector_class.return_value = mock_connector

        result = get_caller_account_id()

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["account_id"], ExtendedString)
        assert result["account_id"] == "123456789012"


class TestListSecrets:
    """Tests for list_secrets tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_secrets_basic(self, mock_connector_class):
        """Test basic list_secrets functionality."""
        from vendor_fabric.aws.tools import list_secrets

        mock_connector = MagicMock()
        mock_connector.list_secrets.return_value = extend_data(
            {
                "my-secret": {
                    "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret",
                    "Description": "Test secret",
                    "LastChangedDate": "2024-01-01T00:00:00Z",
                },
                "another-secret": {
                    "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:another-secret",
                    "Description": "Another test",
                    "LastChangedDate": "2024-01-02T00:00:00Z",
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_secrets()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert isinstance(result[0]["value"], ExtendedDict)
        assert len(result) == 2
        assert result[0]["name"] == "my-secret"
        assert "arn" in result[0]

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_secrets_with_prefix(self, mock_connector_class):
        """Test list_secrets with prefix filter."""
        from vendor_fabric.aws.tools import list_secrets

        mock_connector = MagicMock()
        mock_connector.list_secrets.return_value = {}
        mock_connector_class.return_value = mock_connector

        list_secrets(prefix="prod/")

        mock_connector.list_secrets.assert_called_once_with(prefix="prod/")


class TestGetSecret:
    """Tests for get_secret tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_get_secret_basic(self, mock_connector_class):
        """Test basic get_secret functionality."""
        from vendor_fabric.aws.tools import get_secret

        mock_connector = MagicMock()
        mock_connector.get_secret.return_value = "super-secret-value"
        mock_connector_class.return_value = mock_connector

        result = get_secret("my-secret")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["secret_name"], ExtendedString)
        assert result["secret_name"] == "my-secret"
        assert result["secret_value"] == "super-secret-value"
        assert result["status"] == "retrieved"


class TestListS3Buckets:
    """Tests for list_s3_buckets tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_s3_buckets_basic(self, mock_connector_class):
        """Test basic list_s3_buckets functionality."""
        from vendor_fabric.aws.tools import list_s3_buckets

        mock_connector = MagicMock()
        mock_connector.list_s3_buckets.return_value = extend_data(
            {
                "my-bucket": {
                    "CreationDate": "2024-01-01T00:00:00Z",
                    "region": "us-east-1",
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_s3_buckets()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 1
        assert result[0]["name"] == "my-bucket"
        assert result[0]["region"] == "us-east-1"


class TestListS3Objects:
    """Tests for list_s3_objects tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_s3_objects_basic(self, mock_connector_class):
        """Test basic list_s3_objects functionality."""
        from vendor_fabric.aws.tools import list_s3_objects

        mock_connector = MagicMock()
        mock_connector.list_objects.return_value = extend_data(
            {
                "file1.txt": {
                    "Size": 1024,
                    "LastModified": "2024-01-01T00:00:00Z",
                    "StorageClass": "STANDARD",
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_s3_objects("my-bucket")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["key"], ExtendedString)
        assert len(result) == 1
        assert result[0]["key"] == "file1.txt"
        assert result[0]["size"] == 1024


class TestListAccounts:
    """Tests for list_accounts tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_accounts_basic(self, mock_connector_class):
        """Test basic list_accounts functionality."""
        from vendor_fabric.aws.tools import list_accounts

        mock_connector = MagicMock()
        mock_connector.get_accounts.return_value = extend_data(
            {
                "123456789012": {
                    "Name": "Production",
                    "Email": "prod@example.com",
                    "Status": "ACTIVE",
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_accounts()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 1
        assert result[0]["id"] == "123456789012"
        assert result[0]["name"] == "Production"


class TestListSSOUsers:
    """Tests for list_sso_users tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_sso_users_basic(self, mock_connector_class):
        """Test basic list_sso_users functionality."""
        from vendor_fabric.aws.tools import list_sso_users

        mock_connector = MagicMock()
        mock_connector.list_sso_users.return_value = extend_data(
            {
                "user-123": {
                    "user_name": "john.doe",
                    "display_name": "John Doe",
                    "primary_email": {"value": "john@example.com"},
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_sso_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["user_name"], ExtendedString)
        assert len(result) == 1
        assert result[0]["user_id"] == "user-123"
        assert result[0]["user_name"] == "john.doe"


class TestListSSOGroups:
    """Tests for list_sso_groups tool."""

    @patch(AWS_CONNECTOR_PATCH)
    def test_list_sso_groups_basic(self, mock_connector_class):
        """Test basic list_sso_groups functionality."""
        from vendor_fabric.aws.tools import list_sso_groups

        mock_connector = MagicMock()
        mock_connector.list_sso_groups.return_value = extend_data(
            {
                "group-123": {
                    "display_name": "Admins",
                    "description": "Admin group",
                    "members": ["user-1", "user-2"],
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_sso_groups()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["display_name"], ExtendedString)
        assert len(result) == 1
        assert result[0]["group_id"] == "group-123"
        assert result[0]["display_name"] == "Admins"
        assert result[0]["member_count"] == 2
