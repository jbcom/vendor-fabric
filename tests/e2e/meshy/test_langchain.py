"""E2E tests for Meshy tools with LangChain/LangGraph.

Uses the LangChainRunner to abstract framework-specific code.
"""

from __future__ import annotations

import os

from pathlib import Path

import pytest


@pytest.fixture
def output_dir() -> Path:
    """Output directory for generated models - committed to repository.

    Path: tests/e2e/meshy/fixtures/models/
    Each connector has its own fixtures directory.
    """
    path = Path(__file__).parent / "fixtures" / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.e2e
@pytest.mark.langchain
class TestLangChainE2E:
    """Real E2E tests with LangChain/LangGraph using runners."""

    @pytest.fixture
    def has_deps(self):
        """Check dependencies are available."""
        pytest.importorskip("langchain_anthropic")
        pytest.importorskip("langgraph")

    @pytest.fixture
    def has_api_keys(self, has_deps):
        """Check API keys are available."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY required")
        if not os.environ.get("MESHY_API_KEY"):
            pytest.skip("MESHY_API_KEY required")

    @pytest.fixture
    def runner(self, has_api_keys):
        """Create LangChain runner."""
        from tests.e2e.meshy.runners import LangChainRunner

        return LangChainRunner()

    @pytest.mark.vcr
    @pytest.mark.timeout(600)  # 10 minutes - 3D generation takes time
    def test_langchain_agent_generates_3d_model(self, runner, output_dir):
        """Test LangChain agent generating a REAL 3D model end-to-end.

        This test:
        1. Uses LangChainRunner to create agent and invoke
        2. Generates a 3D sword model
        3. WAITS for completion
        4. Downloads and saves the GLB file
        5. Verifies the GLB file exists and has content
        """
        result = runner.generate_3d_model(
            prompt="a simple wooden sword with a carved handle",
            art_style="realistic",
            output_dir=output_dir,
        )

        # Verify we got a model URL
        assert result.model_url, f"Should have model_url. Result: {result}"

        # Verify the GLB was downloaded and saved
        assert result.glb_path, "Should have glb_path"
        assert result.glb_path.exists(), f"GLB file should exist at {result.glb_path}"
        assert result.file_size > 1000, "GLB file should be at least 1KB (real model)"

    @pytest.mark.vcr
    @pytest.mark.timeout(60)
    def test_langchain_agent_lists_animations(self, has_api_keys):
        """Test agent listing available animations."""
        from langchain_anthropic import ChatAnthropic
        from langgraph.prebuilt import create_react_agent

        from cloud_connectors.meshy.tools import get_langchain_tools

        llm = ChatAnthropic(model="claude-haiku-4-5-20251001")
        tools = get_langchain_tools()
        agent = create_react_agent(llm, tools)

        result = agent.invoke(
            {"messages": [("user", "List available animations using list_animations. Show me fighting animations.")]}
        )

        messages = result["messages"]
        final_content = str(messages[-1].content) if hasattr(messages[-1], "content") else str(messages[-1])

        # Should mention animations
        assert "animation" in final_content.lower() or "fight" in final_content.lower()
