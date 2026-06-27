"""Custom tools for vendor-fabric-agent.

Tool modules are imported lazily so the core package can be imported without
pulling in optional framework dependencies like CrewAI or scraping extras.
"""

from __future__ import annotations

from contextlib import suppress
from importlib import import_module
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from vendor_fabric.agentic.tools.file_tools import DirectoryListTool, GameCodeReaderTool, GameCodeWriterTool
    from vendor_fabric.agentic.tools.scraping_tools import CrawlWebsiteTool, ScrapeWebsiteTool


def _load_attr(module_name: str, attr_name: str) -> Any:
    module = import_module(module_name)
    return getattr(module, attr_name)


def __getattr__(name: str) -> Any:
    if name in {"DirectoryListTool", "GameCodeReaderTool", "GameCodeWriterTool"}:
        return _load_attr("vendor_fabric.agentic.tools.file_tools", name)
    if name in {"CrawlWebsiteTool", "ScrapeWebsiteTool"}:
        return _load_attr("vendor_fabric.agentic.tools.scraping_tools", name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_file_tools() -> list[Any]:
    """Get the standard file manipulation tools."""
    return [
        __getattr__("GameCodeReaderTool")(),
        __getattr__("GameCodeWriterTool")(),
        __getattr__("DirectoryListTool")(),
    ]


def get_scraping_tools() -> list[Any]:
    """Get the web scraping tools."""
    return [
        __getattr__("ScrapeWebsiteTool")(),
        __getattr__("CrawlWebsiteTool")(),
    ]


def get_secrets_sync_tools(framework: str = "auto") -> list[Any]:
    """Get SecretSync tools for the requested agent framework."""
    module = import_module("vendor_fabric.agentic.tools.secrets_sync")
    return module.get_tools(framework)


def get_all_tools() -> list[Any]:
    """Get all available tools."""
    tools = get_file_tools()

    with suppress(ImportError):
        tools.extend(get_scraping_tools())

    with suppress(ImportError):
        tools.extend(get_secrets_sync_tools("strands"))

    try:
        from mesh_toolkit.agent_tools.crewai import get_tools as get_meshy_tools

        tools.extend(get_meshy_tools())
    except ImportError:
        pass

    return tools


__all__ = [
    "CrawlWebsiteTool",
    "DirectoryListTool",
    "GameCodeReaderTool",
    "GameCodeWriterTool",
    "ScrapeWebsiteTool",
    "get_all_tools",
    "get_file_tools",
    "get_scraping_tools",
    "get_secrets_sync_tools",
]
