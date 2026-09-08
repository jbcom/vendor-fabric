"""Tests for the Steam authentication flow."""

from __future__ import annotations

import base64

import httpx
import pytest

from vendor_fabric.steam import (
    EResult,
    SteamAuthError,
    SteamGuardRequiredError,
    SteamSession,
    login,
    parse_eresult,
)
from vendor_fabric.steam._auth import _encrypt_password


# A small but valid RSA key pair so password encryption exercises real maths.
_MODULUS = (
    "c104093219a3dcf0193f83d18550718ebce220847220e8dc2cb59b7383710ee6"
    "74e8a150c89919bc616be5cf05055ea0a02db8f0f0b6f6efd9fd3601d94eb1f5"
    "fd196cad95b3ef644e2ed996c080f414bd4cceeda149daee0401a7d6208974e5"
    "1067f3120d221d5a49c4c06fe87a4dc7e74c61e5e565960ed8e166bbd42a683d"
)
_EXPONENT = "010001"


def _json(payload: object, *, eresult: int | None = 1, status: int = 200) -> httpx.Response:
    """Build a Steam-shaped JSON response."""
    headers = {} if eresult is None else {"x-eresult": str(eresult)}
    return httpx.Response(status, json={"response": payload}, headers=headers)


class TestParseEResult:
    """Tests for x-eresult header parsing."""

    def test_parses_known_code(self):
        assert parse_eresult("5") is EResult.INVALID_PASSWORD

    def test_missing_header_is_invalid(self):
        assert parse_eresult(None) is EResult.INVALID

    def test_unknown_code_is_invalid(self):
        assert parse_eresult("999999") is EResult.INVALID

    def test_non_numeric_is_invalid(self):
        assert parse_eresult("nonsense") is EResult.INVALID

    def test_ok_is_ok(self):
        assert EResult.OK.is_ok
        assert not EResult.INVALID_PASSWORD.is_ok

    def test_every_member_has_a_message(self):
        for member in EResult:
            assert member.message


class TestPasswordEncryption:
    """Tests for RSA password encryption."""

    def test_produces_base64_ciphertext(self):
        encrypted = _encrypt_password("hunter2", _MODULUS, _EXPONENT)
        assert base64.b64decode(encrypted)

    def test_ciphertext_is_not_the_plaintext(self):
        encrypted = _encrypt_password("hunter2", _MODULUS, _EXPONENT)
        assert "hunter2" not in encrypted

    def test_padding_randomizes_output(self):
        """PKCS#1 v1.5 padding must make repeated encryptions differ."""
        first = _encrypt_password("hunter2", _MODULUS, _EXPONENT)
        second = _encrypt_password("hunter2", _MODULUS, _EXPONENT)
        assert first != second


class TestLogin:
    """Tests for the end-to-end login flow."""

    @staticmethod
    def _client(handler) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_rejects_bad_password_via_header(self):
        """Steam signals bad credentials with HTTP 200 and x-eresult: 5."""

        def handler(request: httpx.Request) -> httpx.Response:
            if "GetPasswordRSAPublicKey" in request.url.path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            return _json({}, eresult=EResult.INVALID_PASSWORD)

        with self._client(handler) as client, pytest.raises(SteamAuthError) as excinfo:
            login(client, "user", "wrong-password")

        assert excinfo.value.result is EResult.INVALID_PASSWORD
        assert "Incorrect account name or password" in str(excinfo.value)

    def test_requires_steam_guard_code_when_demanded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "GetPasswordRSAPublicKey" in request.url.path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            return _json(
                {
                    "client_id": "cid",
                    "request_id": "rid",
                    "steamid": "76561197960287930",
                    "allowed_confirmations": [{"confirmation_type": 3}],
                }
            )

        with self._client(handler) as client, pytest.raises(SteamGuardRequiredError) as excinfo:
            login(client, "user", "correct-password")

        assert 3 in excinfo.value.allowed_confirmations

    def test_successful_login_returns_session(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "GetPasswordRSAPublicKey" in path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            if "BeginAuthSessionViaCredentials" in path:
                return _json(
                    {
                        "client_id": "cid",
                        "request_id": "rid",
                        "steamid": "76561197960287930",
                        "allowed_confirmations": [{"confirmation_type": 1}],
                        "interval": 0,
                    }
                )
            if "PollAuthSessionStatus" in path:
                return _json({"refresh_token": "refresh-jwt", "access_token": "access-jwt"})
            if "finalizelogin" in path:
                return httpx.Response(
                    200,
                    json={
                        "transfer_info": [
                            {"url": "https://store.steampowered.com/login/settoken", "params": {"nonce": "n"}}
                        ]
                    },
                )
            return httpx.Response(200, json={}, headers={"set-cookie": "steamLoginSecure=abc; Path=/"})

        with self._client(handler) as client:
            session = login(client, "user", "correct-password")

        assert session.steam_id == "76561197960287930"
        assert session.refresh_token == "refresh-jwt"
        assert session.access_token == "access-jwt"
        assert session.session_id("store.steampowered.com")

    def test_steam_guard_code_is_submitted(self):
        submitted: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "GetPasswordRSAPublicKey" in path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            if "BeginAuthSessionViaCredentials" in path:
                return _json(
                    {
                        "client_id": "cid",
                        "request_id": "rid",
                        "steamid": "1",
                        "allowed_confirmations": [{"confirmation_type": 3}],
                        "interval": 0,
                    }
                )
            if "UpdateAuthSessionWithSteamGuardCode" in path:
                submitted["body"] = request.content.decode()
                return _json({})
            if "PollAuthSessionStatus" in path:
                return _json({"refresh_token": "r", "access_token": "a"})
            if "finalizelogin" in path:
                return httpx.Response(
                    200,
                    json={"transfer_info": [{"url": "https://store.steampowered.com/x", "params": {}}]},
                )
            return httpx.Response(200, json={}, headers={"set-cookie": "steamLoginSecure=abc; Path=/"})

        with self._client(handler) as client:
            login(client, "user", "pw", steam_guard_code="abcde")

        # Steam Guard codes are case-insensitive on input but sent uppercase.
        assert "ABCDE" in submitted["body"]

    def test_non_json_response_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>maintenance</html>", headers={"x-eresult": "1"})

        with self._client(handler) as client, pytest.raises(SteamAuthError, match="non-JSON"):
            login(client, "user", "pw")

    def test_missing_transfer_info_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "GetPasswordRSAPublicKey" in path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            if "BeginAuthSessionViaCredentials" in path:
                return _json({"client_id": "c", "request_id": "r", "steamid": "1", "interval": 0})
            if "PollAuthSessionStatus" in path:
                return _json({"refresh_token": "r"})
            return httpx.Response(200, json={"success": False})

        with self._client(handler) as client, pytest.raises(SteamAuthError, match="transfer info"):
            login(client, "user", "pw")

    def test_confirmation_timeout_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "GetPasswordRSAPublicKey" in path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            if "BeginAuthSessionViaCredentials" in path:
                return _json({"client_id": "c", "request_id": "r", "steamid": "1", "interval": 0})
            return _json({"had_remote_interaction": False})

        with self._client(handler) as client, pytest.raises(SteamAuthError, match="Timed out"):
            login(client, "user", "pw", poll_timeout=0.0)


class TestSteamSession:
    """Tests for session cookie handling."""

    def test_session_id_is_domain_scoped(self):
        """Steam issues a different sessionid per domain; the store one must win.

        Flattening the jar and taking the last value yields the community
        session id, which the store endpoint rejects.
        """
        session = SteamSession(
            steam_id="1",
            access_token="a",
            refresh_token="r",
            cookies={
                "store.steampowered.com": {"sessionid": "store-id"},
                "steamcommunity.com": {"sessionid": "community-id"},
            },
        )
        assert session.session_id("store.steampowered.com") == "store-id"
        assert session.session_id("steamcommunity.com") == "community-id"

    def test_unknown_domain_returns_none(self):
        session = SteamSession(steam_id="1", access_token="a", refresh_token="r")
        assert session.session_id("store.steampowered.com") is None


class TestFinalizeRobustness:
    """The cookie-exchange step must tolerate hostile or partial responses."""

    @staticmethod
    def _handler_with(transfers: list[dict]):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "GetPasswordRSAPublicKey" in path:
                return _json({"publickey_mod": _MODULUS, "publickey_exp": _EXPONENT, "timestamp": "1"})
            if "BeginAuthSessionViaCredentials" in path:
                return _json({"client_id": "c", "request_id": "r", "steamid": "1", "interval": 0})
            if "PollAuthSessionStatus" in path:
                return _json({"refresh_token": "r", "access_token": "a"})
            if "finalizelogin" in path:
                return httpx.Response(200, json={"transfer_info": transfers})
            if request.url.host == "unreachable.invalid":
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={}, headers={"set-cookie": "steamLoginSecure=abc; Path=/"})

        return handler

    def test_session_id_is_not_derived_from_the_clock(self):
        """A predictable session id would be guessable; it is a CSRF token."""
        handler = self._handler_with([{"url": "https://store.steampowered.com/x", "params": {}}])
        ids = set()
        for _ in range(5):
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                ids.add(login(client, "user", "pw").session_id("store.steampowered.com"))
        assert len(ids) == 5

    def test_a_failing_transfer_does_not_abandon_the_login(self):
        handler = self._handler_with(
            [
                {"url": "https://unreachable.invalid/x", "params": {}},
                {"url": "https://store.steampowered.com/x", "params": {}},
            ]
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            session = login(client, "user", "pw")
        assert session.session_id("store.steampowered.com")

    def test_a_malformed_transfer_url_is_skipped(self):
        handler = self._handler_with(
            [{"url": "not-a-url", "params": {}}, {"url": "https://store.steampowered.com/x", "params": {}}]
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            session = login(client, "user", "pw")
        assert session.cookies.get("store.steampowered.com") is not None
