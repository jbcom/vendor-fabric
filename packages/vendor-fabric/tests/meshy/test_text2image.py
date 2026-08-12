"""Tests for Meshy's text-to-image task workflow."""

from __future__ import annotations

import json

from unittest.mock import MagicMock, patch

import httpx
import pytest

from extended_data.containers import ExtendedDict, ExtendedString

from vendor_fabric.meshy import base, text2image
from vendor_fabric.meshy.models import (
    Image2ImageRequest,
    TaskStatus,
    Text2ImageRequest,
    Text3DResult,
)


def _json_response(payload: object) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.content = json.dumps(payload).encode()
    response.json.side_effect = AssertionError("Meshy responses must be decoded from response content")
    return response


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"result": "result-task"}, "result-task"),
        ({"id": "id-task"}, "id-task"),
        ({"task_id": "task-id-task"}, "task-id-task"),
        ({"result": {"id": "nested-result-task"}}, "nested-result-task"),
    ],
)
def test_create_accepts_documented_meshy_task_id_shapes(payload: dict[str, object], expected: str) -> None:
    """Create responses vary across Meshy endpoints and must retain their real task ID."""
    request = Text2ImageRequest(prompt="a painted duck", ai_model="nano-banana")

    with patch("vendor_fabric.meshy.text2image.base.request", return_value=_json_response(payload)) as api_request:
        task_id = text2image.create(request)

    assert isinstance(task_id, ExtendedString)
    assert str(task_id) == expected
    api_request.assert_called_once_with(
        "POST",
        "text-to-image",
        version="v1",
        json={"ai_model": "nano-banana", "prompt": "a painted duck", "generate_multi_view": False},
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"result": ""},
        {"id": 123},
        {"task_id": None},
        {"result": {}},
        ["not", "a", "mapping"],
    ],
)
def test_create_rejects_invalid_task_id_shapes(payload: object) -> None:
    request = Text2ImageRequest(prompt="a painted duck", ai_model="nano-banana")

    with patch("vendor_fabric.meshy.text2image.base.request", return_value=_json_response(payload)):
        with pytest.raises(RuntimeError, match="missing task id"):
            text2image.create(request)


def test_get_returns_validated_extended_image_payload() -> None:
    payload = {
        "id": "image-task",
        "type": "text-to-image",
        "ai_model": "nano-banana",
        "prompt": "a painted duck",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "image_urls": ["https://assets.meshy.ai/image.png"],
    }

    with patch("vendor_fabric.meshy.text2image.base.request", return_value=_json_response(payload)) as api_request:
        result = text2image.get("image-task")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["image_urls"][0], ExtendedString)
    assert result["image_urls"] == ["https://assets.meshy.ai/image.png"]
    api_request.assert_called_once_with("GET", "text-to-image/image-task", version="v1")


def test_generate_builds_request_and_polls() -> None:
    completed = ExtendedDict(
        {
            "id": "image-task",
            "status": TaskStatus.SUCCEEDED,
            "image_urls": ["https://assets.meshy.ai/image.png"],
        }
    )

    with (
        patch("vendor_fabric.meshy.text2image.create", return_value=ExtendedString("image-task")) as create,
        patch("vendor_fabric.meshy.text2image.poll", return_value=completed) as poll,
    ):
        result = text2image.generate(
            "a painted duck",
            ai_model="gpt-image-2",
            aspect_ratio="3:2",
            generate_multi_view=False,
            pose_mode="t-pose",
        )

    assert result is completed
    request = create.call_args.args[0]
    assert isinstance(request, Text2ImageRequest)
    assert request.prompt == "a painted duck"
    assert request.ai_model == "gpt-image-2"
    assert request.aspect_ratio == "3:2"
    assert request.generate_multi_view is False
    assert request.pose_mode == "t-pose"
    poll.assert_called_once_with("image-task")


def test_generate_without_wait_returns_task_id() -> None:
    with (
        patch("vendor_fabric.meshy.text2image.create", return_value=ExtendedString("image-task")),
        patch("vendor_fabric.meshy.text2image.poll") as poll,
    ):
        result = text2image.generate("a painted duck", wait=False)

    assert result == "image-task"
    poll.assert_not_called()


@pytest.mark.parametrize("terminal_status", [TaskStatus.FAILED, TaskStatus.CANCELED, TaskStatus.EXPIRED])
def test_poll_rejects_non_success_terminal_states(terminal_status: TaskStatus) -> None:
    with patch(
        "vendor_fabric.meshy.text2image.get",
        return_value=ExtendedDict(
            {
                "id": "image-task",
                "status": terminal_status,
                "task_error": {"message": "denied password=hunter2"},
            }
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            text2image.poll("image-task", interval=0, timeout=1)

    assert "hunter2" not in str(exc_info.value)
    if terminal_status == TaskStatus.FAILED:
        assert "[REDACTED]" in str(exc_info.value)
    else:
        assert terminal_status.value.title() in str(exc_info.value)


def test_poll_returns_succeeded_task_and_times_out_pending_task(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = ExtendedDict({"id": "image-task", "status": TaskStatus.SUCCEEDED, "image_urls": ["image.png"]})
    monkeypatch.setattr(text2image, "get", lambda task_id: completed)
    assert text2image.poll("image-task", interval=0, timeout=1) is completed

    times = iter([0.0, 2.0])
    monkeypatch.setattr(
        text2image,
        "get",
        lambda task_id: ExtendedDict({"id": task_id, "status": TaskStatus.PENDING, "image_urls": []}),
    )
    monkeypatch.setattr(text2image.base.time, "time", lambda: next(times))
    monkeypatch.setattr(text2image.base.time, "sleep", MagicMock())
    with pytest.raises(TimeoutError, match="Task timed out after 1s"):
        text2image.poll("image-task", interval=0, timeout=1)


def test_download_first_image_uses_first_meshy_url() -> None:
    result = ExtendedDict(
        {
            "id": "image-task",
            "status": TaskStatus.SUCCEEDED,
            "image_urls": ["https://assets.meshy.ai/first.png", "https://assets.meshy.ai/second.png"],
        }
    )

    with patch("vendor_fabric.meshy.text2image.base.download", return_value=321) as download:
        size = text2image.download_first(result, "art/output.png")

    assert size == 321
    download.assert_called_once_with("https://assets.meshy.ai/first.png", "art/output.png")


@pytest.mark.parametrize("image_urls", [None, [], [123]])
def test_download_first_image_rejects_missing_or_invalid_urls(image_urls: object) -> None:
    with pytest.raises(RuntimeError, match="downloadable image URL"):
        text2image.download_first(ExtendedDict({"image_urls": image_urls}), "art/output.png")


def test_list_tasks_uses_meshy_pagination_contract() -> None:
    response = _json_response(
        [
            {
                "id": "image-task",
                "status": "SUCCEEDED",
                "created_at": 1700000000,
                "image_urls": ["https://assets.meshy.ai/image.png"],
            }
        ]
    )
    with patch("vendor_fabric.meshy.text2image.base.request", return_value=response) as api_request:
        tasks = text2image.list_tasks(page_num=2, page_size=25, sort_by="+created_at")

    assert isinstance(tasks[0], ExtendedDict)
    assert tasks[0]["id"] == "image-task"
    api_request.assert_called_once_with(
        "GET",
        "text-to-image",
        version="v1",
        params={"page_num": 2, "page_size": 25, "sort_by": "+created_at"},
    )


def test_delete_task_uses_documented_endpoint() -> None:
    with patch("vendor_fabric.meshy.text2image.base.request") as api_request:
        text2image.delete("image-task")

    api_request.assert_called_once_with("DELETE", "text-to-image/image-task", version="v1")


@pytest.mark.parametrize("request_type", [Text2ImageRequest, Image2ImageRequest])
def test_multi_view_rejects_aspect_ratio_before_request(request_type) -> None:
    kwargs: dict[str, object] = {
        "prompt": "painted duck",
        "generate_multi_view": True,
        "aspect_ratio": "1:1",
    }
    if request_type is Image2ImageRequest:
        kwargs["reference_image_urls"] = ["source.png"]
    with pytest.raises(ValueError, match="aspect_ratio"):
        request_type(**kwargs)


def test_validated_task_payloads_preserve_wire_aliases() -> None:
    payload = {
        "id": "model-task",
        "status": "SUCCEEDED",
        "created_at": 1700000000,
        "model_urls": {"3mf": "https://assets.meshy.ai/model.3mf"},
    }
    one = base.task_payload_from_response(_json_response(payload), Text3DResult, "text-to-3d")
    many = base.task_list_from_response(_json_response([payload]), Text3DResult, "text-to-3d")

    assert one["model_urls"]["3mf"] == "https://assets.meshy.ai/model.3mf"
    assert "three_mf" not in one["model_urls"]
    assert many[0]["model_urls"]["3mf"] == "https://assets.meshy.ai/model.3mf"


def test_task_list_invalid_top_level_shape_uses_public_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="Unexpected API response for text-to-3d"):
        base.task_list_from_response(_json_response({"result": []}), Text3DResult, "text-to-3d")
