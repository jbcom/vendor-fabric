"""Boundary tests between vendor-fabric and agentic-fabric."""

from __future__ import annotations

import importlib.util

from importlib import import_module
from pathlib import Path

import pytest
import tomlkit


PACKAGE_ROOT = Path(__file__).resolve().parents[1]

TOOL_MODULES = (
    "vendor_fabric.anthropic.tools",
    "vendor_fabric.aws.tools",
    "vendor_fabric.cursor.tools",
    "vendor_fabric.github.tools",
    "vendor_fabric.google.tools",
    "vendor_fabric.meshy.tools",
    "vendor_fabric.secrets_sync.tools",
    "vendor_fabric.slack.tools",
    "vendor_fabric.vault.tools",
    "vendor_fabric.zoom.tools",
)

FRAMEWORK_FACTORY_SYMBOLS = (
    "build_langchain_tools",
    "get_crewai_tool_decorator",
    "get_crewai_tools",
    "get_langchain_tools",
    "get_strands_tools",
    "get_tools",
    "raise_unknown_tool_framework",
)

AGENT_FRAMEWORK_EXTRAS = {"ai", "crewai", "langchain", "langgraph", "strands"}
AGENT_FRAMEWORK_DEPENDENCY_NAMES = ("crewai", "langchain", "langgraph", "langsmith", "strands")


def _pyproject() -> tomlkit.TOMLDocument:
    return tomlkit.parse((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_provider_tool_modules_expose_metadata_not_framework_factories(module_name: str) -> None:
    """Provider modules expose capability metadata; agentic-fabric owns framework wrapping."""
    module = import_module(module_name)

    assert isinstance(module.TOOL_DEFINITIONS, list)
    assert module.TOOL_DEFINITIONS
    for definition in module.TOOL_DEFINITIONS:
        assert {"name", "description", "func"} <= set(definition)

    for symbol in FRAMEWORK_FACTORY_SYMBOLS:
        assert not hasattr(module, symbol), f"{module_name} still exports {symbol}"


def test_vendor_fabric_does_not_publish_agent_framework_extras() -> None:
    """Agent framework dependencies belong to agentic-fabric, not vendor-fabric."""
    extras = _pyproject()["project"]["optional-dependencies"]

    assert AGENT_FRAMEWORK_EXTRAS.isdisjoint(extras)
    for dependencies in extras.values():
        for dependency in dependencies:
            normalized = str(dependency).lower()
            assert not any(name in normalized for name in AGENT_FRAMEWORK_DEPENDENCY_NAMES)


def test_vendor_fabric_ai_tools_module_is_not_published() -> None:
    """The old framework adapter module should not be importable from vendor-fabric."""
    assert importlib.util.find_spec("vendor_fabric.ai_tools") is None
