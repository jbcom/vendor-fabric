"""Contract tests for additional current Meshy generation endpoints."""

from __future__ import annotations

import json

from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from extended_data.containers import ExtendedDict, ExtendedString

from vendor_fabric.meshy import image2image, multiimage3d, remesh
from vendor_fabric.meshy.models import (
    Image2ImageRequest,
    MultiImage3DRequest,
    RemeshRequest,
    TaskStatus,
)


def _json_response(payload: object) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.content = json.dumps(payload).encode()
    return response


@pytest.mark.parametrize(
    ("request_path", "create_call", "endpoint"),
    [
        (
            "vendor_fabric.meshy.image2image.base.request",
            lambda: image2image.create(
                Image2ImageRequest(
                    ai_model="nano-banana",
                    prompt="paint this gold",
                    reference_image_urls=["https://example.com/source.png"],
                )
            ),
            "image-to-image",
        ),
        (
            "vendor_fabric.meshy.multiimage3d.base.request",
            lambda: multiimage3d.create(MultiImage3DRequest(image_urls=["https://example.com/front.png"])),
            "multi-image-to-3d",
        ),
        (
            "vendor_fabric.meshy.remesh.base.request",
            lambda: remesh.create(RemeshRequest(input_task_id="model-task", target_formats=["glb"])),
            "remesh",
        ),
    ],
)
def test_additional_endpoint_create_calls_use_v1_and_extended_ids(request_path, create_call, endpoint) -> None:
    with patch(request_path, return_value=_json_response({"task_id": "new-task"})) as api_request:
        task_id = create_call()

    assert isinstance(task_id, ExtendedString)
    assert task_id == "new-task"
    assert api_request.call_args.args == ("POST", endpoint)
    assert api_request.call_args.kwargs["version"] == "v1"


@pytest.mark.parametrize(
    ("module", "endpoint"),
    [(image2image, "image-to-image"), (multiimage3d, "multi-image-to-3d"), (remesh, "remesh")],
)
def test_additional_endpoints_get_list_delete_and_poll(module, endpoint) -> None:
    payload = {
        "id": "task-123",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "image_urls": ["https://example.com/image.png"],
        "model_urls": {"glb": "https://example.com/model.glb"},
    }
    with patch.object(module.base, "request", return_value=_json_response(payload)) as api_request:
        result = module.get("task-123")
    assert isinstance(result, ExtendedDict)
    assert result["id"] == "task-123"
    api_request.assert_called_once_with("GET", f"{endpoint}/task-123", version="v1")

    with patch.object(module, "get", return_value=result):
        assert module.poll("task-123", interval=0, timeout=1) is result

    with patch.object(module.base, "request", return_value=_json_response([payload])) as api_request:
        tasks = module.list_tasks(page_num=2, page_size=25, sort_by="+created_at")
    assert tasks[0]["id"] == "task-123"
    api_request.assert_called_once_with(
        "GET",
        endpoint,
        version="v1",
        params={"page_num": 2, "page_size": 25, "sort_by": "+created_at"},
    )

    with patch.object(module.base, "request") as api_request:
        module.delete("task-123")
    api_request.assert_called_once_with("DELETE", f"{endpoint}/task-123", version="v1")


def test_image2image_generate_builds_current_request() -> None:
    completed = ExtendedDict({"id": "edit-task", "status": TaskStatus.SUCCEEDED})
    with (
        patch("vendor_fabric.meshy.image2image.create", return_value=ExtendedString("edit-task")) as create,
        patch("vendor_fabric.meshy.image2image.poll", return_value=completed) as poll,
    ):
        result = image2image.generate(
            "paint this gold",
            ["https://example.com/source.png"],
            ai_model="gpt-image-2",
            aspect_ratio="3:2",
        )

    assert result is completed
    assert create.call_args.args[0] == Image2ImageRequest(
        ai_model="gpt-image-2",
        prompt="paint this gold",
        reference_image_urls=["https://example.com/source.png"],
        aspect_ratio="3:2",
    )
    poll.assert_called_once_with("edit-task")


def test_multiimage3d_generate_builds_current_request() -> None:
    with (
        patch("vendor_fabric.meshy.multiimage3d.create", return_value=ExtendedString("multi-task")) as create,
        patch("vendor_fabric.meshy.multiimage3d.poll") as poll,
    ):
        result = multiimage3d.generate(
            ["front.png", "back.png"],
            ai_model="meshy-7",
            enable_pbr=True,
            target_formats=["glb", "fbx"],
            wait=False,
        )

    assert result == "multi-task"
    request = create.call_args.args[0]
    assert request.image_urls == ["front.png", "back.png"]
    assert request.ai_model == "meshy-7"
    assert request.enable_pbr is True
    assert request.target_formats == ["glb", "fbx"]
    poll.assert_not_called()


def test_remesh_helpers_support_task_ids_and_urls() -> None:
    with (
        patch(
            "vendor_fabric.meshy.remesh.create",
            side_effect=[ExtendedString("task-remesh"), ExtendedString("url-remesh")],
        ) as create,
        patch("vendor_fabric.meshy.remesh.poll", return_value=ExtendedDict({"status": "SUCCEEDED"})) as poll,
    ):
        task_result = remesh.apply("model-task", topology="quad", target_polycount=1200)
        url_result = remesh.apply_from_url("https://example.com/model.glb", target_formats=["glb"], wait=False)

    assert task_result == {"status": "SUCCEEDED"}
    assert url_result == "url-remesh"
    first, second = [item.args[0] for item in create.call_args_list]
    assert first.input_task_id == "model-task"
    assert first.topology == "quad"
    assert first.target_polycount == 1200
    assert second.model_url == "https://example.com/model.glb"
    assert poll.call_args_list == [call("task-remesh")]


@pytest.mark.parametrize("module", [image2image, multiimage3d, remesh])
def test_additional_endpoint_polling_redacts_failures(module) -> None:
    with patch.object(
        module,
        "get",
        return_value=ExtendedDict(
            {
                "id": "task-123",
                "status": TaskStatus.FAILED,
                "task_error": {"message": "denied password=hunter2"},
            }
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            module.poll("task-123", interval=0, timeout=1)

    assert "hunter2" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


@pytest.mark.parametrize("module", [image2image, multiimage3d, remesh])
@pytest.mark.parametrize("status", [TaskStatus.CANCELED, TaskStatus.EXPIRED])
def test_additional_endpoint_polling_rejects_terminal_states(module, status) -> None:
    with patch.object(module, "get", return_value=ExtendedDict({"id": "task-123", "status": status})):
        with pytest.raises(RuntimeError, match=status.value.title()):
            module.poll("task-123", interval=0, timeout=1)
