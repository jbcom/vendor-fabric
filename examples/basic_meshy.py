#!/usr/bin/env python3
"""Example: Meshy AI 3D Generation.

This example demonstrates how to use the Meshy connector for AI-powered
3D asset generation.

Requirements:
    pip install vendor-fabric[meshy]

Environment Variables:
    MESHY_API_KEY: Your Meshy API key (get one at https://meshy.ai)
"""

from __future__ import annotations

import os
import sys
import time


def main() -> int:
    """Demonstrate Meshy AI 3D generation."""
    # Check for required environment variables
    if not os.getenv("MESHY_API_KEY"):
        print("Error: MESHY_API_KEY environment variable is required.")
        print("Get an API key at https://meshy.ai")
        return 1

    # Import Meshy modules
    from vendor_fabric.meshy import text3d

    # Generate a simple 3D model
    prompt = "a medieval sword with ornate handle"
    print(f"Generating 3D model for prompt: '{prompt}'")

    try:
        # Start the generation (preview mode for faster results)
        result = text3d.generate(
            prompt=prompt,
            art_style="realistic",
            mode="preview",  # Use 'refine' for higher quality
        )
        print(f"Generation started with ID: {result.id}")

        # Poll for completion
        while result.status in ("PENDING", "IN_PROGRESS"):
            print(f"  Status: {result.status} - waiting...")
            time.sleep(5)
            result = text3d.get(result.id)

        if result.status == "SUCCEEDED":
            print(f"Generation succeeded! Result: {result}")
        elif hasattr(result, "task_error"):
            print(f"Generation failed with error: {result.task_error}")
        else:
            print(f"Generation ended with status: {result.status}")

    except Exception as e:
        print(f"Error during generation: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
