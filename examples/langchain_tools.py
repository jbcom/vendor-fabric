#!/usr/bin/env python3
"""Example: Using Meshy Tools with LangChain Agents.

This example demonstrates how to use Meshy AI tools with LangChain
to create an AI agent capable of generating 3D assets.

Requirements:
    pip install vendor-fabric[meshy,langchain]
    pip install langchain-anthropic langgraph  # For Claude as the LLM and agent loop

Environment Variables:
    MESHY_API_KEY: Your Meshy API key
    ANTHROPIC_API_KEY: Your Anthropic API key (for Claude)
"""

from __future__ import annotations

import os
import sys

from vendor_fabric import ConnectorFabric
from vendor_fabric._optional import require_extra
from vendor_fabric.meshy.tools import get_tools


def main() -> int:
    """Demonstrate LangChain integration with Meshy tools."""
    # Check for required environment variables
    missing = []
    if not os.getenv("MESHY_API_KEY"):
        missing.append("MESHY_API_KEY")
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        return 1

    meshy_info = ConnectorFabric().get_connector_info("meshy")
    if not meshy_info["available"]:
        print(f"Error: Meshy connector is unavailable. Install with: {meshy_info['install']}")
        return 1

    try:
        require_extra("langchain_core", "langchain")
        langchain_anthropic = require_extra("langchain_anthropic", "langchain")
        langgraph_prebuilt = require_extra("langgraph.prebuilt", "langchain")
    except ImportError as exc:
        print(f"Error: {exc}")
        print("Install with: pip install vendor-fabric[meshy,langchain] langchain-anthropic langgraph")
        return 1

    # Get Meshy tools for LangChain
    tools = get_tools()
    print(f"Loaded {len(tools)} Meshy tools for LangChain.")

    # Create the LLM
    llm = langchain_anthropic.ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)

    # Create the agent
    agent = langgraph_prebuilt.create_react_agent(llm, tools)

    # Run a query
    query = "Generate a 3D model of a red sports car in preview mode"
    print(f"\nSending query: '{query}'")

    try:
        result = agent.invoke({"messages": [("user", query)]})

        # Print the response
        for message in result["messages"]:
            if hasattr(message, "content") and message.content:
                role = message.__class__.__name__.replace("Message", "")
                if len(message.content) > 500:
                    print(f"\n[{role}] {message.content[:500]}... (truncated)")
                else:
                    print(f"\n[{role}] {message.content}")

    except Exception as e:
        print(f"Error running agent: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
