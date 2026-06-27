"""Live Meshy provider E2E tests.

These tests validate provider behavior directly. Agent runtime execution
belongs in agentic-fabric.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.timeout(120)
def test_meshy_text3d_submit_returns_task_id(require_meshy_api_key: str) -> None:
    """A live Meshy text-to-3D submission should return a task id."""
    from vendor_fabric.meshy import base, text3d

    base.configure(api_key=require_meshy_api_key)
    try:
        task_id = text3d.generate(
            "a tiny plain cube for a vendor-fabric provider smoke test",
            target_polycount=10000,
            wait=False,
        )
    finally:
        base.close()

    assert str(task_id).strip()
