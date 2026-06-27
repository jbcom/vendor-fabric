# ruff: noqa: I001
"""Tests for AWS Organizations helper mixin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("boto3")
pytest.importorskip("botocore")

from botocore.exceptions import ClientError

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from cloud_connectors.aws.organizations import AWSOrganizationsMixin


class _StubLogger:
    def info(self, *args, **kwargs):  # pragma: no cover - no logic to test
        pass

    def debug(self, *args, **kwargs):  # pragma: no cover - no logic to test
        pass

    def warning(self, *args, **kwargs):  # pragma: no cover - no logic to test
        pass


class _StubOrganizationsClient:
    def __init__(self) -> None:
        self.tag_calls: list[dict[str, Any]] = []

    def tag_resource(self, ResourceId: str, Tags: list[dict[str, str]]):
        self.tag_calls.append({"ResourceId": ResourceId, "Tags": Tags})

    def list_roots(self):
        return {"Roots": [{"Id": "r-root"}]}


class _ParentPaginator:
    def __init__(self, pages_by_parent: Mapping[str, list[dict[str, Any]]]) -> None:
        self.pages_by_parent = pages_by_parent

    def paginate(self, ParentId: str) -> list[dict[str, Any]]:
        return self.pages_by_parent.get(ParentId, [])


class _ResourceTagPaginator:
    def __init__(self, tags_by_resource: Mapping[str, list[dict[str, str]]]) -> None:
        self.tags_by_resource = tags_by_resource

    def paginate(self, ResourceId: str) -> list[dict[str, Any]]:
        return [{"Tags": self.tags_by_resource.get(ResourceId, [])}]


class _OrganizationTreeClient:
    def __init__(
        self,
        *,
        account_pages: Mapping[str, list[dict[str, Any]]] | None = None,
        ou_pages: Mapping[str, list[dict[str, Any]]] | None = None,
        tags_by_resource: Mapping[str, list[dict[str, str]]] | None = None,
    ) -> None:
        self.account_pages = account_pages or {}
        self.ou_pages = ou_pages or {}
        self.tags_by_resource = tags_by_resource or {}

    def list_roots(self):
        return {"Roots": [{"Id": "r-root"}]}

    def get_paginator(self, name: str):
        if name == "list_accounts_for_parent":
            return _ParentPaginator(self.account_pages)
        if name == "list_organizational_units_for_parent":
            return _ParentPaginator(self.ou_pages)
        if name == "list_tags_for_resource":
            return _ResourceTagPaginator(self.tags_by_resource)
        raise AssertionError(f"unexpected paginator {name}")


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


class _TestAWSOrganizations(AWSOrganizationsMixin):
    def __init__(self) -> None:
        self.logger = _StubLogger()
        self.execution_role_arn = "arn:aws:iam::111111111111:role/test"
        self._clients: dict[str, Any] = {}

    def register_client(self, name: str, client: Any) -> None:
        self._clients[name] = client

    def get_aws_client(self, client_name: str, execution_role_arn=None):
        return self._clients[client_name]

    def extend_result(self, value: Any) -> Any:
        return extend_data(value)


@pytest.fixture
def organizations_connector() -> _TestAWSOrganizations:
    connector = _TestAWSOrganizations()
    connector.register_client("organizations", _StubOrganizationsClient())
    return connector


def test_classify_accounts_applies_rules(organizations_connector: _TestAWSOrganizations):
    accounts = {
        "111111111111": {"ou_name": "Prod Apps", "tags": {}},
        "222222222222": {"path": "Shared/Dev", "tags": {}},
        "333333333333": {"ou_name": "Misc", "tags": {"Environment": "Sandbox"}},
    }

    result = organizations_connector.classify_accounts(
        accounts=accounts,
        classification_rules={
            "production": ["prod"],
            "development": ["dev"],
            "sandbox": ["sandbox"],
        },
    )

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["111111111111"], ExtendedDict)
    assert isinstance(result["111111111111"]["classification"], ExtendedString)
    assert result["111111111111"]["classification"] == "production"
    assert result["222222222222"]["classification"] == "development"
    assert result["333333333333"]["classification"] == "sandbox"


def test_classify_accounts_fetches_when_missing(mocker, organizations_connector: _TestAWSOrganizations):
    sample_accounts = {"999999999999": {"ou_name": "Shared", "tags": {"Environment": "Shared"}}}
    mock_get = mocker.patch.object(organizations_connector, "get_accounts", return_value=sample_accounts)

    output = organizations_connector.classify_accounts()

    mock_get.assert_called_once()
    assert isinstance(output, ExtendedDict)
    assert output["999999999999"]["classification"] == "shared"


def test_label_account_tags_resource(organizations_connector: _TestAWSOrganizations):
    client = organizations_connector._clients["organizations"]
    organizations_connector.logger = MagicMock()

    organizations_connector.label_account("123456789012", {"Env": "prod", "Owner": "platform"})

    assert client.tag_calls == [
        {
            "ResourceId": "123456789012",
            "Tags": [
                {"Key": "Env", "Value": "prod"},
                {"Key": "Owner", "Value": "platform"},
            ],
        }
    ]
    logs = _logged_text(organizations_connector.logger)
    assert "123456789012" not in logs
    assert "[REDACTED]" in logs


def test_get_organization_accounts_redacts_root_parent_id() -> None:
    class _Paginator:
        def __init__(self, pages: list[dict[str, Any]]) -> None:
            self.pages = pages

        def paginate(self, **_: Any) -> list[dict[str, Any]]:
            return self.pages

    class _RootClient:
        def list_roots(self):
            return {"Roots": [{"Id": "r-sensitive-root"}]}

        def get_paginator(self, name: str):
            if name == "list_accounts_for_parent":
                return _Paginator([{"Accounts": []}])
            if name == "list_organizational_units_for_parent":
                return _Paginator([{"OrganizationalUnits": []}])
            return _Paginator([])

    connector = _TestAWSOrganizations()
    connector.logger = MagicMock()
    connector.register_client("organizations", _RootClient())

    assert connector.get_organization_accounts() == {}

    logs = _logged_text(connector.logger)
    assert "r-sensitive-root" not in logs
    assert "[REDACTED]" in logs


def test_get_organization_accounts_redacts_missing_root_payload() -> None:
    class _BadRootClient:
        def list_roots(self):
            return {"Roots": [{"AccountId": "123456789012"}]}

    connector = _TestAWSOrganizations()
    connector.logger = MagicMock()
    connector.register_client("organizations", _BadRootClient())

    with pytest.raises(RuntimeError) as exc_info:
        connector.get_organization_accounts()

    assert "123456789012" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_get_organization_accounts_recurses_units_tags_and_sorts() -> None:
    """Organization account discovery should merge OU metadata, tags, and sort promoted payloads."""
    client = _OrganizationTreeClient(
        account_pages={
            "r-root": [
                {
                    "Accounts": [
                        {
                            "Id": "222222222222",
                            "Name": "Beta",
                            "Email": "beta@example.com",
                            "Status": "ACTIVE",
                        }
                    ]
                }
            ],
            "ou-prod": [
                {
                    "Accounts": [
                        {
                            "Id": "111111111111",
                            "Name": "Alpha",
                            "Email": "alpha@example.com",
                            "Status": "ACTIVE",
                        }
                    ]
                }
            ],
        },
        ou_pages={
            "r-root": [
                {
                    "OrganizationalUnits": [
                        {"Id": "ou-prod", "Arn": "arn:aws:organizations::123:ou/o-root/ou-prod", "Name": "Prod"}
                    ]
                }
            ],
            "ou-prod": [{"OrganizationalUnits": []}],
        },
        tags_by_resource={
            "111111111111": [{"Key": "Environment", "Value": "prod"}],
            "222222222222": [{"Key": "Owner", "Value": "platform"}],
        },
    )
    connector = _TestAWSOrganizations()
    connector.register_client("organizations", client)

    result = connector.get_organization_accounts(unhump_accounts=True, sort_by_name=True)

    assert isinstance(result, ExtendedDict)
    assert list(result.keys()) == ["111111111111", "222222222222"]
    assert result["111111111111"]["ou_name"] == "Prod"
    assert result["111111111111"]["tags"]["environment"] == "prod"
    assert result["111111111111"]["managed"] is False
    assert result["222222222222"]["tags"]["owner"] == "platform"


def test_get_controltower_accounts_redacts_provider_warning() -> None:
    class _ControlTowerClient:
        def get_paginator(self, _: str):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Denied for 123456789012 token=raw-token"}},
                "SearchProvisionedProducts",
            )

    connector = _TestAWSOrganizations()
    connector.logger = MagicMock()
    connector.register_client("servicecatalog", _ControlTowerClient())

    assert connector.get_controltower_accounts() == {}

    logs = _logged_text(connector.logger)
    assert "123456789012" not in logs
    assert "raw-token" not in logs
    assert "[REDACTED]" in logs


def test_get_controltower_accounts_extracts_outputs_and_skips_failed_products() -> None:
    """Control Tower discovery should map AccountId outputs and skip unreadable products."""

    class _ProvisionedProductsPaginator:
        def paginate(self, **_: Any) -> list[dict[str, Any]]:
            return [
                {
                    "ProvisionedProducts": [
                        {"Id": "pp-good", "Name": "Managed Alpha", "Status": "AVAILABLE"},
                        {"Id": "pp-denied", "Name": "Denied", "Status": "TAINTED"},
                        {"Name": "No Id", "Status": "AVAILABLE"},
                    ]
                }
            ]

    class _ControlTowerClient:
        def get_paginator(self, name: str):
            assert name == "search_provisioned_products"
            return _ProvisionedProductsPaginator()

        def get_provisioned_product_outputs(self, ProvisionedProductId: str):
            if ProvisionedProductId == "pp-denied":
                raise ClientError({"Error": {"Code": "Denied", "Message": "private account 123456789012"}}, "Outputs")
            return {"Outputs": [{"OutputKey": "AccountId", "OutputValue": "111111111111"}]}

    connector = _TestAWSOrganizations()
    connector.register_client("servicecatalog", _ControlTowerClient())

    result = connector.get_controltower_accounts(unhump_accounts=True, sort_by_name=True)

    assert isinstance(result, ExtendedDict)
    assert list(result.keys()) == ["111111111111"]
    assert result["111111111111"]["name"] == "Managed Alpha"
    assert result["111111111111"]["managed"] is True
    assert result["111111111111"]["provisioned_product_id"] == "pp-good"


def test_preprocess_organization_compiles_sections(mocker, organizations_connector: _TestAWSOrganizations):
    mock_get_accounts = mocker.patch.object(
        organizations_connector,
        "get_accounts",
        return_value={"123": {"name": "core"}},
    )
    mock_classify = mocker.patch.object(
        organizations_connector,
        "classify_accounts",
        side_effect=lambda accounts, **_: {k: {**v, "classification": "production"} for k, v in accounts.items()},
    )
    mock_get_units = mocker.patch.object(
        organizations_connector,
        "get_organization_units",
        return_value={"ou-1": {"name": "Shared"}},
    )

    result = organizations_connector.preprocess_organization()

    mock_get_accounts.assert_called_once()
    mock_classify.assert_called_once()
    mock_get_units.assert_called_once()

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["accounts"], ExtendedDict)
    assert result["root_id"] == "r-root"
    assert result["account_count"] == 1
    assert result["ou_count"] == 1
    assert result["accounts"]["123"]["classification"] == "production"
    assert result["organizational_units"] == {"ou-1": {"name": "Shared"}}


def test_preprocess_organization_can_skip_classification(mocker, organizations_connector: _TestAWSOrganizations):
    """Legacy preprocess helper should be able to emit raw account metadata."""
    mock_get_accounts = mocker.patch.object(
        organizations_connector,
        "get_accounts",
        return_value={"123": {"name": "core"}},
    )
    mock_classify = mocker.patch.object(organizations_connector, "classify_accounts")
    mocker.patch.object(organizations_connector, "get_organization_units", return_value={})

    result = organizations_connector.preprocess_organization(include_classification=False)

    mock_get_accounts.assert_called_once()
    mock_classify.assert_not_called()
    assert result["accounts"] == {"123": {"name": "core"}}
    assert result["account_count"] == 1


def test_get_accounts_merges_controltower_data(mocker, organizations_connector: _TestAWSOrganizations):
    mock_org = mocker.patch.object(
        organizations_connector,
        "get_organization_accounts",
        return_value={
            "200": {"Name": "Beta", "managed": False},
            "300": {"Name": "Gamma", "managed": False},
        },
    )
    mock_ctrl = mocker.patch.object(
        organizations_connector,
        "get_controltower_accounts",
        return_value={
            "100": {"Name": "Alpha", "managed": True},
            "200": {"Name": "Beta", "managed": True},
        },
    )

    result = organizations_connector.get_accounts(unhump_accounts=True, sort_by_name=True)

    mock_org.assert_called_once()
    mock_ctrl.assert_called_once()

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["100"], ExtendedDict)
    assert isinstance(result["100"]["name"], ExtendedString)
    assert list(result.keys()) == ["100", "200", "300"]
    assert result["200"]["managed"] is True
    assert result["100"]["name"] == "Alpha"


def test_get_accounts_can_skip_controltower_merge(mocker, organizations_connector: _TestAWSOrganizations):
    """Combined account discovery should support Organizations-only callers."""
    mocker.patch.object(
        organizations_connector,
        "get_organization_accounts",
        return_value={"200": {"Name": "Beta", "managed": False}},
    )
    controltower = mocker.patch.object(organizations_connector, "get_controltower_accounts", return_value={})

    result = organizations_connector.get_accounts(include_controltower=False, unhump_accounts=False)

    controltower.assert_not_called()
    assert result["200"]["Name"] == "Beta"
    assert result["200"]["managed"] is False


def test_get_organization_units_builds_recursive_paths() -> None:
    """Organizational unit discovery should preserve recursive OU paths."""
    client = _OrganizationTreeClient(
        ou_pages={
            "r-root": [
                {
                    "OrganizationalUnits": [
                        {"Id": "ou-prod", "Arn": "arn:aws:organizations::123:ou/o-root/ou-prod", "Name": "Prod"}
                    ]
                }
            ],
            "ou-prod": [
                {
                    "OrganizationalUnits": [
                        {"Id": "ou-apps", "Arn": "arn:aws:organizations::123:ou/o-root/ou-apps", "Name": "Apps"}
                    ]
                }
            ],
            "ou-apps": [{"OrganizationalUnits": []}],
        }
    )
    connector = _TestAWSOrganizations()
    connector.register_client("organizations", client)

    result = connector.get_organization_units(unhump_units=True)

    assert isinstance(result, ExtendedDict)
    assert result["ou-prod"]["path"] == "Prod"
    assert result["ou-apps"]["path"] == "Prod/Apps"


def test_build_org_units_with_tags_collects_control_tower_labels() -> None:
    """Tagged OU helper should return normalized metadata used by account labeling."""
    client = _OrganizationTreeClient(
        ou_pages={
            "r-root": [
                {
                    "OrganizationalUnits": [
                        {"Id": "ou-prod", "Arn": "arn:aws:organizations::123:ou/o-root/ou-prod", "Name": "Prod"}
                    ]
                }
            ],
            "ou-prod": [{"OrganizationalUnits": []}],
        },
        tags_by_resource={"ou-prod": [{"Key": "Environment", "Value": "prod"}]},
    )
    connector = _TestAWSOrganizations()
    connector.register_client("organizations", client)

    result = connector._build_org_units_with_tags(role_arn=None)

    assert result == {
        "ou-prod": {
            "id": "ou-prod",
            "name": "Prod",
            "arn": "arn:aws:organizations::123:ou/o-root/ou-prod",
            "tags": {"Environment": "prod"},
            "control_tower_organizational_unit": "Prod (ou-prod)",
        }
    }


def test_label_aws_accounts_builds_metadata(mocker, organizations_connector: _TestAWSOrganizations):
    mocker.patch.object(
        organizations_connector,
        "get_organization_accounts",
        return_value={
            "123456789012": {
                "Name": "Prod Account",
                "Email": "ops@example.com",
                "OuId": "ou-prod",
                "OuName": "Prod",
                "tags": {"Environment": "prod", "ExecutionRoleName": "CustomRole"},
            }
        },
    )
    mocker.patch.object(organizations_connector, "get_controltower_accounts", return_value={})
    mocker.patch.object(
        organizations_connector,
        "_build_org_units_with_tags",
        return_value={
            "ou-prod": {
                "id": "ou-prod",
                "name": "Prod",
                "tags": {"Spoke": "true"},
            }
        },
    )
    organizations_connector.get_caller_account_id = lambda: "000000000000"  # type: ignore[assignment]

    labeled = organizations_connector.label_aws_accounts(domains={"prod": "example.com"})
    account = labeled["123456789012"]

    assert isinstance(labeled, ExtendedDict)
    assert isinstance(account, ExtendedDict)
    assert isinstance(account["execution_role_arn"], ExtendedString)
    assert account["json_key"] == "ProdAccount"
    assert account["execution_role_arn"].endswith("role/CustomRole")
    assert account["environment"] == "prod"
    assert account["spoke"] is True
    assert ".example.com" in account["subdomain"]


def test_build_labeled_account_handles_root_user_defaults_and_unit_name_lookup(
    organizations_connector: _TestAWSOrganizations,
):
    """Account labeling should cover root account and OU-name lookup defaults."""
    labeled = organizations_connector._build_labeled_account(
        account_id="123456789012",
        account_data={
            "Name": "User-Sandbox",
            "Email": "user@example.com",
            "OuName": "Sandbox",
            "tags": {"Classifications": "Sandbox Accounts"},
        },
        controltower_data=None,
        units_lookup={
            "ou-sandbox": {
                "id": "ou-sandbox",
                "name": "Sandbox",
                "tags": {"Spoke": "true", "Classifications": "Development Accounts"},
            }
        },
        domains={"dev": "dev.example.com", "default": "example.com"},
        caller_account_id="123456789012",
    )

    assert labeled["execution_role_arn"] == ""
    assert labeled["environment"] == "dev"
    assert labeled["domain"] == "dev.example.com"
    assert labeled["subdomain"] == "dev.example.com"
    assert labeled["spoke"] is True
    assert set(labeled["classifications"]) == {"accounts", "sandbox", "development"}


def test_label_aws_accounts_includes_controltower_only_accounts(mocker, organizations_connector: _TestAWSOrganizations):
    """Control Tower-only accounts should still receive normalized account labels."""
    mocker.patch.object(organizations_connector, "get_organization_accounts", return_value={})
    mocker.patch.object(
        organizations_connector,
        "get_controltower_accounts",
        return_value={
            "999999999999": {
                "Name": "Managed Shared",
                "Email": "shared@example.com",
                "managed": True,
                "OrganizationalUnit": "Shared",
                "ProvisionedProductId": "pp-999",
                "tags": {"Environment": "stg"},
            }
        },
    )
    organizations_connector.get_caller_account_id = lambda: "000000000000"  # type: ignore[assignment]

    result = organizations_connector.label_aws_accounts(
        domains={"stg": "example.com"},
        aws_organization_units={"ou-shared": {"id": "ou-shared", "name": "Shared", "tags": {}}},
    )

    account = result["999999999999"]
    assert account["managed"] is True
    assert account["provisioned_product_id"] == "pp-999"
    assert account["organizational_unit"] == "Shared"
    assert account["subdomain"] == "managedshared.example.com"


def test_classify_aws_accounts_generates_suffix(organizations_connector: _TestAWSOrganizations):
    labeled = {
        "123": {"classifications": ["production", "shared"]},
        "456": {"classifications": ["development"]},
    }

    result = organizations_connector.classify_aws_accounts(labeled_accounts=labeled, suffix="_east")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["production_accounts_east"], ExtendedList)
    assert isinstance(result["production_accounts_east"][0], ExtendedString)
    assert result["production_accounts_east"] == ["123"]
    assert result["development_accounts_east"] == ["456"]


def test_classify_aws_accounts_fetches_labels_when_domains_are_provided(
    mocker,
    organizations_connector: _TestAWSOrganizations,
):
    """Classification grouping should build labels when callers provide source domains."""
    label = mocker.patch.object(
        organizations_connector,
        "label_aws_accounts",
        return_value={
            "123": {"classifications": ["production", "accounts"]},
            "456": {"classifications": ["shared"]},
        },
    )

    result = organizations_connector.classify_aws_accounts(domains={"prod": "example.com"})

    label.assert_called_once()
    assert result == {"production_accounts": ["123"], "shared_accounts": ["456"]}


def test_classify_aws_accounts_requires_domains_when_labels_are_missing(
    organizations_connector: _TestAWSOrganizations,
):
    """Classification grouping should fail loudly without enough source data."""
    with pytest.raises(ValueError, match="domains mapping required"):
        organizations_connector.classify_aws_accounts()


def test_preprocess_aws_organization_uses_helpers(mocker, organizations_connector: _TestAWSOrganizations):
    labeled_accounts = {
        "123": {
            "account_name": "Prod Account",
            "email": "prod@example.com",
            "json_key": "ProdAccount",
            "classifications": ["production"],
        }
    }
    mocker.patch.object(
        organizations_connector,
        "_build_org_units_with_tags",
        return_value={"ou-prod": {"id": "ou-prod", "name": "Prod", "tags": {}}},
    )
    mocker.patch.object(
        organizations_connector,
        "label_aws_accounts",
        return_value=labeled_accounts,
    )
    mocker.patch.object(
        organizations_connector,
        "classify_aws_accounts",
        return_value={"production_accounts": ["123"]},
    )

    class _RootsClient:
        def list_roots(self):
            return {"Roots": [{"Id": "r-root"}]}

    mocker.patch.object(
        organizations_connector,
        "get_aws_client",
        return_value=_RootsClient(),
    )

    context = organizations_connector.preprocess_aws_organization(domains={"prod": "example.com"})

    assert isinstance(context, ExtendedDict)
    assert isinstance(context["accounts_by_name"], ExtendedDict)
    assert isinstance(context["organization"], ExtendedDict)
    assert context["organization"]["root_id"] == "r-root"
    assert context["accounts_by_name"]["Prod Account"]["email"] == "prod@example.com"
    assert context["accounts_by_classification"]["production_accounts"] == ["123"]


def test_preprocess_aws_organization_accepts_precomputed_units(mocker, organizations_connector: _TestAWSOrganizations):
    """Full organization preprocessing should reuse caller-provided OU metadata."""
    build_units = mocker.patch.object(organizations_connector, "_build_org_units_with_tags")
    mocker.patch.object(
        organizations_connector,
        "label_aws_accounts",
        return_value={
            "123": {
                "account_name": "Shared",
                "email": "shared@example.com",
                "json_key": "Shared",
                "classifications": ["shared"],
            }
        },
    )
    mocker.patch.object(organizations_connector, "classify_aws_accounts", return_value={"shared_accounts": ["123"]})

    context = organizations_connector.preprocess_aws_organization(
        domains={"default": "example.com"},
        aws_organization_units={"ou-shared": {"id": "ou-shared", "name": "Shared", "classifications": ["shared"]}},
    )

    build_units.assert_not_called()
    assert context["organization"]["ou_count"] == 1
    assert context["unit_classifications_by_name"]["Shared"] == ["shared"]
