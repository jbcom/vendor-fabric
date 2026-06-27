"""Tests for Anthropic connector."""

from __future__ import annotations

import os

from unittest.mock import MagicMock, patch

import httpx
import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data

from vendor_fabric.anthropic import (
    CLAUDE_MODELS,
    AnthropicAPIError,
    AnthropicAuthError,
    AnthropicConnector,
    AnthropicError,
    ContentBlock,
    Message,
    MessageRole,
    Model,
    Usage,
)


def _json_response(payload: object, status_code: int = 200) -> httpx.Response:
    """Build an HTTPX response whose JSON must be read from content bytes."""
    response = httpx.Response(status_code, json=payload)
    response.json = MagicMock(side_effect=AssertionError("Anthropic responses must be decoded from content bytes"))
    return response


def _text_response(text: str, status_code: int = 200) -> httpx.Response:
    """Build an HTTPX response with invalid/non-JSON body text."""
    response = httpx.Response(status_code, content=text.encode())
    response.json = MagicMock(side_effect=AssertionError("Anthropic responses must be decoded from content bytes"))
    return response


def _logged_text(logger: MagicMock) -> str:
    """Return concatenated mock logger messages."""
    return "\n".join(str(arg) for call in logger.method_calls for arg in call.args)


class TestModels:
    """Tests for Pydantic models."""

    def test_content_block(self):
        """ContentBlock should parse correctly."""
        block = ContentBlock(type="text", text="Hello, world!")
        assert block.type == "text"
        assert block.text == "Hello, world!"

    def test_usage(self):
        """Usage should parse correctly."""
        usage = Usage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    def test_message(self):
        """Message should parse correctly."""
        message = Message(
            id="msg_123",
            type="message",
            role=MessageRole.ASSISTANT,
            content=[ContentBlock(type="text", text="Hello!")],
            model="claude-sonnet-4-20250514",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert message.id == "msg_123"
        assert message.role == MessageRole.ASSISTANT
        assert message.text == "Hello!"

    def test_message_text_property(self):
        """Message.text should concatenate text blocks."""
        message = Message(
            id="msg_123",
            type="message",
            role=MessageRole.ASSISTANT,
            content=[
                ContentBlock(type="text", text="Hello"),
                ContentBlock(type="text", text=" "),
                ContentBlock(type="text", text="World!"),
            ],
            model="claude-3-sonnet",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert message.text == "Hello World!"

    def test_model(self):
        """Model should parse correctly."""
        model = Model(id="claude-sonnet-4-20250514", display_name="Claude Sonnet 4")
        assert model.id == "claude-sonnet-4-20250514"
        assert model.display_name == "Claude Sonnet 4"


class TestAnthropicConnector:
    """Tests for AnthropicConnector."""

    def test_init_without_api_key(self):
        """Initialization without API key should fail."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AnthropicError, match="ANTHROPIC_API_KEY is required"):
                AnthropicConnector()

    def test_init_with_api_key(self):
        """Initialization with API key should succeed."""
        import httpx

        with patch.object(httpx, "Client"):
            connector = AnthropicConnector(api_key="test-key")
            assert connector.api_key == "test-key"
            assert connector.api_version == "2023-06-01"

    def test_is_available_true(self):
        """is_available should return True when env var is set."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            assert AnthropicConnector.is_available() is True

    def test_is_available_false(self):
        """is_available should return False when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert AnthropicConnector.is_available() is False

    def test_get_available_models(self):
        """get_available_models should return extended model metadata."""
        models = AnthropicConnector.get_available_models()
        assert "claude-sonnet-4-20250514" in models
        assert "claude-opus-4-20250514" in models
        assert isinstance(models, ExtendedDict)
        assert isinstance(models["claude-sonnet-4-20250514"], ExtendedString)

    def test_validate_model(self):
        """validate_model should check against known models."""
        import httpx

        with patch.object(httpx, "Client"):
            connector = AnthropicConnector(api_key="test-key")
            assert connector.validate_model("claude-sonnet-4-20250514") is True
            assert connector.validate_model("invalid-model") is False

    def test_get_recommended_model(self):
        """get_recommended_model should return appropriate models."""
        import httpx

        with patch.object(httpx, "Client"):
            connector = AnthropicConnector(api_key="test-key")
            # Using verified model IDs from https://docs.anthropic.com/en/docs/about-claude/models
            assert isinstance(connector.get_recommended_model("general"), ExtendedString)
            assert connector.get_recommended_model("general") == "claude-sonnet-4-5-20250929"
            assert connector.get_recommended_model("fast") == "claude-haiku-4-5-20251001"
            assert connector.get_recommended_model("powerful") == "claude-opus-4-5-20251101"

    def test_create_message(self):
        """create_message should send correct request and return message."""
        import httpx

        mock_client = MagicMock()

        mock_response = _json_response(
            {
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello!"}],
                "model": "claude-sonnet-4-20250514",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            message = connector.create_message(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=extend_data([{"role": "user", "content": "Hi"}]),
            )

            assert isinstance(message, ExtendedDict)
            assert isinstance(message["content"], ExtendedList)
            assert isinstance(message["content"][0], ExtendedDict)
            assert isinstance(message["id"], ExtendedString)
            assert message["id"] == "msg_123"
            assert message["role"] == "assistant"
            assert message["content"][0]["text"] == "Hello!"
            assert message["usage"]["input_tokens"] == 10
            assert message["usage"]["output_tokens"] == 5

            # Verify request
            call_args = mock_client.request.call_args
            assert call_args.args[0] == "POST"
            assert "/v1/messages" in call_args.args[1]
            assert call_args.kwargs["json"]["model"] == "claude-sonnet-4-20250514"
            assert call_args.kwargs["json"]["max_tokens"] == 1024
            assert isinstance(call_args.kwargs["json"]["messages"], list)
            assert isinstance(call_args.kwargs["json"]["messages"][0], dict)

    def test_create_message_with_system(self):
        """create_message should include system prompt."""
        import httpx

        mock_client = MagicMock()

        mock_response = _json_response(
            {
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello!"}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            connector.create_message(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": "Hi"}],
                system="You are a helpful assistant.",
            )

            call_args = mock_client.request.call_args
            assert call_args.kwargs["json"]["system"] == "You are a helpful assistant."

    def test_list_models(self):
        """list_models should return parsed models."""
        import httpx

        mock_client = MagicMock()

        mock_response = _json_response(
            {
                "data": [
                    {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
                    {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4"},
                ]
            }
        )
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            models = connector.list_models()

            assert isinstance(models, ExtendedList)
            assert isinstance(models[0], ExtendedDict)
            assert isinstance(models[0]["id"], ExtendedString)
            assert len(models) == 2
            assert models[0]["id"] == "claude-sonnet-4-20250514"

    def test_get_model(self):
        """get_model should return an extended model payload."""
        import httpx

        mock_client = MagicMock()

        mock_response = _json_response({"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"})
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            model = connector.get_model("claude-sonnet-4-20250514")

            assert isinstance(model, ExtendedDict)
            assert isinstance(model["display_name"], ExtendedString)
            assert model["display_name"] == "Claude Sonnet 4"

    def test_count_tokens_returns_vendor_token_count(self):
        """count_tokens should return the explicit Anthropic response value."""
        import httpx

        mock_client = MagicMock()
        mock_response = _json_response({"input_tokens": 42})
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            assert connector.count_tokens(model="claude-sonnet-4-20250514", messages=[]) == 42

    @pytest.mark.parametrize(
        ("method_name", "call", "payload"),
        [
            (
                "create_message",
                lambda connector: connector.create_message(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": "Hi"}],
                ),
                {"role": "assistant", "password": "hunter2", "authorization": "Bearer raw_token"},
            ),
            (
                "list_models",
                lambda connector: connector.list_models(),
                {"data": [{"id": "claude-sonnet-4-20250514", "api_key": "key_123"}]},
            ),
            (
                "get_model",
                lambda connector: connector.get_model("claude-sonnet-4-20250514"),
                {"id": "claude-sonnet-4-20250514", "client_secret": "secret_123"},
            ),
            (
                "count_tokens",
                lambda connector: connector.count_tokens(model="claude-sonnet-4-20250514", messages=[]),
                {"password": "hunter2", "authorization": "Bearer raw_token"},
            ),
        ],
    )
    def test_success_response_validation_errors_are_redacted(self, method_name, call, payload):
        """Malformed success payloads should fail loudly without raw Pydantic details."""
        import httpx

        mock_client = MagicMock()
        mock_response = _json_response(payload)
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            with pytest.raises(AnthropicAPIError) as exc_info:
                call(connector)

        message = str(exc_info.value)
        assert exc_info.value.error_type == "unexpected_response"
        assert method_name in message
        for raw_secret in ["hunter2", "raw_token", "key_123", "secret_123"]:
            assert raw_secret not in message
        assert "ValidationError" not in message
        assert "[REDACTED]" in message

    def test_success_response_json_errors_are_redacted(self):
        """Malformed JSON diagnostics should not expose raw parser exception values."""
        import httpx

        mock_client = MagicMock()
        mock_response = _text_response("bad password=hunter2 Authorization: Bearer raw_token")
        mock_client.request.return_value = mock_response

        with patch.object(httpx, "Client", return_value=mock_client):
            connector = AnthropicConnector(api_key="test-key")
            with pytest.raises(AnthropicAPIError) as exc_info:
                connector.get_model("claude-sonnet-4-20250514")

        message = str(exc_info.value)
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message

    def test_handle_error_redacts_sensitive_vendor_message(self):
        """Anthropic errors should preserve status metadata without leaking secrets."""
        import httpx

        connector = AnthropicConnector(api_key="test-key")
        response = httpx.Response(
            401,
            json={"error": {"type": "auth_error", "message": "denied password=hunter2 Bearer raw_token"}},
        )

        with pytest.raises(AnthropicAuthError) as exc_info:
            connector._handle_error(response)

        message = str(exc_info.value)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_type == "auth_error"
        assert "hunter2" not in message
        assert "raw_token" not in message
        assert "[REDACTED]" in message

class TestClaudeModels:
    """Tests for Claude model constants.

    Source of truth: https://docs.anthropic.com/en/docs/about-claude/models
    """

    def test_claude_models_dict(self):
        """CLAUDE_MODELS should contain verified models from Anthropic API."""
        # Claude 4.5 family
        assert "claude-sonnet-4-5-20250929" in CLAUDE_MODELS
        assert "claude-opus-4-5-20251101" in CLAUDE_MODELS
        assert "claude-haiku-4-5-20251001" in CLAUDE_MODELS
        # Claude 4 family
        assert "claude-sonnet-4-20250514" in CLAUDE_MODELS
        assert "claude-opus-4-20250514" in CLAUDE_MODELS
        # Claude 3.5/3.7 family
        assert "claude-3-5-haiku-20241022" in CLAUDE_MODELS
        assert "claude-3-7-sonnet-20250219" in CLAUDE_MODELS

    def test_claude_models_has_descriptions(self):
        """Each model should have a description."""
        for model_id, description in CLAUDE_MODELS.items():
            assert isinstance(model_id, str)
            assert isinstance(description, str)
            assert len(description) > 0
