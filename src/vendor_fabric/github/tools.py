"""AI framework tools for GitHub operations.

This module provides tools for GitHub operations that work with multiple
AI agent frameworks.
"""

from __future__ import annotations

from typing import Any

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from pydantic import BaseModel, Field

from vendor_fabric.ai_tools import raise_unknown_tool_framework


# =============================================================================
# Input Schemas
# =============================================================================


class ListReposSchema(BaseModel):
    """Schema for listing GitHub repositories."""

    github_owner: str = Field(..., description="The GitHub organization or user name.")
    type_filter: str = Field("all", description="Type of repositories (all, public, private, forks, sources, member).")
    include_branches: bool = Field(False, description="Whether to include branch information.")
    github_token: str | None = Field(None, description="Optional GitHub token.")


class GetRepoSchema(BaseModel):
    """Schema for getting a GitHub repository."""

    github_owner: str = Field(..., description="The GitHub organization or user name.")
    repo_name: str = Field(..., description="The repository name.")
    github_token: str | None = Field(None, description="Optional GitHub token.")


class ListTeamsSchema(BaseModel):
    """Schema for listing GitHub teams."""

    github_owner: str = Field(..., description="The GitHub organization name.")
    include_members: bool = Field(False, description="Whether to include team members.")
    include_repos: bool = Field(False, description="Whether to include team repositories.")
    github_token: str | None = Field(None, description="Optional GitHub token.")


class GetTeamSchema(BaseModel):
    """Schema for getting a GitHub team."""

    github_owner: str = Field(..., description="The GitHub organization name.")
    team_slug: str = Field(..., description="The team slug.")
    github_token: str | None = Field(None, description="Optional GitHub token.")


class ListOrgMembersSchema(BaseModel):
    """Schema for listing GitHub organization members."""

    github_owner: str = Field(..., description="The GitHub organization name.")
    role: str = Field("member", description="Member role (admin, member).")
    include_pending: bool = Field(False, description="Whether to include pending invitations.")
    github_token: str | None = Field(None, description="Optional GitHub token.")


class GetRepositoryFileSchema(BaseModel):
    """Schema for getting a file from a GitHub repository."""

    github_owner: str = Field(..., description="The GitHub organization name.")
    github_repo: str = Field(..., description="The repository name.")
    file_path: str = Field(..., description="Path to the file in the repository.")
    github_branch: str | None = Field(None, description="Branch to get file from.")
    github_token: str | None = Field(None, description="Optional GitHub token.")


# =============================================================================
# Tool Implementation Functions
# =============================================================================


def list_repositories(
    github_owner: str,
    type_filter: str = "all",
    include_branches: bool = False,
    github_token: str | None = None,
    **kwargs: Any,
) -> ExtendedList[ExtendedDict]:
    """List repositories in a GitHub organization.

    Args:
        github_owner: Organization name.
        type_filter: Repository type filter.
        include_branches: Whether to include branch info.
        github_token: Optional GitHub token.

    Returns:
        List of repository data.
    """
    from vendor_fabric.github import GitHubConnector

    connector = GitHubConnector(github_owner=github_owner, github_token=github_token)
    repos = connector.list_repositories(type_filter=type_filter, include_branches=include_branches)

    result = []
    for name, data in repos.items():
        repo_data = data.copy()
        repo_data["name"] = name
        result.append(repo_data)
    return extend_data(result)


def get_repository(
    github_owner: str,
    repo_name: str,
    github_token: str | None = None,
    **kwargs: Any,
) -> ExtendedDict:
    """Get details of a specific GitHub repository.

    Args:
        github_owner: Organization name.
        repo_name: Repository name.
        github_token: Optional GitHub token.

    Returns:
        Dict with repository data and status.
    """
    from vendor_fabric.github import GitHubConnector

    connector = GitHubConnector(github_owner=github_owner, github_token=github_token)
    data = connector.get_repository(repo_name)

    if data:
        return extend_data({"status": "found", **data})
    return extend_data({"status": "not_found", "name": repo_name})


def list_teams(
    github_owner: str,
    include_members: bool = False,
    include_repos: bool = False,
    github_token: str | None = None,
    **kwargs: Any,
) -> ExtendedList[ExtendedDict]:
    """List teams in a GitHub organization.

    Args:
        github_owner: Organization name.
        include_members: Whether to include members.
        include_repos: Whether to include repos.
        github_token: Optional GitHub token.

    Returns:
        List of team data.
    """
    from vendor_fabric.github import GitHubConnector

    connector = GitHubConnector(github_owner=github_owner, github_token=github_token)
    teams = connector.list_teams(include_members=include_members, include_repos=include_repos)
    return extend_data(list(teams.values()))


def get_team(
    github_owner: str,
    team_slug: str,
    github_token: str | None = None,
    **kwargs: Any,
) -> ExtendedDict:
    """Get details of a specific GitHub team.

    Args:
        github_owner: Organization name.
        team_slug: Team slug.
        github_token: Optional GitHub token.

    Returns:
        Dict with team data and status.
    """
    from vendor_fabric.github import GitHubConnector

    connector = GitHubConnector(github_owner=github_owner, github_token=github_token)
    data = connector.get_team(team_slug)

    if data:
        return extend_data({"status": "found", **data})
    return extend_data({"status": "not_found", "slug": team_slug})


def list_org_members(
    github_owner: str,
    role: str = "member",
    include_pending: bool = False,
    github_token: str | None = None,
    **kwargs: Any,
) -> ExtendedList[ExtendedDict]:
    """List members of a GitHub organization.

    Args:
        github_owner: Organization name.
        role: Role filter.
        include_pending: Whether to include pending invites.
        github_token: Optional GitHub token.

    Returns:
        List of member data.
    """
    from vendor_fabric.github import GitHubConnector

    connector = GitHubConnector(github_owner=github_owner, github_token=github_token)
    members = connector.list_org_members(role=role, include_pending=include_pending)
    return extend_data(list(members.values()))


def get_repository_file(
    github_owner: str,
    github_repo: str,
    file_path: str,
    github_branch: str | None = None,
    github_token: str | None = None,
    **kwargs: Any,
) -> ExtendedDict:
    """Get a file from a GitHub repository.

    Args:
        github_owner: Organization name.
        github_repo: Repository name.
        file_path: File path.
        github_branch: Optional branch name.
        github_token: Optional GitHub token.

    Returns:
        Dict with content, sha, path, and status.
    """
    from vendor_fabric.github import GitHubConnector

    connector = GitHubConnector(
        github_owner=github_owner,
        github_repo=github_repo,
        github_branch=github_branch,
        github_token=github_token,
    )
    result = connector.get_repository_file(file_path, return_sha=True)

    content, sha = None, None
    if isinstance(result, tuple):
        content, sha = result[0], result[1]
    else:
        content = result

    status = "empty" if content is None else "retrieved"

    return extend_data(
        {
            "status": status,
            "path": file_path,
            "content": content,
            "sha": sha,
        }
    )


# =============================================================================
# Tool Definitions
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "github_list_repositories",
        "description": "List all repositories in a GitHub organization.",
        "func": list_repositories,
        "schema": ListReposSchema,
    },
    {
        "name": "github_get_repository",
        "description": "Get detailed information about a specific GitHub repository.",
        "func": get_repository,
        "schema": GetRepoSchema,
    },
    {
        "name": "github_list_teams",
        "description": "List all teams in a GitHub organization.",
        "func": list_teams,
        "schema": ListTeamsSchema,
    },
    {
        "name": "github_get_team",
        "description": "Get detailed information about a specific GitHub team.",
        "func": get_team,
        "schema": GetTeamSchema,
    },
    {
        "name": "github_list_org_members",
        "description": "List members of a GitHub organization.",
        "func": list_org_members,
        "schema": ListOrgMembersSchema,
    },
    {
        "name": "github_get_repository_file",
        "description": "Retrieve the content of a file from a GitHub repository.",
        "func": get_repository_file,
        "schema": GetRepositoryFileSchema,
    },
]


# =============================================================================
# Framework-Specific Getters
# =============================================================================


def get_langchain_tools() -> list[Any]:
    """Get all GitHub tools as LangChain StructuredTools."""
    from vendor_fabric.ai_tools import build_langchain_tools

    return build_langchain_tools(TOOL_DEFINITIONS)


def get_crewai_tools() -> list[Any]:
    """Get all GitHub tools as CrewAI tools."""
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
    """Get all GitHub tools as plain Python functions for AWS Strands."""
    return [defn["func"] for defn in TOOL_DEFINITIONS]


def get_tools(framework: str = "auto") -> list[Any]:
    """Get GitHub tools for the specified or auto-detected framework."""
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
    "TOOL_DEFINITIONS",
    "get_crewai_tools",
    "get_langchain_tools",
    "get_repository",
    "get_repository_file",
    "get_strands_tools",
    "get_team",
    "get_tools",
    "list_org_members",
    "list_repositories",
    "list_teams",
]
