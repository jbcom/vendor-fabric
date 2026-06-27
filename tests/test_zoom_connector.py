"""Tests for ZoomConnector."""

from __future__ import annotations

import json

from unittest.mock import MagicMock, patch

import pytest
import requests

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from cloud_connectors.zoom import ZoomConnector


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


def _json_response(payload: object) -> MagicMock:
    """Build a requests-like response whose JSON must be decoded from content."""
    response = MagicMock()
    response.content = json.dumps(payload).encode()
    response.text = response.content.decode()
    response.json.side_effect = AssertionError("Zoom responses must be decoded from content bytes")
    response.raise_for_status = MagicMock()
    return response


def _text_response(text: str) -> MagicMock:
    """Build a requests-like response with invalid/non-JSON body text."""
    response = MagicMock()
    response.content = text.encode()
    response.text = text
    response.json.side_effect = AssertionError("Zoom responses must be decoded from content bytes")
    response.raise_for_status = MagicMock()
    return response


def _token_response(token: str = "test-token") -> MagicMock:
    """Build a successful Zoom OAuth response mock."""
    return _json_response({"access_token": token})


class TestZoomConnector:
    """Test suite for ZoomConnector."""

    def test_init(self, base_connector_kwargs):
        """Test initialization."""
        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        assert connector.client_id == "test-client-id"
        assert connector.client_secret == "test-client-secret"
        assert connector.account_id == "test-account-id"

    @patch("cloud_connectors.zoom.requests.post")
    def test_get_access_token_success(self, mock_post, base_connector_kwargs):
        """Test successful access token retrieval."""
        mock_response = _json_response({"access_token": "test-access-token"})
        mock_post.return_value = mock_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        token = connector.get_access_token()
        assert token == "test-access-token"
        mock_post.assert_called_once()

    @patch("cloud_connectors.zoom.requests.post")
    def test_get_access_token_failure(self, mock_post, base_connector_kwargs):
        """Test failed access token retrieval."""
        mock_post.side_effect = requests.exceptions.RequestException(
            "Connection error test-account-id client_secret=raw-secret"
        )

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError, match="Failed to get Zoom access token") as exc_info:
            connector.get_access_token()

        message = str(exc_info.value)
        assert "test-account-id" not in message
        assert "test-client-secret" not in message
        assert "raw-secret" not in message
        assert "[REDACTED]" in message
        assert exc_info.value.__cause__ is None

    @patch("cloud_connectors.zoom.requests.post")
    def test_get_access_token_malformed_response_is_redacted(self, mock_post, base_connector_kwargs):
        """Missing token responses should fail loudly without exposing OAuth credentials."""
        mock_response = _json_response(
            {
                "password": "hunter2",
                "authorization": "Bearer raw_token",
                "account_id": "test-account-id",
            }
        )
        mock_post.return_value = mock_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError, match="Unexpected Zoom access token response") as exc_info:
            connector.get_access_token()

        message = str(exc_info.value)
        for raw_value in ["hunter2", "raw_token", "test-client-id", "test-client-secret", "test-account-id"]:
            assert raw_value not in message
        assert "[REDACTED]" in message

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_list_users_redacts_request_failure_details(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom list failures should not expose raw secret-bearing exception text."""
        mock_post.return_value = _token_response()
        mock_get.side_effect = requests.exceptions.RequestException(
            "status=401 password=hunter2 Authorization: Bearer raw_token"
        )

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError) as exc_info:
            connector.list_users()

        message = str(exc_info.value)
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message
        assert exc_info.value.__cause__ is None

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_list_users_malformed_response_is_redacted(self, mock_post, mock_get, base_connector_kwargs):
        """Malformed user list responses should not return partial or raw payloads."""
        mock_post.return_value = _token_response()
        mock_users_response = _json_response({"users": [{"password": "hunter2", "authorization": "Bearer raw_token"}]})
        mock_get.return_value = mock_users_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError, match="Unexpected Zoom users response") as exc_info:
            connector.list_users()

        message = str(exc_info.value)
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_list_users(self, mock_post, mock_get, base_connector_kwargs):
        """Test listing Zoom users."""
        mock_post.return_value = _token_response()

        mock_users_response = _json_response(
            {
                "users": [
                    {"email": "user1@example.com", "id": "123", "first_name": "User", "last_name": "One"},
                    {"email": "user2@example.com", "id": "456", "first_name": "User", "last_name": "Two"},
                ],
                "next_page_token": None,
            }
        )
        mock_get.return_value = mock_users_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        users = connector.list_users()
        assert isinstance(users, ExtendedDict)
        assert isinstance(users["user1@example.com"], ExtendedDict)
        assert isinstance(users["user1@example.com"]["first_name"], ExtendedString)
        assert "user1@example.com" in users
        assert "user2@example.com" in users
        assert len(users) == 2

    def test_get_zoom_users_alias_is_not_preserved(self, base_connector_kwargs):
        """The clean major version should expose only the canonical list_users method."""
        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        assert not hasattr(connector, "get_zoom_users")

    @patch("cloud_connectors.zoom.requests.post")
    def test_create_zoom_user(self, mock_post, base_connector_kwargs):
        """Test creating a Zoom user."""
        mock_token_response = _token_response()

        mock_create_response = MagicMock()
        mock_create_response.raise_for_status = MagicMock()

        mock_post.side_effect = [mock_token_response, mock_create_response]

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        result = connector.create_zoom_user("newuser@example.com", "New", "User")
        assert result is True
        assert mock_post.call_count == 2

    @patch("cloud_connectors.zoom.requests.delete")
    @patch("cloud_connectors.zoom.requests.post")
    def test_remove_zoom_user_redacts_error_state_and_logs(self, mock_post, mock_delete, base_connector_kwargs):
        """Zoom mutation failures should redact user IDs and exception secrets."""
        mock_post.return_value = _token_response()
        mock_delete.side_effect = requests.exceptions.RequestException(
            "failed for private-user@example.com?access_token=raw_token"
        )

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        connector.remove_zoom_user("private-user@example.com")

        diagnostics = "\n".join(connector.errors) + _logged_text(connector.logger)
        assert "private-user@example.com" not in diagnostics
        assert "raw_token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        connector.logger.exception.assert_not_called()
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    @patch("cloud_connectors.zoom.requests.post")
    def test_create_zoom_user_redacts_error_state_and_logs(self, mock_post, base_connector_kwargs):
        """Zoom create failures should redact user PII and avoid traceback logs."""
        mock_token_response = _token_response()
        mock_post.side_effect = [
            mock_token_response,
            requests.exceptions.RequestException("failed Jane SecretUser newuser@example.com token=raw-token"),
        ]

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        assert connector.create_zoom_user("newuser@example.com", "Jane", "SecretUser") is False

        diagnostics = "\n".join(connector.errors) + _logged_text(connector.logger)
        assert "newuser@example.com" not in diagnostics
        assert "Jane" not in diagnostics
        assert "SecretUser" not in diagnostics
        assert "raw-token" not in diagnostics
        assert "[REDACTED]" in diagnostics
        connector.logger.exception.assert_not_called()
        assert all("exc_info" not in logged_call.kwargs for logged_call in connector.logger.method_calls)

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_get_user(self, mock_post, mock_get, base_connector_kwargs):
        """Test getting a specific user."""
        mock_post.return_value = _token_response()

        mock_user_response = _json_response(
            {
                "id": "123",
                "email": "user1@example.com",
                "first_name": "User",
                "last_name": "One",
            }
        )
        mock_get.return_value = mock_user_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        user = connector.get_user("user1@example.com")
        assert isinstance(user, ExtendedDict)
        assert isinstance(user["first_name"], ExtendedString)
        assert user["email"] == "user1@example.com"
        assert user["id"] == "123"

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_get_user_redacts_identifier_and_secret_details(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom lookup failures should not echo user identifiers or secrets."""
        mock_post.return_value = _token_response()
        mock_get.side_effect = requests.exceptions.RequestException(
            "404 for user1@example.com and user1%40example.com client_secret=s3cr3t"
        )

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError) as exc_info:
            connector.get_user("user1@example.com")

        message = str(exc_info.value)
        assert "user1@example.com" not in message
        assert "user1%40example.com" not in message
        assert "s3cr3t" not in message
        assert "[REDACTED]" in message
        assert exc_info.value.__cause__ is None

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_get_user_malformed_response_is_redacted(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom user lookups should reject non-object payloads without leaking identifiers."""
        mock_post.return_value = _token_response()
        mock_user_response = _json_response(["private-user@example.com", {"password": "hunter2"}])
        mock_get.return_value = mock_user_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError, match="Unexpected Zoom user response") as exc_info:
            connector.get_user("private-user@example.com")

        message = str(exc_info.value)
        assert "private-user@example.com" not in message
        assert "hunter2" not in message
        assert "[REDACTED]" in message

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_list_meetings(self, mock_post, mock_get, base_connector_kwargs):
        """Test listing meetings for a user."""
        mock_post.return_value = _token_response()

        mock_meetings_response = _json_response(
            {
                "meetings": [
                    {"id": "111", "topic": "Team Meeting"},
                    {"id": "222", "topic": "Client Call"},
                ]
            }
        )
        mock_get.return_value = mock_meetings_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        meetings = connector.list_meetings("user1@example.com")
        assert isinstance(meetings, ExtendedList)
        assert isinstance(meetings[0], ExtendedDict)
        assert len(meetings) == 2
        assert meetings[0]["id"] == "111"

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_list_meetings_redacts_identifier_and_secret_details(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom meeting list failures should not chain raw user identifiers."""
        mock_post.return_value = _token_response()
        mock_get.side_effect = requests.exceptions.RequestException(
            "failed for private-user@example.com type=scheduled token=raw-token"
        )

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError) as exc_info:
            connector.list_meetings("private-user@example.com")

        message = str(exc_info.value)
        assert "private-user@example.com" not in message
        assert "raw-token" not in message
        assert "[REDACTED]" in message
        assert exc_info.value.__cause__ is None

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_list_meetings_malformed_response_is_redacted(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom meeting list responses should preserve the ExtendedList contract."""
        mock_post.return_value = _token_response()
        mock_meetings_response = _json_response(
            {"meetings": [{"id": "111"}, "password=hunter2 Authorization: Bearer raw_token"]}
        )
        mock_get.return_value = mock_meetings_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError, match="Unexpected Zoom meetings response") as exc_info:
            connector.list_meetings("private-user@example.com")

        message = str(exc_info.value)
        assert "private-user@example.com" not in message
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_get_meeting(self, mock_post, mock_get, base_connector_kwargs):
        """Test getting a specific meeting."""
        mock_post.return_value = _token_response()

        mock_meeting_response = _json_response(
            {
                "id": "111",
                "topic": "Team Meeting",
                "start_time": "2024-01-15T10:00:00Z",
            }
        )
        mock_get.return_value = mock_meeting_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        meeting = connector.get_meeting("111")
        assert isinstance(meeting, ExtendedDict)
        assert isinstance(meeting["topic"], ExtendedString)
        assert meeting["id"] == "111"
        assert meeting["topic"] == "Team Meeting"

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_get_meeting_redacts_identifier_and_secret_details(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom meeting lookup failures should not chain raw meeting identifiers."""
        mock_post.return_value = _token_response()
        mock_get.side_effect = requests.exceptions.RequestException("meeting private-meeting token=raw-token")

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError) as exc_info:
            connector.get_meeting("private-meeting")

        message = str(exc_info.value)
        assert "private-meeting" not in message
        assert "raw-token" not in message
        assert "[REDACTED]" in message
        assert exc_info.value.__cause__ is None

    @patch("cloud_connectors.zoom.requests.get")
    @patch("cloud_connectors.zoom.requests.post")
    def test_get_meeting_json_parse_error_is_redacted(self, mock_post, mock_get, base_connector_kwargs):
        """Zoom JSON parse failures should not expose raw meeting IDs or parser text."""
        mock_post.return_value = _token_response()
        mock_meeting_response = _text_response(
            "bad meeting private-meeting password=hunter2 Authorization: Bearer raw_token"
        )
        mock_get.return_value = mock_meeting_response

        connector = ZoomConnector(
            client_id="test-client-id",
            client_secret="test-client-secret",
            account_id="test-account-id",
            **base_connector_kwargs,
        )

        with pytest.raises(RuntimeError, match="Unexpected Zoom meeting response") as exc_info:
            connector.get_meeting("private-meeting")

        message = str(exc_info.value)
        assert "private-meeting" not in message
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message
