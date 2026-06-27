"""Tests for Meshy task-id API helpers."""

from __future__ import annotations

import json

from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from extended_data.containers import ExtendedDict, ExtendedString

from vendor_fabric.meshy import animate, image3d, retexture, rigging, text3d
from vendor_fabric.meshy.models import (
    AnimationRequest,
    ArtStyle,
    Image3DRequest,
    RetextureRequest,
    RiggingRequest,
    TaskStatus,
    Text3DRequest,
)


def _task_response(task_id: str) -> MagicMock:
    return _json_response({"result": task_id})


def _json_response(payload: object) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.content = json.dumps(payload).encode()
    response.json.side_effect = AssertionError("Meshy responses must be decoded from response content")
    return response


def test_text3d_task_ids_are_extended_strings() -> None:
    with patch("vendor_fabric.meshy.text3d.base.request", return_value=_task_response("text-task")):
        created = text3d.create(Text3DRequest(prompt="a sword"))
        refined = text3d.refine("text-task")

    assert isinstance(created, ExtendedString)
    assert isinstance(refined, ExtendedString)
    assert created == "text-task"
    assert refined == "text-task"


def test_image3d_task_ids_are_extended_strings() -> None:
    with patch("vendor_fabric.meshy.image3d.base.request", return_value=_task_response("image-task")):
        created = image3d.create(Image3DRequest(image_url="https://example.com/source.png"))
        refined = image3d.refine("image-task")

    assert isinstance(created, ExtendedString)
    assert isinstance(refined, ExtendedString)
    assert created == "image-task"
    assert refined == "image-task"


def test_animation_task_id_is_extended_string() -> None:
    request = AnimationRequest(rig_task_id="rig-task", action_id=42)

    with patch("vendor_fabric.meshy.animate.base.request", return_value=_task_response("animation-task")):
        created = animate.create(request)

    assert isinstance(created, ExtendedString)
    assert created == "animation-task"


def test_rigging_task_id_is_extended_string() -> None:
    request = RiggingRequest(input_task_id="model-task")

    with patch("vendor_fabric.meshy.rigging.base.request", return_value=_task_response("rig-task")):
        created = rigging.create(request)

    assert isinstance(created, ExtendedString)
    assert created == "rig-task"


def test_retexture_task_id_is_extended_string() -> None:
    request = RetextureRequest(input_task_id="model-task", text_style_prompt="gold")

    with patch("vendor_fabric.meshy.retexture.base.request", return_value=_task_response("retexture-task")):
        created = retexture.create(request)

    assert isinstance(created, ExtendedString)
    assert created == "retexture-task"


def test_text3d_generate_builds_request_and_waits() -> None:
    """Text generation should build the preview request and poll the created task."""
    completed = ExtendedDict({"id": "text-task", "status": TaskStatus.SUCCEEDED})

    with (
        patch("vendor_fabric.meshy.text3d.create", return_value=ExtendedString("text-task")) as create,
        patch("vendor_fabric.meshy.text3d.poll", return_value=completed) as poll,
    ):
        result = text3d.generate(
            "a low-poly castle",
            art_style="sculpture",
            negative_prompt="blurry",
            target_polycount=1234,
            enable_pbr=False,
        )

    assert result is completed
    create.assert_called_once()
    request = create.call_args.args[0]
    assert isinstance(request, Text3DRequest)
    assert request.mode == "preview"
    assert request.prompt == "a low-poly castle"
    assert request.art_style == ArtStyle.SCULPTURE
    assert request.negative_prompt == "blurry"
    assert request.target_polycount == 1234
    assert request.enable_pbr is False
    poll.assert_called_once_with("text-task")


def test_text3d_generate_without_wait_returns_task_id() -> None:
    """Text generation should expose submitted task IDs without polling when wait is disabled."""
    with (
        patch("vendor_fabric.meshy.text3d.create", return_value=ExtendedString("text-task")) as create,
        patch("vendor_fabric.meshy.text3d.poll") as poll,
    ):
        result = text3d.generate("a low-poly crate", wait=False)

    assert isinstance(result, ExtendedString)
    assert result == "text-task"
    create.assert_called_once()
    poll.assert_not_called()


def test_image3d_generate_builds_request_and_waits() -> None:
    """Image generation should build the preview request and poll the created task."""
    completed = ExtendedDict({"id": "image-task", "status": TaskStatus.SUCCEEDED})

    with (
        patch("vendor_fabric.meshy.image3d.create", return_value=ExtendedString("image-task")) as create,
        patch("vendor_fabric.meshy.image3d.poll", return_value=completed) as poll,
    ):
        result = image3d.generate(
            "https://example.com/source.png",
            topology="quad",
            target_polycount=4321,
            enable_pbr=False,
        )

    assert result is completed
    create.assert_called_once()
    request = create.call_args.args[0]
    assert isinstance(request, Image3DRequest)
    assert request.mode == "preview"
    assert request.image_url == "https://example.com/source.png"
    assert request.topology == "quad"
    assert request.target_polycount == 4321
    assert request.enable_pbr is False
    poll.assert_called_once_with("image-task")


def test_animation_apply_builds_request_and_waits() -> None:
    """Animation application should build the animation request and poll the created task."""
    completed = ExtendedDict({"id": "animation-task", "status": TaskStatus.SUCCEEDED})

    with (
        patch("vendor_fabric.meshy.animate.create", return_value=ExtendedString("animation-task")) as create,
        patch("vendor_fabric.meshy.animate.poll", return_value=completed) as poll,
    ):
        result = animate.apply("rig-task", 42, loop=False, frame_rate=24)

    assert result is completed
    create.assert_called_once()
    request = create.call_args.args[0]
    assert isinstance(request, AnimationRequest)
    assert request.rig_task_id == "rig-task"
    assert request.action_id == 42
    assert request.loop is False
    assert request.frame_rate == 24
    poll.assert_called_once_with("animation-task")


def test_rigging_helpers_build_task_and_url_requests() -> None:
    """Rigging helpers should build task-id and model-url request payloads."""
    with (
        patch("vendor_fabric.meshy.rigging.create", return_value=ExtendedString("rig-task")) as create,
        patch("vendor_fabric.meshy.rigging.poll") as poll,
    ):
        task_result = rigging.rig("model-task", height_meters=1.9, wait=False)
        url_result = rigging.rig_from_url(
            "https://example.com/model.glb",
            height_meters=1.8,
            texture_url="https://example.com/texture.png",
            wait=False,
        )

    assert task_result == "rig-task"
    assert url_result == "rig-task"
    task_request, url_request = [call.args[0] for call in create.call_args_list]
    assert isinstance(task_request, RiggingRequest)
    assert task_request.input_task_id == "model-task"
    assert task_request.height_meters == 1.9
    assert isinstance(url_request, RiggingRequest)
    assert url_request.model_url == "https://example.com/model.glb"
    assert url_request.texture_image_url == "https://example.com/texture.png"
    assert url_request.height_meters == 1.8
    poll.assert_not_called()


def test_rigging_helpers_poll_when_wait_enabled() -> None:
    """Rigging helpers should poll created task IDs when wait is enabled."""
    task_completed = ExtendedDict({"id": "rig-task", "status": TaskStatus.SUCCEEDED})
    url_completed = ExtendedDict({"id": "url-rig-task", "status": TaskStatus.SUCCEEDED})

    with (
        patch(
            "vendor_fabric.meshy.rigging.create",
            side_effect=[ExtendedString("rig-task"), ExtendedString("url-rig-task")],
        ),
        patch("vendor_fabric.meshy.rigging.poll", side_effect=[task_completed, url_completed]) as poll,
    ):
        task_result = rigging.rig("model-task")
        url_result = rigging.rig_from_url("https://example.com/model.glb")

    assert task_result is task_completed
    assert url_result is url_completed
    assert poll.call_args_list == [call("rig-task"), call("url-rig-task")]


def test_retexture_helpers_build_text_and_image_style_requests() -> None:
    """Retexture helpers should build text-prompt and image-reference request payloads."""
    with (
        patch("vendor_fabric.meshy.retexture.create", return_value=ExtendedString("retexture-task")) as create,
        patch("vendor_fabric.meshy.retexture.poll") as poll,
    ):
        text_result = retexture.apply(
            "model-task",
            "gold leaf",
            enable_original_uv=False,
            enable_pbr=False,
            wait=False,
        )
        image_result = retexture.apply_from_image(
            "model-task",
            "https://example.com/style.png",
            enable_original_uv=True,
            enable_pbr=True,
            wait=False,
        )

    assert text_result == "retexture-task"
    assert image_result == "retexture-task"
    text_request, image_request = [call.args[0] for call in create.call_args_list]
    assert isinstance(text_request, RetextureRequest)
    assert text_request.input_task_id == "model-task"
    assert text_request.text_style_prompt == "gold leaf"
    assert text_request.enable_original_uv is False
    assert text_request.enable_pbr is False
    assert isinstance(image_request, RetextureRequest)
    assert image_request.image_style_url == "https://example.com/style.png"
    assert image_request.enable_original_uv is True
    assert image_request.enable_pbr is True
    poll.assert_not_called()


def test_retexture_helpers_poll_when_wait_enabled() -> None:
    """Retexture helpers should poll created task IDs when wait is enabled."""
    text_completed = ExtendedDict({"id": "retexture-task", "status": TaskStatus.SUCCEEDED})
    image_completed = ExtendedDict({"id": "image-retexture-task", "status": TaskStatus.SUCCEEDED})

    with (
        patch(
            "vendor_fabric.meshy.retexture.create",
            side_effect=[ExtendedString("retexture-task"), ExtendedString("image-retexture-task")],
        ),
        patch("vendor_fabric.meshy.retexture.poll", side_effect=[text_completed, image_completed]) as poll,
    ):
        text_result = retexture.apply("model-task", "gold leaf")
        image_result = retexture.apply_from_image("model-task", "https://example.com/style.png")

    assert text_result is text_completed
    assert image_result is image_completed
    assert poll.call_args_list == [call("retexture-task"), call("image-retexture-task")]


@pytest.mark.parametrize(
    ("request_path", "call"),
    [
        (
            "vendor_fabric.meshy.text3d.base.request",
            lambda: text3d.create(Text3DRequest(prompt="a sword")),
        ),
        (
            "vendor_fabric.meshy.text3d.base.request",
            lambda: text3d.refine("text-task"),
        ),
        (
            "vendor_fabric.meshy.image3d.base.request",
            lambda: image3d.create(Image3DRequest(image_url="https://example.com/source.png")),
        ),
        (
            "vendor_fabric.meshy.image3d.base.request",
            lambda: image3d.refine("image-task"),
        ),
        (
            "vendor_fabric.meshy.animate.base.request",
            lambda: animate.create(AnimationRequest(rig_task_id="rig-task", action_id=42)),
        ),
        (
            "vendor_fabric.meshy.rigging.base.request",
            lambda: rigging.create(RiggingRequest(input_task_id="model-task")),
        ),
        (
            "vendor_fabric.meshy.retexture.base.request",
            lambda: retexture.create(RetextureRequest(input_task_id="model-task", text_style_prompt="gold")),
        ),
    ],
)
def test_meshy_task_id_responses_fail_loudly_without_string_result(request_path: str, call) -> None:
    """Task creation/refinement must not convert malformed vendor payloads into None."""
    response = _json_response({"password": "hunter2", "authorization": "Bearer raw_token", "result": None})

    with patch(request_path, return_value=response):
        with pytest.raises(RuntimeError, match="missing 'result' key") as exc_info:
            call()

    message = str(exc_info.value)
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_text3d_get_returns_extended_payload() -> None:
    payload = {
        "id": "text-task",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "model_urls": {"glb": "https://example.com/model.glb"},
    }
    with patch("vendor_fabric.meshy.text3d.base.request", return_value=_json_response(payload)):
        result = text3d.get("text-task")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["id"], ExtendedString)
    assert isinstance(result["model_urls"], ExtendedDict)
    assert result["model_urls"]["glb"] == "https://example.com/model.glb"


def test_image3d_get_returns_extended_payload() -> None:
    payload = {
        "id": "image-task",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "model_urls": {"glb": "https://example.com/image.glb"},
    }
    with patch("vendor_fabric.meshy.image3d.base.request", return_value=_json_response(payload)):
        result = image3d.get("image-task")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["model_urls"], ExtendedDict)
    assert result["model_urls"]["glb"] == "https://example.com/image.glb"


def test_animation_get_returns_extended_payload() -> None:
    payload = {
        "id": "animation-task",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "animation_glb_url": "https://example.com/animation.glb",
    }
    with patch("vendor_fabric.meshy.animate.base.request", return_value=_json_response(payload)):
        result = animate.get("animation-task")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["animation_glb_url"], ExtendedString)
    assert result["animation_glb_url"] == "https://example.com/animation.glb"


def test_rigging_get_returns_extended_payload() -> None:
    payload = {
        "id": "rig-task",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "result": {"rigged_character_glb_url": "https://example.com/rig.glb"},
    }
    with patch("vendor_fabric.meshy.rigging.base.request", return_value=_json_response(payload)):
        result = rigging.get("rig-task")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["result"], ExtendedDict)
    assert result["result"]["rigged_character_glb_url"] == "https://example.com/rig.glb"


def test_retexture_get_returns_extended_payload() -> None:
    payload = {
        "id": "retexture-task",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "model_urls": {"glb": "https://example.com/retexture.glb"},
    }
    with patch("vendor_fabric.meshy.retexture.base.request", return_value=_json_response(payload)):
        result = retexture.get("retexture-task")

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["model_urls"], ExtendedDict)
    assert result["model_urls"]["glb"] == "https://example.com/retexture.glb"


@pytest.mark.parametrize(
    ("request_path", "call"),
    [
        ("vendor_fabric.meshy.text3d.base.request", lambda: text3d.get("text-task")),
        ("vendor_fabric.meshy.image3d.base.request", lambda: image3d.get("image-task")),
        ("vendor_fabric.meshy.animate.base.request", lambda: animate.get("animation-task")),
        ("vendor_fabric.meshy.rigging.base.request", lambda: rigging.get("rig-task")),
        ("vendor_fabric.meshy.retexture.base.request", lambda: retexture.get("retexture-task")),
    ],
)
def test_meshy_get_responses_redact_validation_failures(request_path: str, call) -> None:
    """Malformed status payloads should not expose raw vendor data through Pydantic errors."""
    response = _json_response(
        {
            "status": "SUCCEEDED",
            "created_at": 1700000000,
            "password": "hunter2",
            "authorization": "Bearer raw_token",
        }
    )

    with patch(request_path, return_value=response):
        with pytest.raises(RuntimeError, match="Unexpected API response") as exc_info:
            call()

    message = str(exc_info.value)
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "ValidationError" not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize("module", [text3d, image3d, retexture, rigging, animate])
def test_meshy_poll_returns_succeeded_tasks(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    """All Meshy polling helpers should return succeeded task payloads directly."""
    completed = ExtendedDict({"id": "task-123", "status": TaskStatus.SUCCEEDED})
    monkeypatch.setattr(module, "get", lambda task_id: completed)

    result = module.poll("task-123", interval=0, timeout=1)

    assert result is completed


@pytest.mark.parametrize("module", [text3d, image3d, retexture, rigging, animate])
def test_meshy_poll_redacts_failed_task_errors(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    """All Meshy polling helpers should redact vendor task failure messages."""
    monkeypatch.setattr(
        module,
        "get",
        lambda task_id: {
            "id": task_id,
            "status": "FAILED",
            "task_error": {"message": "denied password=hunter2 Authorization: Bearer raw_token"},
            "error": "denied api_key=key_123",
        },
    )

    with pytest.raises(RuntimeError) as exc_info:
        module.poll("task-secret", interval=0, timeout=1)

    message = str(exc_info.value)
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "key_123" not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize("module", [text3d, image3d, retexture, rigging, animate])
def test_meshy_poll_raises_for_expired_tasks(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    """All Meshy polling helpers should fail loudly when tasks expire."""
    monkeypatch.setattr(module, "get", lambda task_id: {"id": task_id, "status": TaskStatus.EXPIRED})

    with pytest.raises(RuntimeError, match="Task expired"):
        module.poll("task-expired", interval=0, timeout=1)


@pytest.mark.parametrize("module", [text3d, image3d, retexture, rigging, animate])
def test_meshy_poll_times_out_pending_tasks(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    """All Meshy polling helpers should time out pending tasks."""
    times = iter([0.0, 2.0])
    monkeypatch.setattr(module, "get", lambda task_id: {"id": task_id, "status": TaskStatus.PENDING})
    monkeypatch.setattr(module.time, "time", lambda: next(times))
    monkeypatch.setattr(module.time, "sleep", MagicMock())

    with pytest.raises(TimeoutError, match="Task timed out after 1s"):
        module.poll("task-pending", interval=0, timeout=1)


@pytest.mark.parametrize("payload", [{"result": ""}, {"result": 123}, ["not", "a", "mapping"]])
def test_meshy_task_id_response_requires_non_empty_string_result(payload: object) -> None:
    """Task ids are string API handles, not arbitrary JSON payload values."""
    response = _json_response(payload)

    with patch("vendor_fabric.meshy.image3d.base.request", return_value=response):
        with pytest.raises(RuntimeError, match="missing 'result' key"):
            image3d.create(Image3DRequest(image_url="https://example.com/source.png"))
