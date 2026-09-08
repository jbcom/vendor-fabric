"""Steam connector: authentication, library ownership, and key redemption."""

from __future__ import annotations

import re

from typing import TYPE_CHECKING, Any, ClassVar, Self

import httpx

from extended_data.containers import ExtendedDict, ExtendedList
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.base import ConnectorBase
from vendor_fabric.capabilities import capability
from vendor_fabric.steam._auth import (
    DEFAULT_TIMEOUT,
    SteamAuthError,
    SteamSession,
    login,
)
from vendor_fabric.steam._redemption import RedemptionResult, describe_redemption


if TYPE_CHECKING:
    from extended_data.logging import Logging


STORE_BASE = "https://store.steampowered.com"
STEAM_USERDATA_API = f"{STORE_BASE}/dynamicstore/userdata/"
STEAM_REDEEM_API = f"{STORE_BASE}/account/ajaxregisterkey/"
STEAM_KEYS_PAGE = f"{STORE_BASE}/account/registerkey"
STEAM_APP_LIST_API = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"

# Steam product keys are three dash-separated groups of five characters.
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]{5}(-[A-Za-z0-9]{5}){2}$")


def is_valid_key(key: object) -> bool:
    """Report whether ``key`` looks like a Steam product key.

    Args:
        key: Candidate value of any type.

    Returns:
        ``True`` when the value matches ``AAAAA-BBBBB-CCCCC``.
    """
    return isinstance(key, str) and bool(_KEY_PATTERN.match(key.strip()))


def _safe(value: Any, *sensitive: Any) -> str:
    """Redact credentials and keys from diagnostic text."""
    return redact_sensitive_text(value, values=[v for v in sensitive if v])


class SteamConnector(ConnectorBase):
    """Connector for the Steam storefront and account APIs.

    Authenticates against Steam's ``IAuthenticationService`` and exposes
    library ownership plus product-key redemption.

    Example:
        >>> connector = SteamConnector()  # doctest: +SKIP
        >>> connector.authenticate()  # doctest: +SKIP
        >>> owned = connector.list_owned_apps()  # doctest: +SKIP
    """

    BASE_URL: ClassVar[str] = STORE_BASE
    CONNECTOR_CATEGORY: ClassVar[str] = "gaming"
    CONNECTOR_CAPABILITIES: ClassVar[tuple[str, ...]] = ("library", "redemption")

    def __init__(
        self,
        account_name: str | None = None,
        password: str | None = None,
        *,
        steam_guard_code: str | None = None,
        session: SteamSession | None = None,
        logger: Logging | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the connector.

        Credentials are only required for :meth:`authenticate`; an existing
        :class:`SteamSession` may be supplied instead.

        Args:
            account_name: Steam account name. Falls back to ``STEAM_ACCOUNT_NAME``.
            password: Account password. Falls back to ``STEAM_PASSWORD``.
            steam_guard_code: Steam Guard code, when already known.
            session: A previously established session to reuse.
            logger: Optional logger.
            **kwargs: Forwarded to :class:`~vendor_fabric.base.ConnectorBase`.
        """
        super().__init__(logger=logger, **kwargs)
        self._account_name = account_name or self.get_input("STEAM_ACCOUNT_NAME", required=False)
        self._password = password or self.get_input("STEAM_PASSWORD", required=False)
        self._steam_guard_code = steam_guard_code
        self._session = session
        self._http = httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=False)

    # ------------------------------------------------------------------ auth

    @property
    def session(self) -> SteamSession | None:
        """The active Steam session, if authenticated."""
        return self._session

    def authenticate(self, steam_guard_code: str | None = None) -> SteamSession:
        """Sign in to Steam and retain the resulting session.

        Args:
            steam_guard_code: Steam Guard code, overriding the constructor value.

        Returns:
            The authenticated :class:`SteamSession`.

        Raises:
            SteamAuthError: If credentials are missing or rejected.
        """
        if not self._account_name or not self._password:
            raise SteamAuthError("Steam account name and password are required to authenticate")

        self._session = login(
            self._http,
            self._account_name,
            self._password,
            steam_guard_code=steam_guard_code or self._steam_guard_code,
        )
        self._apply_cookies(self._session)
        return self._session

    def restore_session(self, session: SteamSession) -> None:
        """Adopt a previously saved session.

        Args:
            session: Session to reuse.
        """
        self._session = session
        self._apply_cookies(session)

    def _apply_cookies(self, session: SteamSession) -> None:
        """Load a session's cookies into the HTTP client, preserving domains."""
        for domain, jar in session.cookies.items():
            for name, value in jar.items():
                self._http.cookies.set(name, value, domain=domain)

    def is_authenticated(self) -> bool:
        """Check whether the stored session is still accepted by Steam.

        Returns:
            ``True`` when Steam serves the key-registration page without
            redirecting to the login form.
        """
        if self._session is None:
            return False
        try:
            response = self._http.get(STEAM_KEYS_PAGE, timeout=DEFAULT_TIMEOUT)
        except httpx.HTTPError:
            return False
        return response.status_code not in (301, 302, 303, 307, 308)

    def _require_session(self) -> SteamSession:
        """Return the active session or raise."""
        if self._session is None:
            raise SteamAuthError("Not signed in to Steam; call authenticate() first")
        return self._session

    # --------------------------------------------------------------- library

    @capability("list_owned_apps", kind="library", aliases=("owned_apps",))
    def list_owned_apps(self) -> ExtendedDict:
        """List the Steam applications the signed-in account owns.

        Returns:
            Mapping of application id to application name.

        Raises:
            SteamAuthError: If the ownership data cannot be read.
        """
        self._require_session()
        try:
            userdata = self._http.get(STEAM_USERDATA_API, timeout=DEFAULT_TIMEOUT).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SteamAuthError(f"Could not read Steam library: {_safe(exc)}") from None

        owned_ids = set(userdata.get("rgOwnedApps", [])) | set(userdata.get("rgOwnedPackages", []))
        if not owned_ids:
            return self.extend_result({})

        try:
            applist = self._http.get(STEAM_APP_LIST_API, timeout=DEFAULT_TIMEOUT).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SteamAuthError(f"Could not read the Steam app list: {_safe(exc)}") from None

        apps = applist.get("applist", {}).get("apps", [])
        return self.extend_result(
            {int(app["appid"]): str(app["name"]) for app in apps if app.get("appid") in owned_ids}
        )

    @capability("owns_app", kind="library")
    def owns_app(self, app_id: int) -> bool:
        """Report whether the account owns a specific application.

        Args:
            app_id: Steam application id.

        Returns:
            ``True`` when the application is owned.
        """
        wanted = int(app_id)
        # Extended containers normalize keys to strings, so compare on both.
        return any(str(key) == str(wanted) for key in self.list_owned_apps())

    # ------------------------------------------------------------ redemption

    @capability("redeem_key", kind="redemption", aliases=("register_key",))
    def redeem_key(self, key: str) -> ExtendedDict:
        """Redeem a Steam product key on the signed-in account.

        Args:
            key: Product key in ``AAAAA-BBBBB-CCCCC`` form.

        Returns:
            Mapping with ``success``, ``result`` (a
            :class:`~vendor_fabric.steam.RedemptionResult`), ``detail``, and
            any ``items`` granted.

        Raises:
            SteamAuthError: If not signed in or Steam is unreachable.
            ValueError: If ``key`` is not a well-formed product key.
        """
        session = self._require_session()
        if not is_valid_key(key):
            raise ValueError("Not a valid Steam product key")

        session_id = session.session_id("store.steampowered.com")
        if not session_id:
            raise SteamAuthError("Steam session is missing its store session id")

        try:
            response = self._http.post(
                STEAM_REDEEM_API,
                data={"product_key": key.strip(), "sessionid": session_id},
                timeout=DEFAULT_TIMEOUT,
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SteamAuthError(f"Steam key redemption failed: {_safe(exc, key)}") from None

        return self.extend_result(self._interpret(payload))

    @staticmethod
    def _interpret(payload: dict[str, Any]) -> dict[str, Any]:
        """Translate Steam's redemption payload into a stable result shape."""
        if payload.get("success") == RedemptionResult.OK:
            receipt = payload.get("purchase_receipt_info") or {}
            items = [
                str(line.get("line_item_description", ""))
                for line in receipt.get("line_items", [])
                if line.get("line_item_description")
            ]
            return {
                "success": True,
                "result": RedemptionResult.OK,
                "detail": describe_redemption(RedemptionResult.OK),
                "items": items,
            }

        detail_code = payload.get("purchase_result_details")
        if detail_code is None:
            detail_code = (payload.get("purchase_receipt_info") or {}).get("result_detail")

        result = RedemptionResult.coerce(detail_code)
        return {
            "success": False,
            "result": result,
            "detail": describe_redemption(result),
            "items": [],
        }

    @capability("redeem_keys", kind="redemption")
    def redeem_keys(self, keys: list[str]) -> ExtendedList[ExtendedDict]:
        """Redeem several product keys in order.

        Redemption stops early when Steam signals rate limiting, since
        further attempts would only deepen the cooldown.

        Args:
            keys: Product keys to redeem.

        Returns:
            One result mapping per attempted key.
        """
        results: list[dict[str, Any]] = []
        for key in keys:
            outcome = dict(self.redeem_key(key))
            outcome["key"] = key
            results.append(outcome)
            if outcome["result"] is RedemptionResult.RATE_LIMITED:
                break
        return self.extend_result(results)

    # ------------------------------------------------------------- lifecycle

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> Self:
        """Enter a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client on context exit."""
        self.close()


__all__ = [
    "STEAM_APP_LIST_API",
    "STEAM_KEYS_PAGE",
    "STEAM_REDEEM_API",
    "STEAM_USERDATA_API",
    "SteamConnector",
    "is_valid_key",
]
