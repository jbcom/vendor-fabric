"""Vault connector built on extended-data primitives."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString
from extended_data.logging import Logging
from extended_data.primitives import is_nothing
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric._optional import require_extra
from vendor_fabric.base import ConnectorBase
from vendor_fabric.capabilities import capability


if TYPE_CHECKING:
    import hvac

    from hvac.exceptions import VaultError
else:
    hvac = None

    class VaultError(Exception):
        """Fallback exception used until hvac is imported."""


def _load_hvac() -> Any:
    """Load hvac lazily so capability metadata can import without the vault extra."""
    global VaultError, hvac

    if hvac is None:
        hvac = require_extra("hvac", "vault")
        VaultError = require_extra("hvac.exceptions", "vault").VaultError
    return hvac


# Default Vault settings
VAULT_URL_ENV_VAR = "VAULT_ADDR"
VAULT_NAMESPACE_ENV_VAR = "VAULT_NAMESPACE"
VAULT_ROLE_ID_ENV_VAR = "VAULT_ROLE_ID"
VAULT_SECRET_ID_ENV_VAR = "VAULT_SECRET_ID"
VAULT_APPROLE_PATH_ENV_VAR = "VAULT_APPROLE_PATH"


def _safe_log_text(value: Any, *sensitive_values: Any) -> str:
    """Return a redacted string for Vault diagnostic output."""
    return redact_sensitive_text(value, values=_iter_diagnostic_values(sensitive_values))


def _safe_ref_text(value: Any) -> str:
    """Return a redacted string for sensitive Vault resource references."""
    return _safe_log_text(value, value)


def _iter_diagnostic_values(values: Iterable[Any]) -> Iterable[Any]:
    """Yield scalar values from nested diagnostic context."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, Mapping):
            yield from _iter_diagnostic_values(value.values())
        elif isinstance(value, (str, bytes)):
            yield value
        elif isinstance(value, Iterable):
            yield from _iter_diagnostic_values(value)
        else:
            yield value


class VaultConnector(ConnectorBase):
    """Vault connector with token and AppRole authentication."""

    def __init__(
        self,
        vault_url: str | None = None,
        vault_namespace: str | None = None,
        vault_token: str | None = None,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(logger=logger, **kwargs)

        self._hvac = _load_hvac()
        self.vault_url = vault_url
        self.vault_namespace = vault_namespace
        self.vault_token = vault_token
        self._vault_client: hvac.Client | None = None
        self._vault_token_expiration: datetime | None = None

        self.logger.info("Initializing Vault connector")

    @property
    def vault_client(self) -> hvac.Client:
        """Lazy initialization of the Vault client."""
        if self._vault_client and self._is_token_valid():
            return self._vault_client

        self.logger.info("Initializing new Vault client connection")

        vault_url = self.vault_url or self.get_input(VAULT_URL_ENV_VAR, required=True)
        vault_namespace = self.vault_namespace or self.get_input(VAULT_NAMESPACE_ENV_VAR, required=False)
        vault_token = self.vault_token or self.get_input("VAULT_TOKEN", required=False)

        vault_opts: dict[str, Any] = {"url": vault_url}
        if vault_namespace:
            vault_opts["namespace"] = vault_namespace
        if vault_token:
            vault_opts["token"] = vault_token

        try:
            self._vault_client = self._hvac.Client(**vault_opts)

            if vault_token and self._vault_client.is_authenticated():
                self._set_token_expiration()
                self.logger.info("Authenticated with existing token")
                return self._vault_client

        except VaultError as e:
            self.logger.error(  # noqa: TRY400 - traceback can expose raw Vault credentials.
                f"Error initializing Vault client with token: "
                f"{_safe_log_text(e, vault_url, vault_namespace, vault_token)}"
            )

        # Fallback to AppRole authentication
        self.logger.info("Attempting AppRole authentication")

        try:
            app_role_path = self.get_input(VAULT_APPROLE_PATH_ENV_VAR, required=False, default="approle")
            role_id = self.get_input(VAULT_ROLE_ID_ENV_VAR, required=False)
            secret_id = self.get_input(VAULT_SECRET_ID_ENV_VAR, required=False)

            if role_id and secret_id:
                vault_opts = {"url": vault_url}
                if vault_namespace:
                    vault_opts["namespace"] = vault_namespace

                self._vault_client = self._hvac.Client(**vault_opts)
                self._vault_client.auth.approle.login(
                    role_id=role_id,
                    secret_id=secret_id,
                    mount_point=app_role_path,
                    use_token=True,
                )

                if self._vault_client.is_authenticated():
                    self._set_token_expiration()
                    self.logger.info("AppRole authentication successful")
                    return self._vault_client

        except VaultError as e:
            msg = f"Error during AppRole authentication: {_safe_log_text(e, app_role_path, role_id, secret_id)}"
            self.logger.error(msg)  # noqa: TRY400 - traceback can expose raw Vault credentials.
            raise RuntimeError(msg) from None

        msg = "Vault authentication failed: no valid token or AppRole credentials provided"
        raise RuntimeError(msg)

    def _set_token_expiration(self) -> None:
        """Set the token expiration time."""
        if self._vault_client is None:
            return

        try:
            token_data = self._vault_client.auth.token.lookup_self()
            expire_time = token_data.get("data", {}).get("expire_time")

            if expire_time:
                expire_time_clean = expire_time.replace("Z", "+00:00")
                self._vault_token_expiration = datetime.fromisoformat(expire_time_clean)
                # fromisoformat with '+00:00' produces a timezone-aware datetime (Python 3.7+ only)
                # No need to manually set tzinfo if running on Python 3.7 or newer.
                # If supporting Python <3.7, manual tzinfo assignment is required.
        except VaultError as e:
            self.logger.warning(f"Failed to lookup Vault token expiration: {_safe_log_text(e)}")

    def _is_token_valid(self) -> bool:
        """Check if the current Vault token is still valid."""
        if not self._vault_token_expiration:
            return False
        return datetime.now(UTC) < self._vault_token_expiration

    @staticmethod
    def _validate_mount_point(mount_point: str | None) -> None:
        """Ensure Vault mount inputs do not allow traversal or null bytes."""
        if mount_point and (".." in mount_point or "\x00" in mount_point):
            msg = "mount_point contains invalid characters"
            raise ValueError(msg)

    @classmethod
    def get_vault_client(
        cls,
        vault_url: str | None = None,
        vault_namespace: str | None = None,
        vault_token: str | None = None,
        **kwargs: Any,
    ) -> hvac.Client:
        """Get an instance of the Vault client."""
        instance = cls(vault_url, vault_namespace, vault_token, **kwargs)
        return instance.vault_client

    @capability("list_secrets", kind="secrets", description="List Vault KV secrets.")
    def list_secrets(
        self,
        root_path: str = "/",
        mount_point: str = "secret",
        max_depth: int | None = None,
    ) -> ExtendedDict:
        """List secrets recursively from Vault KV v2 engine.

        Args:
            root_path: Starting path for listing (default: "/").
            mount_point: KV engine mount point (default: "secret").
            max_depth: Maximum directory depth to traverse (None = unlimited).

        Returns:
            Dict mapping secret paths to their data.

        Raises:
            ValueError: If root_path contains path traversal sequences.
        """
        # Validate root_path to prevent path traversal attacks
        if root_path and (".." in root_path or "\x00" in root_path):
            msg = "root_path contains invalid characters"
            raise ValueError(msg)

        display_root = root_path if root_path not in (None, "", "/") else "/"
        self.logger.info(f"Listing Vault secrets from {_safe_ref_text(mount_point)}{_safe_ref_text(display_root)}")

        secrets: dict[str, dict[str, Any]] = {}
        client = self.vault_client

        normalized_root = (root_path or "").strip("/")
        list_path = normalized_root.rstrip("/") if normalized_root else ""
        path_prefix = f"{list_path}/" if list_path else ""

        # Initial listing from root_path
        try:
            root_result = client.secrets.kv.v2.list_secrets(
                path=list_path,
                mount_point=mount_point,
            )
            initial_paths = [
                (f"{path_prefix}{key}" if path_prefix else key, 0)
                for key in root_result.get("data", {}).get("keys", [])
            ]
        except VaultError as e:
            self.logger.warning(f"Invalid root path {_safe_ref_text(display_root)}: {_safe_log_text(e, display_root)}")
            return self.extend_result(secrets)

        stack: deque[tuple[str, int]] = deque(initial_paths)

        while stack:
            current_path, depth = stack.popleft()

            if not current_path.endswith("/"):
                # It's a secret, fetch it
                try:
                    secret_data = client.secrets.kv.v2.read_secret_version(
                        path=current_path,
                        mount_point=mount_point,
                    )["data"]["data"]
                    secrets[current_path] = secret_data
                    self.logger.debug(f"Retrieved secret: {_safe_ref_text(current_path)}")
                except VaultError as e:
                    self.logger.warning(
                        f"Failed to read secret {_safe_ref_text(current_path)}: {_safe_log_text(e, current_path)}"
                    )
            # It's a directory, list its contents if within max_depth
            elif max_depth is None or depth < max_depth:
                try:
                    listing = client.secrets.kv.v2.list_secrets(
                        path=current_path,
                        mount_point=mount_point,
                    )
                    keys = listing.get("data", {}).get("keys", [])
                    for key in keys:
                        new_path = f"{current_path}{key}"  # current_path already ends with /
                        stack.append((new_path, depth + 1))
                except VaultError as e:
                    self.logger.warning(
                        f"Failed to list path {_safe_ref_text(current_path)}: {_safe_log_text(e, current_path)}"
                    )

        self.logger.info(f"Listed {len(secrets)} Vault secrets")
        return self.extend_result(secrets)

    @capability("read_secret", kind="secrets", aliases=("get_file",), description="Read one Vault secret path.")
    def read_secret(
        self,
        path: str,
        mount_point: str = "secret",
    ) -> ExtendedDict | None:
        """Read a single secret from Vault.

        Args:
            path: Path to the secret.
            mount_point: KV engine mount point (default: "secret").

        Returns:
            Secret data dict, or None if not found.
        """
        try:
            result = self.vault_client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=mount_point,
            )
            data = result.get("data", {}).get("data")
            if data is None:
                return None
            return self.extend_result(data)
        except VaultError as e:
            self.logger.warning(f"Failed to read secret {_safe_ref_text(path)}: {_safe_log_text(e, path)}")
            return None

    @capability("get_secret", kind="secrets", description="Find one Vault secret.")
    def get_secret(
        self,
        path: str = "/",
        secret_name: str | None = None,
        matchers: dict[str, str] | None = None,
        mount_point: str = "secret",
    ) -> ExtendedDict | None:
        """Get Vault secret by path, name, or by searching with matchers.

        This method supports three modes:
        1. Direct path + secret_name: Fetches secret at path/secret_name
        2. Path with matchers: Searches secrets under path and returns first match
        3. Path without matchers: Returns first non-empty secret found

        Args:
            path: Root path to search or base path for secret_name (default: "/").
            secret_name: Specific secret name to append to path.
            matchers: Dict of key/value pairs to match against secret data.
            mount_point: KV engine mount point (default: "secret").

        Returns:
            Secret data dict, or None if not found.
        """
        self.logger.debug(
            f"Getting Vault secret: path={_safe_ref_text(path)}, secret_name={_safe_ref_text(secret_name)}"
        )

        client = self.vault_client
        secret_data = None

        # Handle specific secret_name case - direct fetch
        if not is_nothing(secret_name):
            # Build the full path: path/secret_name or just secret_name if path is "/"
            secret_path = f"{path}/{secret_name}" if path and path != "/" else secret_name
            self.logger.debug(f"Resolved secret path: {_safe_ref_text(secret_path)}")

            try:
                secret_data = client.secrets.kv.v2.read_secret_version(path=secret_path, mount_point=mount_point)[
                    "data"
                ]["data"]
                self.logger.debug(f"Retrieved secret data for {_safe_ref_text(secret_path)}")
            except VaultError as e:
                self.logger.warning(
                    f"Failed to find secret at {_safe_ref_text(path)}"
                    + (f"/{_safe_ref_text(secret_name)}" if not is_nothing(secret_name) else "")
                    + f": {_safe_log_text(e, path, secret_name, secret_path)}"
                )
            return self.extend_result(secret_data) if secret_data is not None else None

        # No secret_name provided - search under path
        self.logger.info(f"Finding secrets under {_safe_ref_text(path)}")

        matching_secret_paths = self.list_secrets(root_path=path, mount_point=mount_point)
        self.logger.debug(f"Found {len(matching_secret_paths)} potential secrets")

        if is_nothing(matching_secret_paths):
            self.logger.warning(f"No secrets found matching {_safe_ref_text(path)}")
            return None

        # Convert to deque for efficient popleft iteration
        path_queue: deque[str] = deque(matching_secret_paths.keys())

        while path_queue and secret_data is None:
            secret_path = path_queue.popleft()
            safe_secret_path = _safe_ref_text(secret_path)
            self.logger.debug(f"Checking secret path: {safe_secret_path}")

            try:
                matching_secret_data = client.secrets.kv.v2.read_secret_version(
                    path=secret_path, mount_point=mount_point
                )["data"]["data"]
                self.logger.debug(
                    f"Secret data for {safe_secret_path}: {_safe_log_text(list(matching_secret_data.keys()))}"
                )
            except VaultError:
                self.logger.warning(f"{safe_secret_path} is empty or invalid, skipping it")
                continue

            # If no matchers, take the first non-empty secret
            if matchers is None or is_nothing(matchers):
                self.logger.warning("No matchers provided, taking the first non-empty secret found")
                secret_data = matching_secret_data
                continue

            # Check matchers against the secret data
            found_match = False
            for k, v in matchers.items():
                datum = matching_secret_data.get(k)
                if datum == v:
                    self.logger.info(f"Matched {safe_secret_path} on matcher {_safe_log_text(k)}")
                    found_match = True
                    break

            if found_match:
                secret_data = matching_secret_data

        return self.extend_result(secret_data) if secret_data is not None else None

    @capability("write_secret", kind="secrets", aliases=("put_file",), description="Write one Vault secret.")
    def write_secret(
        self,
        path: str,
        data: dict[str, Any],
        mount_point: str = "secret",
    ) -> bool:
        """Write a secret to Vault.

        Args:
            path: Path to write the secret.
            data: Secret data dict.
            mount_point: KV engine mount point (default: "secret").

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.vault_client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data,
                mount_point=mount_point,
            )
            self.logger.info(f"Wrote secret to {_safe_ref_text(path)}")
            return True
        except VaultError as e:
            self.logger.error(  # noqa: TRY400 - traceback can expose raw Vault secret paths.
                f"Failed to write secret {_safe_ref_text(path)}: {_safe_log_text(e, path, data)}"
            )
            return False

    # ---------------------------------------------------------------------
    # Vault AWS IAM helpers
    # ---------------------------------------------------------------------

    def list_aws_iam_roles(
        self,
        mount_point: str = "aws",
        prefix: str | None = None,
    ) -> ExtendedList[ExtendedString]:
        """List AWS IAM roles configured in Vault's AWS secrets engine.

        Args:
            mount_point: AWS secrets engine mount point (default: "aws").
            prefix: Optional prefix filter for role names.

        Returns:
            List of role names available for credential generation.
        """
        self._validate_mount_point(mount_point)

        client = self.vault_client
        aws_secrets = client.secrets.aws

        try:
            response = aws_secrets.list_roles(mount_point=mount_point)
        except VaultError as e:
            self.logger.warning(
                f"Failed to list AWS IAM roles from mount {_safe_ref_text(mount_point)}: "
                f"{_safe_log_text(e, mount_point)}"
            )
            return self.extend_result([])

        role_names = response.get("data", {}).get("keys", []) or []
        if prefix:
            role_names = [role for role in role_names if role.startswith(prefix)]

        self.logger.info(f"Found {len(role_names)} AWS IAM roles under mount {_safe_ref_text(mount_point)}")
        return self.extend_result(role_names)

    def get_aws_iam_role(
        self,
        role_name: str,
        mount_point: str = "aws",
    ) -> ExtendedDict | None:
        """Retrieve details about a specific AWS IAM role configured in Vault.

        Args:
            role_name: Name of the role to fetch.
            mount_point: AWS secrets engine mount point (default: "aws").

        Returns:
            Dict containing the role configuration, or None if not found.
        """
        if is_nothing(role_name):
            msg = "role_name is required"
            raise ValueError(msg)

        self._validate_mount_point(mount_point)

        try:
            response = self.vault_client.secrets.aws.read_role(name=role_name, mount_point=mount_point)
        except VaultError as e:
            self.logger.warning(
                f"Failed to read AWS IAM role {_safe_ref_text(role_name)}: {_safe_log_text(e, role_name)}"
            )
            return None

        role_data = response.get("data")
        if is_nothing(role_data):
            self.logger.warning(f"AWS IAM role {_safe_ref_text(role_name)} exists but returned no data")
            return None

        return self.extend_result(role_data)

    def generate_aws_credentials(
        self,
        role_name: str,
        mount_point: str = "aws",
        ttl: str | None = None,
        credential_type: str | None = None,
    ) -> ExtendedDict:
        """Generate AWS credentials via Vault's AWS secrets engine.

        Args:
            role_name: AWS role configured in Vault.
            mount_point: AWS secrets engine mount point (default: "aws").
            ttl: Optional TTL override (e.g., "1h").
            credential_type: Optional credential type override (e.g., "sts").

        Returns:
            Dict of generated credential data (e.g., AccessKeyId, SecretAccessKey, SessionToken).

        Raises:
            ValueError: If role_name is empty or mount_point is invalid.
            RuntimeError: If Vault fails to return credentials.
        """
        if is_nothing(role_name):
            msg = "role_name is required"
            raise ValueError(msg)

        self._validate_mount_point(mount_point)

        aws_secrets = self.vault_client.secrets.aws
        generate_kwargs: dict[str, Any] = {}
        if ttl:
            generate_kwargs["ttl"] = ttl
        if credential_type:
            generate_kwargs["type"] = credential_type

        try:
            response = aws_secrets.generate_credentials(name=role_name, mount_point=mount_point, **generate_kwargs)
        except VaultError as e:
            safe_role_name = _safe_ref_text(role_name)
            self.logger.error(  # noqa: TRY400 - traceback can expose raw Vault role names.
                f"Failed to generate AWS credentials for role {safe_role_name}: "
                f"{_safe_log_text(e, role_name, mount_point, generate_kwargs)}"
            )
            raise RuntimeError(f"Failed to generate AWS credentials for role {safe_role_name}") from None

        credentials = response.get("data") or {}
        if not credentials:
            raise RuntimeError(f"Vault returned empty credentials for role {_safe_ref_text(role_name)}")

        self.logger.info(f"Generated AWS credentials for role {_safe_ref_text(role_name)}")
        return self.extend_result(credentials)


__all__ = [
    # Core connector
    "VaultConnector",
]
