"""Unified MCP Server for Vendor Fabric.

This module provides a single MCP (Model Context Protocol) server that
exposes registered connector data methods as tools via the registry.

Usage:
    # Command line
    vendor-fabric-mcp

    # Or programmatically
    from vendor_fabric.mcp import create_server, main
    server = create_server()

The server automatically discovers all registered connectors and exposes
methods that advertise Extended Data payload returns as MCP tools.

This provides a standard MCP bridge between Python connectors and any MCP-aware
client without leaking raw SDK client factories or low-level HTTP helpers.
"""

from __future__ import annotations

import builtins
import inspect
import sys

from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast, get_origin, get_type_hints

from extended_data.containers import to_builtin
from extended_data.io import wrap_raw_data_for_export
from extended_data.primitives.redaction import redact_sensitive_data, redact_sensitive_text

from vendor_fabric.registry import (
    _list_connector_classes,
    get_connector,
    get_connector_info,
    list_available_connectors,
    list_connector_capabilities,
    list_connector_categories,
    list_connector_info,
    list_connectors,
    list_connectors_by_capability,
    list_connectors_by_category,
)
from vendor_fabric.surface import connector_data_methods


def _check_mcp_installed() -> bool:
    """Check if MCP SDK is installed."""
    try:
        from mcp.server import Server  # noqa: F401

        return True
    except ImportError:
        return False


def _get_method_schema(method: Callable[..., Any]) -> dict[str, Any]:
    """Generate JSON schema from method signature."""
    sig = inspect.signature(method)
    try:
        type_hints = get_type_hints(method)
    except Exception:
        type_hints = {}
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        prop: dict[str, Any] = {"type": "string"}  # Default

        # Try to get type from annotations
        ann = type_hints.get(name, param.annotation)
        if ann != inspect.Parameter.empty:
            if ann is int:
                prop = {"type": "integer"}
            elif ann is float:
                prop = {"type": "number"}
            elif ann is bool:
                prop = {"type": "boolean"}
            elif ann is list or get_origin(ann) is list:
                prop = {"type": "array"}
            elif ann is dict or get_origin(ann) is dict:
                prop = {"type": "object"}

        # Get description from docstring if available
        if method.__doc__:
            # Simple extraction - look for "name:" in docstring
            for line in method.__doc__.split("\n"):
                if f"{name}:" in line.lower():
                    prop["description"] = line.split(":", 1)[-1].strip()
                    break

        # Handle defaults
        if param.default != inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)

        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _get_public_methods(connector_class: builtins.type[Any]) -> list[tuple[str, Callable[..., Any]]]:
    """Get public data methods from a connector class for MCP exposure."""
    return connector_data_methods(connector_class)


def _catalog_tool_definitions() -> dict[str, dict[str, Any]]:
    """Build credential-free connector catalog MCP tools."""
    include_unavailable_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"include_unavailable": {"type": "boolean", "default": True}},
        "required": [],
    }
    empty_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    name_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "include_unavailable": {"type": "boolean", "default": True},
        },
        "required": ["name"],
    }
    category_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "include_unavailable": {"type": "boolean", "default": True},
        },
        "required": ["category"],
    }
    capability_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "capability": {"type": "string"},
            "include_unavailable": {"type": "boolean", "default": True},
        },
        "required": ["capability"],
    }

    return {
        "vendor_fabric_list_connectors": {
            "description": "List Vendor Fabric catalog names.",
            "parameters": include_unavailable_schema,
            "handler": list_connectors,
        },
        "vendor_fabric_list_available_connectors": {
            "description": "List Vendor Fabric available in the current environment.",
            "parameters": empty_schema,
            "handler": list_available_connectors,
        },
        "vendor_fabric_list_connector_info": {
            "description": "List Vendor Fabric catalog metadata.",
            "parameters": include_unavailable_schema,
            "handler": list_connector_info,
        },
        "vendor_fabric_get_connector_info": {
            "description": "Get Vendor Fabric catalog metadata for one connector.",
            "parameters": name_schema,
            "handler": get_connector_info,
        },
        "vendor_fabric_list_connector_categories": {
            "description": "List Vendor Fabric catalog categories.",
            "parameters": include_unavailable_schema,
            "handler": list_connector_categories,
        },
        "vendor_fabric_list_connector_capabilities": {
            "description": "List Vendor Fabric catalog capabilities.",
            "parameters": include_unavailable_schema,
            "handler": list_connector_capabilities,
        },
        "vendor_fabric_list_connectors_by_category": {
            "description": "List Vendor Fabric catalog entries for a category.",
            "parameters": category_schema,
            "handler": list_connectors_by_category,
        },
        "vendor_fabric_list_connectors_by_capability": {
            "description": "List Vendor Fabric catalog entries for a capability.",
            "parameters": capability_schema,
            "handler": list_connectors_by_capability,
        },
    }


def _jsonable_tool_result(result: Any) -> Any:
    """Lower connector tool results to JSON-compatible Python data."""
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif isinstance(result, Iterable) and not isinstance(result, (str, bytes, bytearray, Mapping)):
        result = [item.model_dump() if hasattr(item, "model_dump") else item for item in result]
    result = to_builtin(result)
    if isinstance(result, set | frozenset):
        result = [to_builtin(item) for item in result]
    return redact_sensitive_data(result)


def _tool_error_text(error: Exception, values: Iterable[Any] | None = None) -> str:
    """Return an MCP-safe error string without raw secret values."""
    return f"Error: {type(error).__name__}: {redact_sensitive_text(error, values=values)}"


def _unknown_tool_text(name: str) -> str:
    """Return an MCP-safe unknown-tool diagnostic."""
    return f"Unknown tool: {redact_sensitive_text(name)}"


def _tool_result_text(result: Any) -> str:
    """Return a serialized MCP tool result through the shared export boundary."""
    return wrap_raw_data_for_export(_jsonable_tool_result(result), allow_encoding="json", indent_2=True, default=str)


def create_server() -> Any:
    """Create the unified MCP server with all registered connectors."""
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError as e:
        msg = "MCP SDK not installed. Install with: pip install vendor-fabric[mcp]"
        raise ImportError(msg) from e

    server = Server("vendor-fabric")

    # Build tool registry from all connectors
    tools: dict[str, dict[str, Any]] = {}
    tools.update(_catalog_tool_definitions())

    # Discover all connectors
    connectors = _list_connector_classes()

    for connector_name, connector_class in connectors.items():
        # Get public methods
        for method_name, method in _get_public_methods(connector_class):
            # Skip common base class methods
            if method_name in ("close", "request", "get_input", "register_tool"):
                continue

            tool_name = f"{connector_name}_{method_name}"

            # Get method from class (unbound)
            try:
                schema = _get_method_schema(method)
            except Exception:
                schema = {"type": "object", "properties": {}}

            # Get description from docstring
            description = ""
            if method.__doc__:
                description = method.__doc__.split("\n")[0].strip()
            if not description:
                description = f"{connector_name}.{method_name}()"

            tools[tool_name] = {
                "connector": connector_name,
                "method": method_name,
                "description": description,
                "parameters": schema,
            }

    tool_decorator = cast(Callable[[], Callable[[Callable[..., Any]], Callable[..., Any]]], server.list_tools)
    call_decorator = cast(Callable[[], Callable[[Callable[..., Any]], Callable[..., Any]]], server.call_tool)

    @tool_decorator()
    async def list_tools() -> list[Tool]:
        """Return all available tools."""
        return [
            Tool(name=name, description=tool["description"], inputSchema=tool["parameters"])
            for name, tool in tools.items()
        ]

    @call_decorator()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute a tool and return results."""
        if name not in tools:
            return [TextContent(type="text", text=_unknown_tool_text(name))]

        tool = tools[name]
        handler = tool.get("handler")
        if callable(handler):
            try:
                result = handler(**arguments)
                if inspect.iscoroutine(result):
                    result = await result
                return [TextContent(type="text", text=_tool_result_text(result))]
            except Exception as e:
                return [TextContent(type="text", text=_tool_error_text(e, arguments.values()))]

        connector_name = tool["connector"]
        method_name = tool["method"]

        try:
            # Instantiate connector (will get credentials from env)
            connector = get_connector(connector_name)

            # Get and call the method
            method = getattr(connector, method_name)
            result = method(**arguments)

            # Handle async methods
            if inspect.iscoroutine(result):
                result = await result

            return [TextContent(type="text", text=_tool_result_text(result))]

        except Exception as e:
            return [TextContent(type="text", text=_tool_error_text(e, arguments.values()))]

    return server


def main() -> int:
    """Run the MCP server over stdio."""
    import asyncio

    try:
        from mcp.server.stdio import stdio_server
    except ImportError:
        return 1

    server = create_server()

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
