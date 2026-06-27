"""Provider capability functions for AWS operations.

This module exposes framework-agnostic Python functions plus capability metadata.
Agent framework wrappers belong in agentic-fabric.

Tools provided:
- aws_get_caller_account_id: Get current AWS account ID
- aws_list_s3_buckets: List S3 buckets
- aws_list_s3_objects: List objects in an S3 bucket
- aws_list_accounts: List AWS organization accounts
- aws_list_sso_users: List IAM Identity Center users
- aws_list_sso_groups: List IAM Identity Center groups
- aws_list_secrets: List secrets from Secrets Manager
- aws_get_secret: Get a secret value

"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from pydantic import BaseModel, Field


# =============================================================================
# Input Schemas
# =============================================================================


class GetCallerAccountIdSchema(BaseModel):
    """Schema for getting caller account ID."""


class ListS3BucketsSchema(BaseModel):
    """Schema for listing S3 buckets."""


class ListS3ObjectsSchema(BaseModel):
    """Schema for listing S3 objects."""

    bucket: str = Field(..., description="The name of the S3 bucket.")


class ListAccountsSchema(BaseModel):
    """Schema for listing AWS accounts."""


class ListSSOUsersSchema(BaseModel):
    """Schema for listing SSO users."""


class ListSSOGroupsSchema(BaseModel):
    """Schema for listing SSO groups."""


class ListSecretsSchema(BaseModel):
    """Schema for listing secrets."""

    prefix: str = Field("", description="Optional prefix to filter secrets by name.")
    get_values: bool = Field(False, description="If True, fetch actual secret values (slower).")


class GetSecretSchema(BaseModel):
    """Schema for getting a secret."""

    secret_id: str = Field(..., description="The ARN or name of the secret to retrieve.")


# =============================================================================
# Capability Implementation Functions
# =============================================================================


def get_caller_account_id() -> ExtendedDict:
    """Get the AWS account ID of the caller.

    Returns:
        Dict with account_id field.
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    account_id = connector.get_caller_account_id()
    return extend_data({"account_id": account_id})


def list_s3_buckets() -> ExtendedList[ExtendedDict]:
    """List S3 buckets in the account.

    Returns:
        List of bucket info (name, creation_date, region).
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    buckets = connector.list_s3_buckets()
    return extend_data(
        [
            {
                "name": name,
                "creation_date": str(data.get("CreationDate", "")),
                "region": data.get("region", ""),
            }
            for name, data in buckets.items()
        ]
    )


def list_s3_objects(bucket: str) -> ExtendedList[ExtendedDict]:
    """List objects in an S3 bucket.

    Args:
        bucket: The name of the S3 bucket.

    Returns:
        List of object info (key, size, last_modified).
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    objects_raw: Any = connector.list_objects(bucket)
    if isinstance(objects_raw, Mapping):
        objects = [{"key": key, **data} for key, data in objects_raw.items()]
    else:
        objects = objects_raw

    result: list[dict[str, Any]] = []
    for data in objects:
        if not isinstance(data, Mapping):
            continue
        result.append(
            {
                "key": data.get("key", data.get("Key", "")),
                "size": data.get("size", data.get("Size", 0)),
                "last_modified": str(data.get("last_modified", data.get("LastModified", ""))),
            }
        )
    return extend_data(result)


def list_accounts() -> ExtendedList[ExtendedDict]:
    """List AWS organization accounts.

    Returns:
        List of account info (id, name, email, status).
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    accounts = connector.get_accounts()
    return extend_data(
        [
            {
                "id": acc_id,
                "name": data.get("Name", ""),
                "email": data.get("Email", ""),
                "status": data.get("Status", ""),
            }
            for acc_id, data in accounts.items()
        ]
    )


def list_sso_users() -> ExtendedList[ExtendedDict]:
    """List IAM Identity Center users.

    Returns:
        List of user info (user_id, user_name, display_name, email).
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    users = connector.list_sso_users()
    return extend_data(
        [
            {
                "user_id": user_id,
                "user_name": data.get("user_name", ""),
                "display_name": data.get("display_name", ""),
                "email": data.get("primary_email", {}).get("value", ""),
            }
            for user_id, data in users.items()
        ]
    )


def list_sso_groups() -> ExtendedList[ExtendedDict]:
    """List IAM Identity Center groups.

    Returns:
        List of group info (group_id, display_name, member_count).
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    groups = connector.list_sso_groups()
    return extend_data(
        [
            {
                "group_id": group_id,
                "display_name": data.get("display_name", ""),
                "member_count": len(data.get("members", [])),
            }
            for group_id, data in groups.items()
        ]
    )


def list_secrets(
    prefix: str = "",
    get_values: bool = False,
) -> ExtendedList[ExtendedDict]:
    """List secrets from AWS Secrets Manager.

    Args:
        prefix: Optional prefix to filter secrets by name
        get_values: If True, fetch actual secret values

    Returns:
        List of secret info (name, arn, value).
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    # Align with tests: only pass arguments that match test expectations
    kwargs: dict[str, Any] = {}
    if prefix:
        kwargs["prefix"] = prefix
    if get_values:
        kwargs["get_secret_values"] = get_values

    secrets = connector.list_secrets(**kwargs)

    result: list[dict[str, Any]] = []
    for name, data in secrets.items():
        if isinstance(data, str):
            result.append({"name": name, "arn": data})
        elif data is None:
            result.append({"name": name, "arn": None, "value": None})
        else:
            result.append({"name": name, "arn": data.get("ARN"), "value": data})
    return extend_data(result)


def get_secret(secret_id: str) -> ExtendedDict:
    """Get a single secret value from AWS Secrets Manager.

    Args:
        secret_id: The ARN or name of the secret to retrieve

    Returns:
        Dict with secret_name, secret_value, and status.
    """
    from vendor_fabric.aws import AWSConnector

    connector = AWSConnector()
    value = connector.get_secret(secret_id)
    return extend_data(
        {
            "secret_name": secret_id,
            "secret_value": value,
            "status": "retrieved" if value is not None else "not_found",
        }
    )


# =============================================================================
# Tool Definitions
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "aws_get_caller_account_id",
        "description": "Get the AWS account ID of the current caller identity.",
        "func": get_caller_account_id,
        "schema": GetCallerAccountIdSchema,
    },
    {
        "name": "aws_list_s3_buckets",
        "description": "List all S3 buckets in the current AWS account.",
        "func": list_s3_buckets,
        "schema": ListS3BucketsSchema,
    },
    {
        "name": "aws_list_s3_objects",
        "description": "List objects in a specific S3 bucket.",
        "func": list_s3_objects,
        "schema": ListS3ObjectsSchema,
    },
    {
        "name": "aws_list_accounts",
        "description": "List AWS organization accounts.",
        "func": list_accounts,
        "schema": ListAccountsSchema,
    },
    {
        "name": "aws_list_sso_users",
        "description": "List IAM Identity Center users.",
        "func": list_sso_users,
        "schema": ListSSOUsersSchema,
    },
    {
        "name": "aws_list_sso_groups",
        "description": "List IAM Identity Center groups.",
        "func": list_sso_groups,
        "schema": ListSSOGroupsSchema,
    },
    {
        "name": "aws_list_secrets",
        "description": "List secrets from AWS Secrets Manager with optional name filtering.",
        "func": list_secrets,
        "schema": ListSecretsSchema,
    },
    {
        "name": "aws_get_secret",
        "description": "Retrieve a specific secret value from AWS Secrets Manager by ID or ARN.",
        "func": get_secret,
        "schema": GetSecretSchema,
    },
]


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Tool metadata
    "TOOL_DEFINITIONS",
    # Raw functions
    "get_caller_account_id",
    "get_secret",
    # Framework-specific getters
    "list_accounts",
    "list_s3_buckets",
    "list_s3_objects",
    "list_secrets",
    "list_sso_groups",
    "list_sso_users",
]
