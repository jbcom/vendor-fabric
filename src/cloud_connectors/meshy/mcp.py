"""MCP (Model Context Protocol) server for Meshy AI tools.

This module provides an MCP server that exposes Meshy AI 3D generation tools
to any MCP-compatible client (Claude Desktop, Cline, etc.).

Usage:
    # Command line
    python -m cloud_connectors.meshy.mcp

    # Programmatic
    from cloud_connectors.meshy.mcp import create_server, run_server

    server = create_server()
    run_server(server)

Configure in Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "meshy": {
          "command": "python",
          "args": ["-m", "cloud_connectors.meshy.mcp"],
          "env": {
            "MESHY_API_KEY": "your-api-key-here"
          }
        }
      }
    }
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from extended_data.containers import to_builtin
from extended_data.io import wrap_raw_data_for_export
from extended_data.primitives.redaction import redact_sensitive_data, redact_sensitive_text


MCP_INSTALL_MESSAGE = "MCP SDK not installed. Install with: pip install cloud-connectors[meshy,mcp]"


def _create_mcp_tools() -> list[tuple[Any, Callable[..., Any]]]:
    """Create MCP tool definitions from Meshy functions.

    Returns:
        List of MCP Tool objects
    """
    try:
        from mcp.types import Tool
    except ImportError as e:
        raise ImportError(MCP_INSTALL_MESSAGE) from e

    # Import Meshy tool functions
    from cloud_connectors.meshy import tools

    # Define tool schemas manually for better control
    tool_schemas: list[dict[str, Any]] = [
        {
            "name": "text3d_generate",
            "description": (
                "Generate a 3D GLB model from a text description using Meshy AI. "
                "Provide a detailed prompt describing the model. Returns the task_id, "
                "status, model_url, and thumbnail_url on success."
            ),
            "func": tools.text3d_generate,
            "parameters": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed text description of the 3D model",
                    "required": True,
                },
                "art_style": {
                    "type": "string",
                    "description": "Art style: realistic or sculpture (for sculpture, PBR is not recommended)",
                    "enum": ["realistic", "sculpture"],
                    "default": "realistic",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "Things to avoid in the generation",
                    "default": "",
                },
                "target_polycount": {
                    "type": "integer",
                    "description": "Target polygon count for the model",
                    "default": 30000,
                },
                "enable_pbr": {
                    "type": "boolean",
                    "description": "Enable PBR (physically-based rendering) materials",
                    "default": True,
                },
            },
        },
        {
            "name": "image3d_generate",
            "description": (
                "Generate a 3D GLB model from an image using Meshy AI. "
                "Provide a URL to the source image. Returns the task_id, "
                "status, model_url, and thumbnail_url on success."
            ),
            "func": tools.image3d_generate,
            "parameters": {
                "image_url": {"type": "string", "description": "URL to the source image", "required": True},
                "topology": {
                    "type": "string",
                    "description": "Mesh topology type",
                    "enum": ["", "quad", "triangle"],
                    "default": "",
                },
                "target_polycount": {
                    "type": "integer",
                    "description": "Target polygon count for the model",
                    "default": 15000,
                },
                "enable_pbr": {
                    "type": "boolean",
                    "description": "Enable PBR (physically-based rendering) materials",
                    "default": True,
                },
            },
        },
        {
            "name": "rig_model",
            "description": (
                "Add a skeleton/rig to a static 3D model. This is required before "
                "you can apply animations. Takes the model's task ID and returns "
                "a new task ID for the rigging operation."
            ),
            "func": tools.rig_model,
            "parameters": {
                "model_id": {"type": "string", "description": "Task ID of the static model to rig", "required": True},
                "wait": {"type": "boolean", "description": "Wait for rigging to complete", "default": True},
            },
        },
        {
            "name": "apply_animation",
            "description": (
                "Apply an animation to a rigged 3D model. Use list_animations to "
                "see available animation IDs. The model must be rigged first."
            ),
            "func": tools.apply_animation,
            "parameters": {
                "model_id": {"type": "string", "description": "Task ID of the rigged model", "required": True},
                "animation_id": {
                    "type": "integer",
                    "description": "Animation ID from the Meshy catalog (use list_animations)",
                    "required": True,
                },
                "wait": {"type": "boolean", "description": "Wait for animation to complete", "default": True},
            },
        },
        {
            "name": "retexture_model",
            "description": (
                "Apply new textures to an existing 3D model. Great for creating "
                "color variants or material changes without regenerating the mesh."
            ),
            "func": tools.retexture_model,
            "parameters": {
                "model_id": {"type": "string", "description": "Task ID of the model to retexture", "required": True},
                "texture_prompt": {
                    "type": "string",
                    "description": "Description of the new texture/appearance",
                    "required": True,
                },
                "enable_pbr": {
                    "type": "boolean",
                    "description": "Enable PBR (physically-based rendering) materials",
                    "default": True,
                },
                "wait": {"type": "boolean", "description": "Wait for retexturing to complete", "default": True},
            },
        },
        {
            "name": "list_animations",
            "description": (
                "List available animations from the Meshy animation catalog. "
                "Optionally filter by category. Returns animation IDs and names "
                "that can be used with apply_animation."
            ),
            "func": tools.list_animations,
            "parameters": {
                "category": {
                    "type": "string",
                    "description": "Optional category filter (Fighting, WalkAndRun, Dancing, etc.)",
                    "default": "",
                },
                "limit": {"type": "integer", "description": "Maximum number of animations to return", "default": 50},
            },
        },
        {
            "name": "check_task_status",
            "description": (
                "Check the current status of a Meshy AI task. Returns status "
                "(pending, processing, succeeded, failed), progress percentage, "
                "and model URL if complete."
            ),
            "func": tools.check_task_status,
            "parameters": {
                "task_id": {"type": "string", "description": "The Meshy task ID to check", "required": True},
                "task_type": {
                    "type": "string",
                    "description": "Task type",
                    "enum": ["text-to-3d", "image-to-3d", "rigging", "animation", "retexture"],
                    "default": "text-to-3d",
                },
            },
        },
        {
            "name": "get_animation",
            "description": "Get details of a specific animation by ID, including name, category, subcategory, and preview URL.",
            "func": tools.get_animation,
            "parameters": {
                "animation_id": {"type": "integer", "description": "The animation ID number", "required": True},
            },
        },
    ]

    # Convert to MCP Tool objects
    mcp_tools = []
    for schema in tool_schemas:
        # Build JSON schema properties and required list
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param_def in schema["parameters"].items():
            prop = {
                "type": param_def["type"],
                "description": param_def["description"],
            }

            if "default" in param_def:
                prop["default"] = param_def["default"]

            if "enum" in param_def:
                prop["enum"] = param_def["enum"]

            properties[param_name] = prop

            if param_def.get("required", False):
                required.append(param_name)

        tool = Tool(
            name=schema["name"],
            description=schema["description"],
            inputSchema={
                "type": "object",
                "properties": properties,
                "required": required,
            },
        )
        mcp_tools.append((tool, schema["func"]))

    return mcp_tools


def _jsonable_tool_result(result: Any) -> Any:
    """Lower Meshy tool results to JSON-compatible redacted data."""
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif isinstance(result, Iterable) and not isinstance(result, (str, bytes, bytearray, Mapping)):
        result = [item.model_dump() if hasattr(item, "model_dump") else item for item in result]
    result = to_builtin(result)
    if isinstance(result, set | frozenset):
        result = [to_builtin(item) for item in result]
    return redact_sensitive_data(result)


def _tool_error_payload(error: object, *, values: Iterable[Any] | None = None) -> dict[str, str]:
    """Return an MCP-safe error payload without raw secret values."""
    return {"error": redact_sensitive_text(error, values=values)}


def _tool_payload_text(payload: Any) -> str:
    """Return a serialized MCP text payload through the shared export boundary."""
    return wrap_raw_data_for_export(payload, allow_encoding="json", indent_2=True)


def _tool_result_text(result: Any) -> str:
    """Return a serialized Meshy MCP result through the shared export boundary."""
    return _tool_payload_text(_jsonable_tool_result(result))


def create_server() -> Any:
    """Create an MCP server with Meshy AI tools.

    Returns:
        Configured MCP Server instance

    Raises:
        ImportError: If mcp is not installed
    """
    try:
        from mcp.server import Server
    except ImportError as e:
        raise ImportError(MCP_INSTALL_MESSAGE) from e

    server = Server("meshy-ai")

    # Get tools and their handlers
    mcp_tools = _create_mcp_tools()
    tool_handlers = {tool.name: func for tool, func in mcp_tools}
    tool_list = [tool for tool, _ in mcp_tools]

    tool_decorator = cast(Callable[[], Callable[[Callable[..., Any]], Callable[..., Any]]], server.list_tools)
    call_decorator = cast(Callable[[], Callable[[Callable[..., Any]], Callable[..., Any]]], server.call_tool)

    # Register tools
    @tool_decorator()
    async def list_tools() -> list[Any]:
        return tool_list

    # Handle tool calls
    @call_decorator()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        from mcp.types import TextContent

        tool_arguments = arguments or {}
        handler = tool_handlers.get(name)
        if not handler:
            return [
                TextContent(
                    type="text",
                    text=_tool_payload_text(_tool_error_payload(f"Unknown tool: {name}")),
                )
            ]

        try:
            result = handler(**tool_arguments)
            return [TextContent(type="text", text=_tool_result_text(result))]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=_tool_payload_text(_tool_error_payload(e, values=tool_arguments.values())),
                )
            ]

    return server


def run_server(server: Any | None = None) -> None:
    """Run the MCP server.

    Args:
        server: Optional server instance (creates one if not provided)
    """
    import asyncio

    try:
        from mcp.server.stdio import stdio_server
    except ImportError as e:
        raise ImportError(MCP_INSTALL_MESSAGE) from e

    if server is None:
        server = create_server()

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(main())


def main() -> None:
    """Entry point for the MCP server."""
    run_server()


if __name__ == "__main__":
    main()


__all__ = ["create_server", "main", "run_server"]
