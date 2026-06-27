"""Tests for base connector data helpers."""

from __future__ import annotations

import builtins

from unittest.mock import MagicMock

import httpx
import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from extended_data.io import DataFile
from extended_data.logging import Logging
from extended_data.workflows import DataWorkflow
from pydantic import BaseModel, Field

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
    assert isinstance(data["service"], ExtendedDict)
    assert isinstance(data["service"]["name"], ExtendedString)
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
    mock_client.request.assert_called_once()
    assert mock_client.request.call_args.args[0] == "GET"
    assert mock_client.request.call_args.args[1] == "https://api.example.com/status"


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
    assert artifact.data["service"]["name"].upper_first() == "Api"
    assert artifact.metadata["status_code"] == 200
    assert artifact.metadata["content_type"] == "application/json"
    assert artifact.metadata["method"] == "GET"


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


def test_extend_result_promotes_connector_payloads() -> None:
    """Connector data payloads cross into the Tier 2 container layer explicitly."""
    connector = _connector()

    data = connector.extend_result({"service": {"name": "api"}, "tags": ["core"]})

    assert isinstance(data, ExtendedDict)
    assert isinstance(data["service"], ExtendedDict)
    assert isinstance(data["service"]["name"], ExtendedString)
    assert isinstance(data["tags"], ExtendedList)
    assert data["service"]["name"].upper_first() == "Api"


def test_handle_ai_tool_call_promotes_result_payloads() -> None:
    """AI tool dispatch should expose extended containers, not raw dict payloads."""
    connector = _connector()
    connector.register_tool(lambda: {"status": "ok", "items": ["one"]}, name="status")

    result = connector.handle_ai_tool_call("status", {})

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["items"], ExtendedList)
    assert result["status"].upper_first() == "Ok"


def test_handle_ai_tool_call_redacts_unknown_tool_names() -> None:
    """Unknown AI tool diagnostics should not echo secret-bearing names."""
    connector = _connector()

    with pytest.raises(ValueError) as exc_info:
        connector.handle_ai_tool_call("password=hunter2 Authorization: Bearer raw_token", {})

    message = str(exc_info.value)
    assert "hunter2" not in message
    assert "raw_token" not in message
    assert "[REDACTED]" in message


def test_get_ai_tool_definitions_promotes_definition_payloads() -> None:
    """AI tool definition export should expose extended containers."""

    class StatusArgs(BaseModel):
        verbose: bool = Field(..., description="Include detailed status.")

    def status(verbose: bool) -> dict[str, str]:
        """Read service status."""
        return {"status": "ok" if verbose else "quiet"}

    connector = _connector()
    connector.register_tool(status, name="status", schema=StatusArgs)

    definitions = connector.get_ai_tool_definitions()

    assert isinstance(definitions, ExtendedList)
    assert isinstance(definitions[0], ExtendedDict)
    assert definitions[0]["name"] == "status"
    assert isinstance(definitions[0]["inputSchema"], ExtendedDict)
    assert isinstance(definitions[0]["inputSchema"]["properties"]["verbose"]["description"], ExtendedString)


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


def test_get_tools_requires_langchain_extra(monkeypatch) -> None:
    """Base LangChain tool export should fail visibly when langchain-core is missing."""
    connector = _connector()
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langchain_core.tools":
            raise ImportError("blocked langchain-core")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match=r"vendor-fabric\[langchain\]"):
        connector.get_tools()
