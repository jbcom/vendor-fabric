# ruff: noqa: I001
"""Tests for AWS SSO/Identity Center operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("boto3")
pytest.importorskip("botocore")

from botocore.exceptions import ClientError

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from vendor_fabric.aws import AWSConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


@pytest.fixture
def aws_connector():
    """Create AWS connector with mocked clients."""
    with patch("vendor_fabric.aws.boto3"):
        connector = AWSConnector()
        connector.logger = MagicMock()
        return connector


class TestSSOIdentityStore:
    """Tests for SSO identity store operations."""

    def test_get_identity_store_id(self, aws_connector):
        """Test getting identity store ID."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [
                {
                    "IdentityStoreId": "d-1234567890",
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890",
                }
            ]
        }
        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        result = aws_connector.get_identity_store_id()

        assert isinstance(result, ExtendedString)
        assert result == "d-1234567890"
        aws_connector.get_aws_client.assert_called_once_with(client_name="sso-admin", execution_role_arn=None)
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "d-1234567890" not in logs

    def test_get_identity_store_id_no_instance(self, aws_connector):
        """Test getting identity store ID with no instances."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {"Instances": []}
        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        with pytest.raises(RuntimeError, match="No SSO instances found"):
            aws_connector.get_identity_store_id()

    def test_get_sso_instance_arn(self, aws_connector):
        """Test getting SSO instance ARN."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [
                {
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890",
                    "IdentityStoreId": "d-1234567890",
                }
            ]
        }
        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        result = aws_connector.get_sso_instance_arn()

        assert isinstance(result, ExtendedString)
        assert result == "arn:aws:sso:::instance/ssoins-1234567890"
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "arn:aws:sso:::instance/ssoins-1234567890" not in logs

    def test_get_sso_instance_arn_no_instance(self, aws_connector):
        """Test getting SSO instance ARN with no instances."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {"Instances": []}
        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        with pytest.raises(RuntimeError, match="No SSO instances found"):
            aws_connector.get_sso_instance_arn()


class TestSSOUsers:
    """Tests for SSO user operations."""

    def test_list_sso_users(self, aws_connector):
        """Test listing SSO users."""
        mock_identitystore = MagicMock()
        mock_identitystore.list_users.return_value = {
            "Users": [
                {
                    "UserId": "user-1",
                    "UserName": "john.doe",
                    "Name": {"GivenName": "John", "FamilyName": "Doe"},
                },
                {
                    "UserId": "user-2",
                    "UserName": "jane.smith",
                    "Name": {"GivenName": "Jane", "FamilyName": "Smith"},
                },
            ]
        }

        def get_client(client_name, **kwargs):
            if client_name == "identitystore":
                return mock_identitystore
            mock_sso_admin = MagicMock()
            mock_sso_admin.list_instances.return_value = {"Instances": [{"IdentityStoreId": "d-1234567890"}]}
            return mock_sso_admin

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)

        result = aws_connector.list_sso_users(unhump_users=False, flatten_name=False)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["user-1"], ExtendedDict)
        assert isinstance(result["user-1"]["UserName"], ExtendedString)
        assert len(result) == 2
        assert "user-1" in result
        assert "user-2" in result
        assert result["user-1"]["UserName"] == "john.doe"

    def test_list_sso_users_with_flatten_name(self, aws_connector):
        """Test listing SSO users with flattened names."""
        mock_identitystore = MagicMock()
        mock_identitystore.list_users.return_value = {
            "Users": [
                {
                    "UserId": "user-1",
                    "UserName": "john.doe",
                    "Name": {"GivenName": "John", "FamilyName": "Doe"},
                }
            ]
        }

        def get_client(client_name, **kwargs):
            if client_name == "identitystore":
                return mock_identitystore
            mock_sso_admin = MagicMock()
            mock_sso_admin.list_instances.return_value = {"Instances": [{"IdentityStoreId": "d-1234567890"}]}
            return mock_sso_admin

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)

        result = aws_connector.list_sso_users(unhump_users=False, flatten_name=True, identity_store_id="d-1234567890")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["user-1"], ExtendedDict)
        assert len(result) == 1
        assert result["user-1"]["GivenName"] == "John"
        assert result["user-1"]["FamilyName"] == "Doe"

    def test_list_sso_users_pagination(self, aws_connector):
        """Test listing SSO users with pagination."""
        mock_identitystore = MagicMock()
        mock_identitystore.list_users.side_effect = [
            {
                "Users": [{"UserId": "user-1", "UserName": "user1"}],
                "NextToken": "token123",
            },
            {"Users": [{"UserId": "user-2", "UserName": "user2"}]},
        ]

        aws_connector.get_aws_client = MagicMock(return_value=mock_identitystore)

        result = aws_connector.list_sso_users(identity_store_id="d-1234567890", unhump_users=False, flatten_name=False)

        assert len(result) == 2
        assert mock_identitystore.list_users.call_count == 2

    def test_list_sso_users_sort_by_name(self, aws_connector):
        """Test listing SSO users sorted by name."""
        mock_identitystore = MagicMock()
        mock_identitystore.list_users.return_value = {
            "Users": [
                {"UserId": "user-1", "UserName": "zoe"},
                {"UserId": "user-2", "UserName": "alice"},
                {"UserId": "user-3", "UserName": "mike"},
            ]
        }

        aws_connector.get_aws_client = MagicMock(return_value=mock_identitystore)

        result = aws_connector.list_sso_users(
            identity_store_id="d-1234567890",
            unhump_users=False,
            flatten_name=False,
            sort_by_name=True,
        )

        user_ids = list(result.keys())
        assert user_ids == ["user-2", "user-3", "user-1"]  # alice, mike, zoe

    def test_get_sso_user(self, aws_connector):
        """Test getting a specific SSO user."""
        mock_identitystore = MagicMock()
        mock_identitystore.describe_user.return_value = {
            "UserId": "user-1",
            "UserName": "john.doe",
            "Name": {"GivenName": "John"},
        }

        aws_connector.get_aws_client = MagicMock(return_value=mock_identitystore)

        result = aws_connector.get_sso_user("user-1", identity_store_id="d-1234567890")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["UserName"], ExtendedString)
        assert result["UserId"] == "user-1"
        assert result["UserName"] == "john.doe"

    def test_get_sso_user_not_found(self, aws_connector):
        """Test getting a non-existent SSO user."""
        mock_identitystore = MagicMock()
        error = ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DescribeUser")
        mock_identitystore.describe_user.side_effect = error

        aws_connector.get_aws_client = MagicMock(return_value=mock_identitystore)

        result = aws_connector.get_sso_user("missing-user", identity_store_id="d-1234567890")

        assert result is None

    def test_get_sso_user_other_error(self, aws_connector):
        """Test getting SSO user with other error."""
        mock_identitystore = MagicMock()
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "DescribeUser")
        mock_identitystore.describe_user.side_effect = error

        aws_connector.get_aws_client = MagicMock(return_value=mock_identitystore)

        with pytest.raises(ClientError):
            aws_connector.get_sso_user("user-1", identity_store_id="d-1234567890")


class TestSSOGroups:
    """Tests for SSO group operations."""

    def test_list_sso_groups(self, aws_connector):
        """Test listing SSO groups."""
        mock_identitystore = MagicMock()
        mock_identitystore.list_groups.return_value = {
            "Groups": [
                {"GroupId": "group-1", "DisplayName": "Admins"},
                {"GroupId": "group-2", "DisplayName": "Users"},
            ]
        }
        # Mock list_group_memberships - called once per group
        # For group-1: return one member with pagination, then empty
        # For group-2: return empty immediately
        mock_identitystore.list_group_memberships.side_effect = [
            {"GroupMemberships": [{"GroupId": "group-1", "MemberId": {"UserId": "user-1"}}], "NextToken": "token-1"},
            {"GroupMemberships": []},  # End of group-1 pagination
            {"GroupMemberships": []},  # group-2 has no members
        ]

        def get_client(client_name, **kwargs):
            if client_name == "identitystore":
                return mock_identitystore
            mock_sso_admin = MagicMock()
            mock_sso_admin.list_instances.return_value = {"Instances": [{"IdentityStoreId": "d-1234567890"}]}
            return mock_sso_admin

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)

        result = aws_connector.list_sso_groups(unhump_groups=False)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["group-1"], ExtendedDict)
        assert isinstance(result["group-1"]["DisplayName"], ExtendedString)
        assert len(result) == 2
        assert "group-1" in result
        assert result["group-1"]["DisplayName"] == "Admins"

    def test_create_sso_group(self, aws_connector):
        """Test creating an SSO group."""
        mock_identitystore = MagicMock()
        mock_identitystore.create_group.return_value = {
            "GroupId": "group-1",
            "IdentityStoreId": "d-1234567890",
        }

        def get_client(client_name, **kwargs):
            if client_name == "identitystore":
                return mock_identitystore
            mock_sso_admin = MagicMock()
            mock_sso_admin.list_instances.return_value = {"Instances": [{"IdentityStoreId": "d-1234567890"}]}
            return mock_sso_admin

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)

        result = aws_connector.create_sso_group("Admins", description="Admin group")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["GroupId"], ExtendedString)
        assert result["GroupId"] == "group-1"
        mock_identitystore.create_group.assert_called_once()

    def test_create_sso_group_logs_redact_identifiers_but_preserve_call_args(self, aws_connector):
        """Group mutation diagnostics should redact names and IDs."""
        mock_identitystore = MagicMock()
        mock_identitystore.create_group.return_value = {
            "GroupId": "group-sensitive-1",
            "IdentityStoreId": "d-sensitive",
        }

        def get_client(client_name, **kwargs):
            if client_name == "identitystore":
                return mock_identitystore
            mock_sso_admin = MagicMock()
            mock_sso_admin.list_instances.return_value = {"Instances": [{"IdentityStoreId": "d-sensitive"}]}
            return mock_sso_admin

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)

        aws_connector.create_sso_group("Executive Audit", description="Admin group")

        call_args = mock_identitystore.create_group.call_args.kwargs
        assert call_args["DisplayName"] == "Executive Audit"
        assert call_args["IdentityStoreId"] == "d-sensitive"
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "Executive Audit" not in logs
        assert "group-sensitive-1" not in logs
        assert "d-sensitive" not in logs

    def test_delete_sso_group(self, aws_connector):
        """Test deleting an SSO group."""
        mock_identitystore = MagicMock()
        mock_identitystore.delete_group.return_value = {}

        def get_client(client_name, **kwargs):
            if client_name == "identitystore":
                return mock_identitystore
            mock_sso_admin = MagicMock()
            mock_sso_admin.list_instances.return_value = {"Instances": [{"IdentityStoreId": "d-1234567890"}]}
            return mock_sso_admin

        aws_connector.get_aws_client = MagicMock(side_effect=get_client)

        aws_connector.delete_sso_group("group-1")

        mock_identitystore.delete_group.assert_called_once()


class TestSSOPermissionSets:
    """Tests for SSO permission set operations."""

    def test_list_permission_sets(self, aws_connector):
        """Test listing permission sets."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890"}]
        }
        mock_sso_admin.list_permission_sets.return_value = {
            "PermissionSets": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890/ps-1",
                "arn:aws:sso:::permissionSet/ssoins-1234567890/ps-2",
            ]
        }
        mock_sso_admin.describe_permission_set.side_effect = [
            {
                "PermissionSet": {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890/ps-1",
                    "Name": "AdminAccess",
                }
            },
            {
                "PermissionSet": {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890/ps-2",
                    "Name": "ReadOnlyAccess",
                }
            },
        ]
        mock_sso_admin.get_inline_policy_for_permission_set.return_value = {}
        mock_sso_admin.list_managed_policies_in_permission_set.return_value = {"AttachedManagedPolicies": []}

        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        result = aws_connector.list_permission_sets(unhump_sets=False)

        assert isinstance(result, ExtendedDict)
        assert len(result) == 2
        ps1_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890/ps-1"
        assert isinstance(result[ps1_arn], ExtendedDict)
        assert isinstance(result[ps1_arn]["Name"], ExtendedString)
        assert ps1_arn in result
        assert result[ps1_arn]["Name"] == "AdminAccess"


class TestSSOAccountAssignments:
    """Tests for SSO account assignment operations."""

    def test_list_account_assignments(self, aws_connector):
        """Test listing account assignments."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890/ps-1",
                    "PrincipalType": "USER",
                    "PrincipalId": "user-1",
                }
            ]
        }

        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        result = aws_connector.list_account_assignments(
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890",
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890/ps-1",
            unhump_assignments=False,
        )

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["AccountId"], ExtendedString)
        assert len(result) == 1
        assert result[0]["AccountId"] == "123456789012"
        assert result[0]["PrincipalType"] == "USER"

    def test_create_account_assignment(self, aws_connector):
        """Test creating an account assignment."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890"}]
        }
        mock_sso_admin.create_account_assignment.return_value = {
            "AccountAssignmentCreationStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "req-123",
            }
        }

        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        result = aws_connector.create_account_assignment(
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890/ps-1",
            principal_id="user-1",
            principal_type="USER",
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["AccountAssignmentCreationStatus"], ExtendedDict)
        assert "AccountAssignmentCreationStatus" in result
        mock_sso_admin.create_account_assignment.assert_called_once()

    def test_create_account_assignment_logs_redact_identifiers_but_preserve_call_args(self, aws_connector):
        """Account assignment diagnostics should redact resource identifiers."""
        mock_sso_admin = MagicMock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-sensitive"}]
        }
        mock_sso_admin.create_account_assignment.return_value = {
            "AccountAssignmentCreationStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "req-123",
            }
        }

        aws_connector.get_aws_client = MagicMock(return_value=mock_sso_admin)

        aws_connector.create_account_assignment(
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-sensitive/ps-sensitive",
            principal_id="user-sensitive-1",
            principal_type="USER",
        )

        call_args = mock_sso_admin.create_account_assignment.call_args.kwargs
        assert call_args["TargetId"] == "123456789012"
        assert call_args["PermissionSetArn"] == "arn:aws:sso:::permissionSet/ssoins-sensitive/ps-sensitive"
        assert call_args["PrincipalId"] == "user-sensitive-1"
        logs = _logged_text(aws_connector.logger)
        assert "[REDACTED]" in logs
        assert "123456789012" not in logs
        assert "user-sensitive-1" not in logs
        assert "ssoins-sensitive" not in logs
