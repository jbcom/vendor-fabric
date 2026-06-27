"""Shared framework adapter contracts for connector tool modules."""

from __future__ import annotations

from importlib import import_module
from typing import Any
from unittest.mock import MagicMock

import pytest


TOOL_MODULES = (
    "cloud_connectors.anthropic.tools",
    "cloud_connectors.aws.tools",
    "cloud_connectors.cursor.tools",
    "cloud_connectors.github.tools",
    "cloud_connectors.google.tools",
    "cloud_connectors.meshy.tools",
    "cloud_connectors.slack.tools",
    "cloud_connectors.vault.tools",
    "cloud_connectors.zoom.tools",
)


def _fake_crewai_tool(name: str):
    def decorate(func: Any) -> MagicMock:
        wrapped = MagicMock(wrapped_name=name)
        wrapped.__name__ = func.__name__
        return wrapped

    return decorate


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_langchain_tools_delegate_to_shared_builder(module_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """LangChain factories should pass connector definitions through the shared builder."""
    from cloud_connectors import ai_tools

    module = import_module(module_name)
    expected = [object()]
    build_langchain_tools = MagicMock(return_value=expected)
    monkeypatch.setattr(ai_tools, "build_langchain_tools", build_langchain_tools)

    assert module.get_langchain_tools() is expected
    build_langchain_tools.assert_called_once_with(module.TOOL_DEFINITIONS)


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_crewai_tools_attach_description_and_schema(module_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """CrewAI factories should attach connector metadata to wrapped functions."""
    from cloud_connectors import _optional

    module = import_module(module_name)
    monkeypatch.setattr(_optional, "get_crewai_tool_decorator", lambda: _fake_crewai_tool)

    tools = module.get_crewai_tools()
    first_definition = module.TOOL_DEFINITIONS[0]
    expected_schema = first_definition.get("schema") or first_definition.get("args_schema")

    assert len(tools) == len(module.TOOL_DEFINITIONS)
    assert tools[0].description == first_definition["description"]
    assert tools[0].args_schema is expected_schema


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_crewai_tools_allow_schema_less_definitions(module_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """CrewAI factories should tolerate simple function definitions without schemas."""
    from cloud_connectors import _optional

    class WrappedTool:
        pass

    def fake_tool(name: str):
        def decorate(func: Any) -> WrappedTool:
            wrapped = WrappedTool()
            wrapped.name = name
            wrapped.func = func
            return wrapped

        return decorate

    module = import_module(module_name)
    monkeypatch.setattr(_optional, "get_crewai_tool_decorator", lambda: fake_tool)
    monkeypatch.setattr(
        module,
        "TOOL_DEFINITIONS",
        [{"name": "connector_ping", "description": "Ping connector", "func": lambda: "pong"}],
    )

    tools = module.get_crewai_tools()

    assert len(tools) == 1
    assert tools[0].description == "Ping connector"
    assert not hasattr(tools[0], "args_schema")


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_strands_tools_return_plain_definition_functions(module_name: str) -> None:
    """Strands factories should expose the raw Python functions in definition order."""
    module = import_module(module_name)

    assert module.get_strands_tools() == [definition["func"] for definition in module.TOOL_DEFINITIONS]


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_get_tools_auto_prefers_crewai(module_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-detection should prefer CrewAI when it is importable."""
    from cloud_connectors import _optional

    module = import_module(module_name)
    expected = [object()]
    monkeypatch.setattr(_optional, "is_available", lambda package: package == "crewai")
    monkeypatch.setattr(module, "get_crewai_tools", lambda: expected)

    assert module.get_tools("auto") is expected


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_get_tools_auto_falls_back_to_langchain_then_strands(
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-detection should use LangChain before plain Strands functions."""
    from cloud_connectors import _optional

    module = import_module(module_name)
    langchain_tools = [object()]
    strands_tools = [object()]
    availability = {"langchain_core": True}
    monkeypatch.setattr(_optional, "is_available", lambda package: availability.get(package, False))
    monkeypatch.setattr(module, "get_langchain_tools", lambda: langchain_tools)
    monkeypatch.setattr(module, "get_strands_tools", lambda: strands_tools)

    assert module.get_tools("auto") is langchain_tools

    availability["langchain_core"] = False
    assert module.get_tools("auto") is strands_tools


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_get_tools_explicit_framework_dispatch(module_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit framework names should dispatch to their matching factories."""
    module = import_module(module_name)
    langchain_tools = [object()]
    crewai_tools = [object()]
    strands_tools = [object()]
    monkeypatch.setattr(module, "get_langchain_tools", lambda: langchain_tools)
    monkeypatch.setattr(module, "get_crewai_tools", lambda: crewai_tools)
    monkeypatch.setattr(module, "get_strands_tools", lambda: strands_tools)

    assert module.get_tools("langchain") is langchain_tools
    assert module.get_tools("crewai") is crewai_tools
    assert module.get_tools("strands") is strands_tools
