"""Tests for Zoom AI tools."""

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString


CONNECTOR_PATCH = "cloud_connectors.zoom.ZoomConnector"


class TestToolDefinitions:
    """Test tool definitions."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS exists and has content."""
        from cloud_connectors.zoom.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all tool definitions have required fields."""
        from cloud_connectors.zoom.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn
            assert "description" in defn
            assert "func" in defn
            assert callable(defn["func"])

    def test_tool_names_prefixed(self):
        """Test that all tool names are prefixed with 'zoom_'."""
        from cloud_connectors.zoom.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("zoom_")

    def test_expected_tools_present(self):
        """Test that expected tools are present."""
        from cloud_connectors.zoom.tools import TOOL_DEFINITIONS

        tool_names = [defn["name"] for defn in TOOL_DEFINITIONS]
        assert "zoom_list_users" in tool_names
        assert "zoom_get_user" in tool_names
        assert "zoom_list_meetings" in tool_names
        assert "zoom_get_meeting" in tool_names


class TestListUsers:
    """Test list_users tool."""

    @patch(CONNECTOR_PATCH)
    def test_list_users_basic(self, mock_connector_class):
        """Test listing users."""
        from cloud_connectors.zoom.tools import list_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = {
            "user1@example.com": {
                "id": "123",
                "email": "user1@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "type": 2,
                "status": "active",
            },
            "user2@example.com": {
                "id": "456",
                "email": "user2@example.com",
                "first_name": "Jane",
                "last_name": "Smith",
                "type": 2,
                "status": "active",
            },
        }
        mock_connector_class.return_value = mock_connector

        result = list_users()

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["email"] == "user1@example.com"
        assert result[0]["id"] == "123"
        assert isinstance(result[0]["first_name"], ExtendedString)
        assert result[0]["first_name"] == "John"
        assert result[1]["email"] == "user2@example.com"

    @patch(CONNECTOR_PATCH)
    def test_list_users_with_max_results(self, mock_connector_class):
        """Test listing users with max_results limit."""
        from cloud_connectors.zoom.tools import list_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = {
            f"user{i}@example.com": {
                "id": str(i),
                "email": f"user{i}@example.com",
                "first_name": "User",
                "last_name": f"{i}",
                "type": 2,
                "status": "active",
            }
            for i in range(1, 11)
        }
        mock_connector_class.return_value = mock_connector

        result = list_users(max_results=5)

        assert len(result) == 5

    @patch(CONNECTOR_PATCH)
    def test_list_users_empty(self, mock_connector_class):
        """Test listing users when none exist."""
        from cloud_connectors.zoom.tools import list_users

        mock_connector = MagicMock()
        mock_connector.list_users.return_value = {}
        mock_connector_class.return_value = mock_connector

        result = list_users()

        assert len(result) == 0


class TestGetUser:
    """Test get_user tool."""

    @patch(CONNECTOR_PATCH)
    def test_get_user_basic(self, mock_connector_class):
        """Test getting a specific user."""
        from cloud_connectors.zoom.tools import get_user

        mock_connector = MagicMock()
        mock_connector.get_user.return_value = {
            "id": "123",
            "email": "user1@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "type": 2,
            "status": "active",
            "timezone": "America/New_York",
            "pmi": "1234567890",
        }
        mock_connector_class.return_value = mock_connector

        result = get_user("user1@example.com")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["first_name"], ExtendedString)
        assert result["email"] == "user1@example.com"
        assert result["id"] == "123"
        assert result["first_name"] == "John"
        assert result["timezone"] == "America/New_York"
        mock_connector.get_user.assert_called_once_with("user1@example.com")

    @patch(CONNECTOR_PATCH)
    def test_get_user_by_id(self, mock_connector_class):
        """Test getting a user by ID."""
        from cloud_connectors.zoom.tools import get_user

        mock_connector = MagicMock()
        mock_connector.get_user.return_value = {
            "id": "123",
            "email": "user1@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "type": 2,
            "status": "active",
            "timezone": "America/New_York",
            "pmi": "1234567890",
        }
        mock_connector_class.return_value = mock_connector

        result = get_user("123")

        assert result["id"] == "123"
        mock_connector.get_user.assert_called_once_with("123")


class TestListMeetings:
    """Test list_meetings tool."""

    @patch(CONNECTOR_PATCH)
    def test_list_meetings_basic(self, mock_connector_class):
        """Test listing meetings for a user."""
        from cloud_connectors.zoom.tools import list_meetings

        mock_connector = MagicMock()
        mock_connector.list_meetings.return_value = [
            {
                "id": "111",
                "uuid": "abc123",
                "topic": "Team Meeting",
                "start_time": "2024-01-15T10:00:00Z",
                "duration": 60,
                "type": 2,
                "join_url": "https://zoom.us/j/111",
            },
            {
                "id": "222",
                "uuid": "def456",
                "topic": "Client Call",
                "start_time": "2024-01-16T14:00:00Z",
                "duration": 30,
                "type": 2,
                "join_url": "https://zoom.us/j/222",
            },
        ]
        mock_connector_class.return_value = mock_connector

        result = list_meetings("user1@example.com")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["id"] == "111"
        assert result[0]["topic"] == "Team Meeting"
        assert result[1]["id"] == "222"
        mock_connector.list_meetings.assert_called_once_with("user1@example.com", "scheduled")

    @patch(CONNECTOR_PATCH)
    def test_list_meetings_with_type(self, mock_connector_class):
        """Test listing meetings with specific type."""
        from cloud_connectors.zoom.tools import list_meetings

        mock_connector = MagicMock()
        mock_connector.list_meetings.return_value = []
        mock_connector_class.return_value = mock_connector

        list_meetings("user1@example.com", meeting_type="live")

        mock_connector.list_meetings.assert_called_once_with("user1@example.com", "live")

    @patch(CONNECTOR_PATCH)
    def test_list_meetings_with_max_results(self, mock_connector_class):
        """Test listing meetings with max_results limit."""
        from cloud_connectors.zoom.tools import list_meetings

        mock_connector = MagicMock()
        mock_connector.list_meetings.return_value = [
            {
                "id": str(i),
                "uuid": f"uuid{i}",
                "topic": f"Meeting {i}",
                "start_time": "2024-01-15T10:00:00Z",
                "duration": 60,
                "type": 2,
                "join_url": f"https://zoom.us/j/{i}",
            }
            for i in range(1, 11)
        ]
        mock_connector_class.return_value = mock_connector

        result = list_meetings("user1@example.com", max_results=5)

        assert len(result) == 5


class TestGetMeeting:
    """Test get_meeting tool."""

    @patch(CONNECTOR_PATCH)
    def test_get_meeting_basic(self, mock_connector_class):
        """Test getting a specific meeting."""
        from cloud_connectors.zoom.tools import get_meeting

        mock_connector = MagicMock()
        mock_connector.get_meeting.return_value = {
            "id": "111",
            "uuid": "abc123",
            "topic": "Team Meeting",
            "start_time": "2024-01-15T10:00:00Z",
            "duration": 60,
            "timezone": "America/New_York",
            "type": 2,
            "join_url": "https://zoom.us/j/111",
            "host_id": "123",
            "host_email": "host@example.com",
        }
        mock_connector_class.return_value = mock_connector

        result = get_meeting("111")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["topic"], ExtendedString)
        assert result["id"] == "111"
        assert result["topic"] == "Team Meeting"
        assert result["host_email"] == "host@example.com"
        mock_connector.get_meeting.assert_called_once_with("111")


class TestGetTools:
    """Test framework getters."""

    def test_get_strands_tools(self):
        """Test getting Strands tools (plain functions)."""
        from cloud_connectors.zoom.tools import get_strands_tools

        tools = get_strands_tools()
        assert len(tools) == 4
        assert all(callable(t) for t in tools)

    def test_get_tools_strands(self):
        """Test get_tools with strands framework."""
        from cloud_connectors.zoom.tools import get_tools

        tools = get_tools(framework="strands")
        assert len(tools) == 4
        assert all(callable(t) for t in tools)

    def test_get_tools_rejects_functions_alias(self):
        """Plain-function tools should use the canonical strands framework name."""
        from cloud_connectors.zoom.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools(framework="functions")

    def test_get_tools_invalid_framework(self):
        """Test get_tools with invalid framework raises error."""
        from cloud_connectors.zoom.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools(framework="invalid")

    def test_get_tools_auto_default(self):
        """Test get_tools with auto detection returns something."""
        from cloud_connectors.zoom.tools import get_tools

        tools = get_tools(framework="auto")
        assert len(tools) == 4

    def test_get_langchain_tools_import_error(self):
        """Test that get_langchain_tools raises helpful error when langchain not installed."""
        from cloud_connectors.zoom.tools import get_langchain_tools

        with patch.dict("sys.modules", {"langchain_core": None, "langchain_core.tools": None}):
            with pytest.raises(ImportError, match="langchain-core is required"):
                get_langchain_tools()

    def test_get_crewai_tools_import_error(self):
        """Test that get_crewai_tools raises helpful error when crewai not installed."""
        from cloud_connectors.zoom.tools import get_crewai_tools

        with patch.dict("sys.modules", {"crewai": None, "crewai.tools": None}):
            with pytest.raises(ImportError, match="crewai is required"):
                get_crewai_tools()
