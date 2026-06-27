"""Tests for base connector data helpers."""

from __future__ import annotations

import threading

from unittest.mock import MagicMock

import httpx
import pytest

from extended_data.containers import ExtendedData, ExtendedDict, ExtendedList, ExtendedString
from extended_data.io import DataFile
from extended_data.logging import Logging
from extended_data.workflows import DataWorkflow

from vendor_fabric import base as base_module
from vendor_fabric.base import ConnectorAPIError, ConnectorBase, RateLimitError


class ExampleConnector(ConnectorBase):
    """Small connector used to exercise the base class."""

    BASE_URL = "https://api.example.com"


def _connector() -> ExampleConnector:
    logger = MagicMock(spec=Logging)
    logger.logger = MagicMock()
    return ExampleConnector(from_environment=False, logger=logger)


def test_connector_default_logging_does_not_create_cwd_log_file(tmp_path, monkeypatch) -> None:
    """Default connector construction should not write log files as a side effect."""
    monkeypatch.chdir(tmp_path)

    connector = ExampleConnector(from_environment=False)

    assert connector.logging.enable_file is False
    assert not (tmp_path / "ExampleConnector.log").exists()


def test_api_key_property_requires_configured_secret() -> None:
    """Connectors should fail clearly when a configured API key is absent."""

    class KeyedConnector(ExampleConnector):
        API_KEY_ENV = "EXAMPLE_API_KEY"

    connector = KeyedConnector(from_environment=False)

    with pytest.raises(ValueError, match="EXAMPLE_API_KEY not set"):
        _ = connector.api_key


def test_client_lifecycle_is_lazy_reused_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connector HTTP clients should be lazy, reused, and closed explicitly."""
    client = MagicMock(spec=httpx.Client)
    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(base_module.httpx, "Client", client_factory)
    connector = _connector()

    assert connector.client is client
    assert connector.client is client
    client_factory.assert_called_once_with(timeout=300)

    with connector as active:
        assert active is connector

    client.close.assert_called_once_with()
    assert connector._client is None


def test_close_without_client_is_noop() -> None:
    """Closing an unused connector should be harmless."""
    connector = _connector()

    connector.close()

    assert connector._client is None


def test_rate_limit_uses_per_connector_type_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Base rate limiting should sleep only for the remaining per-type interval."""

    class RateLimitedConnector(ExampleConnector):
        MIN_REQUEST_INTERVAL = 1.0

    connector = RateLimitedConnector(from_environment=False)
    sleep = MagicMock()
    monkeypatch.setattr(base_module.time, "sleep", sleep)
    monkeypatch.setattr(base_module.time, "time", MagicMock(side_effect=[100.25, 100.5]))
    ConnectorBase._rate_limit_locks[type(connector)] = threading.Lock()
    ConnectorBase._last_request_times[type(connector)] = 100.0

    connector._rate_limit()

    sleep.assert_called_once_with(0.75)
    assert ConnectorBase._last_request_times[type(connector)] == 100.5


def test_rate_limit_initializes_per_connector_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """First rate-limit call should initialize per-type state without sleeping."""

    class FirstRateLimitedConnector(ExampleConnector):
        MIN_REQUEST_INTERVAL = 1.0

    connector = FirstRateLimitedConnector(from_environment=False)
    sleep = MagicMock()
    monkeypatch.setattr(base_module.time, "sleep", sleep)
    monkeypatch.setattr(base_module.time, "time", MagicMock(side_effect=[200.0, 200.0]))
    ConnectorBase._rate_limit_locks.pop(type(connector), None)
    ConnectorBase._last_request_times.pop(type(connector), None)

    connector._rate_limit()

    sleep.assert_not_called()
    assert type(connector) in ConnectorBase._rate_limit_locks
    assert ConnectorBase._last_request_times[type(connector)] == 200.0


def test_decode_response_promotes_json_to_extended_containers() -> None:
    """JSON responses flow through the Tier 2 container bridge."""
    connector = _connector()
    response = httpx.Response(
        200,
        content=b'{"service":{"name":"api"}}',
        headers={"content-type": "application/json; charset=utf-8"},
    )

    data = connector.decode_response(response)

    assert isinstance(data, ExtendedDict)
    assert isinstance(data, ExtendedData)
    assert isinstance(data["service"], ExtendedDict)
    assert isinstance(data["service"], ExtendedData)
    assert isinstance(data["service"]["name"], ExtendedString)
    assert isinstance(data["service"]["name"], ExtendedData)
    assert data["service"]["name"].upper_first() == "Api"


def test_decode_response_can_return_plain_json() -> None:
    """Response decoding can opt out of extended containers."""
    connector = _connector()
    response = httpx.Response(
        200,
        content=b'{"service":{"name":"api"}}',
        headers={"content-type": "application/vnd.example+json"},
    )

    data = connector.decode_response(response, as_extended=False)

    assert data == {"service": {"name": "api"}}
    assert not isinstance(data["service"]["name"], ExtendedString)


def test_decode_response_promotes_text_to_extended_string() -> None:
    """Text responses become ExtendedString values by default."""
    connector = _connector()
    response = httpx.Response(
        200,
        content=b"api response",
        headers={"content-type": "text/plain"},
    )

    data = connector.decode_response(response)

    assert isinstance(data, ExtendedString)
    assert isinstance(data, ExtendedData)
    assert data.to_snake_case() == "api_response"


def test_decode_response_preserves_unknown_binary_data() -> None:
    """Unknown binary responses are left as bytes."""
    connector = _connector()
    response = httpx.Response(
        200,
        content=b"\x00\x01\x02",
        headers={"content-type": "application/octet-stream"},
    )

    assert connector.decode_response(response) == b"\x00\x01\x02"


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        (None, None),
        ("application/json", "json"),
        ("application/vnd.example+json", "json"),
        ("application/x-yaml", "yaml"),
        ("application/vnd.example+yaml", "yaml"),
        ("text/toml", "toml"),
        ("application/hcl", "hcl"),
        ("text/plain; charset=utf-8", "raw"),
        ("application/octet-stream", None),
    ],
)
def test_suffix_from_content_type_maps_supported_media_types(content_type: str | None, expected: str | None) -> None:
    """Content-Type inference should cover all supported extended-data formats."""
    assert ExampleConnector._suffix_from_content_type(content_type) == expected


def test_decode_response_returns_none_for_empty_body() -> None:
    """Empty responses should decode to None."""
    connector = _connector()
    response = httpx.Response(204, content=b"")

    assert connector.decode_response(response) is None


def test_request_data_decodes_response_body() -> None:
    """request_data combines the raw request primitive with response decoding."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        200,
        content=b'{"ok":true}',
        headers={"content-type": "application/json"},
    )
    connector._client = mock_client

    data = connector.request_data("GET", "/status")

    assert data == {"ok": True}
    assert isinstance(data, ExtendedDict)
    assert isinstance(data, ExtendedData)
    mock_client.request.assert_called_once()
    assert mock_client.request.call_args.args[0] == "GET"
    assert mock_client.request.call_args.args[1] == "https://api.example.com/status"


def test_request_once_merges_headers_and_accepts_absolute_urls() -> None:
    """Single request attempts should merge caller headers onto auth headers."""
    connector = ExampleConnector(api_key="test-key", from_environment=False)
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(200, content=b"ok")
    connector._client = mock_client

    response = connector._request_once(
        "GET",
        "https://uploads.example.com/blob",
        headers={"X-Trace": "abc"},
        params={"page": "1"},
    )

    assert response.status_code == 200
    mock_client.request.assert_called_once_with(
        "GET",
        "https://uploads.example.com/blob",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer test-key",
            "X-Trace": "abc",
        },
        params={"page": "1"},
    )


def test_request_once_handles_invalid_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid retry-after values should fall back to a bounded default sleep."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(429, headers={"retry-after": "not-a-number"})
    connector._client = mock_client
    sleep = MagicMock()
    monkeypatch.setattr(base_module.time, "sleep", sleep)

    with pytest.raises(RateLimitError, match="not-a-number"):
        connector._request_once("GET", "/status")

    sleep.assert_called_once_with(5)


def test_decode_response_file_returns_artifact_with_metadata() -> None:
    """HTTP response artifacts retain decoded data and non-secret provenance."""
    connector = _connector()
    response = httpx.Response(
        200,
        content=b'{"service":{"name":"api"}}',
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://api.example.com/status"),
    )

    artifact = connector.decode_response_file(response)

    assert isinstance(artifact, DataFile)
    assert artifact.source == "https://api.example.com/status"
    assert artifact.encoding == "json"
    assert isinstance(artifact.data, ExtendedDict)
    assert isinstance(artifact.data, ExtendedData)
    assert artifact.data["service"]["name"].upper_first() == "Api"
    assert artifact.metadata["status_code"] == 200
    assert artifact.metadata["content_type"] == "application/json"
    assert artifact.metadata["method"] == "GET"


def test_decode_response_file_handles_empty_body_with_fallback_metadata() -> None:
    """Empty response artifacts should retain stable fallback provenance."""
    connector = _connector()
    response = httpx.Response(204, content=b"", headers={"content-type": "application/json"})

    artifact = connector.decode_response_file(response)

    assert artifact.source == "response"
    assert artifact.data is None
    assert artifact.encoding == "json"
    assert artifact.metadata["source"] == "response"
    assert artifact.metadata["data_type"] == "NoneType"
    assert artifact.metadata["status_code"] == 204


def test_decode_response_file_preserves_unknown_binary_payload() -> None:
    """Unknown binary API responses remain bytes inside the DataFile artifact."""
    connector = _connector()
    response = httpx.Response(
        200,
        content=b"\x00\x01\x02",
        headers={"content-type": "application/octet-stream"},
    )

    artifact = connector.decode_response_file(response, source="https://api.example.com/blob")

    assert isinstance(artifact, DataFile)
    assert artifact.source == "https://api.example.com/blob"
    assert artifact.encoding == "raw"
    assert artifact.data == b"\x00\x01\x02"
    assert artifact.metadata["data_type"] == "bytes"
    assert artifact.metadata["status_code"] == 200


def test_request_data_file_adds_request_provenance() -> None:
    """request_data_file combines request, decoding, and artifact provenance."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        200,
        content=b'{"ok":true}',
        headers={"content-type": "application/json"},
    )
    connector._client = mock_client

    artifact = connector.request_data_file("GET", "/status")

    assert isinstance(artifact, DataFile)
    assert artifact.source == "https://api.example.com/status"
    assert artifact.data == {"ok": True}
    assert isinstance(artifact.data, ExtendedDict)
    assert artifact.metadata["method"] == "GET"
    assert artifact.metadata["endpoint"] == "/status"
    mock_client.request.assert_called_once()


def test_request_workflow_starts_from_response_artifact() -> None:
    """request_workflow should hand API data directly to DataWorkflow with provenance."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        200,
        content=b'{"HTTPResponseCode":"200","SelectedServices":["api","api","worker"]}',
        headers={"content-type": "application/json"},
    )
    connector._client = mock_client

    workflow = connector.request_workflow("GET", "/status")
    result = workflow.transform("reconstruct", "unhump", "deduplicate").result()

    assert isinstance(workflow, DataWorkflow)
    assert workflow.steps == ("data_file:https://api.example.com/status",)
    assert workflow.metadata["method"] == "GET"
    assert workflow.metadata["endpoint"] == "/status"
    assert result.metadata["status_code"] == 200
    assert result.as_builtin() == {
        "http_response_code": 200,
        "selected_services": ["api", "worker"],
    }
    mock_client.request.assert_called_once()


@pytest.mark.parametrize(
    ("helper_name", "expected_method"),
    [
        ("get_workflow", "GET"),
        ("post_workflow", "POST"),
        ("put_workflow", "PUT"),
        ("patch_workflow", "PATCH"),
        ("delete_workflow", "DELETE"),
    ],
)
def test_http_verb_workflow_helpers_start_response_workflows(helper_name: str, expected_method: str) -> None:
    """Verb-specific workflow helpers should mirror decoded data helpers."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        200,
        content=b'{"ok":true}',
        headers={"content-type": "application/json"},
    )
    connector._client = mock_client

    workflow = getattr(connector, helper_name)("/status")

    assert isinstance(workflow, DataWorkflow)
    assert workflow.metadata["method"] == expected_method
    assert workflow.metadata["endpoint"] == "/status"
    assert workflow.result().as_builtin() == {"ok": True}
    mock_client.request.assert_called_once()
    assert mock_client.request.call_args.args[0] == expected_method
    assert mock_client.request.call_args.args[1] == "https://api.example.com/status"


@pytest.mark.parametrize(
    ("helper_name", "expected_method"),
    [
        ("get", "GET"),
        ("post", "POST"),
        ("put", "PUT"),
        ("patch", "PATCH"),
        ("delete", "DELETE"),
    ],
)
def test_http_verb_helpers_delegate_to_request(helper_name: str, expected_method: str) -> None:
    """Verb-specific raw helpers should delegate to request with the right method."""
    connector = _connector()
    request = MagicMock(return_value=httpx.Response(200, content=b"ok"))
    connector.request = request

    response = getattr(connector, helper_name)("/status", params={"a": "b"})

    assert response.status_code == 200
    request.assert_called_once_with(expected_method, "/status", params={"a": "b"})


@pytest.mark.parametrize(
    ("helper_name", "expected_method"),
    [
        ("get_data", "GET"),
        ("post_data", "POST"),
        ("put_data", "PUT"),
        ("patch_data", "PATCH"),
        ("delete_data", "DELETE"),
    ],
)
def test_http_verb_data_helpers_delegate_to_request_data(helper_name: str, expected_method: str) -> None:
    """Verb-specific data helpers should delegate to request_data with the right method."""
    connector = _connector()
    request_data = MagicMock(return_value={"ok": True})
    connector.request_data = request_data

    result = getattr(connector, helper_name)("/status", suffix="json", as_extended=False, params={"a": "b"})

    assert result == {"ok": True}
    request_data.assert_called_once_with(
        expected_method,
        "/status",
        suffix="json",
        as_extended=False,
        params={"a": "b"},
    )


def test_extend_result_promotes_connector_payloads() -> None:
    """Connector data payloads cross into the Tier 2 container layer explicitly."""
    connector = _connector()

    data = connector.extend_result({"service": {"name": "api"}, "tags": ["core"]})

    assert isinstance(data, ExtendedDict)
    assert isinstance(data["service"], ExtendedDict)
    assert isinstance(data["service"]["name"], ExtendedString)
    assert isinstance(data["tags"], ExtendedList)
    assert data["service"]["name"].upper_first() == "Api"


def test_request_uses_connector_max_retries(mocker) -> None:
    """Connector subclasses control the retry attempt count."""

    class TwoAttemptConnector(ExampleConnector):
        MAX_RETRIES = 2

    connector = TwoAttemptConnector(from_environment=False)
    mocker.patch("vendor_fabric.base.time.sleep")
    mock_client = MagicMock()
    mock_client.request.side_effect = [
        httpx.Response(500, content=b"temporary failure"),
        httpx.Response(200, content=b"ok"),
    ]
    connector._client = mock_client

    response = connector.request("GET", "/status")

    assert response.status_code == 200
    assert mock_client.request.call_count == 2


def test_request_rejects_invalid_max_retries() -> None:
    """Invalid retry configuration fails before issuing a request."""

    class InvalidRetryConnector(ExampleConnector):
        MAX_RETRIES = 0

    connector = InvalidRetryConnector(from_environment=False)
    mock_client = MagicMock()
    connector._client = mock_client

    with pytest.raises(ValueError, match="MAX_RETRIES must be at least 1"):
        connector.request("GET", "/status")

    mock_client.request.assert_not_called()


def test_request_once_redacts_sensitive_client_error_body() -> None:
    """Programmatic connector API errors should not expose raw secret-bearing bodies."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        401,
        content=b'{"password":"hunter2","message":"Authorization: Bearer raw_token"}',
    )
    connector._client = mock_client

    with pytest.raises(ConnectorAPIError) as exc_info:
        connector._request_once("GET", "/status")

    message = str(exc_info.value)
    assert exc_info.value.status_code == 401
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_request_once_redacts_sensitive_server_error_body() -> None:
    """Retry-triggering server errors should not carry raw response secrets."""
    connector = _connector()
    mock_client = MagicMock()
    mock_client.request.return_value = httpx.Response(
        500,
        content=b'{"api_key":"key_123","message":"Bearer raw_token"}',
    )
    connector._client = mock_client

    with pytest.raises(RateLimitError) as exc_info:
        connector._request_once("GET", "/status")

    message = str(exc_info.value)
    assert "key_123" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_download_creates_parent_directory_and_returns_file_size(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Downloads should create parent directories and return the written byte count."""
    connector = _connector()
    response = MagicMock()
    response.content = b"artifact-bytes"
    response.raise_for_status = MagicMock()
    get = MagicMock(return_value=response)
    monkeypatch.setattr(base_module.httpx, "get", get)
    output_path = tmp_path / "nested" / "artifact.bin"

    size = connector.download("https://example.com/artifact.bin", str(output_path))

    assert size == len(b"artifact-bytes")
    assert output_path.read_bytes() == b"artifact-bytes"
    get.assert_called_once_with("https://example.com/artifact.bin", timeout=600.0)
    response.raise_for_status.assert_called_once_with()


def test_download_without_parent_directory_writes_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Downloads should also support output paths in the current directory."""
    connector = _connector()
    response = MagicMock()
    response.content = b"artifact-bytes"
    response.raise_for_status = MagicMock()
    monkeypatch.setattr(base_module.httpx, "get", MagicMock(return_value=response))
    monkeypatch.chdir(tmp_path)

    size = connector.download("https://example.com/artifact.bin", "artifact.bin")

    assert size == len(b"artifact-bytes")
    assert (tmp_path / "artifact.bin").read_bytes() == b"artifact-bytes"
