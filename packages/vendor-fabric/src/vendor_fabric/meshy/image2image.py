"""Image-to-image API."""

from __future__ import annotations

import time

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy import base
from vendor_fabric.meshy.models import Image2ImageRequest, Image2ImageResult, TaskStatus


ENDPOINT = "image-to-image"


def create(request: Image2ImageRequest) -> ExtendedString:
    """Create an image-to-image task and return its task ID."""
    response = base.request("POST", ENDPOINT, version="v1", json=request.model_dump(exclude_none=True))
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get an image-to-image task."""
    response = base.request("GET", f"{ENDPOINT}/{task_id}", version="v1")
    return base.task_payload_from_response(response, Image2ImageResult, ENDPOINT)


def delete(task_id: str) -> None:
    """Permanently delete an image-to-image task."""
    base.request("DELETE", f"{ENDPOINT}/{task_id}", version="v1")


def list_tasks(*, page_num: int = 1, page_size: int = 10, sort_by: str = "-created_at") -> ExtendedList[ExtendedDict]:
    """List image-to-image tasks."""
    response = base.request(
        "GET", ENDPOINT, version="v1", params={"page_num": page_num, "page_size": page_size, "sort_by": sort_by}
    )
    return base.task_list_from_response(response, Image2ImageResult, ENDPOINT)


def poll(task_id: str, interval: float = 5.0, timeout: float = 600.0) -> ExtendedDict:
    """Poll until the image-to-image task reaches a terminal state."""
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
    prompt: str,
    reference_image_urls: list[str],
    *,
    ai_model: str = "nano-banana",
    aspect_ratio: str | None = None,
    generate_multi_view: bool = False,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Edit reference images from a text prompt."""
    task_id = create(
        Image2ImageRequest(
            ai_model=ai_model,
            prompt=prompt,
            reference_image_urls=reference_image_urls,
            generate_multi_view=generate_multi_view,
            aspect_ratio=aspect_ratio,
        )
    )
    if not wait:
        return task_id
    return poll(str(task_id))
