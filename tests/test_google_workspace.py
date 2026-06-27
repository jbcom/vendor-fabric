# ruff: noqa: I001
"""Tests for Google Workspace (Admin Directory) operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.oauth2.service_account")
pytest.importorskip("googleapiclient")

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from cloud_connectors.google import GoogleConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


def _http_error(status: int):
    """Return a Google API HttpError with the requested status."""
    from googleapiclient.errors import HttpError

    response = MagicMock()
    response.status = status
    return HttpError(response, b"Google API error")


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


class TestWorkspaceUsers:
    """Tests for Workspace user operations."""

    def test_list_users(self, google_connector):
        """Test listing Workspace users."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.list.return_value.execute.return_value = {
            "users": [
                {"primaryEmail": "user1@example.com", "name": {"fullName": "User One"}},
                {"primaryEmail": "user2@example.com", "name": {"fullName": "User Two"}},
            ]
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["primaryEmail"], ExtendedString)
        assert len(result) == 2
        assert result[0]["primaryEmail"] == "user1@example.com"

    def test_list_users_with_domain(self, google_connector):
        """Test listing users filtered by domain."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.list.return_value.execute.return_value = {"users": [{"primaryEmail": "user1@example.com"}]}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_users(domain="example.com")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 1
        call_args = mock_users.list.call_args[1]
        assert call_args["domain"] == "example.com"

    def test_list_users_pagination(self, google_connector):
        """Test listing users with pagination."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.list.return_value.execute.side_effect = [
            {
                "users": [{"primaryEmail": "user1@example.com"}],
                "nextPageToken": "token123",
            },
            {
                "users": [{"primaryEmail": "user2@example.com"}],
            },
        ]
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert mock_users.list.return_value.execute.call_count == 2

    def test_list_workspace_users_unhumps_and_uses_subject(self, google_connector):
        """Legacy Workspace user listing should still promote and unhump payloads."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.list.return_value.execute.side_effect = [
            {
                "users": [{"primaryEmail": "user1@example.com", "orgUnitPath": "/Engineering"}],
                "nextPageToken": "next",
            },
            {"users": [{"primaryEmail": "user2@example.com", "orgUnitPath": "/Sales"}]},
        ]
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_workspace_users(
            domain="example.com",
            max_results=100,
            unhump_users=True,
            subject="admin@example.com",
        )

        assert isinstance(result, ExtendedList)
        assert result[0]["primary_email"] == "user1@example.com"
        assert result[0]["org_unit_path"] == "/Engineering"
        google_connector.get_admin_directory_service.assert_called_once_with(subject="admin@example.com")
        first_call, second_call = mock_users.list.call_args_list
        assert first_call.kwargs == {"customer": "my_customer", "maxResults": 100, "domain": "example.com"}
        assert second_call.kwargs["pageToken"] == "next"

    def test_get_user(self, google_connector):
        """Test getting a specific user."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.get.return_value.execute.return_value = {
            "primaryEmail": "user1@example.com",
            "name": {"fullName": "User One"},
            "suspended": False,
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.get_user("user1@example.com")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["primaryEmail"], ExtendedString)
        assert result["primaryEmail"] == "user1@example.com"
        assert result["suspended"] is False

    def test_get_user_not_found(self, google_connector):
        """Test getting non-existent user."""
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_resp = MagicMock()
        mock_resp.status = 404
        error = HttpError(mock_resp, b"Not found")
        mock_users.get.return_value.execute.side_effect = error
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.get_user("missing@example.com")

        assert result is None

    def test_create_user(self, google_connector):
        """Test creating a new user."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.insert.return_value.execute.return_value = {
            "primaryEmail": "newuser@example.com",
            "name": {"givenName": "New", "familyName": "User"},
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_user(
            primary_email="newuser@example.com",
            given_name="New",
            family_name="User",
            password="SecurePass123!",
            customSchemas=extend_data({"HR": {"level": "5"}}),
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["primaryEmail"], ExtendedString)
        assert result["primaryEmail"] == "newuser@example.com"
        mock_users.insert.assert_called_once()
        body = mock_users.insert.call_args.kwargs["body"]
        assert isinstance(body, dict)
        assert isinstance(body["customSchemas"], dict)

    def test_update_user(self, google_connector):
        """Test updating a user."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.update.return_value.execute.return_value = {
            "primaryEmail": "user1@example.com",
            "suspended": True,
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.update_user(
            "user1@example.com",
            suspended=True,
            customSchemas=extend_data({"HR": {"level": "7"}}),
        )

        assert isinstance(result, ExtendedDict)
        assert result["suspended"] is True
        body = mock_users.update.call_args.kwargs["body"]
        assert isinstance(body, dict)
        assert isinstance(body["customSchemas"], dict)

    def test_update_user_logs_redact_identifier_but_preserve_call_args(self, google_connector):
        """Workspace user mutation logs should not expose user keys."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.update.return_value.execute.return_value = {
            "primaryEmail": "sensitive.user@example.com",
            "suspended": True,
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        google_connector.update_user("sensitive.user@example.com", suspended=True)

        assert mock_users.update.call_args.kwargs["userKey"] == "sensitive.user@example.com"
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "sensitive.user@example.com" not in logs

    def test_delete_user(self, google_connector):
        """Test deleting a user."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.delete.return_value.execute.return_value = {}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        google_connector.delete_user("user1@example.com")

        mock_users.delete.assert_called_once_with(userKey="user1@example.com")

    def test_create_or_update_user_returns_existing_when_updates_disabled(self, google_connector):
        """Idempotent user creation should return existing users without mutation by default."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.get.return_value.execute.return_value = {"primaryEmail": "existing@example.com"}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_or_update_user(
            primary_email="existing@example.com",
            given_name="Existing",
            family_name="User",
            password="SecurePass123!",
        )

        assert isinstance(result, ExtendedDict)
        assert result["primaryEmail"] == "existing@example.com"
        mock_users.update.assert_not_called()
        mock_users.insert.assert_not_called()
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "existing@example.com" not in logs

    def test_create_or_update_user_updates_existing_with_builtin_body(self, google_connector):
        """Idempotent user creation should lower extended update payloads before SDK calls."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.get.return_value.execute.return_value = {"primaryEmail": "existing@example.com"}
        mock_users.update.return_value.execute.return_value = {"primaryEmail": "existing@example.com", "updated": True}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_or_update_user(
            primary_email="existing@example.com",
            given_name="Existing",
            family_name="User",
            password="SecurePass123!",
            update_if_exists=True,
            customSchemas=extend_data({"HR": {"level": "5"}}),
        )

        assert isinstance(result, ExtendedDict)
        assert result["updated"] is True
        mock_users.insert.assert_not_called()
        body = mock_users.update.call_args.kwargs["body"]
        assert isinstance(body, dict)
        assert isinstance(body["customSchemas"], dict)
        assert body["customSchemas"] == {"HR": {"level": "5"}}

    def test_create_or_update_user_creates_when_missing(self, google_connector):
        """Idempotent user creation should insert when the user is not found."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.get.return_value.execute.side_effect = _http_error(404)
        mock_users.insert.return_value.execute.return_value = {"primaryEmail": "newuser@example.com"}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_or_update_user(
            primary_email="newuser@example.com",
            given_name="New",
            family_name="User",
            password="SecurePass123!",
        )

        assert isinstance(result, ExtendedDict)
        assert result["primaryEmail"] == "newuser@example.com"
        mock_users.insert.assert_called_once()

    def test_create_or_update_user_reraises_non_not_found_errors(self, google_connector):
        """Idempotent user creation should not mask unexpected Google API errors."""
        mock_service = MagicMock()
        mock_users = mock_service.users.return_value
        mock_users.get.return_value.execute.side_effect = _http_error(403)
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        with pytest.raises(Exception, match="Google API error"):
            google_connector.create_or_update_user(
                primary_email="blocked@example.com",
                given_name="Blocked",
                family_name="User",
                password="SecurePass123!",
            )


class TestWorkspaceGroups:
    """Tests for Workspace group operations."""

    def test_list_groups(self, google_connector):
        """Test listing Workspace groups."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.list.return_value.execute.return_value = {
            "groups": [
                {"email": "group1@example.com", "name": "Group One"},
                {"email": "group2@example.com", "name": "Group Two"},
            ]
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_groups()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["email"], ExtendedString)
        assert len(result) == 2
        assert result[0]["email"] == "group1@example.com"

    def test_list_groups_with_domain(self, google_connector):
        """Test listing groups filtered by domain."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.list.return_value.execute.return_value = {"groups": [{"email": "group1@example.com"}]}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_groups(domain="example.com")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 1
        call_args = mock_groups.list.call_args[1]
        assert call_args["domain"] == "example.com"

    def test_list_workspace_groups_unhumps_and_uses_subject(self, google_connector):
        """Legacy Workspace group listing should still promote and unhump payloads."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.list.return_value.execute.side_effect = [
            {
                "groups": [{"email": "group1@example.com", "directMembersCount": "5"}],
                "nextPageToken": "next",
            },
            {"groups": [{"email": "group2@example.com", "directMembersCount": "2"}]},
        ]
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_workspace_groups(
            domain="example.com",
            max_results=50,
            unhump_groups=True,
            subject="admin@example.com",
        )

        assert isinstance(result, ExtendedList)
        assert result[0]["direct_members_count"] == "5"
        google_connector.get_admin_directory_service.assert_called_once_with(subject="admin@example.com")
        first_call, second_call = mock_groups.list.call_args_list
        assert first_call.kwargs == {"customer": "my_customer", "maxResults": 50, "domain": "example.com"}
        assert second_call.kwargs["pageToken"] == "next"

    def test_get_group(self, google_connector):
        """Test getting a specific group."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.get.return_value.execute.return_value = {
            "email": "group1@example.com",
            "name": "Group One",
            "directMembersCount": "5",
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.get_group("group1@example.com")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["email"], ExtendedString)
        assert result["email"] == "group1@example.com"
        assert result["directMembersCount"] == "5"

    def test_get_group_not_found(self, google_connector):
        """Test getting non-existent group."""
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_resp = MagicMock()
        mock_resp.status = 404
        error = HttpError(mock_resp, b"Not found")
        mock_groups.get.return_value.execute.side_effect = error
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.get_group("missing@example.com")

        assert result is None

    def test_create_group(self, google_connector):
        """Test creating a new group."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.insert.return_value.execute.return_value = {
            "email": "newgroup@example.com",
            "name": "New Group",
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_group(
            email="newgroup@example.com",
            name="New Group",
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["email"], ExtendedString)
        assert result["email"] == "newgroup@example.com"

    def test_list_group_members(self, google_connector):
        """Test listing group members."""
        mock_service = MagicMock()
        mock_members = mock_service.members.return_value
        mock_members.list.return_value.execute.return_value = {
            "members": [
                {"email": "user1@example.com", "role": "MEMBER"},
                {"email": "user2@example.com", "role": "OWNER"},
            ]
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_group_members("group1@example.com")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[1]["role"], ExtendedString)
        assert len(result) == 2
        assert result[1]["role"] == "OWNER"

    def test_add_group_member(self, google_connector):
        """Test adding a member to a group."""
        mock_service = MagicMock()
        mock_members = mock_service.members.return_value
        mock_members.insert.return_value.execute.return_value = {
            "email": "user1@example.com",
            "role": "MEMBER",
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.add_group_member("group1@example.com", "user1@example.com")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["email"], ExtendedString)
        assert result["email"] == "user1@example.com"

    def test_add_group_member_logs_redact_identifiers_but_preserve_call_args(self, google_connector):
        """Workspace membership logs should not expose member or group keys."""
        mock_service = MagicMock()
        mock_members = mock_service.members.return_value
        mock_members.insert.return_value.execute.return_value = {
            "email": "sensitive.user@example.com",
            "role": "MEMBER",
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        google_connector.add_group_member("private-group@example.com", "sensitive.user@example.com")

        assert mock_members.insert.call_args.kwargs["groupKey"] == "private-group@example.com"
        assert mock_members.insert.call_args.kwargs["body"]["email"] == "sensitive.user@example.com"
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "private-group@example.com" not in logs
        assert "sensitive.user@example.com" not in logs

    def test_remove_group_member(self, google_connector):
        """Test removing a member from a group."""
        mock_service = MagicMock()
        mock_members = mock_service.members.return_value
        mock_members.delete.return_value.execute.return_value = {}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        google_connector.remove_group_member("group1@example.com", "user1@example.com")

        mock_members.delete.assert_called_once()

    def test_create_or_update_group_returns_existing_when_updates_disabled(self, google_connector):
        """Idempotent group creation should return existing groups without mutation by default."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.get.return_value.execute.return_value = {"email": "existing-group@example.com"}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_or_update_group(
            email="existing-group@example.com",
            name="Existing Group",
        )

        assert isinstance(result, ExtendedDict)
        assert result["email"] == "existing-group@example.com"
        mock_groups.update.assert_not_called()
        mock_groups.insert.assert_not_called()

    def test_create_or_update_group_updates_existing_with_additional_fields(self, google_connector):
        """Idempotent group creation should lower extended group payloads before SDK calls."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.get.return_value.execute.return_value = {"email": "existing-group@example.com"}
        mock_groups.update.return_value.execute.return_value = {"email": "existing-group@example.com", "updated": True}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_or_update_group(
            email="existing-group@example.com",
            name="Existing Group",
            update_if_exists=True,
            settings=extend_data({"whoCanPostMessage": "ALL_MEMBERS_CAN_POST"}),
        )

        assert isinstance(result, ExtendedDict)
        assert result["updated"] is True
        mock_groups.insert.assert_not_called()
        body = mock_groups.update.call_args.kwargs["body"]
        assert isinstance(body, dict)
        assert body["settings"] == {"whoCanPostMessage": "ALL_MEMBERS_CAN_POST"}

    def test_create_or_update_group_creates_when_missing(self, google_connector):
        """Idempotent group creation should insert when the group is not found."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.get.return_value.execute.side_effect = _http_error(404)
        mock_groups.insert.return_value.execute.return_value = {"email": "newgroup@example.com"}
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.create_or_update_group(
            email="newgroup@example.com",
            name="New Group",
        )

        assert isinstance(result, ExtendedDict)
        assert result["email"] == "newgroup@example.com"
        mock_groups.insert.assert_called_once()

    def test_create_or_update_group_reraises_non_not_found_errors(self, google_connector):
        """Idempotent group creation should not mask unexpected Google API errors."""
        mock_service = MagicMock()
        mock_groups = mock_service.groups.return_value
        mock_groups.get.return_value.execute.side_effect = _http_error(403)
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        with pytest.raises(Exception, match="Google API error"):
            google_connector.create_or_update_group(
                email="blocked-group@example.com",
                name="Blocked Group",
            )


class TestWorkspaceOrgUnits:
    """Tests for Workspace organizational unit operations."""

    def test_list_org_units(self, google_connector):
        """Test listing organizational units."""
        mock_service = MagicMock()
        mock_orgunits = mock_service.orgunits.return_value
        mock_orgunits.list.return_value.execute.return_value = {
            "organizationUnits": [
                {"name": "Engineering", "orgUnitPath": "/Engineering"},
                {"name": "Sales", "orgUnitPath": "/Sales"},
            ]
        }
        google_connector.get_admin_directory_service = MagicMock(return_value=mock_service)

        result = google_connector.list_org_units()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["name"], ExtendedString)
        assert len(result) == 2
        assert result[0]["name"] == "Engineering"


class TestWorkspaceLicenses:
    """Tests for Workspace license operations."""

    def test_list_available_licenses_uses_delegated_credentials_and_paginates(self, google_connector):
        """License listing should use the licensing scope, subject delegation, and pagination."""
        credentials = MagicMock(name="credentials")
        delegated_credentials = MagicMock(name="delegated_credentials")
        credentials.with_subject.return_value = delegated_credentials
        mock_service = MagicMock()
        mock_assignments = mock_service.licenseAssignments.return_value
        mock_assignments.listForProduct.return_value.execute.side_effect = [
            {
                "items": [{"skuId": "sku-1", "userId": "user1@example.com"}],
                "nextPageToken": "next",
            },
            {"items": [{"skuId": "sku-2", "userId": "user2@example.com"}]},
        ]

        with (
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials
            ) as from_info,
            patch("googleapiclient.discovery.build", return_value=mock_service) as build,
        ):
            result = google_connector.list_available_licenses(
                customer_id="customer-1",
                product_id="Google-Apps",
                subject="admin@example.com",
            )

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert result[0]["productId"] == "Google-Apps"
        assert result[1]["skuId"] == "sku-2"
        from_info.assert_called_once_with(
            google_connector.service_account_info,
            scopes=["https://www.googleapis.com/auth/apps.licensing"],
        )
        credentials.with_subject.assert_called_once_with("admin@example.com")
        build.assert_called_once_with(
            "licensing",
            "v1",
            credentials=delegated_credentials,
            cache_discovery=False,
        )
        first_call, second_call = mock_assignments.listForProduct.call_args_list
        assert first_call.kwargs == {"productId": "Google-Apps", "customerId": "customer-1"}
        assert second_call.kwargs["pageToken"] == "next"

    def test_list_available_licenses_ignores_unavailable_products(self, google_connector):
        """Unavailable or forbidden products should not fail broad license discovery."""
        credentials = MagicMock(name="credentials")
        mock_service = MagicMock()
        mock_assignments = mock_service.licenseAssignments.return_value
        mock_assignments.listForProduct.return_value.execute.side_effect = [
            _http_error(404),
            _http_error(403),
            {"items": [{"skuId": "sku-1"}]},
            {"items": []},
            {"items": []},
            {"items": []},
        ]

        with (
            patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials),
            patch("googleapiclient.discovery.build", return_value=mock_service),
        ):
            result = google_connector.list_available_licenses()

        assert isinstance(result, ExtendedList)
        assert result[0]["productId"] == "101034"
        assert mock_assignments.listForProduct.call_count == 6

    def test_list_available_licenses_logs_unexpected_product_errors(self, google_connector):
        """Unexpected product errors should be logged and redacted without aborting discovery."""
        credentials = MagicMock(name="credentials")
        mock_service = MagicMock()
        mock_assignments = mock_service.licenseAssignments.return_value
        mock_assignments.listForProduct.return_value.execute.side_effect = [_http_error(500)]

        with (
            patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials),
            patch("googleapiclient.discovery.build", return_value=mock_service),
        ):
            result = google_connector.list_available_licenses(product_id="private-product@example.com")

        assert result == []
        logs = _logged_text(google_connector.logger)
        assert "[REDACTED]" in logs
        assert "private-product@example.com" not in logs

    def test_get_license_summary_counts_assigned_skus(self, google_connector):
        """License summaries should aggregate promoted license payloads by product and SKU."""
        google_connector.list_available_licenses = MagicMock(
            return_value=extend_data(
                [
                    {"productId": "Google-Apps", "skuId": "sku-1"},
                    {"productId": "Google-Apps", "skuId": "sku-1"},
                    {"productId": "Google-Vault", "skuId": "sku-2"},
                    {"skuId": "sku-unknown"},
                ]
            )
        )

        result = google_connector.get_license_summary(customer_id="customer-1", subject="admin@example.com")

        assert isinstance(result, ExtendedDict)
        assert result["Google-Apps/sku-1"]["assigned"] == 2
        assert result["Google-Vault/sku-2"]["assigned"] == 1
        assert result["unknown/sku-unknown"]["assigned"] == 1
        google_connector.list_available_licenses.assert_called_once_with(
            customer_id="customer-1",
            subject="admin@example.com",
        )
