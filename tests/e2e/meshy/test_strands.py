"""E2E tests for Meshy tools with AWS Strands Agents.

Uses the StrandsRunner to abstract framework-specific code.
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
@pytest.mark.strands
class TestStrandsE2E:
    """Real E2E tests with AWS Strands Agents using runners."""

    @pytest.fixture
    def has_deps(self):
        """Check dependencies are available."""
        pytest.importorskip("strands")

    @pytest.fixture
    def has_api_keys(self, has_deps):
        """Check API keys are available."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY required")
        if not os.environ.get("MESHY_API_KEY"):
            pytest.skip("MESHY_API_KEY required")

    @pytest.fixture
    def runner(self, has_api_keys):
        """Create Strands runner."""
        from tests.e2e.meshy.runners import StrandsRunner

        return StrandsRunner()

    @pytest.mark.vcr
    @pytest.mark.timeout(600)  # 10 minutes - 3D generation takes time
    def test_strands_agent_generates_3d_model(self, runner, output_dir):
        """Test Strands agent generating a REAL 3D model end-to-end.

        This test:
        1. Uses StrandsRunner to create agent and invoke
        2. Generates a 3D axe model
        3. WAITS for completion
        4. Downloads and saves the GLB file
        5. Verifies the GLB file exists and has content
        """
        result = runner.generate_3d_model(
            prompt="a medieval battle axe with wooden handle and steel blade",
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
    def test_strands_agent_lists_animations(self, has_api_keys):
        """Test Strands agent listing animations."""
        from strands import Agent

        from cloud_connectors.meshy.tools import list_animations

        agent = Agent(
            system_prompt="You help users find animations. Use list_animations to search the catalog.",
            tools=[list_animations],
        )

        result = agent("List fighting animations using list_animations with category='Fighting'.")

        result_str = str(result)
        assert "animation" in result_str.lower() or "fight" in result_str.lower()


@pytest.mark.e2e
@pytest.mark.strands
class TestStrandsWithBedrock:
    """E2E tests with Strands using AWS Bedrock."""

    @pytest.fixture
    def has_bedrock(self):
        """Check Bedrock credentials are available."""
        if not (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE")):
            pytest.skip("AWS credentials required for Bedrock")
        if not os.environ.get("MESHY_API_KEY"):
            pytest.skip("MESHY_API_KEY required")

    @pytest.fixture
    def has_strands(self):
        """Check Strands is installed."""
        pytest.importorskip("strands")

    @pytest.mark.vcr
    @pytest.mark.timeout(600)
    def test_strands_bedrock_generates_model(self, has_bedrock, has_strands, output_dir):
        """Test Strands with Bedrock model generating a 3D model."""
        from strands import Agent
        from strands.models import BedrockModel

        from cloud_connectors.meshy.tools import text3d_generate

        # Use Claude via Bedrock
        model = BedrockModel(model_id="anthropic.claude-3-haiku-20240307-v1:0")

        agent = Agent(
            model=model,
            system_prompt="You are a 3D asset generator. Use text3d_generate to create models.",
            tools=[text3d_generate],
        )

        result = agent("Generate a 3D wooden sword using text3d_generate with art_style='realistic'.")

        result_str = str(result)
        assert "task" in result_str.lower() or "model" in result_str.lower()
