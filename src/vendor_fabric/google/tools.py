"""AI framework tools for Google Cloud and Workspace operations.

This module provides tools for Google Cloud and Workspace operations that work
with multiple AI agent frameworks. The core functions are framework-agnostic
Python functions, with native wrappers for each supported framework.

Supported Frameworks:
- LangChain (via langchain-core) - get_langchain_tools()
- CrewAI - get_crewai_tools()
- AWS Strands - get_strands_tools() (plain functions)
- Auto-detection - get_tools() picks the best available

Tools provided:
- google_list_projects: List GCP projects
- google_list_folders: List GCP folders under a parent
- google_list_enabled_services: List enabled services in a project
- google_list_billing_accounts: List billing accounts
- google_list_workspace_users: List Workspace users
- google_list_workspace_groups: List Workspace groups

Usage:
    from vendor_fabric.google.tools import get_tools
    tools = get_tools()  # Returns best format for installed framework
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from pydantic import BaseModel, Field

from vendor_fabric.ai_tools import raise_unknown_tool_framework


# =============================================================================
# Input Schemas
# =============================================================================


class ListProjectsSchema(BaseModel):
    """Schema for listing Google Cloud projects."""

    parent: str = Field(
        "", description="Parent resource (e.g., 'organizations/123' or 'folders/456'). Leave empty for all projects."
    )
    max_results: int = Field(100, description="Maximum number of projects to return.")


class ListFoldersSchema(BaseModel):
    """Schema for listing Google Cloud folders."""

    parent: str = Field(..., description="Parent resource (e.g., 'organizations/123' or 'folders/456').")
    max_results: int = Field(100, description="Maximum number of folders to return.")


class ListEnabledServicesSchema(BaseModel):
    """Schema for listing enabled services in a project."""

    project_id: str = Field(..., description="The GCP project ID to list services for.")
    max_results: int = Field(100, description="Maximum number of services to return.")


class ListBillingAccountsSchema(BaseModel):
    """Schema for listing Google Cloud billing accounts."""

    max_results: int = Field(100, description="Maximum number of billing accounts to return.")


class ListWorkspaceUsersSchema(BaseModel):
    """Schema for listing Google Workspace users."""

    domain: str = Field("", description="Domain to list users from. Leave empty for default domain.")
    max_results: int = Field(100, description="Maximum number of users to return.")


class ListWorkspaceGroupsSchema(BaseModel):
    """Schema for listing Google Workspace groups."""

    domain: str = Field("", description="Domain to list groups from. Leave empty for default domain.")
    max_results: int = Field(100, description="Maximum number of groups to return.")


# =============================================================================
# Tool Implementation Functions
# =============================================================================


def list_projects(
    parent: str = "",
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List Google Cloud projects.

    Args:
        parent: Parent resource (e.g., 'organizations/123' or 'folders/456').
                Leave empty to list all accessible projects.
        max_results: Maximum number of projects to return.

    Returns:
        List of project info (project_id, name, state, parent).
    """
    from vendor_fabric.google import GoogleConnector

    connector = GoogleConnector()
    projects = connector.list_projects(parent=parent or None)

    # Limit results and extract key fields
    result = []
    for project in projects[:max_results]:
        result.append(
            {
                "project_id": project.get("projectId", ""),
                "name": project.get("displayName") or project.get("name", ""),
                "state": project.get("state", ""),
                "parent": project.get("parent", ""),
            }
        )

    return extend_data(result)


def list_folders(
    parent: str,
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List folders under a parent resource.

    Args:
        parent: Parent resource (organizations/ORG_ID or folders/FOLDER_ID).
        max_results: Maximum number of folders to return.

    Returns:
        List of folder info (name, display_name, state, parent).
    """
    from vendor_fabric.google import GoogleConnector

    connector = GoogleConnector()
    folders = connector.list_folders(parent=parent)

    # Limit results and extract key fields
    result = []
    for folder in folders[:max_results]:
        result.append(
            {
                "name": folder.get("name", ""),
                "display_name": folder.get("displayName", ""),
                "state": folder.get("state", ""),
                "parent": folder.get("parent", ""),
            }
        )

    return extend_data(result)


def list_enabled_services(
    project_id: str,
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List enabled services in a Google Cloud project.

    Args:
        project_id: The GCP project ID to list services for.
        max_results: Maximum number of services to return.

    Returns:
        List of service info (name, title, state).
    """
    from vendor_fabric.google import GoogleConnector

    connector = GoogleConnector()
    services = connector.list_enabled_services(project_id=project_id)

    # Limit results and extract key fields
    result = []
    for service in services[:max_results]:
        result.append(
            {
                "name": service.get("name", ""),
                "title": service.get("config", {}).get("title", ""),
                "state": service.get("state", ""),
            }
        )

    return extend_data(result)


def list_billing_accounts(
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List Google Cloud billing accounts.

    Args:
        max_results: Maximum number of billing accounts to return.

    Returns:
        List of billing account info (name, display_name, open, master_billing_account).
    """
    from vendor_fabric.google import GoogleConnector

    connector = GoogleConnector()
    accounts = connector.list_billing_accounts()

    # Limit results and extract key fields
    result = []
    for account in accounts[:max_results]:
        result.append(
            {
                "name": account.get("name", ""),
                "display_name": account.get("displayName", ""),
                "open": account.get("open", False),
                "master_billing_account": account.get("masterBillingAccount", ""),
            }
        )

    return extend_data(result)


def list_workspace_users(
    domain: str = "",
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List users from Google Workspace.

    Args:
        domain: Domain to list users from. Leave empty for default domain.
        max_results: Maximum number of users to return.

    Returns:
        List of user info (email, name, full_name, suspended, org_unit_path).
    """
    from vendor_fabric.google import GoogleConnector

    connector = GoogleConnector()
    users_raw: Any = connector.list_users(
        domain=domain or None,
        flatten_names=True,
        key_by_email=False,
    )
    users = list(users_raw.values()) if isinstance(users_raw, Mapping) else users_raw

    # Limit results and extract key fields
    result: list[dict[str, Any]] = []
    for user in users[:max_results]:
        if not isinstance(user, Mapping):
            continue
        name = user.get("name", {})
        result.append(
            {
                "email": user.get("primaryEmail", ""),
                "name": name.get("fullName", "") if isinstance(name, Mapping) else "",
                "full_name": user.get("full_name", ""),
                "suspended": user.get("suspended", False),
                "org_unit_path": user.get("orgUnitPath", ""),
            }
        )

    return extend_data(result)


def list_workspace_groups(
    domain: str = "",
    max_results: int = 100,
) -> ExtendedList[ExtendedDict]:
    """List groups from Google Workspace.

    Args:
        domain: Domain to list groups from. Leave empty for default domain.
        max_results: Maximum number of groups to return.

    Returns:
        List of group info (email, name, description, direct_members_count).
    """
    from vendor_fabric.google import GoogleConnector

    connector = GoogleConnector()
    groups_raw: Any = connector.list_groups(
        domain=domain or None,
        key_by_email=False,
    )
    groups = list(groups_raw.values()) if isinstance(groups_raw, Mapping) else groups_raw

    # Limit results and extract key fields
    result: list[dict[str, Any]] = []
    for group in groups[:max_results]:
        if not isinstance(group, Mapping):
            continue
        result.append(
            {
                "email": group.get("email", ""),
                "name": group.get("name", ""),
                "description": group.get("description", ""),
                "direct_members_count": group.get("directMembersCount", 0),
            }
        )

    return extend_data(result)


# =============================================================================
# Tool Definitions
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "google_list_projects",
        "description": "List Google Cloud projects with their IDs, names, and states.",
        "func": list_projects,
        "schema": ListProjectsSchema,
    },
    {
        "name": "google_list_folders",
        "description": "List Google Cloud folders under a parent organization or folder.",
        "func": list_folders,
        "schema": ListFoldersSchema,
    },
    {
        "name": "google_list_enabled_services",
        "description": "List enabled APIs/services in a Google Cloud project.",
        "func": list_enabled_services,
        "schema": ListEnabledServicesSchema,
    },
    {
        "name": "google_list_billing_accounts",
        "description": "List Google Cloud billing accounts with their status.",
        "func": list_billing_accounts,
        "schema": ListBillingAccountsSchema,
    },
    {
        "name": "google_list_workspace_users",
        "description": "List users from Google Workspace with their details.",
        "func": list_workspace_users,
        "schema": ListWorkspaceUsersSchema,
    },
    {
        "name": "google_list_workspace_groups",
        "description": "List groups from Google Workspace with member counts.",
        "func": list_workspace_groups,
        "schema": ListWorkspaceGroupsSchema,
    },
]


# =============================================================================
# Framework-Specific Getters
# =============================================================================


def get_langchain_tools() -> list[Any]:
    """Get all Google tools as LangChain StructuredTools.

    Returns:
        List of LangChain StructuredTool objects.

    Raises:
        ImportError: If langchain-core is not installed.
    """
    from vendor_fabric.ai_tools import build_langchain_tools

    return build_langchain_tools(TOOL_DEFINITIONS)


def get_crewai_tools() -> list[Any]:
    """Get all Google tools as CrewAI tools.

    Returns:
        List of CrewAI BaseTool objects.

    Raises:
        ImportError: If crewai is not installed.
    """
    from vendor_fabric._optional import get_crewai_tool_decorator

    crewai_tool = get_crewai_tool_decorator()

    tools = []
    for defn in TOOL_DEFINITIONS:
        wrapped = crewai_tool(defn["name"])(defn["func"])
        wrapped.description = defn["description"]
        schema = defn.get("schema") or defn.get("args_schema")
        if schema:
            wrapped.args_schema = schema
        tools.append(wrapped)

    return tools


def get_strands_tools() -> list[Any]:
    """Get all Google tools as plain Python functions for AWS Strands.

    Returns:
        List of callable functions.
    """
    return [defn["func"] for defn in TOOL_DEFINITIONS]


def get_tools(framework: str = "auto") -> list[Any]:
    """Get Google tools for the specified or auto-detected framework.

    Args:
        framework: Framework to use. Options:
            - "auto" (default): Auto-detect based on installed packages
            - "langchain": Force LangChain StructuredTools
            - "crewai": Force CrewAI tools
            - "strands": Force plain functions for Strands

    Returns:
        List of tools in the appropriate format for the framework.

    Raises:
        ImportError: If the requested framework is not installed.
        ValueError: If an unknown framework is specified.
    """
    from vendor_fabric._optional import is_available

    if framework == "auto":
        if is_available("crewai"):
            return get_crewai_tools()
        if is_available("langchain_core"):
            return get_langchain_tools()
        return get_strands_tools()

    if framework == "langchain":
        return get_langchain_tools()
    if framework == "crewai":
        return get_crewai_tools()
    if framework == "strands":
        return get_strands_tools()

    return raise_unknown_tool_framework(framework)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Tool metadata
    "TOOL_DEFINITIONS",
    "get_crewai_tools",
    "get_langchain_tools",
    "get_strands_tools",
    # Framework-specific getters
    "get_tools",
    "list_billing_accounts",
    "list_enabled_services",
    "list_folders",
    # Raw functions
    "list_projects",
    "list_workspace_groups",
    "list_workspace_users",
]
