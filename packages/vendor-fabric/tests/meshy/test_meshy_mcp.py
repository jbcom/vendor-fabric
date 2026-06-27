"""Tests for Meshy MCP serialization helpers."""

from __future__ import annotations

import json
import sys

from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedSet

from vendor_fabric.meshy import mcp as meshy_mcp_module
from vendor_fabric.meshy.mcp import (
    MCP_INSTALL_MESSAGE,
    _create_mcp_tools,
    _jsonable_tool_result,
    _tool_error_payload,
    _tool_result_text,
    create_server,
    main,
    run_server,
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


def test_meshy_mcp_result_lowers_pydantic_like_iterables_and_sets() -> None:
    """Meshy MCP result serialization should handle common tool return shapes."""

    class _ModelDump:
        def model_dump(self) -> dict[str, str]:
            return {"api_key": "key_123", "name": "asset"}

    result = _jsonable_tool_result([_ModelDump(), {"values": {"b", "a"}}])

    assert result[0] == {"api_key": "[REDACTED]", "name": "asset"}
    assert sorted(result[1]["values"]) == ["a", "b"]


def test_meshy_mcp_result_text_uses_shared_export_boundary() -> None:
    """Meshy MCP text payloads should serialize through the Tier 3 export boundary."""
    payload = ExtendedDict({"service": {"name": "meshy"}})

    with patch(
        "vendor_fabric.meshy.mcp.wrap_raw_data_for_export",
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

    with patch("vendor_fabric.meshy.mcp._create_mcp_tools", return_value=[(tool, fake_tool)]):
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

    with patch("vendor_fabric.meshy.mcp._create_mcp_tools", return_value=[(tool, fake_tool)]):
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

    with patch("vendor_fabric.meshy.mcp._create_mcp_tools", return_value=[(tool, fake_tool)]):
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


def test_create_mcp_tools_raises_actionable_install_message(monkeypatch) -> None:
    """Missing MCP SDK should point users to the Meshy MCP extra combination."""
    monkeypatch.setitem(sys.modules, "mcp.types", None)

    with pytest.raises(ImportError) as exc_info:
        _create_mcp_tools()

    assert MCP_INSTALL_MESSAGE in str(exc_info.value)


def test_create_server_raises_actionable_install_message(monkeypatch) -> None:
    """Server creation should fail with install guidance when MCP is absent."""
    monkeypatch.setitem(sys.modules, "mcp.server", None)

    with pytest.raises(ImportError) as exc_info:
        create_server()

    assert MCP_INSTALL_MESSAGE in str(exc_info.value)


def test_run_server_raises_actionable_install_message(monkeypatch) -> None:
    """Server runtime should fail with install guidance when stdio transport is absent."""
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", None)

    with pytest.raises(ImportError) as exc_info:
        run_server(server=object())

    assert MCP_INSTALL_MESSAGE in str(exc_info.value)


def test_run_server_creates_server_and_runs_stdio(monkeypatch) -> None:
    """run_server should create a server and pass stdio streams to server.run."""
    events: list[tuple[str, object]] = []

    class _AsyncStdio:
        async def __aenter__(self) -> tuple[str, str]:
            return "read-stream", "write-stream"

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    class _Server:
        def create_initialization_options(self) -> dict[str, bool]:
            return {"ready": True}

        async def run(self, read_stream: str, write_stream: str, options: dict[str, bool]) -> None:
            events.append(("run", (read_stream, write_stream, options)))

    def create_stdio_server() -> _AsyncStdio:
        return _AsyncStdio()

    def create_fake_server() -> _Server:
        return _Server()

    stdio_module = ModuleType("mcp.server.stdio")
    stdio_module.stdio_server = create_stdio_server  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", stdio_module)
    monkeypatch.setattr(meshy_mcp_module, "create_server", create_fake_server)

    run_server()

    assert events == [("run", ("read-stream", "write-stream", {"ready": True}))]


def test_main_delegates_to_run_server(monkeypatch) -> None:
    """The module entrypoint should delegate to run_server."""
    called = SimpleNamespace(count=0)

    def fake_run_server() -> None:
        called.count += 1

    monkeypatch.setattr(meshy_mcp_module, "run_server", fake_run_server)

    main()

    assert called.count == 1
