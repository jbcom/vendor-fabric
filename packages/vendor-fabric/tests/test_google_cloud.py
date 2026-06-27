# ruff: noqa: I001
"""Tests for Google Cloud Platform resource management operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.oauth2.service_account")
pytest.importorskip("googleapiclient")

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from vendor_fabric.google import GoogleConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


@pytest.fixture
def google_connector():
    """Create Google connector with mocked services."""
    service_account = {
        "type": "service_account",
        "client_email": "test@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...test\n-----END RSA PRIVATE KEY-----\n",
        "private_key_id": "key123",
        "project_id": "test-project",
    }
    with patch("googleapiclient.discovery.build"):
        connector = GoogleConnector(service_account_info=service_account)
        connector.logger = MagicMock()
        return connector


class TestOrganization:
    """Tests for organization operations."""

    def test_get_organization_id(self, google_connector):
        """Test getting organization ID."""
        mock_service = MagicMock()
        mock_orgs = mock_service.organizations.return_value
        mock_orgs.search.return_value.execute.return_value = {
            "organizations": [{"name": "organizations/123456789", "displayName": "Test Org"}]
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.get_organization_id()

        assert isinstance(result, ExtendedString)
        assert result == "123456789"

    def test_get_organization_id_no_org(self, google_connector):
        """Test getting organization ID when no org exists."""
        mock_service = MagicMock()
        mock_orgs = mock_service.organizations.return_value
        mock_orgs.search.return_value.execute.return_value = {"organizations": []}
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        with pytest.raises(RuntimeError, match="No organizations found"):
            google_connector.get_organization_id()

    def test_get_organization(self, google_connector):
        """Test getting organization details."""
        mock_service = MagicMock()
        mock_orgs = mock_service.organizations.return_value
        mock_orgs.search.return_value.execute.return_value = {
            "organizations": [
                {
                    "name": "organizations/123456789",
                    "displayName": "Test Org",
                    "lifecycleState": "ACTIVE",
                }
            ]
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.get_organization()

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["displayName"], ExtendedString)
        assert result["displayName"] == "Test Org"
        assert result["lifecycleState"] == "ACTIVE"

    def test_get_organization_no_org(self, google_connector):
        """Test getting organization when none exists."""
        mock_service = MagicMock()
        mock_orgs = mock_service.organizations.return_value
        mock_orgs.search.return_value.execute.return_value = {"organizations": []}
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        with pytest.raises(RuntimeError, match="No organizations found"):
            google_connector.get_organization()


class TestProjects:
    """Tests for project operations."""

    def test_list_projects(self, google_connector):
        """Test listing projects."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.search.return_value.execute.return_value = {
            "projects": [
                {"projectId": "project-1", "name": "Project One"},
                {"projectId": "project-2", "name": "Project Two"},
            ]
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.list_projects()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["projectId"], ExtendedString)
        assert len(result) == 2
        assert result[0]["projectId"] == "project-1"

    def test_list_projects_with_parent(self, google_connector):
        """Test listing projects with parent filter."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.search.return_value.execute.return_value = {"projects": [{"projectId": "project-1"}]}
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.list_projects(parent="organizations/123456")

        assert len(result) == 1
        call_args = mock_projects.search.call_args[1]
        assert call_args["parent"] == "organizations/123456"

    def test_list_projects_with_filter(self, google_connector):
        """Test listing projects with filter query."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.search.return_value.execute.return_value = {"projects": [{"projectId": "project-1"}]}
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.list_projects(filter_query="lifecycleState:ACTIVE")

        assert len(result) == 1
        call_args = mock_projects.search.call_args[1]
        assert call_args["filter"] == "lifecycleState:ACTIVE"

    def test_list_projects_pagination(self, google_connector):
        """Test listing projects with pagination."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.search.return_value.execute.side_effect = [
            {
                "projects": [{"projectId": "project-1"}],
                "nextPageToken": "token123",
            },
            {
                "projects": [{"projectId": "project-2"}],
            },
        ]
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.list_projects()

        assert len(result) == 2
        assert mock_projects.search.return_value.execute.call_count == 2

    def test_get_project(self, google_connector):
        """Test getting a specific project."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.get.return_value.execute.return_value = {
            "projectId": "test-project",
            "name": "Test Project",
            "lifecycleState": "ACTIVE",
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.get_project("test-project")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["projectId"], ExtendedString)
        assert result["projectId"] == "test-project"
        assert result["lifecycleState"] == "ACTIVE"

    def test_create_project(self, google_connector):
        """Test creating a new project."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.create.return_value.execute.return_value = {
            "projectId": "new-project",
            "name": "New Project",
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.create_project("new-project", "New Project")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["projectId"], ExtendedString)
        assert result["projectId"] == "new-project"

    def test_create_project_logs_redact_identifier_but_preserve_body(self, google_connector):
        """Project creation logs should not expose project IDs."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.create.return_value.execute.return_value = {
            "projectId": "sensitive-project",
            "name": "Sensitive Project",
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        google_connector.create_project("sensitive-project", "Sensitive Project")

        assert mock_projects.create.call_args.kwargs["body"]["projectId"] == "sensitive-project"
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "sensitive-project" not in logs

    def test_delete_project(self, google_connector):
        """Test deleting a project."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.delete.return_value.execute.return_value = {}
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        google_connector.delete_project("test-project")

        mock_projects.delete.assert_called_once_with(name="projects/test-project")


class TestFolders:
    """Tests for folder operations."""

    def test_list_folders(self, google_connector):
        """Test listing folders."""
        mock_service = MagicMock()
        mock_folders = mock_service.folders.return_value
        mock_folders.list.return_value.execute.return_value = {
            "folders": [
                {"name": "folders/123", "displayName": "Folder One"},
                {"name": "folders/456", "displayName": "Folder Two"},
            ]
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.list_folders(parent="organizations/123456")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["displayName"], ExtendedString)
        assert len(result) == 2
        assert result[0]["displayName"] == "Folder One"


class TestIAM:
    """Tests for IAM operations."""

    def test_get_iam_policy(self, google_connector):
        """Test getting IAM policy."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.getIamPolicy.return_value.execute.return_value = {
            "bindings": [
                {
                    "role": "roles/owner",
                    "members": ["user:owner@example.com"],
                }
            ],
            "etag": "BwXYZ",
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        result = google_connector.get_iam_policy("test-project")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["bindings"], ExtendedList)
        assert len(result["bindings"]) == 1
        assert result["bindings"][0]["role"] == "roles/owner"

    def test_set_iam_policy(self, google_connector):
        """Test setting IAM policy."""
        mock_service = MagicMock()
        mock_projects = mock_service.projects.return_value
        mock_projects.setIamPolicy.return_value.execute.return_value = {
            "bindings": [
                {
                    "role": "roles/viewer",
                    "members": ["user:viewer@example.com"],
                }
            ],
        }
        google_connector.get_cloud_resource_manager_service = MagicMock(return_value=mock_service)

        policy = extend_data(
            {
                "bindings": [
                    {
                        "role": "roles/viewer",
                        "members": ["user:viewer@example.com"],
                    }
                ]
            }
        )
        result = google_connector.set_iam_policy("test-project", policy)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["bindings"], ExtendedList)
        assert result["bindings"][0]["role"] == "roles/viewer"
        call_body = mock_projects.setIamPolicy.call_args.kwargs["body"]
        assert isinstance(call_body["policy"], dict)

    def test_add_iam_binding_logs_redact_member_and_resource_but_preserve_policy(self, google_connector):
        """IAM binding logs should redact member/resource identifiers without changing policy."""
        google_connector.get_iam_policy = MagicMock(return_value=extend_data({"bindings": []}))
        google_connector.set_iam_policy = MagicMock(return_value=extend_data({"bindings": []}))

        google_connector.add_iam_binding(
            "sensitive-project",
            "roles/viewer",
            "user:sensitive.user@example.com",
        )

        policy = google_connector.set_iam_policy.call_args.args[1]
        assert policy["bindings"][0]["members"] == ["user:sensitive.user@example.com"]
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "sensitive-project" not in logs
        assert "sensitive.user@example.com" not in logs
        assert "roles/viewer" in logs

    def test_list_service_accounts(self, google_connector):
        """Test listing service accounts."""
        mock_service = MagicMock()
        mock_accounts = mock_service.projects.return_value.serviceAccounts.return_value
        mock_accounts.list.return_value.execute.return_value = {
            "accounts": [
                {
                    "email": "sa1@test-project.iam.gserviceaccount.com",
                    "displayName": "Service Account 1",
                },
                {
                    "email": "sa2@test-project.iam.gserviceaccount.com",
                    "displayName": "Service Account 2",
                },
            ]
        }
        google_connector.get_iam_service = MagicMock(return_value=mock_service)

        result = google_connector.list_service_accounts("test-project")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["displayName"], ExtendedString)
        assert len(result) == 2
        assert result[0]["displayName"] == "Service Account 1"

    def test_create_service_account(self, google_connector):
        """Test creating a service account."""
        mock_service = MagicMock()
        mock_accounts = mock_service.projects.return_value.serviceAccounts.return_value
        mock_accounts.create.return_value.execute.return_value = {
            "email": "new-sa@test-project.iam.gserviceaccount.com",
            "displayName": "New Service Account",
        }
        google_connector.get_iam_service = MagicMock(return_value=mock_service)

        result = google_connector.create_service_account(
            "test-project",
            "new-sa",
            "New Service Account",
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["displayName"], ExtendedString)
        assert result["displayName"] == "New Service Account"
