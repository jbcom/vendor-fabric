"""Tests for GitHub AI tools."""

from __future__ import annotations

import importlib.util

from unittest.mock import MagicMock, patch

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString


# Patch target for GitHubConnector - patch at source since tools.py imports lazily inside functions
GITHUB_CONNECTOR_PATCH = "cloud_connectors.github.GitHubConnector"


def test_github_connector_requires_pygithub_when_constructed_without_extra() -> None:
    """GitHub tool metadata imports without github, but the connector still requires the extra."""
    if importlib.util.find_spec("github") is not None:
        pytest.skip("github is installed")

    from cloud_connectors.github import GitHubConnector

    with pytest.raises(ImportError, match=r"cloud-connectors\[github\]"):
        GitHubConnector(github_owner="jbcom", github_token="token", from_environment=False)


class TestGitHubToolDefinitions:
    """Test tool definitions and metadata."""

    def test_tool_definitions_exist(self):
        """Test that TOOL_DEFINITIONS is populated."""
        from cloud_connectors.github.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_required_fields(self):
        """Test that all tools have name, description, and func."""
        from cloud_connectors.github.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert "name" in defn, f"Tool missing 'name': {defn}"
            assert "description" in defn, f"Tool missing 'description': {defn}"
            assert "func" in defn, f"Tool missing 'func': {defn}"
            assert callable(defn["func"]), f"Tool func not callable: {defn['name']}"

    def test_tool_names_prefixed(self):
        """Test that all tool names are prefixed with 'github_'."""
        from cloud_connectors.github.tools import TOOL_DEFINITIONS

        for defn in TOOL_DEFINITIONS:
            assert defn["name"].startswith("github_"), f"Tool name not prefixed: {defn['name']}"


class TestListRepositories:
    """Tests for list_repositories tool."""

    @patch(GITHUB_CONNECTOR_PATCH)
    def test_list_repositories_basic(self, mock_connector_class):
        """Test basic list_repositories functionality."""
        from cloud_connectors.github.tools import list_repositories

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
        from cloud_connectors.github.tools import list_repositories

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
        from cloud_connectors.github.tools import get_repository

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
        from cloud_connectors.github.tools import get_repository

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
        from cloud_connectors.github.tools import list_teams

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
        from cloud_connectors.github.tools import list_teams

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
        from cloud_connectors.github.tools import get_team

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
        from cloud_connectors.github.tools import get_team

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
        from cloud_connectors.github.tools import list_org_members

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
        from cloud_connectors.github.tools import list_org_members

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
        from cloud_connectors.github.tools import get_repository_file

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
        from cloud_connectors.github.tools import get_repository_file

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
        from cloud_connectors.github.tools import get_repository_file

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
        from cloud_connectors.github.tools import get_repository_file

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


class TestGetTools:
    """Test framework getters."""

    def test_get_strands_tools(self):
        """Test get_strands_tools returns callable functions."""
        from cloud_connectors.github.tools import get_strands_tools

        tools = get_strands_tools()

        assert len(tools) > 0
        assert all(callable(t) for t in tools)

    def test_get_tools_invalid_framework(self):
        """Test get_tools with invalid framework raises ValueError."""
        from cloud_connectors.github.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools(framework="invalid")

    def test_get_tools_rejects_functions_alias(self):
        """Plain-function tools should use the canonical strands framework name."""
        from cloud_connectors.github.tools import get_tools

        with pytest.raises(ValueError, match="Unknown framework"):
            get_tools(framework="functions")

    def test_get_langchain_tools_delegates_shared_builder(self, monkeypatch: pytest.MonkeyPatch):
        """LangChain tool factory should pass the GitHub definitions to the shared builder."""
        from cloud_connectors import ai_tools
        from cloud_connectors.github import tools as github_tools

        expected = [object()]
        build_langchain_tools = MagicMock(return_value=expected)
        monkeypatch.setattr(ai_tools, "build_langchain_tools", build_langchain_tools)

        assert github_tools.get_langchain_tools() is expected
        build_langchain_tools.assert_called_once_with(github_tools.TOOL_DEFINITIONS)

    def test_get_crewai_tools_wraps_definitions(self, monkeypatch: pytest.MonkeyPatch):
        """CrewAI tool factory should attach descriptions and schemas to wrapped functions."""
        from cloud_connectors import _optional
        from cloud_connectors.github import tools as github_tools

        def fake_tool(name):
            def decorate(func):
                wrapped = MagicMock(wrapped_name=name)
                wrapped.__name__ = func.__name__
                return wrapped

            return decorate

        monkeypatch.setattr(_optional, "get_crewai_tool_decorator", lambda: fake_tool)

        tools = github_tools.get_crewai_tools()

        assert len(tools) == len(github_tools.TOOL_DEFINITIONS)
        assert tools[0].description == github_tools.TOOL_DEFINITIONS[0]["description"]
        assert tools[0].args_schema is github_tools.TOOL_DEFINITIONS[0]["schema"]

    def test_get_crewai_tools_allows_schema_less_definitions(self, monkeypatch: pytest.MonkeyPatch):
        """CrewAI tool factory should tolerate definitions without schema metadata."""
        from cloud_connectors import _optional
        from cloud_connectors.github import tools as github_tools

        class WrappedTool:
            pass

        def fake_tool(name):
            def decorate(func):
                wrapped = WrappedTool()
                wrapped.name = name
                wrapped.func = func
                return wrapped

            return decorate

        monkeypatch.setattr(_optional, "get_crewai_tool_decorator", lambda: fake_tool)
        monkeypatch.setattr(
            github_tools,
            "TOOL_DEFINITIONS",
            [{"name": "github_ping", "description": "Ping GitHub", "func": lambda: "pong"}],
        )

        tools = github_tools.get_crewai_tools()

        assert len(tools) == 1
        assert tools[0].description == "Ping GitHub"
        assert not hasattr(tools[0], "args_schema")

    def test_get_tools_auto_prefers_crewai_when_available(self, monkeypatch: pytest.MonkeyPatch):
        """Auto-detection should prefer CrewAI tools when CrewAI is importable."""
        from cloud_connectors import _optional
        from cloud_connectors.github import tools as github_tools

        expected = [object()]
        monkeypatch.setattr(_optional, "is_available", lambda package: package == "crewai")
        monkeypatch.setattr(github_tools, "get_crewai_tools", lambda: expected)

        assert github_tools.get_tools("auto") is expected

    def test_get_tools_auto_falls_back_to_langchain_then_strands(self, monkeypatch: pytest.MonkeyPatch):
        """Auto-detection should use LangChain before plain Strands functions."""
        from cloud_connectors import _optional
        from cloud_connectors.github import tools as github_tools

        langchain_tools = [object()]
        strands_tools = [object()]
        availability = {"langchain_core": True}
        monkeypatch.setattr(_optional, "is_available", lambda package: availability.get(package, False))
        monkeypatch.setattr(github_tools, "get_langchain_tools", lambda: langchain_tools)
        monkeypatch.setattr(github_tools, "get_strands_tools", lambda: strands_tools)

        assert github_tools.get_tools("auto") is langchain_tools

        availability["langchain_core"] = False
        assert github_tools.get_tools("auto") is strands_tools

    def test_get_tools_explicit_frameworks(self, monkeypatch: pytest.MonkeyPatch):
        """Explicit framework names should dispatch to their matching factories."""
        from cloud_connectors.github import tools as github_tools

        langchain_tools = [object()]
        crewai_tools = [object()]
        strands_tools = [object()]
        monkeypatch.setattr(github_tools, "get_langchain_tools", lambda: langchain_tools)
        monkeypatch.setattr(github_tools, "get_crewai_tools", lambda: crewai_tools)
        monkeypatch.setattr(github_tools, "get_strands_tools", lambda: strands_tools)

        assert github_tools.get_tools("langchain") is langchain_tools
        assert github_tools.get_tools("crewai") is crewai_tools
        assert github_tools.get_tools("strands") is strands_tools


class TestExports:
    """Test that all expected exports are available."""

    def test_all_exports_available(self):
        """Test that __all__ contains expected exports."""
        from cloud_connectors.github import tools

        expected_exports = [
            "get_tools",
            "get_langchain_tools",
            "get_crewai_tools",
            "get_strands_tools",
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
