"""Tests for GitHub AI tools."""

from __future__ import annotations

import importlib.util

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString


# Patch target for GitHubConnector - patch at source since tools.py imports lazily inside functions
GITHUB_CONNECTOR_PATCH = "vendor_fabric.github.GitHubConnector"


def test_github_connector_requires_pygithub_when_constructed_without_extra() -> None:
    """GitHub tool metadata imports without github, but the connector still requires the extra."""
    if importlib.util.find_spec("github") is not None:
        pytest.skip("github is installed")

    from vendor_fabric.github import GitHubConnector

    with pytest.raises(ImportError, match=r"vendor-fabric\[github\]"):
        GitHubConnector(github_owner="jbcom", github_token="token", from_environment=False)


class TestGitHubToolDefinitions:
    """Test tool definitions and metadata."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS is populated."""
        from vendor_fabric.github.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all tools have name, description, and func."""
        from vendor_fabric.github.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Tool missing 'name': {defn}"
            assert "description" in defn, f"Tool missing 'description': {defn}"
            assert "func" in defn, f"Tool missing 'func': {defn}"
            assert callable(defn["func"]), f"Tool func not callable: {defn['name']}"

    def test_tool_names_prefixed(self):
        """Test that all tool names are prefixed with 'github_'."""
        from vendor_fabric.github.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("github_"), f"Tool name not prefixed: {defn['name']}"


class TestListRepositories:
    """Tests for list_repositories tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_repositories_basic(self, mock_connector_class):
        """Test basic list_repositories functionality."""
        from vendor_fabric.github.tools import list_repositories

        mock_connector = MagicMock()
        mock_connector.list_repositories.return_value = {
            "repo1": {
                "full_name": "org/repo1",
                "description": "Test repository",
                "private": False,
                "archived": False,
                "default_branch": "main",
                "html_url": "https://github.com/org/repo1",
                "language": "Python",
                "topics": ["testing"],
            },
            "repo2": {
                "full_name": "org/repo2",
                "description": "Another test",
                "private": True,
                "archived": False,
                "default_branch": "main",
                "html_url": "https://github.com/org/repo2",
                "language": "JavaScript",
                "topics": [],
            },
        }
        mock_connector_class.return_value = mock_connector

        result = list_repositories(github_owner="test-org", github_token="test-token")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["name"] == "repo1"
        assert result[0]["description"] == "Test repository"
        assert isinstance(result[0]["description"], ExtendedString)
        assert result[1]["name"] == "repo2"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_repositories_with_filter(self, mock_connector_class):
        """Test list_repositories with type filter."""
        from vendor_fabric.github.tools import list_repositories

        mock_connector = MagicMock()
        mock_connector.list_repositories.return_value = {}
        mock_connector_class.return_value = mock_connector

        list_repositories(github_owner="test-org", github_token="test-token", type_filter="public")

        mock_connector.list_repositories.assert_called_once_with(type_filter="public", include_branches=False)


class TestGetRepository:
    """Tests for get_repository tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_repository_basic(self, mock_connector_class):
        """Test basic get_repository functionality."""
        from vendor_fabric.github.tools import get_repository

        mock_connector = MagicMock()
        mock_connector.get_repository.return_value = {
            "name": "test-repo",
            "full_name": "org/test-repo",
            "description": "Test repository",
            "private": False,
            "default_branch": "main",
        }
        mock_connector_class.return_value = mock_connector

        result = get_repository(github_owner="test-org", github_token="test-token", repo_name="test-repo")

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "found"
        assert result["name"] == "test-repo"
        assert result["full_name"] == "org/test-repo"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_repository_not_found(self, mock_connector_class):
        """Test get_repository when repository not found."""
        from vendor_fabric.github.tools import get_repository

        mock_connector = MagicMock()
        mock_connector.get_repository.return_value = None
        mock_connector_class.return_value = mock_connector

        result = get_repository(github_owner="test-org", github_token="test-token", repo_name="nonexistent")

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "not_found"
        assert result["name"] == "nonexistent"


class TestListTeams:
    """Tests for list_teams tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_teams_basic(self, mock_connector_class):
        """Test basic list_teams functionality."""
        from vendor_fabric.github.tools import list_teams

        mock_connector = MagicMock()
        mock_connector.list_teams.return_value = {
            "team1": {
                "name": "Team 1",
                "slug": "team1",
                "description": "First team",
                "privacy": "closed",
                "permission": "push",
                "html_url": "https://github.com/orgs/org/teams/team1",
                "members_count": 5,
                "repos_count": 10,
            },
            "team2": {
                "name": "Team 2",
                "slug": "team2",
                "description": "Second team",
                "privacy": "secret",
                "permission": "pull",
                "html_url": "https://github.com/orgs/org/teams/team2",
                "members_count": 3,
                "repos_count": 5,
            },
        }
        mock_connector_class.return_value = mock_connector

        result = list_teams(github_owner="test-org", github_token="test-token")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["slug"] == "team1"
        assert result[0]["name"] == "Team 1"
        assert result[0]["members_count"] == 5

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_teams_with_members(self, mock_connector_class):
        """Test list_teams with include_members option."""
        from vendor_fabric.github.tools import list_teams

        mock_connector = MagicMock()
        mock_connector.list_teams.return_value = {}
        mock_connector_class.return_value = mock_connector

        list_teams(github_owner="test-org", github_token="test-token", include_members=True)

        mock_connector.list_teams.assert_called_once_with(include_members=True, include_repos=False)


class TestGetTeam:
    """Tests for get_team tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_team_basic(self, mock_connector_class):
        """Test basic get_team functionality."""
        from vendor_fabric.github.tools import get_team

        mock_connector = MagicMock()
        mock_connector.get_team.return_value = {
            "name": "Test Team",
            "slug": "test-team",
            "description": "A test team",
            "privacy": "closed",
            "members_count": 5,
        }
        mock_connector_class.return_value = mock_connector

        result = get_team(github_owner="test-org", github_token="test-token", team_slug="test-team")

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "found"
        assert result["slug"] == "test-team"
        assert result["name"] == "Test Team"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_team_not_found(self, mock_connector_class):
        """Test get_team when team not found."""
        from vendor_fabric.github.tools import get_team

        mock_connector = MagicMock()
        mock_connector.get_team.return_value = None
        mock_connector_class.return_value = mock_connector

        result = get_team(github_owner="test-org", github_token="test-token", team_slug="nonexistent")

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "not_found"
        assert result["slug"] == "nonexistent"


class TestListOrgMembers:
    """Tests for list_org_members tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_org_members_basic(self, mock_connector_class):
        """Test basic list_org_members functionality."""
        from vendor_fabric.github.tools import list_org_members

        mock_connector = MagicMock()
        mock_connector.list_org_members.return_value = {
            "user1": {
                "login": "user1",
                "name": "User One",
                "email": "user1@example.com",
                "role": "member",
                "state": "active",
                "avatar_url": "https://github.com/user1.png",
                "html_url": "https://github.com/user1",
            },
            "user2": {
                "login": "user2",
                "name": "User Two",
                "email": "user2@example.com",
                "role": "admin",
                "state": "active",
                "avatar_url": "https://github.com/user2.png",
                "html_url": "https://github.com/user2",
            },
        }
        mock_connector_class.return_value = mock_connector

        result = list_org_members(github_owner="test-org", github_token="test-token")

        assert isinstance(result, ExtendedList)
        assert isinstance(result[0], ExtendedDict)
        assert len(result) == 2
        assert result[0]["login"] == "user1"
        assert result[0]["role"] == "member"
        assert result[1]["login"] == "user2"
        assert result[1]["role"] == "admin"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_org_members_with_role_filter(self, mock_connector_class):
        """Test list_org_members with role filter."""
        from vendor_fabric.github.tools import list_org_members

        mock_connector = MagicMock()
        mock_connector.list_org_members.return_value = {}
        mock_connector_class.return_value = mock_connector

        list_org_members(github_owner="test-org", github_token="test-token", role="admin")

        mock_connector.list_org_members.assert_called_once_with(role="admin", include_pending=False)


class TestGetRepositoryFile:
    """Tests for get_repository_file tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_repository_file_basic(self, mock_connector_class):
        """Test basic get_repository_file functionality."""
        from vendor_fabric.github.tools import get_repository_file

        mock_connector = MagicMock()
        mock_connector.get_repository_file.return_value = ('{"test": "content"}', "abc123", "test.json")
        mock_connector_class.return_value = mock_connector

        result = get_repository_file(
            github_owner="test-org",
            github_token="test-token",
            github_repo="test-repo",
            file_path="test.json",
        )

        assert isinstance(result, ExtendedDict)
        assert result["path"] == "test.json"
        assert result["content"] == '{"test": "content"}'
        assert result["sha"] == "abc123"
        assert result["status"] == "retrieved"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_repository_file_with_branch(self, mock_connector_class):
        """Test get_repository_file with custom branch."""
        from vendor_fabric.github.tools import get_repository_file

        mock_connector = MagicMock()
        mock_connector.get_repository_file.return_value = ("content", "sha", "file.txt")
        mock_connector_class.return_value = mock_connector

        get_repository_file(
            github_owner="test-org",
            github_token="test-token",
            github_repo="test-repo",
            file_path="file.txt",
            github_branch="feature",
        )

        # Verify connector was initialized with correct branch
        mock_connector_class.assert_called_once()
        call_kwargs = mock_connector_class.call_args[1]
        assert call_kwargs["github_branch"] == "feature"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_repository_file_empty(self, mock_connector_class):
        """Test get_repository_file when file is empty."""
        from vendor_fabric.github.tools import get_repository_file

        mock_connector = MagicMock()
        mock_connector.get_repository_file.return_value = (None, "sha", "empty.txt")
        mock_connector_class.return_value = mock_connector

        result = get_repository_file(
            github_owner="test-org",
            github_token="test-token",
            github_repo="test-repo",
            file_path="empty.txt",
        )

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "empty"

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_get_repository_file_single_payload(self, mock_connector_class):
        """Test get_repository_file when the connector returns content without SHA metadata."""
        from vendor_fabric.github.tools import get_repository_file

        mock_connector = MagicMock()
        mock_connector.get_repository_file.return_value = "plain content"
        mock_connector_class.return_value = mock_connector

        result = get_repository_file(
            github_owner="test-org",
            github_token="test-token",
            github_repo="test-repo",
            file_path="README.md",
        )

        assert isinstance(result, ExtendedDict)
        assert result["status"] == "retrieved"
        assert result["content"] == "plain content"
        assert result["sha"] is None


class TestExports:
    """Test that all expected exports are available."""

    def test_all_exports_available(self):
        """Test that __all__ contains expected exports."""
        from vendor_fabric.github import tools

        expected_exports = [
            "list_repositories",
            "get_repository",
            "list_teams",
            "get_team",
            "list_org_members",
            "get_repository_file",
            "TOOL_DEFINITIONS",
        ]

        for export in expected_exports:
            assert hasattr(tools, export), f"Missing export: {export}"
            assert export in tools.__all__, f"Export not in __all__: {export}"
