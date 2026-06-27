"""Tests for TaskRepository persistence layer."""

from __future__ import annotations

import json

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy.persistence import repository as repository_module
from vendor_fabric.meshy.persistence.repository import TaskRepository
from vendor_fabric.meshy.persistence.schemas import (
    ArtifactRecord,
    AssetManifest,
    ProjectManifest,
    TaskStatus,
    TaskSubmission,
)


class TestTaskRepositoryInit:
    """Tests for TaskRepository initialization."""

    def test_creates_base_directory(self, temp_dir):
        """Test that repository creates base directory."""
        base_path = temp_dir / "new_models"
        TaskRepository(base_path=str(base_path))

        assert base_path.exists()

    def test_uses_existing_directory(self, temp_dir):
        """Test that repository uses existing directory."""
        repo = TaskRepository(base_path=str(temp_dir))
        assert repo.base_path == temp_dir


class TestProjectManifest:
    """Tests for project manifest operations."""

    def test_load_creates_new_manifest(self, task_repository):
        """Test loading non-existent project creates new manifest."""
        manifest = task_repository.load_project_manifest("project1")

        assert isinstance(manifest, ExtendedDict)
        assert manifest["project"] == "project1"
        assert manifest["asset_specs"] == {}
        assert manifest["version"] == "1.0"
        assert isinstance(manifest["last_updated"], ExtendedString)

    def test_load_existing_manifest(self, task_repository, temp_dir):
        """Test loading existing manifest."""
        # Create manifest directly
        project_dir = temp_dir / "project2"
        project_dir.mkdir()
        manifest_path = project_dir / "manifest.json"

        manifest_data = {
            "project": "project2",
            "asset_specs": {},
            "version": "1.0",
            "last_updated": datetime.now(UTC).isoformat(),
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        manifest = task_repository.load_project_manifest("project2")
        assert isinstance(manifest, ExtendedDict)
        assert manifest["project"] == "project2"

    def test_load_existing_manifest_decodes_through_data_file_boundary(self, task_repository, temp_dir):
        """Existing manifests should be read through DataFile, not local json.load."""
        project_dir = temp_dir / "project2"
        project_dir.mkdir()
        manifest_path = project_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "project": "project2",
                    "asset_specs": {},
                    "version": "1.0",
                    "last_updated": datetime.now(UTC).isoformat(),
                }
            )
        )

        with patch(
            "vendor_fabric.meshy.persistence.repository.DataFile.read",
            wraps=repository_module.DataFile.read,
        ) as mock_read:
            manifest = task_repository.load_project_manifest("project2")

        assert manifest["project"] == "project2"
        mock_read.assert_called_once_with(manifest_path, as_extended=False)

    def test_save_and_load_manifest(self, task_repository):
        """Test saving and reloading manifest."""
        manifest = ProjectManifest(project="project1")

        # Add an asset record
        asset = AssetManifest(
            asset_spec_hash="hash-123",
            spec_fingerprint="hash-123",
            project="project1",
            asset_intent="creature",
        )
        manifest.asset_specs["hash-123"] = asset

        task_repository.save_project_manifest(manifest)

        # Reload and verify
        reloaded = task_repository.load_project_manifest("project1")
        assert isinstance(reloaded, ExtendedDict)
        assert "hash-123" in reloaded["asset_specs"]
        assert reloaded["asset_specs"]["hash-123"]["project"] == "project1"

    def test_save_manifest_encodes_through_export_boundary(self, task_repository):
        """Saved manifests should use the shared export boundary."""
        manifest = ProjectManifest(project="project1")

        with patch(
            "vendor_fabric.meshy.persistence.repository.wrap_raw_data_for_export",
            wraps=repository_module.wrap_raw_data_for_export,
        ) as mock_wrap_for_export:
            task_repository.save_project_manifest(manifest)

        assert mock_wrap_for_export.called
        assert mock_wrap_for_export.call_args.kwargs == {"allow_encoding": "json", "indent_2": True}


class TestAssetRecordOperations:
    """Tests for asset record operations."""

    def test_get_asset_record_not_found(self, task_repository):
        """Test getting non-existent asset record."""
        record = task_repository.get_asset_record("project1", "nonexistent-hash")
        assert record is None

    def test_upsert_and_get_asset_record(self, task_repository):
        """Test inserting and retrieving asset record."""
        asset = AssetManifest(
            asset_spec_hash="hash-abc",
            spec_fingerprint="hash-abc",
            project="project1",
            asset_intent="creature",
            prompts={"text3d": "An project1 character"},
        )

        task_repository.upsert_asset_record("project1", asset)

        retrieved = task_repository.get_asset_record("project1", "hash-abc")
        assert retrieved is not None
        assert isinstance(retrieved, ExtendedDict)
        assert retrieved["asset_spec_hash"] == "hash-abc"
        assert retrieved["prompts"]["text3d"] == "An project1 character"
        assert isinstance(retrieved["prompts"]["text3d"], ExtendedString)

    def test_upsert_updates_existing(self, task_repository):
        """Test that upsert updates existing record."""
        asset = AssetManifest(
            asset_spec_hash="hash-abc",
            spec_fingerprint="hash-abc",
            project="project1",
            asset_intent="creature",
        )
        task_repository.upsert_asset_record("project1", asset)

        # Update
        asset.prompts["text3d"] = "Updated prompt"
        task_repository.upsert_asset_record("project1", asset)

        retrieved = task_repository.get_asset_record("project1", "hash-abc")
        assert retrieved is not None
        assert retrieved["prompts"]["text3d"] == "Updated prompt"


class TestTaskSubmission:
    """Tests for task submission recording."""

    def test_record_task_submission(self, task_repository):
        """Test recording a task submission."""
        submission = TaskSubmission(
            task_id="task-12345",
            spec_hash="hash-abc",
            project="project1",
            service="text3d",
            status=TaskStatus.PENDING,
            callback_url="https://example.com/webhook",
        )

        task_repository.record_task_submission(submission)

        # Verify it was saved
        asset = task_repository.get_asset_record("project1", "hash-abc")
        assert asset is not None
        assert len(asset["task_graph"]) == 1
        assert asset["task_graph"][0]["task_id"] == "task-12345"
        assert asset["task_graph"][0]["service"] == "text3d"

    def test_record_duplicate_submission_idempotent(self, task_repository):
        """Test that duplicate submissions are idempotent."""
        submission = TaskSubmission(
            task_id="task-12345",
            spec_hash="hash-abc",
            project="project1",
            service="text3d",
            status=TaskStatus.PENDING,
            callback_url="https://example.com/webhook",
        )

        task_repository.record_task_submission(submission)
        task_repository.record_task_submission(submission)  # Duplicate

        asset = task_repository.get_asset_record("project1", "hash-abc")
        assert asset is not None
        assert len(asset["task_graph"]) == 1  # Still just one task

    def test_record_submission_validates_fields(self, task_repository):
        """Test that submission validation works."""
        with pytest.raises(ValueError, match="task_id cannot be empty"):
            submission = TaskSubmission(
                task_id="",
                spec_hash="hash-abc",
                project="project1",
                service="text3d",
                status=TaskStatus.PENDING,
                callback_url="https://example.com/webhook",
            )
            task_repository.record_task_submission(submission)


class TestTaskUpdate:
    """Tests for task status updates."""

    @pytest.fixture
    def repo_with_task(self, task_repository):
        """Create repository with existing task."""
        submission = TaskSubmission(
            task_id="task-12345",
            spec_hash="hash-abc",
            project="project1",
            service="text3d",
            status=TaskStatus.PENDING,
            callback_url="https://example.com/webhook",
        )
        task_repository.record_task_submission(submission)
        return task_repository

    def test_record_task_update(self, repo_with_task):
        """Test updating task status."""
        repo_with_task.record_task_update(
            project="project1",
            spec_hash="hash-abc",
            task_id="task-12345",
            status="SUCCEEDED",
            result_paths={"glb": "https://example.com/model.glb"},
        )

        asset = repo_with_task.get_asset_record("project1", "hash-abc")
        assert asset is not None
        task = asset["task_graph"][0]
        assert task["status"] == "SUCCEEDED"
        assert task["result_paths"]["glb"] == "https://example.com/model.glb"

    def test_record_task_update_with_error(self, repo_with_task):
        """Test updating task with error."""
        repo_with_task.record_task_update(
            project="project1",
            spec_hash="hash-abc",
            task_id="task-12345",
            status="FAILED",
            error="Generation failed",
        )

        asset = repo_with_task.get_asset_record("project1", "hash-abc")
        assert asset is not None
        task = asset["task_graph"][0]
        assert task["status"] == "FAILED"
        assert task["error"] == "Generation failed"

    def test_record_task_update_redacts_error(self, repo_with_task):
        """Persisted task errors should be redacted at the repository boundary."""
        repo_with_task.record_task_update(
            project="project1",
            spec_hash="hash-abc",
            task_id="task-12345",
            status="FAILED",
            error="Generation failed password=hunter2 Authorization: Bearer raw_token",
        )

        asset = repo_with_task.get_asset_record("project1", "hash-abc")
        assert asset is not None
        task = asset["task_graph"][0]
        assert "hunter2" not in task["error"]
        assert "raw_token" not in task["error"]
        assert "[REDACTED]" in task["error"]

    def test_record_task_update_adds_history(self, repo_with_task):
        """Test that updates add history entries."""
        repo_with_task.record_task_update(
            project="project1",
            spec_hash="hash-abc",
            task_id="task-12345",
            status="SUCCEEDED",
            source="webhook",
        )

        asset = repo_with_task.get_asset_record("project1", "hash-abc")
        assert asset is not None
        assert len(asset["history"]) >= 1

        # Find the update entry
        update_entry = None
        for entry in asset["history"]:
            if entry["new_status"] == "SUCCEEDED":
                update_entry = entry
                break

        assert update_entry is not None
        assert update_entry["source"] == "webhook"

    def test_record_task_update_not_found_raises(self, task_repository):
        """Test that updating non-existent asset raises."""
        with pytest.raises(ValueError, match="not found"):
            task_repository.record_task_update(
                project="project1",
                spec_hash="nonexistent",
                task_id="task-123",
                status="SUCCEEDED",
            )

    def test_record_task_update_with_artifacts(self, repo_with_task):
        """Test recording artifacts with update."""
        artifact = ArtifactRecord(
            relative_path="hash-abc_text3d.glb",
            sha256_hash="abc123def456",
            file_size_bytes=10000,
            downloaded_at=datetime.now(UTC),
            source_url="https://example.com/model.glb",
        )

        repo_with_task.record_task_update(
            project="project1",
            spec_hash="hash-abc",
            task_id="task-12345",
            status="SUCCEEDED",
            artifacts=[artifact],
        )

        asset = repo_with_task.get_asset_record("project1", "hash-abc")
        assert asset is not None
        assert len(asset["artifacts"]) == 1
        assert asset["artifacts"][0]["relative_path"] == "hash-abc_text3d.glb"


class TestTaskLookup:
    """Tests for task lookup operations."""

    @pytest.fixture
    def repo_with_tasks(self, task_repository):
        """Create repository with multiple project and tasks."""
        for project in ["project1", "project2"]:
            submission = TaskSubmission(
                task_id=f"task-{project}-123",
                spec_hash=f"hash-{project}",
                project=project,
                service="text3d",
                status=TaskStatus.PENDING,
                callback_url="https://example.com/webhook",
            )
            task_repository.record_task_submission(submission)
        return task_repository

    def test_find_task_by_id_with_project(self, repo_with_tasks):
        """Test finding task with project hint."""
        result = repo_with_tasks.find_task_by_id("task-project1-123", project="project1")

        assert result is not None
        assert isinstance(result, ExtendedDict)
        assert result["project"] == "project1"
        assert result["spec_hash"] == "hash-project1"
        assert result["asset"]["asset_spec_hash"] == "hash-project1"

    def test_find_task_by_id_without_project(self, repo_with_tasks):
        """Test finding task by scanning all project."""
        result = repo_with_tasks.find_task_by_id("task-project2-123")

        assert result is not None
        assert isinstance(result, ExtendedDict)
        assert result["project"] == "project2"

    def test_find_task_not_found(self, repo_with_tasks):
        """Test finding non-existent task."""
        result = repo_with_tasks.find_task_by_id("nonexistent-task")
        assert result is None


class TestPendingAssets:
    """Tests for listing pending assets."""

    def test_list_pending_assets(self, task_repository):
        """Test listing assets with pending tasks."""
        # Create pending task
        submission = TaskSubmission(
            task_id="task-pending",
            spec_hash="hash-pending",
            project="project1",
            service="text3d",
            status=TaskStatus.PENDING,
            callback_url="https://example.com/webhook",
        )
        task_repository.record_task_submission(submission)

        pending = task_repository.list_pending_assets("project1")
        assert isinstance(pending, ExtendedList)
        assert len(pending) == 1
        assert pending[0]["asset_spec_hash"] == "hash-pending"

    def test_list_pending_excludes_completed(self, task_repository):
        """Test that completed assets are not listed."""
        # Create and complete a task
        submission = TaskSubmission(
            task_id="task-done",
            spec_hash="hash-done",
            project="project1",
            service="text3d",
            status=TaskStatus.PENDING,
            callback_url="https://example.com/webhook",
        )
        task_repository.record_task_submission(submission)

        task_repository.record_task_update(
            project="project1",
            spec_hash="hash-done",
            task_id="task-done",
            status="SUCCEEDED",
        )

        pending = task_repository.list_pending_assets("project1")
        assert len(pending) == 0


class TestSpecHash:
    """Tests for spec hash computation."""

    def test_compute_spec_hash_deterministic(self, task_repository):
        """Test that spec hash is deterministic."""
        spec = {"prompt": "An project1", "art_style": "realistic"}

        hash1 = task_repository.compute_spec_hash(spec)
        hash2 = task_repository.compute_spec_hash(spec)

        assert hash1 == hash2

    def test_compute_spec_hash_different_for_different_specs(self, task_repository):
        """Test that different specs get different hashes."""
        spec1 = {"prompt": "An project1"}
        spec2 = {"prompt": "A project2"}

        hash1 = task_repository.compute_spec_hash(spec1)
        hash2 = task_repository.compute_spec_hash(spec2)

        assert hash1 != hash2

    def test_compute_spec_hash_order_independent(self, task_repository):
        """Test that key order doesn't affect hash."""
        spec1 = {"a": 1, "b": 2}
        spec2 = {"b": 2, "a": 1}

        hash1 = task_repository.compute_spec_hash(spec1)
        hash2 = task_repository.compute_spec_hash(spec2)

        assert hash1 == hash2
