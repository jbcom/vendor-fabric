"""Image-to-3D API.

Usage:
    from vendor_fabric.meshy import image3d

    result = image3d.generate("https://example.com/image.png")
    print(result["model_urls"]["glb"])
"""

from __future__ import annotations

import time

from extended_data.containers import ExtendedDict, ExtendedString

from vendor_fabric.meshy import base
from vendor_fabric.meshy.models import Image3DRequest, Image3DResult, TaskStatus


def create(request: Image3DRequest) -> ExtendedString:
    """Create image-to-3d task. Returns task_id."""
    response = base.request(
        "POST",
        "image-to-3d",
        version="v2",
        json=request.model_dump(exclude_none=True),
    )
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get task status."""
    response = base.request("GET", f"image-to-3d/{task_id}", version="v2")
    return base.task_payload_from_response(response, Image3DResult, "image-to-3d")


def refine(task_id: str) -> ExtendedString:
    """Refine preview to full quality. Returns new task_id."""
    response = base.request(
        "POST",
        f"image-to-3d/{task_id}/refine",
        version="v2",
        json={},
    )
    return base.task_id_from_response(response)


def poll(task_id: str, interval: float = 5.0, timeout: float = 600.0) -> ExtendedDict:
    """Polls the status of an image-to-3D task until it completes, fails, expires, or times out.

    Args:
        task_id: The ID of the image-to-3D task to poll.
        interval: Time in seconds between polling attempts (default: 5.0).
        timeout: Maximum time in seconds to wait for task completion (default: 600.0).

    Returns:
        Extended payload for the completed task.

    Raises:
        RuntimeError: If the task fails or expires.
        TimeoutError: If the polling times out before the task completes.
    """
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


def generate(
    image_url: str,
    *,
    topology: str | None = None,
    target_polycount: int | None = None,
    enable_pbr: bool = True,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Generate a 3D model from an image.

    Args:
        image_url: URL to the source image
        topology: Mesh topology ("quad" or "triangle")
        target_polycount: Target polygon count
        enable_pbr: Enable PBR materials
        wait: Wait for completion (default True)

    Returns:
        Extended result payload if wait=True, extended task_id if wait=False.
    """
    request = Image3DRequest(
        mode="preview",
        image_url=image_url,
        topology=topology,
        target_polycount=target_polycount,
        enable_pbr=enable_pbr,
    )

    task_id = create(request)

    if not wait:
        return task_id

    return poll(str(task_id))
