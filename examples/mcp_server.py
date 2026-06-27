#!/usr/bin/env python3
"""Example: Running the Meshy MCP Server.

This example demonstrates how to run the Model Context Protocol (MCP)
server for Meshy AI, enabling integration with Claude Desktop and
other MCP-compatible clients.

Requirements:
    pip install vendor-fabric[meshy,mcp]

Environment Variables:
    MESHY_API_KEY: Your Meshy API key

Usage:
    # Run the server (connects via stdio)
    python examples/connectors/mcp_server.py

    # Or use the installed command
    meshy-mcp

    # Configure in Claude Desktop's config.json:
    {
        "mcpServers": {
            "meshy": {
                "command": "meshy-mcp",
                "env": {
                    "MESHY_API_KEY": "<your-key-here>"
                }
            }
        }
    }
"""

from __future__ import annotations

import os
import sys

from vendor_fabric import ConnectorFabric
from vendor_fabric._optional import require_extra


def main() -> int:
    """Run the Meshy MCP server."""
    # Check for required environment variables
    if not os.getenv("MESHY_API_KEY"):
        print("Error: MESHY_API_KEY environment variable is required.")
        return 1

    meshy_info = ConnectorFabric().get_connector_info("meshy")
    if not meshy_info["available"]:
        print(f"Error: Meshy connector is unavailable. Install with: {meshy_info['install']}")
        return 1

    try:
        require_extra("mcp", "mcp")
        from vendor_fabric.meshy.mcp import run_server
    except ImportError as exc:
        print(f"Error: {exc}")
        print("Install with: pip install vendor-fabric[meshy,mcp]")
        return 1

    print("Starting Meshy MCP server...")
    try:
        # Run the server (blocks until stopped)
        run_server()
    except KeyboardInterrupt:
        pass

    print("\nMCP server stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
