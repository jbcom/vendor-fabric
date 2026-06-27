# ruff: noqa: I001
"""Tests for GoogleConnector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.oauth2.service_account")
pytest.importorskip("googleapiclient")

from extended_data.containers import ExtendedDict, ExtendedString
from cloud_connectors.google import GoogleConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


def _service_account():
    """Return a reusable service account payload."""
    return {
        "type": "service_account",
        "client_email": "test@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...test\n-----END RSA PRIVATE KEY-----\n",
        "private_key_id": "key123",
        "project_id": "test-project",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


class _StubRequest:
    """Simple request stub for the Google Admin SDK."""

    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _StubCollection:
    """Collection stub that yields predefined response pages."""

    def __init__(self, pages):
        self._pages = pages
        self._index = 0

    def list(self, **_):
        payload = self._pages[self._index]
        self._index += 1
        return _StubRequest(payload)


class _StubAdminDirectoryService:
    """Admin Directory service stub exposing users() and groups()."""

    def __init__(self, *, user_pages=None, group_pages=None):
        if user_pages is None:
            user_pages = [{"users": []}]
        if group_pages is None:
            group_pages = [{"groups": []}]

        self._user_collection = _StubCollection(user_pages)
        self._group_collection = _StubCollection(group_pages)

    def users(self):
        return self._user_collection

    def groups(self):
        return self._group_collection


class TestGoogleConnector:
    """Test suite for GoogleConnector."""

    def test_init_with_dict_service_account(self, base_connector_kwargs):
        """Test initialization with dictionary service account."""
        service_account = _service_account()

        connector = GoogleConnector(
            service_account_info=service_account,
            **base_connector_kwargs,
        )

        assert connector.service_account_info == service_account
        assert connector._credentials is None

    @patch("cloud_connectors.google.decode_file")
    def test_init_decodes_service_account_string_through_data_boundary(self, mock_decode_file, base_connector_kwargs):
        """Service-account JSON strings should use the shared data decoder."""
        service_account = _service_account()
        service_account_text = '{"type": "service_account"}'
        mock_decode_file.return_value = service_account

        connector = GoogleConnector(
            service_account_info=service_account_text,
            **base_connector_kwargs,
        )

        assert connector.service_account_info == service_account
        mock_decode_file.assert_called_once_with(service_account_text, suffix="json", as_extended=False)

    def test_init_redacts_invalid_service_account_json_logs(self, base_connector_kwargs):
        """Invalid service-account JSON diagnostics should not expose key material."""
        invalid_service_account = '{"private_key": "-----BEGIN RSA PRIVATE KEY-----\\nMIIE...test"'

        with pytest.raises(ValueError) as exc_info:
            GoogleConnector(service_account_info=invalid_service_account, **base_connector_kwargs)

        logs = _logged_text(base_connector_kwargs["logger"].logger)
        diagnostics = logs + str(exc_info.value)
        assert "MIIE...test" not in diagnostics
        assert "BEGIN RSA PRIVATE KEY" not in diagnostics
        assert "[REDACTED]" in diagnostics
        assert exc_info.value.__cause__ is None
        assert all(
            "exc_info" not in logged_call.kwargs for logged_call in base_connector_kwargs["logger"].logger.method_calls
        )

    @patch("cloud_connectors.google.decode_file")
    def test_sequence_option_input_decodes_json_through_data_boundary(self, mock_decode_file, base_connector_kwargs):
        """List-like Google input values should use the shared data decoder."""
        mock_decode_file.return_value = ["/Engineering", "/Platform"]
        connector = GoogleConnector(
            service_account_info=_service_account(),
            inputs={"GOOGLE_OU_ALLOW_LIST": '["/Engineering", "/Platform"]'},
            **base_connector_kwargs,
        )

        result = connector._resolve_sequence_option(None, "GOOGLE_OU_ALLOW_LIST")

        assert result == ["/Engineering", "/Platform"]
        mock_decode_file.assert_called_once_with('["/Engineering", "/Platform"]', suffix="json", as_extended=False)

    @patch("cloud_connectors.google.service_account.Credentials.from_service_account_info")
    def test_credentials_property(self, mock_from_sa, base_connector_kwargs):
        """Test credentials property creates credentials."""
        service_account = _service_account()

        mock_credentials = MagicMock()
        mock_from_sa.return_value = mock_credentials

        connector = GoogleConnector(
            service_account_info=service_account,
            **base_connector_kwargs,
        )

        creds = connector.credentials
        assert creds == mock_credentials
        mock_from_sa.assert_called_once()

    @patch("cloud_connectors.google.service_account.Credentials.from_service_account_info")
    @patch("cloud_connectors.google.build")
    def test_get_service(self, mock_build, mock_from_sa, base_connector_kwargs):
        """Test getting a Google service."""
        service_account = _service_account()

        mock_credentials = MagicMock()
        mock_from_sa.return_value = mock_credentials
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        connector = GoogleConnector(
            service_account_info=service_account,
            **base_connector_kwargs,
        )

        service = connector.get_service("admin", "directory_v1")
        assert service == mock_service
        mock_build.assert_called_once_with("admin", "directory_v1", credentials=mock_credentials)

    @patch("cloud_connectors.google.service_account.Credentials.from_service_account_info")
    @patch("cloud_connectors.google.build")
    def test_get_service_caching(self, mock_build, mock_from_sa, base_connector_kwargs):
        """Test that services are cached."""
        service_account = _service_account()

        mock_credentials = MagicMock()
        mock_from_sa.return_value = mock_credentials
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        connector = GoogleConnector(
            service_account_info=service_account,
            **base_connector_kwargs,
        )

        # Call twice
        service1 = connector.get_service("admin", "directory_v1")
        service2 = connector.get_service("admin", "directory_v1")

        # Build should only be called once
        assert mock_build.call_count == 1
        assert service1 is service2

    @patch.object(GoogleConnector, "get_admin_directory_service")
    def test_list_users_filters_and_transforms(self, mock_get_service, base_connector_kwargs):
        """Ensure list_users applies filtering, flattening, and keying."""
        user_pages = [
            {
                "users": [
                    {
                        "primaryEmail": "bot@example.com",
                        "orgUnitPath": "/Bots",
                        "isBot": True,
                        "name": {"fullName": "Bot Account", "givenName": "Bot", "familyName": "Account"},
                    },
                    {
                        "primaryEmail": "engineer@example.com",
                        "orgUnitPath": "/Engineering",
                        "name": {"fullName": "Eng One", "givenName": "Eng", "familyName": "One"},
                    },
                ],
                "nextPageToken": "token-1",
            },
            {
                "users": [
                    {
                        "primaryEmail": "suspended@example.com",
                        "orgUnitPath": "/Engineering",
                        "suspended": True,
                        "name": {"fullName": "Susp User", "givenName": "Susp", "familyName": "User"},
                    },
                    {
                        "primaryEmail": "sales@example.com",
                        "orgUnitPath": "/Sales",
                        "name": {"fullName": "Sales User", "givenName": "Sales", "familyName": "User"},
                    },
                ],
            },
        ]
        mock_get_service.return_value = _StubAdminDirectoryService(user_pages=user_pages)

        connector = GoogleConnector(service_account_info=_service_account(), **base_connector_kwargs)
        result = connector.list_users(
            ou_allow_list=["/Engineering"],
            ou_deny_list=["/Sales"],
            flatten_names=True,
            key_by_email=True,
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["engineer@example.com"], ExtendedDict)
        assert isinstance(result["engineer@example.com"]["full_name"], ExtendedString)
        assert "bot@example.com" not in result
        assert "suspended@example.com" not in result
        assert "sales@example.com" not in result
        assert result["engineer@example.com"]["full_name"] == "Eng One"
        assert result["engineer@example.com"]["given_name"] == "Eng"
        assert result["engineer@example.com"]["family_name"] == "One"

    @patch.object(GoogleConnector, "get_admin_directory_service")
    def test_list_groups_key_by_email_and_filters(self, mock_get_service, base_connector_kwargs):
        """Ensure list_groups supports filtering and keying similar to list_users."""
        group_pages = [
            {
                "groups": [
                    {"email": "bots@example.com", "orgUnitPath": "/Bots", "type": "BOT"},
                    {
                        "email": "keepers@example.com",
                        "orgUnitPath": "/Engineering",
                        "suspended": True,
                    },
                    {"primaryEmail": "team@example.com", "orgUnitPath": "/Engineering"},
                ]
            }
        ]
        mock_get_service.return_value = _StubAdminDirectoryService(group_pages=group_pages)

        connector = GoogleConnector(service_account_info=_service_account(), **base_connector_kwargs)
        result = connector.list_groups(
            ou_deny_list=["/Bots"],
            include_suspended=True,
            key_by_email=True,
        )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["keepers@example.com"], ExtendedDict)
        assert "bots@example.com" not in result
        assert "keepers@example.com" in result
        assert result["keepers@example.com"]["suspended"] is True
        assert "team@example.com" in result
        assert result["team@example.com"]["primaryEmail"] == "team@example.com"

    def test_unified_connector_exposes_all_google_operations(self, base_connector_kwargs):
        """The single Google connector exposes Workspace, Cloud, and Billing operations."""
        service_account = _service_account()

        connector = GoogleConnector(service_account_info=service_account, **base_connector_kwargs)

        assert hasattr(connector, "list_projects")
        assert hasattr(connector, "list_users")
        assert hasattr(connector, "list_billing_accounts")

    def test_specialized_google_connector_aliases_are_not_preserved(self):
        """Clean major-version surface should keep Google operations on GoogleConnector."""
        import cloud_connectors.google as google_module

        assert not hasattr(google_module, "GoogleCloudConnector")
        assert not hasattr(google_module, "GoogleWorkspaceConnector")
        assert not hasattr(google_module, "GoogleBillingConnector")
