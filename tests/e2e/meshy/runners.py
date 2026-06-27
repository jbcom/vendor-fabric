"""Reusable test runners for Meshy E2E tests.

These runners abstract away framework-specific agent creation and provide
a consistent interface for testing across LangChain, CrewAI, and Strands.

Usage:
    from tests.e2e.meshy.runners import LangChainRunner, CrewAIRunner, StrandsRunner

    runner = LangChainRunner()
    result = runner.generate_3d_model(
        prompt="a wooden sword",
        art_style="realistic",
        output_dir=Path("tests/e2e/meshy/fixtures/models"),
    )
    assert result.glb_path.exists()
"""

from __future__ import annotations

import json
import re

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GenerationResult:
    """Result from a 3D model generation test."""

    task_id: str | None
    model_url: str | None
    glb_path: Path | None
    file_size: int
    raw_result: Any


class BaseRunner(ABC):
    """Base class for E2E test runners."""

    framework_name: str = "base"

    @abstractmethod
    def create_agent(self, tools: list) -> Any:
        """Create an agent with the given tools."""

    @abstractmethod
    def invoke_agent(self, agent: Any, prompt: str) -> Any:
        """Invoke the agent with a prompt."""

    @abstractmethod
    def extract_result(self, raw_result: Any) -> dict[str, Any]:
        """Extract task_id and model_url from the raw result."""

    @abstractmethod
    def get_native_tools(self) -> list:
        """Get tools in the native format for this framework."""

    def generate_3d_model(
        self,
        prompt: str,
        art_style: str = "realistic",
        output_dir: Path | None = None,
        output_filename: str | None = None,
    ) -> GenerationResult:
        """Generate a 3D model end-to-end.

        This method:
        1. Creates an agent with Meshy tools (native format)
        2. Invokes the agent to generate a 3D model
        3. Waits for completion
        4. Downloads and saves the GLB file
        5. Returns the result with verification

        Args:
            prompt: Description of the 3D model to generate
            art_style: Art style (realistic or sculpture)
            output_dir: Directory to save the GLB file
            output_filename: Optional filename (default: {framework}_{prompt_slug}_{task_id}.glb)

        Returns:
            GenerationResult with paths and metadata
        """
        from cloud_connectors.meshy import base

        # Get tools in native format and create agent
        tools = self.get_native_tools()
        agent = self.create_agent(tools)

        # Build the prompt for the agent
        agent_prompt = f"Generate a 3D model using text3d_generate. Use prompt='{prompt}' and art_style='{art_style}'."

        # Invoke agent - this waits for completion
        raw_result = self.invoke_agent(agent, agent_prompt)

        # Extract model_url and task_id
        extracted = self.extract_result(raw_result)
        model_url = extracted.get("model_url")
        task_id = extracted.get("task_id")

        # Download GLB if we have a URL and output_dir
        glb_path = None
        file_size = 0

        if model_url and output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

            if output_filename:
                filename = output_filename
            else:
                # Create filename from framework, prompt, and task_id
                prompt_slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower())[:20]
                filename = f"{self.framework_name}_{prompt_slug}_{task_id or 'unknown'}.glb"

            glb_path = output_dir / filename
            file_size = base.download(model_url, str(glb_path))

        return GenerationResult(
            task_id=task_id,
            model_url=model_url,
            glb_path=glb_path,
            file_size=file_size,
            raw_result=raw_result,
        )

    def _extract_from_string(self, text: str) -> dict[str, Any]:
        """Extract model_url and task_id from a string."""
        result = {}

        # Try to find GLB URL (including query params for signed URLs)
        # Match URLs that end with .glb or have .glb followed by query params
        url_match = re.search(r'https://[^\s"\'<>]+\.glb(?:\?[^\s"\'<>]+)?', text)
        if url_match:
            result["model_url"] = url_match.group(0)

        # Try to find task_id
        task_match = re.search(r'task_id["\s:]+([a-f0-9-]+)', text, re.IGNORECASE)
        if task_match:
            result["task_id"] = task_match.group(1)

        # Try JSON parsing
        if "model_url" not in result:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    result["model_url"] = data.get("model_url") or result.get("model_url")
                    result["task_id"] = data.get("task_id") or result.get("task_id")
            except (json.JSONDecodeError, TypeError):
                pass

        return result


class LangChainRunner(BaseRunner):
    """Runner for LangChain/LangGraph agents."""

    framework_name = "langchain"

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model

    def get_native_tools(self) -> list:
        """Get tools as LangChain StructuredTools."""
        from cloud_connectors.meshy.tools import get_langchain_tools

        return get_langchain_tools()

    def create_agent(self, tools: list) -> Any:
        """Create a LangGraph ReAct agent."""
        from langchain_anthropic import ChatAnthropic
        from langgraph.prebuilt import create_react_agent

        llm = ChatAnthropic(model=self.model)
        return create_react_agent(llm, tools)

    def invoke_agent(self, agent: Any, prompt: str) -> Any:
        """Invoke the LangGraph agent."""
        return agent.invoke({"messages": [("user", prompt)]})

    def extract_result(self, raw_result: Any) -> dict[str, Any]:
        """Extract from LangGraph result."""
        result = {}
        messages = raw_result.get("messages", [])

        # Look through tool messages for the result
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "tool":
                content = msg.content if hasattr(msg, "content") else str(msg)
                extracted = self._extract_from_string(str(content))
                result.update(extracted)

        # Also check the final message
        if messages:
            final = messages[-1]
            content = final.content if hasattr(final, "content") else str(final)
            extracted = self._extract_from_string(str(content))
            if "model_url" not in result:
                result.update(extracted)

        return result


class CrewAIRunner(BaseRunner):
    """Runner for CrewAI agents."""

    framework_name = "crewai"

    def __init__(self, model: str = "anthropic/claude-haiku-4-5-20251001"):
        self.model = model

    def get_native_tools(self) -> list:
        """Get tools as native CrewAI tools."""
        from cloud_connectors.meshy.tools import get_crewai_tools

        return get_crewai_tools()

    def create_agent(self, tools: list) -> Any:
        """Create a CrewAI agent with tools (already in native format)."""
        from crewai import Agent

        return Agent(
            role="3D Artist",
            goal="Generate 3D models using Meshy AI tools",
            backstory="An AI assistant that creates 3D game assets using Meshy AI.",
            tools=tools,  # Already native CrewAI tools
            llm=self.model,
            verbose=True,
        )

    def invoke_agent(self, agent: Any, prompt: str) -> Any:
        """Invoke the CrewAI agent via a Crew."""
        from crewai import Crew, Task

        task = Task(
            description=prompt + " Return the full result including task_id and model_url.",
            agent=agent,
            expected_output="A dictionary containing task_id, status, and model_url from Meshy AI",
        )

        crew = Crew(agents=[agent], tasks=[task], verbose=True)
        return crew.kickoff()

    def extract_result(self, raw_result: Any) -> dict[str, Any]:
        """Extract from CrewAI result."""
        return self._extract_from_string(str(raw_result))


class StrandsRunner(BaseRunner):
    """Runner for AWS Strands agents."""

    framework_name = "strands"

    def get_native_tools(self) -> list:
        """Get tools as plain Python functions for Strands."""
        from cloud_connectors.meshy.tools import get_strands_tools

        return get_strands_tools()

    def create_agent(self, tools: list) -> Any:
        """Create a Strands agent with tool functions."""
        from strands import Agent

        return Agent(
            system_prompt=(
                "You are a 3D asset generator. Use the tools to create 3D models. "
                "Always return the full result including task_id and model_url."
            ),
            tools=tools,  # Plain Python functions
        )

    def invoke_agent(self, agent: Any, prompt: str) -> Any:
        """Invoke the Strands agent."""
        return agent(prompt)

    def extract_result(self, raw_result: Any) -> dict[str, Any]:
        """Extract from Strands result."""
        return self._extract_from_string(str(raw_result))
