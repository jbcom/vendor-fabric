"""Steam ``EResult`` status codes.

Steam signals the outcome of an ``IAuthenticationService`` call in the
``x-eresult`` response header rather than in the JSON body. A failed
credential check, for example, returns ``HTTP 200`` with a body of
``{"response": {}}`` and ``x-eresult: 5``. Callers that inspect only the
status code or the body therefore see a "successful" empty response.

This module maps the subset of codes the login flow can produce onto an
enum with human-readable messages.
"""

from __future__ import annotations

from enum import IntEnum


class EResult(IntEnum):
    """Steam API result codes relevant to the authentication flow."""

    INVALID = 0
    OK = 1
    FAIL = 2
    NO_CONNECTION = 3
    INVALID_PASSWORD = 5
    LOGGED_IN_ELSEWHERE = 6
    INVALID_PROTOCOL_VERSION = 7
    INVALID_PARAM = 8
    FILE_NOT_FOUND = 9
    BUSY = 10
    INVALID_STATE = 11
    INVALID_NAME = 12
    INVALID_EMAIL = 13
    ACCESS_DENIED = 15
    TIMEOUT = 16
    BANNED = 17
    ACCOUNT_NOT_FOUND = 18
    INVALID_STEAM_ID = 19
    SERVICE_UNAVAILABLE = 20
    NOT_LOGGED_ON = 21
    PENDING = 22
    ENCRYPTION_FAILURE = 23
    INSUFFICIENT_PRIVILEGE = 24
    LIMIT_EXCEEDED = 25
    REVOKED = 26
    EXPIRED = 27
    ALREADY_REDEEMED = 28
    DUPLICATE_REQUEST = 29
    ALREADY_OWNED = 30
    IP_NOT_FOUND = 31
    PERSIST_FAILED = 32
    LOCKING_FAILED = 33
    RATE_LIMIT_EXCEEDED = 84
    ACCOUNT_LOGIN_DENIED_NEED_TWO_FACTOR = 85
    TWO_FACTOR_CODE_MISMATCH = 88
    TWO_FACTOR_ACTIVATION_CODE_MISMATCH = 89

    @property
    def is_ok(self) -> bool:
        """Whether the result represents success."""
        return self is EResult.OK

    @property
    def message(self) -> str:
        """Human-readable description of the result."""
        return _MESSAGES.get(self, self.name.replace("_", " ").title())


_MESSAGES: dict[EResult, str] = {
    EResult.OK: "Success.",
    EResult.FAIL: "Generic failure.",
    EResult.INVALID_PASSWORD: "Incorrect account name or password.",
    EResult.ACCOUNT_NOT_FOUND: "No Steam account with that name exists.",
    EResult.ACCESS_DENIED: "Access denied.",
    EResult.BANNED: "This account is banned.",
    EResult.TIMEOUT: "The request timed out.",
    EResult.SERVICE_UNAVAILABLE: "Steam is temporarily unavailable.",
    EResult.RATE_LIMIT_EXCEEDED: "Too many attempts. Wait before retrying.",
    EResult.ACCOUNT_LOGIN_DENIED_NEED_TWO_FACTOR: "A Steam Guard code is required.",
    EResult.TWO_FACTOR_CODE_MISMATCH: "The Steam Guard code was incorrect.",
    EResult.EXPIRED: "The login session expired before it was confirmed.",
    EResult.INVALID_PARAM: "Steam rejected the request parameters.",
}


def parse_eresult(raw: str | int | None) -> EResult:
    """Coerce an ``x-eresult`` header value into an :class:`EResult`.

    Args:
        raw: Header value, which may be absent or non-numeric.

    Returns:
        The matching :class:`EResult`, or :attr:`EResult.INVALID` when the
        value is missing or unrecognized.
    """
    if raw is None:
        return EResult.INVALID
    try:
        return EResult(int(raw))
    except (TypeError, ValueError):
        return EResult.INVALID


__all__ = ["EResult", "parse_eresult"]
