"""Pytest fixtures for Meshy connector tests."""

from __future__ import annotations

import os
import tempfile

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from vendor_fabric.meshy.persistence.repository import TaskRepository


@pytest.fixture
def api_key():
    """Provide a test API key."""
    return "test-api-key-12345"


@pytest.fixture
def mock_env_api_key(api_key):
    """Set MESHY_API_KEY environment variable for tests."""
    with patch.dict(os.environ, {"MESHY_API_KEY": api_key}):
        yield api_key


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.Client."""
    mock = MagicMock(spec=httpx.Client)
    mock.close = MagicMock()
    return mock


@pytest.fixture
def mock_response():
    """Factory for creating mock HTTP responses."""

    def _create_response(
        status_code: int = 200,
        json_data: dict | None = None,
        headers: dict | None = None,
    ):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.headers = headers or {}
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=response,
            )
        return response

    return _create_response


@pytest.fixture
def task_repository(temp_dir):
    """Create a TaskRepository with temporary storage."""
    return TaskRepository(base_path=str(temp_dir))


# Sample API response fixtures


@pytest.fixture
def text3d_create_response():
    """Sample response from text-to-3d create endpoint."""
    return {"result": "task-12345-abcde"}


@pytest.fixture
def text3d_status_response():
    """Sample response from text-to-3d status endpoint."""
    return {
        "id": "task-12345-abcde",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "started_at": 1700000001,
        "finished_at": 1700000100,
        "model_urls": {
            "glb": "https://assets.meshy.ai/models/task-12345.glb",
            "fbx": "https://assets.meshy.ai/models/task-12345.fbx",
        },
        "texture_urls": [
            {
                "base_color": "https://assets.meshy.ai/textures/task-12345_basecolor.png",
                "normal": "https://assets.meshy.ai/textures/task-12345_normal.png",
            }
        ],
        "thumbnail_url": "https://assets.meshy.ai/thumbnails/task-12345.png",
    }


@pytest.fixture
def text3d_pending_response():
    """Sample response for pending text-to-3d task."""
    return {
        "id": "task-12345-abcde",
        "status": "IN_PROGRESS",
        "progress": 50,
        "created_at": 1700000000,
        "started_at": 1700000001,
    }


@pytest.fixture
def rigging_create_response():
    """Sample response from rigging create endpoint."""
    return {"result": "rig-task-67890"}


@pytest.fixture
def rigging_status_response():
    """Sample response from rigging status endpoint."""
    return {
        "id": "rig-task-67890",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "finished_at": 1700000200,
        "result": {
            "rigged_character_glb_url": "https://assets.meshy.ai/rigged/task-67890.glb",
            "rigged_character_fbx_url": "https://assets.meshy.ai/rigged/task-67890.fbx",
            "basic_animations": {
                "walking_glb_url": "https://assets.meshy.ai/anims/walking.glb",
                "running_glb_url": "https://assets.meshy.ai/anims/running.glb",
            },
        },
    }


@pytest.fixture
def webhook_payload_succeeded():
    """Sample webhook payload for successful task."""
    return {
        "id": "task-12345-abcde",
        "status": "SUCCEEDED",
        "progress": 100,
        "created_at": 1700000000,
        "finished_at": 1700000100,
        "model_urls": {
            "glb": "https://assets.meshy.ai/models/task-12345.glb",
        },
        "thumbnail_url": "https://assets.meshy.ai/thumbnails/task-12345.png",
    }


@pytest.fixture
def webhook_payload_failed():
    """Sample webhook payload for failed task."""
    return {
        "id": "task-failed-xyz",
        "status": "FAILED",
        "progress": 25,
        "created_at": 1700000000,
        "task_error": {
            "message": "Generation failed due to invalid prompt",
            "code": "INVALID_PROMPT",
        },
    }
