"""Tests for the pytest-vendor-fabric plugin."""

from __future__ import annotations

from typing import Any


pytest_plugins = ("pytester",)


def _disable_autoload(monkeypatch: Any) -> None:
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


def test_connector_fixtures_are_available(pytester: Any, monkeypatch: Any) -> None:
    """The plugin exposes shared connector fixtures."""
    _disable_autoload(monkeypatch)
    pytester.makepyfile(
        """
def test_connector_kwargs(base_connector_kwargs):
    assert base_connector_kwargs["from_environment"] is False
    assert base_connector_kwargs["logger"].logger is not None
""",
    )

    result = pytester.runpytest("-p", "pytest_vendor_fabric.plugin", "-q")

    result.assert_outcomes(passed=1)


def test_e2e_tests_skip_by_default(pytester: Any, monkeypatch: Any) -> None:
    """E2E tests are skipped unless --e2e is provided."""
    _disable_autoload(monkeypatch)
    pytester.makepyfile(
        """
import pytest

@pytest.mark.e2e
def test_live():
    assert False

def test_unit():
    assert True
""",
    )

    result = pytester.runpytest("-p", "pytest_vendor_fabric.plugin", "-q")

    result.assert_outcomes(passed=1, skipped=1)


def test_framework_filter_selects_marked_tests(pytester: Any, monkeypatch: Any) -> None:
    """The --framework option skips tests for other framework markers."""
    _disable_autoload(monkeypatch)
    pytester.makepyfile(
        """
import pytest

@pytest.mark.crewai
def test_crewai():
    assert False

@pytest.mark.langgraph
def test_langgraph():
    assert True
""",
    )

    result = pytester.runpytest("-p", "pytest_vendor_fabric.plugin", "--framework=langgraph", "-q")

    result.assert_outcomes(passed=1, skipped=1)


def test_check_api_key_skips_without_anthropic(pytester: Any, monkeypatch: Any) -> None:
    """Credential guards remain available for provider E2E tests."""
    _disable_autoload(monkeypatch)
    pytester.makepyfile(
        """
def test_live_provider(check_api_key):
    assert False
""",
    )

    result = pytester.runpytest("-p", "pytest_vendor_fabric.plugin", "-q")

    result.assert_outcomes(skipped=1)
