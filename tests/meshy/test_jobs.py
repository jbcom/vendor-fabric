"""Tests for job orchestration (AssetGenerator)."""

from __future__ import annotations

import json

from unittest.mock import patch

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data

from cloud_connectors.meshy import jobs as jobs_module
from cloud_connectors.meshy.jobs import (
    AssetGenerator,
    AssetManifest,
    example_character_spec,
    example_environment_spec,
    example_prop_spec,
)
from cloud_connectors.meshy.models import (
    ArtStyle,
    AssetIntent,
    AssetSpec,
    ModelUrls,
    TaskStatus,
    Text3DResult,
    TextureUrls,
)


def _extended_result(result: Text3DResult) -> ExtendedDict:
    return extend_data(result.model_dump(mode="json"))


class TestAssetManifest:
    """Tests for AssetManifest dataclass."""

    def test_create_manifest(self):
        """Test creating an asset manifest."""
        manifest = AssetManifest(
            asset_id="project1-001",
            intent="player_character",
            description="An project1 character",
            art_style="realistic",
            task_id="task-123",
        )
        assert manifest.asset_id == "project1-001"
        assert manifest.intent == "player_character"
        assert manifest.task_id == "task-123"

    def test_manifest_to_dict(self):
        """Test converting manifest to dictionary."""
        manifest = AssetManifest(
            asset_id="test-001",
            intent="prop",
            description="A test prop",
            art_style="cartoon",
            model_path="models/test.glb",
        )
        data = manifest.to_dict()
        assert isinstance(data, ExtendedDict)
        assert isinstance(data["asset_id"], ExtendedString)
        assert data["asset_id"] == "test-001"
        assert data["model_path"] == "models/test.glb"

    def test_manifest_default_metadata(self):
        """Test that metadata defaults to empty dict."""
        manifest = AssetManifest(
            asset_id="test",
            intent="prop",
            description="Test",
            art_style="realistic",
        )
        assert manifest.metadata == {}


class TestAssetGenerator:
    """Tests for AssetGenerator."""

    def test_generate_asset_id_from_spec(self):
        """Test asset ID generation from spec."""
        generator = AssetGenerator()

        spec = AssetSpec(
            intent=AssetIntent.PLAYER_CHARACTER,
            description="Test character",
            output_path="models/test",
            asset_id="custom-id-123",
        )

        asset_id = generator._generate_asset_id(spec)
        assert asset_id == "custom-id-123"

    def test_generate_asset_id_from_slug(self):
        """Test asset ID generation from metadata slug."""
        generator = AssetGenerator()

        spec = AssetSpec(
            intent=AssetIntent.NPC_CHARACTER,
            description="Test NPC",
            output_path="models/test",
            metadata={"slug": "npc-vendor"},
        )

        asset_id = generator._generate_asset_id(spec)
        assert asset_id == "npc-vendor"

    def test_generate_asset_id_from_hash(self):
        """Test asset ID generation from description hash."""
        generator = AssetGenerator()

        spec = AssetSpec(
            intent=AssetIntent.PROP_DECORATION,
            description="A unique barrel",
            output_path="models/props",
        )

        asset_id = generator._generate_asset_id(spec)
        assert asset_id.startswith("prop_decoration_")
        assert len(asset_id) > len("prop_decoration_")

    def test_generate_model_no_wait(self, temp_dir):
        """Test generating model without waiting."""
        with patch("cloud_connectors.meshy.jobs.text3d") as mock_text3d:
            mock_text3d.create.return_value = "task-12345"

            generator = AssetGenerator(output_root=str(temp_dir))

            spec = AssetSpec(
                intent=AssetIntent.PLAYER_CHARACTER,
                description="An project1 character",
                output_path="models/characters",
                asset_id="project1-001",
            )

            manifest = generator.generate_model(spec, wait=False)

            assert isinstance(manifest, ExtendedDict)
            assert isinstance(manifest["asset_id"], ExtendedString)
            assert manifest["asset_id"] == "project1-001"
            assert manifest["task_id"] == "task-12345"
            assert manifest["model_path"] is None  # Not downloaded yet
            mock_text3d.create.assert_called_once()

    def test_generate_model_with_wait(self, temp_dir):
        """Test generating model with polling."""
        with (
            patch("cloud_connectors.meshy.jobs.text3d") as mock_text3d,
            patch("cloud_connectors.meshy.jobs.base") as mock_base,
        ):
            mock_text3d.create.return_value = "task-12345"
            mock_text3d.poll.return_value = _extended_result(
                Text3DResult(
                    id="task-12345",
                    status=TaskStatus.SUCCEEDED,
                    progress=100,
                    created_at=1700000000,
                    model_urls=ModelUrls(glb="https://example.com/model.glb"),
                    texture_urls=[TextureUrls(base_color="https://example.com/base.png")],
                    thumbnail_url="https://example.com/thumb.png",
                )
            )
            mock_base.download.return_value = 1000

            generator = AssetGenerator(output_root=str(temp_dir))

            spec = AssetSpec(
                intent=AssetIntent.PLAYER_CHARACTER,
                description="An project1 character",
                output_path="models/characters",
                asset_id="project1-001",
            )

            manifest = generator.generate_model(spec, wait=True, poll_interval=0.01)

            assert isinstance(manifest, ExtendedDict)
            assert manifest["asset_id"] == "project1-001"
            assert manifest["model_path"] is not None
            assert "project1-001.glb" in manifest["model_path"]
            mock_base.download.assert_called()

    def test_generate_model_saves_manifest_json(self, temp_dir):
        """Test that manifest JSON is saved."""
        with (
            patch("cloud_connectors.meshy.jobs.text3d") as mock_text3d,
            patch("cloud_connectors.meshy.jobs.base") as mock_base,
        ):
            mock_text3d.create.return_value = "task-12345"
            mock_text3d.poll.return_value = _extended_result(
                Text3DResult(
                    id="task-12345",
                    status=TaskStatus.SUCCEEDED,
                    progress=100,
                    created_at=1700000000,
                    model_urls=ModelUrls(glb="https://example.com/model.glb"),
                )
            )
            mock_base.download.return_value = 1000

            generator = AssetGenerator(output_root=str(temp_dir))

            spec = AssetSpec(
                intent=AssetIntent.PROP_DECORATION,
                description="A barrel",
                output_path="models/props",
                asset_id="barrel-001",
            )

            with patch(
                "cloud_connectors.meshy.jobs.wrap_raw_data_for_export",
                wraps=jobs_module.wrap_raw_data_for_export,
            ) as mock_wrap_for_export:
                generator.generate_model(spec, wait=True, poll_interval=0.01)

            manifest_path = temp_dir / "models" / "props" / "barrel-001_manifest.json"
            assert manifest_path.exists()

            with open(manifest_path) as f:
                saved_manifest = json.load(f)
            assert saved_manifest["asset_id"] == "barrel-001"
            mock_wrap_for_export.assert_called_once()
            assert mock_wrap_for_export.call_args.kwargs == {"allow_encoding": "json", "indent_2": True}

    def test_batch_generate(self, temp_dir):
        """Test batch generation of multiple assets."""
        with (
            patch("cloud_connectors.meshy.jobs.text3d") as mock_text3d,
            patch("cloud_connectors.meshy.jobs.base") as mock_base,
        ):
            mock_text3d.create.return_value = "task-12345"
            mock_text3d.poll.return_value = _extended_result(
                Text3DResult(
                    id="task-12345",
                    status=TaskStatus.SUCCEEDED,
                    progress=100,
                    created_at=1700000000,
                    model_urls=ModelUrls(glb="https://example.com/model.glb"),
                )
            )
            mock_base.download.return_value = 1000

            generator = AssetGenerator(output_root=str(temp_dir))

            specs = [
                AssetSpec(
                    intent=AssetIntent.PROP_DECORATION,
                    description="Item 1",
                    output_path="models/props",
                    asset_id="item-001",
                ),
                AssetSpec(
                    intent=AssetIntent.PROP_DECORATION,
                    description="Item 2",
                    output_path="models/props",
                    asset_id="item-002",
                ),
            ]

            manifests = generator.batch_generate(specs)

            assert isinstance(manifests, ExtendedList)
            assert isinstance(manifests[0], ExtendedDict)
            assert len(manifests) == 2
            assert manifests[0]["asset_id"] == "item-001"
            assert manifests[1]["asset_id"] == "item-002"

    def test_batch_generate_continues_on_failure(self, temp_dir):
        """Test that batch generation continues if one fails."""
        with (
            patch("cloud_connectors.meshy.jobs.text3d") as mock_text3d,
            patch("cloud_connectors.meshy.jobs.base") as mock_base,
        ):
            call_count = [0]

            def create_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    msg = "First task failed"
                    raise RuntimeError(msg)
                return "task-success"

            mock_text3d.create.side_effect = create_side_effect
            mock_text3d.poll.return_value = _extended_result(
                Text3DResult(
                    id="task-success",
                    status=TaskStatus.SUCCEEDED,
                    progress=100,
                    created_at=1700000000,
                    model_urls=ModelUrls(glb="https://example.com/model.glb"),
                )
            )
            mock_base.download.return_value = 1000

            generator = AssetGenerator(output_root=str(temp_dir))

            specs = [
                AssetSpec(
                    intent=AssetIntent.PROP_DECORATION,
                    description="Will fail",
                    output_path="models/props",
                    asset_id="fail-001",
                ),
                AssetSpec(
                    intent=AssetIntent.PROP_DECORATION,
                    description="Will succeed",
                    output_path="models/props",
                    asset_id="success-001",
                ),
            ]

            manifests = generator.batch_generate(specs)

            # Only the successful one should be in results
            assert isinstance(manifests, ExtendedList)
            assert len(manifests) == 1
            assert manifests[0]["asset_id"] == "success-001"


class TestExampleSpecs:
    """Tests for example asset specs."""

    def test_example_character_spec(self):
        """Test character example preset."""
        spec = example_character_spec()
        assert spec.intent == AssetIntent.PLAYER_CHARACTER
        assert spec.art_style == ArtStyle.REALISTIC
        assert spec.target_polycount == 15000
        assert "character" in spec.description.lower()

    def test_example_prop_spec(self):
        """Test prop example preset."""
        spec = example_prop_spec()
        assert spec.intent == AssetIntent.PROP_INTERACTABLE
        assert spec.target_polycount == 5000
        assert "crate" in spec.description.lower()

    def test_example_environment_spec(self):
        """Test environment example preset."""
        spec = example_environment_spec()
        assert spec.intent == AssetIntent.TERRAIN_ELEMENT
        assert spec.target_polycount == 8000
        assert "rock" in spec.description.lower()
