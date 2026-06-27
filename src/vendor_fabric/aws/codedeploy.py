"""AWS CodeDeploy helpers for vendor-fabric.

This module centralizes CodeDeploy helper functions so infrastructure stacks
and standalone Python workloads can rely on the same implementation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from extended_data.containers import ExtendedDict, extend_data, to_builtin
from extended_data.logging import Logging

from vendor_fabric.aws import AWSConnector
from vendor_fabric.aws._diagnostics import aws_operation_error, safe_aws_ref, safe_aws_text


if TYPE_CHECKING:
    from botocore.client import BaseClient
    from botocore.config import Config
    from botocore.exceptions import ClientError, WaiterError
else:
    BaseClient = Any
    Config = Any

    try:
        from botocore.exceptions import ClientError, WaiterError
    except ImportError:

        class ClientError(Exception):
            """Fallback exception used until botocore is imported."""

        class WaiterError(Exception):
            """Fallback exception used until botocore is imported."""


_BATCH_GET_LIMIT = 25
_VALID_FILE_BEHAVIORS = {"DISALLOW", "OVERWRITE", "RETAIN"}
_DEPLOYMENT_STATUS_MAP = {
    "created": "Created",
    "queued": "Queued",
    "ready": "Ready",
    "inprogress": "InProgress",
    "in_progress": "InProgress",
    "succeeded": "Succeeded",
    "failed": "Failed",
    "stopped": "Stopped",
}


def _chunked(sequence: Sequence[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(sequence), size):
        yield list(sequence[idx : idx + size])


def _coerce_datetime(value: datetime | str | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    msg = f"Unsupported datetime value type: {type(value)!r}"
    raise TypeError(msg)


def _normalize_statuses(statuses: Sequence[str] | None) -> list[str] | None:
    if not statuses:
        return None
    normalized: list[str] = []
    for status in statuses:
        key = status.replace("-", "_").lower()
        if key not in _DEPLOYMENT_STATUS_MAP:
            valid = ", ".join(sorted(set(_DEPLOYMENT_STATUS_MAP.values())))
            msg = f"Unsupported CodeDeploy status '{status}'. Valid statuses: {valid}"
            raise ValueError(msg)
        normalized.append(_DEPLOYMENT_STATUS_MAP[key])
    # Preserve caller order while deduplicating
    seen: set[str] = set()
    ordered: list[str] = []
    for status in normalized:
        if status not in seen:
            seen.add(status)
            ordered.append(status)
    return ordered


def _resolve_logging_adapter(
    aws_connector: AWSConnector | None,
    logging_adapter: Logging | None,
) -> Logging:
    if logging_adapter:
        return logging_adapter
    if aws_connector and getattr(aws_connector, "logging", None):
        return aws_connector.logging
    return Logging(logger_name="AWSCodeDeploy")


def _resolve_codedeploy_client(
    codedeploy_client: BaseClient | None,
    aws_connector: AWSConnector | None,
    logging_adapter: Logging,
    execution_role_arn: str | None,
    role_session_name: str | None,
    region_name: str | None,
    config: Config | None,
) -> tuple[BaseClient, AWSConnector | None]:
    if codedeploy_client:
        return codedeploy_client, aws_connector

    connector = aws_connector or AWSConnector(
        execution_role_arn=execution_role_arn,
        logger=logging_adapter,
    )
    client_kwargs: dict[str, Any] = {}
    if region_name:
        client_kwargs["region_name"] = region_name
    client = connector.get_aws_client(
        client_name="codedeploy",
        execution_role_arn=execution_role_arn or connector.execution_role_arn,
        role_session_name=role_session_name,
        config=config,
        **client_kwargs,
    )
    return client, connector


def _safe_get_deployment(
    codedeploy_client: BaseClient,
    deployment_id: str,
    logger: Any,
) -> dict[str, Any] | None:
    try:
        response = codedeploy_client.get_deployment(deploymentId=deployment_id)
    except ClientError as exc:
        logger.warning(
            "Unable to fetch CodeDeploy deployment details for %s: %s",
            safe_aws_ref(deployment_id),
            safe_aws_text(exc, deployment_id),
        )
        return None
    return response.get("deploymentInfo")


def get_aws_codedeploy_deployments(
    application_name: str | None = None,
    deployment_group_name: str | None = None,
    deployment_config_name: str | None = None,
    statuses: Sequence[str] | None = None,
    created_after: datetime | str | float | None = None,
    created_before: datetime | str | float | None = None,
    tag_filters: Sequence[Mapping[str, Any]] | None = None,
    include_details: bool = True,
    limit: int | None = None,
    next_token: str | None = None,
    max_pages: int | None = None,
    codedeploy_client: BaseClient | None = None,
    aws_connector: AWSConnector | None = None,
    execution_role_arn: str | None = None,
    role_session_name: str | None = None,
    region_name: str | None = None,
    config: Config | None = None,
    logging_adapter: Logging | None = None,
) -> ExtendedDict:
    """List CodeDeploy deployments with optional detail hydration.

    Returns a dictionary with the deployment identifiers, optional deployment
    details (when ``include_details`` is True) and the next pagination token.
    """
    logging_adapter = _resolve_logging_adapter(aws_connector, logging_adapter)
    logger = logging_adapter.logger
    client, connector = _resolve_codedeploy_client(
        codedeploy_client=codedeploy_client,
        aws_connector=aws_connector,
        logging_adapter=logging_adapter,
        execution_role_arn=execution_role_arn or getattr(aws_connector, "execution_role_arn", None),
        role_session_name=role_session_name,
        region_name=region_name,
        config=config,
    )

    params: dict[str, Any] = {}
    if application_name:
        params["applicationName"] = application_name
    if deployment_group_name:
        params["deploymentGroupName"] = deployment_group_name
    if deployment_config_name:
        params["deploymentConfigName"] = deployment_config_name
    normalized_statuses = _normalize_statuses(statuses)
    if normalized_statuses:
        params["includeOnlyStatuses"] = normalized_statuses
    start = _coerce_datetime(created_after)
    end = _coerce_datetime(created_before)
    if start or end:
        params["createTimeRange"] = {}
        if start:
            params["createTimeRange"]["start"] = start
        if end:
            params["createTimeRange"]["end"] = end
    if tag_filters:
        params["tagFilters"] = [dict(to_builtin(tag_filter)) for tag_filter in tag_filters]

    deployment_ids: list[str] = []
    pages = 0
    final_token: str | None = None
    token = next_token

    try:
        while True:
            if token:
                params["nextToken"] = token
            else:
                params.pop("nextToken", None)

            response = client.list_deployments(**params)
            pages += 1
            new_ids: list[str] = response.get("deployments", [])

            if limit is not None:
                remaining = max(limit - len(deployment_ids), 0)
                deployment_ids.extend(new_ids[:remaining])
                if remaining <= len(new_ids):
                    final_token = response.get("nextToken")
                    break
            else:
                deployment_ids.extend(new_ids)

            token = response.get("nextToken")
            if not token:
                break
            if max_pages is not None and pages >= max_pages:
                final_token = token
                break
    except ClientError as exc:
        msg = aws_operation_error(
            "Failed to list AWS CodeDeploy deployments",
            exc,
            application_name,
            deployment_group_name,
            deployment_config_name,
            next_token,
            tag_filters,
        )
        logger.error(msg)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
        raise RuntimeError(msg) from None

    deployment_infos: list[dict[str, Any]] | None = None
    if include_details and deployment_ids:
        deployment_infos = []
        for chunk in _chunked(deployment_ids, _BATCH_GET_LIMIT):
            batch = client.batch_get_deployments(deploymentIds=chunk)
            items = {item.get("deploymentId"): item for item in batch.get("deploymentsInfo", [])}
            for deployment_id in chunk:
                if deployment_id in items:
                    deployment_infos.append(items[deployment_id])

    safe_token_detail = f" (next token: {safe_aws_ref(final_token)})" if final_token else ""
    logger.info("Fetched %s CodeDeploy deployments%s", len(deployment_ids), safe_token_detail)

    _ = connector  # appease linters when we instantiate a connector internally
    return extend_data(
        {
            "deployment_ids": deployment_ids,
            "deployments": deployment_infos,
            "next_token": final_token,
            "pages": pages,
        }
    )


def create_codedeploy_deployment(
    application_name: str,
    deployment_group_name: str,
    revision: Mapping[str, Any],
    description: str | None = None,
    ignore_application_stop_failures: bool | None = None,
    file_exists_behavior: str | None = None,
    auto_rollback_configuration: Mapping[str, Any] | None = None,
    update_outdated_instances_only: bool | None = None,
    wait: bool = False,
    waiter_delay: int = 15,
    waiter_max_attempts: int = 120,
    include_details: bool = True,
    codedeploy_client: BaseClient | None = None,
    aws_connector: AWSConnector | None = None,
    execution_role_arn: str | None = None,
    role_session_name: str | None = None,
    region_name: str | None = None,
    config: Config | None = None,
    logging_adapter: Logging | None = None,
    **additional_params: Any,
) -> ExtendedDict:
    """Create a CodeDeploy deployment and optionally wait for completion."""
    if not revision:
        msg = "The CodeDeploy revision payload is required."
        raise ValueError(msg)

    if file_exists_behavior:
        upper = file_exists_behavior.upper()
        if upper not in _VALID_FILE_BEHAVIORS:
            valid = ", ".join(sorted(_VALID_FILE_BEHAVIORS))
            msg = f"file_exists_behavior must be one of {valid}"
            raise ValueError(msg)
        file_exists_behavior = upper

    logging_adapter = _resolve_logging_adapter(aws_connector, logging_adapter)
    logger = logging_adapter.logger
    client, connector = _resolve_codedeploy_client(
        codedeploy_client=codedeploy_client,
        aws_connector=aws_connector,
        logging_adapter=logging_adapter,
        execution_role_arn=execution_role_arn or getattr(aws_connector, "execution_role_arn", None),
        role_session_name=role_session_name,
        region_name=region_name,
        config=config,
    )

    request: dict[str, Any] = {
        "applicationName": application_name,
        "deploymentGroupName": deployment_group_name,
        "revision": dict(to_builtin(revision)),
    }
    if description:
        request["description"] = description
    if ignore_application_stop_failures is not None:
        request["ignoreApplicationStopFailures"] = ignore_application_stop_failures
    if file_exists_behavior:
        request["fileExistsBehavior"] = file_exists_behavior
    if auto_rollback_configuration:
        request["autoRollbackConfiguration"] = dict(to_builtin(auto_rollback_configuration))
    if update_outdated_instances_only is not None:
        request["updateOutdatedInstancesOnly"] = update_outdated_instances_only
    request.update(to_builtin(additional_params))

    try:
        response = client.create_deployment(**request)
    except ClientError as exc:
        msg = aws_operation_error(
            "Failed to create AWS CodeDeploy deployment",
            exc,
            application_name,
            deployment_group_name,
            revision,
            description,
        )
        logger.error(msg)  # noqa: TRY400 - traceback can expose raw provider diagnostics.
        raise RuntimeError(msg) from None

    deployment_id = response.get("deploymentId")
    if not deployment_id:
        msg = "CodeDeploy did not return a deploymentId."
        raise RuntimeError(msg)

    logger.info(
        "Created CodeDeploy deployment %s for %s/%s",
        safe_aws_ref(deployment_id),
        safe_aws_ref(application_name),
        safe_aws_ref(deployment_group_name),
    )

    deployment_info: dict[str, Any] | None = None
    if wait:
        waiter = client.get_waiter("deployment_successful")
        try:
            waiter.wait(
                deploymentId=deployment_id,
                WaiterConfig={"Delay": waiter_delay, "MaxAttempts": waiter_max_attempts},
            )
        except WaiterError:
            deployment_info = _safe_get_deployment(client, deployment_id, logger)
            status = deployment_info.get("status") if deployment_info else "unknown"
            safe_deployment_id = safe_aws_ref(deployment_id)
            safe_status = safe_aws_text(status)
            msg = f"Deployment {safe_deployment_id} did not reach a successful state (status={safe_status})."
            raise RuntimeError(msg) from None
        deployment_info = _safe_get_deployment(client, deployment_id, logger)
    elif include_details:
        deployment_info = _safe_get_deployment(client, deployment_id, logger)

    _ = connector
    return extend_data(
        {
            "deployment_id": deployment_id,
            "status": deployment_info.get("status") if deployment_info else None,
            "deployment_info": deployment_info,
        }
    )
