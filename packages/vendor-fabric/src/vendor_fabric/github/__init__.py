"""GitHub connector using shared extended-data primitives."""

from __future__ import annotations

import os

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, ExtendedTuple
from extended_data.io import (
    decode_file,
    get_encoding_for_file_path,
    wrap_raw_data_for_export,
)
from extended_data.logging import Logging
from extended_data.primitives import is_nothing

from vendor_fabric._optional import require_extra
from vendor_fabric.base import ConnectorBase
from vendor_fabric.capabilities import capability
from vendor_fabric.github._diagnostics import safe_github_ref, safe_github_text


Auth: Any = None
Github: Any = None
GraphqlClient: Any = None


class GitHubFallbackError(Exception):
    """Fallback exception used until PyGithub is imported."""


GithubException: Any = GitHubFallbackError
UnknownObjectException: Any = GitHubFallbackError


FilePath = str | os.PathLike[str]


def _require_loaded(module: Any | None, module_name: str) -> Any:
    if module is None:  # pragma: no cover - defensive guard for loader invariants
        raise RuntimeError(f"Failed to load optional GitHub dependency module: {module_name}")
    return module


def _load_github_sdk() -> None:
    """Load GitHub SDK dependencies lazily so tool metadata remains importable."""
    global Auth, Github, GithubException, GraphqlClient, UnknownObjectException

    needs_github_module = Auth is None or Github is None
    needs_exceptions = GithubException is GitHubFallbackError or UnknownObjectException is GitHubFallbackError
    needs_graphql = GraphqlClient is None

    if needs_github_module or needs_exceptions or needs_graphql:
        try:
            github_module = require_extra("github", "github") if needs_github_module else None
            github_exceptions = require_extra("github.GithubException", "github") if needs_exceptions else None
            graphql_module = require_extra("python_graphql_client", "github") if needs_graphql else None
        except ImportError as exc:
            msg = "PyGithub is required for GitHubConnector. Install with: pip install vendor-fabric[github]"
            raise ImportError(msg) from exc

        if Auth is None:
            Auth = _require_loaded(github_module, "github").Auth
        if Github is None:
            Github = _require_loaded(github_module, "github").Github
        if GithubException is GitHubFallbackError:
            GithubException = _require_loaded(github_exceptions, "github.GithubException").GithubException
        if UnknownObjectException is GitHubFallbackError:
            UnknownObjectException = _require_loaded(github_exceptions, "github.GithubException").UnknownObjectException
        if GraphqlClient is None:
            GraphqlClient = _require_loaded(graphql_module, "python_graphql_client").GraphqlClient


def get_github_api_error(exc: BaseException) -> str | None:
    """Extract error message from a GitHub exception."""
    data = getattr(exc, "data", {})
    return data.get("message", None)


DEFAULT_PER_PAGE = 100


class GitHubConnector(ConnectorBase):
    """GitHub connector for repository operations."""

    def __init__(
        self,
        github_owner: str,
        github_repo: str | None = None,
        github_branch: str | None = None,
        github_token: str | None = None,
        per_page: int = DEFAULT_PER_PAGE,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(logger=logger, **kwargs)
        _load_github_sdk()

        self.GITHUB_OWNER = github_owner
        self.GITHUB_REPO = github_repo
        self.GITHUB_TOKEN = github_token or self.get_input("GITHUB_TOKEN", required=True)

        auth = Auth.Token(self.GITHUB_TOKEN)
        self.git = Github(auth=auth, per_page=per_page)
        self.org = self.git.get_organization(self.GITHUB_OWNER)

        self.repo = None
        if github_repo:
            repo_ref = f"{self.GITHUB_OWNER}/{self.GITHUB_REPO}"
            try:
                self.repo = self.git.get_repo(repo_ref)
                self.logger.info(f"Connecting to Git repository {safe_github_ref(repo_ref)}")
            except UnknownObjectException:
                self.logger.warning(f"Repository {safe_github_ref(repo_ref)} does not exist")

        if github_branch is None and self.repo:
            self.GITHUB_BRANCH: str | None = self.repo.default_branch
        else:
            self.GITHUB_BRANCH = github_branch

        self.graphql_client = GraphqlClient(endpoint="https://api.github.com/graphql")

    def get_repository_branch(self, branch_name: str) -> Any | None:
        """Get a repository branch by name."""
        if self.repo is None:
            self.logger.warning(
                f"Repository not set for {safe_github_ref(self.GITHUB_OWNER)}, "
                f"cannot get branch {safe_github_ref(branch_name)}"
            )
            return None

        try:
            return self.repo.get_branch(branch_name)
        except UnknownObjectException:
            self.logger.warning(f"{safe_github_ref(branch_name)} does not yet exist")
            return None

    def create_repository_branch(self, branch_name: str, parent_branch: str | None = None) -> Any | None:
        """Create a new repository branch."""
        if self.repo is None:
            self.logger.warning(
                f"Repository not set for {safe_github_ref(self.GITHUB_OWNER)}, "
                f"cannot create branch {safe_github_ref(branch_name)}"
            )
            return None

        parent_branch_ref = self.get_repository_branch(parent_branch or self.repo.default_branch)
        if parent_branch_ref is None or is_nothing(parent_branch_ref):
            msg = (
                f"Cannot create Git branch {safe_github_ref(branch_name)}, "
                f"parent branch {safe_github_ref(parent_branch)} does not yet exist"
            )
            raise RuntimeError(msg)

        try:
            return self.repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=parent_branch_ref.commit.sha,
            )
        except GithubException as exc:
            if get_github_api_error(exc) == "Reference already exists":
                self.logger.info(f"Branch {safe_github_ref(branch_name)} already exists in Git repository")
                return self.get_repository_branch(branch_name)

            msg = f"Failed to create branch {safe_github_ref(branch_name)}: {safe_github_text(exc, branch_name)}"
            raise RuntimeError(msg) from None

    @capability("get_file", kind="files", aliases=("read_file",), description="Read a GitHub repository file.")
    def get_repository_file(
        self,
        file_path: FilePath,
        decode: bool | None = True,
        return_sha: bool | None = False,
        return_path: bool | None = False,
        charset: str | None = "utf-8",
        errors: str | None = "strict",
        raise_on_not_found: bool = False,
    ) -> ExtendedDict | ExtendedList[Any] | ExtendedString | ExtendedTuple[Any] | None:
        """Get a file from the repository."""
        file_path_text = os.fspath(file_path)
        safe_file_path = safe_github_ref(file_path_text)
        if self.repo is None:
            self.logger.warning(
                f"Repository not set for {safe_github_ref(self.GITHUB_OWNER)}, cannot get file {safe_file_path}"
            )
            return None

        def state_negative_result(result: str) -> None:
            self.logger.warning(result)
            if raise_on_not_found:
                raise FileNotFoundError(result)

        def get_retval(d: Any, s: str | None, p: str) -> Any:
            retval: list[Any] = [d]
            if return_sha:
                retval.append(s)
            if return_path:
                retval.append(p)
            if len(retval) == 1:
                return retval[0]
            return tuple(retval)

        file_data: Any = {} if decode else ""
        file_sha = None

        self.logger.debug(f"Getting repository file: {safe_file_path}")

        try:
            raw_file_data = self.repo.get_contents(file_path_text, ref=self.GITHUB_BRANCH)
            file_sha = raw_file_data.sha
            if is_nothing(raw_file_data.content):
                self.logger.warning(f"{safe_file_path} is empty of content: {safe_github_ref(self.GITHUB_BRANCH)}")
            else:
                file_data = raw_file_data.decoded_content.decode(charset, errors)
        except (UnknownObjectException, AttributeError):
            state_negative_result(f"{safe_file_path} does not exist")
        except ValueError as exc:
            self.logger.warning(f"Reading {safe_file_path} not supported: {safe_github_text(exc, file_path_text)}")
            decode = False

        if not decode or is_nothing(file_data):
            return self.extend_result(get_retval(file_data, file_sha, file_path_text))

        # Decode file content based on file type
        encoding = get_encoding_for_file_path(file_path_text)
        try:
            decoded_data = decode_file(file_data, file_path=file_path_text, as_extended=True)
        except Exception as exc:
            self.logger.warning(
                f"Failed to decode {safe_file_path} as {encoding}: {safe_github_text(exc, file_path_text)}"
            )
            decoded_data = file_data

        return self.extend_result(get_retval(decoded_data, file_sha, file_path_text))

    @capability("put_file", kind="files", aliases=("write_file",), description="Create or update a GitHub repository file.")
    def update_repository_file(
        self,
        file_path: FilePath,
        file_data: Any,
        file_sha: str | None = None,
        msg: str | None = None,
        allow_encoding: bool | str | None = None,
        allow_empty: bool = False,
        **format_opts: Any,
    ) -> Any | None:
        """Update a file in the repository."""
        file_path_text = os.fspath(file_path)
        safe_file_path = safe_github_ref(file_path_text)
        if self.repo is None:
            self.logger.warning(
                f"Repository not set for {safe_github_ref(self.GITHUB_OWNER)}, cannot update file {safe_file_path}"
            )
            return None

        if is_nothing(file_data) and not allow_empty:
            self.logger.warning(f"Empty file data for {safe_file_path} not allowed")
            return None

        if msg:
            self.logger.info("Using caller-provided repository file message")

        if allow_encoding is None:
            allow_encoding = get_encoding_for_file_path(file_path_text)

        file_data = wrap_raw_data_for_export(file_data, allow_encoding=allow_encoding, **format_opts)

        if not isinstance(file_data, str):
            file_data = str(file_data)

        self.logger.info(f"Updating repository file: {safe_file_path}")

        if file_sha is None:
            result = self.get_repository_file(file_path_text, return_sha=True)
            if isinstance(result, tuple):
                _, file_sha = result

        if file_sha is None:
            if msg is None:
                msg = f"Creating {file_path_text}"
            return self.repo.create_file(
                path=file_path_text,
                message=msg,
                branch=self.GITHUB_BRANCH,
                content=file_data,
            )
        else:
            if msg is None:
                msg = f"Updating {file_path_text}"
            return self.repo.update_file(
                path=file_path_text,
                message=msg,
                content=file_data,
                sha=file_sha,
                branch=self.GITHUB_BRANCH,
            )

    @capability("delete_file", kind="files", description="Delete a GitHub repository file.")
    def delete_repository_file(self, file_path: FilePath, msg: str | None = None) -> Any | None:
        """Delete a file from the repository."""
        file_path_text = os.fspath(file_path)
        safe_file_path = safe_github_ref(file_path_text)
        if self.repo is None:
            self.logger.warning(
                f"Repository not set for {safe_github_ref(self.GITHUB_OWNER)}, cannot delete file {safe_file_path}"
            )
            return None

        self.logger.info(f"Deleting repository file: {safe_file_path}")

        result = self.get_repository_file(file_path=file_path_text, return_sha=True)
        sha = None
        if isinstance(result, tuple):
            _, sha = result

        if sha is None:
            return None

        if msg is None:
            msg = f"Deleting {file_path_text}"

        return self.repo.delete_file(
            path=file_path_text,
            message=msg,
            branch=self.GITHUB_BRANCH,
            sha=sha,
        )

    # =========================================================================
    # Organization Members
    # =========================================================================

    @capability("list_users", kind="users", description="List GitHub organization members.")
    def list_org_members(
        self,
        role: str | None = None,
        include_pending: bool = False,
    ) -> ExtendedDict:
        """List organization members.

        Args:
            role: Filter by role ('admin', 'member'). None returns all.
            include_pending: Include pending invitations. Defaults to False.

        Returns:
            Dictionary mapping usernames to member data.
        """
        self.logger.info(f"Listing members for organization: {safe_github_ref(self.GITHUB_OWNER)}")

        members: dict[str, dict[str, Any]] = {}

        # Get active members
        filter_args = {}
        if role:
            filter_args["role"] = role

        for member in self.org.get_members(**filter_args):
            membership = self.org.get_user_membership(member)
            members[member.login] = {
                "id": member.id,
                "login": member.login,
                "name": member.name,
                "email": member.email,
                "role": membership.role,
                "state": membership.state,
                "avatar_url": member.avatar_url,
                "html_url": member.html_url,
            }

        # Include pending invitations
        if include_pending:
            for invite in self.org.invitations():
                login = invite.login or invite.email
                members[login] = {
                    "id": invite.id,
                    "login": invite.login,
                    "email": invite.email,
                    "role": invite.role,
                    "state": "pending",
                    "invited_at": str(invite.created_at) if invite.created_at else None,
                }

        self.logger.info(f"Retrieved {len(members)} organization members")
        return self.extend_result(members)

    def get_org_member(self, username: str) -> ExtendedDict | None:
        """Get a specific organization member.

        Args:
            username: GitHub username.

        Returns:
            Member data or None if not found.
        """
        try:
            member = self.git.get_user(username)
            membership = self.org.get_user_membership(member)
            return self.extend_result(
                {
                    "id": member.id,
                    "login": member.login,
                    "name": member.name,
                    "email": member.email,
                    "role": membership.role,
                    "state": membership.state,
                    "avatar_url": member.avatar_url,
                    "html_url": member.html_url,
                }
            )
        except UnknownObjectException:
            self.logger.warning(f"User not found: {safe_github_ref(username)}")
            return None

    # =========================================================================
    # Repositories
    # =========================================================================

    @capability("list_repositories", kind="repositories", description="List GitHub repositories.")
    def list_repositories(
        self,
        type_filter: str = "all",
        include_branches: bool = False,
    ) -> ExtendedDict:
        """List organization repositories.

        Args:
            type_filter: Filter type ('all', 'public', 'private', 'forks', 'sources', 'member').
            include_branches: Include branch information. Defaults to False.

        Returns:
            Dictionary mapping repo names to repository data.
        """
        self.logger.info(f"Listing repositories for organization: {safe_github_ref(self.GITHUB_OWNER)}")

        repos: dict[str, dict[str, Any]] = {}

        for repo in self.org.get_repos(type=type_filter):
            repo_data = {
                "id": repo.id,
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "private": repo.private,
                "archived": repo.archived,
                "default_branch": repo.default_branch,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "ssh_url": repo.ssh_url,
                "language": repo.language,
                "topics": repo.topics,
                "created_at": str(repo.created_at) if repo.created_at else None,
                "updated_at": str(repo.updated_at) if repo.updated_at else None,
                "pushed_at": str(repo.pushed_at) if repo.pushed_at else None,
            }

            if include_branches:
                branches = []
                for branch in repo.get_branches():
                    branches.append(
                        {
                            "name": branch.name,
                            "protected": branch.protected,
                            "sha": branch.commit.sha,
                        }
                    )
                repo_data["branches"] = branches

            repos[repo.name] = repo_data

        self.logger.info(f"Retrieved {len(repos)} repositories")
        return self.extend_result(repos)

    def get_repository(self, repo_name: str) -> ExtendedDict | None:
        """Get a specific repository.

        Args:
            repo_name: Repository name.

        Returns:
            Repository data or None if not found.
        """
        try:
            repo = self.git.get_repo(f"{self.GITHUB_OWNER}/{repo_name}")
            return self.extend_result(
                {
                    "id": repo.id,
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "private": repo.private,
                    "archived": repo.archived,
                    "default_branch": repo.default_branch,
                    "html_url": repo.html_url,
                    "clone_url": repo.clone_url,
                    "ssh_url": repo.ssh_url,
                    "language": repo.language,
                    "topics": repo.topics,
                }
            )
        except UnknownObjectException:
            self.logger.warning(f"Repository not found: {safe_github_ref(repo_name)}")
            return None

    # =========================================================================
    # Teams
    # =========================================================================

    @capability("list_teams", kind="teams", description="List GitHub organization teams.")
    def list_teams(
        self,
        include_members: bool = False,
        include_repos: bool = False,
    ) -> ExtendedDict:
        """List organization teams.

        Args:
            include_members: Include team members. Defaults to False.
            include_repos: Include team repositories. Defaults to False.

        Returns:
            Dictionary mapping team slugs to team data.
        """
        self.logger.info(f"Listing teams for organization: {safe_github_ref(self.GITHUB_OWNER)}")

        teams: dict[str, dict[str, Any]] = {}

        for team in self.org.get_teams():
            team_data = {
                "id": team.id,
                "name": team.name,
                "slug": team.slug,
                "description": team.description,
                "privacy": team.privacy,
                "permission": team.permission,
                "html_url": team.html_url,
                "members_count": team.members_count,
                "repos_count": team.repos_count,
            }

            if include_members:
                members = []
                for member in team.get_members():
                    members.append(
                        {
                            "login": member.login,
                            "id": member.id,
                            "name": member.name,
                        }
                    )
                team_data["members"] = members

            if include_repos:
                repos = []
                for repo in team.get_repos():
                    repos.append(
                        {
                            "name": repo.name,
                            "full_name": repo.full_name,
                            "permission": team.get_repo_permission(repo),
                        }
                    )
                team_data["repositories"] = repos

            teams[team.slug] = team_data

        self.logger.info(f"Retrieved {len(teams)} teams")
        return self.extend_result(teams)

    def get_team(self, team_slug: str) -> ExtendedDict | None:
        """Get a specific team.

        Args:
            team_slug: Team slug.

        Returns:
            Team data or None if not found.
        """
        try:
            team = self.org.get_team_by_slug(team_slug)
            return self.extend_result(
                {
                    "id": team.id,
                    "name": team.name,
                    "slug": team.slug,
                    "description": team.description,
                    "privacy": team.privacy,
                    "permission": team.permission,
                    "html_url": team.html_url,
                    "members_count": team.members_count,
                    "repos_count": team.repos_count,
                }
            )
        except UnknownObjectException:
            self.logger.warning(f"Team not found: {safe_github_ref(team_slug)}")
            return None

    def add_team_member(self, team_slug: str, username: str, role: str = "member") -> bool:
        """Add a member to a team.

        Args:
            team_slug: Team slug.
            username: GitHub username.
            role: Role ('member' or 'maintainer'). Defaults to 'member'.

        Returns:
            True if successful.
        """
        safe_username = safe_github_ref(username)
        safe_team = safe_github_ref(team_slug)
        self.logger.info(f"Adding {safe_username} to team {safe_team}")
        try:
            team = self.org.get_team_by_slug(team_slug)
            user = self.git.get_user(username)
            team.add_membership(user, role=role)
            self.logger.info(f"Added {safe_username} to team {safe_team}")
            return True
        except (UnknownObjectException, GithubException) as e:
            self.logger.error(  # noqa: TRY400 - traceback can expose raw GitHub identifiers.
                f"Failed to add {safe_username} to team {safe_team}: {safe_github_text(e, username, team_slug)}"
            )
            return False

    def remove_team_member(self, team_slug: str, username: str) -> bool:
        """Remove a member from a team.

        Args:
            team_slug: Team slug.
            username: GitHub username.

        Returns:
            True if successful.
        """
        safe_username = safe_github_ref(username)
        safe_team = safe_github_ref(team_slug)
        self.logger.info(f"Removing {safe_username} from team {safe_team}")
        try:
            team = self.org.get_team_by_slug(team_slug)
            user = self.git.get_user(username)
            team.remove_membership(user)
            self.logger.info(f"Removed {safe_username} from team {safe_team}")
            return True
        except (UnknownObjectException, GithubException) as e:
            self.logger.error(  # noqa: TRY400 - traceback can expose raw GitHub identifiers.
                f"Failed to remove {safe_username} from team {safe_team}: {safe_github_text(e, username, team_slug)}"
            )
            return False

    # =========================================================================
    # GraphQL Queries
    # =========================================================================

    def execute_graphql(self, query: str, variables: dict[str, Any] | None = None) -> ExtendedDict:
        """Execute a GraphQL query against the GitHub API.

        Args:
            query: GraphQL query string.
            variables: Optional query variables.

        Returns:
            Query response data.
        """
        headers = {"Authorization": f"Bearer {self.GITHUB_TOKEN}"}
        return self.extend_result(
            self.graphql_client.execute(
                query=query,
                variables=variables or {},
                headers=headers,
            )
        )

    # =========================================================================
    # Enhanced User Operations
    # =========================================================================

    def get_users_with_verified_emails(
        self,
        members: Mapping[str, Mapping[str, Any]] | None = None,
        domain_filter: str | None = None,
    ) -> ExtendedDict:
        """Get organization members with their verified emails.

        Uses GraphQL to get verified email addresses for org members.

        Args:
            members: Pre-fetched members dict. Fetched if not provided.
            domain_filter: Filter by email domain (e.g., 'company.com').

        Returns:
            Dictionary mapping usernames to member data with verified emails.
        """
        self.logger.info(f"Getting users with verified emails for {safe_github_ref(self.GITHUB_OWNER)}")

        if members is None:
            members = self.list_org_members()

        # GraphQL query for verified emails
        query = """
        query($login: String!) {
            user(login: $login) {
                login
                email
                organizationVerifiedDomainEmails(login: $login)
            }
        }
        """

        enriched: dict[str, dict[str, Any]] = {}

        for username, member_data in members.items():
            try:
                result = self.execute_graphql(query, {"login": username})
                user_data = result.get("data", {}).get("user", {})

                verified_emails = user_data.get("organizationVerifiedDomainEmails", [])
                primary_email = user_data.get("email")

                enriched_data = dict(member_data)
                enriched_data["verified_emails"] = verified_emails
                enriched_data["primary_email"] = primary_email

                # Apply domain filter
                if domain_filter:
                    matching_emails = [e for e in verified_emails if e.endswith(f"@{domain_filter}")]
                    if not matching_emails:
                        continue
                    enriched_data["domain_emails"] = matching_emails

                enriched[username] = enriched_data

            except Exception as e:
                self.logger.warning(
                    f"Failed to get verified emails for {safe_github_ref(username)}: {safe_github_text(e, username)}"
                )
                enriched[username] = dict(member_data)

        self.logger.info(f"Retrieved verified emails for {len(enriched)} users")
        return self.extend_result(enriched)

    # =========================================================================
    # GitHub Actions Workflows
    # =========================================================================

    def build_workflow(
        self,
        name: str,
        on: Mapping[str, Any],
        jobs: Mapping[str, Mapping[str, Any]],
        env: Mapping[str, str] | None = None,
        permissions: Mapping[str, str] | None = None,
        concurrency: Mapping[str, Any] | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> ExtendedDict:
        """Build a GitHub Actions workflow structure.

        Args:
            name: Workflow name.
            on: Trigger configuration.
            jobs: Jobs configuration.
            env: Global environment variables.
            permissions: Workflow permissions.
            concurrency: Concurrency settings.
            defaults: Default settings for jobs.

        Returns:
            Workflow configuration dict suitable for YAML export.
        """
        workflow: dict[str, Any] = {"name": name}

        if permissions:
            workflow["permissions"] = permissions

        workflow["on"] = on

        if env:
            workflow["env"] = env

        if concurrency:
            workflow["concurrency"] = concurrency

        if defaults:
            workflow["defaults"] = defaults

        workflow["jobs"] = jobs

        return self.extend_result(workflow)

    def build_workflow_job(
        self,
        runs_on: str = "ubuntu-latest",
        steps: Sequence[Mapping[str, Any]] | None = None,
        needs: Sequence[str] | None = None,
        if_condition: str | None = None,
        env: Mapping[str, str] | None = None,
        strategy: Mapping[str, Any] | None = None,
        timeout_minutes: int | None = None,
        services: Mapping[str, Any] | None = None,
        outputs: Mapping[str, str] | None = None,
    ) -> ExtendedDict:
        """Build a GitHub Actions workflow job.

        Args:
            runs_on: Runner label(s).
            steps: Job steps.
            needs: Dependencies on other jobs.
            if_condition: Conditional expression.
            env: Job environment variables.
            strategy: Matrix strategy.
            timeout_minutes: Job timeout.
            services: Service containers.
            outputs: Job outputs.

        Returns:
            Job configuration dict.
        """
        job: dict[str, Any] = {"runs-on": runs_on}

        if needs:
            job["needs"] = needs

        if if_condition:
            job["if"] = if_condition

        if env:
            job["env"] = env

        if strategy:
            job["strategy"] = strategy

        if timeout_minutes:
            job["timeout-minutes"] = timeout_minutes

        if services:
            job["services"] = services

        if outputs:
            job["outputs"] = outputs

        job["steps"] = list(steps or [])

        return self.extend_result(job)

    def build_workflow_step(
        self,
        name: str,
        uses: str | None = None,
        run: str | None = None,
        with_params: Mapping[str, Any] | None = None,
        env: Mapping[str, str] | None = None,
        if_condition: str | None = None,
        working_directory: str | None = None,
        shell: str | None = None,
        id: str | None = None,  # noqa: A002
    ) -> ExtendedDict:
        """Build a GitHub Actions workflow step.

        Args:
            name: Step name.
            uses: Action to use (e.g., 'actions/checkout@v4').
            run: Shell command(s) to run.
            with_params: Input parameters for the action.
            env: Step environment variables.
            if_condition: Conditional expression.
            working_directory: Working directory for run commands.
            shell: Shell to use for run commands.
            id: Step ID for outputs.

        Returns:
            Step configuration dict.
        """
        step: dict[str, Any] = {"name": name}

        if id:
            step["id"] = id

        if if_condition:
            step["if"] = if_condition

        if uses:
            step["uses"] = uses
            if with_params:
                step["with"] = with_params
        elif run:
            step["run"] = run
            if shell:
                step["shell"] = shell
            if working_directory:
                step["working-directory"] = working_directory

        if env:
            step["env"] = env

        return self.extend_result(step)

    def create_python_ci_workflow(
        self,
        python_versions: list[str] | None = None,
        test_command: str = "pytest",
        lint_command: str = "ruff check",
        format_command: str | None = "ruff format --check",
        install_command: str = "uv sync --all-packages",
        working_directory: str = ".",
    ) -> ExtendedDict:
        """Create a standard Python CI workflow.

        Args:
            python_versions: Python versions to test. Defaults to ['3.12'].
            test_command: Test command. Defaults to 'pytest'.
            lint_command: Lint command. Defaults to 'ruff check'.
            format_command: Format check command. None to skip.
            install_command: Dependency install command.
            working_directory: Working directory for commands.

        Returns:
            Complete workflow configuration.
        """
        python_versions = python_versions or ["3.12"]

        setup_steps = [
            self.build_workflow_step(
                name="Checkout code",
                uses="actions/checkout@v6",
            ),
            self.build_workflow_step(
                name="Set up Python",
                uses="actions/setup-python@v6",
                with_params={
                    "python-version": "${{ matrix.python-version }}",
                },
            ),
            self.build_workflow_step(
                name="Install uv",
                uses="astral-sh/setup-uv@v7",
            ),
            self.build_workflow_step(
                name="Install dependencies",
                run=install_command,
                working_directory=working_directory,
            ),
        ]

        test_steps = []

        if lint_command:
            test_steps.append(
                self.build_workflow_step(
                    name="Lint",
                    run=lint_command,
                    working_directory=working_directory,
                )
            )

        if format_command:
            test_steps.append(
                self.build_workflow_step(
                    name="Format check",
                    run=format_command,
                    working_directory=working_directory,
                )
            )

        test_steps.append(
            self.build_workflow_step(
                name="Run tests",
                run=test_command,
                working_directory=working_directory,
            )
        )

        test_job = self.build_workflow_job(
            runs_on="ubuntu-latest",
            steps=setup_steps + test_steps,
            strategy={
                "matrix": {
                    "python-version": python_versions,
                },
            },
        )

        return self.build_workflow(
            name="CI",
            on={
                "push": {"branches": ["main"]},
                "pull_request": {"branches": ["main"]},
            },
            jobs={"test": test_job},
        )


def build_github_actions_workflow(
    workflow_name: str,
    jobs: dict[str, Any],
    concurrency_group: str | None = None,
    environment_variables: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    use_oidc_auth: bool = True,
    events: dict[str, Any] | None = None,
    triggers: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    pull_requests: dict[str, Any] | None = None,
) -> str:
    """Generate a GitHub Actions workflow YAML string."""
    if not workflow_name:
        msg = "workflow_name is required"
        raise ValueError(msg)
    if not jobs:
        msg = "jobs definition is required"
        raise ValueError(msg)

    env_block = {
        "COMMIT_SHA": "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}",
        "BRANCH": "${{ github.event_name == 'pull_request' && format('refs/heads/{0}', github.event.pull_request.head.ref) || github.ref }}",
    }
    for key, value in (environment_variables or {}).items():
        env_block[key] = value
    for key, secret_name in (secrets or {}).items():
        env_block[key] = f"${{{{ secrets.{secret_name} }}}}"

    permissions = {"contents": "write", "pull-requests": "write"}
    if use_oidc_auth:
        permissions["id-token"] = "write"

    trigger_defaults = {"push": True, "pull_request": True, "workflow_dispatch": True, "workflow_call": bool(inputs)}
    if events:
        trigger_defaults.update(events)

    workflow_on: dict[str, Any] = {}
    push_config = deepcopy(triggers or {})

    if trigger_defaults.get("push"):
        workflow_on["push"] = push_config
    if trigger_defaults.get("pull_request"):
        workflow_on["pull_request"] = pull_requests or {}
    if trigger_defaults.get("workflow_dispatch"):
        dispatch_block: dict[str, Any] = {}
        if inputs:
            dispatch_block["inputs"] = inputs
        workflow_on["workflow_dispatch"] = dispatch_block
    if trigger_defaults.get("workflow_call"):
        call_block: dict[str, Any] = {}
        if inputs:
            call_block["inputs"] = inputs
        workflow_on["workflow_call"] = call_block

    workflow: dict[str, Any] = {
        "name": workflow_name,
        "on": workflow_on,
        "env": env_block,
        "permissions": permissions,
        "jobs": jobs,
    }

    if concurrency_group:
        workflow["concurrency"] = concurrency_group

    return wrap_raw_data_for_export(workflow, allow_encoding="yaml").strip()


__all__ = [
    # Core connector
    "GitHubConnector",
]
