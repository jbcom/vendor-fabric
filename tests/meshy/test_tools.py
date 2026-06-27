"""Tests for cloud_connectors.meshy.tools module.

Tests tool implementations with mocked Meshy API calls.
Framework-specific tools (LangChain, CrewAI) are tested separately
since those frameworks are optional dependencies.
"""

from __future__ import annotations

import importlib.util

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data


# Expected tools list - canonical reference for all Meshy tools
EXPECTED_MESHY_TOOLS = {
    "text3d_generate",
    "image3d_generate",
    "rig_model",
    "apply_animation",
    "retexture_model",
    "list_animations",
    "check_task_status",
    "get_animation",
}


class TestToolDefinitions:
    """Tests for TOOL_DEFINITIONS metadata."""

    def test_tool_definitions_has_all_tools(self):
        """Test that TOOL_DEFINITIONS contains all expected tools."""
        from cloud_connectors.meshy.tools import TOOL_DEFINITIONS

        tool_names = {defn["name"] for defn in TOOL_DEFINITIONS}
        assert tool_names == EXPECTED_MESHY_TOOLS

    def test_tool_definitions_have_required_fields(self):
        """Test that each tool definition has func, name, description."""
        from cloud_connectors.meshy.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "func" in defn, f"Missing 'func' in {defn.get('name')}"
            assert "name" in defn, "Missing 'name' in tool definition"
            assert "description" in defn, f"Missing 'description' in {defn.get('name')}"
            assert callable(defn["func"]), f"'func' not callable in {defn['name']}"


class TestStrandsTools:
    """Tests for Strands/plain function tools (always available)."""

    def test_get_strands_tools_returns_functions(self):
        """Test that get_strands_tools returns plain functions."""
        from cloud_connectors.meshy.tools import get_strands_tools

        tools = get_strands_tools()
        assert isinstance(tools, list)
        assert len(tools) == len(EXPECTED_MESHY_TOOLS)
        assert all(callable(t) for t in tools)


class TestText3DGenerate:
    """Tests for text3d_generate function."""

    def test_successful_generation(self):
        """Test successful 3D model generation."""
        from cloud_connectors.meshy.tools import text3d_generate

        # Mock the meshy module
        mock_result = MagicMock()
        mock_result.id = "task_123"
        mock_result.status.value = "SUCCEEDED"
        mock_result.model_urls = MagicMock()
        mock_result.model_urls.glb = "https://example.com/model.glb"
        mock_result.thumbnail_url = "https://example.com/thumb.png"

        with patch("cloud_connectors.meshy.text3d.generate", return_value=mock_result):
            result = text3d_generate(
                prompt="a medieval sword",
                art_style="realistic",
            )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["task_id"], ExtendedString)
        assert result["task_id"] == "task_123"
        assert result["status"] == "SUCCEEDED"
        assert result["model_url"] == "https://example.com/model.glb"
        assert result["thumbnail_url"] == "https://example.com/thumb.png"

    def test_successful_generation_accepts_extended_payload(self):
        """Tool wrapper should consume the real extended result payload shape."""
        from cloud_connectors.meshy.tools import text3d_generate

        mock_result = extend_data(
            {
                "id": "task_123",
                "status": "SUCCEEDED",
                "model_urls": {"glb": "https://example.com/model.glb"},
                "thumbnail_url": "https://example.com/thumb.png",
            }
        )

        with patch("cloud_connectors.meshy.text3d.generate", return_value=mock_result):
            result = text3d_generate(prompt="a medieval sword")

        assert isinstance(result, ExtendedDict)
        assert result["task_id"] == "task_123"
        assert result["status"] == "SUCCEEDED"
        assert result["model_url"] == "https://example.com/model.glb"

    def test_generation_with_defaults(self):
        """Test generation with default parameters.

        Per Meshy API docs, defaults are:
        - art_style: realistic
        - target_polycount: 30000
        """
        from cloud_connectors.meshy.tools import text3d_generate

        mock_result = MagicMock()
        mock_result.id = "task_456"
        mock_result.status.value = "SUCCEEDED"
        mock_result.model_urls = MagicMock()
        mock_result.model_urls.glb = "https://example.com/model.glb"
        mock_result.thumbnail_url = None

        with patch("cloud_connectors.meshy.text3d.generate", return_value=mock_result) as mock_gen:
            result = text3d_generate(prompt="test prompt")

            # Verify defaults were used (per Meshy API docs)
            mock_gen.assert_called_once_with(
                "test prompt",
                art_style="realistic",
                negative_prompt="",
                target_polycount=30000,
                enable_pbr=True,
                wait=True,
            )

        assert isinstance(result, ExtendedDict)
        assert result["task_id"] == "task_456"


class TestImage3DGenerate:
    """Tests for image3d_generate function."""

    def test_successful_image_to_3d(self):
        """Test successful image-to-3D generation."""
        from cloud_connectors.meshy.tools import image3d_generate

        mock_result = MagicMock()
        mock_result.id = "img_task_456"
        mock_result.status.value = "SUCCEEDED"
        mock_result.model_urls = MagicMock()
        mock_result.model_urls.glb = "https://example.com/img_model.glb"
        mock_result.thumbnail_url = None

        with patch("cloud_connectors.meshy.image3d.generate", return_value=mock_result):
            result = image3d_generate(
                image_url="https://example.com/image.png",
                topology="quad",
            )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["model_url"], ExtendedString)
        assert result["task_id"] == "img_task_456"
        assert result["status"] == "SUCCEEDED"
        assert result["model_url"] == "https://example.com/img_model.glb"


class TestRigModel:
    """Tests for rig_model function."""

    def test_successful_rigging_with_wait(self):
        """Test successful model rigging with wait=True."""
        from cloud_connectors.meshy.tools import rig_model

        mock_result = MagicMock()
        mock_result.id = "rig_789"
        mock_result.status.value = "SUCCEEDED"

        with patch("cloud_connectors.meshy.rigging.rig", return_value=mock_result):
            result = rig_model(model_id="model_123", wait=True)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["message"], ExtendedString)
        assert result["task_id"] == "rig_789"
        assert result["status"] == "SUCCEEDED"
        assert "Rigging completed" in result["message"]

    def test_rigging_without_wait(self):
        """Test model rigging with wait=False."""
        from cloud_connectors.meshy.tools import rig_model

        # When wait=False, rigging.rig returns just the task_id string
        with patch("cloud_connectors.meshy.rigging.rig", return_value="pending_rig_task"):
            result = rig_model(model_id="model_123", wait=False)

        assert isinstance(result, ExtendedDict)
        assert result["task_id"] == "pending_rig_task"
        assert result["status"] == "pending"


class TestApplyAnimation:
    """Tests for apply_animation function."""

    def test_successful_animation(self):
        """Test successful animation application."""
        from cloud_connectors.meshy.tools import apply_animation

        mock_result = MagicMock()
        mock_result.id = "anim_task_123"
        mock_result.status.value = "SUCCEEDED"
        mock_result.animation_glb_url = "https://example.com/animated.glb"

        with patch("cloud_connectors.meshy.animate.apply", return_value=mock_result):
            result = apply_animation(
                model_id="rigged_model",
                animation_id=42,
                wait=True,
            )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["glb_url"], ExtendedString)
        assert result["task_id"] == "anim_task_123"
        assert result["status"] == "SUCCEEDED"
        assert result["glb_url"] == "https://example.com/animated.glb"

    def test_animation_without_wait(self):
        """Test animation without waiting."""
        from cloud_connectors.meshy.tools import apply_animation

        with patch("cloud_connectors.meshy.animate.apply", return_value="anim_pending"):
            result = apply_animation(
                model_id="model",
                animation_id=1,
                wait=False,
            )

        assert isinstance(result, ExtendedDict)
        assert result["task_id"] == "anim_pending"
        assert result["status"] == "pending"


class TestRetextureModel:
    """Tests for retexture_model function."""

    def test_successful_retexture(self):
        """Test successful retexturing."""
        from cloud_connectors.meshy.tools import retexture_model

        mock_result = MagicMock()
        mock_result.id = "retex_123"
        mock_result.status.value = "SUCCEEDED"
        mock_result.model_url = "https://example.com/retextured.glb"

        with patch("cloud_connectors.meshy.retexture.apply", return_value=mock_result):
            result = retexture_model(
                model_id="original_model",
                texture_prompt="golden metallic finish",
            )

        assert isinstance(result, ExtendedDict)
        assert result["task_id"] == "retex_123"
        assert result["status"] == "SUCCEEDED"


class TestListAnimations:
    """Tests for list_animations function."""

    def test_list_all_animations(self):
        """Test listing all animations."""
        from cloud_connectors.meshy.tools import list_animations

        # Create mock animations
        mock_anim_1 = MagicMock()
        mock_anim_1.id = 1
        mock_anim_1.name = "Walk"
        mock_anim_1.category = "Movement"
        mock_anim_1.subcategory = "Basic"

        mock_anim_2 = MagicMock()
        mock_anim_2.id = 2
        mock_anim_2.name = "Run"
        mock_anim_2.category = "Movement"
        mock_anim_2.subcategory = "Basic"

        mock_animations = {1: mock_anim_1, 2: mock_anim_2}

        with patch("cloud_connectors.meshy.animations.ANIMATIONS", mock_animations):
            result = list_animations()

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["animations"], ExtendedList)
        assert isinstance(result["animations"][0], ExtendedDict)
        assert result["count"] == 2
        assert result["total"] == 2
        assert len(result["animations"]) == 2

    def test_list_animations_with_category_filter(self):
        """Test listing animations with category filter."""
        from cloud_connectors.meshy.tools import list_animations

        mock_anim_fight = MagicMock()
        mock_anim_fight.id = 1
        mock_anim_fight.name = "Punch"
        mock_anim_fight.category = "Fighting"
        mock_anim_fight.subcategory = "Combat"

        mock_anim_walk = MagicMock()
        mock_anim_walk.id = 2
        mock_anim_walk.name = "Walk"
        mock_anim_walk.category = "Movement"
        mock_anim_walk.subcategory = "Basic"

        mock_animations = {1: mock_anim_fight, 2: mock_anim_walk}

        with patch("cloud_connectors.meshy.animations.ANIMATIONS", mock_animations):
            result = list_animations(category="Fighting")

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["animations"][0]["name"], ExtendedString)
        assert result["count"] == 1
        assert result["animations"][0]["name"] == "Punch"

    def test_list_animations_with_limit(self):
        """Test listing animations with limit."""
        from cloud_connectors.meshy.tools import list_animations

        mock_animations = {}
        for i in range(100):
            mock_anim = MagicMock()
            mock_anim.id = i
            mock_anim.name = f"Animation_{i}"
            mock_anim.category = "Test"
            mock_anim.subcategory = "Test"
            mock_animations[i] = mock_anim

        with patch("cloud_connectors.meshy.animations.ANIMATIONS", mock_animations):
            result = list_animations(limit=10)

        assert result["count"] == 10
        assert result["total"] == 100


class TestCheckTaskStatus:
    """Tests for check_task_status function."""

    def test_check_text3d_status(self):
        """Test checking text-to-3D task status."""
        from cloud_connectors.meshy.tools import check_task_status

        mock_result = MagicMock()
        mock_result.status.value = "SUCCEEDED"
        mock_result.progress = 100
        mock_result.model_urls = MagicMock()
        mock_result.model_urls.glb = "https://example.com/model.glb"

        with patch("cloud_connectors.meshy.text3d.get", return_value=mock_result):
            result = check_task_status(
                task_id="task_123",
                task_type="text-to-3d",
            )

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["task_id"], ExtendedString)
        assert result["task_id"] == "task_123"
        assert result["status"] == "SUCCEEDED"
        assert result["progress"] == 100
        assert result["model_url"] == "https://example.com/model.glb"

    def test_check_text3d_status_accepts_extended_payload(self):
        """Task status wrapper should consume the real extended get() payload."""
        from cloud_connectors.meshy.tools import check_task_status

        mock_result = extend_data(
            {
                "status": "SUCCEEDED",
                "progress": 100,
                "model_urls": {"glb": "https://example.com/model.glb"},
            }
        )

        with patch("cloud_connectors.meshy.text3d.get", return_value=mock_result):
            result = check_task_status(task_id="task_123", task_type="text-to-3d")

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "SUCCEEDED"
        assert result["progress"] == 100
        assert result["model_url"] == "https://example.com/model.glb"

    def test_check_unknown_task_type(self):
        """Test checking unknown task type."""
        from cloud_connectors.meshy.tools import check_task_status

        with pytest.raises(ValueError, match="Unknown task type"):
            check_task_status(
                task_id="task_123",
                task_type="invalid-type",
            )


class TestGetAnimation:
    """Tests for get_animation function."""

    def test_get_existing_animation(self):
        """Test getting an existing animation."""
        from cloud_connectors.meshy.tools import get_animation

        mock_anim = MagicMock()
        mock_anim.id = 42
        mock_anim.name = "Dance"
        mock_anim.category = "Dancing"
        mock_anim.subcategory = "Casual"
        mock_anim.preview_url = "https://example.com/preview.gif"

        with patch("cloud_connectors.meshy.animations.ANIMATIONS", {42: mock_anim}):
            result = get_animation(animation_id=42)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["name"], ExtendedString)
        assert result["id"] == 42
        assert result["name"] == "Dance"
        assert result["preview_url"] == "https://example.com/preview.gif"

    def test_get_nonexistent_animation(self):
        """Test getting a nonexistent animation."""
        from cloud_connectors.meshy.tools import get_animation

        with patch("cloud_connectors.meshy.animations.ANIMATIONS", {}):
            with pytest.raises(ValueError, match="not found"):
                get_animation(animation_id=999)


class TestLangChainTools:
    """Tests for LangChain tools (optional dependency)."""

    @pytest.mark.skipif(
        importlib.util.find_spec("langchain_core") is None,
        reason="langchain-core not installed",
    )
    def test_get_langchain_tools_returns_structured_tools(self):
        """Test that get_langchain_tools returns LangChain StructuredTools."""
        from cloud_connectors.meshy.tools import get_langchain_tools

        tools = get_langchain_tools()
        assert isinstance(tools, list)
        assert len(tools) == len(EXPECTED_MESHY_TOOLS)

        # Verify they're StructuredTools
        from langchain_core.tools import StructuredTool

        for tool in tools:
            assert isinstance(tool, StructuredTool)

        # Verify names
        tool_names = {t.name for t in tools}
        assert tool_names == EXPECTED_MESHY_TOOLS


class TestCrewAITools:
    """Tests for CrewAI tools integration (optional dependency)."""

    def test_get_crewai_tools_requires_crewai(self):
        """Test that get_crewai_tools raises ImportError without crewai."""
        with patch.dict("sys.modules", {"crewai": None, "crewai.tools": None}):
            from cloud_connectors.meshy import tools as meshy_tools

            with pytest.raises(ImportError, match="crewai is required"):
                meshy_tools.get_crewai_tools()


class TestAutoDetection:
    """Tests for framework auto-detection."""

    def test_get_tools_with_explicit_framework(self):
        """Test get_tools with explicit framework selection."""
        from cloud_connectors.meshy.tools import get_tools

        # Strands always works because it returns plain functions.
        tools = get_tools("strands")
        assert isinstance(tools, list)
        assert all(callable(t) for t in tools)

    def test_get_tools_rejects_functions_alias(self):
        """Plain-function tools should use the canonical strands framework name."""
        from cloud_connectors.meshy.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools("functions")

    def test_get_tools_invalid_framework(self):
        """Test get_tools raises ValueError for invalid framework."""
        from cloud_connectors.meshy.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools("invalid_framework")
