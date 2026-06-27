"""Base class for all vendor fabric.

This module provides ConnectorBase - the foundation for ALL connectors
in the package connector fabric. It extends InputProvider and provides:

1. Credential loading from env vars, stdin, or direct inputs
2. HTTP client with retries and rate limiting
3. MCP server scaffolding

ALL connectors should extend this class instead of InputProvider directly.

Usage:
    from extended_data import ExtendedDict
    from vendor_fabric import ConnectorBase

    class MyConnector(ConnectorBase):
        API_KEY_ENV = "MY_API_KEY"  # Required env var name
        BASE_URL = "https://api.example.com"

        def __init__(self, api_key: str | None = None, **kwargs):
            super().__init__(**kwargs)
            self._api_key = api_key or self.get_input(self.API_KEY_ENV, required=True)

        def my_operation(self) -> ExtendedDict:
            return self.request_data("GET", "/endpoint", suffix="json")
"""

from __future__ import annotations

import builtins
import threading
import time

from abc import ABC
from collections.abc import Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, ClassVar, Self

import httpx

from extended_data.inputs import InputProvider
from extended_data.logging import Logging
from extended_data.primitives.redaction import redact_sensitive_text
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from vendor_fabric.capabilities import CapabilityProviderMixin


if TYPE_CHECKING:
    from types import TracebackType

    from extended_data.io import DataFile
    from extended_data.workflows import DataWorkflow


class RateLimitError(Exception):
    """Raised when API rate limit is hit - triggers retry."""


class ConnectorAPIError(Exception):
    """Raised when API returns an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ConnectorBase(CapabilityProviderMixin, InputProvider, ABC):
    """Base class for all vendor fabric.

    Provides:
    - InputProvider for credential loading (env, stdin, direct)
    - HTTP client with connection pooling
    - Automatic retries with exponential backoff
    - Rate limiting
    - MCP tool registration scaffolding

    Class Attributes:
        BASE_URL: API base URL (required for HTTP connectors)
        API_KEY_ENV: Environment variable name for API key
        CONNECTOR_CATEGORY: Catalog category for registry metadata
        CONNECTOR_CAPABILITIES: Catalog capabilities for registry metadata
        TIMEOUT: HTTP timeout in seconds (default 300)
        MIN_REQUEST_INTERVAL: Minimum seconds between requests (rate limiting)
        MAX_RETRIES: Maximum retry attempts (default 5)

    Instance Attributes:
        logger: Logger instance
        _client: HTTP client (lazy-initialized)
    """

    # Class-level configuration - override in subclasses
    BASE_URL: ClassVar[str] = ""
    API_KEY_ENV: ClassVar[str] = ""
    CONNECTOR_CATEGORY: ClassVar[str] = "external"
    CONNECTOR_CAPABILITIES: ClassVar[tuple[str, ...]] = ()
    TIMEOUT: ClassVar[float] = 300.0
    MIN_REQUEST_INTERVAL: ClassVar[float] = 0.0  # No rate limit by default
    MAX_RETRIES: ClassVar[int] = 5

    # Per-connector-type rate limiting state
    # Each subclass gets its own lock and timestamp to avoid cross-connector interference.
    # This is intentionally class-level (not instance-level) so all instances of the same
    # connector type share rate limiting, but different connector types are independent.
    _rate_limit_locks: ClassVar[dict[builtins.type[ConnectorBase], threading.Lock]] = {}
    _last_request_times: ClassVar[dict[builtins.type[ConnectorBase], float]] = {}

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the connector.

        Args:
            api_key: API key (overrides environment variable)
            base_url: Base URL (overrides class default)
            timeout: HTTP timeout in seconds
            logger: Logger instance
            **kwargs: Passed to InputProvider
        """
        super().__init__(**kwargs)

        # Set up logging
        self.logging = logger or Logging(logger_name=self.__class__.__name__)
        self.logger = self.logging.logger

        # Configuration with fallbacks
        self._base_url = base_url or self.BASE_URL
        self._timeout = timeout or self.TIMEOUT

        # Load API key from inputs if API_KEY_ENV is set
        self._api_key: str | None = None
        if api_key:
            self._api_key = api_key
        elif self.API_KEY_ENV:
            self._api_key = self.get_input(self.API_KEY_ENV, required=False)

        # Lazy-initialized HTTP client
        self._client: httpx.Client | None = None

    @property
    def api_key(self) -> str:
        """Get API key, raising if not set."""
        if not self._api_key:
            msg = f"{self.API_KEY_ENV or 'API key'} not set"
            raise ValueError(msg)
        return self._api_key

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: builtins.type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - close client."""
        self.close()

    # -------------------------------------------------------------------------
    # HTTP Methods with Retry and Rate Limiting
    # -------------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests.

        Rate limiting is per-connector-type (not global), so different connector
        types (e.g., MeshyConnector vs AWSConnector) don't interfere with each other.
        """
        if self.MIN_REQUEST_INTERVAL <= 0:
            return

        connector_type = type(self)

        # Lazily initialize lock and timestamp for this connector type
        if connector_type not in self._rate_limit_locks:
            self._rate_limit_locks[connector_type] = threading.Lock()
            self._last_request_times[connector_type] = 0.0

        with self._rate_limit_locks[connector_type]:
            now = time.time()
            elapsed = now - self._last_request_times[connector_type]
            if elapsed < self.MIN_REQUEST_INTERVAL:
                time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
            self._last_request_times[connector_type] = time.time()

    def _build_headers(self) -> dict[str, str]:
        """Build request headers. Override in subclasses for custom auth."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint."""
        if endpoint.startswith("http"):
            return endpoint
        base = self._base_url.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base}/{endpoint}"

    def _max_retry_attempts(self) -> int:
        """Return the validated retry attempt count for this connector."""
        if self.MAX_RETRIES < 1:
            msg = f"{type(self).__name__}.MAX_RETRIES must be at least 1"
            raise ValueError(msg)
        return self.MAX_RETRIES

    def _request_once(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make one HTTP request attempt with rate limiting and response handling."""
        self._rate_limit()

        url = self._build_url(endpoint)
        request_headers = self._build_headers()
        if headers:
            request_headers.update(headers)

        response = self.client.request(method, url, headers=request_headers, **kwargs)

        # Handle rate limiting - retry
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after", "5")
            try:
                time.sleep(float(retry_after))
            except ValueError:
                time.sleep(5)
            msg = f"Rate limit exceeded, retrying after {retry_after}s"
            raise RateLimitError(msg)

        # Retry on 5xx server errors
        if response.status_code >= 500:
            msg = f"Server error {response.status_code}: {redact_sensitive_text(response.text)}"
            raise RateLimitError(msg)

        # Raise on 4xx client errors (don't retry)
        if response.status_code >= 400:
            msg = f"API error {response.status_code}: {redact_sensitive_text(response.text)}"
            raise ConnectorAPIError(msg, status_code=response.status_code)

        return response

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make HTTP request with retries and rate limiting.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (relative to BASE_URL)
            headers: Additional headers (merged with defaults)
            **kwargs: Passed to httpx.request (json, params, data, etc.)

        Returns:
            httpx.Response

        Raises:
            RateLimitError: On 429 or 5xx responses after retries are exhausted.
            ConnectorAPIError: On other API errors.
        """
        retryer = Retrying(
            retry=retry_if_exception_type((RateLimitError, httpx.TimeoutException)),
            stop=stop_after_attempt(self._max_retry_attempts()),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            sleep=time.sleep,
            reraise=True,
        )

        for attempt in retryer:
            with attempt:
                return self._request_once(method, endpoint, headers=headers, **kwargs)

        message = "Retry loop exited without returning or raising."
        raise RuntimeError(message)

    @staticmethod
    def _suffix_from_content_type(content_type: str | None) -> str | None:
        """Infer a data suffix from an HTTP Content-Type header."""
        if not content_type:
            return None

        media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if media_type == "application/json" or media_type.endswith("+json"):
            return "json"
        if media_type in {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"} or media_type.endswith(
            "+yaml"
        ):
            return "yaml"
        if media_type in {"application/toml", "text/toml"}:
            return "toml"
        if media_type in {"application/hcl", "text/hcl"}:
            return "hcl"
        if media_type.startswith("text/"):
            return "raw"
        return None

    def decode_response(
        self,
        response: httpx.Response,
        *,
        suffix: str | None = None,
        as_extended: bool = True,
    ) -> Any:
        """Decode an HTTP response body through the extended-data IO layer.

        Structured response bodies are decoded from JSON, YAML, TOML, or HCL and
        promoted through the ExtendedData root by default. Text responses become raw
        strings, and unknown binary responses remain bytes.
        """
        if not response.content:
            return None

        resolved_suffix = suffix or self._suffix_from_content_type(response.headers.get("content-type"))
        if resolved_suffix is None:
            return response.content

        from extended_data.io.files import decode_file

        return decode_file(response.content, suffix=resolved_suffix, as_extended=as_extended)

    @staticmethod
    def _response_source(response: httpx.Response, fallback: str | None = None) -> str:
        """Return a stable source label for a response artifact."""
        if fallback:
            return fallback
        try:
            return str(response.request.url)
        except RuntimeError:
            return "response"

    @staticmethod
    def _response_metadata(response: httpx.Response, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return non-secret response provenance for a DataFile artifact."""
        response_metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
        }
        with suppress(RuntimeError):
            response_metadata["method"] = response.request.method
        if metadata:
            response_metadata.update(metadata)
        return response_metadata

    def decode_response_file(
        self,
        response: httpx.Response,
        *,
        source: str | None = None,
        suffix: str | None = None,
        as_extended: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> DataFile:
        """Decode an HTTP response body into a DataFile artifact with provenance."""
        from extended_data.containers import ExtendedDict, ExtendedString
        from extended_data.io import DataFile

        resolved_suffix = suffix or self._suffix_from_content_type(response.headers.get("content-type"))
        artifact_source = self._response_source(response, fallback=source)
        artifact_metadata = self._response_metadata(response, metadata=metadata)

        if not response.content:
            return DataFile(
                source=ExtendedString(artifact_source),
                data=None,
                encoding=ExtendedString(resolved_suffix or "raw"),
                metadata=ExtendedDict(
                    {
                        "source": artifact_source,
                        "encoding": resolved_suffix or "raw",
                        "path": None,
                        "is_url": artifact_source.startswith(("http://", "https://")),
                        "data_type": "NoneType",
                        **artifact_metadata,
                    }
                ),
            )

        if resolved_suffix is None:
            return DataFile(
                source=ExtendedString(artifact_source),
                data=response.content,
                encoding=ExtendedString("raw"),
                metadata=ExtendedDict(
                    {
                        "source": artifact_source,
                        "encoding": "raw",
                        "path": None,
                        "is_url": artifact_source.startswith(("http://", "https://")),
                        "data_type": type(response.content).__name__,
                        **artifact_metadata,
                    }
                ),
            )

        return DataFile.decode(
            response.content,
            file_path=artifact_source,
            suffix=resolved_suffix,
            as_extended=as_extended,
            metadata=artifact_metadata,
        )

    def extend_result(self, value: Any) -> Any:
        """Promote connector data payloads through the ExtendedData root."""
        from extended_data.containers import extend_data

        return extend_data(value)

    def request_data(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Make an HTTP request and return decoded response data."""
        response = self.request(method, endpoint, headers=headers, **kwargs)
        return self.decode_response(response, suffix=suffix, as_extended=as_extended)

    def request_data_file(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataFile:
        """Make an HTTP request and return a decoded DataFile response artifact."""
        response = self.request(method, endpoint, headers=headers, **kwargs)
        return self.decode_response_file(
            response,
            source=self._build_url(endpoint),
            suffix=suffix,
            as_extended=as_extended,
            metadata={"method": method.upper(), "endpoint": endpoint},
        )

    def request_workflow(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataWorkflow:
        """Make an HTTP request and return a workflow over the decoded response artifact."""
        return self.request_data_file(
            method,
            endpoint,
            headers=headers,
            suffix=suffix,
            as_extended=as_extended,
            **kwargs,
        ).workflow(as_extended=as_extended)

    def get(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        """HTTP GET request."""
        return self.request("GET", endpoint, **kwargs)

    def get_data(self, endpoint: str, *, suffix: str | None = None, as_extended: bool = True, **kwargs: Any) -> Any:
        """HTTP GET request returning decoded response data."""
        return self.request_data("GET", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def get_workflow(
        self,
        endpoint: str,
        *,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataWorkflow:
        """HTTP GET request returning a workflow over decoded response data."""
        return self.request_workflow("GET", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        """HTTP POST request."""
        return self.request("POST", endpoint, **kwargs)

    def post_data(self, endpoint: str, *, suffix: str | None = None, as_extended: bool = True, **kwargs: Any) -> Any:
        """HTTP POST request returning decoded response data."""
        return self.request_data("POST", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def post_workflow(
        self,
        endpoint: str,
        *,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataWorkflow:
        """HTTP POST request returning a workflow over decoded response data."""
        return self.request_workflow("POST", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def put(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        """HTTP PUT request."""
        return self.request("PUT", endpoint, **kwargs)

    def put_data(self, endpoint: str, *, suffix: str | None = None, as_extended: bool = True, **kwargs: Any) -> Any:
        """HTTP PUT request returning decoded response data."""
        return self.request_data("PUT", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def put_workflow(
        self,
        endpoint: str,
        *,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataWorkflow:
        """HTTP PUT request returning a workflow over decoded response data."""
        return self.request_workflow("PUT", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        """HTTP DELETE request."""
        return self.request("DELETE", endpoint, **kwargs)

    def delete_data(self, endpoint: str, *, suffix: str | None = None, as_extended: bool = True, **kwargs: Any) -> Any:
        """HTTP DELETE request returning decoded response data."""
        return self.request_data("DELETE", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def delete_workflow(
        self,
        endpoint: str,
        *,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataWorkflow:
        """HTTP DELETE request returning a workflow over decoded response data."""
        return self.request_workflow("DELETE", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def patch(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        """HTTP PATCH request."""
        return self.request("PATCH", endpoint, **kwargs)

    def patch_data(self, endpoint: str, *, suffix: str | None = None, as_extended: bool = True, **kwargs: Any) -> Any:
        """HTTP PATCH request returning decoded response data."""
        return self.request_data("PATCH", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    def patch_workflow(
        self,
        endpoint: str,
        *,
        suffix: str | None = None,
        as_extended: bool = True,
        **kwargs: Any,
    ) -> DataWorkflow:
        """HTTP PATCH request returning a workflow over decoded response data."""
        return self.request_workflow("PATCH", endpoint, suffix=suffix, as_extended=as_extended, **kwargs)

    # -------------------------------------------------------------------------
    # File Downloads
    # -------------------------------------------------------------------------

    def download(self, url: str, output_path: str) -> int:
        """Download file from URL.

        Args:
            url: URL to download from
            output_path: Local path to save to

        Returns:
            File size in bytes
        """
        import os

        dirname = os.path.dirname(output_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # Use a separate client for downloads (different timeout)
        response = httpx.get(url, timeout=600.0)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        return len(response.content)
