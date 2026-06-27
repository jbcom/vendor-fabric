"""Tests for Cursor AI tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from extended_data.containers import ExtendedDict, ExtendedString, extend_data

from vendor_fabric.cursor import AgentState


def test_cursor_launch_agent():
    """Test launch_agent tool."""
    from vendor_fabric.cursor.tools import cursor_launch_agent

    with patch("vendor_fabric.cursor.CursorConnector") as mock_connector_class:
        mock_connector = MagicMock()
        mock_agent = extend_data(
            {
                "id": "agent_123",
                "state": AgentState.RUNNING,
                "repository": "org/repo",
            }
        )
        mock_connector.launch_agent.return_value = mock_agent
        mock_connector_class.return_value = mock_connector

        result = cursor_launch_agent(prompt="Fix bug", repository="org/repo")
        assert isinstance(result, ExtendedDict)
        assert isinstance(result["agent_id"], ExtendedString)
        assert result["agent_id"] == "agent_123"
        assert result["state"] == "running"
        assert result["repository"].sanitize() == "org_repo"


def test_cursor_get_agent_status():
    """Test get_agent_status tool."""
    from vendor_fabric.cursor.tools import cursor_get_agent_status

    with patch("vendor_fabric.cursor.CursorConnector") as mock_connector_class:
        mock_connector = MagicMock()
        mock_agent = extend_data(
            {
                "id": "agent_123",
                "state": AgentState.FINISHED,
                "error": None,
                "pr_url": "https://github.com/org/repo/pull/1",
            }
        )
        mock_connector.get_agent_status.return_value = mock_agent
        mock_connector_class.return_value = mock_connector

        result = cursor_get_agent_status(agent_id="agent_123")
        assert isinstance(result, ExtendedDict)
        assert isinstance(result["state"], ExtendedString)
        assert result["agent_id"] == "agent_123"
        assert result["state"] == "finished"
        assert result["pr_url"] == "https://github.com/org/repo/pull/1"


def test_cursor_get_agent_status_redacts_error():
    """Cursor status tool should not expose secret-bearing agent errors."""
    from vendor_fabric.cursor.tools import cursor_get_agent_status

    with patch("vendor_fabric.cursor.CursorConnector") as mock_connector_class:
        mock_connector = MagicMock()
        mock_agent = extend_data(
            {
                "id": "agent_123",
                "state": AgentState.ERRORED,
                "error": "failed password=hunter2 Authorization: Bearer raw_token",
                "pr_url": None,
            }
        )
        mock_connector.get_agent_status.return_value = mock_agent
        mock_connector_class.return_value = mock_connector

        result = cursor_get_agent_status(agent_id="agent_123")

        assert isinstance(result, ExtendedDict)
        assert "hunter2" not in result["error"]
        assert "raw_token" not in result["error"]
        assert "[REDACTED]" in result["error"]
