"""Multi-image-to-3D API."""

from __future__ import annotations

import time

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy import base
from vendor_fabric.meshy.models import MultiImage3DRequest, MultiImage3DResult, TaskStatus


ENDPOINT = "multi-image-to-3d"


def create(request: MultiImage3DRequest) -> ExtendedString:
    """Create a multi-image-to-3D task and return its task ID."""
    response = base.request("POST", ENDPOINT, version="v1", json=request.model_dump(exclude_none=True))
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get a multi-image-to-3D task."""
    response = base.request("GET", f"{ENDPOINT}/{task_id}", version="v1")
    return base.task_payload_from_response(response, MultiImage3DResult, ENDPOINT)


def delete(task_id: str) -> None:
    """Permanently delete a multi-image-to-3D task."""
    base.request("DELETE", f"{ENDPOINT}/{task_id}", version="v1")


def list_tasks(*, page_num: int = 1, page_size: int = 10, sort_by: str = "-created_at") -> ExtendedList[ExtendedDict]:
    """List multi-image-to-3D tasks."""
    response = base.request(
        "GET", ENDPOINT, version="v1", params={"page_num": page_num, "page_size": page_size, "sort_by": sort_by}
    )
    return base.task_list_from_response(response, MultiImage3DResult, ENDPOINT)


def poll(task_id: str, interval: float = 5.0, timeout: float = 600.0) -> ExtendedDict:
    """Poll until the multi-image-to-3D task reaches a terminal state."""
    start = time.time()
    while True:
        result = get(task_id)
        status = result.get("status")
        if status == TaskStatus.SUCCEEDED:
            return result
        if status == TaskStatus.FAILED:
            raise RuntimeError(base.task_failure_message(result.get("task_error") or result.get("error")))
        if status in {TaskStatus.CANCELED, TaskStatus.EXPIRED}:
            raise RuntimeError(f"Task {str(status).title()}")
        if time.time() - start > timeout:
            raise TimeoutError(f"Task timed out after {timeout}s")
        time.sleep(interval)


def generate(
    image_urls: list[str],
    *,
    ai_model: str = "latest",
    should_texture: bool = True,
    enable_pbr: bool = False,
    target_formats: list[str] | None = None,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Generate a 3D model from one to four views of the same subject."""
    task_id = create(
        MultiImage3DRequest(
            image_urls=image_urls,
            ai_model=ai_model,
            should_texture=should_texture,
            enable_pbr=enable_pbr,
            target_formats=target_formats,
        )
    )
    if not wait:
        return task_id
    return poll(str(task_id))
