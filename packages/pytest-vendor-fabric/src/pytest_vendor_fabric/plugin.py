"""Pytest plugin for vendor-fabric test suites."""

from __future__ import annotations

import os

from typing import Any
from unittest.mock import MagicMock

import pytest


def pytest_addoption(parser: Any) -> None:
    """Add vendor-fabric test-suite options."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E tests that require real vendor credentials and external services",
    )


def pytest_configure(config: Any) -> None:
    """Register markers used by vendor-fabric test suites."""
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring credentials or external services")


def pytest_collection_modifyitems(config: Any, items: list[pytest.Item]) -> None:
    """Skip live E2E tests by default."""
    e2e_enabled = config.getoption("--e2e")

    skip_e2e = pytest.mark.skip(reason="E2E tests disabled; pass --e2e to run them")

    for item in items:
        if "e2e" in item.keywords and not e2e_enabled:
            item.add_marker(skip_e2e)


@pytest.fixture
def mock_logger() -> MagicMock:
    """Provide a mock Extended Data logger for connector tests."""
    from extended_data.logging import Logging

    mock_logging = MagicMock(spec=Logging)
    mock_logging.logger = MagicMock()
    return mock_logging


@pytest.fixture
def base_connector_kwargs(mock_logger: MagicMock) -> dict[str, Any]:
    """Provide common keyword arguments for vendor connector tests."""
    return {
        "logger": mock_logger,
        "from_environment": False,
    }


@pytest.fixture
def anthropic_api_key() -> str | None:
    """Return the Anthropic API key from the environment, when present."""
    return os.environ.get("ANTHROPIC_API_KEY")


@pytest.fixture
def skip_without_anthropic(anthropic_api_key: str | None) -> None:
    """Skip a live test when ``ANTHROPIC_API_KEY`` is unavailable."""
    if not anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY required")


@pytest.fixture
def check_api_key() -> None:
    """Skip live E2E tests when Anthropic credentials are unavailable."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")


@pytest.fixture
def check_aws_credentials() -> None:
    """Skip live E2E tests when AWS Bedrock credentials are unavailable."""
    has_key = os.environ.get("AWS_ACCESS_KEY_ID")
    has_profile = os.environ.get("AWS_PROFILE")
    if not (has_key or has_profile):
        pytest.skip("AWS credentials not configured; set AWS_ACCESS_KEY_ID or AWS_PROFILE")
