"""Rigging API - add skeletons to models.

Usage:
    from cloud_connectors.meshy import rigging

    result = rigging.rig(model_task_id)
"""

from __future__ import annotations

import time

from extended_data.containers import ExtendedDict, ExtendedString

from cloud_connectors.meshy import base
from cloud_connectors.meshy.models import RiggingRequest, RiggingResult, TaskStatus


def create(request: RiggingRequest) -> ExtendedString:
    """Create rigging task. Returns task_id."""
    response = base.request(
        "POST",
        "rigging",
        version="v1",
        json=request.model_dump(exclude_none=True),
    )
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get task status."""
    response = base.request("GET", f"rigging/{task_id}", version="v1")
    return base.task_payload_from_response(response, RiggingResult, "rigging")


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


def rig(
    model_task_id: str,
    *,
    height_meters: float = 1.7,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Rig a model for animation.

    Args:
        model_task_id: Task ID of model to rig
        height_meters: Character height (affects bone scaling)
        wait: Wait for completion (default True)

    Returns:
        Extended result payload if wait=True, extended task_id if wait=False.
    """
    request = RiggingRequest(
        input_task_id=model_task_id,
        height_meters=height_meters,
    )

    task_id = create(request)

    if not wait:
        return task_id

    return poll(str(task_id))


def rig_from_url(
    model_url: str,
    *,
    height_meters: float = 1.7,
    texture_url: str | None = None,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Rig a model from URL.

    Args:
        model_url: URL to GLB model
        height_meters: Character height
        texture_url: Optional texture image URL
        wait: Wait for completion (default True)

    Returns:
        Extended result payload if wait=True, extended task_id if wait=False.
    """
    request = RiggingRequest(
        model_url=model_url,
        height_meters=height_meters,
        texture_image_url=texture_url,
    )

    task_id = create(request)

    if not wait:
        return task_id

    return poll(str(task_id))
