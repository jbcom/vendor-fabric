"""Shared pytest configuration for E2E tests.

This module provides common fixtures and configuration used across
all E2E test subpackages.

Directory structure:
    tests/e2e/
    ├── conftest.py          # This file (shared config)
    └── <connector>/
        ├── conftest.py      # Connector-specific config
        ├── cassettes/       # VCR cassettes
        ├── fixtures/        # Connector-specific fixtures
        │   └── models/      # Generated GLB files, etc.
        └── test_*.py        # Test files
"""

from __future__ import annotations

import os

from pathlib import Path

import pytest


# Base directory
E2E_DIR = Path(__file__).parent


@pytest.fixture
def anthropic_api_key() -> str | None:
    """Get Anthropic API key from environment."""
    return os.environ.get("ANTHROPIC_API_KEY")


@pytest.fixture
def skip_without_anthropic(anthropic_api_key: str | None):
    """Skip test if ANTHROPIC_API_KEY not set."""
    if not anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY required")


def pytest_configure(config):
    """Register custom markers for E2E tests."""
    config.addinivalue_line(
        "markers",
        "e2e: mark test as end-to-end (may require API keys)",
    )
    config.addinivalue_line(
        "markers",
        "langchain: mark test as using LangChain/LangGraph framework",
    )
    config.addinivalue_line(
        "markers",
        "crewai: mark test as using CrewAI framework",
    )
    config.addinivalue_line(
        "markers",
        "strands: mark test as using AWS Strands framework",
    )
    config.addinivalue_line(
        "markers",
        "vcr: mark test for VCR cassette recording",
    )
