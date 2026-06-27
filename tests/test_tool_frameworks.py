"""Shared framework selection tests for connector tool modules."""

from __future__ import annotations

import importlib

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


@pytest.mark.parametrize("module_path", TOOL_MODULES)
def test_get_tools_rejects_functions_alias(module_path: str) -> None:
    """Plain-function tools should use the canonical strands framework name."""
    module = importlib.import_module(module_path)

    with pytest.raises(ValueError, match="Unknown framework"):
        module.get_tools("functions")


@pytest.mark.parametrize("module_path", TOOL_MODULES)
def test_get_tools_redacts_unknown_framework_diagnostics(module_path: str) -> None:
    """Unknown framework diagnostics should not echo secret-bearing input."""
    module = importlib.import_module(module_path)

    with pytest.raises(ValueError) as exc_info:
        module.get_tools("password=hunter2 Authorization: Bearer raw_token")

    message = str(exc_info.value)
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message
    assert "auto, langchain, crewai, strands" in message
