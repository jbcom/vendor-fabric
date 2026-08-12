"""Remesh API."""

from __future__ import annotations

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy import base
from vendor_fabric.meshy.models import RemeshRequest, RemeshResult


ENDPOINT = "remesh"


def create(request: RemeshRequest) -> ExtendedString:
    """Create a remesh task and return its task ID."""
    response = base.request("POST", ENDPOINT, version="v1", json=request.model_dump(exclude_none=True))
    return base.task_id_from_response(response)


def get(task_id: str) -> ExtendedDict:
    """Get a remesh task."""
    response = base.request("GET", f"{ENDPOINT}/{task_id}", version="v1")
    return base.task_payload_from_response(response, RemeshResult, ENDPOINT)


def delete(task_id: str) -> None:
    """Permanently delete a remesh task."""
    base.request("DELETE", f"{ENDPOINT}/{task_id}", version="v1")


def list_tasks(*, page_num: int = 1, page_size: int = 10, sort_by: str = "-created_at") -> ExtendedList[ExtendedDict]:
    """List remesh tasks."""
    response = base.request(
        "GET", ENDPOINT, version="v1", params={"page_num": page_num, "page_size": page_size, "sort_by": sort_by}
    )
    return base.task_list_from_response(response, RemeshResult, ENDPOINT)


def poll(task_id: str, interval: float = 5.0, timeout: float = 600.0) -> ExtendedDict:
    """Poll until the remesh task reaches a terminal state."""
    return base.poll_task(get, task_id, interval, timeout)


def apply(
    model_task_id: str,
    *,
    target_formats: list[str] | None = None,
    topology: str = "triangle",
    target_polycount: int | None = None,
    decimation_mode: int | None = None,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Remesh a completed Meshy model task."""
    task_id = create(
        RemeshRequest(
            input_task_id=model_task_id,
            target_formats=target_formats or ["glb"],
            topology=topology,
            target_polycount=target_polycount,
            decimation_mode=decimation_mode,
        )
    )
    if not wait:
        return task_id
    return poll(str(task_id))


def apply_from_url(
    model_url: str,
    *,
    target_formats: list[str] | None = None,
    topology: str = "triangle",
    target_polycount: int | None = None,
    decimation_mode: int | None = None,
    wait: bool = True,
) -> ExtendedDict | ExtendedString:
    """Remesh a model supplied by public URL or data URI."""
    task_id = create(
        RemeshRequest(
            model_url=model_url,
            target_formats=target_formats or ["glb"],
            topology=topology,
            target_polycount=target_polycount,
            decimation_mode=decimation_mode,
        )
    )
    if not wait:
        return task_id
    return poll(str(task_id))
