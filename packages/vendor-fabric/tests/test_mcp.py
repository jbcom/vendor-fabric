"""Tests for unified MCP server."""

from __future__ import annotations

import json

from unittest.mock import patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedSet

from vendor_fabric import mcp as mcp_module
from vendor_fabric.mcp import (
    _catalog_tool_definitions,
    _check_mcp_installed,
    _get_method_schema,
    _get_public_methods,
    _jsonable_tool_result,
    _tool_error_text,
    _tool_result_text,
    _unknown_tool_text,
    create_server,
)
from vendor_fabric.meshy.connector import MeshyConnector


class ExampleMCPConnector:
    """Tiny connector shell for MCP handler tests."""

    def fetch(self, enabled: bool = False, count: int = 0) -> ExtendedDict:
        """Fetch example MCP data."""
        return ExtendedDict({"enabled": enabled, "count": count, "password": "hunter2"})


class AsyncMCPConnector:
    """Tiny async connector shell for MCP handler tests."""

    async def fetch(self, token: str) -> ExtendedDict:
        """Fetch async data."""
        return ExtendedDict({"token": token, "status": "ok"})

    async def fail(self, token: str) -> ExtendedDict:
        """Fail with a sensitive value."""
        raise RuntimeError(f"failed with {token}")


def _block_imports(monkeypatch: pytest.MonkeyPatch, blocked_name: str) -> None:
    real_import = mcp_module.builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == blocked_name:
            raise ImportError(blocked_name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(mcp_module.builtins, "__import__", blocked_import)


def test_create_server() -> None:
    """Test that the MCP server can be created and has tools."""
    pytest.importorskip("mcp")
    server = create_server()
    assert server.name == "vendor-fabric"
    # Basic check that server was initialized
    assert server is not None


def test_check_mcp_installed_reports_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP availability checks should degrade to False when the SDK import fails."""
    _block_imports(monkeypatch, "mcp.server")

    assert _check_mcp_installed() is False


def test_create_server_reports_install_hint_when_mcp_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server creation should fail with the documented extra when MCP is absent."""
    _block_imports(monkeypatch, "mcp.server")

    with pytest.raises(ImportError, match=r"pip install vendor-fabric\[mcp\]"):
        create_server()


def test_mcp_public_methods_only_include_extended_payload_boundaries() -> None:
    """Generic MCP exposure should skip raw clients and inherited base helpers."""
    method_names = {name for name, _ in _get_public_methods(MeshyConnector)}

    assert "text3d_generate" in method_names
    assert "image3d_generate" in method_names
    assert "request_data" not in method_names
    assert "decode_response" not in method_names
    assert "get_ai_tool_definitions" not in method_names
    assert "freeze_inputs" not in method_names
    assert "merge_inputs" not in method_names
    assert "replace_inputs" not in method_names


def test_method_schema_maps_supported_parameter_types_and_doc_descriptions() -> None:
    """MCP schemas should infer simple JSON types and required fields."""

    def sample(count: int, ratio: float, enabled: bool, tags: list[str], metadata: dict[str, str], note="n/a") -> None:
        """Do sample work.

        count: number of items
        metadata: item metadata
        """

    schema = _get_method_schema(sample)

    assert schema["required"] == ["count", "ratio", "enabled", "tags", "metadata"]
    assert schema["properties"]["count"] == {"type": "integer", "description": "number of items"}
    assert schema["properties"]["ratio"]["type"] == "number"
    assert schema["properties"]["enabled"]["type"] == "boolean"
    assert schema["properties"]["tags"]["type"] == "array"
    assert schema["properties"]["metadata"] == {"type": "object", "description": "item metadata"}
    assert schema["properties"]["note"] == {"type": "string", "default": "n/a"}


def test_method_schema_falls_back_when_type_hints_are_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP schema generation should still work when annotations cannot resolve."""

    def sample(value: MissingAnnotation) -> None:  # noqa: F821
        pass

    monkeypatch.setattr(mcp_module, "get_type_hints", lambda method: (_ for _ in ()).throw(NameError("missing")))

    schema = _get_method_schema(sample)

    assert schema["properties"]["value"]["type"] == "string"
    assert schema["required"] == ["value"]


def test_catalog_tools_expose_connector_discovery_without_credentials() -> None:
    """Generic MCP should expose connector catalog queries as first-class tools."""
    tools = _catalog_tool_definitions()

    expected = {
        "vendor_fabric_list_connectors",
        "vendor_fabric_list_available_connectors",
        "vendor_fabric_list_connector_info",
        "vendor_fabric_get_connector_info",
        "vendor_fabric_list_connector_categories",
        "vendor_fabric_list_connector_capabilities",
        "vendor_fabric_list_connectors_by_category",
        "vendor_fabric_list_connectors_by_capability",
    }

    assert expected <= set(tools)
    assert tools["vendor_fabric_get_connector_info"]["parameters"]["required"] == ["name"]
    assert tools["vendor_fabric_list_connectors_by_category"]["parameters"]["required"] == ["category"]
    assert tools["vendor_fabric_list_connectors_by_capability"]["parameters"]["required"] == ["capability"]


def test_catalog_tool_handlers_return_tier2_catalog_payloads() -> None:
    """Catalog MCP handlers should reuse the registry's Tier 2 payload surface."""
    tools = _catalog_tool_definitions()

    names = tools["vendor_fabric_list_connectors"]["handler"]()
    available_names = tools["vendor_fabric_list_available_connectors"]["handler"]()
    github = tools["vendor_fabric_get_connector_info"]["handler"](name="github")
    categories = tools["vendor_fabric_list_connector_categories"]["handler"]()
    repositories = tools["vendor_fabric_list_connectors_by_capability"]["handler"](capability="repositories")

    assert isinstance(names, ExtendedList)
    assert "github" in names
    assert isinstance(available_names, ExtendedList)
    assert "cursor" in available_names
    assert set(available_names) <= set(names)
    assert isinstance(github, ExtendedDict)
    assert github["category"] == "development"
    assert "repositories" in github["capabilities"]
    assert isinstance(categories, ExtendedList)
    assert "cloud" in categories
    assert isinstance(repositories, ExtendedList)
    assert "github" in {connector["name"] for connector in repositories}


def test_catalog_tool_result_text_uses_shared_export_boundary() -> None:
    """Catalog MCP tool output should serialize like connector method output."""
    tools = _catalog_tool_definitions()
    payload = tools["vendor_fabric_get_connector_info"]["handler"](name="github")

    text = _tool_result_text(payload)

    assert '"name": "github"' in text
    assert '"category": "development"' in text
    assert '"capabilities": [' in text


def test_jsonable_tool_result_lowers_extended_mapping_payloads() -> None:
    """MCP result serialization keeps Tier 2 mapping payloads as JSON objects."""
    payload = ExtendedDict({"service": {"name": "api"}})

    assert _jsonable_tool_result(payload) == {"service": {"name": "api"}}


def test_tool_result_text_uses_shared_export_boundary() -> None:
    """MCP text payloads should serialize through the Tier 3 export boundary."""
    payload = ExtendedDict({"service": {"name": "api"}})

    with patch(
        "vendor_fabric.mcp.wrap_raw_data_for_export",
        wraps=mcp_module.wrap_raw_data_for_export,
    ) as mock_wrap_for_export:
        text = _tool_result_text(payload)

    assert '"service": {' in text
    mock_wrap_for_export.assert_called_once_with(
        {"service": {"name": "api"}},
        allow_encoding="json",
        indent_2=True,
        default=str,
    )


def test_jsonable_tool_result_redacts_sensitive_mapping_payloads() -> None:
    """MCP result serialization should not bypass connector redaction."""
    payload = ExtendedDict({"password": "hunter2", "nested": {"api_key": "key_123"}})

    assert _jsonable_tool_result(payload) == {"password": "[REDACTED]", "nested": {"api_key": "[REDACTED]"}}


def test_jsonable_tool_result_lowers_extended_sequence_payloads() -> None:
    """MCP result serialization keeps Tier 2 sequence payloads as JSON arrays."""
    payload = ExtendedList([{"service": "api"}])

    assert _jsonable_tool_result(payload) == [{"service": "api"}]


def test_jsonable_tool_result_redacts_sensitive_sequence_payloads() -> None:
    """MCP result serialization should redact secrets inside array payloads."""
    payload = ExtendedList([{"name": "api", "access_token": "tok_123"}, {"message": "client_secret=raw"}])

    assert _jsonable_tool_result(payload) == [
        {"name": "api", "access_token": "[REDACTED]"},
        {"message": "client_secret=[REDACTED]"},
    ]


def test_jsonable_tool_result_lowers_extended_set_payloads() -> None:
    """MCP result serialization turns Tier 2 sets into JSON arrays."""
    payload = ExtendedSet({"api", "worker"})

    assert sorted(_jsonable_tool_result(payload)) == ["api", "worker"]


def test_tool_error_text_redacts_sensitive_exception_values() -> None:
    """Generic MCP errors should not bypass connector redaction."""
    error = RuntimeError("failed password=hunter2 Authorization: Bearer raw_token")

    text = _tool_error_text(error)

    assert "hunter2" not in text
    assert "raw_token" not in text
    assert "[REDACTED]" in text


def test_tool_error_text_redacts_explicit_argument_values() -> None:
    """Generic MCP errors should redact caller-provided resource context."""
    error = RuntimeError("failed for private-user@example.com at /tmp/private%2Fpath while handling Fix login")

    text = _tool_error_text(
        error,
        values=[
            {
                "email": "private-user@example.com",
                "metadata": {"path": "/tmp/private/path", "prompt": "Fix login"},
            }
        ],
    )

    assert "private-user@example.com" not in text
    assert "/tmp/private%2Fpath" not in text
    assert "Fix login" not in text
    assert text.count("[REDACTED]") >= 3


def test_unknown_tool_text_redacts_sensitive_tool_names() -> None:
    """Generic MCP unknown-tool diagnostics should redact user-controlled names."""
    text = _unknown_tool_text("password=hunter2 Authorization: Bearer raw_token")

    assert "hunter2" not in text
    assert "raw_token" not in text
    assert "[REDACTED]" in text


@pytest.mark.asyncio
async def test_create_server_registered_list_tools_handler_exposes_catalog_and_methods() -> None:
    """The registered MCP list-tools handler should expose catalog and connector tools."""
    mcp_types = pytest.importorskip("mcp.types")

    with patch("vendor_fabric.mcp._list_connector_classes", return_value={"example": ExampleMCPConnector}):
        server = create_server()

    result = await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
    tools = {tool.name: tool for tool in result.root.tools}

    assert "vendor_fabric_get_connector_info" in tools
    assert tools["vendor_fabric_get_connector_info"].inputSchema["required"] == ["name"]
    assert "example_fetch" in tools
    assert tools["example_fetch"].description == "Fetch example MCP data."
    assert tools["example_fetch"].inputSchema["properties"]["enabled"]["type"] == "boolean"
    assert tools["example_fetch"].inputSchema["properties"]["count"]["type"] == "integer"


@pytest.mark.asyncio
async def test_create_server_registered_catalog_call_handler_uses_shared_result_boundary() -> None:
    """The registered MCP call handler should serialize catalog tool results."""
    mcp_types = pytest.importorskip("mcp.types")
    server = create_server()
    await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())

    result = await server.request_handlers[mcp_types.CallToolRequest](
        mcp_types.CallToolRequest(
            params=mcp_types.CallToolRequestParams(
                name="vendor_fabric_get_connector_info",
                arguments={"name": "github"},
            )
        )
    )

    payload = json.loads(result.root.content[0].text)
    assert payload["name"] == "github"
    assert payload["category"] == "development"
    assert "repositories" in payload["capabilities"]


@pytest.mark.asyncio
async def test_create_server_registered_connector_call_handler_redacts_payloads() -> None:
    """The registered MCP call handler should dispatch connector methods and redact results."""
    mcp_types = pytest.importorskip("mcp.types")
    connector = ExampleMCPConnector()

    with (
        patch("vendor_fabric.mcp._list_connector_classes", return_value={"example": ExampleMCPConnector}),
        patch("vendor_fabric.mcp.get_connector", return_value=connector) as mock_get_connector,
    ):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="example_fetch",
                    arguments={"enabled": True, "count": 3},
                )
            )
        )

    mock_get_connector.assert_called_once_with("example")
    payload = json.loads(result.root.content[0].text)
    assert payload == {"enabled": True, "count": 3, "password": "[REDACTED]"}


@pytest.mark.asyncio
async def test_create_server_registered_connector_call_handler_awaits_coroutines_and_redacts() -> None:
    """The registered MCP call handler should await async connector results."""
    mcp_types = pytest.importorskip("mcp.types")
    connector = AsyncMCPConnector()

    with (
        patch("vendor_fabric.mcp._list_connector_classes", return_value={"async_example": AsyncMCPConnector}),
        patch("vendor_fabric.mcp.get_connector", return_value=connector),
    ):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="async_example_fetch",
                    arguments={"token": "secret-token"},
                )
            )
        )

    payload = json.loads(result.root.content[0].text)
    assert payload == {"token": "[REDACTED]", "status": "ok"}


@pytest.mark.asyncio
async def test_create_server_registered_connector_call_handler_redacts_exceptions() -> None:
    """The registered MCP call handler should redact async connector failures."""
    mcp_types = pytest.importorskip("mcp.types")
    connector = AsyncMCPConnector()

    with (
        patch("vendor_fabric.mcp._list_connector_classes", return_value={"async_example": AsyncMCPConnector}),
        patch("vendor_fabric.mcp.get_connector", return_value=connector),
    ):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="async_example_fail",
                    arguments={"token": "secret-token"},
                )
            )
        )

    text = result.root.content[0].text
    assert "secret-token" not in text
    assert "RuntimeError" in text
    assert "[REDACTED]" in text


@pytest.mark.asyncio
async def test_create_server_registered_catalog_call_handler_redacts_exceptions() -> None:
    """Catalog MCP handler failures should redact caller arguments."""
    mcp_types = pytest.importorskip("mcp.types")

    def fail_catalog(token: str) -> ExtendedDict:
        raise RuntimeError(f"failed with {token}")

    with patch(
        "vendor_fabric.mcp._catalog_tool_definitions",
        return_value={
            "vendor_fabric_fail": {
                "description": "Fail catalog",
                "parameters": {
                    "type": "object",
                    "properties": {"token": {"type": "string"}},
                    "required": ["token"],
                },
                "handler": fail_catalog,
            }
        },
    ):
        server = create_server()
        await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        result = await server.request_handlers[mcp_types.CallToolRequest](
            mcp_types.CallToolRequest(
                params=mcp_types.CallToolRequestParams(
                    name="vendor_fabric_fail",
                    arguments={"token": "secret-token"},
                )
            )
        )

    text = result.root.content[0].text
    assert "secret-token" not in text
    assert "RuntimeError" in text
    assert "[REDACTED]" in text


@pytest.mark.asyncio
async def test_create_server_registered_call_handler_redacts_unknown_tools() -> None:
    """The registered MCP call handler should sanitize unknown tool diagnostics."""
    mcp_types = pytest.importorskip("mcp.types")
    server = create_server()
    await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())

    result = await server.request_handlers[mcp_types.CallToolRequest](
        mcp_types.CallToolRequest(
            params=mcp_types.CallToolRequestParams(
                name="password=hunter2 Authorization: Bearer raw_token",
                arguments={},
            )
        )
    )

    text = result.root.content[0].text
    assert "hunter2" not in text
    assert "raw_token" not in text
    assert "Unknown tool: password=[REDACTED]" in text
