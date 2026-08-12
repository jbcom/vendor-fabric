"""Text-to-image API.

Usage:
    from vendor_fabric.meshy import text2image

    result = text2image.generate("hand-painted forest shrine")
    text2image.download_first(result, "art/forest-shrine.png")
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import httpx

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy import base
from vendor_fabric.meshy.models import Text2ImageRequest, Text2ImageResult


Requester = Callable[..., httpx.Response]


def create(request: Text2ImageRequest, *, requester: Requester | None = None) -> ExtendedString:
    """Create a text-to-image task and return its task ID."""
    response = (requester or base.request)(
        "POST",
        "text-to-image",
        version="v1",
        json=request.model_dump(exclude_none=True),
    )
    return base.task_id_from_response(response)


def get(task_id: str, *, requester: Requester | None = None) -> ExtendedDict:
    """Get a text-to-image task."""
    response = (requester or base.request)("GET", f"text-to-image/{task_id}", version="v1")
    return base.task_payload_from_response(response, Text2ImageResult, "text-to-image")


def delete(task_id: str) -> None:
    """Permanently delete a text-to-image task and its generated images."""
    base.request("DELETE", f"text-to-image/{task_id}", version="v1")


def list_tasks(
    *,
    page_num: int = 1,
    page_size: int = 10,
    sort_by: str = "-created_at",
) -> ExtendedList[ExtendedDict]:
    """List text-to-image tasks using Meshy's pagination contract."""
    response = base.request(
        "GET",
        "text-to-image",
        version="v1",
        params={"page_num": page_num, "page_size": page_size, "sort_by": sort_by},
    )
    return base.task_list_from_response(response, Text2ImageResult, "text-to-image")


def poll(
    task_id: str,
    interval: float = 5.0,
    timeout: float = 600.0,
    *,
    requester: Requester | None = None,
) -> ExtendedDict:
    """Poll until the text-to-image task succeeds or reaches a terminal state."""
    fetch = get if requester is None else lambda pending_id: get(pending_id, requester=requester)
    return base.poll_task(fetch, task_id, interval, timeout)


def generate(
    prompt: str,
    *,
    ai_model: str = "nano-banana",
    aspect_ratio: str | None = None,
    generate_multi_view: bool = False,
    pose_mode: str | None = None,
    wait: bool = True,
    requester: Requester | None = None,
) -> ExtendedDict | ExtendedString:
    """Generate images from text, optionally waiting for the completed task."""
    request = Text2ImageRequest(
        ai_model=ai_model,
        prompt=prompt,
        generate_multi_view=generate_multi_view,
        pose_mode=pose_mode,
        aspect_ratio=aspect_ratio,
    )
    task_id = create(request) if requester is None else create(request, requester=requester)
    if not wait:
        return task_id
    return poll(str(task_id)) if requester is None else poll(str(task_id), requester=requester)


def download_first(result: Mapping[str, object], output_path: str) -> int:
    """Download `image_urls[0]` from a completed text-to-image task."""
    image_urls = result.get("image_urls")
    if (
        not isinstance(image_urls, Sequence)
        or isinstance(image_urls, (str, bytes, bytearray))
        or not image_urls
        or not isinstance(image_urls[0], (str, ExtendedString))
    ):
        msg = "Text-to-image task has no downloadable image URL"
        raise RuntimeError(msg)
    return base.download(str(image_urls[0]), output_path)
