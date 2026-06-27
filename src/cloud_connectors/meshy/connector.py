"""Meshy AI Connector - HTTP client for Meshy AI 3D generation API.

This connector provides Python access to Meshy AI's 3D asset generation API,
following the shared connector patterns used across cloud-connectors.
"""

from __future__ import annotations

from typing import Any

from extended_data.containers import ExtendedDict, ExtendedString

from cloud_connectors.base import ConnectorBase
from cloud_connectors.meshy import animate, image3d, retexture, rigging, text3d


class MeshyConnector(ConnectorBase):
    """Meshy AI 3D generation connector.

    Provides access to text-to-3D, image-to-3D, rigging, animation, and retexturing.
    """

    API_KEY_ENV = "MESHY_API_KEY"
    BASE_URL = "https://api.meshy.ai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 300.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout, **kwargs)

    def text3d_generate(
        self,
        prompt: str,
        art_style: str = "realistic",
        negative_prompt: str = "",
        target_polycount: int = 30000,
        enable_pbr: bool = True,
        wait: bool = True,
    ) -> ExtendedDict | ExtendedString:
        """Generate a 3D model from text description."""
        return text3d.generate(
            prompt,
            art_style=art_style,
            negative_prompt=negative_prompt,
            target_polycount=target_polycount,
            enable_pbr=enable_pbr,
            wait=wait,
        )

    def image3d_generate(
        self,
        image_url: str,
        topology: str = "triangle",
        target_polycount: int = 15000,
        enable_pbr: bool = True,
        wait: bool = True,
    ) -> ExtendedDict | ExtendedString:
        """Generate a 3D model from an image."""
        return image3d.generate(
            image_url,
            topology=topology,
            target_polycount=target_polycount,
            enable_pbr=enable_pbr,
            wait=wait,
        )

    def rig_model(self, model_id: str, wait: bool = True) -> ExtendedDict | ExtendedString:
        """Add skeleton/rig to a static 3D model."""
        return rigging.rig(model_id, wait=wait)

    def apply_animation(self, model_id: str, animation_id: int, wait: bool = True) -> ExtendedDict | ExtendedString:
        """Apply animation to a rigged model."""
        return animate.apply(model_id, animation_id, wait=wait)

    def retexture_model(
        self,
        model_id: str,
        texture_prompt: str,
        enable_pbr: bool = True,
        wait: bool = True,
    ) -> ExtendedDict | ExtendedString:
        """Apply new textures to an existing model."""
        return retexture.apply(
            model_id,
            texture_prompt,
            enable_pbr=enable_pbr,
            wait=wait,
        )
