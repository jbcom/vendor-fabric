"""Tests for Cursor connector."""

from __future__ import annotations

import json
import os

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data

from cloud_connectors.cursor import (
    Agent,
    AgentState,
    Conversation,
    ConversationMessage,
    CursorAPIError,
    CursorConnector,
    CursorError,
    CursorValidationError,
    Repository,
    sanitize_error,
    validate_agent_id,
    validate_prompt_text,
    validate_repository,
    validate_webhook_url,
)


def _logged_text(logger: MagicMock) -> str:
    """Collect structured mock log calls into one searchable diagnostic string."""
    messages: list[str] = []
    for method_name in ("debug", "info", "warning", "error", "exception"):
        method = getattr(logger, method_name)
        for call in method.call_args_list:
            messages.extend(str(arg) for arg in call.args)
            messages.extend(str(value) for value in call.kwargs.values())
    return "\n".join(messages)


def _json_response(payload: object) -> MagicMock:
    """Build a JSON Cursor API response mock."""
    response = MagicMock()
    response.status_code = 200
    response.is_success = True
    response.headers = {"content-type": "application/json"}
    response.text = json.dumps(payload)
    response.content = response.text.encode()
    response.json.return_value = payload
    return response


class TestValidators:
    """Tests for input validators."""

    def test_validate_agent_id_valid(self):
        """Valid agent IDs should pass."""
        validate_agent_id("abc-123")
        validate_agent_id("agent-id-with-numbers-123")
        validate_agent_id("simple")

    def test_validate_agent_id_empty(self):
        """Empty agent ID should fail."""
        with pytest.raises(CursorValidationError, match="required"):
            validate_agent_id("")

    def test_validate_agent_id_too_long(self):
        """Agent ID over 100 chars should fail."""
        with pytest.raises(CursorValidationError, match="maximum length"):
            validate_agent_id("a" * 101)

    def test_validate_agent_id_invalid_chars(self):
        """Agent ID with invalid chars should fail."""
        with pytest.raises(CursorValidationError, match="invalid characters"):
            validate_agent_id("agent@id")
        with pytest.raises(CursorValidationError, match="invalid characters"):
            validate_agent_id("agent id")

    def test_validate_prompt_text_valid(self):
        """Valid prompt text should pass."""
        validate_prompt_text("Hello, world!")
        validate_prompt_text("Implement feature X with multiple lines\nand more text")

    def test_validate_prompt_text_empty(self):
        """Empty prompt should fail."""
        with pytest.raises(CursorValidationError, match="required"):
            validate_prompt_text("")
        with pytest.raises(CursorValidationError, match="cannot be empty"):
            validate_prompt_text("   ")

    def test_validate_prompt_text_too_long(self):
        """Prompt over 100k chars should fail."""
        with pytest.raises(CursorValidationError, match="maximum length"):
            validate_prompt_text("a" * 100001)

    def test_validate_repository_valid(self):
        """Valid repository names should pass."""
        validate_repository("owner/repo")
        validate_repository("https://github.com/owner/repo")

    def test_validate_repository_invalid(self):
        """Invalid repository names should fail."""
        with pytest.raises(CursorValidationError, match="format"):
            validate_repository("invalid-no-slash")

    def test_validate_webhook_url_valid(self):
        """Valid HTTPS webhook URLs should pass."""
        validate_webhook_url("https://example.com/webhook")
        validate_webhook_url("https://api.myservice.io/hooks/123")

    def test_validate_webhook_url_http(self):
        """HTTP (non-HTTPS) URLs should fail."""
        with pytest.raises(CursorValidationError, match="HTTPS"):
            validate_webhook_url("http://example.com/webhook")

    def test_validate_webhook_url_internal(self):
        """Internal/private URLs should fail (SSRF protection)."""
        # IPv4 localhost and private ranges
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://localhost/webhook")
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://127.0.0.1/webhook")
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://192.168.1.1/webhook")
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://10.0.0.1/webhook")

    def test_validate_webhook_url_ipv6_internal(self):
        """IPv6 internal addresses should fail (SSRF protection)."""
        # IPv6 localhost
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://[::1]/webhook")
        # IPv6 unique local addresses (fc00::/7, fd00::/8)
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://[fc00::1]/webhook")
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://[fd12:3456::1]/webhook")
        # IPv6 link-local (fe80::/10)
        with pytest.raises(CursorValidationError, match="internal"):
            validate_webhook_url("https://[fe80::1]/webhook")

    def test_sanitize_error_uses_shared_secret_redaction(self):
        """Cursor error sanitization should cover common connector secret patterns."""
        redacted = sanitize_error("failed password=hunter2 token=tok_123 Authorization: Bearer raw_token")

        assert "hunter2" not in redacted
        assert "tok_123" not in redacted
        assert "raw_token" not in redacted
        assert "[REDACTED]" in redacted

    def test_sanitize_error_redacts_explicit_values(self):
        """Cursor sanitization should remove caller-provided identifiers, not just secret keys."""
        redacted = sanitize_error(
            "request to /agents/secret-agent failed for secret-org/private-repo",
            values=["secret-agent", "secret-org/private-repo"],
        )

        assert "secret-agent" not in redacted
        assert "secret-org/private-repo" not in redacted
        assert "[REDACTED]" in redacted

    def test_agent_model_payload_redacts_error(self):
        """Cursor agent payload serialization should redact agent error text."""
        agent = Agent(
            id="test-agent-123",
            state=AgentState.ERRORED,
            error="failed password=hunter2 Authorization: Bearer raw_token",
        )

        payload = CursorConnector._model_payload(agent)

        assert "hunter2" not in payload["error"]
        assert "raw_token" not in payload["error"]
        assert "[REDACTED]" in payload["error"]


class TestModels:
    """Tests for Pydantic models."""

    def test_agent_model(self):
        """Agent model should parse correctly."""
        agent = Agent(
            id="test-agent-123",
            state=AgentState.RUNNING,
            task="Implement feature X",
            repository="owner/repo",
        )
        assert agent.id == "test-agent-123"
        assert agent.state == AgentState.RUNNING
        assert agent.task == "Implement feature X"

    def test_agent_model_extra_fields(self):
        """Agent model should allow extra fields from API."""
        agent = Agent.model_validate(
            {
                "id": "test",
                "state": "running",
                "custom_field": "value",
            }
        )
        assert agent.id == "test"
        assert hasattr(agent, "custom_field")

    def test_repository_model(self):
        """Repository model should parse correctly."""
        repo = Repository(name="owner/repo", url="https://github.com/owner/repo")
        assert repo.name == "owner/repo"

    def test_conversation_model(self):
        """Conversation model should parse correctly."""
        conv = Conversation(
            agent_id="test",
            messages=[
                ConversationMessage(role="user", content="Hello"),
                ConversationMessage(role="assistant", content="Hi there!"),
            ],
        )
        assert conv.agent_id == "test"
        assert len(conv.messages) == 2


class TestTransport:
    """Tests for Cursor HTTP transport integration with Extended Data."""

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_request_api_decodes_response_through_extended_data_boundary(self, mock_client_class):
        """Private transport should decode JSON bytes into ExtendedDict payloads."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"service": {"name": "api"}}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.side_effect = AssertionError("raw response.json() should not be used")
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        payload = connector._request_api("/status")

        assert isinstance(payload, ExtendedDict)
        assert isinstance(payload["service"], ExtendedDict)
        assert isinstance(payload["service"]["name"], ExtendedString)
        assert payload["service"]["name"].upper_first() == "Api"


class TestCursorConnector:
    """Tests for CursorConnector."""

    def test_init_without_api_key(self):
        """Initialization without API key should fail."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(CursorError, match="CURSOR_API_KEY is required"):
                CursorConnector()

    def test_init_with_api_key(self):
        """Initialization with API key should succeed."""
        with patch("cloud_connectors.cursor.httpx.Client"):
            connector = CursorConnector(api_key="test-key")
            assert connector.api_key == "test-key"

    def test_is_available_true(self):
        """is_available should return True when env var is set."""
        with patch.dict(os.environ, {"CURSOR_API_KEY": "test"}):
            assert CursorConnector.is_available() is True

    def test_is_available_false(self):
        """is_available should return False when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert CursorConnector.is_available() is False

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_list_agents(self, mock_client_class):
        """list_agents should return parsed agents."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"agents": [{"id": "agent-1", "state": "running"}]}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {"agents": [{"id": "agent-1", "state": "running"}]}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        agents = connector.list_agents()

        assert isinstance(agents, ExtendedList)
        assert isinstance(agents[0], ExtendedDict)
        assert isinstance(agents[0]["id"], ExtendedString)
        assert len(agents) == 1
        assert agents[0]["id"] == "agent-1"
        assert agents[0]["state"] == "running"

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_get_agent_status_returns_extended_dict(self, mock_client_class):
        """get_agent_status should return an extended agent payload."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"id": "agent-1", "state": "finished", "pr_url": "https://github.com/org/repo/pull/1"}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {
            "id": "agent-1",
            "state": "finished",
            "pr_url": "https://github.com/org/repo/pull/1",
        }
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        agent = connector.get_agent_status("agent-1")

        assert isinstance(agent, ExtendedDict)
        assert isinstance(agent["state"], ExtendedString)
        assert agent["pr_url"] == "https://github.com/org/repo/pull/1"

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_get_agent_status_empty_response_redacts_agent_id(self, mock_client_class):
        """Empty status responses should not leak the raw agent ID in logs or errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = ""
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        connector.logger = MagicMock()

        with pytest.raises(CursorAPIError) as exc_info:
            connector.get_agent_status("secret-agent")

        assert exc_info.value.__cause__ is None
        assert "secret-agent" not in str(exc_info.value)
        assert "[REDACTED]" in str(exc_info.value)
        logs = _logged_text(connector.logger)
        assert "secret-agent" not in logs
        assert "[REDACTED]" in logs

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_get_agent_conversation_returns_extended_dict(self, mock_client_class):
        """get_agent_conversation should return an extended conversation payload."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"messages": [{"role": "user", "content": "hello"}]}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {"messages": [{"role": "user", "content": "hello"}]}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        conversation = connector.get_agent_conversation("agent-1")

        assert isinstance(conversation, ExtendedDict)
        assert isinstance(conversation["messages"], ExtendedList)
        assert isinstance(conversation["messages"][0], ExtendedDict)
        assert conversation["messages"][0]["content"] == "hello"

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_launch_agent(self, mock_client_class):
        """launch_agent should send correct request and return agent."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"id": "new-agent", "state": "pending"}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {"id": "new-agent", "state": "pending"}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        agent = connector.launch_agent(
            prompt_text="Implement feature X",
            repository="owner/repo",
            images=extend_data([{"data": "base64", "dimensions": {"width": 16, "height": 16}}]),
        )

        assert isinstance(agent, ExtendedDict)
        assert isinstance(agent["id"], ExtendedString)
        assert agent["id"] == "new-agent"
        assert agent["state"] == "pending"

        # Verify request was made correctly
        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert "/agents" in call_args.args[1]
        assert "prompt" in call_args.kwargs["json"]
        assert "source" in call_args.kwargs["json"]
        assert isinstance(call_args.kwargs["json"]["prompt"]["images"], list)
        assert isinstance(call_args.kwargs["json"]["prompt"]["images"][0], dict)

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_launch_agent_redacts_repository_diagnostics_but_preserves_payload(self, mock_client_class):
        """Agent launches should send raw repository data while redacting logs."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"id": "new-agent", "state": "pending"}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {"id": "new-agent", "state": "pending"}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        connector.logger = MagicMock()
        connector.launch_agent(prompt_text="Implement feature X", repository="secret-org/private-repo")

        call_args = mock_client.request.call_args
        assert call_args.kwargs["json"]["source"]["repository"] == "secret-org/private-repo"
        logs = _logged_text(connector.logger)
        assert "secret-org/private-repo" not in logs
        assert "[REDACTED]" in logs

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_launch_agent_validation(self, mock_client_class):
        """launch_agent should validate inputs."""
        mock_client_class.return_value = MagicMock()

        connector = CursorConnector(api_key="test-key")

        with pytest.raises(CursorValidationError, match="required"):
            connector.launch_agent(prompt_text="", repository="owner/repo")

        with pytest.raises(CursorValidationError, match="format"):
            connector.launch_agent(prompt_text="Hello", repository="invalid")

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_list_repositories_returns_extended_list(self, mock_client_class):
        """list_repositories should return extended repository payloads."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"repositories": [{"name": "org/repo", "default_branch": "main"}]}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {"repositories": [{"name": "org/repo", "default_branch": "main"}]}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        repositories = connector.list_repositories()

        assert isinstance(repositories, ExtendedList)
        assert isinstance(repositories[0], ExtendedDict)
        assert repositories[0]["name"] == "org/repo"

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_list_models_returns_extended_list(self, mock_client_class):
        """list_models should expose model names as an extended container."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"models": ["cursor-small", "cursor-large"]}'
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {"models": ["cursor-small", "cursor-large"]}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        models = connector.list_models()

        assert isinstance(models, ExtendedList)
        assert isinstance(models[0], ExtendedString)
        assert models[0].to_snake_case() == "cursor_small"

    @patch("cloud_connectors.cursor.httpx.Client")
    def test_list_models_empty_response_returns_extended_list(self, mock_client_class):
        """list_models should extend the empty response path too."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = "{}"
        mock_response.content = mock_response.text.encode()
        mock_response.json.return_value = {}
        mock_client.request.return_value = mock_response

        connector = CursorConnector(api_key="test-key")
        models = connector.list_models()

        assert isinstance(models, ExtendedList)
        assert models == []

    @pytest.mark.parametrize(
        ("method_name", "call", "payload", "raw_values"),
        [
            (
                "list_agents",
                lambda connector: connector.list_agents(),
                {"agents": [{"state": "running", "password": "hunter2", "authorization": "Bearer raw_token"}]},
                ["hunter2", "raw_token"],
            ),
            (
                "get_agent_status",
                lambda connector: connector.get_agent_status("secret-agent"),
                {"id": "secret-agent", "api_key": "key_123"},
                ["secret-agent", "key_123"],
            ),
            (
                "get_agent_conversation",
                lambda connector: connector.get_agent_conversation("secret-agent"),
                {"messages": [{"role": "user", "password": "hunter2", "authorization": "Bearer raw_token"}]},
                ["secret-agent", "hunter2", "raw_token"],
            ),
            (
                "launch_agent",
                lambda connector: connector.launch_agent(
                    prompt_text="rotate password=hunter2 for customer-prod",
                    repository="secret-org/private-repo",
                ),
                {"state": "pending", "task": "rotate password=hunter2 for secret-org/private-repo"},
                ["hunter2", "secret-org/private-repo", "customer-prod"],
            ),
            (
                "list_repositories",
                lambda connector: connector.list_repositories(),
                {"repositories": [{"url": "https://github.com/org/repo", "client_secret": "secret_123"}]},
                ["secret_123"],
            ),
            (
                "list_models",
                lambda connector: connector.list_models(),
                {"models": ["cursor-small", {"password": "hunter2"}]},
                ["hunter2"],
            ),
        ],
    )
    @patch("cloud_connectors.cursor.httpx.Client")
    def test_success_response_validation_errors_are_redacted(
        self,
        mock_client_class,
        method_name,
        call,
        payload,
        raw_values,
    ):
        """Malformed success payloads should fail loudly without raw Pydantic details."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.request.return_value = _json_response(payload)

        connector = CursorConnector(api_key="test-key")

        with pytest.raises(CursorAPIError) as exc_info:
            call(connector)

        message = str(exc_info.value)
        assert method_name in message
        assert "ValidationError" not in message
        assert "[REDACTED]" in message
        for raw_value in raw_values:
            assert raw_value not in message
