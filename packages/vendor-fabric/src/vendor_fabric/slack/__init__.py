"""Slack connector built on extended-data primitives."""

from __future__ import annotations

import sys

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import suppress
from time import sleep
from typing import Any


# batched was added in Python 3.12
if sys.version_info >= (3, 12):
    from itertools import batched as _batched
else:
    from itertools import islice

    def _batched(iterable: Iterable[Any], n: int) -> Iterator[tuple[Any, ...]]:
        """Batch an iterable into chunks of size n for Python < 3.12."""
        it = iter(iterable)
        while batch := tuple(islice(it, n)):
            yield batch


from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data, to_builtin
from extended_data.io import wrap_raw_data_for_export
from extended_data.logging import Logging
from extended_data.primitives import is_nothing
from extended_data.primitives.redaction import redact_sensitive_data, redact_sensitive_text

from vendor_fabric._optional import require_extra
from vendor_fabric.base import ConnectorBase


class SlackFallbackError(Exception):
    """Fallback exception used until slack-sdk is imported."""


SlackApiError: Any = SlackFallbackError
WebClient: Any = None


def _load_slack_sdk() -> None:
    """Load slack-sdk lazily so capability metadata can import without the slack extra."""
    global SlackApiError, WebClient

    if WebClient is None:
        try:
            if SlackApiError is SlackFallbackError:
                SlackApiError = require_extra("slack_sdk.errors", "slack").SlackApiError
            WebClient = require_extra("slack_sdk.web", "slack").WebClient
        except ImportError as exc:
            msg = "slack-sdk is required for SlackConnector. Install with: pip install vendor-fabric[slack]"
            raise ImportError(msg) from exc
    elif SlackApiError is SlackFallbackError:
        with suppress(ImportError):
            SlackApiError = require_extra("slack_sdk.errors", "slack").SlackApiError


# Settings
MAX_RETRY_TIMEOUT_SECONDS = 30


class SlackAPIError(RuntimeError):
    """Slack API error wrapper."""

    def __init__(self, response: Any) -> None:
        self.response = _slack_response_payload(response)
        self.status_code = response.status_code if hasattr(response, "status_code") else None
        super().__init__(f"Slack API error: {redact_sensitive_text(self.response)}")


def _slack_response_payload(response: Any) -> dict[str, Any]:
    """Normalize Slack SDK response objects into a serializable payload."""
    if isinstance(response, Mapping):
        return redact_sensitive_data(dict(response))

    data = getattr(response, "data", None)
    if isinstance(data, Mapping):
        return redact_sensitive_data(dict(data))

    payload: dict[str, Any] = {}
    response_get = getattr(response, "get", None)
    if callable(response_get):
        for key in ("ok", "error", "warning"):
            value = response_get(key)
            if value is not None:
                payload[key] = value

    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        payload["status_code"] = status_code

    return redact_sensitive_data(payload or {"response": str(response)})


def get_divider() -> ExtendedDict:
    """Return a Slack divider block.

    Returns:
        Extended Slack block definition for a divider element.
    """
    return extend_data({"type": "divider"})


def get_header_block(field_title: str) -> ExtendedList[ExtendedDict]:
    """Return header and divider blocks for a section title.

    Args:
        field_title: Title text to render in the header block.

    Returns:
        Extended Slack blocks containing a header followed by a divider.
    """
    return extend_data(
        [
            {"type": "header", "text": {"type": "plain_text", "text": field_title}},
            get_divider(),
        ]
    )


def get_field_context_message_blocks(field_name: str, context_data: Mapping[str, Any]) -> ExtendedList[ExtendedDict]:
    """Build header and context blocks for detailed field data.

    Args:
        field_name: Name rendered in the header section.
        context_data: Mapping of key/value pairs rendered inside context blocks.

    Returns:
        Extended Slack blocks describing the field data.
    """
    field_title = field_name.title()
    blocks: list[Any] = [
        {"type": "header", "text": {"type": "plain_text", "text": field_title}},
        get_divider(),
    ]

    for field_keys in _batched(context_data.keys(), 10):
        context_elements: list[dict[str, str]] = []
        for field_key in field_keys:
            field_value = context_data.get(field_key)
            if is_nothing(field_value):
                continue
            if isinstance(field_value, Mapping):
                field_value = wrap_raw_data_for_export(field_value, allow_encoding=True)
            field_value = str(field_value)
            context_elements.append({"type": "mrkdwn", "text": f"{field_key}: {field_value}"})

        blocks.extend([{"type": "context", "elements": context_elements}, get_divider()])

    return extend_data(blocks)


def get_key_value_blocks(k: str, v: Any) -> ExtendedList[ExtendedDict]:
    """Format a key/value pair into Slack section blocks.

    Args:
        k: Human-readable field label.
        v: Value to render. Mappings are encoded to Slack-safe text.

    Returns:
        Extended Slack section block followed by a divider.
    """
    k = k.title()
    if isinstance(v, Mapping):
        v = wrap_raw_data_for_export(v, allow_encoding=True)
    if not isinstance(v, str):
        v = str(v)

    return extend_data([{"type": "section", "text": {"type": "mrkdwn", "text": f"*{k}*: {v}"}}, get_divider()])


def get_rich_text_blocks(
    lines: list[str],
    bold: bool = False,
    italic: bool = False,
    strike: bool = False,
) -> ExtendedList[ExtendedDict]:
    """Build a rich text block for multiline messages.

    Args:
        lines: Message lines inserted as separate rich-text elements.
        bold: Whether to render text in bold.
        italic: Whether to render text in italics.
        strike: Whether to strike through the text.

    Returns:
        Extended rich-text block followed by a divider.
    """
    style: dict[str, bool] = {}
    if bold:
        style["bold"] = True
    if italic:
        style["italic"] = True
    if strike:
        style["strike"] = True

    elements: list[dict[str, Any]] = []
    for line in lines:
        element: dict[str, Any] = {"type": "text", "text": line}
        if not is_nothing(style):
            element["style"] = style
        elements.append(element)

    return extend_data([{"type": "rich_text", "elements": elements}, get_divider()])


class SlackConnector(ConnectorBase):
    """Slack connector for messaging, directory, and channel management."""

    def __init__(
        self,
        token: str | None = None,
        bot_token: str | None = None,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Slack connector.

        Args:
            token: Slack user token with directory scopes.
            bot_token: Bot token used for posting messages.
            logger: Optional shared logger instance.
            **kwargs: Extra keyword arguments forwarded to ConnectorBase.
        """
        super().__init__(logger=logger, **kwargs)
        _load_slack_sdk()

        self.token = token or self.get_input("SLACK_TOKEN", required=True)
        self.bot_token = bot_token or self.get_input("SLACK_BOT_TOKEN", required=True)

        self.web_client = WebClient(self.token)
        self.bot_web_client = WebClient(self.bot_token)

    @staticmethod
    def _normalize_identifier_filter(
        identifiers: str | Sequence[str] | None,
    ) -> set[str] | None:
        """Normalize comma-separated or iterable identifiers into a set.

        Args:
            identifiers: Identifiers passed as a string or iterable.

        Returns:
            Optional[set[str]]: Unique identifier set, or None when not provided.
        """
        if identifiers is None or is_nothing(identifiers):
            return None

        if isinstance(identifiers, str):
            raw_values = (value.strip() for value in identifiers.split(","))
        else:
            raw_values = (str(value).strip() for value in identifiers)

        normalized = {value for value in raw_values if value}
        return normalized or None

    def send_message(
        self,
        channel_name: str,
        text: str,
        blocks: list[Any] | ExtendedList[ExtendedDict] | None = None,
        lines: list[str] | None = None,
        bold: bool = False,
        italic: bool = False,
        strike: bool = False,
        thread_id: str | None = None,
        raise_on_api_error: bool = True,
    ) -> ExtendedString | ExtendedDict:
        """Send a message to a Slack channel using the bot token.

        Args:
            channel_name: Human-readable channel name (without #).
            text: Plain text fallback for the message body.
            blocks: Optional structured block payload to include.
            lines: Convenience helper to render rich-text lines.
            bold: Whether to bold the rendered lines.
            italic: Whether to italicize the rendered lines.
            strike: Whether to strike-through the rendered lines.
            thread_id: Optional thread timestamp to reply within a thread.
            raise_on_api_error: When True, raise `SlackAPIError` on API failures.

        Returns:
            Extended timestamp string, or an extended error payload when
            `raise_on_api_error=False`.

        Raises:
            RuntimeError: If the bot is not a member of the channel.
            SlackAPIError: When Slack returns an error and `raise_on_api_error` is True.
        """
        if blocks is None:
            blocks = []

        if lines and len(lines) > 0:
            blocks.extend(get_rich_text_blocks(lines=lines, bold=bold, italic=italic, strike=strike))

        channels = self.get_bot_channels()
        if channel_name not in channels:
            safe_channel_name = redact_sensitive_text(channel_name, values=[channel_name])
            raise RuntimeError(f"Bot not in channel {safe_channel_name}. Add the bot first.")

        channel_id = channels[channel_name].get("id")
        if is_nothing(channel_id):
            safe_channel_name = redact_sensitive_text(channel_name, values=[channel_name])
            raise RuntimeError(f"{safe_channel_name} does not have a channel ID")

        opts: dict[str, Any] = {"channel": channel_id, "text": text}
        if not is_nothing(blocks):
            opts["blocks"] = blocks
        if not is_nothing(thread_id):
            opts["thread_ts"] = thread_id

        try:
            return self.extend_result(self.bot_web_client.chat_postMessage(**to_builtin(opts)).get("ts"))
        except SlackApiError as exc:
            if raise_on_api_error:
                raise SlackAPIError(exc.response) from None
            return self.extend_result(_slack_response_payload(exc.response))

    def get_bot_channels(self) -> ExtendedDict:
        """Return channels the bot account is a member of.

        Returns:
            dict[str, dict]: Mapping of channel name to channel metadata.

        Raises:
            SlackAPIError: If Slack returns an error.
        """
        try:
            channels = {channel["name"]: channel for channel in self.bot_web_client.users_conversations()["channels"]}
            return self.extend_result(channels)
        except SlackApiError as exc:
            raise SlackAPIError(exc.response) from None

    def list_users(
        self,
        include_locale: bool | None = None,
        limit: int | None = None,
        team_id: str | None = None,
        include_deleted: bool | None = None,
        include_bots: bool | None = None,
        include_app_users: bool | None = None,
        **kwargs: Any,
    ) -> ExtendedDict:
        """List Slack users with optional filtering flags.

        Args:
            include_locale: When True, include the locale for each user.
            limit: Maximum number of users per API call.
            team_id: Optional team/workspace ID.
            include_deleted: Include deactivated accounts when True.
            include_bots: Include bot accounts when True.
            include_app_users: Include app users when True.
            **kwargs: Additional keyword arguments forwarded to `users_list`.

        Returns:
            dict[str, dict[str, Any]]: Filtered mapping of user IDs to user profiles.
        """
        if include_locale is None:
            include_locale = self.get_input("include_locale", required=False, is_bool=True)
        if limit is None:
            limit = self.get_input("limit", required=False, is_integer=True)
        if team_id is None:
            team_id = self.get_input("team_id", required=False)
        if include_deleted is None:
            include_deleted = self.get_input("include_deleted", required=False, default=False, is_bool=True)
        if include_bots is None:
            include_bots = self.get_input("include_bots", required=False, default=False, is_bool=True)
        if include_app_users is None:
            include_app_users = self.get_input("include_app_users", required=False, default=False, is_bool=True)

        self.logger.info("Retrieving users from Slack")
        response = self._call_api(
            "users_list", group_by="members", include_locale=include_locale, limit=limit, team_id=team_id, **kwargs
        )

        if include_deleted and include_bots and include_app_users:
            return self.extend_result(response)

        filtered = {}
        for user_id, user_data in response.items():
            deleted = user_data.get("deleted", False)
            is_bot = user_data.get("is_bot", False) or user_data.get("is_workflow_bot", False)
            is_app_user = user_data.get("is_app_user", False)

            if (
                (deleted and not include_deleted)
                or (is_bot and not include_bots)
                or (is_app_user and not include_app_users)
            ):
                continue
            filtered[user_id] = user_data

        return self.extend_result(filtered)

    def list_usergroups(
        self,
        include_disabled: bool | None = None,
        include_count: bool | None = None,
        include_users: bool | None = None,
        team_id: str | None = None,
        usergroup_ids: str | Sequence[str] | None = None,
        **kwargs: Any,
    ) -> ExtendedDict:
        """List Slack user groups with optional filtering.

        Args:
            include_disabled: Include disabled user groups when True.
            include_count: Include member counts when True.
            include_users: Include member lists when True.
            team_id: Optional workspace/team identifier.
            usergroup_ids: Comma-separated string or iterable of user group IDs to return.
            **kwargs: Extra keyword arguments forwarded to `usergroups_list`.

        Returns:
            dict[str, dict[str, Any]]: Mapping of user group IDs to metadata.
        """
        if include_disabled is None:
            include_disabled = self.get_input("include_disabled", required=False, default=False, is_bool=True)
        if include_count is None:
            include_count = self.get_input("include_count", required=False, default=False, is_bool=True)
        if include_users is None:
            include_users = self.get_input("include_users", required=False, default=False, is_bool=True)
        if team_id is None:
            team_id = self.get_input("team_id", required=False)

        identifier_filter = (
            usergroup_ids if usergroup_ids is not None else self.get_input("usergroup_ids", required=False)
        )
        normalized_ids = self._normalize_identifier_filter(identifier_filter)

        response = self._call_api(
            "usergroups_list",
            group_by="usergroups",
            include_disabled=include_disabled,
            include_count=include_count,
            include_users=include_users,
            team_id=team_id,
            **kwargs,
        )

        if not normalized_ids:
            return self.extend_result(response)

        return self.extend_result({gid: gdata for gid, gdata in response.items() if gid in normalized_ids})

    def list_conversations(
        self,
        exclude_archived: bool | None = None,
        limit: int | None = None,
        team_id: str | None = None,
        types: str | Sequence[str] | None = None,
        get_members: bool | None = None,
        channels_only: bool | None = None,
        **kwargs: Any,
    ) -> ExtendedDict:
        """List Slack conversations with optional filtering.

        Args:
            exclude_archived: Exclude archived conversations when True.
            limit: Maximum number of conversations to request.
            team_id: Optional workspace/team identifier.
            types: Slack channel type(s) (public_channel, private_channel, im, mpim).
            get_members: Include member lists when True.
            channels_only: Return only channel-type conversations when True.
            **kwargs: Extra keyword arguments forwarded to `conversations_list`.

        Returns:
            dict[str, dict[str, Any]]: Mapping of conversation IDs to metadata.
        """
        if exclude_archived is None:
            exclude_archived = self.get_input("exclude_archived", required=False, is_bool=True)
        if limit is None:
            limit = self.get_input("limit", required=False, is_integer=True)
        if team_id is None:
            team_id = self.get_input("team_id", required=False)
        if get_members is None:
            get_members = self.get_input("get_members", required=False, default=False, is_bool=True)
        if channels_only is None:
            channels_only = self.get_input("channels_only", required=False, default=False, is_bool=True)

        normalized_types: str | None
        if types is None or isinstance(types, str):
            normalized_types = types
        else:
            normalized_types = ",".join(
                sorted({str(channel_type).strip() for channel_type in types if str(channel_type).strip()})
            )

        self.logger.info("Getting Slack conversations")
        response = self._call_api(
            "conversations_list",
            group_by="channels",
            exclude_archived=exclude_archived,
            limit=limit,
            team_id=team_id,
            types=normalized_types,
            **kwargs,
        )

        if not channels_only:
            return self.extend_result(response)

        return self.extend_result({cid: cdata for cid, cdata in response.items() if cdata.get("is_channel")})

    def _call_api(
        self,
        method: str,
        group_by: str | None = None,
        id_field_name: str = "id",
        **kwargs: Any,
    ) -> Any:
        """Call a Slack WebClient method with retry and grouping support.

        Args:
            method: Slack WebClient method name to invoke.
            group_by: Optional response field containing a list to re-index by ID.
            id_field_name: Field used as the dictionary key when grouping results.
            **kwargs: Keyword arguments forwarded to the Slack API method.

        Returns:
            Any: Raw Slack response or grouped mapping when `group_by` is provided.

        Raises:
            AttributeError: If the requested method is not implemented by WebClient.
            SlackAPIError: When Slack returns an error other than rate limiting.
            TimeoutError: If rate-limited retries exceed `MAX_RETRY_TIMEOUT_SECONDS`.
        """
        call = getattr(self.web_client, method, None)
        safe_method = redact_sensitive_text(method)
        if call is None:
            raise AttributeError(f"{safe_method} is not supported by the Slack WebClient")

        response: Any | None = None
        attempt = 1
        total_delay = 0

        while not response:
            self.logger.debug(f"[Attempt {attempt}] Calling Slack WebClient {safe_method}...")
            try:
                response = call(**kwargs)
            except SlackApiError as exc:
                if exc.response["error"] == "ratelimited":
                    delay = int(exc.response.headers["Retry-After"])
                    total_delay += delay
                    if total_delay > MAX_RETRY_TIMEOUT_SECONDS:
                        raise TimeoutError(
                            f"Slack WebClient {safe_method} timed out after {total_delay} seconds"
                        ) from None
                    self.logger.warning(f"Rate limited. Retrying in {delay} seconds")
                    sleep(delay)
                    attempt += 1
                else:
                    raise SlackAPIError(exc.response) from None

        if is_nothing(response) or is_nothing(group_by):
            return response

        grouped: dict[str, dict[str, Any]] = {}
        for datum in response.get(group_by, {}):
            datum_id = datum.get(id_field_name)
            if is_nothing(datum_id):
                safe_field_name = redact_sensitive_text(id_field_name)
                safe_datum = redact_sensitive_data(datum)
                raise RuntimeError(f"No ID for field {safe_field_name} in returned datum: {safe_datum}")
            grouped[datum_id] = datum

        return grouped


__all__ = [
    # Exceptions
    "SlackAPIError",
    # Core connector
    "SlackConnector",
    # Helper functions
    "get_divider",
    "get_field_context_message_blocks",
    "get_header_block",
    "get_key_value_blocks",
    "get_rich_text_blocks",
]
