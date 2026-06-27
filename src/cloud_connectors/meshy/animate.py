"""Animation API - apply animations to rigged models.

Usage:
    from cloud_connectors.meshy import animate
    from cloud_connectors.meshy.animations import ANIMATIONS

    result = animate.apply(rigged_task_id, animation_id=0)

    # Browse animations
    for anim in ANIMATIONS.values():
        print(f"{anim.id}: {anim.name}")
"""

from __future__ import annotations

import time

from extended_data.containers import ExtendedDict, ExtendedString

from cloud_connectors.meshy import base
from cloud_connectors.meshy.models import AnimationRequest, AnimationResult, TaskStatus


def create(request: AnimationRequest) -> ExtendedString:
    """Create animation task. Returns task_id."""
    response = base.request(
        "POST",
        "animations",
        version="v1",
        json=request.model_dump(exclude_none=True),
    )
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get task status."""
    response = base.request("GET", f"animations/{task_id}", version="v1")
    return base.task_payload_from_response(response, AnimationResult, "animations")


def poll(task_id: str, interval: float = 5.0, timeout: float = 600.0) -> ExtendedDict:
    """Poll until complete or failed."""
    start = time.time()
    while True:
        result = get(task_id)
        status = result.get("status")
        if status == TaskStatus.SUCCEEDED:
            return result
        if status == TaskStatus.FAILED:
            error = result.get("task_error") or result.get("error")
            raise RuntimeError(base.task_failure_message(error))
        if status == TaskStatus.EXPIRED:
            msg = "Task expired"
            raise RuntimeError(msg)
        if time.time() - start > timeout:
            msg = f"Task timed out after {timeout}s"
            raise TimeoutError(msg)
        time.sleep(interval)


def apply(
    rigged_task_id: str,
    animation_id: int,
    *,
    loop: bool = True,
    frame_rate: int = 30,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Apply animation to a rigged model.

    Args:
        rigged_task_id: Task ID of rigged model
        animation_id: Animation ID (0-677, see animations.ANIMATIONS)
        loop: Whether animation loops
        frame_rate: Animation frame rate
        wait: Wait for completion (default True)

    Returns:
        Extended result payload if wait=True, extended task_id if wait=False.
    """
    request = AnimationRequest(
        rig_task_id=rigged_task_id,
        action_id=animation_id,
        loop=loop,
        frame_rate=frame_rate,
    )

    task_id = create(request)

    if not wait:
        return task_id

    return poll(str(task_id))
