"""Google Workspace (Admin Directory) operations.

This module provides operations for managing Google Workspace users and groups
through the Admin Directory API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from extended_data.containers import ExtendedDict, ExtendedList, to_builtin
from extended_data.primitives import unhump_map

from cloud_connectors.google._diagnostics import safe_google_ref, safe_google_text


class GoogleWorkspaceMixin:
    """Mixin providing Google Workspace operations.

    This mixin requires the base GoogleConnector class to provide:
    - get_admin_directory_service()
    - get_service()
    - logger
    """

    if TYPE_CHECKING:
        logger: Any
        service_account_info: dict[str, Any]

        def get_admin_directory_service(self, subject: str | None = None) -> Any: ...

        def extend_result(self, value: Any) -> Any: ...

    def list_workspace_users(
        self,
        domain: str | None = None,
        max_results: int = 500,
        unhump_users: bool = False,
        subject: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List users from Google Workspace.

        Args:
            domain: Optional domain to filter users.
            max_results: Maximum results per page. Defaults to 500.
            unhump_users: Convert keys to snake_case. Defaults to False.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            List of user dictionaries.
        """
        service = self.get_admin_directory_service(subject=subject)
        users: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"customer": "my_customer", "maxResults": max_results}
            if domain:
                params["domain"] = domain
            if page_token:
                params["pageToken"] = page_token

            response = service.users().list(**params).execute()
            users.extend(response.get("users", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(users)} users from Google Workspace")

        if unhump_users:
            users = [unhump_map(u) for u in users]

        return self.extend_result(users)

    def get_user(
        self,
        user_key: str,
        subject: str | None = None,
    ) -> ExtendedDict | None:
        """Get a specific user from Google Workspace.

        Args:
            user_key: Email or unique ID of the user.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            User dictionary or None if not found.
        """
        from googleapiclient.errors import HttpError

        service = self.get_admin_directory_service(subject=subject)

        try:
            return self.extend_result(service.users().get(userKey=user_key).execute())
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"User not found: {safe_google_ref(user_key)}")
                return None
            raise

    def create_user(
        self,
        primary_email: str,
        given_name: str,
        family_name: str,
        password: str | None = None,
        change_password_at_next_login: bool = True,
        org_unit_path: str = "/",
        subject: str | None = None,
        **additional_fields: Any,
    ) -> ExtendedDict:
        """Create a user in Google Workspace.

        Args:
            primary_email: Primary email address.
            given_name: First name.
            family_name: Last name.
            password: Initial password. Generated if not provided.
            change_password_at_next_login: Force password change. Defaults to True.
            org_unit_path: Organizational unit path. Defaults to '/'.
            subject: Email to impersonate for domain-wide delegation.
            **additional_fields: Additional user fields.

        Returns:
            Created user dictionary.
        """
        import secrets

        service = self.get_admin_directory_service(subject=subject)

        if not password:
            password = secrets.token_urlsafe(16)

        user_body = {
            "primaryEmail": primary_email,
            "name": {
                "givenName": given_name,
                "familyName": family_name,
            },
            "password": password,
            "changePasswordAtNextLogin": change_password_at_next_login,
            "orgUnitPath": org_unit_path,
            **additional_fields,
        }

        result = service.users().insert(body=to_builtin(user_body)).execute()
        self.logger.info(f"Created user: {safe_google_ref(primary_email)}")
        return self.extend_result(result)

    def update_user(
        self,
        user_key: str,
        subject: str | None = None,
        **fields: Any,
    ) -> ExtendedDict:
        """Update a user in Google Workspace.

        Args:
            user_key: Email or unique ID of the user.
            subject: Email to impersonate for domain-wide delegation.
            **fields: Fields to update.

        Returns:
            Updated user dictionary.
        """
        service = self.get_admin_directory_service(subject=subject)
        result = service.users().update(userKey=user_key, body=to_builtin(fields)).execute()
        self.logger.info(f"Updated user: {safe_google_ref(user_key)}")
        return self.extend_result(result)

    def delete_user(
        self,
        user_key: str,
        subject: str | None = None,
    ) -> None:
        """Delete a user from Google Workspace.

        Args:
            user_key: Email or unique ID of the user.
            subject: Email to impersonate for domain-wide delegation.
        """
        service = self.get_admin_directory_service(subject=subject)
        service.users().delete(userKey=user_key).execute()
        self.logger.info(f"Deleted user: {safe_google_ref(user_key)}")

    def list_workspace_groups(
        self,
        domain: str | None = None,
        max_results: int = 200,
        unhump_groups: bool = False,
        subject: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List groups from Google Workspace.

        Args:
            domain: Optional domain to filter groups.
            max_results: Maximum results per page. Defaults to 200.
            unhump_groups: Convert keys to snake_case. Defaults to False.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            List of group dictionaries.
        """
        service = self.get_admin_directory_service(subject=subject)
        groups: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"customer": "my_customer", "maxResults": max_results}
            if domain:
                params["domain"] = domain
            if page_token:
                params["pageToken"] = page_token

            response = service.groups().list(**params).execute()
            groups.extend(response.get("groups", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(groups)} groups from Google Workspace")

        if unhump_groups:
            groups = [unhump_map(g) for g in groups]

        return self.extend_result(groups)

    def get_group(
        self,
        group_key: str,
        subject: str | None = None,
    ) -> ExtendedDict | None:
        """Get a specific group from Google Workspace.

        Args:
            group_key: Email or unique ID of the group.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            Group dictionary or None if not found.
        """
        from googleapiclient.errors import HttpError

        service = self.get_admin_directory_service(subject=subject)

        try:
            return self.extend_result(service.groups().get(groupKey=group_key).execute())
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"Group not found: {safe_google_ref(group_key)}")
                return None
            raise

    def create_group(
        self,
        email: str,
        name: str,
        description: str = "",
        subject: str | None = None,
    ) -> ExtendedDict:
        """Create a group in Google Workspace.

        Args:
            email: Group email address.
            name: Display name.
            description: Group description.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            Created group dictionary.
        """
        service = self.get_admin_directory_service(subject=subject)

        group_body = {
            "email": email,
            "name": name,
            "description": description,
        }

        result = service.groups().insert(body=to_builtin(group_body)).execute()
        self.logger.info(f"Created group: {safe_google_ref(email)}")
        return self.extend_result(result)

    def delete_group(
        self,
        group_key: str,
        subject: str | None = None,
    ) -> None:
        """Delete a group from Google Workspace.

        Args:
            group_key: Email or unique ID of the group.
            subject: Email to impersonate for domain-wide delegation.
        """
        service = self.get_admin_directory_service(subject=subject)
        service.groups().delete(groupKey=group_key).execute()
        self.logger.info(f"Deleted group: {safe_google_ref(group_key)}")

    def list_group_members(
        self,
        group_key: str,
        roles: list[str] | None = None,
        unhump_members: bool = False,
        subject: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List members of a Google Workspace group.

        Args:
            group_key: Email or unique ID of the group.
            roles: Filter by roles (OWNER, MANAGER, MEMBER). Defaults to all.
            unhump_members: Convert keys to snake_case. Defaults to False.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            List of member dictionaries.
        """
        service = self.get_admin_directory_service(subject=subject)
        members: list[dict[str, Any]] = []
        page_token = None

        while True:
            params: dict[str, Any] = {"groupKey": group_key}
            if roles:
                params["roles"] = ",".join(roles)
            if page_token:
                params["pageToken"] = page_token

            response = service.members().list(**params).execute()
            members.extend(response.get("members", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        self.logger.info(f"Retrieved {len(members)} members from group {safe_google_ref(group_key)}")

        if unhump_members:
            members = [unhump_map(m) for m in members]

        return self.extend_result(members)

    def add_group_member(
        self,
        group_key: str,
        email: str,
        role: str = "MEMBER",
        subject: str | None = None,
    ) -> ExtendedDict:
        """Add a member to a Google Workspace group.

        Args:
            group_key: Email or unique ID of the group.
            email: Email of the member to add.
            role: Member role (OWNER, MANAGER, MEMBER). Defaults to MEMBER.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            Created member dictionary.
        """
        service = self.get_admin_directory_service(subject=subject)

        member_body = {
            "email": email,
            "role": role,
        }

        result = service.members().insert(groupKey=group_key, body=to_builtin(member_body)).execute()
        self.logger.info(f"Added {safe_google_ref(email)} to group {safe_google_ref(group_key)} with role {role}")
        return self.extend_result(result)

    def remove_group_member(
        self,
        group_key: str,
        member_key: str,
        subject: str | None = None,
    ) -> None:
        """Remove a member from a Google Workspace group.

        Args:
            group_key: Email or unique ID of the group.
            member_key: Email or unique ID of the member.
            subject: Email to impersonate for domain-wide delegation.
        """
        service = self.get_admin_directory_service(subject=subject)
        service.members().delete(groupKey=group_key, memberKey=member_key).execute()
        self.logger.info(f"Removed {safe_google_ref(member_key)} from group {safe_google_ref(group_key)}")

    def list_org_units(
        self,
        org_unit_path: str = "/",
        org_unit_type: str = "all",
        subject: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List organizational units in Google Workspace.

        Args:
            org_unit_path: Parent org unit path. Defaults to '/'.
            org_unit_type: Type filter (all, children, allIncludingParent).
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            List of org unit dictionaries.
        """
        service = self.get_admin_directory_service(subject=subject)

        response = (
            service.orgunits()
            .list(
                customerId="my_customer",
                orgUnitPath=org_unit_path,
                type=org_unit_type,
            )
            .execute()
        )

        org_units = response.get("organizationUnits", [])
        self.logger.info(f"Retrieved {len(org_units)} org units")
        return self.extend_result(org_units)

    def create_or_update_user(
        self,
        primary_email: str,
        given_name: str,
        family_name: str,
        password: str | None = None,
        update_if_exists: bool = False,
        change_password_at_next_login: bool = True,
        org_unit_path: str = "/",
        subject: str | None = None,
        **additional_fields: Any,
    ) -> ExtendedDict:
        """Create or update a user in Google Workspace.

        This method provides terraform-style idempotent user management.
        If update_if_exists is True and the user exists, it updates instead of failing.

        Args:
            primary_email: Primary email address.
            given_name: First name.
            family_name: Last name.
            password: Initial password. Generated if not provided.
            update_if_exists: If True, update existing user instead of failing.
            change_password_at_next_login: Force password change. Defaults to True.
            org_unit_path: Organizational unit path. Defaults to '/'.
            subject: Email to impersonate for domain-wide delegation.
            **additional_fields: Additional user fields.

        Returns:
            Created or updated user dictionary.
        """
        import secrets

        from googleapiclient.errors import HttpError

        service = self.get_admin_directory_service(subject=subject)

        if not password:
            password = secrets.token_urlsafe(16)

        user_body: dict[str, Any] = {
            "primaryEmail": primary_email,
            "name": {
                "givenName": given_name,
                "familyName": family_name,
            },
            "password": password,
            "changePasswordAtNextLogin": change_password_at_next_login,
            "orgUnitPath": org_unit_path,
            **additional_fields,
        }

        # Check if user exists
        try:
            existing = service.users().get(userKey=primary_email).execute()
            if update_if_exists:
                # Update existing user
                result = service.users().update(userKey=primary_email, body=to_builtin(user_body)).execute()
                self.logger.info(f"Updated existing user: {safe_google_ref(primary_email)}")
                return self.extend_result(result)
            self.logger.info(f"User already exists: {safe_google_ref(primary_email)}")
            return self.extend_result(existing)
        except HttpError as e:
            if e.resp.status != 404:
                raise
            # User doesn't exist, create new

        result = service.users().insert(body=to_builtin(user_body)).execute()
        self.logger.info(f"Created user: {safe_google_ref(primary_email)}")
        return self.extend_result(result)

    def create_or_update_group(
        self,
        email: str,
        name: str,
        description: str = "",
        update_if_exists: bool = False,
        subject: str | None = None,
        **additional_fields: Any,
    ) -> ExtendedDict:
        """Create or update a group in Google Workspace.

        This method provides terraform-style idempotent group management.
        If update_if_exists is True and the group exists, it updates instead of failing.

        Args:
            email: Group email address.
            name: Display name.
            description: Group description.
            update_if_exists: If True, update existing group instead of failing.
            subject: Email to impersonate for domain-wide delegation.
            **additional_fields: Additional group fields.

        Returns:
            Created or updated group dictionary.
        """
        from googleapiclient.errors import HttpError

        service = self.get_admin_directory_service(subject=subject)

        group_body: dict[str, Any] = {
            "email": email,
            "name": name,
            "description": description,
            **additional_fields,
        }

        # Check if group exists
        try:
            existing = service.groups().get(groupKey=email).execute()
            if update_if_exists:
                # Update existing group
                result = service.groups().update(groupKey=email, body=to_builtin(group_body)).execute()
                self.logger.info(f"Updated existing group: {safe_google_ref(email)}")
                return self.extend_result(result)
            self.logger.info(f"Group already exists: {safe_google_ref(email)}")
            return self.extend_result(existing)
        except HttpError as e:
            if e.resp.status != 404:
                raise
            # Group doesn't exist, create new

        result = service.groups().insert(body=to_builtin(group_body)).execute()
        self.logger.info(f"Created group: {safe_google_ref(email)}")
        return self.extend_result(result)

    def list_available_licenses(
        self,
        customer_id: str = "my_customer",
        product_id: str | None = None,
        subject: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """List available Google Workspace licenses.

        Args:
            customer_id: Customer ID. Defaults to 'my_customer'.
            product_id: Filter by product (e.g., 'Google-Apps', 'Google-Vault').
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            List of license dictionaries.
        """
        from googleapiclient.errors import HttpError

        self.logger.info("Listing available Google Workspace licenses")

        # Get licensing service
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials_class = cast(Any, service_account.Credentials)
        credentials = credentials_class.from_service_account_info(
            self.service_account_info,
            scopes=["https://www.googleapis.com/auth/apps.licensing"],
        )

        if subject:
            credentials = credentials.with_subject(subject)

        service = build("licensing", "v1", credentials=credentials, cache_discovery=False)

        licenses: list[dict[str, Any]] = []

        # Common product IDs to check
        product_ids = (
            [product_id]
            if product_id
            else [
                "Google-Apps",
                "101031",  # Google Workspace Enterprise Plus
                "101034",  # Google Workspace Business Starter
                "101037",  # Google Workspace Business Standard
                "101038",  # Google Workspace Business Plus
                "Google-Vault",
            ]
        )

        for prod_id in product_ids:
            try:
                page_token = None
                while True:
                    params: dict[str, Any] = {
                        "productId": prod_id,
                        "customerId": customer_id,
                    }
                    if page_token:
                        params["pageToken"] = page_token

                    response = service.licenseAssignments().listForProduct(**params).execute()

                    for item in response.get("items", []):
                        item["productId"] = prod_id
                        licenses.append(item)

                    page_token = response.get("nextPageToken")
                    if not page_token:
                        break

            except HttpError as e:
                if e.resp.status == 404:
                    # Product not available
                    self.logger.debug(f"Product {safe_google_ref(prod_id)} not available")
                elif e.resp.status == 403:
                    self.logger.debug(f"No access to product {safe_google_ref(prod_id)}")
                else:
                    self.logger.warning(
                        f"Error listing licenses for {safe_google_ref(prod_id)}: {safe_google_text(e, prod_id)}"
                    )

        self.logger.info(f"Retrieved {len(licenses)} license assignments")
        return self.extend_result(licenses)

    def get_license_summary(
        self,
        customer_id: str = "my_customer",
        subject: str | None = None,
    ) -> ExtendedDict:
        """Get a summary of license usage by product.

        Args:
            customer_id: Customer ID. Defaults to 'my_customer'.
            subject: Email to impersonate for domain-wide delegation.

        Returns:
            Dictionary mapping product IDs to usage counts.
        """
        licenses = self.list_available_licenses(
            customer_id=customer_id,
            subject=subject,
        )

        summary: dict[str, dict[str, int]] = {}
        for lic in licenses:
            product = lic.get("productId", "unknown")
            sku = lic.get("skuId", "unknown")
            key = f"{product}/{sku}"

            if key not in summary:
                summary[key] = {"assigned": 0}
            summary[key]["assigned"] += 1

        return self.extend_result(summary)
