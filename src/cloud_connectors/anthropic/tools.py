"""AI framework tools for Anthropic Claude operations.

This module provides tools for Anthropic operations that work with multiple
AI agent frameworks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from pydantic import BaseModel, Field

from cloud_connectors.ai_tools import raise_unknown_tool_framework


def _message_text(message: Mapping[str, Any]) -> str:
    """Extract concatenated text blocks from a message payload."""
    return "".join(
        str(block.get("text", ""))
        for block in message.get("content", [])
        if block.get("type") == "text" and block.get("text")
    )


class CreateMessageSchema(BaseModel):
    """Pydantic schema for the anthropic_create_message tool."""

    model: str = Field(..., description="Model ID (e.g., 'claude-sonnet-4-5-20250929')")
    max_tokens: int = Field(1024, description="Maximum tokens to generate")
    prompt: str = Field(..., description="The user prompt text")
    system: str | None = Field(None, description="Optional system prompt")


class ListModelsSchema(BaseModel):
    """Pydantic schema for the anthropic_list_models tool."""


def anthropic_create_message(
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    system: str | None = None,
) -> ExtendedDict:
    """Create a message using Anthropic Claude.

    Args:
        model: Model ID.
        prompt: User prompt text.
        max_tokens: Max tokens to generate.
        system: Optional system prompt.

    Returns:
        Dict with message ID, text, and usage.
    """
    from cloud_connectors.anthropic import AnthropicConnector

    connector = AnthropicConnector()
    response = connector.create_message(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )

    return extend_data(
        {
            "id": response.get("id", ""),
            "text": _message_text(response),
            "model": response.get("model", ""),
            "usage": {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            },
        }
    )


def anthropic_list_models() -> ExtendedList[ExtendedDict]:
    """List available Anthropic Claude models.

    Returns:
        List of models with ID and display name.
    """
    from cloud_connectors.anthropic import AnthropicConnector

    connector = AnthropicConnector()
    models = connector.list_models()

    return extend_data([{"id": m.get("id", ""), "display_name": m.get("display_name", "")} for m in models])


TOOL_DEFINITIONS = [
    {
        "name": "anthropic_create_message",
        "description": "Create a message using Anthropic Claude AI. Provide a model ID and prompt.",
        "func": anthropic_create_message,
        "schema": CreateMessageSchema,
    },
    {
        "name": "anthropic_list_models",
        "description": "List available Anthropic Claude models.",
        "func": anthropic_list_models,
        "schema": ListModelsSchema,
    },
]


def get_langchain_tools() -> list[Any]:
    """Get all Anthropic tools as LangChain StructuredTools."""
    from cloud_connectors.ai_tools import build_langchain_tools

    return build_langchain_tools(TOOL_DEFINITIONS)


def get_crewai_tools() -> list[Any]:
    """Get all Anthropic tools as CrewAI tools."""
    from cloud_connectors._optional import get_crewai_tool_decorator

    crewai_tool = get_crewai_tool_decorator()

    tools = []
    for defn in TOOL_DEFINITIONS:
        wrapped = crewai_tool(defn["name"])(defn["func"])
        wrapped.description = defn["description"]
        schema = defn.get("schema") or defn.get("args_schema")
        if schema:
            wrapped.args_schema = schema
        tools.append(wrapped)

    return tools


def get_strands_tools() -> list[Any]:
    """Get all Anthropic tools as plain Python functions for AWS Strands."""
    return [defn["func"] for defn in TOOL_DEFINITIONS]


def get_tools(framework: str = "auto") -> list[Any]:
    """Get Anthropic tools for the specified or auto-detected framework."""
    from cloud_connectors._optional import is_available

    if framework == "auto":
        if is_available("crewai"):
            return get_crewai_tools()
        if is_available("langchain_core"):
            return get_langchain_tools()
        return get_strands_tools()

    if framework == "langchain":
        return get_langchain_tools()
    if framework == "crewai":
        return get_crewai_tools()
    if framework == "strands":
        return get_strands_tools()

    return raise_unknown_tool_framework(framework)


__all__ = [
    "TOOL_DEFINITIONS",
    "anthropic_create_message",
    "anthropic_list_models",
    "get_crewai_tools",
    "get_langchain_tools",
    "get_strands_tools",
    "get_tools",
]
