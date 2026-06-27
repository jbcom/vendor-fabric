"""High-level job orchestration for 3D asset generation.

This module provides AssetGenerator for batch workflows with
asset downloading and manifest generation.
"""

from __future__ import annotations

import hashlib
import logging

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from extended_data.io import wrap_raw_data_for_export

from vendor_fabric.meshy import base, text3d
from vendor_fabric.meshy.models import ArtStyle, AssetIntent, AssetSpec, Text3DRequest


logger = logging.getLogger("vendor_fabric.meshy.jobs")


@dataclass
class AssetManifest:
    """Metadata for generated asset."""

    asset_id: str
    intent: str
    description: str
    art_style: str
    model_path: str | None = None
    texture_paths: dict[str, str] | None = None
    thumbnail_path: str | None = None
    task_id: str = ""
    polycount_target: int | None = None
    polycount_estimate: int | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> ExtendedDict:
        """Return an extended manifest payload."""
        return extend_data(asdict(self))


class AssetGenerator:
    """Orchestrates 3D asset generation workflows."""

    def __init__(self, output_root: str = "client/public"):
        self.output_root = Path(output_root)

    def _generate_asset_id(self, spec: AssetSpec) -> str:
        """Generate unique asset ID from spec."""
        if spec.asset_id:
            return spec.asset_id

        if spec.metadata and "slug" in spec.metadata:
            return spec.metadata["slug"]

        desc_hash = hashlib.sha256(spec.description.encode()).hexdigest()[:8]
        return f"{spec.intent.value}_{desc_hash}"

    def generate_model(self, spec: AssetSpec, wait: bool = True, poll_interval: float = 5.0) -> ExtendedDict:
        """Generate 3D model from spec and return an extended manifest payload."""
        asset_id = self._generate_asset_id(spec)

        # Create task using text3d module
        task_id = text3d.create(
            Text3DRequest(
                mode="preview",
                prompt=spec.description,
                art_style=spec.art_style,
                negative_prompt="low quality, blurry, distorted, extra limbs, bad topology",
                target_polycount=spec.target_polycount,
                enable_pbr=spec.enable_pbr,
            )
        )

        manifest = AssetManifest(
            asset_id=asset_id,
            intent=spec.intent.value,
            description=spec.description,
            art_style=spec.art_style.value,
            task_id=str(task_id),
            polycount_target=spec.target_polycount,
            metadata=spec.metadata.copy() if spec.metadata else {},
        )

        if not wait:
            return manifest.to_dict()

        # Poll until complete
        result = text3d.poll(str(task_id), interval=poll_interval)

        # Download assets
        output_dir = self.output_root / spec.output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        model_urls = result.get("model_urls") or {}
        glb_url = model_urls.get("glb")
        if glb_url:
            glb_path = output_dir / f"{asset_id}.glb"
            base.download(str(glb_url), str(glb_path))
            manifest.model_path = str(glb_path.relative_to(self.output_root))

        texture_urls = result.get("texture_urls") or []
        if texture_urls and len(texture_urls) > 0:
            textures = texture_urls[0]
            texture_paths = {}

            for map_type, url in textures.items():
                if url:
                    tex_path = output_dir / f"{asset_id}_{map_type}.png"
                    base.download(str(url), str(tex_path))
                    texture_paths[map_type] = str(tex_path.relative_to(self.output_root))

            manifest.texture_paths = texture_paths

        thumbnail_url = result.get("thumbnail_url")
        if thumbnail_url:
            thumb_path = output_dir / f"{asset_id}_thumb.png"
            base.download(str(thumbnail_url), str(thumb_path))
            manifest.thumbnail_path = str(thumb_path.relative_to(self.output_root))

        # Save manifest
        manifest_path = output_dir / f"{asset_id}_manifest.json"
        with open(manifest_path, "w") as f:
            f.write(wrap_raw_data_for_export(manifest.to_dict(), allow_encoding="json", indent_2=True))

        return manifest.to_dict()

    def batch_generate(self, specs: list[AssetSpec]) -> ExtendedList[ExtendedDict]:
        """Generate multiple assets and return extended manifest payloads.

        Generation runs sequentially; failures are logged at debug level
        and the batch continues. Failed specs are omitted from the
        returned list.
        """
        manifests = []

        for spec in specs:
            try:
                manifest = self.generate_model(spec, wait=True)
                manifests.append(manifest)
            except Exception:
                logger.debug("batch_generate: spec %s failed", getattr(spec, "description", "<unknown>"), exc_info=True)
                continue

        return extend_data(manifests)


# Example specs


def example_character_spec() -> AssetSpec:
    """Example character asset specification."""
    return AssetSpec(
        intent=AssetIntent.PLAYER_CHARACTER,
        description="Humanoid character in casual clothing, standing pose, game-ready low-poly",
        art_style=ArtStyle.REALISTIC,
        target_polycount=15000,
        enable_pbr=True,
        output_path="models/characters",
    )


def example_prop_spec() -> AssetSpec:
    """Example prop asset specification."""
    return AssetSpec(
        intent=AssetIntent.PROP_INTERACTABLE,
        description="Wooden crate with metal reinforcements, game-ready low-poly",
        art_style=ArtStyle.REALISTIC,
        target_polycount=5000,
        enable_pbr=True,
        output_path="models/props",
    )


def example_environment_spec() -> AssetSpec:
    """Example environment asset specification."""
    return AssetSpec(
        intent=AssetIntent.TERRAIN_ELEMENT,
        description="Rocky outcrop with moss, natural stone formation, game-ready low-poly",
        art_style=ArtStyle.REALISTIC,
        target_polycount=8000,
        enable_pbr=True,
        output_path="models/environment",
    )
