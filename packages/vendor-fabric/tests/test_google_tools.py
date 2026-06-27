"""Tests for Google AI tools."""

from __future__ import annotations

import importlib.util

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data


# Patch where the tool functions instantiate the first-class connector.
GOOGLE_CONNECTOR_PATCH = "vendor_fabric.google.GoogleConnector"


def test_google_connector_requires_google_sdk_when_constructed_without_extra() -> None:
    """Google tool metadata imports without Google SDKs, but the connector still requires the extra."""
    if importlib.util.find_spec("googleapiclient") is not None:
        pytest.skip("google-api-python-client is installed")

    from vendor_fabric.google import GoogleConnector

    with pytest.raises(ImportError, match=r"vendor-fabric\[google\]"):
        GoogleConnector(service_account_info={"type": "service_account"}, from_environment=False)


class TestGoogleToolDefinitions:
    """Test tool definitions and metadata."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS is populated."""
        from vendor_fabric.google.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all tools have name, description, and func."""
        from vendor_fabric.google.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Tool missing 'name': {defn}"
            assert "description" in defn, f"Tool missing 'description': {defn}"
            assert "func" in defn, f"Tool missing 'func': {defn}"
            assert callable(defn["func"]), f"Tool func not callable: {defn['name']}"

    def test_tool_names_prefixed(self):
        """Test that all tool names are prefixed with 'google_'."""
        from vendor_fabric.google.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("google_"), f"Tool name not prefixed: {defn['name']}"

    def test_tool_count(self):
        """Test that we have exactly 6 tools as specified."""
        from vendor_fabric.google.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) == 6


class TestListProjects:
    """Tests for list_projects tool."""

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_projects_basic(self, mock_connector_class):
        """Test basic list_projects functionality."""
        from vendor_fabric.google.tools import list_projects

        mock_connector = MagicMock()
        mock_connector.list_projects.return_value = extend_data(
            [
                {
                    "projectId": "my-project-123",
                    "displayName": "My Project",
                    "state": "ACTIVE",
                    "parent": "organizations/123456",
                },
                {
                    "projectId": "another-project-456",
                    "name": "projects/another-project-456",
                    "state": "ACTIVE",
                    "parent": "folders/789",
                },
            ]
        )
        mock_connector_class.return_value = mock_connector

        result = list_projects()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["project_id"], ExtendedString)
        assert len(result) == 2
        assert result[0]["project_id"] == "my-project-123"
        assert result[0]["name"] == "My Project"
        assert result[0]["state"] == "ACTIVE"
        assert result[1]["project_id"] == "another-project-456"

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_projects_with_parent(self, mock_connector_class):
        """Test list_projects with parent filter."""
        from vendor_fabric.google.tools import list_projects

        mock_connector = MagicMock()
        mock_connector.list_projects.return_value = []
        mock_connector_class.return_value = mock_connector

        list_projects(parent="organizations/123456")

        mock_connector.list_projects.assert_called_once_with(parent="organizations/123456")

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_projects_max_results(self, mock_connector_class):
        """Test list_projects respects max_results."""
        from vendor_fabric.google.tools import list_projects

        mock_connector = MagicMock()
        # Return more projects than max_results
        mock_connector.list_projects.return_value = [
            {"projectId": f"project-{i}", "state": "ACTIVE"} for i in range(150)
        ]
        mock_connector_class.return_value = mock_connector

        result = list_projects(max_results=50)

        assert len(result) == 50


class TestListFolders:
    """Tests for list_folders tool."""

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_folders_basic(self, mock_connector_class):
        """Test basic list_folders functionality."""
        from vendor_fabric.google.tools import list_folders

        mock_connector = MagicMock()
        mock_connector.list_folders.return_value = extend_data(
            [
                {
                    "name": "folders/123",
                    "displayName": "Engineering",
                    "state": "ACTIVE",
                    "parent": "organizations/456",
                }
            ]
        )
        mock_connector_class.return_value = mock_connector

        result = list_folders(parent="organizations/456")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["display_name"], ExtendedString)
        assert result[0]["name"] == "folders/123"
        assert result[0]["display_name"] == "Engineering"


class TestListEnabledServices:
    """Tests for list_enabled_services tool."""

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_enabled_services_basic(self, mock_connector_class):
        """Test basic list_enabled_services functionality."""
        from vendor_fabric.google.tools import list_enabled_services

        mock_connector = MagicMock()
        mock_connector.list_enabled_services.return_value = extend_data(
            [
                {
                    "name": "projects/123/services/compute.googleapis.com",
                    "config": {"title": "Compute Engine API"},
                    "state": "ENABLED",
                },
                {
                    "name": "projects/123/services/storage.googleapis.com",
                    "config": {"title": "Cloud Storage API"},
                    "state": "ENABLED",
                },
            ]
        )
        mock_connector_class.return_value = mock_connector

        result = list_enabled_services(project_id="my-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["title"], ExtendedString)
        assert len(result) == 2
        assert result[0]["name"] == "projects/123/services/compute.googleapis.com"
        assert result[0]["title"] == "Compute Engine API"
        assert result[0]["state"] == "ENABLED"

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_enabled_services_with_project(self, mock_connector_class):
        """Test list_enabled_services passes project_id correctly."""
        from vendor_fabric.google.tools import list_enabled_services

        mock_connector = MagicMock()
        mock_connector.list_enabled_services.return_value = []
        mock_connector_class.return_value = mock_connector

        list_enabled_services(project_id="test-project-123")

        mock_connector.list_enabled_services.assert_called_once_with(project_id="test-project-123")


class TestListBillingAccounts:
    """Tests for list_billing_accounts tool."""

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_billing_accounts_basic(self, mock_connector_class):
        """Test basic list_billing_accounts functionality."""
        from vendor_fabric.google.tools import list_billing_accounts

        mock_connector = MagicMock()
        mock_connector.list_billing_accounts.return_value = extend_data(
            [
                {
                    "name": "billingAccounts/012345-6789AB-CDEF01",
                    "displayName": "My Billing Account",
                    "open": True,
                    "masterBillingAccount": "",
                },
                {
                    "name": "billingAccounts/ABCDEF-123456-789012",
                    "displayName": "Another Billing",
                    "open": False,
                    "masterBillingAccount": "billingAccounts/012345-6789AB-CDEF01",
                },
            ]
        )
        mock_connector_class.return_value = mock_connector

        result = list_billing_accounts()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["display_name"], ExtendedString)
        assert len(result) == 2
        assert "billingAccounts/" in result[0]["name"]
        assert result[0]["display_name"] == "My Billing Account"
        assert result[0]["open"] is True
        assert result[1]["open"] is False

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_billing_accounts_empty(self, mock_connector_class):
        """Test list_billing_accounts with no accounts."""
        from vendor_fabric.google.tools import list_billing_accounts

        mock_connector = MagicMock()
        mock_connector.list_billing_accounts.return_value = []
        mock_connector_class.return_value = mock_connector

        result = list_billing_accounts()

        assert len(result) == 0


class TestListWorkspaceUsers:
    """Tests for list_workspace_users tool."""

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_workspace_users_basic(self, mock_connector_class):
        """Test basic list_workspace_users functionality."""
        from vendor_fabric.google.tools import list_workspace_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = extend_data(
            {
                "john.doe@example.com": {
                    "primaryEmail": "john.doe@example.com",
                    "name": {"fullName": "John Doe"},
                    "full_name": "John Doe",
                    "suspended": False,
                    "orgUnitPath": "/",
                },
                "jane.smith@example.com": {
                    "primaryEmail": "jane.smith@example.com",
                    "name": {"fullName": "Jane Smith"},
                    "full_name": "Jane Smith",
                    "suspended": False,
                    "orgUnitPath": "/Engineering",
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_workspace_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["email"], ExtendedString)
        assert len(result) == 2
        assert result[0]["email"] == "john.doe@example.com"
        assert result[0]["full_name"] == "John Doe"
        assert result[0]["suspended"] is False
        assert result[1]["org_unit_path"] == "/Engineering"

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_workspace_users_with_domain(self, mock_connector_class):
        """Test list_workspace_users with domain parameter."""
        from vendor_fabric.google.tools import list_workspace_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = []
        mock_connector_class.return_value = mock_connector

        list_workspace_users(domain="example.com")

        # Verify the correct parameters were passed
        mock_connector.list_users.assert_called_once()
        call_kwargs = mock_connector.list_users.call_args[1]
        assert call_kwargs["domain"] == "example.com"
        assert call_kwargs["flatten_names"] is True
        assert call_kwargs["key_by_email"] is False

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_workspace_users_suspended(self, mock_connector_class):
        """Test list_workspace_users handles suspended users."""
        from vendor_fabric.google.tools import list_workspace_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = [
            {
                "primaryEmail": "suspended@example.com",
                "name": {"fullName": "Suspended User"},
                "full_name": "Suspended User",
                "suspended": True,
                "orgUnitPath": "/",
            },
        ]
        mock_connector_class.return_value = mock_connector

        result = list_workspace_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 1
        assert result[0]["suspended"] is True


class TestListWorkspaceGroups:
    """Tests for list_workspace_groups tool."""

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_workspace_groups_basic(self, mock_connector_class):
        """Test basic list_workspace_groups functionality."""
        from vendor_fabric.google.tools import list_workspace_groups

        mock_connector = MagicMock()
        mock_connector.list_groups.return_value = extend_data(
            {
                "admins@example.com": {
                    "email": "admins@example.com",
                    "name": "Admins",
                    "description": "Administrator group",
                    "directMembersCount": 5,
                },
                "developers@example.com": {
                    "email": "developers@example.com",
                    "name": "Developers",
                    "description": "Development team",
                    "directMembersCount": 25,
                },
            }
        )
        mock_connector_class.return_value = mock_connector

        result = list_workspace_groups()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["email"], ExtendedString)
        assert len(result) == 2
        assert result[0]["email"] == "admins@example.com"
        assert result[0]["name"] == "Admins"
        assert result[0]["description"] == "Administrator group"
        assert result[0]["direct_members_count"] == 5
        assert result[1]["direct_members_count"] == 25

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_workspace_groups_with_domain(self, mock_connector_class):
        """Test list_workspace_groups with domain parameter."""
        from vendor_fabric.google.tools import list_workspace_groups

        mock_connector = MagicMock()
        mock_connector.list_groups.return_value = []
        mock_connector_class.return_value = mock_connector

        list_workspace_groups(domain="example.com")

        # Verify the correct parameters were passed
        mock_connector.list_groups.assert_called_once()
        call_kwargs = mock_connector.list_groups.call_args[1]
        assert call_kwargs["domain"] == "example.com"
        assert call_kwargs["key_by_email"] is False

    @patch(GOOGLE_CONNECTOR_PATCH)
    def test_list_workspace_groups_empty_description(self, mock_connector_class):
        """Test list_workspace_groups handles missing description."""
        from vendor_fabric.google.tools import list_workspace_groups

        mock_connector = MagicMock()
        mock_connector.list_groups.return_value = [
            {
                "email": "nodescrip@example.com",
                "name": "No Description Group",
                "directMembersCount": 0,
            },
        ]
        mock_connector_class.return_value = mock_connector

        result = list_workspace_groups()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 1
        assert result[0]["description"] == ""
        assert result[0]["direct_members_count"] == 0


class TestGetTools:
    """Tests for Google capability exports."""

    def test_all_exports_exist(self):
        """Test that all expected exports are available."""
        from vendor_fabric.google import tools

        expected_exports = [
            "list_projects",
            "list_enabled_services",
            "list_billing_accounts",
            "list_workspace_users",
            "list_workspace_groups",
            "TOOL_DEFINITIONS",
        ]

        for export in expected_exports:
            assert hasattr(tools, export), f"Missing export: {export}"
