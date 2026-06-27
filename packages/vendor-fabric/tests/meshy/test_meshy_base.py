"""Tests for Meshy connector HTTP base helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from extended_data.containers import ExtendedDict, ExtendedString

from vendor_fabric.meshy import base
from vendor_fabric.meshy.models import Text3DResult


@pytest.fixture(autouse=True)
def reset_meshy_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset Meshy base globals so helper tests stay isolated."""
    monkeypatch.setattr(base, "_client", None)
    monkeypatch.setattr(base, "_inputs", None)
    monkeypatch.setattr(base, "_last_request_time", 0)
    monkeypatch.setattr(base, "_min_request_interval", 0.5)


def _raw_request(*args, **kwargs):
    return base.request.__wrapped__(*args, **kwargs)


def test_configure_sets_and_merges_api_inputs() -> None:
    """Meshy configuration should feed the shared InputProvider boundary."""
    base.configure(api_key="first-key", EXTRA_INPUT="value")

    assert base.get_api_key() == "first-key"

    base.configure(api_key="second-key")

    assert base.get_api_key() == "second-key"


def test_get_client_reuses_client_and_close_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Meshy HTTP clients should be lazy, reused, and closed explicitly."""
    client = MagicMock(spec=httpx.Client)
    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(base.httpx, "Client", client_factory)

    assert base.get_client() is client
    assert base.get_client() is client
    client_factory.assert_called_once_with(timeout=300.0)

    base.close()

    client.close.assert_called_once_with()
    assert base._client is None


def test_rate_limit_sleeps_only_when_interval_has_not_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rate limiting should sleep only for the remaining interval."""
    sleep = MagicMock()
    monkeypatch.setattr(base.time, "sleep", sleep)
    monkeypatch.setattr(base.time, "time", MagicMock(side_effect=[100.2, 100.7, 102.0, 102.0]))
    monkeypatch.setattr(base, "_last_request_time", 100.0)

    base._rate_limit()
    assert pytest.approx(sleep.call_args.args[0]) == 0.3
    assert base._last_request_time == 100.7

    sleep.reset_mock()
    base._rate_limit()
    sleep.assert_not_called()
    assert base._last_request_time == 102.0


def test_headers_uses_bearer_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Meshy request headers should be built from the configured API key."""
    monkeypatch.setattr(base, "get_api_key", lambda: "test-key")

    assert base._headers() == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }


def test_meshy_request_redacts_sensitive_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Meshy API errors should not expose raw response secrets."""
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        400,
        content=b'{"api_key":"key_123","message":"Authorization: Bearer raw_token"}',
    )

    monkeypatch.setattr(base, "_rate_limit", lambda: None)
    monkeypatch.setattr(base, "_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(base, "get_client", lambda: mock_client)

    with pytest.raises(base.MeshyAPIError) as exc_info:
        base.request("GET", "text-to-3d")

    message = str(exc_info.value)
    assert exc_info.value.status_code == 400
    assert "key_123" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_meshy_request_builds_url_and_returns_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Meshy requests should build versioned OpenAPI URLs with shared headers."""
    response = httpx.Response(200, content=b'{"result":"task-123"}')
    mock_client = MagicMock()
    mock_client.request.return_value = response
    monkeypatch.setattr(base, "_rate_limit", lambda: None)
    monkeypatch.setattr(base, "_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(base, "get_client", lambda: mock_client)

    result = _raw_request("POST", "text-to-3d", version="v2", json={"prompt": "ship"})

    assert result is response
    mock_client.request.assert_called_once_with(
        "POST",
        "https://api.meshy.ai/openapi/v2/text-to-3d",
        headers={"Authorization": "Bearer test"},
        json={"prompt": "ship"},
    )


def test_meshy_request_raises_rate_limit_for_429_and_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Meshy retryable responses should raise RateLimitError with bounded sleeps."""
    mock_client = MagicMock()
    mock_client.request.side_effect = [
        httpx.Response(429, headers={"retry-after": "0.25"}),
        httpx.Response(429, headers={"retry-after": "not-a-number"}),
        httpx.Response(503, content=b"unavailable"),
    ]
    sleep = MagicMock()
    monkeypatch.setattr(base, "_rate_limit", lambda: None)
    monkeypatch.setattr(base, "_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(base, "get_client", lambda: mock_client)
    monkeypatch.setattr(base.time, "sleep", sleep)

    with pytest.raises(base.RateLimitError, match=r"0\.25s"):
        _raw_request("GET", "text-to-3d")
    sleep.assert_called_once_with(0.25)

    sleep.reset_mock()
    with pytest.raises(base.RateLimitError, match="not-a-number"):
        _raw_request("GET", "text-to-3d")
    sleep.assert_called_once_with(5)

    with pytest.raises(base.RateLimitError, match="Server error 503"):
        _raw_request("GET", "text-to-3d")


def test_task_failure_message_redacts_sensitive_values() -> None:
    """Meshy task failure messages should share the connector redaction boundary."""
    message = base.task_failure_message({"message": "failed password=hunter2 Authorization: Bearer raw_token"})

    assert message.startswith("Task failed:")
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_task_failure_message_falls_back_to_error_and_unknown() -> None:
    """Task failure messages should preserve useful public errors."""
    assert base.task_failure_message({"error": "bad mesh"}) == "Task failed: bad mesh"
    assert base.task_failure_message(None) == "Task failed: Unknown error"


def test_unexpected_response_message_redacts_sensitive_payloads() -> None:
    """Unexpected response diagnostics should not echo secret-bearing payloads."""
    message = base.unexpected_response_message({"api_key": "key_123", "message": "Authorization: Bearer raw_token"})

    assert "key_123" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_decode_response_json_handles_empty_and_extended_payloads() -> None:
    """Response JSON decoding should promote payloads across the data boundary."""
    assert base._decode_response_json(httpx.Response(204, content=b"")) is None

    result = base._decode_response_json(httpx.Response(200, content=b'{"result":"task-123"}'))

    assert isinstance(result, ExtendedDict)
    assert result["result"] == "task-123"


def test_task_id_from_response_extracts_non_empty_result() -> None:
    """Task creation responses should expose non-empty task IDs as ExtendedString."""
    task_id = base.task_id_from_response(httpx.Response(200, content=b'{"result":"task-123"}'))

    assert isinstance(task_id, ExtendedString)
    assert task_id == "task-123"


def test_task_id_from_response_rejects_missing_or_blank_results() -> None:
    """Task creation responses should fail loudly for unusable response bodies."""
    with pytest.raises(RuntimeError, match="missing 'result' key"):
        base.task_id_from_response(httpx.Response(200, content=b'{"api_key":"key_123","result":"   "}'))


def test_task_payload_from_response_validates_and_promotes_model_payload() -> None:
    """Task status responses should validate through Pydantic and return extended data."""
    response = httpx.Response(
        200,
        content=b'{"id":"task-123","status":"SUCCEEDED","progress":100,"created_at":1700000000}',
    )

    result = base.task_payload_from_response(response, Text3DResult, "text-to-3d")

    assert isinstance(result, ExtendedDict)
    assert result["id"] == "task-123"
    assert result["status"] == "SUCCEEDED"


def test_task_payload_from_response_redacts_invalid_payloads() -> None:
    """Task status validation errors should redact unexpected vendor payloads."""
    response = httpx.Response(200, content=b'{"api_key":"key_123","status":"FAILED"}')

    with pytest.raises(RuntimeError) as exc_info:
        base.task_payload_from_response(response, Text3DResult, "text-to-3d")

    message = str(exc_info.value)
    assert "key_123" not in message
    assert "[REDACTED]" in message


def test_download_creates_parent_directories_and_returns_size(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Meshy downloads should write bytes and return the downloaded size."""
    response = MagicMock()
    response.content = b"glb-bytes"
    response.raise_for_status = MagicMock()
    get = MagicMock(return_value=response)
    monkeypatch.setattr(base.httpx, "get", get)
    output_path = tmp_path / "nested" / "model.glb"

    size = base.download("https://assets.meshy.ai/model.glb", str(output_path))

    assert size == len(b"glb-bytes")
    assert output_path.read_bytes() == b"glb-bytes"
    response.raise_for_status.assert_called_once_with()
    get.assert_called_once_with("https://assets.meshy.ai/model.glb")
