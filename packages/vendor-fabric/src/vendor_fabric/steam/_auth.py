"""Steam web authentication.

Implements Steam's ``IAuthenticationService`` login flow directly over
HTTPS. Steam serves this API as JSON, so no protobuf handling is required:

1. ``GetPasswordRSAPublicKey`` returns a per-account RSA modulus/exponent.
2. The password is encrypted with PKCS#1 v1.5 under that key.
3. ``BeginAuthSessionViaCredentials`` opens a login session.
4. Steam Guard codes are submitted via ``UpdateAuthSessionWithSteamGuardCode``.
5. ``PollAuthSessionStatus`` returns the refresh token once confirmed.
6. ``login.steampowered.com/jwt/finalizelogin`` exchanges the refresh token
   for the per-domain cookies the Steam store expects.

Failures are reported in the ``x-eresult`` response header rather than the
HTTP status or body; see :mod:`vendor_fabric.steam._eresult`.
"""

from __future__ import annotations

import base64
import time

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vendor_fabric._optional import require_extra
from vendor_fabric.steam._eresult import EResult, parse_eresult


if TYPE_CHECKING:
    import httpx


AUTH_BASE = "https://api.steampowered.com/IAuthenticationService"
LOGIN_BASE = "https://login.steampowered.com"
STEAM_COOKIE_DOMAINS = (
    "store.steampowered.com",
    "help.steampowered.com",
    "steamcommunity.com",
)

DEFAULT_TIMEOUT = 30.0
_POLL_TIMEOUT = 180.0


class SteamAuthError(RuntimeError):
    """Raised when Steam rejects or cannot complete a login."""

    def __init__(self, message: str, result: EResult = EResult.FAIL) -> None:
        super().__init__(message)
        self.result = result


class SteamGuardRequiredError(SteamAuthError):
    """Raised when a login needs a Steam Guard code that was not supplied.

    Attributes:
        allowed_confirmations: Confirmation type codes Steam will accept.
    """

    def __init__(self, message: str, allowed_confirmations: tuple[int, ...] = ()) -> None:
        super().__init__(message, EResult.ACCOUNT_LOGIN_DENIED_NEED_TWO_FACTOR)
        self.allowed_confirmations = allowed_confirmations


# Steam Guard confirmation types returned in ``allowed_confirmations``.
CONFIRM_NONE = 1
CONFIRM_EMAIL_CODE = 2
CONFIRM_DEVICE_CODE = 3
CONFIRM_DEVICE_CONFIRMATION = 4


@dataclass(slots=True)
class SteamSession:
    """An authenticated Steam web session.

    Attributes:
        steam_id: The 64-bit Steam ID of the signed-in account.
        access_token: Short-lived JWT used for API calls.
        refresh_token: Long-lived JWT used to mint new access tokens.
        cookies: Per-domain cookie jar contents keyed by domain.
    """

    steam_id: str
    access_token: str
    refresh_token: str
    cookies: dict[str, dict[str, str]] = field(default_factory=dict)

    def session_id(self, domain: str = "store.steampowered.com") -> str | None:
        """Return the ``sessionid`` cookie scoped to ``domain``.

        Steam issues a *different* ``sessionid`` per domain. Flattening the
        jar and taking whichever value survives yields a token that the
        target domain rejects, so callers must ask for the domain they are
        about to post to.

        Args:
            domain: Cookie domain to read.

        Returns:
            The session id, or ``None`` when the domain has no cookie.
        """
        return self.cookies.get(domain, {}).get("sessionid")


def _encrypt_password(password: str, modulus_hex: str, exponent_hex: str) -> str:
    """Encrypt ``password`` with Steam's per-account RSA public key.

    Args:
        password: Plaintext account password.
        modulus_hex: RSA modulus as a hex string.
        exponent_hex: RSA exponent as a hex string.

    Returns:
        Base64-encoded ciphertext.
    """
    pkcs1_15 = require_extra("Cryptodome.Cipher.PKCS1_v1_5", "steam")
    rsa = require_extra("Cryptodome.PublicKey.RSA", "steam")

    key = rsa.construct((int(modulus_hex, 16), int(exponent_hex, 16)))
    ciphertext = pkcs1_15.new(key).encrypt(password.encode("utf-8"))
    return base64.b64encode(ciphertext).decode("ascii")


def _check(response: httpx.Response, action: str) -> dict[str, Any]:
    """Validate a Steam auth response and return its ``response`` payload.

    Args:
        response: The HTTP response to validate.
        action: Human-readable description used in error messages.

    Returns:
        The decoded ``response`` object.

    Raises:
        SteamAuthError: If Steam reported a non-OK ``x-eresult``.
    """
    result = parse_eresult(response.headers.get("x-eresult"))
    # Steam omits x-eresult on some success paths; absence is not failure.
    if result not in (EResult.OK, EResult.INVALID):
        detail = response.headers.get("x-error_message") or result.message
        raise SteamAuthError(f"{action}: {detail}", result)

    if response.status_code >= 400:
        raise SteamAuthError(f"{action}: Steam returned HTTP {response.status_code}", result)

    try:
        body = response.json()
    except ValueError as exc:
        raise SteamAuthError(f"{action}: Steam returned a non-JSON response") from exc

    payload = body.get("response") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        raise SteamAuthError(f"{action}: unexpected Steam response shape")
    return payload


def _finalize(client: httpx.Client, refresh_token: str, steam_id: str) -> dict[str, dict[str, str]]:
    """Exchange a refresh token for per-domain Steam cookies.

    Args:
        client: HTTP client to use.
        refresh_token: Refresh token from a confirmed login.
        steam_id: The account's 64-bit Steam ID.

    Returns:
        Cookie jars keyed by domain.

    Raises:
        SteamAuthError: If Steam declines to issue cookies.
    """
    session_id = base64.b64encode(f"{steam_id}{time.time()}".encode()).decode("ascii")[:24]

    response = client.post(
        f"{LOGIN_BASE}/jwt/finalizelogin",
        data={"nonce": refresh_token, "sessionid": session_id, "redir": "https://store.steampowered.com/login"},
        timeout=DEFAULT_TIMEOUT,
    )
    body = response.json() if response.content else {}
    if not body.get("transfer_info"):
        raise SteamAuthError("Steam did not return login transfer info")

    cookies: dict[str, dict[str, str]] = {}
    for transfer in body["transfer_info"]:
        url = transfer.get("url", "")
        params = dict(transfer.get("params", {}))
        params["steamID"] = steam_id
        transfer_response = client.post(url, data=params, timeout=DEFAULT_TIMEOUT)
        for cookie_name, cookie_value in transfer_response.cookies.items():
            domain = url.split("/")[2]
            cookies.setdefault(domain, {})[cookie_name] = cookie_value

    for jar in cookies.values():
        jar.setdefault("sessionid", session_id)

    if not cookies:
        raise SteamAuthError("Steam issued no session cookies")
    return cookies


def login(
    client: httpx.Client,
    account_name: str,
    password: str,
    *,
    steam_guard_code: str | None = None,
    poll_timeout: float = _POLL_TIMEOUT,
) -> SteamSession:
    """Sign in to Steam and return an authenticated session.

    Args:
        client: HTTP client used for every request in the flow.
        account_name: Steam account name (not the display/persona name).
        password: Account password. Encrypted before transmission.
        steam_guard_code: Steam Guard code, when one is already known.
        poll_timeout: Seconds to wait for mobile-app confirmation.

    Returns:
        The authenticated :class:`SteamSession`.

    Raises:
        SteamAuthError: If credentials are rejected or the login expires.
        SteamGuardRequiredError: If a Steam Guard code is needed but absent.
    """
    key_payload = _check(
        client.get(
            f"{AUTH_BASE}/GetPasswordRSAPublicKey/v1/",
            params={"account_name": account_name},
            timeout=DEFAULT_TIMEOUT,
        ),
        "Could not begin Steam login",
    )

    encrypted = _encrypt_password(password, key_payload["publickey_mod"], key_payload["publickey_exp"])

    begin = _check(
        client.post(
            f"{AUTH_BASE}/BeginAuthSessionViaCredentials/v1/",
            data={
                "account_name": account_name,
                "encrypted_password": encrypted,
                "encryption_timestamp": key_payload["timestamp"],
                "persistence": "1",
                "website_id": "Community",
            },
            timeout=DEFAULT_TIMEOUT,
        ),
        "Steam rejected the sign-in",
    )

    client_id = begin.get("client_id")
    request_id = begin.get("request_id")
    if not client_id or not request_id:
        raise SteamAuthError("Steam did not open a login session", EResult.INVALID_PASSWORD)

    steam_id = str(begin.get("steamid", ""))
    confirmations = tuple(
        int(entry["confirmation_type"])
        for entry in begin.get("allowed_confirmations", [])
        if "confirmation_type" in entry
    )
    needs_code = any(c in (CONFIRM_EMAIL_CODE, CONFIRM_DEVICE_CODE) for c in confirmations)

    if needs_code:
        if not steam_guard_code:
            raise SteamGuardRequiredError("Steam Guard code required", confirmations)
        _check(
            client.post(
                f"{AUTH_BASE}/UpdateAuthSessionWithSteamGuardCode/v1/",
                data={
                    "client_id": client_id,
                    "steamid": steam_id,
                    "code": steam_guard_code.strip().upper(),
                    "code_type": str(
                        CONFIRM_DEVICE_CODE if CONFIRM_DEVICE_CODE in confirmations else CONFIRM_EMAIL_CODE
                    ),
                },
                timeout=DEFAULT_TIMEOUT,
            ),
            "Steam rejected the Steam Guard code",
        )

    deadline = time.monotonic() + poll_timeout
    interval = float(begin.get("interval", 5) or 5)
    while True:
        poll = _check(
            client.post(
                f"{AUTH_BASE}/PollAuthSessionStatus/v1/",
                data={"client_id": client_id, "request_id": request_id},
                timeout=DEFAULT_TIMEOUT,
            ),
            "Steam login could not be confirmed",
        )
        if poll.get("refresh_token"):
            break
        if poll.get("had_remote_interaction") is False and time.monotonic() > deadline:
            raise SteamAuthError("Timed out waiting for Steam login confirmation", EResult.EXPIRED)
        if time.monotonic() > deadline:
            raise SteamAuthError("Timed out waiting for Steam login confirmation", EResult.EXPIRED)
        time.sleep(interval)

    refresh_token = str(poll["refresh_token"])
    access_token = str(poll.get("access_token", ""))
    steam_id = str(poll.get("steamid") or steam_id)

    return SteamSession(
        steam_id=steam_id,
        access_token=access_token,
        refresh_token=refresh_token,
        cookies=_finalize(client, refresh_token, steam_id),
    )


__all__ = [
    "AUTH_BASE",
    "CONFIRM_DEVICE_CODE",
    "CONFIRM_DEVICE_CONFIRMATION",
    "CONFIRM_EMAIL_CODE",
    "LOGIN_BASE",
    "STEAM_COOKIE_DOMAINS",
    "SteamAuthError",
    "SteamGuardRequiredError",
    "SteamSession",
    "login",
]
