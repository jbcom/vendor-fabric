# ruff: noqa: I001
"""Tests for the AWS CodeDeploy helper module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("botocore")

from botocore.exceptions import ClientError, WaiterError

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from cloud_connectors.aws.codedeploy import (
    create_codedeploy_deployment,
    get_aws_codedeploy_deployments,
)


def _client_error(operation: str, message: str = "denied") -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": "AccessDenied", "Message": message}},
        operation_name=operation,
    )


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


def _logging_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.logger = MagicMock()
    return adapter


class TestGetAwsCodeDeployDeployments:
    def test_returns_details_and_normalizes_statuses(self):
        codedeploy_client = MagicMock()
        codedeploy_client.list_deployments.side_effect = [
            {"deployments": ["dep-1", "dep-2"], "nextToken": "token-1"},
            {"deployments": ["dep-3"]},
        ]
        codedeploy_client.batch_get_deployments.return_value = {
            "deploymentsInfo": [
                {"deploymentId": "dep-1", "status": "Succeeded"},
                {"deploymentId": "dep-2", "status": "Failed"},
                {"deploymentId": "dep-3", "status": "Created"},
            ]
        }

        result = get_aws_codedeploy_deployments(
            application_name="app",
            deployment_group_name="group",
            statuses=["succeeded", "FAILED"],
            codedeploy_client=codedeploy_client,
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["deployment_ids"], ExtendedList)
        assert isinstance(result["deployment_ids"][0], ExtendedString)
        assert isinstance(result["deployments"][0], ExtendedDict)
        assert result["deployment_ids"] == ["dep-1", "dep-2", "dep-3"]
        assert [item["deploymentId"] for item in result["deployments"]] == ["dep-1", "dep-2", "dep-3"]

        first_call_kwargs = codedeploy_client.list_deployments.call_args_list[0].kwargs
        assert first_call_kwargs["includeOnlyStatuses"] == ["Succeeded", "Failed"]

    def test_raises_runtime_error_on_client_failure(self):
        codedeploy_client = MagicMock()
        codedeploy_client.list_deployments.side_effect = _client_error(
            "ListDeployments",
            "denied private-app prod-group token-private tag-private token=raw-token",
        )
        logging_adapter = _logging_adapter()

        with pytest.raises(RuntimeError) as exc_info:
            get_aws_codedeploy_deployments(
                application_name="private-app",
                deployment_group_name="prod-group",
                next_token="token-private",
                tag_filters=[{"Value": "tag-private"}],
                codedeploy_client=codedeploy_client,
                logging_adapter=logging_adapter,
            )

        diagnostics = _logged_text(logging_adapter.logger) + str(exc_info.value)
        assert "private-app" not in diagnostics
        assert "prod-group" not in diagnostics
        assert "token-private" not in diagnostics
        assert "tag-private" not in diagnostics
        assert "raw-token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all("exc_info" not in logged_call.kwargs for logged_call in logging_adapter.logger.method_calls)


class TestCreateCodeDeployDeployment:
    def test_waits_for_success_and_returns_details(self):
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.return_value = {"deploymentId": "dep-123"}
        codedeploy_client.get_deployment.return_value = {
            "deploymentInfo": {"deploymentId": "dep-123", "status": "Succeeded"}
        }

        waiter = MagicMock()
        codedeploy_client.get_waiter.return_value = waiter

        result = create_codedeploy_deployment(
            application_name="app",
            deployment_group_name="group",
            revision={
                "revisionType": "S3",
                "s3Location": {"bucket": "bucket", "key": "bundle.zip", "bundleType": "zip"},
            },
            wait=True,
            codedeploy_client=codedeploy_client,
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["deployment_id"], ExtendedString)
        assert isinstance(result["deployment_info"], ExtendedDict)
        assert result["deployment_id"] == "dep-123"
        assert result["status"] == "Succeeded"
        waiter.wait.assert_called_once_with(
            deploymentId="dep-123",
            WaiterConfig={"Delay": 15, "MaxAttempts": 120},
        )

    def test_waiter_failure_raises_runtime_error(self):
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.return_value = {"deploymentId": "dep-sensitive"}
        codedeploy_client.get_deployment.return_value = {
            "deploymentInfo": {"deploymentId": "dep-sensitive", "status": "Failed"}
        }
        logging_adapter = _logging_adapter()

        waiter = MagicMock()
        waiter.wait.side_effect = WaiterError(
            name="deployment_successful",
            reason="failure",
            last_response={},
        )
        codedeploy_client.get_waiter.return_value = waiter

        with pytest.raises(RuntimeError) as exc_info:
            create_codedeploy_deployment(
                application_name="app",
                deployment_group_name="group",
                revision={
                    "revisionType": "S3",
                    "s3Location": {"bucket": "bucket", "key": "bundle.zip", "bundleType": "zip"},
                },
                wait=True,
                codedeploy_client=codedeploy_client,
                logging_adapter=logging_adapter,
            )

        diagnostics = _logged_text(logging_adapter.logger) + str(exc_info.value)
        assert "dep-sensitive" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None

    def test_detail_fetch_failure_logs_redact_deployment_id(self):
        """Detail hydration failures should not log deployment identifiers or raw provider messages."""
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.return_value = {"deploymentId": "dep-sensitive"}
        codedeploy_client.get_deployment.side_effect = _client_error(
            "GetDeployment",
            "denied for dep-sensitive token=raw-token",
        )
        logging_adapter = _logging_adapter()

        result = create_codedeploy_deployment(
            application_name="app",
            deployment_group_name="group",
            revision={
                "revisionType": "S3",
                "s3Location": {"bucket": "bucket", "key": "bundle.zip", "bundleType": "zip"},
            },
            wait=False,
            include_details=True,
            codedeploy_client=codedeploy_client,
            logging_adapter=logging_adapter,
        )

        assert result["deployment_id"] == "dep-sensitive"
        logs = _logged_text(logging_adapter.logger)
        assert "[REDACTED]" in logs
        assert "dep-sensitive" not in logs
        assert "raw-token" not in logs
        assert all("exc_info" not in logged_call.kwargs for logged_call in logging_adapter.logger.method_calls)

    def test_create_failure_redacts_request_context(self):
        """Create failures should redact app/group/revision identifiers from diagnostics."""
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.side_effect = _client_error(
            "CreateDeployment",
            "denied private-app prod-group prod-bucket bundle.zip secret=raw-secret",
        )
        logging_adapter = _logging_adapter()

        with pytest.raises(RuntimeError) as exc_info:
            create_codedeploy_deployment(
                application_name="private-app",
                deployment_group_name="prod-group",
                revision={
                    "revisionType": "S3",
                    "s3Location": {"bucket": "prod-bucket", "key": "bundle.zip", "bundleType": "zip"},
                },
                codedeploy_client=codedeploy_client,
                logging_adapter=logging_adapter,
            )

        diagnostics = _logged_text(logging_adapter.logger) + str(exc_info.value)
        assert "private-app" not in diagnostics
        assert "prod-group" not in diagnostics
        assert "prod-bucket" not in diagnostics
        assert "bundle.zip" not in diagnostics
        assert "raw-secret" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all("exc_info" not in logged_call.kwargs for logged_call in logging_adapter.logger.method_calls)

    def test_validates_file_exists_behavior(self):
        codedeploy_client = MagicMock()

        with pytest.raises(ValueError):
            create_codedeploy_deployment(
                application_name="app",
                deployment_group_name="group",
                revision={
                    "revisionType": "S3",
                    "s3Location": {"bucket": "bucket", "key": "bundle.zip", "bundleType": "zip"},
                },
                file_exists_behavior="skip",
                codedeploy_client=codedeploy_client,
            )
