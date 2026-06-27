# ruff: noqa: I001
"""Tests for the AWS CodeDeploy helper module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("botocore")

from botocore.exceptions import ClientError, WaiterError

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from vendor_fabric.aws.codedeploy import (
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

    def test_normalizes_datetime_filters_limit_and_max_pages(self):
        """List requests should normalize filters and preserve continuation tokens."""
        codedeploy_client = MagicMock()
        codedeploy_client.list_deployments.side_effect = [
            {"deployments": ["dep-1", "dep-2", "dep-3"], "nextToken": "token-2"},
            {"deployments": ["dep-4"], "nextToken": "token-3"},
        ]

        result = get_aws_codedeploy_deployments(
            application_name="app",
            deployment_group_name="group",
            deployment_config_name="CodeDeployDefault.AllAtOnce",
            statuses=["in-progress", "in_progress", "queued"],
            created_after="2026-06-27T00:00:00Z",
            created_before=1782518400.0,
            tag_filters=[ExtendedDict({"Key": "env", "Value": "prod"})],
            include_details=False,
            limit=2,
            max_pages=1,
            next_token="token-1",
            codedeploy_client=codedeploy_client,
        )

        assert result["deployment_ids"] == ["dep-1", "dep-2"]
        assert result["deployments"] is None
        assert result["next_token"] == "token-2"
        assert result["pages"] == 1
        call_kwargs = codedeploy_client.list_deployments.call_args.kwargs
        assert call_kwargs["includeOnlyStatuses"] == ["InProgress", "Queued"]
        assert call_kwargs["deploymentConfigName"] == "CodeDeployDefault.AllAtOnce"
        assert call_kwargs["nextToken"] == "token-1"
        assert call_kwargs["tagFilters"] == [{"Key": "env", "Value": "prod"}]
        assert call_kwargs["createTimeRange"]["start"].isoformat() == "2026-06-27T00:00:00+00:00"

    def test_invalid_status_and_datetime_type_fail_fast(self):
        """Bad caller filter values should fail before provider calls."""
        codedeploy_client = MagicMock()

        with pytest.raises(ValueError, match="Unsupported CodeDeploy status"):
            get_aws_codedeploy_deployments(statuses=["not-real"], codedeploy_client=codedeploy_client)

        with pytest.raises(TypeError, match="Unsupported datetime value type"):
            get_aws_codedeploy_deployments(created_after=object(), codedeploy_client=codedeploy_client)

        codedeploy_client.list_deployments.assert_not_called()

    def test_resolves_client_from_connector_and_region(self):
        """The helper should construct a CodeDeploy client through AWSConnector when needed."""
        codedeploy_client = MagicMock()
        codedeploy_client.list_deployments.return_value = {"deployments": []}
        aws_connector = MagicMock()
        aws_connector.execution_role_arn = "arn:aws:iam::123456789012:role/deploy"
        aws_connector.get_aws_client.return_value = codedeploy_client

        result = get_aws_codedeploy_deployments(
            aws_connector=aws_connector,
            role_session_name="deploy-session",
            region_name="us-east-1",
            config="cfg",
        )

        assert result["deployment_ids"] == []
        aws_connector.get_aws_client.assert_called_once_with(
            client_name="codedeploy",
            execution_role_arn="arn:aws:iam::123456789012:role/deploy",
            role_session_name="deploy-session",
            config="cfg",
            region_name="us-east-1",
        )

    def test_detail_hydration_preserves_requested_order_and_ignores_missing_items(self):
        """Batch detail hydration should not reorder list_deployments results."""
        deployment_ids = [f"dep-{idx}" for idx in range(30)]
        codedeploy_client = MagicMock()
        codedeploy_client.list_deployments.return_value = {"deployments": deployment_ids}
        codedeploy_client.batch_get_deployments.side_effect = [
            {
                "deploymentsInfo": [
                    {"deploymentId": "dep-1"},
                    {"deploymentId": "dep-0"},
                ]
            },
            {"deploymentsInfo": [{"deploymentId": "dep-25"}]},
        ]

        result = get_aws_codedeploy_deployments(codedeploy_client=codedeploy_client)

        assert result["deployment_ids"] == deployment_ids
        assert [item["deploymentId"] for item in result["deployments"]] == ["dep-0", "dep-1", "dep-25"]
        assert codedeploy_client.batch_get_deployments.call_count == 2


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

    def test_requires_revision_before_provider_call(self):
        """A deployment revision is required by the public contract."""
        codedeploy_client = MagicMock()

        with pytest.raises(ValueError, match="revision payload is required"):
            create_codedeploy_deployment(
                application_name="app",
                deployment_group_name="group",
                revision={},
                codedeploy_client=codedeploy_client,
            )

        codedeploy_client.create_deployment.assert_not_called()

    def test_create_builds_optional_request_without_detail_fetch(self):
        """Optional CodeDeploy request flags should be passed through exactly."""
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.return_value = {"deploymentId": "dep-123"}

        result = create_codedeploy_deployment(
            application_name="app",
            deployment_group_name="group",
            revision=ExtendedDict(
                {
                    "revisionType": "S3",
                    "s3Location": {"bucket": "bucket", "key": "bundle.zip", "bundleType": "zip"},
                }
            ),
            description="ship it",
            ignore_application_stop_failures=False,
            file_exists_behavior="overwrite",
            auto_rollback_configuration=ExtendedDict({"enabled": True, "events": ["DEPLOYMENT_FAILURE"]}),
            update_outdated_instances_only=True,
            include_details=False,
            codedeploy_client=codedeploy_client,
            alarmConfiguration={"enabled": False},
        )

        assert result["deployment_id"] == "dep-123"
        assert result["status"] is None
        assert result["deployment_info"] is None
        codedeploy_client.get_deployment.assert_not_called()
        call_kwargs = codedeploy_client.create_deployment.call_args.kwargs
        assert call_kwargs["description"] == "ship it"
        assert call_kwargs["ignoreApplicationStopFailures"] is False
        assert call_kwargs["fileExistsBehavior"] == "OVERWRITE"
        assert call_kwargs["autoRollbackConfiguration"] == {"enabled": True, "events": ["DEPLOYMENT_FAILURE"]}
        assert call_kwargs["updateOutdatedInstancesOnly"] is True
        assert call_kwargs["alarmConfiguration"] == {"enabled": False}

    def test_missing_deployment_id_raises_clear_error(self):
        """Provider responses without deploymentId should be rejected."""
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.return_value = {}

        with pytest.raises(RuntimeError, match="did not return a deploymentId"):
            create_codedeploy_deployment(
                application_name="app",
                deployment_group_name="group",
                revision={
                    "revisionType": "S3",
                    "s3Location": {"bucket": "bucket", "key": "bundle.zip", "bundleType": "zip"},
                },
                codedeploy_client=codedeploy_client,
            )

    def test_waiter_failure_without_deployment_info_uses_unknown_status(self):
        """Waiter failures should still return redacted, cause-free diagnostics without details."""
        codedeploy_client = MagicMock()
        codedeploy_client.create_deployment.return_value = {"deploymentId": "dep-sensitive"}
        codedeploy_client.get_deployment.side_effect = _client_error(
            "GetDeployment",
            "denied for dep-sensitive token=raw-token",
        )
        waiter = MagicMock()
        waiter.wait.side_effect = WaiterError(name="deployment_successful", reason="failure", last_response={})
        codedeploy_client.get_waiter.return_value = waiter
        logging_adapter = _logging_adapter()

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
        assert "unknown" in str(exc_info.value)
        assert "dep-sensitive" not in diagnostics
        assert "raw-token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
