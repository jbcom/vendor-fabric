"""AWS IAM Identity Center (SSO) operations.

This module provides operations for managing AWS SSO users, groups,
permission sets, and account assignments through IAM Identity Center.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from deepmerge import always_merger
from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, to_builtin
from extended_data.primitives import is_nothing, unhump_map

from cloud_connectors.aws._diagnostics import safe_aws_ref


if TYPE_CHECKING:
    pass


class AWSSSOmixin:
    """Mixin providing AWS SSO/Identity Center operations.

    This mixin requires the base AWSConnector class to provide:
    - get_aws_client()
    - logger
    - execution_role_arn
    """

    if TYPE_CHECKING:
        logger: Any
        execution_role_arn: str | None

        def get_aws_client(
            self,
            client_name: str,
            execution_role_arn: str | None = None,
            role_session_name: str | None = None,
            config: Any | None = None,
            **client_args: Any,
        ) -> Any: ...

        def extend_result(self, value: Any) -> Any: ...

    def get_identity_store_id(
        self,
        execution_role_arn: str | None = None,
    ) -> ExtendedString:
        """Get the IAM Identity Center identity store ID.

        Args:
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The identity store ID.

        Raises:
            RuntimeError: If no SSO instance found.
        """
        self.logger.info("Getting IAM Identity Center identity store ID")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        sso_admin = self.get_aws_client(
            client_name="sso-admin",
            execution_role_arn=role_arn,
        )

        instances = sso_admin.list_instances()
        instance_list = instances.get("Instances", [])

        if not instance_list:
            msg = "No SSO instances found"
            raise RuntimeError(msg)

        identity_store_id = instance_list[0]["IdentityStoreId"]
        self.logger.info(f"Identity store ID: {safe_aws_ref(identity_store_id)}")
        return self.extend_result(identity_store_id)

    def get_sso_instance_arn(
        self,
        execution_role_arn: str | None = None,
    ) -> ExtendedString:
        """Get the IAM Identity Center instance ARN.

        Args:
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            The SSO instance ARN.

        Raises:
            RuntimeError: If no SSO instance found.
        """
        self.logger.info("Getting IAM Identity Center instance ARN")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        sso_admin = self.get_aws_client(
            client_name="sso-admin",
            execution_role_arn=role_arn,
        )

        instances = sso_admin.list_instances()
        instance_list = instances.get("Instances", [])

        if not instance_list:
            msg = "No SSO instances found"
            raise RuntimeError(msg)

        instance_arn = instance_list[0]["InstanceArn"]
        self.logger.info(f"SSO instance ARN: {safe_aws_ref(instance_arn)}")
        return self.extend_result(instance_arn)

    # =========================================================================
    # Users
    # =========================================================================

    def list_sso_users(
        self,
        identity_store_id: str | None = None,
        unhump_users: bool = True,
        flatten_name: bool = True,
        sort_by_name: bool = False,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """List all users from IAM Identity Center.

        Args:
            identity_store_id: Identity store ID. Auto-detected if not provided.
            unhump_users: Convert keys to snake_case. Defaults to True.
            flatten_name: Flatten Name sub-object into user dict. Defaults to True.
            sort_by_name: Sort users by UserName. Defaults to False.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary mapping user IDs to user data.
        """
        self.logger.info("Listing SSO users")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        users: dict[str, dict[str, Any]] = {}
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"IdentityStoreId": identity_store_id}
            if page_token:
                params["NextToken"] = page_token

            response = identitystore.list_users(**params)

            for user in response.get("Users", []):
                user_id = user["UserId"]

                # Flatten Name sub-object
                if flatten_name:
                    name_data = user.pop("Name", {})
                    merged_user = always_merger.merge(deepcopy(user), deepcopy(name_data))
                else:
                    merged_user = user

                users[user_id] = merged_user

            page_token = response.get("NextToken")
            if not page_token:
                break

        # Sort if requested
        if sort_by_name:
            users = dict(sorted(users.items(), key=lambda x: x[1].get("UserName", "")))

        if unhump_users:
            users = {k: unhump_map(v) for k, v in users.items()}

        self.logger.info(f"Retrieved {len(users)} SSO users")
        return self.extend_result(users)

    def get_sso_user(
        self,
        user_id: str,
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict | None:
        """Get a specific SSO user by ID.

        Args:
            user_id: The user ID.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            User dictionary or None if not found.
        """
        from botocore.exceptions import ClientError

        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        try:
            return self.extend_result(
                identitystore.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=user_id,
                )
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return None
            raise

    def create_sso_user(
        self,
        user_name: str,
        display_name: str,
        given_name: str | None = None,
        family_name: str | None = None,
        emails: Sequence[Mapping[str, Any]] | None = None,
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Create a user in IAM Identity Center.

        Args:
            user_name: Unique username.
            display_name: Display name.
            given_name: First name.
            family_name: Last name.
            emails: List of email objects with Value, Type, Primary keys.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Created user response.
        """
        safe_user_name = safe_aws_ref(user_name)
        self.logger.info(f"Creating SSO user: {safe_user_name}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        user_body: dict[str, Any] = {
            "IdentityStoreId": identity_store_id,
            "UserName": user_name,
            "DisplayName": display_name,
        }

        if given_name or family_name:
            user_body["Name"] = {}
            if given_name:
                user_body["Name"]["GivenName"] = given_name
            if family_name:
                user_body["Name"]["FamilyName"] = family_name

        if emails:
            user_body["Emails"] = to_builtin(list(emails))

        result = identitystore.create_user(**user_body)
        self.logger.info(f"Created SSO user: {safe_user_name} ({safe_aws_ref(result.get('UserId'))})")
        return self.extend_result(result)

    def delete_sso_user(
        self,
        user_id: str,
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> None:
        """Delete a user from IAM Identity Center.

        Args:
            user_id: The user ID to delete.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.
        """
        safe_user_id = safe_aws_ref(user_id)
        self.logger.info(f"Deleting SSO user: {safe_user_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        identitystore.delete_user(
            IdentityStoreId=identity_store_id,
            UserId=user_id,
        )
        self.logger.info(f"Deleted SSO user: {safe_user_id}")

    # =========================================================================
    # Groups
    # =========================================================================

    def list_sso_groups(
        self,
        identity_store_id: str | None = None,
        unhump_groups: bool = True,
        expand_members: bool = False,
        users: Mapping[str, Mapping[str, Any]] | None = None,
        sort_by_name: bool = False,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """List all groups from IAM Identity Center.

        Args:
            identity_store_id: Identity store ID. Auto-detected if not provided.
            unhump_groups: Convert keys to snake_case. Defaults to True.
            expand_members: Include full user data for members. Defaults to False.
            users: Pre-fetched users dict for member expansion. Auto-fetched if needed.
            sort_by_name: Sort groups by DisplayName. Defaults to False.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary mapping group IDs to group data with Members list/dict.
        """
        self.logger.info("Listing SSO groups")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        # Pre-fetch users if expanding members
        if expand_members and not users:
            self.logger.info("Fetching users for member expansion")
            users = self.list_sso_users(
                identity_store_id=identity_store_id,
                unhump_users=False,
                execution_role_arn=role_arn,
            )

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        groups: dict[str, dict[str, Any]] = {}
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"IdentityStoreId": identity_store_id}
            if page_token:
                params["NextToken"] = page_token

            response = identitystore.list_groups(**params)

            for group in response.get("Groups", []):
                group_id = group["GroupId"]

                # Get group memberships
                members = self._get_group_members(
                    group_id=group_id,
                    identity_store_id=identity_store_id,
                    identitystore=identitystore,
                    expand_members=expand_members,
                    users=users,
                )
                group["Members"] = members

                groups[group_id] = group

            page_token = response.get("NextToken")
            if not page_token:
                break

        # Sort if requested
        if sort_by_name:
            groups = dict(sorted(groups.items(), key=lambda x: x[1].get("DisplayName", "")))

        if unhump_groups:
            groups = {k: unhump_map(v) for k, v in groups.items()}

        self.logger.info(f"Retrieved {len(groups)} SSO groups")
        return self.extend_result(groups)

    def _get_group_members(
        self,
        group_id: str,
        identity_store_id: str,
        identitystore: Any,
        expand_members: bool = False,
        users: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[str] | dict[str, Mapping[str, Any]]:
        """Get members of an SSO group.

        Args:
            group_id: The group ID.
            identity_store_id: Identity store ID.
            identitystore: Pre-created identitystore client.
            expand_members: Return full user data instead of just IDs.
            users: Pre-fetched users dict for expansion.

        Returns:
            List of user IDs or dict mapping user IDs to user data.
        """
        members: list[str] | dict[str, Mapping[str, Any]] = {} if expand_members else []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "IdentityStoreId": identity_store_id,
                "GroupId": group_id,
            }
            if page_token:
                params["NextToken"] = page_token

            response = identitystore.list_group_memberships(**params)

            for membership in response.get("GroupMemberships", []):
                user_id = membership.get("MemberId", {}).get("UserId")
                if not user_id:
                    continue

                if expand_members and users:
                    user_data = users.get(user_id, {})
                    members[user_id] = user_data
                elif isinstance(members, list):
                    members.append(user_id)

            page_token = response.get("NextToken")
            if not page_token:
                break

        return members

    def create_sso_group(
        self,
        display_name: str,
        description: str = "",
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Create a group in IAM Identity Center.

        Args:
            display_name: Group display name.
            description: Group description.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Created group response.
        """
        safe_display_name = safe_aws_ref(display_name)
        self.logger.info(f"Creating SSO group: {safe_display_name}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        result = identitystore.create_group(
            IdentityStoreId=identity_store_id,
            DisplayName=display_name,
            Description=description,
        )
        self.logger.info(f"Created SSO group: {safe_display_name} ({safe_aws_ref(result.get('GroupId'))})")
        return self.extend_result(result)

    def delete_sso_group(
        self,
        group_id: str,
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> None:
        """Delete a group from IAM Identity Center.

        Args:
            group_id: The group ID to delete.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.
        """
        safe_group_id = safe_aws_ref(group_id)
        self.logger.info(f"Deleting SSO group: {safe_group_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        identitystore.delete_group(
            IdentityStoreId=identity_store_id,
            GroupId=group_id,
        )
        self.logger.info(f"Deleted SSO group: {safe_group_id}")

    def add_user_to_group(
        self,
        user_id: str,
        group_id: str,
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Add a user to an SSO group.

        Args:
            user_id: The user ID to add.
            group_id: The group ID.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Membership response.
        """
        safe_user_id = safe_aws_ref(user_id)
        safe_group_id = safe_aws_ref(group_id)
        self.logger.info(f"Adding user {safe_user_id} to group {safe_group_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        result = identitystore.create_group_membership(
            IdentityStoreId=identity_store_id,
            GroupId=group_id,
            MemberId={"UserId": user_id},
        )
        self.logger.info(f"Added user {safe_user_id} to group {safe_group_id}")
        return self.extend_result(result)

    def remove_user_from_group(
        self,
        membership_id: str,
        identity_store_id: str | None = None,
        execution_role_arn: str | None = None,
    ) -> None:
        """Remove a user from an SSO group.

        Args:
            membership_id: The membership ID to remove.
            identity_store_id: Identity store ID. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.
        """
        safe_membership_id = safe_aws_ref(membership_id)
        self.logger.info(f"Removing membership: {safe_membership_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not identity_store_id:
            identity_store_id = str(self.get_identity_store_id(execution_role_arn=role_arn))

        identitystore = self.get_aws_client(
            client_name="identitystore",
            execution_role_arn=role_arn,
        )

        identitystore.delete_group_membership(
            IdentityStoreId=identity_store_id,
            MembershipId=membership_id,
        )
        self.logger.info(f"Removed membership: {safe_membership_id}")

    # =========================================================================
    # Permission Sets
    # =========================================================================

    def list_permission_sets(
        self,
        instance_arn: str | None = None,
        include_inline_policy: bool = True,
        include_managed_policies: bool = True,
        unhump_sets: bool = True,
        sort_by_name: bool = False,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """List all permission sets from IAM Identity Center.

        Args:
            instance_arn: SSO instance ARN. Auto-detected if not provided.
            include_inline_policy: Fetch inline policy for each set. Defaults to True.
            include_managed_policies: Fetch managed policies for each set. Defaults to True.
            unhump_sets: Convert keys to snake_case. Defaults to True.
            sort_by_name: Sort by permission set name. Defaults to False.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Dictionary mapping permission set ARNs to permission set data.
        """
        self.logger.info("Listing SSO permission sets")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not instance_arn:
            instance_arn = str(self.get_sso_instance_arn(execution_role_arn=role_arn))

        sso_admin = self.get_aws_client(
            client_name="sso-admin",
            execution_role_arn=role_arn,
        )

        permission_sets: dict[str, dict[str, Any]] = {}
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"InstanceArn": instance_arn}
            if page_token:
                params["NextToken"] = page_token

            response = sso_admin.list_permission_sets(**params)

            for ps_arn in response.get("PermissionSets", []):
                # Get full details
                ps_details = sso_admin.describe_permission_set(
                    InstanceArn=instance_arn,
                    PermissionSetArn=ps_arn,
                )
                ps_data = ps_details.get("PermissionSet", {})

                # Get inline policy
                if include_inline_policy:
                    inline_resp = sso_admin.get_inline_policy_for_permission_set(
                        InstanceArn=instance_arn,
                        PermissionSetArn=ps_arn,
                    )
                    inline_policy = inline_resp.get("InlinePolicy")
                    if not is_nothing(inline_policy):
                        ps_data["InlinePolicy"] = inline_policy

                # Get managed policies
                if include_managed_policies:
                    managed_policies = self._get_managed_policies_for_permission_set(
                        instance_arn=instance_arn,
                        permission_set_arn=ps_arn,
                        sso_admin=sso_admin,
                    )
                    if managed_policies:
                        ps_data["ManagedPolicies"] = managed_policies

                permission_sets[ps_arn] = ps_data

            page_token = response.get("NextToken")
            if not page_token:
                break

        # Sort if requested
        if sort_by_name:
            permission_sets = dict(sorted(permission_sets.items(), key=lambda x: x[1].get("Name", "")))

        if unhump_sets:
            permission_sets = {k: unhump_map(v) for k, v in permission_sets.items()}

        self.logger.info(f"Retrieved {len(permission_sets)} permission sets")
        return self.extend_result(permission_sets)

    def _get_managed_policies_for_permission_set(
        self,
        instance_arn: str,
        permission_set_arn: str,
        sso_admin: Any,
    ) -> list[dict[str, Any]]:
        """Get managed policies attached to a permission set."""
        managed_policies: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "InstanceArn": instance_arn,
                "PermissionSetArn": permission_set_arn,
            }
            if page_token:
                params["NextToken"] = page_token

            response = sso_admin.list_managed_policies_in_permission_set(**params)
            managed_policies.extend(response.get("AttachedManagedPolicies", []))

            page_token = response.get("NextToken")
            if not page_token:
                break

        return managed_policies

    # =========================================================================
    # Account Assignments
    # =========================================================================

    def list_account_assignments(
        self,
        account_id: str,
        permission_set_arn: str,
        instance_arn: str | None = None,
        unhump_assignments: bool = True,
        execution_role_arn: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List account assignments for a permission set.

        Args:
            account_id: AWS account ID.
            permission_set_arn: Permission set ARN.
            instance_arn: SSO instance ARN. Auto-detected if not provided.
            unhump_assignments: Convert keys to snake_case. Defaults to True.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            List of account assignment dictionaries.
        """
        safe_account_id = safe_aws_ref(account_id)
        self.logger.info(f"Listing account assignments for {safe_account_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not instance_arn:
            instance_arn = str(self.get_sso_instance_arn(execution_role_arn=role_arn))

        sso_admin = self.get_aws_client(
            client_name="sso-admin",
            execution_role_arn=role_arn,
        )

        assignments: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "InstanceArn": instance_arn,
                "AccountId": account_id,
                "PermissionSetArn": permission_set_arn,
            }
            if page_token:
                params["NextToken"] = page_token

            response = sso_admin.list_account_assignments(**params)
            assignments.extend(response.get("AccountAssignments", []))

            page_token = response.get("NextToken")
            if not page_token:
                break

        if unhump_assignments:
            assignments = [unhump_map(a) for a in assignments]

        self.logger.info(f"Retrieved {len(assignments)} assignments for {safe_account_id}")
        return self.extend_result(assignments)

    def create_account_assignment(
        self,
        account_id: str,
        permission_set_arn: str,
        principal_id: str,
        principal_type: str,
        instance_arn: str | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Create an account assignment.

        Args:
            account_id: AWS account ID.
            permission_set_arn: Permission set ARN.
            principal_id: User or group ID.
            principal_type: 'USER' or 'GROUP'.
            instance_arn: SSO instance ARN. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Account assignment creation status.
        """
        safe_principal_id = safe_aws_ref(principal_id)
        safe_account_id = safe_aws_ref(account_id)
        self.logger.info(f"Creating account assignment: {principal_type} {safe_principal_id} -> {safe_account_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not instance_arn:
            instance_arn = str(self.get_sso_instance_arn(execution_role_arn=role_arn))

        sso_admin = self.get_aws_client(
            client_name="sso-admin",
            execution_role_arn=role_arn,
        )

        result = sso_admin.create_account_assignment(
            InstanceArn=instance_arn,
            TargetId=account_id,
            TargetType="AWS_ACCOUNT",
            PermissionSetArn=permission_set_arn,
            PrincipalType=principal_type,
            PrincipalId=principal_id,
        )
        self.logger.info(f"Created account assignment for {safe_principal_id}")
        return self.extend_result(result)

    def delete_account_assignment(
        self,
        account_id: str,
        permission_set_arn: str,
        principal_id: str,
        principal_type: str,
        instance_arn: str | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Delete an account assignment.

        Args:
            account_id: AWS account ID.
            permission_set_arn: Permission set ARN.
            principal_id: User or group ID.
            principal_type: 'USER' or 'GROUP'.
            instance_arn: SSO instance ARN. Auto-detected if not provided.
            execution_role_arn: ARN of role to assume for cross-account access.

        Returns:
            Account assignment deletion status.
        """
        safe_principal_id = safe_aws_ref(principal_id)
        safe_account_id = safe_aws_ref(account_id)
        self.logger.info(f"Deleting account assignment: {principal_type} {safe_principal_id} -> {safe_account_id}")
        role_arn = execution_role_arn or getattr(self, "execution_role_arn", None)

        if not instance_arn:
            instance_arn = str(self.get_sso_instance_arn(execution_role_arn=role_arn))

        sso_admin = self.get_aws_client(
            client_name="sso-admin",
            execution_role_arn=role_arn,
        )

        result = sso_admin.delete_account_assignment(
            InstanceArn=instance_arn,
            TargetId=account_id,
            TargetType="AWS_ACCOUNT",
            PermissionSetArn=permission_set_arn,
            PrincipalType=principal_type,
            PrincipalId=principal_id,
        )
        self.logger.info(f"Deleted account assignment for {safe_principal_id}")
        return self.extend_result(result)
