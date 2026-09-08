"""Tests for SteamConnector."""

from __future__ import annotations

import httpx
import pytest

from vendor_fabric.steam import (
    RedemptionResult,
    SteamAuthError,
    SteamConnector,
    SteamSession,
    describe_redemption,
    is_valid_key,
)


VALID_KEY = "AAAAA-BBBBB-CCCCC"


def _session() -> SteamSession:
    """Build an authenticated-looking session."""
    return SteamSession(
        steam_id="76561197960287930",
        access_token="access",
        refresh_token="refresh",
        cookies={
            "store.steampowered.com": {"sessionid": "store-id", "steamLoginSecure": "secure"},
            "steamcommunity.com": {"sessionid": "community-id"},
        },
    )


def _connector(handler) -> SteamConnector:
    """Build a connector whose HTTP client is backed by a mock transport."""
    connector = SteamConnector(account_name="user", password="pw")
    connector._http = httpx.Client(transport=httpx.MockTransport(handler))
    connector.restore_session(_session())
    return connector


class TestKeyValidation:
    """Tests for Steam product-key shape validation."""

    @pytest.mark.parametrize("key", ["AAAAA-BBBBB-CCCCC", "12345-ABCDE-67890", "a1b2c-D3f4G-h5J6k"])
    def test_accepts_well_formed_keys(self, key):
        assert is_valid_key(key)

    @pytest.mark.parametrize(
        ("key", "shape"),
        [
            ("QQQQQ-WWWWW-EEEEE-RRRRR-TTTTT", "five groups, as Humble bundle keys use"),
            ("AAAAA-BBBBB-CCCCC-DDDDD", "four groups"),
            ("QQQQ-WWWW-EEEE-RRRR", "four groups of four, as some titles use"),
            ("QQQQWWWWEEEERRRR", "undashed, as some publishers issue"),
        ],
    )
    def test_accepts_the_other_shapes_steam_issues(self, key, shape):
        """Rejecting these discards keys that would have activated.

        Found against a real 1,053-key Humble library: two keys were being
        skipped permanently because only the three-group form was accepted.
        """
        assert is_valid_key(key), shape

    @pytest.mark.parametrize(
        "key",
        [
            "",
            "AAAAA-BBBBB",
            "AAA-BBB-CCC",
            "AAAAA_BBBBB_CCCCC",
            "AAAAA-BBBBB-CCCC!",
            None,
            12345,
            ["AAAAA-BBBBB-CCCCC"],
        ],
    )
    def test_rejects_malformed_keys(self, key):
        assert not is_valid_key(key)

    def test_tolerates_surrounding_whitespace(self):
        assert is_valid_key("  AAAAA-BBBBB-CCCCC  ")

    @pytest.mark.parametrize(
        "link",
        [
            "https://www.humblebundle.com/gift?key=Fuf4vTFqh7rYyt4b",
            "https://humblebundle.com/gift",
        ],
    )
    def test_rejects_gift_links(self, link):
        """Humble stores these in the same field as real keys.

        Sending one to Steam spends one of about ten failed activations an
        hour, so widening the accepted shapes must not let them through.
        """
        assert not is_valid_key(link)


class TestRedemptionResult:
    """Tests for redemption result codes."""

    def test_coerces_known_code(self):
        assert RedemptionResult.coerce(15) is RedemptionResult.DUPLICATE_ACTIVATION_CODE

    def test_missing_code_is_unknown_not_rate_limited(self):
        """A missing detail code must not be mistaken for a rate limit.

        The original implementation defaulted to 53 (rate limited), which sent
        callers into an unbounded retry loop on any unexpected failure.
        """
        assert RedemptionResult.coerce(None) is RedemptionResult.UNKNOWN
        assert RedemptionResult.coerce(None) is not RedemptionResult.RATE_LIMITED

    def test_unrecognized_code_is_unknown(self):
        assert RedemptionResult.coerce(9999) is RedemptionResult.UNKNOWN

    def test_already_owned_classification(self):
        assert RedemptionResult.ALREADY_OWNED.is_already_owned
        assert RedemptionResult.DUPLICATE_ACTIVATION_CODE.is_already_owned
        assert not RedemptionResult.BAD_ACTIVATION_CODE.is_already_owned

    def test_only_rate_limit_is_retryable(self):
        assert RedemptionResult.RATE_LIMITED.is_retryable
        assert not RedemptionResult.UNKNOWN.is_retryable

    def test_every_member_has_a_description(self):
        for member in RedemptionResult:
            assert describe_redemption(member)


class TestOwnership:
    """Tests for library ownership queries."""

    def test_lists_owned_apps(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "dynamicstore" in request.url.path:
                return httpx.Response(200, json={"rgOwnedApps": [220], "rgOwnedPackages": []})
            return httpx.Response(
                200,
                json={"applist": {"apps": [{"appid": 220, "name": "Half-Life 2"}, {"appid": 1, "name": "Other"}]}},
            )

        with _connector(handler) as connector:
            owned = connector.list_owned_apps()

        assert owned == {220: "Half-Life 2"}

    def test_owns_app(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "dynamicstore" in request.url.path:
                return httpx.Response(200, json={"rgOwnedApps": [220]})
            return httpx.Response(200, json={"applist": {"apps": [{"appid": 220, "name": "Half-Life 2"}]}})

        with _connector(handler) as connector:
            assert connector.owns_app(220)
            assert not connector.owns_app(999)

    def test_empty_library_short_circuits(self):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, json={"rgOwnedApps": [], "rgOwnedPackages": []})

        with _connector(handler) as connector:
            assert connector.list_owned_apps() == {}

        # The (large) app list must not be fetched when nothing is owned.
        assert not any("GetAppList" in path for path in calls)

    def test_requires_authentication(self):
        connector = SteamConnector(account_name="user", password="pw")
        with pytest.raises(SteamAuthError, match="Not signed in"):
            connector.list_owned_apps()
        connector.close()


class TestRedemption:
    """Tests for product-key redemption."""

    def test_successful_redemption_reports_items(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "success": 1,
                    "purchase_receipt_info": {"line_items": [{"line_item_description": "Portal 2"}]},
                },
            )

        with _connector(handler) as connector:
            outcome = connector.redeem_key(VALID_KEY)

        assert outcome["success"] is True
        assert outcome["result"] is RedemptionResult.OK
        assert outcome["items"] == ["Portal 2"]

    def test_already_owned_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": 0, "purchase_result_details": 9})

        with _connector(handler) as connector:
            outcome = connector.redeem_key(VALID_KEY)

        assert outcome["success"] is False
        assert outcome["result"] is RedemptionResult.ALREADY_OWNED

    def test_falls_back_to_receipt_result_detail(self):
        """Steam sometimes omits purchase_result_details."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": 0, "purchase_receipt_info": {"result_detail": 14}})

        with _connector(handler) as connector:
            outcome = connector.redeem_key(VALID_KEY)

        assert outcome["result"] is RedemptionResult.BAD_ACTIVATION_CODE

    def test_absent_detail_is_unknown_not_rate_limited(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": 0})

        with _connector(handler) as connector:
            outcome = connector.redeem_key(VALID_KEY)

        assert outcome["result"] is RedemptionResult.UNKNOWN

    def test_posts_store_scoped_session_id(self):
        """The store sessionid must be sent, not the community one."""
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"success": 1, "purchase_receipt_info": {"line_items": []}})

        with _connector(handler) as connector:
            connector.redeem_key(VALID_KEY)

        assert "store-id" in captured["body"]
        assert "community-id" not in captured["body"]

    def test_rejects_malformed_key_before_calling_steam(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
            raise AssertionError("Steam must not be contacted for a malformed key")

        with _connector(handler) as connector, pytest.raises(ValueError, match="valid Steam product key"):
            connector.redeem_key("not-a-key")

    def test_batch_stops_on_rate_limit(self):
        """Further attempts during a cooldown only deepen it."""
        attempts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request.content.decode())
            return httpx.Response(200, json={"success": 0, "purchase_result_details": 53})

        with _connector(handler) as connector:
            results = connector.redeem_keys([VALID_KEY, "DDDDD-EEEEE-FFFFF", "GGGGG-HHHHH-IIIII"])

        assert len(attempts) == 1
        assert len(results) == 1
        assert results[0]["result"] is RedemptionResult.RATE_LIMITED

    def test_batch_continues_past_ordinary_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": 0, "purchase_result_details": 9})

        with _connector(handler) as connector:
            results = connector.redeem_keys([VALID_KEY, "DDDDD-EEEEE-FFFFF"])

        assert len(results) == 2

    def test_network_failure_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection reset")

        with _connector(handler) as connector, pytest.raises(SteamAuthError, match="redemption failed"):
            connector.redeem_key(VALID_KEY)

    def test_missing_store_session_id_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
            raise AssertionError("Steam must not be contacted without a session id")

        connector = SteamConnector(account_name="user", password="pw")
        connector._http = httpx.Client(transport=httpx.MockTransport(handler))
        connector.restore_session(SteamSession(steam_id="1", access_token="a", refresh_token="r"))

        with pytest.raises(SteamAuthError, match="store session id"):
            connector.redeem_key(VALID_KEY)
        connector.close()


class TestAuthenticationState:
    """Tests for session lifecycle behavior."""

    def test_requires_credentials_to_authenticate(self):
        connector = SteamConnector(account_name=None, password=None)
        with pytest.raises(SteamAuthError, match="required to authenticate"):
            connector.authenticate()
        connector.close()

    def test_is_authenticated_false_without_session(self):
        connector = SteamConnector(account_name="user", password="pw")
        assert not connector.is_authenticated()
        connector.close()

    def test_is_authenticated_detects_redirect_to_login(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://store.steampowered.com/login/"})

        with _connector(handler) as connector:
            assert not connector.is_authenticated()

    def test_is_authenticated_true_when_page_served(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>Register key</html>")

        with _connector(handler) as connector:
            assert connector.is_authenticated()

    def test_is_authenticated_false_on_network_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        with _connector(handler) as connector:
            assert not connector.is_authenticated()

    def test_restore_session_exposes_session(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - unused
            return httpx.Response(200, json={})

        with _connector(handler) as connector:
            assert connector.session is not None
            assert connector.session.steam_id == "76561197960287930"


class TestMalformedSteamResponses:
    """Steam's payloads are not guaranteed to be well-formed."""

    def test_app_list_entries_missing_fields_are_skipped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "dynamicstore" in request.url.path:
                return httpx.Response(200, json={"rgOwnedApps": [220, 440]})
            return httpx.Response(
                200,
                json={
                    "applist": {
                        "apps": [
                            {"appid": 220, "name": "Half-Life 2"},
                            {"appid": 440},  # no name
                            "not-a-dict",
                        ]
                    }
                },
            )

        with _connector(handler) as connector:
            assert connector.list_owned_apps() == {220: "Half-Life 2"}

    def test_non_dict_line_items_are_skipped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "success": 1,
                    "purchase_receipt_info": {"line_items": [{"line_item_description": "Portal 2"}, "junk", {}]},
                },
            )

        with _connector(handler) as connector:
            assert connector.redeem_key(VALID_KEY)["items"] == ["Portal 2"]
