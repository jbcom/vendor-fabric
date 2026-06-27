"""Shared pytest configuration for live provider E2E tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def meshy_api_key() -> str | None:
    """Return the Meshy API key from the environment, when present."""
    return os.environ.get("MESHY_API_KEY")


@pytest.fixture
def require_meshy_api_key(meshy_api_key: str | None) -> str:
    """Return a Meshy API key or skip the live provider test."""
    if not meshy_api_key:
        pytest.skip("MESHY_API_KEY required")
    return meshy_api_key
