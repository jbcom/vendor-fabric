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


def main() -> int:
    """Demonstrate Meshy AI 3D generation."""
    if not os.getenv("MESHY_API_KEY"):
        print("Error: MESHY_API_KEY environment variable is required.")
        print("Get an API key at https://meshy.ai")
        return 1

    from vendor_fabric.meshy import text3d

    prompt = "a medieval sword with ornate handle"
    print(f"Generating 3D model for prompt: '{prompt}'")

    try:
        # `generate` submits a preview task and polls until it completes.
        # Pass `wait=False` to get the task id back immediately and poll
        # yourself with `text3d.poll(task_id)`.
        result = text3d.generate(
            prompt=prompt,
            art_style="realistic",
            negative_prompt="blurry, low detail",
            target_polycount=15000,
            enable_pbr=True,
        )

        # text3d.generate returns an ExtendedDict when wait=True.
        status = result["status"]
        print(f"Final status: {status}")

        if status != "SUCCEEDED":
            error = result.get("error")
            print(f"Generation failed: {error}")
            return 1

        model_urls = result.get("model_urls") or {}
        print(f"GLB url: {model_urls.get('glb')}")
        print(f"OBJ url: {model_urls.get('obj')}")

        # Refine the preview to full quality using the task id.
        task_id = str(result["id"])
        print(f"Refining task {task_id} to full quality...")
        refined_id = text3d.refine(task_id)
        refined = text3d.poll(str(refined_id))
        refined_urls = refined.get("model_urls") or {}
        print(f"Refined GLB url: {refined_urls.get('glb')}")

    except Exception as e:
        print(f"Error during generation: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
