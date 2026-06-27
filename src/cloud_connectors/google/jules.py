"""Google Jules Connector - HTTP client for Google Jules AI Agent API.

Jules is Google's AI coding agent that can analyze code, create PRs,
and automate development tasks.

Usage:
    from cloud_connectors.google.jules import JulesConnector

    connector = JulesConnector(api_key="...")

    # List available sources (GitHub repos)
    sources = connector.list_sources()

    # Create a session
    session = connector.create_session(
        prompt="Fix the login bug",
        source="sources/github/org/repo",
        automation_mode="AUTO_CREATE_PR"
    )

    # Poll for completion
    status = connector.get_session(session["name"])

Reference: https://developers.google.com/jules/api
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from enum import StrEnum
from typing import Any

import httpx

from extended_data.containers import ExtendedDict, ExtendedList, to_builtin
from extended_data.primitives.redaction import redact_sensitive_data
from pydantic import BaseModel, Field, ValidationError

from cloud_connectors.base import ConnectorBase
from cloud_connectors.google._diagnostics import safe_google_text


__all__ = [
    "JulesConnector",
    "JulesError",
    "PullRequestOutput",
    "Session",
    "SessionState",
    "Source",
    "SourceContext",
]


class SessionState(StrEnum):
    """Jules session states."""

    UNSPECIFIED = "SESSION_STATE_UNSPECIFIED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
    AWAITING_USER_RESPONSE = "AWAITING_USER_RESPONSE"
    CANCELLED = "CANCELLED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"


class AutomationMode(StrEnum):
    """Automation modes for Jules sessions."""

    UNSPECIFIED = "AUTOMATION_MODE_UNSPECIFIED"
    AUTO_CREATE_PR = "AUTO_CREATE_PR"
    MANUAL = "MANUAL"


class Source(BaseModel):
    """A connected source (e.g., GitHub repository)."""

    name: str = Field(..., description="Resource name (e.g., sources/github/org/repo)")
    id: str = Field(..., description="Source ID")
    github_repo: dict[str, Any] | None = Field(None, alias="githubRepo")


class SourceContext(BaseModel):
    """Context for a session's source."""

    source: str = Field(..., description="Source resource name")
    github_repo_context: dict[str, Any] | None = Field(None, alias="githubRepoContext")


class PullRequestOutput(BaseModel):
    """Pull request created by Jules."""

    url: str = Field(..., description="GitHub PR URL")
    title: str = Field("", description="PR title")
    description: str = Field("", description="PR description")


class Session(BaseModel):
    """A Jules session."""

    model_config = {"extra": "allow"}  # Allow unknown fields

    name: str = Field(..., description="Resource name (e.g., sessions/123)")
    id: str = Field("", description="Session ID")
    title: str = Field("", description="Session title")
    prompt: str = Field("", description="Original prompt")
    state: str | None = Field(None, description="Current state")
    source_context: SourceContext | None = Field(None, alias="sourceContext")
    outputs: list[dict[str, Any]] = Field(default_factory=list, description="Session outputs")

    @property
    def pull_request(self) -> PullRequestOutput | None:
        """Get the pull request output if available."""
        for output in self.outputs:
            if "pullRequest" in output:
                return PullRequestOutput(**output["pullRequest"])
        return None


class JulesError(Exception):
    """Error from Jules API."""

    def __init__(self, message: str, code: int = 0, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


class JulesConnector(ConnectorBase):
    """Connector for Google Jules AI Agent API.

    Provides methods to interact with Jules for automated coding tasks.
    """

    BASE_URL = "https://jules.googleapis.com/v1alpha"
    API_KEY_ENV = "JULES_API_KEY"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        """Initialize the Jules connector.

        Args:
            api_key: Jules API key. Defaults to JULES_API_KEY env var.
            base_url: API base URL. Defaults to production.
            timeout: Request timeout in seconds.
            **kwargs: Extra arguments for base class.
        """
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout, **kwargs)

    def _build_headers(self) -> dict[str, str]:
        """Build Jules-specific headers."""
        return {
            "X-Goog-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _handle_response(self, response: httpx.Response, operation: str, *sensitive_values: Any) -> dict[str, Any]:
        """Handle API response, raising redacted errors for API or payload failures."""
        diagnostic_values = self._response_diagnostic_values(response, *sensitive_values)
        if not response.is_success:
            self._raise_api_error(response, operation, diagnostic_values)

        data = self._response_json(response, operation, diagnostic_values)
        if not isinstance(data, Mapping):
            raise self._unexpected_response_error(operation, data, response.status_code, diagnostic_values)
        return to_builtin(data)

    def _raise_api_error(
        self,
        response: httpx.Response,
        operation: str,
        diagnostic_values: list[Any],
    ) -> None:
        """Raise a Jules API error with all details redacted."""
        try:
            error_data = self._response_json(response, operation, diagnostic_values)
        except JulesError:
            raise JulesError(safe_google_text(response.text, diagnostic_values), response.status_code) from None

        raw_error = error_data.get("error", {}) if isinstance(error_data, Mapping) else {}
        error = raw_error if isinstance(raw_error, Mapping) else {}
        error_code = error.get("code", response.status_code)
        if not isinstance(error_code, int):
            error_code = response.status_code

        raise JulesError(
            safe_google_text(error.get("message", response.text), diagnostic_values),
            error_code,
            redact_sensitive_data(to_builtin(error.get("details")), values=diagnostic_values),
        )

    def _response_json(self, response: httpx.Response, operation: str, diagnostic_values: list[Any]) -> Any:
        """Parse JSON response content or raise a redacted malformed-response error."""
        if not response.content:
            return {}
        try:
            return self.decode_response(response, suffix="json", as_extended=True)
        except Exception:
            raise self._unexpected_response_error(
                operation,
                response.text,
                response.status_code,
                diagnostic_values,
            ) from None

    @staticmethod
    def _unexpected_response_error(
        operation: str,
        data: Any,
        status_code: int,
        diagnostic_values: list[Any],
    ) -> JulesError:
        """Build a redacted malformed-response error."""
        return JulesError(
            f"Unexpected Jules response for {operation}: {safe_google_text(data, diagnostic_values)}",
            status_code,
        )

    def _response_diagnostic_values(self, response: httpx.Response, *sensitive_values: Any) -> list[Any]:
        """Collect caller-controlled response identifiers for diagnostics redaction."""
        values: list[Any] = [self._base_url, self._api_key, *sensitive_values]
        with suppress(RuntimeError):
            values.append(str(response.request.url))
        return values

    # =========================================================================
    # Sources
    # =========================================================================

    @staticmethod
    def _model_payload(model: BaseModel) -> dict[str, Any]:
        """Serialize a Jules model using API field aliases."""
        return model.model_dump(by_alias=True)

    def _parse_model_response(
        self,
        data: Any,
        model_type: type[BaseModel],
        operation: str,
        *sensitive_values: Any,
    ) -> dict[str, Any]:
        """Validate one Jules response model and return a JSON payload."""
        try:
            return self._model_payload(model_type.model_validate(to_builtin(data)))
        except ValidationError:
            raise self._unexpected_response_error(
                operation,
                data,
                200,
                list(sensitive_values),
            ) from None

    def _parse_model_list(
        self,
        data: Mapping[str, Any],
        field_name: str,
        model_type: type[BaseModel],
        operation: str,
        *sensitive_values: Any,
    ) -> list[dict[str, Any]]:
        """Validate a Jules response list and return JSON payloads."""
        items = data.get(field_name)
        if not isinstance(items, list):
            raise self._unexpected_response_error(operation, data, 200, list(sensitive_values))

        try:
            return [self._model_payload(model_type.model_validate(to_builtin(item))) for item in items]
        except ValidationError:
            raise self._unexpected_response_error(operation, data, 200, list(sensitive_values)) from None

    def list_sources(self, page_size: int = 100, page_token: str = "") -> ExtendedList[ExtendedDict]:
        """List available sources (connected GitHub repos).

        Args:
            page_size: Maximum number of results.
            page_token: Pagination token.

        Returns:
            List of Source objects.
        """
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token

        response = self.get("/sources", params=params)
        data = self._handle_response(response, "list_sources", params)

        return self.extend_result(self._parse_model_list(data, "sources", Source, "list_sources", params))

    # =========================================================================
    # Sessions
    # =========================================================================

    def create_session(
        self,
        prompt: str,
        source: str,
        title: str = "",
        starting_branch: str = "main",
        automation_mode: str = "AUTO_CREATE_PR",
        require_plan_approval: bool = False,
    ) -> ExtendedDict:
        """Create a new Jules session.

        Args:
            prompt: Task description for Jules.
            source: Source resource name (e.g., sources/github/org/repo).
            title: Optional session title.
            starting_branch: Git branch to start from.
            automation_mode: AUTO_CREATE_PR or MANUAL.
            require_plan_approval: Whether to require explicit plan approval.

        Returns:
            Created Session object.
        """
        body: dict[str, Any] = {
            "prompt": prompt,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {
                    "startingBranch": starting_branch,
                },
            },
            "automationMode": automation_mode,
        }

        if title:
            body["title"] = title
        if require_plan_approval:
            body["requirePlanApproval"] = True

        response = self.post("/sessions", json=body)
        data = self._handle_response(response, "create_session", body)

        return self.extend_result(self._parse_model_response(data, Session, "create_session", body))

    def get_session(self, session_name: str) -> ExtendedDict:
        """Get a session by name.

        Args:
            session_name: Full resource name (e.g., sessions/123).

        Returns:
            Session object with current state.
        """
        # Handle both full name and just ID
        if not session_name.startswith("sessions/"):
            session_name = f"sessions/{session_name}"

        response = self.get(f"/{session_name}")
        data = self._handle_response(response, "get_session", session_name)

        return self.extend_result(self._parse_model_response(data, Session, "get_session", session_name))

    def list_sessions(self, page_size: int = 20, page_token: str = "") -> ExtendedList[ExtendedDict]:
        """List sessions.

        Args:
            page_size: Maximum number of results.
            page_token: Pagination token.

        Returns:
            List of Session objects.
        """
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token

        response = self.get("/sessions", params=params)
        data = self._handle_response(response, "list_sessions", params)

        return self.extend_result(self._parse_model_list(data, "sessions", Session, "list_sessions", params))

    def approve_plan(self, session_name: str) -> ExtendedDict:
        """Approve the plan for a session that requires approval.

        Args:
            session_name: Full resource name.

        Returns:
            Updated Session object.
        """
        if not session_name.startswith("sessions/"):
            session_name = f"sessions/{session_name}"

        response = self.post(f"/{session_name}:approvePlan")
        self._handle_response(response, "approve_plan", session_name)

        # API returns empty on success, fetch updated session
        return self.get_session(session_name)

    def add_user_response(self, session_name: str, message: str) -> ExtendedDict:
        """Add a follow-up message to a session or resume it.

        Note: The Jules API uses the :sendMessage endpoint with a required
        prompt body. The response body is empty on success, so this method
        fetches and returns the updated session.

        Args:
            session_name: Full resource name.
            message: Optional user message.

        Returns:
            Updated Session object.
        """
        if not isinstance(message, str) or not message.strip():
            msg = "Jules sendMessage requires a non-empty prompt"
            raise ValueError(msg)

        if not session_name.startswith("sessions/"):
            session_name = f"sessions/{session_name}"

        body = {"prompt": message}
        response = self.post(f"/{session_name}:sendMessage", json=body)
        self._handle_response(response, "add_user_response", session_name, body)

        # API returns empty on success, fetch updated session
        return self.get_session(session_name)

    def resume_session(self, session_name: str, message: str) -> ExtendedDict:
        """Resume a paused or awaiting session by sending a follow-up prompt.

        Args:
            session_name: Full resource name.
            message: User prompt to send to the session.

        Returns:
            Updated Session object.
        """
        return self.add_user_response(session_name, message)
