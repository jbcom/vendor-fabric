"""Provider capability functions for Zoom operations.

This module provides provider capability functions for Zoom operations.
"""

from __future__ import annotations

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from pydantic import BaseModel, Field


# =============================================================================
# Input Schemas
# =============================================================================


class ListUsersSchema(BaseModel):
    """Pydantic schema for the zoom_list_users tool."""

    max_results: int = Field(100, description="Maximum number of users to return.")


class GetUserSchema(BaseModel):
    """Pydantic schema for the zoom_get_user tool."""

    user_id: str = Field(..., description="User ID or email address.")


class ListMeetingsSchema(BaseModel):
    """Pydantic schema for the zoom_list_meetings tool."""

    user_id: str = Field(..., description="User ID or email address")
    meeting_type: str = Field(
        "scheduled", description="Type of meetings (scheduled, live, upcoming, previous_meetings)"
    )
    max_results: int = Field(100, description="Maximum number of meetings to return.")


class GetMeetingSchema(BaseModel):
    """Pydantic schema for the zoom_get_meeting tool."""

    meeting_id: str = Field(..., description="The unique meeting ID.")


# =============================================================================
# Capability Implementation Functions
# =============================================================================


def list_users(max_results: int = 100) -> ExtendedList[ExtendedDict]:
    """List Zoom users.

    Args:
        max_results: Max users to return.

    Returns:
        List of user data.
    """
    from vendor_fabric.zoom import ZoomConnector

    connector = ZoomConnector()
    users = connector.list_users()
    # Sort by email for consistent output in tests
    sorted_users = [users[email] for email in sorted(users.keys())]
    return extend_data(sorted_users[:max_results])


def get_user(user_id: str) -> ExtendedDict:
    """Get a specific Zoom user by ID or email.

    Args:
        user_id: User ID or email.

    Returns:
        User data.
    """
    from vendor_fabric.zoom import ZoomConnector

    connector = ZoomConnector()
    return extend_data(connector.get_user(user_id))


def list_meetings(
    user_id: str,
    meeting_type: str = "scheduled",
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List Zoom meetings for a specific user.

    Args:
        user_id: User ID or email.
        meeting_type: Meeting type.
        max_results: Max meetings to return.

    Returns:
        List of meeting data.
    """
    from vendor_fabric.zoom import ZoomConnector

    connector = ZoomConnector()
    meetings = connector.list_meetings(user_id, meeting_type)
    return extend_data(meetings[:max_results])


def get_meeting(meeting_id: str) -> ExtendedDict:
    """Get details of a specific Zoom meeting.

    Args:
        meeting_id: Meeting ID.

    Returns:
        Meeting data.
    """
    from vendor_fabric.zoom import ZoomConnector

    connector = ZoomConnector()
    return extend_data(connector.get_meeting(meeting_id))


# =============================================================================
# Tool Definitions
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "zoom_list_users",
        "description": "List Zoom users in the account.",
        "func": list_users,
        "schema": ListUsersSchema,
    },
    {
        "name": "zoom_get_user",
        "description": "Get detailed information about a specific Zoom user.",
        "func": get_user,
        "schema": GetUserSchema,
    },
    {
        "name": "zoom_list_meetings",
        "description": "List Zoom meetings for a specific user by their ID or email.",
        "func": list_meetings,
        "schema": ListMeetingsSchema,
    },
    {
        "name": "zoom_get_meeting",
        "description": "Get detailed information about a specific Zoom meeting.",
        "func": get_meeting,
        "schema": GetMeetingSchema,
    },
]


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "TOOL_DEFINITIONS",
    "get_meeting",
    "get_user",
    "list_meetings",
    "list_users",
]
