"""Provider capability functions for Meshy AI 3D generation.

This module exposes framework-agnostic Python functions plus tool metadata.
Agent framework wrappers belong in agentic-fabric.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from extended_data.containers import ExtendedDict, extend_data
from pydantic import BaseModel, Field


# =============================================================================
# Pydantic Schemas for Tool Inputs
# =============================================================================


class Text3dGenerateSchema(BaseModel):
    """Pydantic schema for the text3d_generate tool."""

    prompt: str = Field(..., description="Detailed text description of the 3D model (max 600 chars)")
    art_style: str = Field(
        "realistic",
        description="One of: realistic, sculpture. For 'sculpture', set enable_pbr=False.",
    )
    negative_prompt: str = Field("", description="Things to avoid in the generation")
    target_polycount: int = Field(30000, description="Target polygon count")
    enable_pbr: bool = Field(
        True,
        description="Enable PBR materials. API defaults to False; we default to True for better realistic renders. Set False for sculpture.",
    )


class Image3dGenerateSchema(BaseModel):
    """Pydantic schema for the image3d_generate tool."""

    image_url: str = Field(..., description="URL to the source image")
    topology: str = Field("", description='Mesh topology ("quad" or "triangle"), empty for default')
    target_polycount: int = Field(15000, description="Target polygon count")
    enable_pbr: bool = Field(True, description="Enable PBR materials")


class RigModelSchema(BaseModel):
    """Pydantic schema for the rig_model tool."""

    model_id: str = Field(..., description="Task ID of the static model to rig")
    wait: bool = Field(True, description="Whether to wait for completion (default True)")


class ApplyAnimationSchema(BaseModel):
    """Pydantic schema for the apply_animation tool."""

    model_id: str = Field(..., description="Task ID of the rigged model")
    animation_id: int = Field(..., description="Animation ID from the Meshy catalog (integer)")
    wait: bool = Field(True, description="Whether to wait for completion (default True)")


class RetextureModelSchema(BaseModel):
    """Pydantic schema for the retexture_model tool."""

    model_id: str = Field(..., description="Task ID of the model to retexture")
    texture_prompt: str = Field(..., description="Description of the new texture/appearance")
    enable_pbr: bool = Field(True, description="Enable PBR materials")
    wait: bool = Field(True, description="Whether to wait for completion (default True)")


class ListAnimationsSchema(BaseModel):
    """Pydantic schema for the list_animations tool."""

    category: str = Field("", description="Optional category filter (Fighting, WalkAndRun, etc.)")
    limit: int = Field(50, description="Maximum number of results")


class CheckTaskStatusSchema(BaseModel):
    """Pydantic schema for the check_task_status tool."""

    task_id: str = Field(..., description="The Meshy task ID")
    task_type: str = Field(
        "text-to-3d",
        description="Task type (text-to-3d, rigging, animation, retexture)",
    )


class GetAnimationSchema(BaseModel):
    """Pydantic schema for the get_animation tool."""

    animation_id: int = Field(..., description="The animation ID number")


# =============================================================================
# Tool Implementation Functions
# =============================================================================


def _result_get(result: object, field: str, default: object = None) -> object:
    """Read a field from an extended payload or a model-like test double."""
    if isinstance(result, Mapping):
        return result.get(field, default)
    return getattr(result, field, default)


def _result_status(result: object) -> str:
    """Read a task status from an extended payload or model-like object."""
    status = _result_get(result, "status", "unknown")
    return str(status.value) if hasattr(status, "value") else str(status)


def _extract_result_fields(result: object) -> ExtendedDict:
    """Extract common fields from Meshy API result objects.

    Safely extracts status, model_url, and thumbnail_url from result objects,
    handling missing attributes gracefully.

    Args:
        result: A Meshy API result object (Text3DResult, Image3DResult, etc.)

    Returns:
        Dict with status, model_url, and thumbnail_url fields
    """
    # Extract status - prefer .value if it's an enum, otherwise str()
    status = _result_status(result)

    # Extract model_url from model_urls.glb if available
    model_url = None
    model_urls = _result_get(result, "model_urls")
    if isinstance(model_urls, Mapping):
        model_url = model_urls.get("glb")
    elif model_urls:
        model_url = getattr(model_urls, "glb", None)

    # Extract thumbnail_url
    thumbnail_url = _result_get(result, "thumbnail_url")

    return extend_data(
        {
            "status": status,
            "model_url": model_url,
            "thumbnail_url": thumbnail_url,
        }
    )


def text3d_generate(
    prompt: str,
    art_style: str = "realistic",
    negative_prompt: str = "",
    target_polycount: int = 30000,
    enable_pbr: bool = True,
) -> ExtendedDict:
    """Generate a 3D model from text description.

    Args:
        prompt: Detailed text description of the 3D model (max 600 chars)
        art_style: One of: realistic, sculpture. For 'sculpture', set
            enable_pbr=False as sculpture style generates its own PBR maps.
        negative_prompt: Things to avoid in the generation
        target_polycount: Target polygon count
        enable_pbr: Enable PBR materials. API defaults to False; we default
            to True for better realistic renders. Set False for sculpture.

    Returns:
        Dict with task_id, status, model_url, and thumbnail_url
    """
    from vendor_fabric.meshy import text3d

    result = text3d.generate(
        prompt,
        art_style=art_style,
        negative_prompt=negative_prompt,
        target_polycount=target_polycount,
        enable_pbr=enable_pbr,
        wait=True,
    )

    if isinstance(result, str):
        return extend_data(
            {
                "task_id": result,
                "status": "pending",
                "message": "Text-to-3D task submitted",
            }
        )

    fields = _extract_result_fields(result)
    return extend_data(
        {
            "task_id": _result_get(result, "id"),
            **fields,
        }
    )


def image3d_generate(
    image_url: str,
    topology: str = "",
    target_polycount: int = 15000,
    enable_pbr: bool = True,
) -> ExtendedDict:
    """Generate a 3D model from an image.

    Args:
        image_url: URL to the source image
        topology: Mesh topology ("quad" or "triangle"), empty for default
        target_polycount: Target polygon count
        enable_pbr: Enable PBR materials

    Returns:
        Dict with task_id, status, model_url, and thumbnail_url
    """
    from vendor_fabric.meshy import image3d

    result = image3d.generate(
        image_url,
        topology=topology or None,
        target_polycount=target_polycount,
        enable_pbr=enable_pbr,
        wait=True,
    )

    if isinstance(result, str):
        return extend_data(
            {
                "task_id": result,
                "status": "pending",
                "message": "Image-to-3D task submitted",
            }
        )

    fields = _extract_result_fields(result)
    return extend_data(
        {
            "task_id": _result_get(result, "id"),
            **fields,
        }
    )


def rig_model(model_id: str, wait: bool = True) -> ExtendedDict:
    """Add skeleton/rig to a static 3D model.

    Args:
        model_id: Task ID of the static model to rig
        wait: Whether to wait for completion (default True)

    Returns:
        Dict with task_id and status
    """
    from vendor_fabric.meshy import rigging

    result = rigging.rig(model_id, wait=wait)

    if isinstance(result, str):
        return extend_data(
            {
                "task_id": result,
                "status": "pending",
                "message": "Rigging task submitted",
            }
        )

    if wait:
        return extend_data(
            {
                "task_id": _result_get(result, "id"),
                "status": _result_status(result),
                "message": "Rigging completed",
            }
        )

    msg = "Expected rigging task id when wait=False"
    raise TypeError(msg)


def apply_animation(model_id: str, animation_id: int, wait: bool = True) -> ExtendedDict:
    """Apply animation to a rigged model.

    Args:
        model_id: Task ID of the rigged model
        animation_id: Animation ID from the Meshy catalog (integer)
        wait: Whether to wait for completion (default True)

    Returns:
        Dict with task_id, status, and glb_url
    """
    from vendor_fabric.meshy import animate

    result = animate.apply(model_id, int(animation_id), wait=wait)

    if isinstance(result, str):
        return extend_data(
            {
                "task_id": result,
                "status": "pending",
                "message": "Animation task submitted",
            }
        )

    if wait:
        return extend_data(
            {
                "task_id": _result_get(result, "id"),
                "status": _result_status(result),
                "message": "Animation completed",
                "glb_url": _result_get(result, "animation_glb_url"),
            }
        )

    msg = "Expected animation task id when wait=False"
    raise TypeError(msg)


def retexture_model(
    model_id: str,
    texture_prompt: str,
    enable_pbr: bool = True,
    wait: bool = True,
) -> ExtendedDict:
    """Apply new textures to an existing model.

    Args:
        model_id: Task ID of the model to retexture
        texture_prompt: Description of the new texture/appearance
        enable_pbr: Enable PBR materials
        wait: Whether to wait for completion (default True)

    Returns:
        Dict with task_id, status, and model_url
    """
    from vendor_fabric.meshy import retexture

    result = retexture.apply(
        model_id,
        texture_prompt,
        enable_pbr=enable_pbr,
        wait=wait,
    )

    if isinstance(result, str):
        return extend_data(
            {
                "task_id": result,
                "status": "pending",
                "message": "Retexture task submitted",
            }
        )

    if wait:
        return extend_data(
            {
                "task_id": _result_get(result, "id"),
                "status": _result_status(result),
                "message": "Retexture completed",
                "model_url": _result_get(result, "model_url"),
            }
        )

    msg = "Expected retexture task id when wait=False"
    raise TypeError(msg)


def list_animations(category: str = "", limit: int = 50) -> ExtendedDict:
    """List available animations from the Meshy catalog.

    Args:
        category: Optional category filter (Fighting, WalkAndRun, etc.)
        limit: Maximum number of results

    Returns:
        Dict with count, total, and list of animations
    """
    from vendor_fabric.meshy.animations import ANIMATIONS

    animations = list(ANIMATIONS.values())

    if category:
        animations = [a for a in animations if category.lower() in a.category.lower()]

    results = []
    for anim in animations[:limit]:
        results.append(
            {
                "id": anim.id,
                "name": anim.name,
                "category": anim.category,
                "subcategory": anim.subcategory,
            }
        )

    return extend_data(
        {
            "count": len(results),
            "total": len(animations),
            "animations": results,
        }
    )


def check_task_status(task_id: str, task_type: str = "text-to-3d") -> ExtendedDict:
    """Check status of a Meshy task.

    Args:
        task_id: The Meshy task ID
        task_type: Task type (text-to-3d, rigging, animation, retexture)

    Returns:
        Dict with status, progress, and model_url if complete
    """
    from vendor_fabric.meshy import animate, image3d, retexture, rigging, text3d

    # Call the appropriate get function based on task type
    get_funcs: dict[str, Callable[[str], Any]] = {
        "text-to-3d": text3d.get,
        "image-to-3d": image3d.get,
        "rigging": rigging.get,
        "animation": animate.get,
        "retexture": retexture.get,
    }

    get_func = get_funcs.get(task_type)
    if not get_func:
        raise ValueError(f"Unknown task type: {task_type}")

    result = get_func(task_id)
    status = _result_status(result)

    # Get model URL if available
    model_url = None
    model_urls = _result_get(result, "model_urls")
    if isinstance(model_urls, Mapping):
        model_url = model_urls.get("glb")
    elif model_urls:
        model_url = getattr(model_urls, "glb", None)
    if model_url is None:
        model_url = _result_get(result, "glb_url")

    return extend_data(
        {
            "task_id": task_id,
            "status": status,
            "progress": _result_get(result, "progress"),
            "model_url": model_url,
        }
    )


def get_animation(animation_id: int) -> ExtendedDict:
    """Get details of a specific animation.

    Args:
        animation_id: The animation ID number

    Returns:
        Dict with animation details
    """
    from vendor_fabric.meshy.animations import ANIMATIONS

    if animation_id not in ANIMATIONS:
        raise ValueError(f"Animation ID {animation_id} not found")

    anim = ANIMATIONS[animation_id]

    return extend_data(
        {
            "id": anim.id,
            "name": anim.name,
            "category": anim.category,
            "subcategory": anim.subcategory,
            "preview_url": anim.preview_url,
        }
    )


# =============================================================================
# Tool Metadata
# =============================================================================

# Tool definitions with framework-agnostic metadata.
TOOL_DEFINITIONS = [
    {
        "func": text3d_generate,
        "name": "text3d_generate",
        "description": (
            "Generate a 3D GLB model from a text description using Meshy AI. "
            "Provide a detailed prompt describing the model. Returns the task_id, "
            "status, model_url, and thumbnail_url on success."
        ),
        "schema": Text3dGenerateSchema,
    },
    {
        "func": image3d_generate,
        "name": "image3d_generate",
        "description": (
            "Generate a 3D GLB model from an image using Meshy AI. "
            "Provide a URL to the source image. Returns the task_id, "
            "status, model_url, and thumbnail_url on success."
        ),
        "schema": Image3dGenerateSchema,
    },
    {
        "func": rig_model,
        "name": "rig_model",
        "description": (
            "Add a skeleton/rig to a static 3D model. This is required before "
            "you can apply animations. Takes the model's task ID and returns "
            "a new task ID for the rigging operation."
        ),
        "schema": RigModelSchema,
    },
    {
        "func": apply_animation,
        "name": "apply_animation",
        "description": (
            "Apply an animation to a rigged 3D model. Use list_animations to "
            "see available animation IDs. The model must be rigged first."
        ),
        "schema": ApplyAnimationSchema,
    },
    {
        "func": retexture_model,
        "name": "retexture_model",
        "description": (
            "Apply new textures to an existing 3D model. Great for creating "
            "color variants or material changes without regenerating the mesh."
        ),
        "schema": RetextureModelSchema,
    },
    {
        "func": list_animations,
        "name": "list_animations",
        "description": (
            "List available animations from the Meshy animation catalog. "
            "Optionally filter by category. Returns animation IDs and names "
            "that can be used with apply_animation."
        ),
        "schema": ListAnimationsSchema,
    },
    {
        "func": check_task_status,
        "name": "check_task_status",
        "description": (
            "Check the current status of a Meshy AI task. Returns status "
            "(pending, processing, succeeded, failed), progress percentage, "
            "and model URL if complete."
        ),
        "schema": CheckTaskStatusSchema,
    },
    {
        "func": get_animation,
        "name": "get_animation",
        "description": (
            "Get details of a specific animation by ID, including name, category, subcategory, and preview URL."
        ),
        "schema": GetAnimationSchema,
    },
]


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Tool metadata (for custom integrations)
    "TOOL_DEFINITIONS",
    "apply_animation",
    "check_task_status",
    "get_animation",
    # Framework-specific getters
    "image3d_generate",
    "list_animations",
    "retexture_model",
    "rig_model",
    # Raw functions (for direct use or custom wrappers)
    "text3d_generate",
]
