"""Dependency-free GitHub connector payload contract tests."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import call as mock_call

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, ExtendedTuple

import vendor_fabric.github as github_module

from vendor_fabric.github import GitHubConnector, GitHubFallbackError, build_github_actions_workflow


def _connector() -> GitHubConnector:
    """Build a GitHubConnector shell without importing optional SDK dependencies."""
    connector = GitHubConnector.__new__(GitHubConnector)
    connector.GITHUB_OWNER = "test-org"
    connector.GITHUB_TOKEN = "test-token"
    connector.GITHUB_BRANCH = "main"
    connector.logger = MagicMock()
    connector.repo = MagicMock()
    connector.org = MagicMock()
    connector.git = MagicMock()
    connector.graphql_client = MagicMock()
    return connector


def _logged_text(logger: MagicMock) -> str:
    """Collect structured mock log calls into one searchable diagnostic string."""
    messages: list[str] = []
    for method_name in ("debug", "info", "warning", "error", "exception"):
        method = getattr(logger, method_name)
        for log_call in method.call_args_list:
            messages.extend(str(arg) for arg in log_call.args)
            messages.extend(str(value) for value in log_call.kwargs.values())
    return "\n".join(messages)


def _member(login: str, *, member_id: int = 1) -> MagicMock:
    member = MagicMock()
    member.id = member_id
    member.login = login
    member.name = login.title()
    member.email = f"{login}@example.com"
    member.avatar_url = f"https://github.com/{login}.png"
    member.html_url = f"https://github.com/{login}"
    return member


def _repo(name: str) -> MagicMock:
    repo = MagicMock()
    repo.id = 1
    repo.name = name
    repo.full_name = f"test-org/{name}"
    repo.description = f"{name} repository"
    repo.private = False
    repo.archived = False
    repo.default_branch = "main"
    repo.html_url = f"https://github.com/test-org/{name}"
    repo.clone_url = f"https://github.com/test-org/{name}.git"
    repo.ssh_url = f"git@github.com:test-org/{name}.git"
    repo.language = "Python"
    repo.topics = ["data", "connector"]
    repo.created_at = None
    repo.updated_at = None
    repo.pushed_at = None
    return repo


def _team(slug: str) -> MagicMock:
    team = MagicMock()
    team.id = 1
    team.name = slug.replace("-", " ").title()
    team.slug = slug
    team.description = f"{slug} team"
    team.privacy = "closed"
    team.permission = "push"
    team.html_url = f"https://github.com/orgs/test-org/teams/{slug}"
    team.members_count = 1
    team.repos_count = 1
    return team


def test_repository_file_decodes_into_extended_payload_with_metadata() -> None:
    """Decoded repository files should enter the Tier 2 fabric immediately."""
    connector = _connector()
    mock_file = MagicMock()
    mock_file.decoded_content = b'{"service":{"name":"api"}}'
    mock_file.sha = "abc123"
    mock_file.content = "test content"
    connector.repo.get_contents.return_value = mock_file

    result = connector.get_repository_file("service.json", return_sha=True, return_path=True)

    assert isinstance(result, ExtendedTuple)
    assert isinstance(result[0], ExtendedDict)
    assert isinstance(result[0]["service"]["name"], ExtendedString)
    assert result[0]["service"]["name"].upper_first() == "Api"
    assert result[1:] == ("abc123", "service.json")


def test_get_repository_file_returns_raw_text_when_decode_disabled() -> None:
    """Raw repository reads should preserve text content and optional metadata."""
    connector = _connector()
    mock_file = MagicMock()
    mock_file.decoded_content = b"raw text"
    mock_file.sha = "abc123"
    mock_file.content = "raw text"
    connector.repo.get_contents.return_value = mock_file

    result = connector.get_repository_file("README.md", decode=False, return_sha=True)

    assert isinstance(result, ExtendedTuple)
    assert result == ("raw text", "abc123")
    connector.repo.get_contents.assert_called_once_with("README.md", ref="main")


def test_get_repository_file_missing_can_raise_redacted_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing repository files should raise on demand without leaking caller paths."""
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)
    connector = _connector()
    connector.repo.get_contents.side_effect = GitHubFallbackError("missing private/path.json")

    with pytest.raises(FileNotFoundError) as exc_info:
        connector.get_repository_file("private/path.json", raise_on_not_found=True)

    message = str(exc_info.value)
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in message
    assert "[REDACTED]" in logs
    assert "private/path.json" not in message
    assert "private/path.json" not in logs


def test_get_repository_file_without_repo_returns_none_and_redacts_log() -> None:
    """Repository file reads should no-op when no repository is configured."""
    connector = _connector()
    connector.repo = None

    assert connector.get_repository_file("private/path.json") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private/path.json" not in logs


def test_get_repository_file_empty_content_returns_default_payload() -> None:
    """Empty repository files should return the default decoded payload shape."""
    connector = _connector()
    mock_file = MagicMock()
    mock_file.content = ""
    mock_file.decoded_content = b""
    mock_file.sha = "empty-sha"
    connector.repo.get_contents.return_value = mock_file

    result = connector.get_repository_file("empty.json", return_sha=True)

    assert isinstance(result, ExtendedTuple)
    assert result == ({}, "empty-sha")


def test_get_repository_file_decode_failure_returns_raw_text_with_redacted_log() -> None:
    """Decode failures should return raw text and avoid leaking repository paths."""
    connector = _connector()
    mock_file = MagicMock()
    mock_file.content = "not-json"
    mock_file.decoded_content = b"{not-json"
    mock_file.sha = "bad-json-sha"
    connector.repo.get_contents.return_value = mock_file

    result = connector.get_repository_file("private/config.json")

    assert isinstance(result, ExtendedString)
    assert result == "{not-json"
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private/config.json" not in logs


def test_get_repository_file_unsupported_read_returns_raw_default() -> None:
    """Unsupported SDK content reads should return decoded defaults instead of crashing."""
    connector = _connector()
    mock_file = MagicMock()
    mock_file.content = "content"
    mock_file.decoded_content.decode.side_effect = ValueError("unsupported private/path.bin")
    mock_file.sha = "binary-sha"
    connector.repo.get_contents.return_value = mock_file

    result = connector.get_repository_file("private/path.bin", return_sha=True)

    assert isinstance(result, ExtendedTuple)
    assert result == ({}, "binary-sha")
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private/path.bin" not in logs


def test_update_repository_file_creates_missing_file_with_encoded_payload() -> None:
    """Repository updates should create files when no current SHA can be found."""
    connector = _connector()
    connector.get_repository_file = MagicMock(return_value=ExtendedString(""))

    result = connector.update_repository_file(
        "config/service.json",
        {"service": {"name": "api"}},
        allow_encoding="json",
    )

    assert result is connector.repo.create_file.return_value
    connector.repo.create_file.assert_called_once()
    kwargs = connector.repo.create_file.call_args.kwargs
    assert kwargs["path"] == "config/service.json"
    assert kwargs["message"] == "Creating config/service.json"
    assert kwargs["branch"] == "main"
    assert '"service"' in kwargs["content"]
    connector.repo.update_file.assert_not_called()


def test_update_repository_file_rejects_empty_payloads_unless_allowed() -> None:
    """Repository updates should not silently write empty payloads by default."""
    connector = _connector()

    result = connector.update_repository_file("empty.txt", "")

    assert result is None
    connector.repo.create_file.assert_not_called()
    connector.repo.update_file.assert_not_called()
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "empty.txt" not in logs


def test_update_repository_file_allows_empty_payloads_when_requested() -> None:
    """Explicit empty writes should be allowed when allow_empty is true."""
    connector = _connector()

    result = connector.update_repository_file(
        "empty.txt", "", file_sha="abc123", allow_empty=True, allow_encoding=False
    )

    assert result is connector.repo.update_file.return_value
    connector.repo.update_file.assert_called_once_with(
        path="empty.txt",
        message="Updating empty.txt",
        content="",
        sha="abc123",
        branch="main",
    )


def test_update_repository_file_without_repo_returns_none_and_redacts_log() -> None:
    """Repository file updates should no-op when no repository is configured."""
    connector = _connector()
    connector.repo = None

    assert connector.update_repository_file("private/path.json", {"x": 1}) is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private/path.json" not in logs


def test_delete_repository_file_deletes_when_sha_exists() -> None:
    """Repository deletes should fetch the current SHA and call delete_file."""
    connector = _connector()
    connector.get_repository_file = MagicMock(return_value=ExtendedTuple(("", "abc123")))

    result = connector.delete_repository_file("config/service.json")

    assert result is connector.repo.delete_file.return_value
    connector.get_repository_file.assert_called_once_with(file_path="config/service.json", return_sha=True)
    connector.repo.delete_file.assert_called_once_with(
        path="config/service.json",
        message="Deleting config/service.json",
        branch="main",
        sha="abc123",
    )


def test_delete_repository_file_skips_when_sha_missing() -> None:
    """Repository deletes should be no-ops when the current file cannot be resolved."""
    connector = _connector()
    connector.get_repository_file = MagicMock(return_value=None)

    assert connector.delete_repository_file("missing.txt") is None

    connector.repo.delete_file.assert_not_called()


def test_delete_repository_file_without_repo_returns_none_and_redacts_log() -> None:
    """Repository file deletes should no-op when no repository is configured."""
    connector = _connector()
    connector.repo = None

    assert connector.delete_repository_file("private/path.json") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private/path.json" not in logs


def test_list_repositories_promotes_sdk_payloads() -> None:
    """Repository listing payloads should be extended containers, not raw dicts."""
    connector = _connector()
    repo = MagicMock()
    repo.id = 1
    repo.name = "api-service"
    repo.full_name = "test-org/api-service"
    repo.description = "API service"
    repo.private = False
    repo.archived = False
    repo.default_branch = "main"
    repo.html_url = "https://github.com/test-org/api-service"
    repo.clone_url = "https://github.com/test-org/api-service.git"
    repo.ssh_url = "git@github.com:test-org/api-service.git"
    repo.language = "Python"
    repo.topics = ["data", "vendor"]
    repo.created_at = None
    repo.updated_at = None
    repo.pushed_at = None
    connector.org.get_repos.return_value = [repo]

    result = connector.list_repositories()

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["api-service"], ExtendedDict)
    assert isinstance(result["api-service"]["topics"], ExtendedList)
    assert result["api-service"]["name"].to_snake_case() == "api_service"


def test_create_repository_branch_uses_parent_sha() -> None:
    """Branch creation should create Git refs from the selected parent branch SHA."""
    connector = _connector()
    connector.repo.default_branch = "main"
    parent = MagicMock()
    parent.commit.sha = "parent-sha"
    connector.get_repository_branch = MagicMock(return_value=parent)

    result = connector.create_repository_branch("feature/data")

    assert result is connector.repo.create_git_ref.return_value
    connector.get_repository_branch.assert_called_once_with("main")
    connector.repo.create_git_ref.assert_called_once_with(ref="refs/heads/feature/data", sha="parent-sha")


def test_get_repository_branch_without_repo_returns_none_and_redacts_log() -> None:
    """Branch lookup should no-op when no repository is configured."""
    connector = _connector()
    connector.repo = None

    assert connector.get_repository_branch("private-branch") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-branch" not in logs


def test_get_repository_branch_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing branch lookup should return None and redact branch names."""
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)
    connector = _connector()
    connector.repo.get_branch.side_effect = GitHubFallbackError("missing private-branch")

    assert connector.get_repository_branch("private-branch") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-branch" not in logs


def test_create_repository_branch_without_repo_returns_none_and_redacts_log() -> None:
    """Branch creation should no-op when no repository is configured."""
    connector = _connector()
    connector.repo = None

    assert connector.create_repository_branch("private-branch") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-branch" not in logs


def test_create_repository_branch_returns_existing_branch_on_reference_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing branch creation should return the current branch instead of failing."""

    class ReferenceExistsError(GitHubFallbackError):
        data = {"message": "Reference already exists"}

    monkeypatch.setattr(github_module, "GithubException", GitHubFallbackError)
    connector = _connector()
    parent = MagicMock()
    parent.commit.sha = "parent-sha"
    existing = MagicMock()
    connector.repo.default_branch = "main"
    connector.repo.create_git_ref.side_effect = ReferenceExistsError("Reference already exists")
    connector.get_repository_branch = MagicMock(side_effect=[parent, existing])

    assert connector.create_repository_branch("feature/data") is existing

    assert connector.get_repository_branch.call_args_list == [mock_call("main"), mock_call("feature/data")]


def test_create_repository_branch_redacts_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected branch creation errors should redact branch identifiers."""
    monkeypatch.setattr(github_module, "GithubException", GitHubFallbackError)
    connector = _connector()
    parent = MagicMock()
    parent.commit.sha = "parent-sha"
    connector.get_repository_branch = MagicMock(return_value=parent)
    connector.repo.create_git_ref.side_effect = GitHubFallbackError("branch private-branch token=raw-token")

    with pytest.raises(RuntimeError) as exc_info:
        connector.create_repository_branch("private-branch")

    message = str(exc_info.value)
    assert "[REDACTED]" in message
    assert "private-branch" not in message
    assert "raw-token" not in message


def test_create_repository_branch_raises_when_parent_missing() -> None:
    """Branch creation should fail loudly when the parent branch is missing."""
    connector = _connector()
    connector.get_repository_branch = MagicMock(return_value=None)

    with pytest.raises(RuntimeError, match="parent branch"):
        connector.create_repository_branch("feature/data", parent_branch="missing")


def test_list_org_members_includes_pending_invitations() -> None:
    """Organization member lists should include active and pending members when requested."""
    connector = _connector()
    active = _member("octocat", member_id=1)
    membership = MagicMock()
    membership.role = "admin"
    membership.state = "active"
    invite = MagicMock()
    invite.id = 2
    invite.login = None
    invite.email = "pending@example.com"
    invite.role = "direct_member"
    invite.created_at = None
    connector.org.get_members.return_value = [active]
    connector.org.get_user_membership.return_value = membership
    connector.org.invitations.return_value = [invite]

    result = connector.list_org_members(role="admin", include_pending=True)

    assert isinstance(result, ExtendedDict)
    assert result["octocat"]["role"] == "admin"
    assert result["pending@example.com"]["state"] == "pending"
    connector.org.get_members.assert_called_once_with(role="admin")


def test_get_org_member_returns_none_for_missing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing organization members should return None and redact diagnostics."""
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)
    connector = _connector()
    connector.git.get_user.side_effect = GitHubFallbackError("missing secret-user")

    assert connector.get_org_member("secret-user") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "secret-user" not in logs


def test_list_repositories_includes_branch_payloads() -> None:
    """Repository listings should optionally include promoted branch metadata."""
    connector = _connector()
    repo = _repo("api-service")
    branch = MagicMock()
    branch.name = "main"
    branch.protected = True
    branch.commit.sha = "branch-sha"
    repo.get_branches.return_value = [branch]
    connector.org.get_repos.return_value = [repo]

    result = connector.list_repositories(type_filter="private", include_branches=True)

    assert isinstance(result["api-service"]["branches"], ExtendedList)
    assert result["api-service"]["branches"][0]["name"] == "main"
    assert result["api-service"]["branches"][0]["protected"] is True
    assert result["api-service"]["branches"][0]["sha"] == "branch-sha"
    connector.org.get_repos.assert_called_once_with(type="private")


def test_get_repository_returns_none_for_missing_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing repositories should return None and redact repo names."""
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)
    connector = _connector()
    connector.git.get_repo.side_effect = GitHubFallbackError("missing private-repo")

    assert connector.get_repository("private-repo") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-repo" not in logs


def test_list_teams_includes_members_and_repositories() -> None:
    """Team lists should optionally include promoted member and repository details."""
    connector = _connector()
    team = _team("data-team")
    member = _member("octocat")
    repo = _repo("api-service")
    team.get_members.return_value = [member]
    team.get_repos.return_value = [repo]
    team.get_repo_permission.return_value = "admin"
    connector.org.get_teams.return_value = [team]

    result = connector.list_teams(include_members=True, include_repos=True)

    assert isinstance(result, ExtendedDict)
    assert result["data-team"]["members"][0]["login"] == "octocat"
    assert result["data-team"]["repositories"][0]["permission"] == "admin"
    assert isinstance(result["data-team"]["repositories"], ExtendedList)


def test_get_team_returns_promoted_payload() -> None:
    """Team lookup should promote SDK payloads into Tier 2 containers."""
    connector = _connector()
    connector.org.get_team_by_slug.return_value = _team("data-team")

    result = connector.get_team("data-team")

    assert isinstance(result, ExtendedDict)
    assert result["slug"] == "data-team"
    assert isinstance(result["name"], ExtendedString)


def test_get_team_returns_none_for_missing_team(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing team lookups should return None and redact team slugs."""
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)
    connector = _connector()
    connector.org.get_team_by_slug.side_effect = GitHubFallbackError("missing private-team")

    assert connector.get_team("private-team") is None

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-team" not in logs


def test_add_and_remove_team_member_success_paths() -> None:
    """Team membership helpers should call the SDK and return true on success."""
    connector = _connector()
    team = _team("data-team")
    user = _member("octocat")
    connector.org.get_team_by_slug.return_value = team
    connector.git.get_user.return_value = user

    assert connector.add_team_member("data-team", "octocat", role="maintainer") is True
    assert connector.remove_team_member("data-team", "octocat") is True

    team.add_membership.assert_called_once_with(user, role="maintainer")
    team.remove_membership.assert_called_once_with(user)


def test_remove_team_member_failure_redacts_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Team member removal failures should redact user/team identifiers."""
    monkeypatch.setattr(github_module, "GithubException", GitHubFallbackError)
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)
    connector = _connector()
    connector.git.get_user.side_effect = GitHubFallbackError("team private-team user secret-user token=raw-token")

    assert connector.remove_team_member("private-team", "secret-user") is False

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-team" not in logs
    assert "secret-user" not in logs
    assert "raw-token" not in logs


def test_execute_graphql_promotes_response_payload() -> None:
    """GraphQL response dictionaries should expose nested extended containers."""
    connector = _connector()
    connector.graphql_client.execute.return_value = {
        "data": {"user": {"login": "octocat", "organizationVerifiedDomainEmails": ["octo@example.com"]}}
    }

    result = connector.execute_graphql("query($login: String!) { user(login: $login) { login } }", {"login": "octocat"})

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["data"]["user"], ExtendedDict)
    assert isinstance(result["data"]["user"]["organizationVerifiedDomainEmails"], ExtendedList)
    assert result["data"]["user"]["login"].upper_first() == "Octocat"


def test_verified_email_enrichment_returns_extended_payload() -> None:
    """Derived GitHub user payloads should remain in the extended container layer."""
    connector = _connector()
    connector.graphql_client.execute.return_value = {
        "data": {
            "user": {
                "login": "octocat",
                "email": "octocat@example.com",
                "organizationVerifiedDomainEmails": ["octocat@example.com"],
            }
        }
    }

    result = connector.get_users_with_verified_emails(
        members={"octocat": {"login": "octocat", "role": "member"}},
        domain_filter="example.com",
    )

    assert isinstance(result, ExtendedDict)
    assert isinstance(result["octocat"], ExtendedDict)
    assert isinstance(result["octocat"]["verified_emails"], ExtendedList)
    assert result["octocat"]["primary_email"].upper_first() == "Octocat@example.com"


def test_verified_email_enrichment_filters_domain_matches() -> None:
    """Verified email enrichment should keep only members with matching domain emails."""
    connector = _connector()
    connector.execute_graphql = MagicMock(
        side_effect=[
            {
                "data": {
                    "user": {
                        "email": "octocat@example.com",
                        "organizationVerifiedDomainEmails": ["octocat@example.com", "octocat@other.test"],
                    }
                }
            },
            {
                "data": {
                    "user": {
                        "email": "nomatch@other.test",
                        "organizationVerifiedDomainEmails": ["nomatch@other.test"],
                    }
                }
            },
        ]
    )

    result = connector.get_users_with_verified_emails(
        members={
            "octocat": {"login": "octocat"},
            "nomatch": {"login": "nomatch"},
        },
        domain_filter="example.com",
    )

    assert set(result) == {"octocat"}
    assert result["octocat"]["domain_emails"] == ["octocat@example.com"]


def test_verified_email_enrichment_preserves_member_on_graphql_failure() -> None:
    """GraphQL failures should preserve existing member payloads and redact diagnostics."""
    connector = _connector()
    connector.execute_graphql = MagicMock(side_effect=RuntimeError("failed for secret-user token=raw-token"))

    result = connector.get_users_with_verified_emails(members={"secret-user": {"login": "secret-user"}})

    assert result["secret-user"]["login"] == "secret-user"
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "secret-user" not in logs
    assert "raw-token" not in logs


def test_workflow_builders_return_extended_data() -> None:
    """Local GitHub workflow builders should produce first-class extended data."""
    connector = _connector()

    step = connector.build_workflow_step(name="Run tests", run="pytest")
    job = connector.build_workflow_job(steps=[step])
    workflow = connector.build_workflow(name="CI", on={"pull_request": {}}, jobs={"test": job})

    assert isinstance(step, ExtendedDict)
    assert isinstance(job, ExtendedDict)
    assert isinstance(workflow, ExtendedDict)
    assert isinstance(workflow["jobs"]["test"]["steps"], ExtendedList)
    assert workflow["jobs"]["test"]["steps"][0]["run"].upper_first() == "Pytest"


def test_create_python_ci_workflow_builds_integrated_default_pipeline() -> None:
    """Python CI workflow helper should compose checkout, setup, lint, format, and test steps."""
    connector = _connector()

    workflow = connector.create_python_ci_workflow(python_versions=["3.12", "3.13"], working_directory="packages/api")

    assert isinstance(workflow, ExtendedDict)
    assert workflow["name"] == "CI"
    steps = workflow["jobs"]["test"]["steps"]
    assert [step["name"] for step in steps] == [
        "Checkout code",
        "Set up Python",
        "Install uv",
        "Install dependencies",
        "Lint",
        "Format check",
        "Run tests",
    ]
    assert workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"] == ["3.12", "3.13"]
    assert steps[-1]["working-directory"] == "packages/api"


def test_create_python_ci_workflow_can_skip_optional_checks() -> None:
    """Python CI workflow helper should omit lint/format steps when callers disable them."""
    connector = _connector()

    workflow = connector.create_python_ci_workflow(lint_command="", format_command=None)

    assert [step["name"] for step in workflow["jobs"]["test"]["steps"]] == [
        "Checkout code",
        "Set up Python",
        "Install uv",
        "Install dependencies",
        "Run tests",
    ]


def test_build_github_actions_workflow_rejects_missing_required_fields() -> None:
    """Standalone workflow YAML builder should fail loudly for unusable inputs."""
    with pytest.raises(ValueError, match="workflow_name is required"):
        build_github_actions_workflow("", {"test": {"runs-on": "ubuntu-latest", "steps": []}})

    with pytest.raises(ValueError, match="jobs definition is required"):
        build_github_actions_workflow("CI", {})


def test_build_github_actions_workflow_can_disable_oidc_and_events() -> None:
    """Standalone workflow builder should honor event and permission options."""
    workflow_yaml = build_github_actions_workflow(
        "Release",
        {"release": {"runs-on": "ubuntu-latest", "steps": [{"run": "echo release"}]}},
        use_oidc_auth=False,
        events={"push": False, "pull_request": False, "workflow_dispatch": True},
        triggers={"branches": ["main"]},
        pull_requests={"branches": ["main"]},
    )

    assert "id-token" not in workflow_yaml
    assert "workflow_dispatch:" in workflow_yaml
    assert "pull_request:" not in workflow_yaml


def test_update_repository_file_redacts_diagnostics_but_preserves_payload() -> None:
    """GitHub file updates should not leak caller paths or messages in logs."""
    connector = _connector()
    raw_path = "private/path.txt"
    raw_message = "commit mentions private/path.txt token=raw-token"

    connector.update_repository_file(
        raw_path,
        "raw file data",
        file_sha="abc123",
        msg=raw_message,
        allow_encoding=False,
    )

    connector.repo.update_file.assert_called_once_with(
        path=raw_path,
        message=raw_message,
        content="raw file data",
        sha="abc123",
        branch="main",
    )
    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert raw_path not in logs
    assert raw_message not in logs
    assert "raw-token" not in logs


def test_add_team_member_failure_redacts_diagnostics_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Team membership failures should redact user/team identifiers and avoid tracebacks."""
    monkeypatch.setattr(github_module, "GithubException", GitHubFallbackError)
    monkeypatch.setattr(github_module, "UnknownObjectException", GitHubFallbackError)

    connector = _connector()
    connector.org.get_team_by_slug.side_effect = GitHubFallbackError(
        "team private-team user secret-user token=raw-token"
    )

    assert connector.add_team_member("private-team", "secret-user") is False

    logs = _logged_text(connector.logger)
    assert "[REDACTED]" in logs
    assert "private-team" not in logs
    assert "secret-user" not in logs
    assert "raw-token" not in logs
    connector.logger.exception.assert_not_called()
    for log_call in connector.logger.error.call_args_list:
        assert log_call.kwargs.get("exc_info") is not True
