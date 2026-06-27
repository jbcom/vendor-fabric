"""ConnectorFabric - cached connector access for vendor fabric."""

from __future__ import annotations

import hashlib

from typing import TYPE_CHECKING, Any, cast

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from extended_data.inputs import InputProvider
from extended_data.logging import Logging
from extended_data.primitives import get_default_dict, get_unique_signature, make_hashable

# Import zoom directly (no extra deps)
from vendor_fabric.base import ConnectorBase
from vendor_fabric.registry import (
    ConnectorAdapter,
    get_connector_adapter,
    get_connector_class,
)
from vendor_fabric.registry import (
    get_connector_info as get_registered_connector_info,
)
from vendor_fabric.registry import (
    list_available_connectors as list_registered_available_connectors,
)
from vendor_fabric.registry import (
    list_connector_capabilities as list_registered_connector_capabilities,
)
from vendor_fabric.registry import (
    list_connector_categories as list_registered_connector_categories,
)
from vendor_fabric.registry import (
    list_connector_info as list_registered_connector_info,
)
from vendor_fabric.registry import (
    list_connectors as list_registered_connectors,
)
from vendor_fabric.registry import (
    list_connectors_by_capability as list_registered_connectors_by_capability,
)
from vendor_fabric.registry import (
    list_connectors_by_category as list_registered_connectors_by_category,
)
from vendor_fabric.zoom import ZoomConnector


_SENSITIVE_CACHE_KEY_PARTS = (
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "password",
    "secret",
    "token",
)


def _is_sensitive_cache_field(name: str) -> bool:
    """Return whether a cache-key field name usually carries secret material."""
    normalized = name.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_CACHE_KEY_PARTS)


def _cache_safe_value(name: str, value: Any) -> Any:
    """Return cache-key material without storing raw secret values."""
    hashable_value = make_hashable(value)
    if value is None or not _is_sensitive_cache_field(name):
        return hashable_value

    digest = hashlib.sha256(repr(hashable_value).encode()).hexdigest()
    return ("sha256", digest)


# Optional connectors - imported lazily when methods are called
# This allows the package to be imported without all optional SDKs installed

if TYPE_CHECKING:
    import boto3
    import hvac

    from boto3.resources.base import ServiceResource
    from botocore.config import Config

    from vendor_fabric.aws import AWSConnector
    from vendor_fabric.github import GitHubConnector
    from vendor_fabric.google import GoogleConnector
    from vendor_fabric.slack import SlackConnector
    from vendor_fabric.vault import VaultConnector


class ConnectorFabric(InputProvider):
    """Public API for vendor fabric with client caching.

    This class provides cached access to registered connectors while
    sharing input snapshots, lifecycle logging, and data normalization.

    Usage:
        vc = ConnectorFabric()
        slack = vc.get_slack_client(token="...", bot_token="...")
        github = vc.get_github_client(github_owner="org", github_token="...")
        aws_client = vc.get_aws_client("s3")

    For Meshy AI, use the functional interface directly:
        from vendor_fabric.meshy import text3d, image3d, rigging, animate
        model = text3d.generate("a medieval sword")

    Meshy does not provide a `get_meshy_client()` method because it uses a functional interface
    rather than a connector class, in order to simplify async operations and usage.
    """

    def __init__(
        self,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.logging = logger or Logging(logger_name=get_unique_signature(self))
        self.logger = self.logging.logger

        # Client cache - nested dict for different client types and their params
        self._client_cache: dict[str, dict[frozenset[tuple[str, Any]], Any]] = get_default_dict(levels=2)

    def _get_cache_key(self, **kwargs: Any) -> frozenset[tuple[str, Any]]:
        """Generate a hashable cache key from kwargs."""
        hashable_kwargs = {k: _cache_safe_value(k, v) for k, v in kwargs.items()}
        return frozenset(hashable_kwargs.items())

    def _get_cached_client(self, client_type: str, **kwargs: Any) -> Any | None:
        """Retrieve a client from cache."""
        cache_key = self._get_cache_key(**kwargs)
        return self._client_cache[client_type].get(cache_key)

    def _set_cached_client(self, client_type: str, client: Any, **kwargs: Any) -> None:
        """Store a client in cache."""
        cache_key = self._get_cache_key(**kwargs)
        self._client_cache[client_type][cache_key] = client

    def list_connectors(self) -> ExtendedList[ExtendedString]:
        """List connector catalog names."""
        return list_registered_connectors()

    def list_available_connectors(self) -> ExtendedList[ExtendedString]:
        """List connector names available in the current environment."""
        return list_registered_available_connectors()

    def list_connector_info(self, *, include_unavailable: bool = True) -> ExtendedList[ExtendedDict]:
        """List connector catalog metadata."""
        return list_registered_connector_info(include_unavailable=include_unavailable)

    def list_connector_categories(self, *, include_unavailable: bool = True) -> ExtendedList[ExtendedString]:
        """List connector catalog categories."""
        return list_registered_connector_categories(include_unavailable=include_unavailable)

    def list_connector_capabilities(self, *, include_unavailable: bool = True) -> ExtendedList[ExtendedString]:
        """List connector catalog capabilities."""
        return list_registered_connector_capabilities(include_unavailable=include_unavailable)

    def list_connectors_by_category(
        self,
        category: str,
        *,
        include_unavailable: bool = True,
    ) -> ExtendedList[ExtendedDict]:
        """List connector catalog metadata for a category."""
        return list_registered_connectors_by_category(category, include_unavailable=include_unavailable)

    def list_connectors_by_capability(
        self,
        capability: str,
        *,
        include_unavailable: bool = True,
    ) -> ExtendedList[ExtendedDict]:
        """List connector catalog metadata for a capability."""
        return list_registered_connectors_by_capability(capability, include_unavailable=include_unavailable)

    def get_connector_info(self, name: str, *, include_unavailable: bool = True) -> ExtendedDict:
        """Get catalog metadata for one connector."""
        return get_registered_connector_info(name, include_unavailable=include_unavailable)

    def get_connector_adapter(self, name: str, *, include_unavailable: bool = True) -> ConnectorAdapter:
        """Get the adapter registry entry for one connector."""
        return get_connector_adapter(name, include_unavailable=include_unavailable)

    def get_connector(self, name: str, **kwargs: Any) -> ConnectorBase:
        """Get a cached connector instance by registry name.

        The connector receives the fabric's shared inputs and logger unless
        explicit values are passed in ``kwargs``. This is the generic path for
        connectors that are registered through entry points or built-ins.
        """
        connector_name = name.strip().lower()
        cache_kwargs = {"name": connector_name, **kwargs}

        cached = self._get_cached_client("connector", **cache_kwargs)
        if cached:
            return cached

        connector_cls = get_connector_class(connector_name)
        connector_kwargs = dict(kwargs)
        connector_kwargs.setdefault("logger", self.logging)
        connector_kwargs.setdefault("inputs", self.inputs)
        connector = connector_cls(**connector_kwargs)
        self._set_cached_client("connector", connector, **cache_kwargs)
        return connector

    # -------------------------------------------------------------------------
    # AWS
    # -------------------------------------------------------------------------

    def get_aws_connector(
        self,
        execution_role_arn: str | None = None,
    ) -> AWSConnector:
        """Get a cached AWSConnector instance.

        Requires: pip install vendor-fabric[aws]
        """
        execution_role_arn = execution_role_arn or self.get_input("EXECUTION_ROLE_ARN", required=False)
        connector = self.get_connector("aws", execution_role_arn=execution_role_arn)
        return cast("AWSConnector", connector)

    def get_aws_client(
        self,
        client_name: str,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
        config: Config | None = None,
        **client_args: Any,
    ) -> boto3.client:
        """Get a cached boto3 client."""
        execution_role_arn = execution_role_arn or self.get_input("EXECUTION_ROLE_ARN", required=False)
        role_session_name = role_session_name or self.get_input("ROLE_SESSION_NAME", required=False)

        cached = self._get_cached_client(
            "aws_client",
            client_name=client_name,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        if cached:
            return cached

        connector = self.get_aws_connector(execution_role_arn)
        client = connector.get_aws_client(
            client_name=client_name,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
            config=config,
            **client_args,
        )
        self._set_cached_client(
            "aws_client",
            client,
            client_name=client_name,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        return client

    def get_aws_resource(
        self,
        service_name: str,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
        config: Config | None = None,
        **resource_args: Any,
    ) -> ServiceResource:
        """Get a cached boto3 resource."""
        execution_role_arn = execution_role_arn or self.get_input("EXECUTION_ROLE_ARN", required=False)
        role_session_name = role_session_name or self.get_input("ROLE_SESSION_NAME", required=False)

        cached = self._get_cached_client(
            "aws_resource",
            service_name=service_name,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        if cached:
            return cached

        connector = self.get_aws_connector(execution_role_arn)
        resource = connector.get_aws_resource(
            service_name=service_name,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
            config=config,
            **resource_args,
        )
        self._set_cached_client(
            "aws_resource",
            resource,
            service_name=service_name,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        return resource

    def get_aws_session(
        self,
        execution_role_arn: str | None = None,
        role_session_name: str | None = None,
    ) -> boto3.Session:
        """Get a cached boto3 session."""
        execution_role_arn = execution_role_arn or self.get_input("EXECUTION_ROLE_ARN", required=False)
        role_session_name = role_session_name or self.get_input("ROLE_SESSION_NAME", required=False)

        cached = self._get_cached_client(
            "aws_session",
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        if cached:
            return cached

        connector = self.get_aws_connector(execution_role_arn)
        session = connector.get_aws_session(
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        self._set_cached_client(
            "aws_session",
            session,
            execution_role_arn=execution_role_arn,
            role_session_name=role_session_name,
        )
        return session

    # -------------------------------------------------------------------------
    # GitHub
    # -------------------------------------------------------------------------

    def get_github_client(
        self,
        github_owner: str | None = None,
        github_repo: str | None = None,
        github_branch: str | None = None,
        github_token: str | None = None,
    ) -> GitHubConnector:
        """Get a cached GitHubConnector instance.

        Requires: pip install vendor-fabric[github]
        """
        github_owner = github_owner or self.get_input("GITHUB_OWNER", required=True)
        github_repo = github_repo or self.get_input("GITHUB_REPO", required=False)
        github_branch = github_branch or self.get_input("GITHUB_BRANCH", required=False)
        github_token = github_token or self.get_input("GITHUB_TOKEN", required=True)

        connector = self.get_connector(
            "github",
            github_owner=github_owner,
            github_repo=github_repo,
            github_branch=github_branch,
            github_token=github_token,
        )
        return cast("GitHubConnector", connector)

    # -------------------------------------------------------------------------
    # Google
    # -------------------------------------------------------------------------

    def get_google_client(
        self,
        service_account_info: dict[str, Any] | str | None = None,
        scopes: list[str] | None = None,
        subject: str | None = None,
    ) -> GoogleConnector:
        """Get a cached GoogleConnector instance.

        Requires: pip install vendor-fabric[google]
        """
        service_account_info = service_account_info or self.get_input("GOOGLE_SERVICE_ACCOUNT", required=True)
        connector = self.get_connector(
            "google",
            service_account_info=service_account_info,
            scopes=scopes,
            subject=subject,
        )
        return cast("GoogleConnector", connector)

    # -------------------------------------------------------------------------
    # Slack
    # -------------------------------------------------------------------------

    def get_slack_client(
        self,
        token: str | None = None,
        bot_token: str | None = None,
    ) -> SlackConnector:
        """Get a cached SlackConnector instance.

        Requires: pip install vendor-fabric[slack]
        """
        token = token or self.get_input("SLACK_TOKEN", required=True)
        bot_token = bot_token or self.get_input("SLACK_BOT_TOKEN", required=True)

        connector = self.get_connector("slack", token=token, bot_token=bot_token)
        return cast("SlackConnector", connector)

    # -------------------------------------------------------------------------
    # Vault
    # -------------------------------------------------------------------------

    def get_vault_client(
        self,
        vault_url: str | None = None,
        vault_namespace: str | None = None,
        vault_token: str | None = None,
    ) -> hvac.Client:
        """Get a cached Vault hvac.Client instance.

        Requires: pip install vendor-fabric[vault]
        """
        vault_url = vault_url or self.get_input("VAULT_ADDR", required=False)
        vault_namespace = vault_namespace or self.get_input("VAULT_NAMESPACE", required=False)
        vault_token = vault_token or self.get_input("VAULT_TOKEN", required=False)

        connector = cast(
            "VaultConnector",
            self.get_connector(
                "vault",
                vault_url=vault_url,
                vault_namespace=vault_namespace,
                vault_token=vault_token,
            ),
        )
        return connector.vault_client

    def get_vault_connector(
        self,
        vault_url: str | None = None,
        vault_namespace: str | None = None,
        vault_token: str | None = None,
    ) -> VaultConnector:
        """Get a cached VaultConnector instance.

        Requires: pip install vendor-fabric[vault]
        """
        vault_url = vault_url or self.get_input("VAULT_ADDR", required=False)
        vault_namespace = vault_namespace or self.get_input("VAULT_NAMESPACE", required=False)
        vault_token = vault_token or self.get_input("VAULT_TOKEN", required=False)

        connector = self.get_connector(
            "vault",
            vault_url=vault_url,
            vault_namespace=vault_namespace,
            vault_token=vault_token,
        )
        return cast("VaultConnector", connector)

    # -------------------------------------------------------------------------
    # Zoom
    # -------------------------------------------------------------------------

    def get_zoom_client(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        account_id: str | None = None,
    ) -> ZoomConnector:
        """Get a cached ZoomConnector instance."""
        client_id = client_id or self.get_input("ZOOM_CLIENT_ID", required=True)
        client_secret = client_secret or self.get_input("ZOOM_CLIENT_SECRET", required=True)
        account_id = account_id or self.get_input("ZOOM_ACCOUNT_ID", required=True)

        cached = self._get_cached_client(
            "zoom",
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
        )
        if cached:
            return cached

        connector = ZoomConnector(
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
            logger=self.logging,
            inputs=self.inputs,
        )
        self._set_cached_client(
            "zoom",
            connector,
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
        )
        return connector
