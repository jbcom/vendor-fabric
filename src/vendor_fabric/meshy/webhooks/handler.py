"""Webhook handler for Meshy API callbacks."""

from __future__ import annotations

import base64
import hashlib
import hmac

from datetime import UTC, datetime

from extended_data.containers import ExtendedDict, extend_data, to_builtin
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.meshy import base
from vendor_fabric.meshy.webhooks.schemas import MeshyWebhookPayload

from ..persistence.repository import TaskRepository
from ..persistence.schemas import ArtifactRecord


def _utc_now() -> datetime:
    """Return current UTC time with timezone info."""
    return datetime.now(UTC)


class WebhookHandler:
    """Handle webhook callbacks from Meshy API.

    This class processes webhook payloads, updates task state in the repository,
    and downloads artifacts on successful completion.
    """

    def __init__(
        self,
        repository: TaskRepository,
        download_artifacts: bool = True,
        webhook_secret: str | bytes | None = None,
    ) -> None:
        """Initialize webhook handler.

        Args:
            repository: TaskRepository for updating state
            download_artifacts: Whether to download GLB files on SUCCEEDED
            webhook_secret: Shared secret used to verify HMAC-SHA256 signatures
        """
        self.repository = repository
        self.download_artifacts = download_artifacts
        self.webhook_secret = webhook_secret

    def handle_signed_webhook(
        self,
        payload: bytes,
        signature: str,
        project: str | None = None,
        spec_hash: str | None = None,
    ) -> ExtendedDict:
        """Verify a raw webhook payload before parsing and processing it."""
        if not self.verify_signature(payload, signature):
            return extend_data(
                {
                    "status": "error",
                    "message": "Invalid webhook signature",
                }
            )

        try:
            parsed_payload = MeshyWebhookPayload.model_validate_json(payload)
        except ValueError as exc:
            return extend_data(
                {
                    "status": "error",
                    "message": "Invalid webhook payload",
                    "error": redact_sensitive_text(exc),
                }
            )

        return self.handle_webhook(parsed_payload, project=project, spec_hash=spec_hash)

    def handle_webhook(
        self, payload: MeshyWebhookPayload, project: str | None = None, spec_hash: str | None = None
    ) -> ExtendedDict:
        """Process webhook payload and update repository.

        Args:
            payload: Parsed webhook payload
            project: Optional project name (will search if not provided)
            spec_hash: Optional spec hash (will search if not provided)

        Returns:
            Extended dict with status and details.
        """
        task_lookup = self.repository.find_task_by_id(task_id=payload.id, project=project)

        if not task_lookup:
            return extend_data(
                {
                    "status": "error",
                    "message": f"Task {payload.id} not found in repository",
                    "task_id": payload.id,
                }
            )

        found_project = str(task_lookup["project"])
        found_spec_hash = str(task_lookup["spec_hash"])
        asset_manifest = task_lookup["asset"]

        service_name = None
        for task_entry in asset_manifest.get("task_graph", []):
            if task_entry["task_id"] == payload.id:
                service_name = str(task_entry["service"])
                break

        if not service_name:
            return extend_data(
                {
                    "status": "error",
                    "message": f"Task {payload.id} not found in task graph",
                    "task_id": payload.id,
                }
            )

        error_message = None
        if payload.status == "FAILED":
            raw_error_message = payload.get_error_message()
            error_message = redact_sensitive_text(raw_error_message) if raw_error_message else None

        result_paths = to_builtin(payload.get_all_urls())

        artifacts = []
        if payload.status == "SUCCEEDED" and self.download_artifacts:
            glb_url = payload.get_glb_url()
            if glb_url:
                artifact = self._download_glb_artifact(
                    project=found_project,
                    spec_hash=found_spec_hash,
                    service=service_name,
                    glb_url=glb_url,
                )
                if artifact:
                    artifacts.append(artifact)

        self.repository.record_task_update(
            project=found_project,
            spec_hash=found_spec_hash,
            task_id=payload.id,
            status=payload.status,
            result_paths=result_paths,
            artifacts=artifacts or None,
            source="webhook",
            error=error_message,
        )

        return extend_data(
            {
                "status": "success",
                "task_id": payload.id,
                "project": found_project,
                "spec_hash": found_spec_hash,
                "service": service_name,
                "task_status": payload.status,
                "artifacts_downloaded": len(artifacts),
            }
        )

    def _download_glb_artifact(self, project: str, spec_hash: str, service: str, glb_url: str) -> ArtifactRecord | None:
        """Download GLB artifact and create record."""
        try:
            project_dir = self.repository.base_path / project
            filename = f"{spec_hash}_{service}.glb"
            output_path = project_dir / filename

            file_size = base.download(glb_url, str(output_path))

            with open(output_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            return ArtifactRecord(
                relative_path=filename,
                sha256_hash=file_hash,
                file_size_bytes=file_size,
                downloaded_at=_utc_now(),
                source_url=glb_url,
            )

        except Exception:
            return None

    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        *,
        secret: str | bytes | None = None,
    ) -> bool:
        """Verify an HMAC-SHA256 webhook signature for a raw payload."""
        secret_value = self.webhook_secret if secret is None else secret
        if secret_value is None or not signature.strip():
            return False

        secret_bytes = secret_value.encode("utf-8") if isinstance(secret_value, str) else secret_value
        if not secret_bytes:
            return False

        digest = hmac.new(secret_bytes, payload, hashlib.sha256).digest()
        expected_hex = digest.hex()
        expected_base64 = base64.b64encode(digest).decode("ascii")
        expected_urlsafe_base64 = base64.urlsafe_b64encode(digest).decode("ascii")

        signature_value = signature.strip()
        if signature_value.casefold().startswith("sha256="):
            signature_value = signature_value.split("=", 1)[1].strip()

        return (
            hmac.compare_digest(signature_value.casefold(), expected_hex)
            or hmac.compare_digest(signature_value, expected_base64)
            or hmac.compare_digest(signature_value, expected_urlsafe_base64)
        )
