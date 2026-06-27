"""Tests for the pytest-vendor-fabric plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pytest_vendor_fabric import plugin


pytest_plugins = ("pytester",)


def _disable_autoload(monkeypatch: Any) -> None:
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


class FakeItem:
    """Small pytest item double used for collection-hook tests."""

    def __init__(self, keywords: set[str]) -> None:
        self.keywords = keywords
        self.markers: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        """Record markers added by the plugin hook."""
        self.markers.append(marker)


def test_pytest_addoption_registers_vendor_options() -> None:
    """The plugin should register E2E and framework selection options."""
    parser = MagicMock()

    plugin.pytest_addoption(parser)

    option_names = [call.args[0] for call in parser.addoption.call_args_list]
    assert option_names == ["--e2e", "--framework"]
    assert parser.addoption.call_args_list[1].kwargs["choices"] == tuple(sorted(plugin.FRAMEWORK_MARKERS))


def test_pytest_configure_registers_markers() -> None:
    """The plugin should register all public test markers."""
    config = MagicMock()

    plugin.pytest_configure(config)

    marker_lines = [call.args[1] for call in config.addinivalue_line.call_args_list]
    assert marker_lines == [
        "crewai: tests that require CrewAI runtime dependencies",
        "e2e: end-to-end tests requiring credentials or external services",
        "langchain: tests that require LangChain runtime dependencies",
        "langgraph: tests that require LangGraph runtime dependencies",
        "strands: tests that require Strands runtime dependencies",
        "vcr: tests that use recorded HTTP cassettes",
    ]


def test_pytest_collection_modifyitems_applies_e2e_and_framework_skips() -> None:
    """Collection filtering should skip disabled E2E and unselected frameworks."""
    config = MagicMock()
    config.getoption.side_effect = lambda option: {"--e2e": False, "--framework": "langgraph"}[option]
    live_item = FakeItem({"e2e"})
    crew_item = FakeItem({"crewai"})
    langgraph_item = FakeItem({"langgraph"})

    plugin.pytest_collection_modifyitems(config, [live_item, crew_item, langgraph_item])

    assert [marker.kwargs["reason"] for marker in live_item.markers] == ["E2E tests disabled; pass --e2e to run them"]
    assert [marker.kwargs["reason"] for marker in crew_item.markers] == ["Test not selected by --framework=langgraph"]
    assert langgraph_item.markers == []


def test_fixture_helpers_return_connector_defaults(monkeypatch: Any) -> None:
    """Fixture helpers should expose mock logging and optional credential values."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    mock_logger = plugin.mock_logger.__wrapped__()

    assert mock_logger.logger is not None
    assert plugin.base_connector_kwargs.__wrapped__(mock_logger) == {
        "logger": mock_logger,
        "from_environment": False,
    }
    assert plugin.anthropic_api_key.__wrapped__() == "anthropic-test"


def test_credential_guards_skip_when_credentials_are_absent(monkeypatch: Any) -> None:
    """Credential guard fixtures should skip cleanly when required env vars are absent."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    with pytest.raises(pytest.skip.Exception):
        plugin.skip_without_anthropic.__wrapped__(None)
    with pytest.raises(pytest.skip.Exception):
        plugin.check_api_key.__wrapped__()
    with pytest.raises(pytest.skip.Exception):
        plugin.check_aws_credentials.__wrapped__()


def test_credential_guards_allow_configured_credentials(monkeypatch: Any) -> None:
    """Credential guard fixtures should return normally when env vars are configured."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    monkeypatch.setenv("AWS_PROFILE", "dev")

    assert plugin.skip_without_anthropic.__wrapped__("anthropic-test") is None
    assert plugin.check_api_key.__wrapped__() is None
    assert plugin.check_aws_credentials.__wrapped__() is None


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
