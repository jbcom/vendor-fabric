"""Zoom connector built on extended-data primitives."""

from __future__ import annotations

import base64

from collections.abc import Iterable, Mapping
from typing import Any

import requests

from extended_data.containers import ExtendedDict, ExtendedList, to_builtin
from extended_data.io.files import decode_file
from extended_data.logging import Logging
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.base import ConnectorBase


# Default timeout for HTTP requests in seconds
DEFAULT_REQUEST_TIMEOUT = 30


def _safe_zoom_text(value: Any, *sensitive_values: Any) -> str:
    """Redact secrets and request identifiers from Zoom diagnostics."""
    return redact_sensitive_text(value, values=_iter_diagnostic_values(sensitive_values))


def _iter_diagnostic_values(values: Iterable[Any]) -> Iterable[Any]:
    """Yield scalar values from nested diagnostic context."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, Mapping):
            yield from _iter_diagnostic_values(value.values())
        elif isinstance(value, (str, bytes)):
            yield value
        elif isinstance(value, Iterable):
            yield from _iter_diagnostic_values(value)
        else:
            yield value


def _zoom_error(action: str, exc: BaseException, *sensitive_values: Any) -> str:
    """Build a redacted Zoom operational error message."""
    return f"{action}: {_safe_zoom_text(exc, *sensitive_values)}"


def _zoom_response_error(action: str, data: Any, *sensitive_values: Any) -> RuntimeError:
    """Build a redacted malformed-response error."""
    return RuntimeError(f"{action}: {_safe_zoom_text(data, *sensitive_values)}")


class ZoomConnector(ConnectorBase):
    """Zoom connector for user management."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        account_id: str | None = None,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(logger=logger, **kwargs)
        self.errors: list[str] = []  # Track errors for programmatic access

        self.client_id = client_id or self.get_input("ZOOM_CLIENT_ID", required=True)
        self.client_secret = client_secret or self.get_input("ZOOM_CLIENT_SECRET", required=True)
        self.account_id = account_id or self.get_input("ZOOM_ACCOUNT_ID", required=True)

    def _response_json(self, response: Any, action: str, *sensitive_values: Any) -> Any:
        """Parse a Zoom JSON response or raise a redacted diagnostic."""
        content = getattr(response, "content", b"")
        if not content:
            return {}
        try:
            return decode_file(content, suffix="json", as_extended=True)
        except Exception:
            raise _zoom_response_error(action, getattr(response, "text", content), *sensitive_values) from None

    def _response_mapping(self, response: Any, action: str, *sensitive_values: Any) -> dict[str, Any]:
        """Parse and validate a Zoom object response."""
        data = self._response_json(response, action, *sensitive_values)
        if not isinstance(data, Mapping):
            raise _zoom_response_error(action, data, *sensitive_values)
        return to_builtin(data)

    def _response_list_field(
        self,
        response: Any,
        field_name: str,
        action: str,
        *sensitive_values: Any,
    ) -> list[dict[str, Any]]:
        """Parse and validate a Zoom list field containing object payloads."""
        data = self._response_mapping(response, action, *sensitive_values)
        items = data.get(field_name, [])
        if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
            raise _zoom_response_error(action, data, *sensitive_values)
        return [dict(item) for item in items]

    def get_access_token(self) -> str | None:
        """Get an OAuth access token from Zoom."""
        url = "https://zoom.us/oauth/token"
        auth_string = f"{self.client_id}:{self.client_secret}"
        headers = {
            "Authorization": f"Basic {base64.b64encode(auth_string.encode()).decode()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "account_credentials", "account_id": self.account_id}

        try:
            response = requests.post(url, headers=headers, data=data, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            token_data = self._response_mapping(
                response,
                "Unexpected Zoom access token response",
                self.client_id,
                self.client_secret,
                self.account_id,
            )
            token = token_data.get("access_token")
            if not isinstance(token, str) or not token.strip():
                raise _zoom_response_error(
                    "Unexpected Zoom access token response",
                    token_data,
                    self.client_id,
                    self.client_secret,
                    self.account_id,
                )
            return token
        except requests.exceptions.RequestException as exc:
            msg = _zoom_error(
                "Failed to get Zoom access token",
                exc,
                self.client_id,
                self.client_secret,
                self.account_id,
            )
            raise RuntimeError(msg) from None

    def get_headers(self) -> dict[str, str]:
        """Get headers with authorization for Zoom API calls."""
        token = self.get_access_token()
        if not token:
            msg = "Failed to get access token"
            raise RuntimeError(msg)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def list_users(self) -> ExtendedDict:
        """List all Zoom users.

        Returns:
            Dictionary mapping user emails to user data.
        """
        url = "https://api.zoom.us/v2/users"
        headers = self.get_headers()
        users: dict[str, dict[str, Any]] = {}
        page_size = 300
        next_page_token = None

        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if next_page_token:
                params["next_page_token"] = next_page_token

            try:
                response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
                response.raise_for_status()
                data = self._response_mapping(response, "Unexpected Zoom users response", next_page_token, params)
                raw_users = data.get("users", [])
                if not isinstance(raw_users, list):
                    raise _zoom_response_error("Unexpected Zoom users response", data, next_page_token, params)
                for user in raw_users:
                    if not isinstance(user, Mapping) or not isinstance(user.get("email"), str):
                        raise _zoom_response_error("Unexpected Zoom users response", data, next_page_token, params)
                    users[user["email"]] = dict(user)

                next_page_token = data.get("next_page_token")
                if next_page_token is not None and not isinstance(next_page_token, str):
                    raise _zoom_response_error("Unexpected Zoom users response", data, next_page_token, params)
                if not next_page_token:
                    break
            except requests.exceptions.RequestException as exc:
                raise RuntimeError(_zoom_error("Failed to get Zoom users", exc, next_page_token, params)) from None

        return self.extend_result(users)

    def remove_zoom_user(self, email: str) -> None:
        """Remove a Zoom user."""
        url = f"https://api.zoom.us/v2/users/{email}"
        headers = self.get_headers()
        try:
            response = requests.delete(url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            self.logger.warning("Removed Zoom user")
        except requests.exceptions.RequestException as exc:
            error_msg = _zoom_error("Failed to remove Zoom user", exc, email)
            self.errors.append(error_msg)
            self.logger.error(error_msg)  # noqa: TRY400 - traceback can expose raw Zoom user identifiers.

    def create_zoom_user(self, email: str, first_name: str, last_name: str) -> bool:
        """Create a Zoom user with a paid license."""
        url = "https://api.zoom.us/v2/users"
        headers = self.get_headers()
        user_info = {
            "action": "create",
            "user_info": {"email": email, "type": 2, "first_name": first_name, "last_name": last_name},
        }
        try:
            response = requests.post(url, headers=headers, json=user_info, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            self.logger.info("Created Zoom user")
            return True
        except requests.exceptions.RequestException as exc:
            error_msg = _zoom_error("Failed to create Zoom user", exc, email, first_name, last_name)
            self.errors.append(error_msg)
            self.logger.error(error_msg)  # noqa: TRY400 - traceback can expose raw Zoom user identifiers.
            return False

    def get_user(self, user_id: str) -> ExtendedDict:
        """Get a specific Zoom user by ID or email.

        Args:
            user_id: User ID or email address

        Returns:
            User data dictionary
        """
        url = f"https://api.zoom.us/v2/users/{user_id}"
        headers = self.get_headers()

        try:
            response = requests.get(url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            return self.extend_result(self._response_mapping(response, "Unexpected Zoom user response", user_id))
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(_zoom_error("Failed to get Zoom user", exc, user_id)) from None

    def list_meetings(self, user_id: str, meeting_type: str = "scheduled") -> ExtendedList[ExtendedDict]:
        """List meetings for a specific user.

        Args:
            user_id: User ID or email address
            meeting_type: Type of meetings to list (scheduled, live, upcoming, previous_meetings)

        Returns:
            List of meeting data dictionaries
        """
        url = f"https://api.zoom.us/v2/users/{user_id}/meetings"
        headers = self.get_headers()
        params = {"type": meeting_type}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            return self.extend_result(
                self._response_list_field(response, "meetings", "Unexpected Zoom meetings response", user_id, params)
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(_zoom_error("Failed to list Zoom meetings", exc, user_id, params)) from None

    def get_meeting(self, meeting_id: str) -> ExtendedDict:
        """Get details of a specific meeting.

        Args:
            meeting_id: Meeting ID

        Returns:
            Meeting data dictionary
        """
        url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
        headers = self.get_headers()

        try:
            response = requests.get(url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            return self.extend_result(self._response_mapping(response, "Unexpected Zoom meeting response", meeting_id))
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(_zoom_error("Failed to get Zoom meeting", exc, meeting_id)) from None


__all__ = [
    # Core connector
    "ZoomConnector",
]
