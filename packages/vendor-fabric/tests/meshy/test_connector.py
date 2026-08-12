"""Tests for Meshy connector facade methods."""

from __future__ import annotations

from unittest.mock import MagicMock

from extended_data.containers import ExtendedDict, ExtendedString

from vendor_fabric.meshy import connector as connector_module
from vendor_fabric.meshy.connector import MeshyConnector


def test_meshy_connector_uses_meshy_defaults() -> None:
    """Meshy connector construction should preserve the shared base configuration."""
    connector = MeshyConnector(api_key="test-key")

    assert connector.api_key == "test-key"
    assert connector._base_url == "https://api.meshy.ai"
    assert connector._timeout == 300.0


def test_meshy_text3d_generate_dispatches_to_text3d_module(monkeypatch) -> None:
    """Text-to-3D facade should pass explicit options to the module helper."""
    generate = MagicMock(return_value=ExtendedString("task-123"))
    monkeypatch.setattr(connector_module.text3d, "generate", generate)

    result = MeshyConnector(api_key="test-key").text3d_generate(
        "low-poly ship",
        art_style="cartoon",
        negative_prompt="blurry",
        target_polycount=1234,
        enable_pbr=False,
        wait=False,
    )

    assert result == "task-123"
    generate.assert_called_once_with(
        "low-poly ship",
        art_style="cartoon",
        negative_prompt="blurry",
        target_polycount=1234,
        enable_pbr=False,
        wait=False,
    )


def test_meshy_image3d_generate_dispatches_to_image3d_module(monkeypatch) -> None:
    """Image-to-3D facade should pass explicit options to the module helper."""
    generate = MagicMock(return_value=ExtendedString("image-task-123"))
    monkeypatch.setattr(connector_module.image3d, "generate", generate)

    result = MeshyConnector(api_key="test-key").image3d_generate(
        "https://example.com/reference.png",
        topology="quad",
        target_polycount=4321,
        enable_pbr=False,
        wait=False,
    )

    assert result == "image-task-123"
    generate.assert_called_once_with(
        "https://example.com/reference.png",
        topology="quad",
        target_polycount=4321,
        enable_pbr=False,
        wait=False,
    )


def test_meshy_text2image_generate_dispatches_to_text2image_module(monkeypatch) -> None:
    """Text-to-image facade should pass current image generation options through."""
    generate = MagicMock(return_value=ExtendedString("image-task-123"))
    monkeypatch.setattr(connector_module.text2image, "generate", generate)

    result = MeshyConnector(api_key="test-key").text2image_generate(
        "painted forest shrine",
        ai_model="gpt-image-2",
        aspect_ratio="3:2",
        wait=False,
    )

    assert result == "image-task-123"
    generate.assert_called_once_with(
        "painted forest shrine",
        ai_model="gpt-image-2",
        aspect_ratio="3:2",
        generate_multi_view=False,
        pose_mode=None,
        wait=False,
    )


def test_meshy_additional_generation_facades_dispatch(monkeypatch) -> None:
    """Current image edit, multi-view, and remesh facades should preserve explicit options."""
    image_generate = MagicMock(return_value=ExtendedString("edit-task"))
    multi_generate = MagicMock(return_value=ExtendedString("multi-task"))
    remesh_apply = MagicMock(return_value=ExtendedString("remesh-task"))
    monkeypatch.setattr(connector_module.image2image, "generate", image_generate)
    monkeypatch.setattr(connector_module.multiimage3d, "generate", multi_generate)
    monkeypatch.setattr(connector_module.remesh, "apply", remesh_apply)
    connector = MeshyConnector(api_key="test-key")

    assert connector.image2image_generate("gold", ["source.png"], wait=False) == "edit-task"
    assert connector.multiimage3d_generate(["front.png", "back.png"], wait=False) == "multi-task"
    assert connector.remesh_model("model-task", topology="quad", target_polycount=1234, wait=False) == "remesh-task"

    image_generate.assert_called_once_with(
        "gold",
        ["source.png"],
        ai_model="nano-banana",
        aspect_ratio=None,
        generate_multi_view=False,
        wait=False,
    )
    multi_generate.assert_called_once_with(
        ["front.png", "back.png"],
        ai_model="latest",
        should_texture=True,
        enable_pbr=False,
        target_formats=None,
        wait=False,
    )
    remesh_apply.assert_called_once_with(
        "model-task",
        target_formats=None,
        topology="quad",
        target_polycount=1234,
        wait=False,
    )


def test_meshy_rig_model_dispatches_to_rigging_module(monkeypatch) -> None:
    """Rigging facade should dispatch to the rigging helper."""
    rig = MagicMock(return_value=ExtendedDict({"id": "rig-task"}))
    monkeypatch.setattr(connector_module.rigging, "rig", rig)

    result = MeshyConnector(api_key="test-key").rig_model("model-123", wait=False)

    assert result == {"id": "rig-task"}
    rig.assert_called_once_with("model-123", wait=False)


def test_meshy_apply_animation_dispatches_to_animate_module(monkeypatch) -> None:
    """Animation facade should dispatch to the animation helper."""
    apply = MagicMock(return_value=ExtendedDict({"id": "animation-task"}))
    monkeypatch.setattr(connector_module.animate, "apply", apply)

    result = MeshyConnector(api_key="test-key").apply_animation("model-123", 42, wait=False)

    assert result == {"id": "animation-task"}
    apply.assert_called_once_with("model-123", 42, wait=False)


def test_meshy_retexture_model_dispatches_to_retexture_module(monkeypatch) -> None:
    """Retexture facade should dispatch to the retexture helper."""
    apply = MagicMock(return_value=ExtendedDict({"id": "texture-task"}))
    monkeypatch.setattr(connector_module.retexture, "apply", apply)

    result = MeshyConnector(api_key="test-key").retexture_model(
        "model-123",
        "painted brass",
        enable_pbr=False,
        wait=False,
    )

    assert result == {"id": "texture-task"}
    apply.assert_called_once_with("model-123", "painted brass", enable_pbr=False, wait=False)
