"""Task repository for manifest storage and retrieval."""

from __future__ import annotations

import os
import tempfile

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from extended_data.io import wrap_raw_data_for_export
from extended_data.io.files import DataFile
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.meshy.persistence.schemas import (
    ArtifactRecord,
    AssetManifest,
    ProjectManifest,
    StatusHistoryEntry,
    TaskGraphEntry,
    TaskSubmission,
)
from vendor_fabric.meshy.persistence.utils import compute_spec_hash as util_compute_spec_hash


def _utc_now() -> datetime:
    """Return current UTC time with timezone info."""
    return datetime.now(UTC)


def _manifest_payload(manifest: ProjectManifest) -> dict[str, Any]:
    """Convert an internal project manifest model to a JSON-friendly payload."""
    return manifest.model_dump(mode="json")


def _asset_payload(asset: AssetManifest) -> dict[str, Any]:
    """Convert an internal asset manifest model to a JSON-friendly payload."""
    return asset.model_dump(mode="json")


class TaskRepository:
    """File-backed repository for task manifests with atomic operations."""

    def __init__(self, base_path: str = "client/public/models"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, project: str) -> Path:
        """Get path to project manifest file."""
        return self.base_path / project / "manifest.json"

    def _load_project_manifest_model(self, project: str) -> ProjectManifest:
        """Load the internal project manifest model, creating an empty one if missing."""
        manifest_path = self._manifest_path(project)

        if not manifest_path.exists():
            # Create empty manifest
            manifest = ProjectManifest(project=project)
            self.save_project_manifest(manifest)
            return manifest

        data = DataFile.read(manifest_path, as_extended=False).as_builtin()
        return ProjectManifest(**data)

    def load_project_manifest(self, project: str) -> ExtendedDict:
        """Load manifest for a project, creating empty one if missing.

        Args:
            project: Project name (e.g., "otter", "beaver")

        Returns:
            Extended project manifest payload.
        """
        return cast(ExtendedDict, extend_data(_manifest_payload(self._load_project_manifest_model(project))))

    def save_project_manifest(self, manifest: ProjectManifest) -> None:
        """Atomically save project manifest to disk.

        Args:
            manifest: ProjectManifest to save
        """
        manifest.last_updated = _utc_now()
        manifest_path = self._manifest_path(manifest.project)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize Pydantic model with datetime → ISO string conversion
        manifest_dict = manifest.model_dump(mode="json")

        # Atomic write: write to temp file, then rename
        with tempfile.NamedTemporaryFile(mode="w", dir=manifest_path.parent, delete=False, suffix=".tmp") as tmp_file:
            tmp_file.write(wrap_raw_data_for_export(manifest_dict, allow_encoding="json", indent_2=True))
            tmp_path = tmp_file.name

        # Atomic rename
        os.replace(tmp_path, manifest_path)

    def get_asset_record(self, project: str, spec_hash: str) -> ExtendedDict | None:
        """Get asset manifest by spec hash.

        Args:
            project: Project name
            spec_hash: Asset spec hash

        Returns:
            Extended asset manifest payload if found, None otherwise
        """
        manifest = self._load_project_manifest_model(project)
        asset = manifest.asset_specs.get(spec_hash)
        if asset is None:
            return None
        return cast(ExtendedDict, extend_data(_asset_payload(asset)))

    def upsert_asset_record(self, project: str, asset_manifest: AssetManifest) -> None:
        """Insert or update asset manifest.

        Args:
            project: Project name
            asset_manifest: AssetManifest to save
        """
        manifest = self._load_project_manifest_model(project)
        asset_manifest.updated_at = _utc_now()
        manifest.asset_specs[asset_manifest.asset_spec_hash] = asset_manifest
        self.save_project_manifest(manifest)

    def record_task_update(
        self,
        project: str,
        spec_hash: str,
        task_id: str,
        status: str,
        service: str | None = None,
        payload: dict[str, Any] | None = None,
        result_paths: dict[str, str] | None = None,
        artifacts: list[ArtifactRecord] | None = None,
        source: str = "orchestrator",
        error: str | None = None,
    ) -> None:
        """Record task status update in manifest.

        Args:
            project: Project name
            spec_hash: Asset spec hash
            task_id: Meshy task ID
            status: New status string
            service: Service name (text3d, rigging, etc)
            payload: Request payload
            result_paths: Result URLs/paths
            artifacts: Downloaded artifacts
            source: Update source (orchestrator, webhook, manual)
            error: Error message if failed
        """
        manifest = self._load_project_manifest_model(project)
        asset_record = manifest.asset_specs.get(spec_hash)

        if not asset_record:
            msg = f"Asset {spec_hash} not found for project {project}"
            raise ValueError(msg)

        safe_error = redact_sensitive_text(error) if error else None

        # Find existing task entry or create new
        task_entry = None
        for entry in asset_record.task_graph:
            if entry.task_id == task_id:
                task_entry = entry
                break

        if task_entry:
            # Update existing entry
            old_status = task_entry.status
            task_entry.status = status
            task_entry.updated_at = _utc_now()

            if result_paths:
                task_entry.result_paths.update(result_paths)

            if safe_error:
                task_entry.error = safe_error

            # Record status transition
            asset_record.history.append(
                StatusHistoryEntry(
                    timestamp=_utc_now(),
                    old_status=old_status,
                    new_status=status,
                    source=source,
                    task_id=task_id,
                )
            )

        elif service:
            # Create new task entry
            task_entry = TaskGraphEntry(
                task_id=task_id,
                service=service,
                status=status,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                payload=payload or {},
                result_paths=result_paths or {},
                error=safe_error,
            )
            asset_record.task_graph.append(task_entry)

            # Record initial status
            asset_record.history.append(
                StatusHistoryEntry(
                    timestamp=_utc_now(),
                    old_status="",
                    new_status=status,
                    source=source,
                    task_id=task_id,
                )
            )

        # Add artifacts if provided
        if artifacts:
            asset_record.artifacts.extend(artifacts)

        # Save updated manifest
        self.save_project_manifest(manifest)

    def list_pending_assets(self, project: str) -> ExtendedList[ExtendedDict]:
        """List all assets with pending/in-progress tasks.

        Args:
            project: Project name

        Returns:
            Extended asset manifest payloads with non-terminal tasks
        """
        manifest = self._load_project_manifest_model(project)
        pending: list[dict[str, Any]] = []

        terminal_statuses = {"SUCCEEDED", "FAILED", "EXPIRED", "CANCELED"}

        for asset_record in manifest.asset_specs.values():
            has_pending = any(task.status not in terminal_statuses for task in asset_record.task_graph)
            if has_pending:
                pending.append(_asset_payload(asset_record))

        return cast(ExtendedList[ExtendedDict], extend_data(pending))

    def find_task_by_id(self, task_id: str, project: str | None = None) -> ExtendedDict | None:
        """Find asset by task ID (for webhook lookups).

        Args:
            task_id: Meshy task ID
            project: Optional project to narrow search

        Returns:
            Extended payload with project, spec_hash, and asset if found
        """
        # Determine which project to search
        if project:
            project_list = [project]
        else:
            # Search all project directories
            project_list = [d.name for d in self.base_path.iterdir() if d.is_dir() and (d / "manifest.json").exists()]

        for sp in project_list:
            manifest = self._load_project_manifest_model(sp)
            for spec_hash, asset_record in manifest.asset_specs.items():
                for task in asset_record.task_graph:
                    if task.task_id == task_id:
                        return cast(
                            ExtendedDict,
                            extend_data(
                                {
                                    "project": sp,
                                    "spec_hash": spec_hash,
                                    "asset": _asset_payload(asset_record),
                                }
                            ),
                        )

        return None

    def compute_spec_hash(self, spec: dict[str, Any]) -> str:
        """Compute deterministic hash for task spec.

        Args:
            spec: Task specification dictionary

        Returns:
            SHA256 hex digest of canonicalized spec
        """
        return util_compute_spec_hash(spec)

    def record_task_submission(self, submission: TaskSubmission) -> None:
        """Record a task submission to the manifest (idempotent).

        Args:
            submission: TaskSubmission with task_id, project, service, etc.

        Raises:
            ValueError: If submission data is invalid
        """
        if not submission.task_id:
            msg = "task_id cannot be empty"
            raise ValueError(msg)
        if not submission.callback_url:
            msg = "callback_url cannot be empty"
            raise ValueError(msg)
        if not submission.project:
            msg = "project cannot be empty"
            raise ValueError(msg)
        if not submission.spec_hash:
            msg = "spec_hash cannot be empty"
            raise ValueError(msg)

        manifest = self._load_project_manifest_model(submission.project)

        asset_record = manifest.asset_specs.get(submission.spec_hash)
        if not asset_record:
            asset_record = AssetManifest(
                asset_spec_hash=submission.spec_hash,
                spec_fingerprint=submission.spec_hash,
                project=submission.project,
                asset_intent="creature",
            )
            manifest.asset_specs[submission.spec_hash] = asset_record

        # Idempotency: if task_id already exists with same status, short-circuit (webhook retry)
        for existing_task in asset_record.task_graph:
            if existing_task.task_id == submission.task_id:
                if existing_task.status == submission.status.value:
                    # Duplicate submission with same status - idempotent, return silently
                    return
                else:
                    msg = (
                        f"Task {submission.task_id} already exists with different status: "
                        f"{existing_task.status} != {submission.status.value}"
                    )
                    raise ValueError(msg)

        task_entry = TaskGraphEntry(
            task_id=submission.task_id,
            service=submission.service,
            status=submission.status.value,
            created_at=submission.created_at,
            updated_at=submission.updated_at,
            payload={"callback_url": submission.callback_url},
            result_paths={},
            error=None,
        )
        asset_record.task_graph.append(task_entry)

        asset_record.history.append(
            StatusHistoryEntry(
                timestamp=_utc_now(),
                old_status="",
                new_status=submission.status.value,
                source="service",
                task_id=submission.task_id,
            )
        )

        self.save_project_manifest(manifest)
