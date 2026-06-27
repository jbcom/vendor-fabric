"""Text-to-3D API.

Usage:
    from cloud_connectors.meshy import text3d

    result = text3d.generate("a medieval sword")
    print(result["model_urls"]["glb"])
"""

from __future__ import annotations

import time

from extended_data.containers import ExtendedDict, ExtendedString

from cloud_connectors.meshy import base
from cloud_connectors.meshy.models import ArtStyle, TaskStatus, Text3DRequest, Text3DResult


def create(request: Text3DRequest) -> ExtendedString:
    """Create text-to-3d task. Returns task_id."""
    response = base.request(
        "POST",
        "text-to-3d",
        version="v2",
        json=request.model_dump(exclude_none=True),
    )
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get task status."""
    response = base.request("GET", f"text-to-3d/{task_id}", version="v2")
    return base.task_payload_from_response(response, Text3DResult, "text-to-3d")


def refine(task_id: str) -> ExtendedString:
    """Refine preview to full quality. Returns new task_id."""
    response = base.request(
        "POST",
        f"text-to-3d/{task_id}/refine",
        version="v2",
        json={},
    )
    return base.task_id_from_response(response)


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


def generate(
    prompt: str,
    *,
    art_style: ArtStyle | str = ArtStyle.REALISTIC,
    negative_prompt: str = "",
    target_polycount: int = 15000,
    enable_pbr: bool = True,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Generate a 3D model from text.

    Args:
        prompt: Text description
        art_style: Style (realistic, sculpture, cartoon, low-poly)
        negative_prompt: Things to avoid
        target_polycount: Target polygon count
        enable_pbr: Enable PBR materials
        wait: Wait for completion (default True)

    Returns:
        Extended result payload if wait=True, extended task_id if wait=False.
    """
    if isinstance(art_style, str):
        art_style = ArtStyle(art_style)

    request = Text3DRequest(
        mode="preview",
        prompt=prompt,
        art_style=art_style,
        negative_prompt=negative_prompt,
        target_polycount=target_polycount,
        enable_pbr=enable_pbr,
    )

    task_id = create(request)

    if not wait:
        return task_id

    return poll(str(task_id))
