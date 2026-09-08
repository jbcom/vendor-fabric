"""Steam connector — authentication, library ownership, and key redemption.

Part of vendor-fabric, providing access to the Steam storefront and account
APIs. Steam's ``IAuthenticationService`` login flow is implemented directly
over HTTPS, so no third-party Steam SDK is required.

Usage:
    from vendor_fabric.steam import SteamConnector

    with SteamConnector(account_name="user", password="...") as steam:
        steam.authenticate(steam_guard_code="ABCDE")
        owned = steam.list_owned_apps()
        outcome = steam.redeem_key("AAAAA-BBBBB-CCCCC")

Sessions can be persisted and reused so that Steam Guard is not required on
every run:

    session = steam.session
    ...
    steam.restore_session(session)

Note:
    Steam rate-limits activations to roughly 50 per hour, and *failed*
    activations to only 10 per hour. Check ownership before redeeming so the
    scarce failure budget is not spent on keys the account already has.
"""

from __future__ import annotations

from vendor_fabric.steam._auth import (
    SteamAuthError,
    SteamGuardRequiredError,
    SteamSession,
    login,
)
from vendor_fabric.steam._connector import (
    STEAM_APP_LIST_API,
    STEAM_KEYS_PAGE,
    STEAM_REDEEM_API,
    STEAM_USERDATA_API,
    SteamConnector,
    is_valid_key,
)
from vendor_fabric.steam._eresult import EResult, parse_eresult
from vendor_fabric.steam._redemption import RedemptionResult, describe_redemption


__all__ = [
    "STEAM_APP_LIST_API",
    "STEAM_KEYS_PAGE",
    "STEAM_REDEEM_API",
    "STEAM_USERDATA_API",
    "EResult",
    "RedemptionResult",
    "SteamAuthError",
    "SteamConnector",
    "SteamGuardRequiredError",
    "SteamSession",
    "describe_redemption",
    "is_valid_key",
    "login",
    "parse_eresult",
]
