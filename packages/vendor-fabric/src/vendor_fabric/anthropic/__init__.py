"""Anthropic connector for Claude APIs.

This connector provides Python access to Anthropic's Claude API.

Usage:
    from vendor_fabric.anthropic import AnthropicConnector

    # Standard API access
    connector = AnthropicConnector(api_key="...")
    response = connector.create_message(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}]
    )

Reference: https://docs.anthropic.com/claude/reference
"""

from __future__ import annotations

import os

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import httpx

from extended_data.containers import ExtendedDict, ExtendedList, extend_data, to_builtin
from extended_data.logging import Logging
from extended_data.primitives.redaction import redact_sensitive_text
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vendor_fabric.base import ConnectorBase


if TYPE_CHECKING:
    pass

__all__ = [
    "AnthropicConnector",
    "AnthropicError",
    "ContentBlock",
    "Message",
    "MessageRole",
    "Model",
    "Usage",
]


# =============================================================================
# Constants
# =============================================================================

DEFAULT_API_URL = "https://api.anthropic.com"
DEFAULT_API_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_TOKENS = 4096

# Available Claude models
# SOURCE OF TRUTH: https://docs.anthropic.com/en/docs/about-claude/models
# API verification: curl https://api.anthropic.com/v1/models -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01"
# Last verified: 2025-12-07
CLAUDE_MODELS = {
    # Claude 4.5 family (latest)
    "claude-opus-4-5-20251101": "Claude Opus 4.5",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    # Claude 4.1 family
    "claude-opus-4-1-20250805": "Claude Opus 4.1",
    # Claude 4 family
    "claude-sonnet-4-20250514": "Claude Sonnet 4",
    "claude-opus-4-20250514": "Claude Opus 4",
    # Claude 3.7 family
    "claude-3-7-sonnet-20250219": "Claude Sonnet 3.7",
    # Claude 3.5 family
    "claude-3-5-haiku-20241022": "Claude Haiku 3.5",
    # Claude 3 family
    "claude-3-opus-20240229": "Claude Opus 3",
    "claude-3-haiku-20240307": "Claude Haiku 3",
}


# =============================================================================
# Exceptions
# =============================================================================


class AnthropicError(Exception):
    """Base exception for Anthropic API errors."""

    def __init__(self, message: str, status_code: int | None = None, error_type: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type


class AnthropicAuthError(AnthropicError):
    """Authentication error."""


class AnthropicRateLimitError(AnthropicError):
    """Rate limit exceeded error."""


class AnthropicAPIError(AnthropicError):
    """API error from Anthropic service."""


# =============================================================================
# Models
# =============================================================================


class MessageRole(StrEnum):
    """Message role in conversation."""

    USER = "user"
    ASSISTANT = "assistant"


class ContentBlock(BaseModel):
    """Content block within a message."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(description="Content type (text, image, tool_use, tool_result)")
    text: str | None = Field(default=None, description="Text content")
    id: str | None = Field(default=None, description="Tool use ID")
    name: str | None = Field(default=None, description="Tool name")
    input: dict[str, Any] | None = Field(default=None, description="Tool input")


class Usage(BaseModel):
    """Token usage information."""

    model_config = ConfigDict(extra="allow")

    input_tokens: int = Field(description="Number of input tokens")
    output_tokens: int = Field(description="Number of output tokens")


class Message(BaseModel):
    """Claude message response."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Message ID")
    type: str = Field(default="message", description="Response type")
    role: MessageRole = Field(description="Message role")
    content: list[ContentBlock] = Field(description="Message content blocks")
    model: str = Field(description="Model used")
    stop_reason: str | None = Field(default=None, description="Stop reason")
    stop_sequence: str | None = Field(default=None, description="Stop sequence if triggered")
    usage: Usage = Field(description="Token usage")

    @property
    def text(self) -> str:
        """Get the text content of the message."""
        text_blocks = [b.text for b in self.content if b.type == "text" and b.text]
        return "".join(text_blocks)


class Model(BaseModel):
    """Claude model information."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Model ID")
    display_name: str = Field(description="Human-readable model name")
    created_at: datetime | None = Field(default=None, description="Creation timestamp")


# =============================================================================
# Connector
# =============================================================================


class AnthropicConnector(ConnectorBase):
    """Anthropic Claude API connector.

    Provides HTTP client access to Anthropic's Claude API for message
    generation and model metadata.

    Args:
        api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
        api_version: API version string. Default "2023-06-01".
        timeout: Request timeout in seconds. Default 60s.
        logger: Optional logger instance.
        **kwargs: Additional InputProvider arguments.

    Example:
        >>> connector = AnthropicConnector()
        >>> response = connector.create_message(
        ...     model="claude-sonnet-4-20250514",
        ...     max_tokens=1024,
        ...     messages=[{"role": "user", "content": "Hello"}]
        ... )
        >>> print(response["content"][0]["text"])
    """

    API_KEY_ENV = "ANTHROPIC_API_KEY"
    BASE_URL = DEFAULT_API_URL

    def __init__(
        self,
        api_key: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, logger=logger, timeout=timeout, **kwargs)

        # Validate API key
        if not self._api_key:
            msg = "ANTHROPIC_API_KEY is required. Set it in environment or pass to constructor."
            raise AnthropicError(msg)

        self.api_version = api_version

        self.logger.info(f"Initialized AnthropicConnector with API version: {self.api_version}")

    def _build_headers(self) -> dict[str, str]:
        """Build Anthropic-specific headers."""
        headers = super()._build_headers()
        headers["anthropic-version"] = self.api_version
        if self._api_key:
            headers["x-api-key"] = self._api_key
            # Anthropic uses x-api-key, so remove standard Authorization header if present
            headers.pop("Authorization", None)
        return headers

    @staticmethod
    def is_available() -> bool:
        """Check if API key is available.

        Returns:
            True if ANTHROPIC_API_KEY is set in environment.
        """
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @staticmethod
    def get_available_models() -> ExtendedDict:
        """Get dictionary of available Claude models.

        Returns:
            Extended dictionary mapping model IDs to display names.
        """
        return extend_data(CLAUDE_MODELS.copy())

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle API error responses.

        Args:
            response: httpx Response object.

        Raises:
            AnthropicError: Appropriate error type for the response.
        """
        status_code = response.status_code
        try:
            error_data = self.decode_response(response, suffix="json", as_extended=True)
            raw_error = error_data.get("error", {}) if isinstance(error_data, Mapping) else {}
            error = raw_error if isinstance(raw_error, Mapping) else {}
            error_type = error.get("type", "unknown")
            message = error.get("message", response.text)
        except Exception:
            error_type = "unknown"
            message = response.text
        message = redact_sensitive_text(message)

        if status_code == 401:
            raise AnthropicAuthError(message, status_code=status_code, error_type=error_type)
        if status_code == 429:
            raise AnthropicRateLimitError(message, status_code=status_code, error_type=error_type)
        raise AnthropicAPIError(message, status_code=status_code, error_type=error_type)

    @staticmethod
    def _model_payload(model: BaseModel) -> dict[str, Any]:
        """Serialize an Anthropic model into JSON-compatible API field names."""
        return model.model_dump(mode="json")

    @staticmethod
    def _unexpected_response_error(operation: str, data: Any, *, status_code: int | None = None) -> AnthropicAPIError:
        """Build a redacted malformed-response error."""
        return AnthropicAPIError(
            f"Unexpected Anthropic response for {operation}: {redact_sensitive_text(data)}",
            status_code=status_code,
            error_type="unexpected_response",
        )

    def _response_json(self, response: httpx.Response, operation: str) -> Any:
        """Parse a response body or raise a redacted malformed-response error."""
        try:
            return self.decode_response(response, suffix="json", as_extended=True)
        except Exception:
            raise self._unexpected_response_error(
                operation,
                response.text,
                status_code=response.status_code,
            ) from None

    def _parse_model_response(
        self,
        response: httpx.Response,
        model_type: type[BaseModel],
        operation: str,
    ) -> dict[str, Any]:
        """Validate one Anthropic model response and return a JSON payload."""
        data = self._response_json(response, operation)
        try:
            return self._model_payload(model_type.model_validate(to_builtin(data)))
        except ValidationError:
            raise self._unexpected_response_error(
                operation,
                data,
                status_code=response.status_code,
            ) from None

    @staticmethod
    def _message_text(message: Mapping[str, Any]) -> str:
        """Extract concatenated text blocks from an extended message payload."""
        return "".join(
            str(block.get("text", ""))
            for block in message.get("content", [])
            if block.get("type") == "text" and block.get("text")
        )

    # =========================================================================
    # Message Operations
    # =========================================================================

    def create_message(
        self,
        model: str,
        max_tokens: int,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        stop_sequences: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtendedDict:
        """Create a message using Claude.

        Args:
            model: Model ID (e.g., "claude-sonnet-4-20250514").
            max_tokens: Maximum tokens to generate.
            messages: List of message dicts with role and content.
            system: Optional system prompt.
            temperature: Sampling temperature (0-1).
            top_p: Top-p sampling parameter.
            top_k: Top-k sampling parameter.
            stop_sequences: Stop sequences to end generation.
            tools: Tool definitions for function calling.
            tool_choice: Tool choice configuration.
            metadata: Optional metadata for the request.

        Returns:
            Message response payload.

        Raises:
            AnthropicError: If the API request fails.
        """
        self.logger.info(f"Creating message with model: {model}")

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p
        if top_k is not None:
            body["top_k"] = top_k
        if stop_sequences:
            body["stop_sequences"] = stop_sequences
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice
        if metadata:
            body["metadata"] = metadata

        response = self.post("/v1/messages", json=to_builtin(body))

        if not response.is_success:
            self._handle_error(response)

        return self.extend_result(self._parse_model_response(response, Message, "create_message"))

    def count_tokens(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> int:
        """Count tokens for a set of messages.

        Args:
            model: Model ID.
            messages: List of message dicts.
            system: Optional system prompt.
            tools: Optional tool definitions.

        Returns:
            Token count.

        Raises:
            AnthropicError: If the API request fails.
        """
        self.logger.info(f"Counting tokens for model: {model}")

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        response = self.post("/v1/messages/count_tokens", json=to_builtin(body))

        if not response.is_success:
            self._handle_error(response)

        data = self._response_json(response, "count_tokens")
        if not isinstance(data, Mapping) or not isinstance(data.get("input_tokens"), int):
            raise self._unexpected_response_error(
                "count_tokens",
                data,
                status_code=response.status_code,
            )
        return data["input_tokens"]

    # =========================================================================
    # Model Operations
    # =========================================================================

    def list_models(self) -> ExtendedList[ExtendedDict]:
        """List available models from the API.

        Returns:
            List of model payload dictionaries.

        Raises:
            AnthropicError: If the API request fails.
        """
        self.logger.info("Listing models from API")

        response = self.get("/v1/models")

        if not response.is_success:
            self._handle_error(response)

        data = self._response_json(response, "list_models")
        models_data = data.get("data") if isinstance(data, Mapping) else None
        if not isinstance(models_data, (list, ExtendedList)):
            raise self._unexpected_response_error(
                "list_models",
                data,
                status_code=response.status_code,
            )

        try:
            parsed_models = [
                self._model_payload(Model.model_validate(to_builtin(model_data))) for model_data in models_data
            ]
        except ValidationError:
            raise self._unexpected_response_error(
                "list_models",
                data,
                status_code=response.status_code,
            ) from None
        return self.extend_result(parsed_models)

    def get_model(self, model_id: str) -> ExtendedDict:
        """Get information about a specific model.

        Args:
            model_id: Model identifier.

        Returns:
            Model payload dictionary with details.

        Raises:
            AnthropicError: If the API request fails.
        """
        self.logger.info(f"Getting model info: {model_id}")

        response = self.get(f"/v1/models/{model_id}")

        if not response.is_success:
            self._handle_error(response)

        return self.extend_result(self._parse_model_response(response, Model, "get_model"))

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def validate_model(self, model_id: str) -> bool:
        """Check if a model ID is valid.

        Args:
            model_id: Model identifier to validate.

        Returns:
            True if model exists in known models.
        """
        return model_id in CLAUDE_MODELS

    def get_recommended_model(self, use_case: str = "general") -> str:
        """Get recommended model for a use case.

        Args:
            use_case: Use case type ("general", "coding", "fast", "powerful").

        Returns:
            Recommended model ID.
        """
        # Using verified model IDs from Anthropic API
        recommendations = {
            "general": "claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5 - best balance
            "coding": "claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5 - great for code
            "fast": "claude-haiku-4-5-20251001",  # Claude Haiku 4.5 - fastest
            "powerful": "claude-opus-4-5-20251101",  # Claude Opus 4.5 - most capable
        }
        return self.extend_result(recommendations.get(use_case, recommendations["general"]))
