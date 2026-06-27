"""Tests for package metadata boundaries."""

from __future__ import annotations

import tomllib

from pathlib import Path


def test_agentic_and_sync_extras_are_declared() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    extras = pyproject["project"]["optional-dependencies"]

    for extra in [
        "ai",
        "crewai",
        "langgraph",
        "mcp",
        "scraping",
        "secrets-sync",
        "strands",
    ]:
        assert extra in extras


def test_core_metadata_has_no_local_path_sources() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert "tool" in pyproject
    assert "uv" not in pyproject["tool"]


def test_secrets_sync_extra_targets_native_vendor_dependencies() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    extras = pyproject["project"]["optional-dependencies"]

    assert extras["secrets-sync"] == [
        "boto3>=1.42.92",
        "hvac>=2.4.0",
    ]


def test_ownership_map_documents_moved_surfaces() -> None:
    ownership_map = Path("docs/ownership-map.md").read_text()

    for expected in [
        "~/src/jbcom/extended-data-library",
        "extended-data",
        "vendor-fabric",
        "vendor_fabric.secrets_sync",
        "vendor_fabric.agentic",
        "vendor_fabric.agentic.tools.secrets_sync",
    ]:
        assert expected in ownership_map
