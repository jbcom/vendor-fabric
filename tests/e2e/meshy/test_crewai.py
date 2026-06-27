"""E2E tests for Meshy tools with CrewAI.

Uses the CrewAIRunner to abstract framework-specific code.
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
@pytest.mark.crewai
class TestCrewAIE2E:
    """Real E2E tests with CrewAI using runners."""

    @pytest.fixture
    def has_deps(self):
        """Check dependencies are available."""
        pytest.importorskip("crewai")

    @pytest.fixture
    def has_api_keys(self, has_deps):
        """Check API keys are available."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY required")
        if not os.environ.get("MESHY_API_KEY"):
            pytest.skip("MESHY_API_KEY required")

    @pytest.fixture
    def runner(self, has_api_keys):
        """Create CrewAI runner."""
        from tests.e2e.meshy.runners import CrewAIRunner

        return CrewAIRunner()

    @pytest.mark.vcr
    @pytest.mark.timeout(600)  # 10 minutes - 3D generation takes time
    def test_crewai_agent_generates_3d_model(self, runner, output_dir):
        """Test CrewAI agent generating a REAL 3D model end-to-end.

        This test:
        1. Uses CrewAIRunner to create agent and invoke
        2. Generates a 3D shield model
        3. WAITS for completion
        4. Downloads and saves the GLB file
        5. Verifies the GLB file exists and has content
        """
        result = runner.generate_3d_model(
            prompt="a wooden medieval shield with metal reinforcements",
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
    def test_crewai_agent_lists_animations(self, has_api_keys):
        """Test CrewAI agent listing animations."""
        from crewai import Agent, Crew, Task

        from cloud_connectors.meshy.tools import get_crewai_tools

        # Get native CrewAI tools directly
        crewai_tools = get_crewai_tools()

        # Filter to just list_animations
        list_anim_tool = next(t for t in crewai_tools if "list_animations" in str(t))

        agent = Agent(
            role="Animation Researcher",
            goal="Find available animations in the Meshy catalog",
            backstory="An AI that researches animation options.",
            tools=[list_anim_tool],
            llm="anthropic/claude-haiku-4-5-20251001",
            verbose=True,
        )

        task = Task(
            description="List available fighting animations using list_animations with category='Fighting'.",
            agent=agent,
            expected_output="A list of fighting animations with their IDs and names",
        )

        crew = Crew(agents=[agent], tasks=[task], verbose=True)
        result = crew.kickoff()

        result_str = str(result)
        assert "animation" in result_str.lower() or "fight" in result_str.lower()
