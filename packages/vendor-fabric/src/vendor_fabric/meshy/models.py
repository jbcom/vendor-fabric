"""Pydantic models for Meshy API types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class ArtStyle(StrEnum):
    """Art style for text-to-3D generation.

    Per Meshy API docs:
    - realistic: Realistic style
    - sculpture: Sculpture style (PBR not recommended but not enforced)
    """

    REALISTIC = "realistic"
    SCULPTURE = "sculpture"


class TexturePBRMapType(StrEnum):
    BASE_COLOR = "baseColor"
    METALLIC = "metallic"
    ROUGHNESS = "roughness"
    NORMAL = "normal"
    AO = "ao"


# Text-to-3D Models


class Text3DRequest(BaseModel):
    mode: str = Field(default="preview", description="preview or refine")
    prompt: str
    art_style: ArtStyle = ArtStyle.REALISTIC
    negative_prompt: str | None = None
    ai_model: str | None = None
    topology: str | None = None  # quad, triangle
    target_polycount: int | None = None
    enable_pbr: bool | None = None


class ModelUrls(BaseModel):
    glb: str | None = None
    fbx: str | None = None
    usdz: str | None = None
    obj: str | None = None
    mtl: str | None = None


class TextureUrls(BaseModel):
    base_color: str | None = None
    metallic: str | None = None
    roughness: str | None = None
    normal: str | None = None
    ao: str | None = None


class Text3DResult(BaseModel):
    id: str
    status: TaskStatus
    progress: int = 0
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    model_urls: ModelUrls | None = None
    texture_urls: list[TextureUrls] | None = None
    thumbnail_url: str | None = None
    error: str | None = None


# Task classes for services
class Text3DTask(BaseModel):
    task_id: str
    prompt: str = ""
    art_style: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    thumbnail_url: str | None = None
    model_urls: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class RiggingTask(BaseModel):
    task_id: str
    model_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    thumbnail_url: str | None = None
    model_urls: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class AnimationTask(BaseModel):
    task_id: str
    model_id: str = ""
    animation_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    video_url: str | None = None
    model_urls: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class RetextureTask(BaseModel):
    task_id: str
    model_id: str = ""
    prompt: str = ""
    art_style: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    thumbnail_url: str | None = None
    model_urls: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class AnimationAction(BaseModel):
    id: str
    name: str
    category: str = ""
    duration: float = 0.0
    preview_url: str | None = None


# Text-to-Texture Models


class TextTextureRequest(BaseModel):
    model_url: str
    prompt: str
    art_style: ArtStyle = ArtStyle.REALISTIC
    negative_prompt: str | None = None
    ai_model: str | None = None
    resolution: str | None = "1024"  # 1024, 2048, 4096
    enable_pbr: bool | None = True


class TextTextureResult(BaseModel):
    id: str
    status: TaskStatus
    progress: int = 0
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    texture_urls: list[TextureUrls] | None = None
    thumbnail_url: str | None = None
    error: str | None = None


# Image-to-3D Models


class Image3DRequest(BaseModel):
    mode: str = Field(default="preview", description="preview or refine")
    image_url: str
    ai_model: str | None = None
    topology: str | None = None
    target_polycount: int | None = None
    enable_pbr: bool | None = None


class Image3DResult(BaseModel):
    id: str
    status: TaskStatus
    progress: int = 0
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    model_urls: ModelUrls | None = None
    texture_urls: list[TextureUrls] | None = None
    thumbnail_url: str | None = None
    error: str | None = None


# Rigging Models


class RiggingRequest(BaseModel):
    input_task_id: str | None = None
    model_url: str | None = None
    height_meters: float = 1.7
    texture_image_url: str | None = None


class BasicAnimations(BaseModel):
    walking_glb_url: str | None = None
    walking_fbx_url: str | None = None
    walking_armature_glb_url: str | None = None
    running_glb_url: str | None = None
    running_fbx_url: str | None = None
    running_armature_glb_url: str | None = None


class RiggingResultData(BaseModel):
    rigged_character_fbx_url: str | None = None
    rigged_character_glb_url: str | None = None
    basic_animations: BasicAnimations | None = None


class RiggingResult(BaseModel):
    id: str
    status: TaskStatus
    progress: int = 0
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    expires_at: int | None = None
    task_error: dict[str, Any] | None = None
    result: RiggingResultData | None = None
    preceding_tasks: int = 0


# Animation Models


class AnimationRequest(BaseModel):
    rig_task_id: str
    action_id: int
    loop: bool | None = True
    frame_rate: int | None = 30


class AnimationResult(BaseModel):
    id: str
    status: TaskStatus
    progress: int = 0
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    expires_at: int | None = None
    animation_glb_url: str | None = None
    animation_fbx_url: str | None = None
    task_error: dict[str, Any] | None = None
    preceding_tasks: int = 0


# Retexture Models


class RetextureRequest(BaseModel):
    input_task_id: str | None = None
    model_url: str | None = None
    text_style_prompt: str | None = None
    image_style_url: str | None = None
    ai_model: str = "latest"
    enable_original_uv: bool = True
    enable_pbr: bool = False


class RetextureResult(BaseModel):
    id: str
    status: TaskStatus
    progress: int = 0
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    expires_at: int | None = None
    model_urls: ModelUrls | None = None
    texture_urls: list[TextureUrls] | None = None
    thumbnail_url: str | None = None
    text_style_prompt: str | None = None
    image_style_url: str | None = None
    task_error: dict[str, Any] | None = None
    preceding_tasks: int = 0


# Asset Intent categories


class AssetIntent(StrEnum):
    """Categories for 3D asset generation."""

    PLAYER_CHARACTER = "player_character"
    NPC_CHARACTER = "npc_character"
    CREATURE_PREDATOR = "creature_predator"
    CREATURE_PREY = "creature_prey"
    PROP_INTERACTABLE = "prop_interactable"
    PROP_DECORATION = "prop_decoration"
    TERRAIN_ELEMENT = "terrain_element"
    TEXTURE_TERRAIN = "texture_terrain"
    TEXTURE_MATERIAL = "texture_material"


class AssetSpec(BaseModel):
    """High-level specification for 3D asset generation."""

    intent: AssetIntent
    description: str
    art_style: ArtStyle = ArtStyle.REALISTIC
    target_polycount: int | None = None
    enable_pbr: bool = True
    output_path: str = Field(description="Relative output path for downloaded assets")
    metadata: dict[str, Any] = Field(default_factory=dict)
    asset_id: str | None = Field(default=None, description="Unique asset identifier (auto-generated if not provided)")
