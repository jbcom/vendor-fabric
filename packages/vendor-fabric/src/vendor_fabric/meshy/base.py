"""Base HTTP client - auth, retries, rate limiting.

This module handles ALL the HTTP infrastructure. API modules import this.

Uses InputProvider for credential loading, consistent with other
vendor-fabric integrations. Credentials can come from:
- Environment variables (MESHY_API_KEY)
- Direct parameters
- stdin JSON input
"""

from __future__ import annotations

import threading
import time

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import httpx

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data, to_builtin
from extended_data.inputs import InputProvider
from extended_data.io.files import decode_file
from extended_data.primitives.redaction import redact_sensitive_text
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class RateLimitError(Exception):
    """Raised when API rate limit is hit."""


class MeshyAPIError(Exception):
    """Raised when API returns an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# Global client state
_client: httpx.Client | None = None
_inputs: InputProvider | None = None
_last_request_time: float = 0
_rate_limit_lock = threading.Lock()
_min_request_interval: float = 0.5  # 500ms between requests

BASE_URL = "https://api.meshy.ai"


def _get_inputs() -> InputProvider:
    """Get or create the InputProvider instance."""
    global _inputs
    if _inputs is None:
        _inputs = InputProvider()
    return _inputs


def configure(api_key: str | None = None, **kwargs: Any) -> None:
    """Configure Meshy API credentials.

    Args:
        api_key: Meshy API key (overrides environment variable)
        **kwargs: Additional inputs to merge
    """
    global _inputs
    inputs = {"MESHY_API_KEY": api_key} if api_key else {}
    inputs.update(kwargs)
    if _inputs is None:
        _inputs = InputProvider(inputs=inputs)
    else:
        _inputs.merge_inputs(inputs)


def get_api_key() -> str:
    """Get API key from InputProvider (env vars, direct inputs, or stdin)."""
    inputs = _get_inputs()
    return inputs.get_input("MESHY_API_KEY", required=True)


def get_client() -> httpx.Client:
    """Get or create HTTP client."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=300.0)
    return _client


def close() -> None:
    """Close the HTTP client."""
    global _client
    if _client:
        _client.close()
        _client = None


def _rate_limit() -> None:
    """Simple rate limiting with thread safety."""
    global _last_request_time

    with _rate_limit_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _min_request_interval:
            time.sleep(_min_request_interval - elapsed)
        _last_request_time = time.time()


def _headers() -> dict[str, str]:
    """Build request headers."""
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }


def task_failure_message(error: Any) -> str:
    """Return a public, redacted Meshy task failure message."""
    if isinstance(error, Mapping):
        message = error.get("message") or error.get("error") or "Unknown error"
    else:
        message = error or "Unknown error"
    return f"Task failed: {redact_sensitive_text(message)}"


def unexpected_response_message(data: Any) -> str:
    """Return a public, redacted unexpected-response diagnostic."""
    return (
        "Unexpected API response: missing 'result' key; missing task id in "
        f"'result', 'id', or 'task_id'. Response: {redact_sensitive_text(data)}"
    )


def _decode_response_json(response: httpx.Response) -> Any:
    """Decode a Meshy JSON response through the shared data boundary."""
    if not response.content:
        return None
    return decode_file(response.content, suffix="json", as_extended=True)


def task_id_from_response(response: httpx.Response) -> ExtendedString:
    """Extract a non-empty Meshy task id from any documented create-response shape."""
    data = _decode_response_json(response)
    task_id: object = None
    if isinstance(data, Mapping):
        result = data.get("result")
        task_id = result.get("id") or result.get("task_id") if isinstance(result, Mapping) else result
        task_id = task_id or data.get("id") or data.get("task_id")
    if not isinstance(task_id, (str, ExtendedString)) or not str(task_id).strip():
        raise RuntimeError(unexpected_response_message(data))
    return ExtendedString(str(task_id))


def task_payload_from_response(response: httpx.Response, model_type: type[BaseModel], endpoint: str) -> ExtendedDict:
    """Validate a Meshy task payload and return a promoted public mapping."""
    data = _decode_response_json(response)
    try:
        result = model_type.model_validate(to_builtin(data))
    except ValidationError:
        raise RuntimeError(f"Unexpected API response for {endpoint}: {redact_sensitive_text(data)}") from None
    return cast(ExtendedDict, extend_data(result.model_dump(mode="json", by_alias=True)))


def task_list_from_response(
    response: httpx.Response, model_type: type[BaseModel], endpoint: str
) -> ExtendedList[ExtendedDict]:
    """Validate a Meshy task list and return promoted public mappings."""
    data = _decode_response_json(response)
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
        raise RuntimeError(  # noqa: TRY004 -- every invalid provider response has one public exception contract
            f"Unexpected API response for {endpoint}: {redact_sensitive_text(data)}"
        )
    try:
        results = [model_type.model_validate(to_builtin(item)).model_dump(mode="json", by_alias=True) for item in data]
    except ValidationError:
        raise RuntimeError(f"Unexpected API response for {endpoint}: {redact_sensitive_text(data)}") from None
    return cast(ExtendedList[ExtendedDict], extend_data(results))


def poll_task(
    fetch: Callable[[str], ExtendedDict],
    task_id: str,
    interval: float = 5.0,
    timeout: float = 600.0,
) -> ExtendedDict:
    """Poll a Meshy task through its endpoint-specific fetch function."""
    start = time.time()
    while True:
        result = fetch(task_id)
        status = result.get("status")
        if status == "SUCCEEDED":
            return result
        if status == "FAILED":
            error = result.get("task_error") or result.get("error")
            raise RuntimeError(task_failure_message(error))
        if status in {"CANCELED", "EXPIRED"}:
            raise RuntimeError(f"Task {str(status).title()}")
        if time.time() - start > timeout:
            raise TimeoutError(f"Task timed out after {timeout}s")
        time.sleep(interval)


@retry(
    retry=retry_if_exception_type((RateLimitError, httpx.TimeoutException)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def request(
    method: str,
    endpoint: str,
    *,
    version: str = "v2",
    **kwargs: Any,
) -> httpx.Response:
    """Make HTTP request with retries and rate limiting.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint (e.g., "text-to-3d")
        version: API version (v1 or v2)
        **kwargs: Passed to httpx.request (json, params, etc.)

    Returns:
        httpx.Response

    Raises:
        RateLimitError: On 429 (will retry)
        MeshyAPIError: On other API errors
    """
    _rate_limit()

    url = f"{BASE_URL}/openapi/{version}/{endpoint}"
    response = get_client().request(method, url, headers=_headers(), **kwargs)

    # Handle rate limiting
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after", "5")
        try:
            time.sleep(float(retry_after))
        except ValueError:
            time.sleep(5)
        msg = f"Rate limit exceeded, retried after {retry_after}s"
        raise RateLimitError(msg)

    # Retry on 5xx
    if response.status_code >= 500:
        msg = f"Server error {response.status_code}"
        raise RateLimitError(msg)

    # Raise on 4xx
    if response.status_code >= 400:
        msg = f"API error: {redact_sensitive_text(response.text)}"
        raise MeshyAPIError(
            msg,
            status_code=response.status_code,
        )

    return response


def download(url: str, output_path: str) -> int:
    """Download file from URL.

    Args:
        url: URL to download from
        output_path: Local path to save to

    Returns:
        File size in bytes
    """
    import os as _os

    dirname = _os.path.dirname(output_path)
    if dirname:
        _os.makedirs(dirname, exist_ok=True)

    response = httpx.get(url)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    return len(response.content)
