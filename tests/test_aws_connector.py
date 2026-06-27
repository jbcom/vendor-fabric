# ruff: noqa: I001
"""Tests for AWSConnector."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, call, patch

import pytest

pytest.importorskip("boto3")
pytest.importorskip("botocore")

from botocore.exceptions import ClientError

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from cloud_connectors.aws import AWSConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


class TestAWSConnector:
    """Test suite for AWSConnector."""

    def test_init_without_role(self, base_connector_kwargs):
        """Test initialization without execution role."""
        connector = AWSConnector(**base_connector_kwargs)
        assert connector.execution_role_arn is None
        assert connector.aws_sessions == {}
        assert connector.default_aws_session is not None

    def test_init_with_role(self, base_connector_kwargs):
        """Test initialization with execution role."""
        role_arn = "arn:aws:iam::123456789012:role/TestRole"
        connector = AWSConnector(execution_role_arn=role_arn, **base_connector_kwargs)
        assert connector.execution_role_arn == role_arn

    @patch("cloud_connectors.aws.boto3.Session")
    def test_assume_role_success(self, mock_session_class, base_connector_kwargs):
        """Test successful role assumption."""
        mock_sts_client = MagicMock()
        mock_sts_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test-access-key",
                "SecretAccessKey": "test-secret-key",
                "SessionToken": "test-session-token",
                "Expiration": Mock(isoformat=lambda: "2024-12-31T23:59:59Z"),
            }
        }

        mock_default_session = MagicMock()
        mock_default_session.client.return_value = mock_sts_client
        mock_session_class.return_value = mock_default_session

        connector = AWSConnector(**base_connector_kwargs)
        connector.default_aws_session = mock_default_session

        role_arn = "arn:aws:iam::123456789012:role/TestRole"
        connector.assume_role(role_arn, "test-session")

        mock_sts_client.assume_role.assert_called_once_with(RoleArn=role_arn, RoleSessionName="test-session")

    @patch("cloud_connectors.aws.boto3.Session")
    def test_assume_role_failure(self, mock_session_class, base_connector_kwargs):
        """Test failed role assumption."""
        role_arn = "arn:aws:iam::123456789012:role/TestRole"
        mock_sts_client = MagicMock()
        mock_sts_client.assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": f"Not authorized for {role_arn} token=raw-token"}},
            "AssumeRole",
        )

        mock_default_session = MagicMock()
        mock_default_session.client.return_value = mock_sts_client
        mock_session_class.return_value = mock_default_session

        connector = AWSConnector(**base_connector_kwargs)
        connector.default_aws_session = mock_default_session

        with pytest.raises(RuntimeError, match="Failed to assume role") as exc_info:
            connector.assume_role(role_arn, "test-session")

        diagnostics = _logged_text(connector.logger) + str(exc_info.value)
        assert role_arn not in diagnostics
        assert "raw-token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    def test_get_aws_session_default(self, base_connector_kwargs):
        """Test getting default AWS session."""
        connector = AWSConnector(**base_connector_kwargs)
        session = connector.get_aws_session()
        assert session == connector.default_aws_session

    def test_create_standard_retry_config(self):
        """Test creating standard retry configuration."""
        config = AWSConnector.create_standard_retry_config(max_attempts=5)
        assert config.retries["max_attempts"] == 5
        assert config.retries["mode"] == "standard"

    @patch("cloud_connectors.aws.boto3.Session")
    def test_get_aws_client(self, mock_session_class, base_connector_kwargs):
        """Test getting AWS client."""
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        mock_session_class.return_value = mock_session

        connector = AWSConnector(**base_connector_kwargs)
        connector.default_aws_session = mock_session

        client = connector.get_aws_client("s3")

        assert client == mock_client
        mock_session.client.assert_called_once()

    @patch("cloud_connectors.aws.boto3.Session")
    def test_get_aws_resource(self, mock_session_class, base_connector_kwargs):
        """Test getting AWS resource."""
        mock_session = MagicMock()
        mock_resource = MagicMock()
        mock_session.resource.return_value = mock_resource
        mock_session_class.return_value = mock_session

        connector = AWSConnector(**base_connector_kwargs)
        connector.default_aws_session = mock_session

        resource = connector.get_aws_resource("s3")

        assert resource == mock_resource
        mock_session.resource.assert_called_once()

    @patch("cloud_connectors.aws.boto3.Session")
    def test_get_aws_resource_failure_redacts_exception_context(self, mock_session_class, base_connector_kwargs):
        """Resource creation failures should not chain raw provider exceptions into diagnostics."""
        mock_session = MagicMock()
        mock_session.resource.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied for arn:role/private token=raw-token"}},
            "CreateResource",
        )
        mock_session_class.return_value = mock_session

        connector = AWSConnector(**base_connector_kwargs)
        connector.default_aws_session = mock_session
        connector.get_aws_session = MagicMock(return_value=mock_session)

        with pytest.raises(RuntimeError) as exc_info:
            connector.get_aws_resource("s3", execution_role_arn="arn:role/private")

        diagnostics = _logged_text(connector.logger) + str(exc_info.value)
        assert "arn:role/private" not in diagnostics
        assert "raw-token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    def test_list_secrets_returns_arns_with_filters(self, base_connector_kwargs):
        """Ensure listing secrets returns ARNs when not fetching values."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_secretsmanager = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "SecretList": [
                    {"Name": "/vendors/foo", "ARN": "arn:foo"},
                    {"Name": "/vendors/bar", "ARN": "arn:bar"},
                ]
            }
        ]
        mock_secretsmanager.get_paginator.return_value = mock_paginator
        connector.get_aws_client = MagicMock(return_value=mock_secretsmanager)

        filters = [{"Key": "description", "Values": ["prod"]}]
        secrets = connector.list_secrets(filters=filters, prefix="/vendors/")

        assert isinstance(secrets, ExtendedDict)
        assert isinstance(secrets["/vendors/foo"], ExtendedString)
        assert secrets == {"/vendors/foo": "arn:foo", "/vendors/bar": "arn:bar"}
        connector.get_aws_client.assert_called_once_with(
            client_name="secretsmanager",
            execution_role_arn=None,
            role_session_name=None,
        )
        mock_paginator.paginate.assert_called_once_with(
            IncludePlannedDeletion=False,
            Filters=[
                {"Key": "description", "Values": ["prod"]},
                {"Key": "name", "Values": ["/vendors/"]},
            ],
        )

    def test_list_secrets_fetches_values_and_skips_empty(self, base_connector_kwargs):
        """Ensure fetching secret values respects skip_empty_secrets."""
        connector = AWSConnector(execution_role_arn="arn:aws:iam::123:role/default", **base_connector_kwargs)

        mock_secretsmanager = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "SecretList": [
                    {"Name": "secret/a", "ARN": "arn:a"},
                    {"Name": "secret/b", "ARN": "arn:b"},
                    {"Name": "secret/c", "ARN": "arn:c"},
                ]
            }
        ]
        mock_secretsmanager.get_paginator.return_value = mock_paginator
        connector.get_aws_client = MagicMock(return_value=mock_secretsmanager)

        with (
            patch.object(AWSConnector, "get_secret", side_effect=["value-a", None, "value-c"]) as mock_get_secret,
            patch("cloud_connectors.aws.is_nothing", side_effect=lambda value: value in (None, "", {})),
        ):
            secrets = connector.list_secrets(
                get_secret_values=True,
                skip_empty_secrets=True,
                execution_role_arn="arn:aws:iam::789:role/override",
                role_session_name="session",
            )

        assert isinstance(secrets, ExtendedDict)
        assert isinstance(secrets["secret/a"], ExtendedString)
        assert secrets == {"secret/a": "value-a", "secret/c": "value-c"}
        connector.get_aws_client.assert_called_once_with(
            client_name="secretsmanager",
            execution_role_arn="arn:aws:iam::789:role/override",
            role_session_name="session",
        )
        mock_paginator.paginate.assert_called_once_with(IncludePlannedDeletion=False)
        mock_get_secret.assert_has_calls(
            [
                call(
                    secret_id="arn:a",
                    execution_role_arn="arn:aws:iam::789:role/override",
                    role_session_name="session",
                    secretsmanager=mock_secretsmanager,
                ),
                call(
                    secret_id="arn:b",
                    execution_role_arn="arn:aws:iam::789:role/override",
                    role_session_name="session",
                    secretsmanager=mock_secretsmanager,
                ),
                call(
                    secret_id="arn:c",
                    execution_role_arn="arn:aws:iam::789:role/override",
                    role_session_name="session",
                    secretsmanager=mock_secretsmanager,
                ),
            ]
        )

    def test_list_secrets_rejects_path_traversal(self, base_connector_kwargs):
        """Ensure list_secrets rejects path traversal in prefix."""
        import pytest

        connector = AWSConnector(**base_connector_kwargs)

        # Should reject path traversal attempts
        with pytest.raises(ValueError, match="invalid characters"):
            connector.list_secrets(prefix="../../../etc/passwd")

        with pytest.raises(ValueError, match="invalid characters"):
            connector.list_secrets(prefix="secrets/../admin")

        # Should reject null bytes
        with pytest.raises(ValueError, match="invalid characters"):
            connector.list_secrets(prefix="secrets\x00admin")

    def test_list_secrets_does_not_preserve_name_prefix_alias(self, base_connector_kwargs):
        """Clean major-version surface should keep prefix as the only prefix keyword."""
        connector = AWSConnector(**base_connector_kwargs)

        with pytest.raises(TypeError, match="name_prefix"):
            connector.list_secrets(name_prefix="/vendors/")  # type: ignore[call-arg]

    def test_get_secret_returns_extended_string(self, base_connector_kwargs):
        """Ensure get_secret promotes returned secret strings."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "secret-value"}
        connector.get_aws_client = MagicMock(return_value=mock_client)

        value = connector.get_secret("arn:secret:test")

        assert isinstance(value, ExtendedString)
        assert value == "secret-value"

    def test_get_secret_redacts_client_error_diagnostics(self, base_connector_kwargs):
        """AWS secret lookup failures should not expose IDs or secret-bearing error text."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied token=raw_token password=hunter2"}},
            "GetSecretValue",
        )
        connector.get_aws_client = MagicMock(return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            connector.get_secret("prod/customer-private")

        diagnostics = _logged_text(connector.logger) + str(exc_info.value)
        assert "prod/customer-private" not in diagnostics
        assert "raw_token" not in diagnostics
        assert "hunter2" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    def test_get_secret_redacts_missing_secret_log(self, base_connector_kwargs):
        """AWS missing-secret logs should not expose raw requested IDs."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "missing"}},
            "GetSecretValue",
        )
        connector.get_aws_client = MagicMock(return_value=mock_client)

        assert connector.get_secret("prod/customer-private") is None

        logs = _logged_text(connector.logger)
        assert "prod/customer-private" not in logs
        assert "[REDACTED]" in logs

    def test_create_secret_with_tags_and_description(self, base_connector_kwargs):
        """Ensure create_secret builds payload and sends to AWS."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.create_secret.return_value = {"ARN": "arn:secret:test"}
        connector.get_aws_client = MagicMock(return_value=mock_client)

        response = connector.create_secret(
            name="/vendors/test",
            secret_value="super-secret",
            description="Test secret",
            tags={"env": "dev", "team": "platform"},
            execution_role_arn="arn:role:override",
        )

        assert isinstance(response, ExtendedDict)
        assert isinstance(response["ARN"], ExtendedString)
        assert response == {"ARN": "arn:secret:test"}
        connector.get_aws_client.assert_called_once_with(
            client_name="secretsmanager",
            execution_role_arn="arn:role:override",
        )
        mock_client.create_secret.assert_called_once()
        assert mock_client.create_secret.call_args.kwargs["Name"] == "/vendors/test"
        assert mock_client.create_secret.call_args.kwargs["SecretString"] == "super-secret"
        assert mock_client.create_secret.call_args.kwargs["Description"] == "Test secret"
        assert mock_client.create_secret.call_args.kwargs["Tags"] == [
            {"Key": "env", "Value": "dev"},
            {"Key": "team", "Value": "platform"},
        ]

    def test_create_secret_requires_name(self, base_connector_kwargs):
        """Ensure create_secret validates required parameters."""
        connector = AWSConnector(**base_connector_kwargs)

        with pytest.raises(ValueError, match="name is required"):
            connector.create_secret(name="", secret_value="value")

    def test_create_secret_redacts_error_diagnostics(self, base_connector_kwargs):
        """AWS secret creation failures should not expose names, values, or exception secrets."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.create_secret.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied secret=raw-secret api_key=key_123"}},
            "CreateSecret",
        )
        connector.get_aws_client = MagicMock(return_value=mock_client)

        with pytest.raises(RuntimeError) as exc_info:
            connector.create_secret(name="/vendors/private", secret_value="super-secret")

        diagnostics = _logged_text(connector.logger) + str(exc_info.value)
        assert "/vendors/private" not in diagnostics
        assert "super-secret" not in diagnostics
        assert "raw-secret" not in diagnostics
        assert "key_123" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    def test_update_secret_calls_aws(self, base_connector_kwargs):
        """Ensure update_secret forwards call to boto3 client."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.update_secret.return_value = {"ARN": "arn:secret:test"}
        connector.get_aws_client = MagicMock(return_value=mock_client)

        response = connector.update_secret(
            secret_id="arn:secret:test",
            secret_value="updated",
            execution_role_arn="arn:role:override",
        )

        assert isinstance(response, ExtendedDict)
        assert isinstance(response["ARN"], ExtendedString)
        assert response == {"ARN": "arn:secret:test"}
        connector.get_aws_client.assert_called_once_with(
            client_name="secretsmanager",
            execution_role_arn="arn:role:override",
        )
        mock_client.update_secret.assert_called_once_with(SecretId="arn:secret:test", SecretString="updated")

    def test_delete_secret_with_recovery_window(self, base_connector_kwargs):
        """Ensure delete_secret honors recovery windows."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.delete_secret.return_value = {"ARN": "arn:secret:test"}
        connector.get_aws_client = MagicMock(return_value=mock_client)

        response = connector.delete_secret(
            secret_id="arn:secret:test",
            recovery_window_days=10,
            execution_role_arn="arn:role:override",
        )

        assert isinstance(response, ExtendedDict)
        assert isinstance(response["ARN"], ExtendedString)
        assert response == {"ARN": "arn:secret:test"}
        mock_client.delete_secret.assert_called_once_with(SecretId="arn:secret:test", RecoveryWindowInDays=10)

    def test_delete_secret_force_delete(self, base_connector_kwargs):
        """Ensure delete_secret can force delete without recovery."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        mock_client.delete_secret.return_value = {"ARN": "arn:secret:test"}
        connector.get_aws_client = MagicMock(return_value=mock_client)

        connector.delete_secret(secret_id="arn:secret:test", force_delete=True)

        mock_client.delete_secret.assert_called_once_with(
            SecretId="arn:secret:test",
            ForceDeleteWithoutRecovery=True,
        )

    def test_delete_secret_invalid_recovery_window(self, base_connector_kwargs):
        """Ensure invalid recovery window raises error."""
        connector = AWSConnector(**base_connector_kwargs)

        with pytest.raises(ValueError, match="recovery_window_days"):
            connector.delete_secret(secret_id="arn:secret:test", recovery_window_days=60)

    def test_delete_secrets_matching_dry_run(self, base_connector_kwargs):
        """Ensure delete_secrets_matching can run dry without deletions."""
        connector = AWSConnector(**base_connector_kwargs)
        connector.list_secrets = MagicMock(return_value={"secret/a": "arn:a", "secret/b": "arn:b"})
        connector.delete_secret = MagicMock()

        to_delete = connector.delete_secrets_matching(
            prefix="/vendors/",
            dry_run=True,
            force_delete=False,
            execution_role_arn="arn:role:override",
        )

        assert isinstance(to_delete, ExtendedList)
        assert isinstance(to_delete[0], ExtendedString)
        assert to_delete == ["arn:a", "arn:b"]
        connector.delete_secret.assert_not_called()
        logs = _logged_text(connector.logger)
        assert "/vendors/" not in logs
        assert "[REDACTED]" in logs
        connector.list_secrets.assert_called_once_with(
            prefix="/vendors/",
            execution_role_arn="arn:role:override",
        )

    def test_delete_secrets_matching_executes_delete(self, base_connector_kwargs):
        """Ensure delete_secrets_matching deletes secrets when not dry run."""
        connector = AWSConnector(**base_connector_kwargs)
        connector.list_secrets = MagicMock(return_value={"secret/a": "arn:a", "secret/b": "arn:b"})
        connector.delete_secret = MagicMock(
            side_effect=[{"ARN": "arn:a"}, {"ARN": "arn:b"}],
        )

        deleted = connector.delete_secrets_matching(
            prefix="/vendors/",
            dry_run=False,
            force_delete=True,
            execution_role_arn="arn:role:override",
        )

        assert isinstance(deleted, ExtendedList)
        assert isinstance(deleted[0], ExtendedString)
        assert deleted == ["arn:a", "arn:b"]
        connector.delete_secret.assert_has_calls(
            [
                call(
                    secret_id="arn:a",
                    force_delete=True,
                    recovery_window_days=30,
                    execution_role_arn="arn:role:override",
                ),
                call(
                    secret_id="arn:b",
                    force_delete=True,
                    recovery_window_days=30,
                    execution_role_arn="arn:role:override",
                ),
            ]
        )

    def test_delete_secrets_matching_does_not_preserve_name_prefix_alias(self, base_connector_kwargs):
        """Clean major-version surface should keep prefix as the only deletion keyword."""
        connector = AWSConnector(**base_connector_kwargs)

        with pytest.raises(TypeError, match="name_prefix"):
            connector.delete_secrets_matching(name_prefix="/vendors/")  # type: ignore[call-arg]

    def test_copy_secrets_to_s3_unwraps_extended_data(self, base_connector_kwargs):
        """Ensure copy_secrets_to_s3 uploads JSON built from plain containers."""
        connector = AWSConnector(**base_connector_kwargs)
        mock_client = MagicMock()
        connector.get_aws_client = MagicMock(return_value=mock_client)

        uri = connector.copy_secrets_to_s3(
            secrets=extend_data({"TOKEN": "secret-value"}),
            bucket="target-bucket",
            key="secrets.json",
        )

        assert isinstance(uri, ExtendedString)
        assert uri == "s3://target-bucket/secrets.json"
        logs = _logged_text(connector.logger)
        assert "target-bucket" not in logs
        assert "secrets.json" not in logs
        mock_client.put_object.assert_called_once_with(
            Bucket="target-bucket",
            Key="secrets.json",
            Body=b'{"TOKEN": "secret-value"}',
            ContentType="application/json",
        )

    def test_load_secrets_by_prefix_returns_extended_mapping(self, base_connector_kwargs):
        """Ensure prefix-loaded secrets are promoted without vendor-specific naming."""
        connector = AWSConnector(**base_connector_kwargs)
        connector.list_secrets = MagicMock(return_value={"/services/github_token": "ghp_test"})

        secrets = connector.load_secrets_by_prefix(
            prefix="/services/",
            uppercase_keys=True,
            execution_role_arn="arn:role:override",
            role_session_name="session",
        )

        assert isinstance(secrets, ExtendedDict)
        assert isinstance(secrets["GITHUB_TOKEN"], ExtendedString)
        assert secrets == {"GITHUB_TOKEN": "ghp_test"}
        connector.list_secrets.assert_called_once_with(
            prefix="/services/",
            get_secret_values=True,
            skip_empty_secrets=True,
            execution_role_arn="arn:role:override",
            role_session_name="session",
        )

    def test_load_secrets_by_prefix_requires_prefix(self, base_connector_kwargs):
        """Ensure prefix loading fails loudly without a prefix."""
        connector = AWSConnector(**base_connector_kwargs)

        with pytest.raises(ValueError, match="prefix is required"):
            connector.load_secrets_by_prefix("")

    def test_aws_connector_does_not_keep_vendor_secret_loader_alias(self):
        """Clean major-version surface should not preserve the old vendor loader name."""
        assert not hasattr(AWSConnector, "load_vendors_from_asm")
