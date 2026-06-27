"""Tests for Meshy MCP serialization helpers."""

from __future__ import annotations

import json

from unittest.mock import patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedSet

from cloud_connectors.meshy import mcp as meshy_mcp_module
from cloud_connectors.meshy.mcp import (
    _jsonable_tool_result,
    _tool_error_payload,
    _tool_result_text,
    create_server,
)


def test_meshy_mcp_result_lowers_and_redacts_extended_payloads() -> None:
    """Meshy MCP result serialization should handle Tier 2 payloads directly."""
    payload = ExtendedDict(
        {
            "service": {"name": "meshy"},
            "password": "hunter2",
            "tags": ExtendedSet({"asset", "model"}),
        }
    )

    result = _jsonable_tool_result(payload)

    assert result["service"] == {"name": "meshy"}
    assert result["password"] == "[REDACTED]"
    assert sorted(result["tags"]) == ["asset", "model"]


def test_meshy_mcp_result_text_uses_shared_export_boundary() -> None:
    """Meshy MCP text payloads should serialize through the Tier 3 export boundary."""
    payload = ExtendedDict({"service": {"name": "meshy"}})

    with patch(
        "cloud_connectors.meshy.mcp.wrap_raw_data_for_export",
        wraps=meshy_mcp_module.wrap_raw_data_for_export,
    ) as mock_wrap_for_export:
        text = _tool_result_text(payload)

    assert '"service": {' in text
    mock_wrap_for_export.assert_called_once_with(
        {"service": {"name": "meshy"}},
        allow_encoding="json",
        indent_2=True,
    )


def test_meshy_mcp_error_payload_redacts_sensitive_values() -> None:
    """Meshy MCP errors should not return raw secret-bearing exception text."""
    payload = _tool_error_payload(RuntimeError("failed api_key=key_123 Bearer raw_token"))

    assert "key_123" not in payload["error"]
    assert "raw_token" not in payload["error"]
    assert "[REDACTED]" in payload["error"]


def test_meshy_mcp_error_payload_redacts_unknown_tool_names() -> None:
    """Meshy MCP unknown-tool diagnostics should redact user-controlled names."""
    payload = _tool_error_payload("Unknown tool: password=hunter2 Authorization: Bearer raw_token")

    assert "hunter2" not in payload["error"]
    assert "raw_token" not in payload["error"]
    assert "[REDACTED]" in payload["error"]


def test_meshy_mcp_error_payload_redacts_argument_values() -> None:
    """Meshy MCP errors should redact operation-specific argument values."""
    payload = _tool_error_payload(
        RuntimeError("failed for user@example.com"),
        values=["user@example.com"],
    )

    assert "user@example.com" not in payload["error"]
    assert "[REDACTED]" in payload["error"]


@pytest.mark.asyncio
async def test_create_server_registered_list_tools_handler_exposes_meshy_tools() -> None:
    """The registered Meshy MCP list-tools handler should expose expected schemas."""
    mcp_types = pytest.importorskip("mcp.types")

    server = create_server()
    result = await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
    tools = {tool.name: tool for tool in result.root.tools}

    assert "text3d_generate" in tools
    assert tools["text3d_generate"].inputSchema["required"] == ["prompt"]
    assert tools["text3d_generate"].inputSchema["properties"]["enable_pbr"]["type"] == "boolean"
    assert "check_task_status" in tools
    assert tools["check_task_status"].inputSchema["properties"]["task_type"]["default"] == "text-to-3d"


@pytest.mark.asyncio
async def test_create_server_registered_call_handler_redacts_payloads() -> None:
    """The registered Meshy MCP call handler should serialize and redact tool results."""
    mcp_types = pytest.importorskip("mcp.types")

    def fake_tool(enabled: bool = False) -> ExtendedDict:
        return ExtendedDict({"enabled": enabled, "password": "hunter2"})

    tool = mcp_types.Tool(
        name="fake_meshy_tool",
        description="Fake Meshy tool.",
        inputSchema={
            "type": "object",
            "properties": {"enabled": {"type": "boolean", "default": False}},
            "required": [],
        },
    )

    with patch("cloud_connectors.meshy.mcp._create_mcp_tools", return_value=[(tool, fake_tool)]):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="fake_meshy_tool",
                    arguments={"enabled": True},
                )
            )
        )

    assert json.loads(result.root.content[0].text) == {"enabled": True, "password": "[REDACTED]"}


@pytest.mark.asyncio
async def test_create_server_registered_call_handler_redacts_error_argument_values() -> None:
    """The registered Meshy MCP call handler should redact operation-specific error values."""
    mcp_types = pytest.importorskip("mcp.types")

    def fake_tool(email: str) -> None:
        raise RuntimeError(f"failed for {email} with api_key=key_123")

    tool = mcp_types.Tool(
        name="fake_meshy_tool",
        description="Fake Meshy tool.",
        inputSchema={
            "type": "object",
            "properties": {"email": {"type": "string"}},
            "required": ["email"],
        },
    )

    with patch("cloud_connectors.meshy.mcp._create_mcp_tools", return_value=[(tool, fake_tool)]):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="fake_meshy_tool",
                    arguments={"email": "user@example.com"},
                )
            )
        )

    payload = json.loads(result.root.content[0].text)
    assert "user@example.com" not in payload["error"]
    assert "key_123" not in payload["error"]
    assert "[REDACTED]" in payload["error"]


@pytest.mark.asyncio
async def test_create_server_registered_call_handler_accepts_missing_arguments() -> None:
    """The registered Meshy MCP call handler should treat omitted arguments as empty."""
    mcp_types = pytest.importorskip("mcp.types")

    def fake_tool() -> ExtendedDict:
        return ExtendedDict({"status": "ok"})

    tool = mcp_types.Tool(
        name="fake_meshy_tool",
        description="Fake Meshy tool.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    )

    with patch("cloud_connectors.meshy.mcp._create_mcp_tools", return_value=[(tool, fake_tool)]):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="fake_meshy_tool",
                )
            )
        )

    assert json.loads(result.root.content[0].text) == {"status": "ok"}
