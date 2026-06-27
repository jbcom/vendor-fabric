"""Core CrewAI engine - discovery, loading, and running of package-defined crews."""

from __future__ import annotations

from vendor_fabric.agentic.core.discovery import discover_packages, get_crew_config, load_manifest
from vendor_fabric.agentic.core.loader import load_crew_from_config
from vendor_fabric.agentic.core.manager import ManagerAgent
from vendor_fabric.agentic.core.runner import run_crew


__all__ = [
    "ManagerAgent",
    "discover_packages",
    "get_crew_config",
    "load_crew_from_config",
    "load_manifest",
    "run_crew",
]
