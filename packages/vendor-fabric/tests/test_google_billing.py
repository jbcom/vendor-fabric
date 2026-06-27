# ruff: noqa: I001
"""Tests for Google Billing mixin helpers."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.oauth2.service_account")
pytest.importorskip("googleapiclient")

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from vendor_fabric.google.billing import GoogleBillingMixin


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


def _http_error(status: int):
    """Return a Google API HttpError with the requested status."""
    from googleapiclient.errors import HttpError

    response = MagicMock()
    response.status = status
    return HttpError(response, b"Google API error")


class _ImmediateResponse:
    def __init__(self, response: dict[str, Any]):
        self._response = response

    def execute(self) -> dict[str, Any]:
        return self._response


class _StubProjectsAPI:
    def __init__(self):
        self.update_calls: list[dict[str, Any]] = []

    def updateBillingInfo(self, name: str, body: dict[str, Any]):
        self.update_calls.append({"name": name, "body": body})
        return _ImmediateResponse({"name": name, **body})


class _StubBillingAccountProjectsAPI:
    def __init__(self, responses: Iterable[dict[str, Any]]):
        self._responses = deque(responses)
        self.list_calls: list[dict[str, Any]] = []

    def list(self, **params):
        self.list_calls.append(params)
        return _ImmediateResponse(self._responses.popleft())


class _StubBillingAccountsAPI:
    def __init__(
        self,
        account_responses: Iterable[dict[str, Any]],
        project_responses: Iterable[dict[str, Any]],
    ):
        self._account_responses = deque(account_responses)
        self.list_calls: list[dict[str, Any]] = []
        self._projects_api = _StubBillingAccountProjectsAPI(project_responses)

    def list(self, **params):
        self.list_calls.append(params)
        return _ImmediateResponse(self._account_responses.popleft())

    def projects(self):
        return self._projects_api


class _StubBillingService:
    def __init__(
        self,
        account_responses: Iterable[dict[str, Any]],
        project_responses: Iterable[dict[str, Any]],
    ):
        self._accounts_api = _StubBillingAccountsAPI(account_responses, project_responses)
        self._projects_api = _StubProjectsAPI()

    def billingAccounts(self):
        return self._accounts_api

    def projects(self):
        return self._projects_api


class _TestGoogleBilling(GoogleBillingMixin):
    def __init__(self, service: Any):
        self.logger = MagicMock()
        self._service = service
        self.service_account_info = {
            "type": "service_account",
            "client_email": "test@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...test\n-----END RSA PRIVATE KEY-----\n",
            "private_key_id": "key123",
            "project_id": "test-project",
        }

    def get_billing_service(self):
        return self._service

    def extend_result(self, value: Any) -> Any:
        return extend_data(value)


def test_list_billing_accounts_paginates_and_unhumps():
    service = _StubBillingService(
        account_responses=[
            {
                "billingAccounts": [
                    {"name": "billingAccounts/ABC", "displayName": "Primary"},
                ],
                "nextPageToken": "token-1",
            },
            {
                "billingAccounts": [
                    {"name": "billingAccounts/DEF", "displayName": "Secondary"},
                ],
            },
        ],
        project_responses=[],
    )
    connector = _TestGoogleBilling(service)

    accounts = connector.list_billing_accounts(filter_query="parent:organizations/1", unhump_accounts=True)

    assert isinstance(accounts, ExtendedList)
    assert isinstance(accounts[0], ExtendedDict)
    assert isinstance(accounts[0]["display_name"], ExtendedString)
    assert [acct["name"] for acct in accounts] == ["billingAccounts/ABC", "billingAccounts/DEF"]
    # Ensure snake_case conversion applied
    assert accounts[0]["display_name"] == "Primary"
    assert service.billingAccounts().list_calls == [
        {"filter": "parent:organizations/1"},
        {"filter": "parent:organizations/1", "pageToken": "token-1"},
    ]


def test_get_billing_account_prefixes_name_and_promotes_result():
    service = MagicMock()
    service.billingAccounts.return_value.get.return_value.execute.return_value = {
        "name": "billingAccounts/1234-ABCD",
        "displayName": "Primary",
    }
    connector = _TestGoogleBilling(service)

    account = connector.get_billing_account("1234-ABCD")

    assert isinstance(account, ExtendedDict)
    assert account["name"] == "billingAccounts/1234-ABCD"
    assert isinstance(account["displayName"], ExtendedString)
    service.billingAccounts.return_value.get.assert_called_once_with(name="billingAccounts/1234-ABCD")


def test_get_billing_account_accepts_prefixed_name():
    service = MagicMock()
    service.billingAccounts.return_value.get.return_value.execute.return_value = {
        "name": "billingAccounts/1234-ABCD",
    }
    connector = _TestGoogleBilling(service)

    connector.get_billing_account("billingAccounts/1234-ABCD")

    service.billingAccounts.return_value.get.assert_called_once_with(name="billingAccounts/1234-ABCD")


def test_get_billing_account_returns_none_for_not_found():
    service = MagicMock()
    service.billingAccounts.return_value.get.return_value.execute.side_effect = _http_error(404)
    connector = _TestGoogleBilling(service)

    account = connector.get_billing_account("private-account@example.com")

    assert account is None
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-account@example.com" not in logs


def test_get_billing_account_reraises_unexpected_errors():
    service = MagicMock()
    service.billingAccounts.return_value.get.return_value.execute.side_effect = _http_error(403)
    connector = _TestGoogleBilling(service)

    with pytest.raises(Exception, match="Google API error"):
        connector.get_billing_account("1234-ABCD")


def test_get_project_billing_info_promotes_result():
    service = MagicMock()
    service.projects.return_value.getBillingInfo.return_value.execute.return_value = {
        "name": "projects/demo-project/billingInfo",
        "billingEnabled": True,
    }
    connector = _TestGoogleBilling(service)

    info = connector.get_project_billing_info("demo-project")

    assert isinstance(info, ExtendedDict)
    assert info["billingEnabled"] is True
    service.projects.return_value.getBillingInfo.assert_called_once_with(name="projects/demo-project")


def test_get_project_billing_info_returns_none_for_not_found():
    service = MagicMock()
    service.projects.return_value.getBillingInfo.return_value.execute.side_effect = _http_error(404)
    connector = _TestGoogleBilling(service)

    info = connector.get_project_billing_info("secret-project@example.com")

    assert info is None
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "secret-project@example.com" not in logs


def test_update_project_billing_info_prefixes_account_name():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)

    response = connector.update_project_billing_info("demo-project", "1234-ABCD")

    assert isinstance(response, ExtendedDict)
    assert isinstance(response["billingAccountName"], ExtendedString)
    assert response["billingAccountName"] == "billingAccounts/1234-ABCD"
    assert service.projects().update_calls == [
        {
            "name": "projects/demo-project",
            "body": {"billingAccountName": "billingAccounts/1234-ABCD"},
        }
    ]


def test_update_project_billing_info_logs_redact_identifiers_but_preserve_call_args():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)

    connector.update_project_billing_info("sensitive-project", "1234-PRIVATE")

    assert service.projects().update_calls == [
        {
            "name": "projects/sensitive-project",
            "body": {"billingAccountName": "billingAccounts/1234-PRIVATE"},
        }
    ]
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "sensitive-project" not in logs
    assert "1234-PRIVATE" not in logs


def test_disable_project_billing_sets_empty_account():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)

    response = connector.disable_project_billing("demo-project")

    assert isinstance(response, ExtendedDict)
    assert isinstance(response["billingAccountName"], ExtendedString)
    assert response["billingAccountName"] == ""
    assert service.projects().update_calls[-1] == {
        "name": "projects/demo-project",
        "body": {"billingAccountName": ""},
    }


def test_list_billing_account_projects_handles_prefixing():
    service = _StubBillingService(
        account_responses=[],
        project_responses=[
            {
                "projectBillingInfo": [{"projectId": "alpha"}],
                "nextPageToken": "p1",
            },
            {
                "projectBillingInfo": [{"projectId": "beta"}],
            },
        ],
    )
    connector = _TestGoogleBilling(service)

    projects = connector.list_billing_account_projects("123456-AAAA", unhump_projects=True)

    assert isinstance(projects, ExtendedList)
    assert isinstance(projects[0], ExtendedDict)
    assert isinstance(projects[0]["project_id"], ExtendedString)
    assert [proj["project_id"] for proj in projects] == ["alpha", "beta"]
    assert service.billingAccounts().projects().list_calls == [
        {"name": "billingAccounts/123456-AAAA"},
        {"name": "billingAccounts/123456-AAAA", "pageToken": "p1"},
    ]


def test_get_billing_account_iam_policy_prefixes_resource():
    service = MagicMock()
    service.billingAccounts.return_value.getIamPolicy.return_value.execute.return_value = {
        "bindings": [{"role": "roles/billing.viewer"}],
    }
    connector = _TestGoogleBilling(service)

    policy = connector.get_billing_account_iam_policy("123456-AAAA")

    assert isinstance(policy, ExtendedDict)
    assert policy["bindings"][0]["role"] == "roles/billing.viewer"
    service.billingAccounts.return_value.getIamPolicy.assert_called_once_with(resource="billingAccounts/123456-AAAA")


def test_set_billing_account_iam_policy_lowers_extended_policy():
    service = MagicMock()
    service.billingAccounts.return_value.setIamPolicy.return_value.execute.return_value = {
        "bindings": [{"role": "roles/billing.admin"}],
    }
    connector = _TestGoogleBilling(service)

    policy = connector.set_billing_account_iam_policy(
        "123456-AAAA",
        extend_data({"bindings": [{"role": "roles/billing.admin"}]}),
    )

    assert isinstance(policy, ExtendedDict)
    service.billingAccounts.return_value.setIamPolicy.assert_called_once_with(
        resource="billingAccounts/123456-AAAA",
        body={"policy": {"bindings": [{"role": "roles/billing.admin"}]}},
    )


def test_get_bigquery_billing_dataset_filters_billing_tables():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)
    credentials = MagicMock(name="credentials")
    bigquery = MagicMock()
    bigquery.datasets.return_value.get.return_value.execute.return_value = {
        "datasetReference": {"datasetId": "billing_export"},
        "location": "US",
        "description": "Billing export",
    }
    bigquery.tables.return_value.list.return_value.execute.return_value = {
        "tables": [
            {"tableReference": {"tableId": "gcp_billing_export_v1_123"}},
            {"tableReference": {"tableId": "not_billing"}},
        ]
    }

    with (
        patch(
            "google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials
        ) as from_info,
        patch("googleapiclient.discovery.build", return_value=bigquery) as build,
    ):
        result = connector.get_bigquery_billing_dataset("billing-project", "billing_export")

    assert isinstance(result, ExtendedDict)
    assert result["location"] == "US"
    assert len(result["billing_tables"]) == 1
    assert result["billing_tables"][0]["tableReference"]["tableId"] == "gcp_billing_export_v1_123"
    from_info.assert_called_once_with(
        connector.service_account_info,
        scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
    )
    build.assert_called_once_with("bigquery", "v2", credentials=credentials, cache_discovery=False)


def test_get_bigquery_billing_dataset_returns_none_for_missing_dataset():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)
    credentials = MagicMock(name="credentials")
    bigquery = MagicMock()
    bigquery.datasets.return_value.get.return_value.execute.side_effect = _http_error(404)

    with (
        patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials),
        patch("googleapiclient.discovery.build", return_value=bigquery),
    ):
        result = connector.get_bigquery_billing_dataset("secret-project@example.com", "billing@example.com")

    assert result is None
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "secret-project@example.com" not in logs
    assert "billing@example.com" not in logs


def test_setup_billing_export_returns_existing_dataset_config():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)
    credentials = MagicMock(name="credentials")
    bigquery = MagicMock()
    bigquery.datasets.return_value.get.return_value.execute.return_value = {"location": "EU"}

    with (
        patch(
            "google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials
        ) as from_info,
        patch("googleapiclient.discovery.build", return_value=bigquery) as build,
    ):
        result = connector.setup_billing_export(
            "123456-AAAA",
            "billing-project",
            dataset_id="billing_export",
            location="EU",
        )

    assert isinstance(result, ExtendedDict)
    assert result["billing_account_id"] == "123456-AAAA"
    assert result["project_id"] == "billing-project"
    assert result["dataset_id"] == "billing_export"
    assert result["location"] == "EU"
    assert result["full_dataset_id"] == "billing-project.billing_export"
    bigquery.datasets.return_value.insert.assert_not_called()
    from_info.assert_called_once_with(
        connector.service_account_info,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    build.assert_called_once_with("bigquery", "v2", credentials=credentials, cache_discovery=False)


def test_setup_billing_export_creates_missing_dataset():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)
    credentials = MagicMock(name="credentials")
    bigquery = MagicMock()
    bigquery.datasets.return_value.get.return_value.execute.side_effect = _http_error(404)
    bigquery.datasets.return_value.insert.return_value.execute.return_value = {"location": "US"}

    with (
        patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials),
        patch("googleapiclient.discovery.build", return_value=bigquery),
    ):
        result = connector.setup_billing_export("123456-AAAA", "billing-project")

    assert isinstance(result, ExtendedDict)
    assert result["location"] == "US"
    insert_call = bigquery.datasets.return_value.insert.call_args
    assert insert_call.kwargs["projectId"] == "billing-project"
    body = insert_call.kwargs["body"]
    assert body["datasetReference"] == {"projectId": "billing-project", "datasetId": "billing_export"}
    assert body["labels"]["billing_account"] == "123456_AAAA"


def test_setup_billing_export_reraises_unexpected_dataset_errors():
    service = _StubBillingService(account_responses=[], project_responses=[])
    connector = _TestGoogleBilling(service)
    credentials = MagicMock(name="credentials")
    bigquery = MagicMock()
    bigquery.datasets.return_value.get.return_value.execute.side_effect = _http_error(403)

    with (
        patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=credentials),
        patch("googleapiclient.discovery.build", return_value=bigquery),
    ):
        with pytest.raises(Exception, match="Google API error"):
            connector.setup_billing_export("123456-AAAA", "billing-project")
