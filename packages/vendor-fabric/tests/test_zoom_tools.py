"""Tests for Zoom provider capabilities."""

from unittest.mock import MagicMock, patch

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString


CONNECTOR_PATCH = "vendor_fabric.zoom.ZoomConnector"


class TestToolDefinitions:
    """Test capability definitions."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS exists and has content."""
        from vendor_fabric.zoom.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all capability definitions have required fields."""
        from vendor_fabric.zoom.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn
            assert "description" in defn
            assert "func" in defn
            assert callable(defn["func"])

    def test_tool_names_prefixed(self):
        """Test that all capability names are prefixed with 'zoom_'."""
        from vendor_fabric.zoom.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("zoom_")

    def test_expected_tools_present(self):
        """Test that expected capabilities are present."""
        from vendor_fabric.zoom.tools import TOOL_DEFINITIONS

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
        from vendor_fabric.zoom.tools import list_users

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
        from vendor_fabric.zoom.tools import list_users

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
        from vendor_fabric.zoom.tools import list_users

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
        from vendor_fabric.zoom.tools import get_user

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
        from vendor_fabric.zoom.tools import get_user

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
        from vendor_fabric.zoom.tools import list_meetings

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
        from vendor_fabric.zoom.tools import list_meetings

        mock_connector = MagicMock()
        mock_connector.list_meetings.return_value = []
        mock_connector_class.return_value = mock_connector

        list_meetings("user1@example.com", meeting_type="live")

        mock_connector.list_meetings.assert_called_once_with("user1@example.com", "live")

    @patch(CONNECTOR_PATCH)
    def test_list_meetings_with_max_results(self, mock_connector_class):
        """Test listing meetings with max_results limit."""
        from vendor_fabric.zoom.tools import list_meetings

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
        from vendor_fabric.zoom.tools import get_meeting

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
