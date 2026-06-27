"""Tests for Anthropic AI tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data


def test_anthropic_list_models():
    """Test list_models tool."""
    from cloud_connectors.anthropic.tools import anthropic_list_models

    with patch("cloud_connectors.anthropic.AnthropicConnector") as mock_connector_class:
        mock_connector = MagicMock()
        mock_connector.list_models.return_value = extend_data(
            [{"id": "claude-3-opus", "display_name": "Claude 3 Opus"}]
        )
        mock_connector_class.return_value = mock_connector

        result = anthropic_list_models()
        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert isinstance(result[0]["id"], ExtendedString)
        assert len(result) == 1
        assert result[0]["id"] == "claude-3-opus"


def test_anthropic_create_message():
    """Test create_message tool."""
    from cloud_connectors.anthropic.tools import anthropic_create_message

    with patch("cloud_connectors.anthropic.AnthropicConnector") as mock_connector_class:
        mock_connector = MagicMock()
        mock_connector.create_message.return_value = extend_data(
            {
                "id": "msg_123",
                "content": [{"type": "text", "text": "Hello!"}],
                "model": "claude-3-opus",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        mock_connector_class.return_value = mock_connector

        result = anthropic_create_message(model="claude-3-opus", prompt="Hi")
        assert isinstance(result, ExtendedDict)
        assert isinstance(result["text"], ExtendedString)
        assert isinstance(result["usage"], ExtendedDict)
        assert result["id"] == "msg_123"
        assert result["text"] == "Hello!"
