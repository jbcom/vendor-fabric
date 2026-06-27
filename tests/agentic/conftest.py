"""Pytest configuration for crew-agents tests."""

from __future__ import annotations

import os
import sys
import types

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pytest_mock import MockerFixture


class CrewMocker:
    """Focused optional-framework mocking helper for runner tests."""

    MagicMock = MagicMock

    def __init__(self, mocker: MockerFixture) -> None:
        self.mocker = mocker
        self.patch = mocker.patch
        self.mocked_modules: dict[str, types.ModuleType | MagicMock] = {}

    def mock_module(self, name: str) -> types.ModuleType:
        """Create or return a mocked module in sys.modules."""
        existing = sys.modules.get(name)
        if isinstance(existing, types.ModuleType):
            return existing

        module = types.ModuleType(name)
        sys.modules[name] = module
        self.mocked_modules[name] = module
        return module

    def restore_modules(self) -> None:
        """Remove modules inserted by this helper."""
        for name in list(self.mocked_modules):
            sys.modules.pop(name, None)
        self.mocked_modules.clear()

    def mock_crewai(self) -> dict[str, types.ModuleType]:
        """Mock the CrewAI modules imported by the package."""
        crewai = self.mock_module("crewai")
        crewai.Agent = MagicMock(name="Agent")
        crewai.Task = MagicMock(name="Task")
        crewai.Crew = MagicMock(name="Crew")
        crewai.LLM = MagicMock(name="LLM")
        crewai.Process = types.SimpleNamespace(sequential="sequential", hierarchical="hierarchical")

        knowledge_pkg = self.mock_module("crewai.knowledge")
        knowledge_source_pkg = self.mock_module("crewai.knowledge.source")
        text_source = self.mock_module("crewai.knowledge.source.text_file_knowledge_source")
        text_source.TextFileKnowledgeSource = MagicMock(name="TextFileKnowledgeSource")

        return {
            "crewai": crewai,
            "knowledge": knowledge_pkg,
            "knowledge_source": knowledge_source_pkg,
            "text_file_knowledge_source": text_source,
        }

    def patch_crewai_agent(self) -> MagicMock:
        return self.patch("crewai.Agent", autospec=False)

    def patch_crewai_task(self) -> MagicMock:
        return self.patch("crewai.Task", autospec=False)

    def patch_crewai_crew(self) -> MagicMock:
        return self.patch("crewai.Crew", autospec=False)

    def patch_crewai_process(self) -> MagicMock:
        return self.patch("crewai.Process", types.SimpleNamespace(sequential="sequential", hierarchical="hierarchical"))

    def patch_knowledge_source(self) -> MagicMock:
        return self.patch(
            "crewai.knowledge.source.text_file_knowledge_source.TextFileKnowledgeSource",
            autospec=False,
        )

    def mock_crewai_crew(self, result: str = "Test result") -> MagicMock:
        """Return a CrewAI-like crew object with kickoff behavior."""
        crew = MagicMock(name="Crew")
        kickoff_result = MagicMock()
        kickoff_result.raw = result
        crew.kickoff.return_value = kickoff_result
        return crew

    def mock_langgraph(self) -> dict[str, types.ModuleType]:
        """Mock LangGraph and LangChain modules imported by the package."""
        langgraph = self.mock_module("langgraph")
        prebuilt = self.mock_module("langgraph.prebuilt")
        prebuilt.create_react_agent = MagicMock(name="create_react_agent")

        langchain_anthropic = self.mock_module("langchain_anthropic")
        langchain_anthropic.ChatAnthropic = MagicMock(name="ChatAnthropic")

        return {"langgraph": langgraph, "prebuilt": prebuilt, "langchain_anthropic": langchain_anthropic}

    def patch_create_react_agent(self) -> MagicMock:
        return self.patch("langgraph.prebuilt.create_react_agent", autospec=False)

    def patch_chat_anthropic(self) -> MagicMock:
        return self.patch("langchain_anthropic.ChatAnthropic", autospec=False)

    def mock_langgraph_graph(self, result: str = "Test response") -> MagicMock:
        """Return a LangGraph-like graph with invoke behavior."""
        graph = MagicMock(name="LangGraph")
        graph.invoke.return_value = {"messages": [types.SimpleNamespace(content=result)]}
        return graph

    def mock_strands(self) -> dict[str, types.ModuleType]:
        """Mock Strands modules imported by the package."""
        strands = self.mock_module("strands")
        strands.Agent = MagicMock(name="Agent")
        return {"strands": strands}

    def patch_strands_agent(self) -> MagicMock:
        return self.patch("strands.Agent", autospec=False)

    def mock_strands_agent(self, result: str = "Test response") -> MagicMock:
        """Return a callable Strands-like agent."""
        agent = MagicMock(name="StrandsAgent")
        agent.return_value = result
        return agent

    def patch_get_llm(self, return_value: Any | None = None) -> MagicMock:
        """Patch the shared LLM factory."""
        if return_value is None:
            return_value = MagicMock(name="LLM")
        return self.patch("vendor_fabric.agentic.config.llm.get_llm", return_value=return_value)


@pytest.fixture(autouse=True)
def mock_llm_env() -> Generator[None, Any, None]:
    """Set up test environment with mocked LLM credentials."""
    # Set dummy API keys for testing (will be mocked anyway)
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "sk-test-mock-key",
            "ANTHROPIC_API_KEY": "sk-ant-test-mock-key",
            "CREWAI_TESTING": "true",
        },
    ):
        yield


@pytest.fixture
def crew_mocker(mocker: MockerFixture) -> Generator[CrewMocker, None, None]:
    """Provide optional-framework mocks for runner tests."""
    helper = CrewMocker(mocker)
    try:
        yield helper
    finally:
        helper.restore_modules()


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with package structure."""
    # Create packages directory structure
    packages_dir = tmp_path / "packages"
    packages_dir.mkdir()

    # Create a mock otterfall package with .crewai structure
    otterfall_dir = packages_dir / "otterfall"
    otterfall_dir.mkdir()

    crewai_dir = otterfall_dir / ".crewai"
    crewai_dir.mkdir()

    # Create minimal manifest (dict format, not list)
    manifest = crewai_dir / "manifest.yaml"
    manifest.write_text("""
name: otterfall
description: Test package
crews:
  test_crew:
    description: A test crew
    agents: crews/test_crew/agents.yaml
    tasks: crews/test_crew/tasks.yaml
""")

    # Create crews directory
    crews_dir = crewai_dir / "crews" / "test_crew"
    crews_dir.mkdir(parents=True)

    # Create minimal agent and task configs
    (crews_dir / "agents.yaml").write_text("""
test_agent:
  role: Test Agent
  goal: Test goal
  backstory: Test backstory
""")

    (crews_dir / "tasks.yaml").write_text("""
test_task:
  description: Test task description
  expected_output: Test output
  agent: test_agent
""")

    return tmp_path


@pytest.fixture
def mock_crew() -> MagicMock:
    """Create a mock crew result."""
    result = MagicMock()
    result.raw = {"output": "test output", "success": True}
    return result
