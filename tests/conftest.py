"""Pytest configuration and fixtures for vendor_fabric tests.

This module configures pytest for the vendor-fabric test suite:
- Unit tests run by default
- E2E tests require the --e2e flag
- Framework-specific E2E tests can be selected with --framework

Usage:
    # Run unit tests only (default)
    pytest tests/

    # Run E2E tests (requires API keys)
    pytest tests/e2e/ --e2e

    # Run specific framework E2E tests
    pytest tests/e2e/ --e2e --framework=langchain
    pytest tests/e2e/ --e2e --framework=crewai
    pytest tests/e2e/ --e2e --framework=strands
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from extended_data.logging import Logging


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E tests (requires MESHY_API_KEY and ANTHROPIC_API_KEY)",
    )
    parser.addoption(
        "--framework",
        action="store",
        default=None,
        choices=["langchain", "crewai", "strands"],
        help="Run E2E tests for specific AI framework only",
    )


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "e2e: End-to-end tests requiring API keys")
    config.addinivalue_line("markers", "e2e_langchain: E2E tests for LangChain")
    config.addinivalue_line("markers", "e2e_crewai: E2E tests for CrewAI")
    config.addinivalue_line("markers", "e2e_strands: E2E tests for AWS Strands")


def pytest_collection_modifyitems(config, items):
    """Skip E2E tests unless --e2e flag is provided."""
    run_e2e = config.getoption("--e2e")
    framework = config.getoption("--framework")

    skip_e2e = pytest.mark.skip(reason="E2E tests require --e2e flag")
    skip_framework = pytest.mark.skip(reason=f"Test not for framework: {framework}")

    for item in items:
        # Check if test is in e2e directory
        is_e2e_test = "e2e" in str(item.fspath)

        if is_e2e_test:
            if not run_e2e:
                item.add_marker(skip_e2e)
            elif framework:
                # Filter by framework if specified
                test_framework = None
                if "langchain" in item.name or "langchain" in str(item.fspath):
                    test_framework = "langchain"
                elif "crewai" in item.name or "crewai" in str(item.fspath):
                    test_framework = "crewai"
                elif "strands" in item.name or "strands" in str(item.fspath):
                    test_framework = "strands"

                if test_framework and test_framework != framework:
                    item.add_marker(skip_framework)


@pytest.fixture
def mock_logger():
    """Provide a mock Logging instance for testing."""
    mock_logging = MagicMock(spec=Logging)
    mock_logging.logger = MagicMock()
    return mock_logging


@pytest.fixture
def base_connector_kwargs(mock_logger):
    """Provide common kwargs for all connectors."""
    return {
        "logger": mock_logger,
        "from_environment": False,
    }
