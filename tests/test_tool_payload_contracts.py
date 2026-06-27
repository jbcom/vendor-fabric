"""Contracts for connector AI-tool payload surfaces."""

from __future__ import annotations

from importlib import import_module
from typing import get_args, get_origin, get_type_hints

import pytest

from extended_data.containers import ExtendedDict, ExtendedList


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


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_tool_definition_functions_advertise_extended_payloads(module_name: str) -> None:
    """Data-returning AI tools expose Tier 2 payload contracts."""
    module = import_module(module_name)

    for definition in module.TOOL_DEFINITIONS:
        func = definition["func"]
        return_type = get_type_hints(func)["return"]
        origin = get_origin(return_type)

        if origin is ExtendedList:
            assert get_args(return_type) == (ExtendedDict,), f"{module_name}.{func.__name__}"
            continue

        assert return_type is ExtendedDict, f"{module_name}.{func.__name__}"
