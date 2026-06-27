"""Loader module - creates CrewAI Crew objects from YAML configurations.

Note: This module imports CrewAI lazily to allow the core package to be
installed without requiring CrewAI. For framework-agnostic usage, prefer
using the decomposer module with runners instead.
"""

from __future__ import annotations

import logging

from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from crewai import Agent, Crew, Task

from vendor_fabric.agentic.tools.registry import resolve_tools


logger = logging.getLogger(__name__)


def load_knowledge_sources(knowledge_paths: list[Path]) -> list:
    """Load knowledge sources from the specified paths.

    Args:
        knowledge_paths: List of paths to knowledge directories.

    Returns:
        List of TextFileKnowledgeSource objects.

    Raises:
        ImportError: If crewai is not installed.
    """
    from crewai.knowledge.source.text_file_knowledge_source import TextFileKnowledgeSource

    sources = []

    for knowledge_path in knowledge_paths:
        if not knowledge_path.exists():
            continue

        # Load .md and .ts files
        for ext in ["*.md", "*.ts", "*.tsx", "*.py"]:
            for file_path in knowledge_path.rglob(ext):
                try:
                    # Read file content directly
                    content = file_path.read_text(encoding="utf-8")
                    if content.strip():
                        sources.append(
                            TextFileKnowledgeSource(
                                file_paths=[str(file_path)],
                            )
                        )
                except (OSError, ValueError):
                    logger.warning("Could not load knowledge source %s", file_path, exc_info=True)

    return sources


def create_agent_from_config(
    agent_name: str,
    agent_config: dict,
    tools: list | None = None,
) -> Agent:
    """Create an Agent from YAML configuration.

    Args:
        agent_name: Name/key of the agent.
        agent_config: Agent configuration dict with role, goal, backstory.
        tools: Optional list of tools to give the agent.

    Returns:
        Configured Agent instance.

    Raises:
        ImportError: If crewai is not installed.
    """
    from crewai import Agent

    from vendor_fabric.agentic.config.llm import get_llm

    return Agent(
        role=agent_config.get("role", agent_name),
        goal=agent_config.get("goal", ""),
        backstory=agent_config.get("backstory", ""),
        llm=get_llm(),
        tools=tools or [],
        allow_delegation=agent_config.get("allow_delegation", False),
        verbose=True,
    )


def create_task_from_config(
    task_name: str,
    task_config: dict,
    agent: Agent,
) -> Task:
    """Create a Task from YAML configuration.

    Args:
        task_name: Name/key of the task.
        task_config: Task configuration dict with description, expected_output.
        agent: Agent to assign to this task.

    Returns:
        Configured Task instance.

    Raises:
        ImportError: If crewai is not installed.
    """
    from crewai import Task

    return Task(
        description=task_config.get("description", ""),
        expected_output=task_config.get("expected_output", ""),
        agent=agent,
    )


def load_crew_from_config(crew_config: dict) -> Crew:
    """Load a complete Crew from configuration.

    Args:
        crew_config: Configuration dict from get_crew_config().

    Returns:
        Configured Crew instance ready to kickoff.

    Raises:
        ImportError: If crewai is not installed.
    """
    from crewai import Crew, Process

    from vendor_fabric.agentic.tools.file_tools import (
        DirectoryListTool,
        GameCodeReaderTool,
        GameCodeWriterTool,
    )

    # Initialize tools
    code_writer = GameCodeWriterTool()
    code_reader = GameCodeReaderTool()
    dir_lister = DirectoryListTool()
    all_tools = [code_writer, code_reader, dir_lister]
    read_tools = [code_reader, dir_lister]

    # Create agents
    agents_config = crew_config.get("agents", {})
    agents: dict[str, Any] = {}

    for agent_name, agent_cfg in agents_config.items():
        resolved_tools = resolve_tools(agent_cfg.get("tools", []))

        # Preserve the older role-based fallback when no concrete tool could be resolved.
        if resolved_tools:
            tools = resolved_tools
        else:
            tools = all_tools if "engineer" in agent_name.lower() or "developer" in agent_name.lower() else read_tools

        agents[agent_name] = create_agent_from_config(agent_name, agent_cfg, tools)

    # Create tasks
    tasks_config = crew_config.get("tasks", {})
    tasks = []

    for task_name, task_cfg in tasks_config.items():
        # Find the agent for this task
        agent_name = task_cfg.get("agent")
        if not agent_name:
            raise ValueError(f"Task '{task_name}' is missing an 'agent' assignment.")

        agent = agents.get(agent_name)
        if not agent:
            raise ValueError(
                f"Agent '{agent_name}' for task '{task_name}' not found. Available agents: {list(agents.keys())}"
            )

        tasks.append(create_task_from_config(task_name, task_cfg, agent))

    # Load knowledge sources
    knowledge_sources = load_knowledge_sources(crew_config.get("knowledge_paths", []))

    # Create and return the crew
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        planning=True,
        memory=True,
        knowledge_sources=knowledge_sources or None,
        verbose=True,
    )
