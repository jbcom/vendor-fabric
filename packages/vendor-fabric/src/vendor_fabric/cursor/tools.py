"""AI framework tools for Cursor Background Agent operations.

This module provides tools for Cursor operations that work with multiple
AI agent frameworks.
"""

from __future__ import annotations

from typing import Any

from extended_data.containers import ExtendedDict, extend_data
from pydantic import BaseModel, Field

from vendor_fabric.ai_tools import raise_unknown_tool_framework


def _error_value(error: Any) -> Any:
    """Return a sanitized error value while preserving empty values."""
    if not error:
        return error

    from vendor_fabric.cursor import sanitize_error

    return sanitize_error(error)


def _state_value(state: Any) -> Any:
    """Return enum values for tool payloads while preserving plain strings."""
    return getattr(state, "value", state)


class LaunchAgentSchema(BaseModel):
    """Pydantic schema for the cursor_launch_agent tool."""

    prompt: str = Field(..., description="Task description for the agent")
    repository: str = Field(..., description="Repository full name (owner/repo)")
    ref: str | None = Field(None, description="Git ref (branch/tag/commit)")
    branch_name: str | None = Field(None, description="Custom branch name for PR")


class GetAgentStatusSchema(BaseModel):
    """Pydantic schema for the cursor_get_agent_status tool."""

    agent_id: str = Field(..., description="The unique agent identifier")


def cursor_launch_agent(
    prompt: str,
    repository: str,
    ref: str | None = None,
    branch_name: str | None = None,
) -> ExtendedDict:
    """Launch a new Cursor coding agent.

    Args:
        prompt: Task description.
        repository: Repository (owner/repo).
        ref: Optional git ref.
        branch_name: Optional branch name.

    Returns:
        Dict with agent ID and state.
    """
    from vendor_fabric.cursor import CursorConnector

    connector = CursorConnector()
    agent = connector.launch_agent(
        prompt_text=prompt,
        repository=repository,
        ref=ref,
        branch_name=branch_name,
    )

    return extend_data(
        {
            "agent_id": agent.get("id", ""),
            "state": _state_value(agent.get("state")),
            "repository": agent.get("repository"),
        }
    )


def cursor_get_agent_status(agent_id: str) -> ExtendedDict:
    """Get the current status of a Cursor agent.

    Args:
        agent_id: Agent identifier.

    Returns:
        Dict with agent state and details.
    """
    from vendor_fabric.cursor import CursorConnector

    connector = CursorConnector()
    agent = connector.get_agent_status(agent_id)

    return extend_data(
        {
            "agent_id": agent.get("id", ""),
            "state": _state_value(agent.get("state")),
            "error": _error_value(agent.get("error")),
            "pr_url": agent.get("pr_url"),
        }
    )


TOOL_DEFINITIONS = [
    {
        "name": "cursor_launch_agent",
        "description": "Launch a new Cursor Background Agent to perform a coding task.",
        "func": cursor_launch_agent,
        "schema": LaunchAgentSchema,
    },
    {
        "name": "cursor_get_agent_status",
        "description": "Check the status of a Cursor coding agent by its ID.",
        "func": cursor_get_agent_status,
        "schema": GetAgentStatusSchema,
    },
]


def get_langchain_tools() -> list[Any]:
    """Get all Cursor tools as LangChain StructuredTools."""
    from vendor_fabric.ai_tools import build_langchain_tools

    return build_langchain_tools(TOOL_DEFINITIONS)


def get_crewai_tools() -> list[Any]:
    """Get all Cursor tools as CrewAI tools."""
    from vendor_fabric._optional import get_crewai_tool_decorator

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
    """Get all Cursor tools as plain Python functions for AWS Strands."""
    return [defn["func"] for defn in TOOL_DEFINITIONS]


def get_tools(framework: str = "auto") -> list[Any]:
    """Get Cursor tools for the specified or auto-detected framework."""
    from vendor_fabric._optional import is_available

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
    "cursor_get_agent_status",
    "cursor_launch_agent",
    "get_crewai_tools",
    "get_langchain_tools",
    "get_strands_tools",
    "get_tools",
]
