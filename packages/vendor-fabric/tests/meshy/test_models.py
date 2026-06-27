"""Tests for Pydantic models."""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from vendor_fabric.meshy.models import (
    AnimationRequest,
    AnimationResult,
    ArtStyle,
    AssetIntent,
    AssetSpec,
    BasicAnimations,
    Image3DRequest,
    ModelUrls,
    RetextureRequest,
    RetextureResult,
    RiggingRequest,
    RiggingResult,
    RiggingResultData,
    TaskStatus,
    Text3DRequest,
    Text3DResult,
    TextTextureRequest,
    TextureUrls,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_exist(self):
        """Verify all expected statuses are defined."""
        assert TaskStatus.PENDING == "PENDING"
        assert TaskStatus.IN_PROGRESS == "IN_PROGRESS"
        assert TaskStatus.SUCCEEDED == "SUCCEEDED"
        assert TaskStatus.FAILED == "FAILED"
        assert TaskStatus.EXPIRED == "EXPIRED"

    def test_string_comparison(self):
        """TaskStatus should be comparable to strings."""
        assert TaskStatus.SUCCEEDED == "SUCCEEDED"
        assert TaskStatus.PENDING != "SUCCEEDED"


class TestArtStyle:
    """Tests for ArtStyle enum.

    Per Meshy API docs (https://docs.meshy.ai/en/api/text-to-3d):
    - realistic: Realistic style
    - sculpture: Sculpture style (enable_pbr should be false)
    """

    def test_all_styles_exist(self):
        """Verify all expected art styles are defined."""
        assert ArtStyle.REALISTIC == "realistic"
        assert ArtStyle.SCULPTURE == "sculpture"

    def test_only_two_styles(self):
        """Verify only valid styles exist (per Meshy API)."""
        styles = list(ArtStyle)
        assert len(styles) == 2
        assert {s.value for s in styles} == {"realistic", "sculpture"}


class TestText3DRequest:
    """Tests for Text3DRequest model."""

    def test_minimal_request(self):
        """Test creating request with only required fields."""
        request = Text3DRequest(prompt="A red apple")
        assert request.prompt == "A red apple"
        assert request.mode == "preview"
        assert request.art_style == ArtStyle.REALISTIC

    def test_full_request(self):
        """Test creating request with all fields."""
        request = Text3DRequest(
            mode="refine",
            prompt="A detailed robot",
            art_style=ArtStyle.SCULPTURE,
            negative_prompt="low quality",
            ai_model="meshy-4",
            topology="quad",
            target_polycount=10000,
            enable_pbr=False,  # sculpture style disables PBR
        )
        assert request.mode == "refine"
        assert request.art_style == ArtStyle.SCULPTURE
        assert request.target_polycount == 10000

    def test_model_dump_excludes_none(self):
        """Test that model_dump(exclude_none=True) works correctly."""
        request = Text3DRequest(prompt="Test")
        data = request.model_dump(exclude_none=True)
        assert "prompt" in data
        assert "negative_prompt" not in data

    def test_missing_prompt_raises_error(self):
        """Test that missing prompt raises validation error."""
        with pytest.raises(ValidationError):
            Text3DRequest()


class TestText3DResult:
    """Tests for Text3DResult model."""

    def test_result_parsing(self):
        """Test parsing a complete result."""
        result = Text3DResult(
            id="task-123",
            status=TaskStatus.SUCCEEDED,
            progress=100,
            created_at=1700000000,
            model_urls=ModelUrls(glb="https://example.com/model.glb"),
        )
        assert result.id == "task-123"
        assert result.status == TaskStatus.SUCCEEDED
        assert result.model_urls.glb == "https://example.com/model.glb"

    def test_result_with_textures(self):
        """Test result with texture URLs."""
        result = Text3DResult(
            id="task-123",
            status=TaskStatus.SUCCEEDED,
            progress=100,
            created_at=1700000000,
            texture_urls=[
                TextureUrls(
                    base_color="https://example.com/base.png",
                    normal="https://example.com/normal.png",
                )
            ],
        )
        assert len(result.texture_urls) == 1
        assert result.texture_urls[0].base_color == "https://example.com/base.png"


class TestImage3DRequest:
    """Tests for Image3DRequest model."""

    def test_minimal_request(self):
        """Test creating request with only required fields."""
        request = Image3DRequest(image_url="https://example.com/image.png")
        assert request.image_url == "https://example.com/image.png"
        assert request.mode == "preview"

    def test_full_request(self):
        """Test creating request with all fields."""
        request = Image3DRequest(
            mode="refine",
            image_url="https://example.com/image.png",
            ai_model="meshy-4",
            topology="triangle",
            target_polycount=5000,
            enable_pbr=True,
        )
        assert request.topology == "triangle"
        assert request.enable_pbr is True


class TestTextTextureRequest:
    """Tests for TextTextureRequest model."""

    def test_minimal_request(self):
        """Test creating request with only required fields."""
        request = TextTextureRequest(
            model_url="https://example.com/model.glb",
            prompt="Wood texture",
        )
        assert request.model_url == "https://example.com/model.glb"
        assert request.prompt == "Wood texture"

    def test_default_values(self):
        """Test default values are set correctly."""
        request = TextTextureRequest(
            model_url="https://example.com/model.glb",
            prompt="Metal texture",
        )
        assert request.resolution == "1024"
        assert request.enable_pbr is True
        assert request.art_style == ArtStyle.REALISTIC


class TestRiggingModels:
    """Tests for rigging-related models."""

    def test_rigging_request_with_task_id(self):
        """Test rigging request using input_task_id."""
        request = RiggingRequest(
            input_task_id="task-123",
            height_meters=1.8,
        )
        assert request.input_task_id == "task-123"
        assert request.height_meters == 1.8

    def test_rigging_request_with_url(self):
        """Test rigging request using model_url."""
        request = RiggingRequest(
            model_url="https://example.com/model.glb",
            texture_image_url="https://example.com/texture.png",
        )
        assert request.model_url == "https://example.com/model.glb"

    def test_rigging_result(self):
        """Test parsing rigging result."""
        result = RiggingResult(
            id="rig-123",
            status=TaskStatus.SUCCEEDED,
            progress=100,
            created_at=1700000000,
            result=RiggingResultData(
                rigged_character_glb_url="https://example.com/rigged.glb",
                basic_animations=BasicAnimations(walking_glb_url="https://example.com/walk.glb"),
            ),
        )
        assert result.result.rigged_character_glb_url == "https://example.com/rigged.glb"
        assert result.result.basic_animations.walking_glb_url == "https://example.com/walk.glb"


class TestAnimationModels:
    """Tests for animation-related models."""

    def test_animation_request(self):
        """Test creating animation request."""
        request = AnimationRequest(
            rig_task_id="rig-123",
            action_id=1,
            loop=True,
            frame_rate=60,
        )
        assert request.rig_task_id == "rig-123"
        assert request.action_id == 1
        assert request.frame_rate == 60

    def test_animation_result(self):
        """Test parsing animation result."""
        result = AnimationResult(
            id="anim-123",
            status=TaskStatus.SUCCEEDED,
            progress=100,
            created_at=1700000000,
            animation_glb_url="https://example.com/anim.glb",
        )
        assert result.animation_glb_url == "https://example.com/anim.glb"


class TestRetextureModels:
    """Tests for retexture-related models."""

    def test_retexture_request(self):
        """Test creating retexture request."""
        request = RetextureRequest(
            input_task_id="task-123",
            text_style_prompt="cyberpunk neon style",
            enable_pbr=True,
        )
        assert request.input_task_id == "task-123"
        assert request.text_style_prompt == "cyberpunk neon style"

    def test_retexture_result(self):
        """Test parsing retexture result."""
        result = RetextureResult(
            id="retex-123",
            status=TaskStatus.SUCCEEDED,
            progress=100,
            created_at=1700000000,
            model_urls=ModelUrls(glb="https://example.com/retextured.glb"),
        )
        assert result.model_urls.glb == "https://example.com/retextured.glb"


class TestAssetSpec:
    """Tests for AssetSpec model."""

    def test_full_spec(self):
        """Test creating a complete game asset spec."""
        spec = AssetSpec(
            intent=AssetIntent.PLAYER_CHARACTER,
            description="A heroic knight in shining armor",
            art_style=ArtStyle.REALISTIC,
            target_polycount=15000,
            enable_pbr=True,
            output_path="models/characters",
            metadata={"faction": "knights"},
        )
        assert spec.intent == AssetIntent.PLAYER_CHARACTER
        assert spec.target_polycount == 15000
        assert spec.metadata["faction"] == "knights"

    def test_asset_intents(self):
        """Test all asset intent values."""
        assert AssetIntent.PLAYER_CHARACTER == "player_character"
        assert AssetIntent.NPC_CHARACTER == "npc_character"
        assert AssetIntent.CREATURE_PREDATOR == "creature_predator"
        assert AssetIntent.PROP_INTERACTABLE == "prop_interactable"
        assert AssetIntent.TERRAIN_ELEMENT == "terrain_element"

    def test_asset_id_optional(self):
        """Test that asset_id is optional."""
        spec = AssetSpec(
            intent=AssetIntent.PROP_DECORATION,
            description="A wooden barrel",
            output_path="models/props",
        )
        assert spec.asset_id is None
