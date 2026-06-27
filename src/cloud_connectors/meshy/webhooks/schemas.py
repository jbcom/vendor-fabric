"""Pydantic schemas for Meshy webhook payloads."""

from __future__ import annotations

from extended_data.containers import ExtendedDict, extend_data
from pydantic import BaseModel, Field


class WebhookModelUrls(BaseModel):
    """Model URLs in webhook payload."""

    glb: str | None = None
    fbx: str | None = None
    usdz: str | None = None
    obj: str | None = None
    mtl: str | None = None


class WebhookTextureUrls(BaseModel):
    """Texture URLs in webhook payload."""

    base_color: str | None = None
    metallic: str | None = None
    roughness: str | None = None
    normal: str | None = None
    ao: str | None = None


class WebhookBasicAnimations(BaseModel):
    """Basic animations in rigging webhook."""

    walking_glb_url: str | None = None
    walking_fbx_url: str | None = None
    walking_armature_glb_url: str | None = None
    running_glb_url: str | None = None
    running_fbx_url: str | None = None
    running_armature_glb_url: str | None = None


class WebhookRiggingResult(BaseModel):
    """Rigging result in webhook payload."""

    rigged_character_fbx_url: str | None = None
    rigged_character_glb_url: str | None = None
    basic_animations: WebhookBasicAnimations | None = None


class WebhookTaskError(BaseModel):
    """Error details in webhook payload."""

    message: str | None = None
    code: str | None = None


class MeshyWebhookPayload(BaseModel):
    """Webhook payload from Meshy API.

    This represents the JSON payload sent by Meshy when a task completes.
    Different services (text3d, rigging, animation, retexture) send different fields.
    """

    id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status: PENDING, IN_PROGRESS, SUCCEEDED, FAILED, EXPIRED")
    progress: int = Field(default=0, description="Progress percentage (0-100)")
    created_at: int = Field(..., description="Unix timestamp")
    started_at: int | None = None
    finished_at: int | None = None
    expires_at: int | None = None

    # Text-to-3D specific fields
    model_urls: WebhookModelUrls | None = None
    texture_urls: list[WebhookTextureUrls] | None = None
    thumbnail_url: str | None = None

    # Rigging specific fields
    result: WebhookRiggingResult | None = None

    # Animation specific fields
    animation_glb_url: str | None = None
    animation_fbx_url: str | None = None
    video_url: str | None = None

    # Error handling
    task_error: WebhookTaskError | None = None

    # Metadata
    preceding_tasks: int = Field(default=0)

    def get_error_message(self) -> str | None:
        """Extract error message from task_error field."""
        if self.task_error and self.task_error.message:
            return self.task_error.message
        return None

    def get_glb_url(self) -> str | None:
        """Get GLB URL regardless of service type."""
        # Text-to-3D / Retexture
        if self.model_urls and self.model_urls.glb:
            return self.model_urls.glb

        # Rigging
        if self.result and self.result.rigged_character_glb_url:
            return self.result.rigged_character_glb_url

        # Animation
        if self.animation_glb_url:
            return self.animation_glb_url

        return None

    def get_all_urls(self) -> ExtendedDict:
        """Get all available URLs as an extended flat dict."""
        urls = {}

        # Model URLs
        if self.model_urls:
            if self.model_urls.glb:
                urls["glb"] = self.model_urls.glb
            if self.model_urls.fbx:
                urls["fbx"] = self.model_urls.fbx
            if self.model_urls.usdz:
                urls["usdz"] = self.model_urls.usdz
            if self.model_urls.obj:
                urls["obj"] = self.model_urls.obj
            if self.model_urls.mtl:
                urls["mtl"] = self.model_urls.mtl

        # Rigging URLs
        if self.result:
            if self.result.rigged_character_glb_url:
                urls["glb"] = self.result.rigged_character_glb_url
            if self.result.rigged_character_fbx_url:
                urls["fbx"] = self.result.rigged_character_fbx_url

        # Animation URLs
        if self.animation_glb_url:
            urls["glb"] = self.animation_glb_url
        if self.animation_fbx_url:
            urls["fbx"] = self.animation_fbx_url
        if self.video_url:
            urls["video"] = self.video_url

        # Thumbnail
        if self.thumbnail_url:
            urls["thumbnail"] = self.thumbnail_url

        return extend_data(urls)
