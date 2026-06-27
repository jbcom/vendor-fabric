# ruff: noqa: I001
"""Tests for GitHub connector exports and behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("github")

from vendor_fabric import GitHubConnector as RootGitHubConnector
from vendor_fabric.github import GitHubConnector
from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString


class TestGitHubConnector:
    """Test suite for GitHub connector behavior."""

    def test_root_export_points_to_same_connector(self):
        """The canonical root export and canonical class should resolve to the same class."""
        assert RootGitHubConnector is GitHubConnector

    @patch("vendor_fabric.github.Github")
    def test_init_with_repo(self, mock_github_class, base_connector_kwargs):
        """Test initialization with repository."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"

        mock_github.get_organization.return_value = mock_org
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(
            github_owner="test-org", github_repo="test-repo", github_token="test-token", **base_connector_kwargs
        )

        assert connector.GITHUB_OWNER == "test-org"
        assert connector.GITHUB_REPO == "test-repo"
        assert connector.repo is not None
        assert connector.GITHUB_BRANCH == "main"

    @patch("vendor_fabric.github.Github")
    def test_init_without_repo(self, mock_github_class, base_connector_kwargs):
        """Test initialization without repository."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(github_owner="test-org", github_token="test-token", **base_connector_kwargs)

        assert connector.repo is None

    @patch("vendor_fabric.github.Github")
    def test_get_repository_branch(self, mock_github_class, base_connector_kwargs):
        """Test getting repository branch."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_repo = MagicMock()
        mock_branch = MagicMock()

        mock_repo.get_branch.return_value = mock_branch
        mock_repo.default_branch = "main"
        mock_github.get_organization.return_value = mock_org
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(
            github_owner="test-org", github_repo="test-repo", github_token="test-token", **base_connector_kwargs
        )

        branch = connector.get_repository_branch("feature-branch")
        assert branch == mock_branch

    @patch("vendor_fabric.github.Github")
    def test_get_repository_file(self, mock_github_class, base_connector_kwargs):
        """Test getting repository file."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_repo = MagicMock()
        mock_file = MagicMock()
        mock_file.decoded_content = b'{"test": "data"}'
        mock_file.sha = "abc123"
        mock_file.content = "test content"

        mock_repo.get_contents.return_value = mock_file
        mock_repo.default_branch = "main"
        mock_github.get_organization.return_value = mock_org
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(
            github_owner="test-org", github_repo="test-repo", github_token="test-token", **base_connector_kwargs
        )

        content = connector.get_repository_file("test.json")
        assert isinstance(content, ExtendedDict)
        assert isinstance(content["test"], ExtendedString)
        assert content["test"].upper_first() == "Data"

    @patch("vendor_fabric.github.Github")
    def test_get_repository_file_with_metadata_returns_extended_tuple(self, mock_github_class, base_connector_kwargs):
        """Repository file metadata tuples preserve shape while promoting decoded content."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_repo = MagicMock()
        mock_file = MagicMock()
        mock_file.decoded_content = b'{"test": "data"}'
        mock_file.sha = "abc123"
        mock_file.content = "test content"

        mock_repo.get_contents.return_value = mock_file
        mock_repo.default_branch = "main"
        mock_github.get_organization.return_value = mock_org
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(
            github_owner="test-org", github_repo="test-repo", github_token="test-token", **base_connector_kwargs
        )

        content, sha, path = connector.get_repository_file("test.json", return_sha=True, return_path=True)

        assert isinstance(content, ExtendedDict)
        assert isinstance(content["test"], ExtendedString)
        assert sha == "abc123"
        assert path == "test.json"

    @patch("vendor_fabric.github.Github")
    def test_list_repositories_promotes_vendor_payloads(self, mock_github_class, base_connector_kwargs):
        """Vendor SDK list payloads should return extended containers."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_repo = MagicMock()
        mock_repo.id = 1
        mock_repo.name = "api-service"
        mock_repo.full_name = "test-org/api-service"
        mock_repo.description = "API service"
        mock_repo.private = False
        mock_repo.archived = False
        mock_repo.default_branch = "main"
        mock_repo.html_url = "https://github.com/test-org/api-service"
        mock_repo.clone_url = "https://github.com/test-org/api-service.git"
        mock_repo.ssh_url = "git@github.com:test-org/api-service.git"
        mock_repo.language = "Python"
        mock_repo.topics = ["data", "vendor"]
        mock_repo.created_at = None
        mock_repo.updated_at = None
        mock_repo.pushed_at = None

        mock_org.get_repos.return_value = [mock_repo]
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(github_owner="test-org", github_token="test-token", **base_connector_kwargs)

        repos = connector.list_repositories()

        assert isinstance(repos, ExtendedDict)
        assert isinstance(repos["api-service"], ExtendedDict)
        assert isinstance(repos["api-service"]["name"], ExtendedString)
        assert isinstance(repos["api-service"]["topics"], ExtendedList)
        assert repos["api-service"]["name"].to_snake_case() == "api_service"

    @patch("vendor_fabric.github.Github")
    def test_build_workflow_helpers_return_extended_data(self, mock_github_class, base_connector_kwargs):
        """GitHub workflow builders should also produce first-class extended data."""
        mock_github = MagicMock()
        mock_org = MagicMock()
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github

        connector = GitHubConnector(github_owner="test-org", github_token="test-token", **base_connector_kwargs)

        step = connector.build_workflow_step(name="Run tests", run="pytest")
        job = connector.build_workflow_job(steps=[step])
        workflow = connector.build_workflow(name="CI", on={"pull_request": {}}, jobs={"test": job})

        assert isinstance(step, ExtendedDict)
        assert isinstance(job, ExtendedDict)
        assert isinstance(workflow, ExtendedDict)
        assert isinstance(workflow["jobs"]["test"]["steps"], ExtendedList)
        assert workflow["jobs"]["test"]["steps"][0]["run"].upper_first() == "Pytest"
