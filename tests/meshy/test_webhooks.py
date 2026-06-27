"""Tests for webhook handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedString, extend_data

from cloud_connectors.meshy.persistence.schemas import (
    AssetManifest,
    TaskGraphEntry,
)
from cloud_connectors.meshy.webhooks.handler import WebhookHandler
from cloud_connectors.meshy.webhooks.schemas import (
    MeshyWebhookPayload,
    WebhookModelUrls,
    WebhookRiggingResult,
)


def _task_lookup_payload(project: str, spec_hash: str, asset_manifest: AssetManifest) -> ExtendedDict:
    """Build the repository task lookup payload shape."""
    return extend_data(
        {
            "project": project,
            "spec_hash": spec_hash,
            "asset": asset_manifest.model_dump(mode="json"),
        }
    )


class TestMeshyWebhookPayload:
    """Tests for MeshyWebhookPayload schema."""

    def test_parse_succeeded_payload(self, webhook_payload_succeeded):
        """Test parsing a successful webhook payload."""
        payload = MeshyWebhookPayload(**webhook_payload_succeeded)
        assert payload.id == "task-12345-abcde"
        assert payload.status == "SUCCEEDED"
        assert payload.progress == 100

    def test_parse_failed_payload(self, webhook_payload_failed):
        """Test parsing a failed webhook payload."""
        payload = MeshyWebhookPayload(**webhook_payload_failed)
        assert payload.id == "task-failed-xyz"
        assert payload.status == "FAILED"
        assert payload.task_error is not None
        assert payload.task_error.message == "Generation failed due to invalid prompt"

    def test_get_error_message(self, webhook_payload_failed):
        """Test extracting error message."""
        payload = MeshyWebhookPayload(**webhook_payload_failed)
        error = payload.get_error_message()
        assert error == "Generation failed due to invalid prompt"

    def test_get_error_message_none(self, webhook_payload_succeeded):
        """Test error message when no error."""
        payload = MeshyWebhookPayload(**webhook_payload_succeeded)
        assert payload.get_error_message() is None

    def test_get_glb_url_from_model_urls(self):
        """Test getting GLB URL from model_urls."""
        payload = MeshyWebhookPayload(
            id="task-123",
            status="SUCCEEDED",
            created_at=1700000000,
            model_urls=WebhookModelUrls(glb="https://example.com/model.glb"),
        )
        assert payload.get_glb_url() == "https://example.com/model.glb"

    def test_get_glb_url_from_rigging_result(self):
        """Test getting GLB URL from rigging result."""
        payload = MeshyWebhookPayload(
            id="rig-123",
            status="SUCCEEDED",
            created_at=1700000000,
            result=WebhookRiggingResult(rigged_character_glb_url="https://example.com/rigged.glb"),
        )
        assert payload.get_glb_url() == "https://example.com/rigged.glb"

    def test_get_glb_url_from_animation(self):
        """Test getting GLB URL from animation result."""
        payload = MeshyWebhookPayload(
            id="anim-123",
            status="SUCCEEDED",
            created_at=1700000000,
            animation_glb_url="https://example.com/anim.glb",
        )
        assert payload.get_glb_url() == "https://example.com/anim.glb"

    def test_get_all_urls(self):
        """Test getting all URLs."""
        payload = MeshyWebhookPayload(
            id="task-123",
            status="SUCCEEDED",
            created_at=1700000000,
            model_urls=WebhookModelUrls(
                glb="https://example.com/model.glb",
                fbx="https://example.com/model.fbx",
            ),
            thumbnail_url="https://example.com/thumb.png",
        )
        urls = payload.get_all_urls()
        assert isinstance(urls, ExtendedDict)
        assert isinstance(urls["glb"], ExtendedString)
        assert urls["glb"] == "https://example.com/model.glb"
        assert urls["fbx"] == "https://example.com/model.fbx"
        assert urls["thumbnail"] == "https://example.com/thumb.png"


class TestWebhookHandler:
    """Tests for WebhookHandler."""

    @pytest.fixture
    def mock_repository(self, temp_dir):
        """Create mock repository with task lookup."""
        repo = MagicMock()
        repo.base_path = temp_dir

        # Create a mock asset manifest with task graph
        asset_manifest = AssetManifest(
            asset_spec_hash="hash-abc123",
            spec_fingerprint="hash-abc123",
            project="project1",
            asset_intent="creature",
            task_graph=[
                TaskGraphEntry(
                    task_id="task-12345-abcde",
                    service="text3d",
                    status="IN_PROGRESS",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ],
        )

        repo.find_task_by_id.return_value = _task_lookup_payload("project1", "hash-abc123", asset_manifest)
        repo.record_task_update.return_value = None

        return repo

    @pytest.fixture
    def webhook_handler(self, mock_repository, temp_dir):
        """Create WebhookHandler with mocks."""
        mock_repository.base_path = temp_dir
        return WebhookHandler(
            repository=mock_repository,
            download_artifacts=True,
        )

    def test_handle_webhook_success(self, webhook_handler, mock_repository, webhook_payload_succeeded):
        """Test handling successful webhook."""
        with patch("cloud_connectors.meshy.webhooks.handler.base") as mock_base:
            mock_base.download.return_value = 1000

            payload = MeshyWebhookPayload(**webhook_payload_succeeded)
            result = webhook_handler.handle_webhook(payload)

            assert isinstance(result, ExtendedDict)
            assert isinstance(result["status"], ExtendedString)
            assert result["status"] == "success"
            assert result["task_id"] == "task-12345-abcde"
            assert result["project"] == "project1"
            assert result["task_status"] == "SUCCEEDED"

            # Verify repository was updated
            mock_repository.record_task_update.assert_called_once()

    def test_handle_webhook_task_not_found(self, webhook_handler, mock_repository):
        """Test handling webhook for unknown task."""
        mock_repository.find_task_by_id.return_value = None

        payload = MeshyWebhookPayload(
            id="unknown-task",
            status="SUCCEEDED",
            created_at=1700000000,
        )
        result = webhook_handler.handle_webhook(payload)

        assert isinstance(result, ExtendedDict)
        assert isinstance(result["message"], ExtendedString)
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_handle_webhook_failed_task(self, webhook_handler, mock_repository, webhook_payload_failed):
        """Test handling failed webhook."""
        # Update mock to find this task
        asset_manifest = AssetManifest(
            asset_spec_hash="hash-xyz",
            spec_fingerprint="hash-xyz",
            project="project1",
            asset_intent="creature",
            task_graph=[
                TaskGraphEntry(
                    task_id="task-failed-xyz",
                    service="text3d",
                    status="IN_PROGRESS",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ],
        )
        mock_repository.find_task_by_id.return_value = _task_lookup_payload("project1", "hash-xyz", asset_manifest)

        payload = MeshyWebhookPayload(**webhook_payload_failed)
        result = webhook_handler.handle_webhook(payload)

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "success"  # Handler succeeded
        assert result["task_status"] == "FAILED"  # Task failed

        # Verify error was recorded
        call_args = mock_repository.record_task_update.call_args
        assert call_args[1]["error"] == "Generation failed due to invalid prompt"

    def test_handle_webhook_redacts_failed_task_error(self, webhook_handler, mock_repository):
        """Failed task errors recorded from webhook payloads should be redacted."""
        asset_manifest = AssetManifest(
            asset_spec_hash="hash-xyz",
            spec_fingerprint="hash-xyz",
            project="project1",
            asset_intent="creature",
            task_graph=[
                TaskGraphEntry(
                    task_id="task-failed-secret",
                    service="text3d",
                    status="IN_PROGRESS",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ],
        )
        mock_repository.find_task_by_id.return_value = _task_lookup_payload("project1", "hash-xyz", asset_manifest)

        payload = MeshyWebhookPayload(
            id="task-failed-secret",
            status="FAILED",
            created_at=1700000000,
            task_error={"message": "denied password=hunter2 Authorization: Bearer raw_token"},
        )

        webhook_handler.handle_webhook(payload)

        error = mock_repository.record_task_update.call_args.kwargs["error"]
        assert "hunter2" not in error
        assert "raw_token" not in error
        assert "[REDACTED]" in error

    def test_handle_webhook_downloads_artifact(self, temp_dir, webhook_payload_succeeded):
        """Test that handler downloads artifacts on success."""
        from pathlib import Path

        # Set up mock repository with proper task graph
        mock_repository = MagicMock()
        mock_repository.base_path = temp_dir

        # Create project directory
        project_dir = temp_dir / "project1"
        project_dir.mkdir(parents=True, exist_ok=True)

        asset_manifest = AssetManifest(
            asset_spec_hash="hash-abc123",
            spec_fingerprint="hash-abc123",
            project="project1",
            asset_intent="creature",
            task_graph=[
                TaskGraphEntry(
                    task_id="task-12345-abcde",
                    service="text3d",
                    status="IN_PROGRESS",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ],
        )
        mock_repository.find_task_by_id.return_value = _task_lookup_payload("project1", "hash-abc123", asset_manifest)
        mock_repository.record_task_update.return_value = None

        def mock_download(url, output_path):
            # Actually create the file so the hash calculation works
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"fake glb content")
            return 1000

        with patch("cloud_connectors.meshy.webhooks.handler.base") as mock_base:
            mock_base.download.side_effect = mock_download

            handler = WebhookHandler(
                repository=mock_repository,
                download_artifacts=True,
            )

            payload = MeshyWebhookPayload(**webhook_payload_succeeded)
            result = handler.handle_webhook(payload)

            assert isinstance(result, ExtendedDict)
            assert result["artifacts_downloaded"] == 1
            mock_base.download.assert_called_once()

    def test_handle_webhook_no_download_when_disabled(self, mock_repository, webhook_payload_succeeded):
        """Test that downloads are skipped when disabled."""
        handler = WebhookHandler(
            repository=mock_repository,
            download_artifacts=False,
        )

        with patch("cloud_connectors.meshy.webhooks.handler.base") as mock_base:
            payload = MeshyWebhookPayload(**webhook_payload_succeeded)
            result = handler.handle_webhook(payload)

            assert isinstance(result, ExtendedDict)
            assert result["artifacts_downloaded"] == 0
            mock_base.download.assert_not_called()

    def test_verify_signature_requires_secret(self, webhook_handler):
        """Unsigned handlers reject signatures instead of accepting placeholders."""
        payload = b'{"id":"task-12345-abcde"}'
        signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()

        assert webhook_handler.verify_signature(payload, signature) is False

    def test_verify_signature_accepts_hmac_sha256_hex(self, mock_repository):
        """Verify raw payloads with HMAC-SHA256 hex signatures."""
        payload = b'{"id":"task-12345-abcde"}'
        signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
        handler = WebhookHandler(repository=mock_repository, webhook_secret="secret")

        assert handler.verify_signature(payload, signature) is True
        assert handler.verify_signature(payload, f"sha256={signature.upper()}") is True
        assert handler.verify_signature(b'{"id":"tampered"}', signature) is False
        assert handler.verify_signature(payload, "not-a-signature") is False

    def test_verify_signature_accepts_hmac_sha256_base64(self, mock_repository):
        """Verify raw payloads with HMAC-SHA256 base64 signatures."""
        payload = b'{"id":"task-12345-abcde"}'
        digest = hmac.new(b"secret", payload, hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("ascii")
        handler = WebhookHandler(repository=mock_repository, webhook_secret=b"secret")

        assert handler.verify_signature(payload, signature) is True

    def test_handle_signed_webhook_rejects_invalid_signature(self, mock_repository, webhook_payload_succeeded):
        """Invalid signatures fail before payload parsing or repository mutation."""
        payload = json.dumps(webhook_payload_succeeded, separators=(",", ":")).encode("utf-8")
        handler = WebhookHandler(repository=mock_repository, webhook_secret="secret")

        result = handler.handle_signed_webhook(payload, "invalid")

        assert isinstance(result, ExtendedDict)
        assert result == {
            "status": "error",
            "message": "Invalid webhook signature",
        }
        mock_repository.find_task_by_id.assert_not_called()
        mock_repository.record_task_update.assert_not_called()

    def test_handle_signed_webhook_redacts_invalid_payload_error(self, mock_repository):
        """Signed payload parse failures should not echo secret-bearing input."""
        payload = b'{"id":"task-12345-abcde","password":"hunter2","authorization":"Bearer raw_token"}'
        signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
        handler = WebhookHandler(repository=mock_repository, webhook_secret="secret")

        result = handler.handle_signed_webhook(payload, signature)

        assert result["status"] == "error"
        assert result["message"] == "Invalid webhook payload"
        assert "hunter2" not in result["error"]
        assert "raw_token" not in result["error"]
        assert "[REDACTED]" in result["error"]
        mock_repository.find_task_by_id.assert_not_called()
        mock_repository.record_task_update.assert_not_called()

    def test_handle_signed_webhook_processes_valid_signature(self, mock_repository, webhook_payload_succeeded):
        """Valid signed raw payloads are parsed and processed."""
        payload = json.dumps(webhook_payload_succeeded, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
        handler = WebhookHandler(
            repository=mock_repository,
            download_artifacts=False,
            webhook_secret="secret",
        )

        result = handler.handle_signed_webhook(payload, signature)

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "success"
        assert result["task_id"] == "task-12345-abcde"
        mock_repository.record_task_update.assert_called_once()


class TestWebhookHandlerArtifactDownload:
    """Tests for artifact download functionality."""

    def test_download_glb_artifact(self, temp_dir):
        """Test downloading GLB artifact."""
        # Create the project directory
        project_dir = temp_dir / "project1"
        project_dir.mkdir(parents=True, exist_ok=True)

        repo = MagicMock()
        repo.base_path = temp_dir

        handler = WebhookHandler(
            repository=repo,
            download_artifacts=True,
        )

        with patch("cloud_connectors.meshy.webhooks.handler.base") as mock_base:
            # Simulate actual file download
            def mock_download(url, output_path):
                from pathlib import Path

                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(b"fake glb content for testing")
                return 5000

            mock_base.download.side_effect = mock_download

            artifact = handler._download_glb_artifact(
                project="project1",
                spec_hash="hash-abc123",
                service="text3d",
                glb_url="https://example.com/model.glb",
            )

            assert artifact is not None
            assert artifact.relative_path == "hash-abc123_text3d.glb"
            assert artifact.file_size_bytes == 5000
            assert artifact.source_url == "https://example.com/model.glb"

    def test_download_artifact_handles_error(self, temp_dir):
        """Test that download errors are handled gracefully."""
        repo = MagicMock()
        repo.base_path = temp_dir

        handler = WebhookHandler(
            repository=repo,
            download_artifacts=True,
        )

        with patch("cloud_connectors.meshy.webhooks.handler.base") as mock_base:
            mock_base.download.side_effect = Exception("Network error")

            artifact = handler._download_glb_artifact(
                project="project1",
                spec_hash="hash-abc123",
                service="text3d",
                glb_url="https://example.com/model.glb",
            )

            assert artifact is None
