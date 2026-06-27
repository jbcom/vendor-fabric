"""AWS connector built on extended-data primitives.

This package provides AWS operations organized into submodules:
- organizations: AWS Organizations and Control Tower account management
- sso: IAM Identity Center (SSO) operations
- s3: S3 bucket and object operations
- secrets: Secrets Manager operations
- ecs: ECS cluster and service operations

Usage:
    from cloud_connectors.aws import AWSConnector

    connector = AWSConnector()
    accounts = connector.get_accounts()
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, to_builtin
from extended_data.logging import Logging
from extended_data.primitives import is_nothing

from cloud_connectors._optional import require_extra
from cloud_connectors.aws._diagnostics import aws_operation_error, safe_aws_ref, safe_aws_text
from cloud_connectors.aws.organizations import AWSOrganizationsMixin
from cloud_connectors.aws.s3 import AWSS3Mixin
from cloud_connectors.aws.sso import AWSSSOmixin
from cloud_connectors.base import ConnectorBase


AWSSecretValue = str | ExtendedString | Mapping[str, Any] | None


if TYPE_CHECKING:
    import boto3

    from boto3.resources.base import ServiceResource
    from botocore.config import Config
    from botocore.exceptions import ClientError
else:
    boto3 = None
    Config = None
    ServiceResource = Any

    class ClientError(Exception):
        """Fallback exception used until botocore is imported."""


def _load_aws_sdk() -> Any:
    """Load boto3/botocore lazily so tool metadata can import without the aws extra."""
    global ClientError, Config, ServiceResource, boto3

    if boto3 is None:
        boto3 = require_extra("boto3", "aws")
        Config = require_extra("botocore.config", "aws").Config
        ClientError = require_extra("botocore.exceptions", "aws").ClientError
        ServiceResource = require_extra("boto3.resources.base", "aws").ServiceResource
    return boto3


class AWSConnector(AWSOrganizationsMixin, AWSSSOmixin, AWSS3Mixin, ConnectorBase):
    """AWS connector for boto3 client, resource, and external data operations.

    This first-class connector provides:
    - Session management and role assumption
    - Client/resource creation with retry configuration
    - Secrets Manager operations
    - Organizations, IAM Identity Center, and S3 operations
    """

    def __init__(
        self,
        execution_role_arn: str | None = None,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(logger=logger, **kwargs)
        self._boto3 = _load_aws_sdk()
        self.execution_role_arn = execution_role_arn
        self.aws_sessions: dict[str, dict[str, Any]] = {}
        self.default_aws_session = self._boto3.Session()

    # =========================================================================
    # Session Management
    # =========================================================================

    def assume_role(self, execution_role_arn: str, role_session_name: str) -> Any:
        """Assume an AWS IAM role and return a boto3 Session.

        Args:
            execution_role_arn: ARN of the role to assume.
            role_session_name: Name for the assumed role session.

        Returns:
            A boto3 Session with the assumed role credentials.

        Raises:
            RuntimeError: If role assumption fails.
        """
        safe_role_arn = safe_aws_ref(execution_role_arn)
        self.logger.info(f"Attempting to assume role: {safe_role_arn}")
        sts_client = self.default_aws_session.client("sts")

        try:
            response = sts_client.assume_role(RoleArn=execution_role_arn, RoleSessionName=role_session_name)
            credentials = response["Credentials"]
            self.logger.info(f"Successfully assumed role: {safe_role_arn}")
            return self._boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
        except ClientError as e:
            error_message = aws_operation_error("Failed to assume role", e, execution_role_arn)
            self.logger.error(error_message)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
            raise RuntimeError(error_message) from None

    def get_aws_session(
        self,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
    ) -> Any:
        """Get a boto3 Session, optionally assuming a role.

        Args:
            execution_role_arn: ARN of role to assume. If None, uses default session.
            role_session_name: Name for the assumed role session.

        Returns:
            A boto3 Session.
        """
        if not execution_role_arn:
            return self.default_aws_session

        if execution_role_arn not in self.aws_sessions:
            self.aws_sessions[execution_role_arn] = {}

        if not role_session_name:
            role_session_name = "ConnectorFabric"

        if role_session_name not in self.aws_sessions[execution_role_arn]:
            self.aws_sessions[execution_role_arn][role_session_name] = self.assume_role(
                execution_role_arn, role_session_name
            )

        return self.aws_sessions[execution_role_arn][role_session_name]

    # =========================================================================
    # Client/Resource Creation
    # =========================================================================

    @staticmethod
    def create_standard_retry_config(max_attempts: int = 5) -> Any:
        """Create a standard retry configuration.

        Args:
            max_attempts: Maximum retry attempts. Defaults to 5.

        Returns:
            A botocore Config with retry settings.
        """
        _load_aws_sdk()
        return Config(retries={"max_attempts": max_attempts, "mode": "standard"})

    def get_aws_client(
        self,
        client_name: str,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
        config: Any | None = None,
        **client_args: Any,
    ) -> Any:
        """Get a boto3 client for the specified service.

        Args:
            client_name: AWS service name (e.g., 's3', 'ec2', 'organizations').
            execution_role_arn: ARN of role to assume for cross-account access.
            role_session_name: Name for the assumed role session.
            config: Optional botocore Config. Defaults to standard retry config.
            **client_args: Additional arguments passed to boto3 client.

        Returns:
            A boto3 client for the specified service.
        """
        session = self.get_aws_session(execution_role_arn, role_session_name)
        if config is None:
            config = self.create_standard_retry_config()
        return session.client(client_name, config=config, **client_args)

    def get_aws_resource(
        self,
        service_name: str,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
        config: Any | None = None,
        **resource_args: Any,
    ) -> Any:
        """Get a boto3 resource for the specified service.

        Args:
            service_name: AWS service name (e.g., 's3', 'ec2', 'dynamodb').
            execution_role_arn: ARN of role to assume for cross-account access.
            role_session_name: Name for the assumed role session.
            config: Optional botocore Config. Defaults to standard retry config.
            **resource_args: Additional arguments passed to boto3 resource.

        Returns:
            A boto3 resource for the specified service.

        Raises:
            RuntimeError: If resource creation fails.
        """
        session = self.get_aws_session(execution_role_arn, role_session_name)
        if config is None:
            config = self.create_standard_retry_config()

        try:
            return session.resource(service_name, config=config, **resource_args)
        except ClientError as e:
            error_message = aws_operation_error(
                f"Failed to create resource for service {service_name}",
                e,
                execution_role_arn,
                role_session_name,
            )
            self.logger.error(error_message)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
            raise RuntimeError(error_message) from None

    # =========================================================================
    # Identity Operations
    # =========================================================================

    def get_caller_account_id(self) -> ExtendedString:
        """Get the AWS account ID of the caller.

        Returns:
            The 12-digit AWS account ID.
        """
        sts = self.get_aws_client("sts")
        identity = sts.get_caller_identity()
        return self.extend_result(identity["Account"])

    # =========================================================================
    # Secrets Manager Operations
    # =========================================================================

    def get_secret(
        self,
        secret_id: str,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
        secretsmanager: Any | None = None,
    ) -> ExtendedString | None:
        """Get a single secret value from AWS Secrets Manager.

        Args:
            secret_id: The ARN or name of the secret to retrieve.
            execution_role_arn: ARN of role to assume for cross-account access.
            role_session_name: Session name for assumed role.
            secretsmanager: Optional pre-existing Secrets Manager client.

        Returns:
            The secret value as a string, or None if not found.
        """
        safe_secret_id = safe_aws_text(secret_id, secret_id)
        self.logger.debug(f"Getting AWS secret: {safe_secret_id}")

        if secretsmanager is None:
            secretsmanager = self.get_aws_client(
                client_name="secretsmanager",
                execution_role_arn=execution_role_arn or self.execution_role_arn,
                role_session_name=role_session_name,
            )

        try:
            response = secretsmanager.get_secret_value(SecretId=secret_id)
            self.logger.debug(f"Successfully retrieved secret: {safe_secret_id}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                self.logger.warning(f"Secret not found: {safe_secret_id}")
                return None
            error_message = aws_operation_error("Failed to get secret", e, secret_id)
            self.logger.error(error_message)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
            raise ValueError(error_message) from None

        if "SecretString" in response:
            return self.extend_result(response["SecretString"])
        return self.extend_result(response["SecretBinary"].decode("utf-8"))

    def list_secrets(
        self,
        filters: Sequence[Mapping[str, Any]] | None = None,
        prefix: str | None = None,
        get_secret_values: bool = False,
        skip_empty_secrets: bool = False,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
    ) -> ExtendedDict:
        """List secrets from AWS Secrets Manager.

        Args:
            filters: List of filter dicts for list_secrets API.
            prefix: Optional prefix for the AWS "name" filter.
            get_secret_values: If True, fetch actual secret values.
            skip_empty_secrets: If True, skip secrets with empty values.
            execution_role_arn: ARN of role to assume for cross-account access.
            role_session_name: Session name for assumed role.

        Returns:
            Dict mapping secret names to ARNs or values.

        Raises:
            ValueError: If prefix contains invalid characters.
        """
        self.logger.info("Listing AWS Secrets Manager secrets")

        if prefix and (".." in prefix or "\x00" in prefix):
            msg = "prefix contains invalid characters"
            raise ValueError(msg)

        if skip_empty_secrets:
            get_secret_values = True

        role_arn = execution_role_arn or self.execution_role_arn
        secretsmanager = self.get_aws_client(
            client_name="secretsmanager",
            execution_role_arn=role_arn,
            role_session_name=role_session_name,
        )

        secrets: dict[str, AWSSecretValue] = {}
        paginator = secretsmanager.get_paginator("list_secrets")

        effective_filters: list[dict[str, Any]] = []
        if filters:
            effective_filters.extend(dict(to_builtin(filter_item)) for filter_item in filters)
        if prefix:
            effective_filters.append({"Key": "name", "Values": [prefix]})

        paginate_kwargs: dict[str, Any] = {"IncludePlannedDeletion": False}
        if effective_filters:
            paginate_kwargs["Filters"] = effective_filters

        for page in paginator.paginate(**paginate_kwargs):
            for secret in page.get("SecretList", []):
                secret_name = secret["Name"]
                secret_arn = secret["ARN"]

                if get_secret_values:
                    secret_value = self.get_secret(
                        secret_id=secret_arn,
                        execution_role_arn=role_arn,
                        role_session_name=role_session_name,
                        secretsmanager=secretsmanager,
                    )

                    if is_nothing(secret_value) and skip_empty_secrets:
                        continue

                    secrets[secret_name] = secret_value
                else:
                    secrets[secret_name] = secret_arn

        self.logger.info(f"Retrieved {len(secrets)} secrets")
        return self.extend_result(secrets)

    def create_secret(
        self,
        name: str,
        secret_value: str,
        description: str = "",
        tags: Mapping[str, str] | None = None,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Create a new secret in AWS Secrets Manager."""
        if not name:
            msg = "name is required to create a secret"
            raise ValueError(msg)
        if is_nothing(secret_value):
            msg = "secret_value is required to create a secret"
            raise ValueError(msg)

        safe_name = safe_aws_text(name, name)
        self.logger.info(f"Creating AWS secret: {safe_name}")
        role_arn = execution_role_arn or self.execution_role_arn
        secretsmanager = self.get_aws_client(
            client_name="secretsmanager",
            execution_role_arn=role_arn,
        )

        create_kwargs: dict[str, Any] = {"Name": name, "SecretString": secret_value}
        if description:
            create_kwargs["Description"] = description
        if tags:
            create_kwargs["Tags"] = [{"Key": str(key), "Value": str(value)} for key, value in tags.items()]

        try:
            response = secretsmanager.create_secret(**create_kwargs)
            self.logger.info(f"Created AWS secret ARN: {safe_aws_text(response.get('ARN'), response.get('ARN'))}")
            return self.extend_result(response)
        except ClientError as exc:
            error_message = aws_operation_error("Failed to create secret", exc, name, secret_value)
            self.logger.error(error_message)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
            raise RuntimeError(error_message) from None

    def update_secret(
        self,
        secret_id: str,
        secret_value: str,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Update an existing secret value."""
        if not secret_id:
            msg = "secret_id is required to update a secret"
            raise ValueError(msg)
        if is_nothing(secret_value):
            msg = "secret_value is required to update a secret"
            raise ValueError(msg)

        safe_secret_id = safe_aws_text(secret_id, secret_id)
        self.logger.info(f"Updating AWS secret: {safe_secret_id}")

        role_arn = execution_role_arn or self.execution_role_arn
        secretsmanager = self.get_aws_client(
            client_name="secretsmanager",
            execution_role_arn=role_arn,
        )

        try:
            response = secretsmanager.update_secret(SecretId=secret_id, SecretString=secret_value)
            response_arn = response.get("ARN", secret_id)
            self.logger.info(f"Updated AWS secret ARN: {safe_aws_text(response_arn, response_arn)}")
            return self.extend_result(response)
        except ClientError as exc:
            error_message = aws_operation_error("Failed to update secret", exc, secret_id, secret_value)
            self.logger.error(error_message)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
            raise RuntimeError(error_message) from None

    def delete_secret(
        self,
        secret_id: str,
        force_delete: bool = False,
        recovery_window_days: int = 30,
        execution_role_arn: str | None = None,
    ) -> ExtendedDict:
        """Delete a secret from AWS Secrets Manager."""
        if not secret_id:
            msg = "secret_id is required to delete a secret"
            raise ValueError(msg)

        if not force_delete and not 7 <= recovery_window_days <= 30:
            msg = "recovery_window_days must be between 7 and 30 when not forcing deletion"
            raise ValueError(msg)

        safe_secret_id = safe_aws_text(secret_id, secret_id)
        self.logger.info(f"Deleting AWS secret: {safe_secret_id}")

        role_arn = execution_role_arn or self.execution_role_arn
        secretsmanager = self.get_aws_client(
            client_name="secretsmanager",
            execution_role_arn=role_arn,
        )

        delete_kwargs: dict[str, Any] = {"SecretId": secret_id}
        if force_delete:
            delete_kwargs["ForceDeleteWithoutRecovery"] = True
        else:
            delete_kwargs["RecoveryWindowInDays"] = recovery_window_days

        try:
            response = secretsmanager.delete_secret(**delete_kwargs)
            response_arn = response.get("ARN", secret_id)
            self.logger.info(f"Delete secret request submitted for: {safe_aws_text(response_arn, response_arn)}")
            return self.extend_result(response)
        except ClientError as exc:
            error_message = aws_operation_error("Failed to delete secret", exc, secret_id)
            self.logger.error(error_message)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
            raise RuntimeError(error_message) from None

    def delete_secrets_matching(
        self,
        prefix: str | None = None,
        force_delete: bool = False,
        dry_run: bool = True,
        execution_role_arn: str | None = None,
    ) -> ExtendedList[ExtendedString]:
        """Delete all secrets that match the provided name prefix."""
        if not prefix:
            msg = "prefix is required to delete matching secrets"
            raise ValueError(msg)

        safe_prefix = safe_aws_text(prefix, prefix)
        self.logger.info(f"Deleting secrets matching prefix: {safe_prefix} (dry_run={dry_run})")

        role_arn = execution_role_arn or self.execution_role_arn
        secrets = self.list_secrets(
            prefix=prefix,
            execution_role_arn=role_arn,
        )

        secret_arns: list[str] = []
        for secret_name, value in secrets.items():
            if isinstance(value, str):
                secret_arns.append(value)
            elif isinstance(value, Mapping) and "ARN" in value:
                secret_arns.append(value["ARN"])
            else:
                self.logger.debug(f"Skipping secret {safe_aws_text(secret_name, secret_name)} due to missing ARN data")

        if not secret_arns:
            self.logger.info(f"No secrets found for prefix: {safe_prefix}")
            return self.extend_result([])

        if dry_run:
            self.logger.info(f"Dry run enabled; would delete {len(secret_arns)} secrets for prefix {safe_prefix}")
            return self.extend_result(secret_arns)

        deleted_arns: list[str] = []
        for secret_arn in secret_arns:
            response = self.delete_secret(
                secret_id=secret_arn,
                force_delete=force_delete,
                recovery_window_days=30,
                execution_role_arn=role_arn,
            )
            deleted_arns.append(response.get("ARN", secret_arn))

        self.logger.info(f"Deleted {len(deleted_arns)} secrets for prefix {safe_prefix}")
        return self.extend_result(deleted_arns)

    def copy_secrets_to_s3(
        self,
        secrets: Mapping[str, AWSSecretValue],
        bucket: str,
        key: str,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
    ) -> ExtendedString:
        """Copy secrets dictionary to S3 as JSON.

        Args:
            secrets: Dictionary of secrets to upload.
            bucket: S3 bucket name.
            key: S3 object key.
            execution_role_arn: ARN of role to assume for S3 access.
            role_session_name: Session name for assumed role.

        Returns:
            S3 URI of uploaded object.
        """
        import json as json_module

        self.logger.info(f"Copying {len(secrets)} secrets to S3")

        s3_client = self.get_aws_client(
            client_name="s3",
            execution_role_arn=execution_role_arn or self.execution_role_arn,
            role_session_name=role_session_name,
        )

        body = json_module.dumps(to_builtin(secrets))
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )

        s3_uri = f"s3://{bucket}/{key}"
        self.logger.info("Uploaded secrets to S3")
        return self.extend_result(s3_uri)

    def load_secrets_by_prefix(
        self,
        prefix: str,
        *,
        strip_prefix: bool = True,
        uppercase_keys: bool = False,
        skip_empty_secrets: bool = True,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
    ) -> ExtendedDict:
        """Load AWS Secrets Manager values into a mapping keyed by secret name.

        Args:
            prefix: AWS Secrets Manager name prefix to load.
            strip_prefix: Remove the prefix from returned mapping keys.
            uppercase_keys: Uppercase returned mapping keys for env-style use.
            skip_empty_secrets: Skip missing or empty secret values.
            execution_role_arn: ARN of role to assume for cross-account access.
            role_session_name: Session name for assumed role.

        Returns:
            Mapping of transformed secret names to secret values.
        """
        if not prefix:
            msg = "prefix is required to load secrets"
            raise ValueError(msg)

        secrets = self.list_secrets(
            prefix=prefix,
            get_secret_values=True,
            skip_empty_secrets=skip_empty_secrets,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )

        loaded: dict[str, AWSSecretValue] = {}
        for secret_name, secret_value in secrets.items():
            key = str(secret_name)
            if strip_prefix and key.startswith(prefix):
                key = key.removeprefix(prefix)
            if uppercase_keys:
                key = key.upper()
            loaded[key] = secret_value

        return self.extend_result(loaded)


from cloud_connectors.aws.codedeploy import create_codedeploy_deployment, get_aws_codedeploy_deployments
from cloud_connectors.aws.tools import (
    get_crewai_tools,
    get_langchain_tools,
    get_strands_tools,
    get_tools,
)


__all__ = [
    # Core connector classes
    "AWSConnector",
    "AWSOrganizationsMixin",
    "AWSS3Mixin",
    "AWSSSOmixin",
    "create_codedeploy_deployment",
    "get_aws_codedeploy_deployments",
    "get_crewai_tools",
    "get_langchain_tools",
    "get_strands_tools",
    # Tools
    "get_tools",
]
