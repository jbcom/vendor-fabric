"""Steam product-key redemption result codes.

Steam reports redemption outcomes as ``purchase_result_details`` integers.
Distinguishing them matters operationally: Steam rate-limits roughly 50
successful activations per hour but only 10 *failed* ones, so treating an
unknown failure as a rate limit (or vice versa) either stalls a run for an
hour or burns the much scarcer failure budget.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class RedemptionResult(IntEnum):
    """Outcome of a Steam product-key activation."""

    OK = 1
    BAD_ACTIVATION_CODE = 14
    DUPLICATE_ACTIVATION_CODE = 15
    REGION_LOCKED = 13
    ALREADY_OWNED = 9
    BASE_GAME_REQUIRED = 24
    PS3_ACTIVATION_REQUIRED = 36
    WALLET_CODE = 50
    RATE_LIMITED = 53
    UNKNOWN = 0

    @classmethod
    def coerce(cls, value: Any) -> RedemptionResult:
        """Convert a raw Steam detail code into a member.

        Args:
            value: Raw ``purchase_result_details`` value.

        Returns:
            The matching member, or :attr:`UNKNOWN` when unrecognized.

        Note:
            An absent code is *not* assumed to be a rate limit. The original
            implementation defaulted missing codes to ``53``, which made any
            unexpected failure look like a cooldown and sent callers into an
            unbounded retry loop.
        """
        if value is None:
            return cls.UNKNOWN
        try:
            return cls(int(value))
        except (TypeError, ValueError):
            return cls.UNKNOWN

    @property
    def is_already_owned(self) -> bool:
        """Whether the failure means the account already has the product."""
        return self in (RedemptionResult.ALREADY_OWNED, RedemptionResult.DUPLICATE_ACTIVATION_CODE)

    @property
    def is_retryable(self) -> bool:
        """Whether retrying later could succeed."""
        return self is RedemptionResult.RATE_LIMITED


_DESCRIPTIONS: dict[RedemptionResult, str] = {
    RedemptionResult.OK: "Key redeemed successfully.",
    RedemptionResult.BAD_ACTIVATION_CODE: (
        "The product code is not valid. Check for mistyped characters — I, L and 1 "
        "look alike, as do V and Y, and 0 and O."
    ),
    RedemptionResult.DUPLICATE_ACTIVATION_CODE: (
        "The product code has already been activated by a different Steam account."
    ),
    RedemptionResult.REGION_LOCKED: "This product is not available for purchase in this country.",
    RedemptionResult.ALREADY_OWNED: "This Steam account already owns the products in this offer.",
    RedemptionResult.BASE_GAME_REQUIRED: (
        "This code requires ownership of another product. Activate the base game first."
    ),
    RedemptionResult.PS3_ACTIVATION_REQUIRED: (
        "This code must first be played and registered on a PlayStation®3 system."
    ),
    RedemptionResult.WALLET_CODE: (
        "This is a Steam Gift Card or Wallet code. Redeem it at "
        "https://store.steampowered.com/account/redeemwalletcode"
    ),
    RedemptionResult.RATE_LIMITED: (
        "Too many recent activation attempts from this account or IP address. "
        "Steam allows roughly 50 activations and only 10 failures per hour."
    ),
    RedemptionResult.UNKNOWN: (
        "Steam reported an unexpected error and the code was not redeemed. "
        "Wait 30 minutes and try again."
    ),
}


def describe_redemption(result: RedemptionResult) -> str:
    """Return a human-readable explanation of a redemption result.

    Args:
        result: The result to describe.

    Returns:
        An explanatory sentence suitable for display to a user.
    """
    return _DESCRIPTIONS.get(result, _DESCRIPTIONS[RedemptionResult.UNKNOWN])


__all__ = ["RedemptionResult", "describe_redemption"]
