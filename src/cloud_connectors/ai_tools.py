"""AI tool definition helpers for Vercel AI SDK compatibility.

This module provides Pydantic-based helpers to define AI tool schemas
that are compatible with the Vercel AI SDK and other modern AI frameworks.
"""

from __future__ import annotations

import builtins

from collections.abc import Callable, Iterable, Mapping
from typing import Any, NoReturn, cast

from extended_data.containers import ExtendedDict, extend_data
from extended_data.primitives.redaction import redact_sensitive_text
from pydantic import BaseModel


def get_pydantic_schema(model: builtins.type[BaseModel]) -> ExtendedDict:
    """Generate a Vercel AI SDK-compatible JSON schema from a Pydantic model.

    This function removes the top-level 'title' and 'description' fields,
    which are often redundant and not used by AI frameworks. Parameter-level
    'description' fields are preserved as they are crucial for the AI to
    understand the tool's inputs.

    Args:
        model: The Pydantic model class.

    Returns:
        An extended JSON schema dictionary.
    """
    schema = model.model_json_schema()

    # Remove top-level title and description
    schema.pop("title", None)
    schema.pop("description", None)

    return cast(ExtendedDict, extend_data(schema))


def raise_unknown_tool_framework(framework: str) -> NoReturn:
    """Raise a redacted unknown-framework diagnostic for AI tool factories."""
    safe_framework = redact_sensitive_text(framework)
    msg = f"Unknown framework: {safe_framework}. Options: auto, langchain, crewai, strands"
    raise ValueError(msg)


def build_langchain_tools(tool_definitions: Iterable[Mapping[str, Any]]) -> list[Any]:
    """Build LangChain StructuredTools from connector tool definition mappings."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as e:
        msg = "langchain-core is required for LangChain tools.\nInstall with: pip install cloud-connectors[langchain]"
        raise ImportError(msg) from e

    tools: list[Any] = []
    for definition in tool_definitions:
        args_schema = definition.get("schema") or definition.get("args_schema")
        tools.append(
            StructuredTool.from_function(
                func=cast(Callable[..., Any], definition["func"]),
                name=cast(str, definition["name"]),
                description=cast(str, definition["description"]),
                args_schema=cast(Any, args_schema),
            )
        )
    return tools
