"""Tests for Slack AI tools.

Tests mock the SlackConnector to avoid live API calls and
handle the slack_sdk optional dependency gracefully.
"""

from __future__ import annotations

import sys

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString


@pytest.fixture(autouse=True)
def mock_slack_sdk():
    """Mock slack_sdk module for all tests since it's an optional dependency."""
    # Create mock modules
    mock_slack_sdk = MagicMock()
    mock_slack_sdk.errors = MagicMock()
    mock_slack_sdk.errors.SlackApiError = Exception
    mock_slack_sdk.web = MagicMock()
    mock_slack_sdk.web.WebClient = MagicMock()

    # Insert into sys.modules before importing vendor_fabric.slack
    with patch.dict(
        sys.modules,
        {
            "slack_sdk": mock_slack_sdk,
            "slack_sdk.errors": mock_slack_sdk.errors,
            "slack_sdk.web": mock_slack_sdk.web,
        },
    ):
        yield mock_slack_sdk


class TestSlackToolDefinitions:
    """Test tool definitions and metadata."""

    def test_tool_definitions_exist(self, mock_slack_sdk):
        """Test that TOOL_DEFINITIONS is populated."""
        from vendor_fabric.slack.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self, mock_slack_sdk):
        """Test that all tools have name, description, and func."""
        from vendor_fabric.slack.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Tool missing 'name': {defn}"
            assert "description" in defn, f"Tool missing 'description': {defn}"
            assert "func" in defn, f"Tool missing 'func': {defn}"
            assert callable(defn["func"]), f"Tool func not callable: {defn['name']}"

    def test_tool_names_prefixed(self, mock_slack_sdk):
        """Test that all tool names are prefixed with 'slack_'."""
        from vendor_fabric.slack.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("slack_"), f"Tool name not prefixed: {defn['name']}"


class TestListChannels:
    """Tests for list_channels tool."""

    def test_list_channels_basic(self, mock_slack_sdk):
        """Test basic list_channels functionality."""
        from vendor_fabric.slack.tools import list_channels

        mock_connector = MagicMock()
        mock_connector.list_conversations.return_value = {
            "C12345": {
                "name": "general",
                "is_private": False,
                "topic": {"value": "General discussion"},
                "purpose": {"value": "Company-wide announcements"},
                "num_members": 42,
            },
            "C67890": {
                "name": "random",
                "is_private": False,
                "topic": {"value": "Random stuff"},
                "purpose": {"value": "Water cooler"},
                "num_members": 38,
            },
        }

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            result = list_channels()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["id"] == "C12345"
        assert result[0]["name"] == "general"
        assert isinstance(result[0]["name"], ExtendedString)
        assert result[0]["member_count"] == 42

    def test_list_channels_with_archived(self, mock_slack_sdk):
        """Test list_channels including archived."""
        from vendor_fabric.slack.tools import list_channels

        mock_connector = MagicMock()
        mock_connector.list_conversations.return_value = {}

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            list_channels(exclude_archived=False)

        mock_connector.list_conversations.assert_called_once()
        call_kwargs = mock_connector.list_conversations.call_args[1]
        assert call_kwargs["exclude_archived"] is False


class TestListUsers:
    """Tests for list_users tool."""

    def test_list_users_basic(self, mock_slack_sdk):
        """Test basic list_users functionality."""
        from vendor_fabric.slack.tools import list_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = {
            "U12345": {
                "name": "john.doe",
                "real_name": "John Doe",
                "profile": {"email": "john@example.com"},
                "is_admin": True,
                "is_bot": False,
            },
            "U67890": {
                "name": "jane.smith",
                "real_name": "Jane Smith",
                "profile": {"email": "jane@example.com"},
                "is_admin": False,
                "is_bot": False,
            },
        }

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            result = list_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["id"] == "U12345"
        assert result[0]["name"] == "john.doe"
        assert isinstance(result[0]["email"], ExtendedString)
        assert result[0]["email"] == "john@example.com"
        assert result[0]["is_admin"] is True

    def test_list_users_with_bots(self, mock_slack_sdk):
        """Test list_users including bots."""
        from vendor_fabric.slack.tools import list_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = {}

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            list_users(include_bots=True)

        mock_connector.list_users.assert_called_once()
        call_kwargs = mock_connector.list_users.call_args[1]
        assert call_kwargs["include_bots"] is True


class TestSendMessage:
    """Tests for send_message tool."""

    def test_send_message_basic(self, mock_slack_sdk):
        """Test basic send_message functionality."""
        from vendor_fabric.slack.tools import send_message

        mock_connector = MagicMock()
        mock_connector.send_message.return_value = "1234567890.123456"

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            result = send_message(channel="general", text="Hello, world!")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["channel"], ExtendedString)
        assert result["channel"] == "general"
        assert result["text"] == "Hello, world!"
        assert result["timestamp"] == "1234567890.123456"
        assert result["status"] == "sent"

    def test_send_message_with_thread(self, mock_slack_sdk):
        """Test send_message with thread_id."""
        from vendor_fabric.slack.tools import send_message

        mock_connector = MagicMock()
        mock_connector.send_message.return_value = "1234567890.123457"

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            send_message(channel="general", text="Reply", thread_id="1234567890.123456")

        mock_connector.send_message.assert_called_once()
        call_kwargs = mock_connector.send_message.call_args[1]
        assert call_kwargs["thread_id"] == "1234567890.123456"


class TestGetChannelHistory:
    """Tests for get_channel_history tool."""

    def test_get_channel_history_basic(self, mock_slack_sdk):
        """Test basic get_channel_history functionality."""
        from vendor_fabric.slack.tools import get_channel_history

        mock_connector = MagicMock()
        mock_connector.list_conversations.return_value = {
            "C12345": {"name": "general"},
        }
        mock_connector._call_api.return_value = {
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "user": "U12345",
                    "text": "Hello, world!",
                    "type": "message",
                },
                {
                    "ts": "1234567890.123457",
                    "user": "U67890",
                    "text": "Hi there!",
                    "type": "message",
                },
            ]
        }

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            result = get_channel_history(channel="general")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["timestamp"] == "1234567890.123456"
        assert result[0]["user"] == "U12345"
        assert isinstance(result[0]["text"], ExtendedString)
        assert result[0]["text"] == "Hello, world!"

    def test_get_channel_history_channel_not_found(self, mock_slack_sdk):
        """Test get_channel_history with non-existent channel."""
        from vendor_fabric.slack.tools import get_channel_history

        mock_connector = MagicMock()
        mock_connector.list_conversations.return_value = {}

        with patch("vendor_fabric.slack.tools._get_connector", return_value=mock_connector):
            result = get_channel_history(channel="nonexistent")

        assert isinstance(result, ExtendedList)
        assert len(result) == 0


class TestGetTools:
    """Tests for get_tools function."""

    def test_get_strands_tools(self, mock_slack_sdk):
        """Test getting tools as plain functions."""
        from vendor_fabric.slack.tools import get_strands_tools

        tools = get_strands_tools()
        assert len(tools) > 0
        assert all(callable(t) for t in tools)

    def test_get_tools_auto_fallback(self, mock_slack_sdk):
        """Test auto-detection falls back to strands/functions."""
        from vendor_fabric.slack.tools import get_tools

        with patch("vendor_fabric._optional.is_available", return_value=False):
            tools = get_tools(framework="auto")

        assert len(tools) > 0
        assert all(callable(t) for t in tools)

    def test_get_tools_invalid_framework(self, mock_slack_sdk):
        """Test invalid framework raises error."""
        from vendor_fabric.slack.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools(framework="invalid")
