"""Cognito USER_SRP_AUTH plus SOFTWARE_TOKEN_MFA sign-in (stdlib only).

Only the public, unauthenticated Cognito user-pool operations are used
(``InitiateAuth`` and ``RespondToAuthChallenge``).  No AWS credentials or SigV4 signing are
involved.  The SRP-6a parameters follow the Cognito user-pool definition: the 3072-bit
RFC 5054 group, ``g = 2``, ``k = H(00 || N || 0 || g)``, ``x = H(salt || H(poolId username ":" password))``
and a one-block HKDF-SHA256 with info ``"Caldera Derived Key"`` truncated to 16 bytes.

Nothing here logs or returns the password, the TOTP secret, the TOTP code or a token in
an error.  ``SignInBlocked`` carries a closed reason naming the human step that is missing.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from typing import Callable

from tools.dev_integration.http import Evidence, HttpResponse, Transport
from tools.dev_integration.totp import decode_base32_secret, seconds_left_in_step, totp

N_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74"
    "020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F1437"
    "4FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF05"
    "98DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB"
    "9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF695581718"
    "3995497CEA956AE515D2261898FA051015728E5A8AAAC42DAD33170D04507A33"
    "A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864"
    "D87602733EC86A64521F2B18177B200CBBE117577A615D6C770988C0BAD946E2"
    "08E24FA074E5AB3143DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"
)
G_HEX = "2"
INFO_BITS = b"Caldera Derived Key"
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def hash_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().rjust(64, "0")


def hex_hash(hex_string: str) -> str:
    return hash_sha256(bytes.fromhex(hex_string))


def long_to_hex(value: int) -> str:
    return "%x" % value


def pad_hex(value) -> str:
    """Two's-complement-safe even-length hex, as Cognito hashes it."""
    text = value if isinstance(value, str) else long_to_hex(value)
    if len(text) % 2 == 1:
        return "0" + text
    if text[0] in "89ABCDEFabcdef":
        return "00" + text
    return text


def compute_hkdf(ikm: bytes, salt: bytes) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, INFO_BITS + b"\x01", hashlib.sha256).digest()[:16]


def cognito_timestamp(now: datetime) -> str:
    """``Mon Oct 5 03:04:05 UTC 2026``: day of month without zero padding, in UTC."""
    now = now.astimezone(timezone.utc)
    return (f"{_DAYS[now.weekday()]} {_MONTHS[now.month - 1]} {now.day} "
            f"{now:%H:%M:%S} UTC {now.year}")


class SrpClient:
    def __init__(self, pool_id: str, random_bytes: Callable[[int], bytes] = os.urandom) -> None:
        if "_" not in pool_id:
            raise ValueError("pool id must look like <region>_<id>")
        self.pool_short = pool_id.split("_", 1)[1]
        self.big_n = int(N_HEX, 16)
        self.g = int(G_HEX, 16)
        self.k = int(hex_hash("00" + N_HEX + "0" + G_HEX), 16)
        self.small_a = int.from_bytes(random_bytes(128), "big") % self.big_n
        self.large_a = pow(self.g, self.small_a, self.big_n)
        if self.small_a == 0 or self.large_a % self.big_n == 0:
            raise ValueError("unsafe SRP ephemeral")

    @property
    def srp_a(self) -> str:
        return long_to_hex(self.large_a)

    def u_value(self, server_b: int) -> int:
        return int(hex_hash(pad_hex(self.large_a) + pad_hex(server_b)), 16)

    def x_value(self, username: str, password: str, salt_hex: str) -> int:
        inner = hash_sha256(f"{self.pool_short}{username}:{password}".encode("utf-8"))
        return int(hex_hash(pad_hex(salt_hex) + inner), 16)

    def authentication_key(self, username: str, password: str, server_b_hex: str, salt_hex: str) -> bytes:
        server_b = int(server_b_hex, 16)
        if server_b % self.big_n == 0:
            raise ValueError("unsafe SRP_B")
        u = self.u_value(server_b)
        if u == 0:
            raise ValueError("unsafe SRP u")
        x = self.x_value(username, password, salt_hex)
        base = server_b - self.k * pow(self.g, x, self.big_n)
        s = pow(base, self.small_a + u * x, self.big_n)
        return compute_hkdf(bytes.fromhex(pad_hex(s)), bytes.fromhex(pad_hex(long_to_hex(u))))

    def password_claim(self, params: dict, password: str, now: datetime) -> dict:
        user_id = params["USER_ID_FOR_SRP"]
        key = self.authentication_key(user_id, password, params["SRP_B"], params["SALT"])
        timestamp = cognito_timestamp(now)
        message = (self.pool_short.encode() + user_id.encode()
                   + base64.b64decode(params["SECRET_BLOCK"]) + timestamp.encode())
        signature = base64.b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode()
        return {"TIMESTAMP": timestamp, "USERNAME": user_id,
                "PASSWORD_CLAIM_SECRET_BLOCK": params["SECRET_BLOCK"],
                "PASSWORD_CLAIM_SIGNATURE": signature}


class SignInBlocked(Exception):
    """A human step is missing (closed reason; no secret material)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SignInFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Identity:
    """A signed-in synthetic test identity.  ``repr`` never shows the token."""

    label: str
    access_token: str = field(repr=False)
    user_id: str = field(repr=False)
    client_id: str = ""
    issuer: str = ""
    expires_at: int = 0

    @property
    def authorization(self) -> str:
        return "Bearer " + self.access_token


def decode_claims(token: str) -> dict:
    """Read (not verify) JWT claims; the backends verify signatures themselves."""
    try:
        payload = token.split(".")[1]
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        raise SignInFailed("ACCESS_TOKEN_NOT_A_JWT") from None
    if not isinstance(value, dict):
        raise SignInFailed("ACCESS_TOKEN_NOT_A_JWT")
    return value


_BLOCKING_ERRORS = {
    "NotAuthorizedException": "TEST_IDENTITY_SIGN_IN_REJECTED",
    "UserNotFoundException": "TEST_IDENTITY_SIGN_IN_REJECTED",
    "UserNotConfirmedException": "TEST_IDENTITY_EMAIL_NOT_CONFIRMED",
    "PasswordResetRequiredException": "TEST_IDENTITY_PASSWORD_RESET_REQUIRED",
    "CodeMismatchException": "TEST_IDENTITY_TOTP_REJECTED",
    "ExpiredCodeException": "TEST_IDENTITY_TOTP_REJECTED",
    "EnableSoftwareTokenMFAException": "TEST_IDENTITY_MFA_NOT_ENROLLED",
}
_BLOCKING_CHALLENGES = {
    "MFA_SETUP": "TEST_IDENTITY_MFA_NOT_ENROLLED",
    "NEW_PASSWORD_REQUIRED": "TEST_IDENTITY_PASSWORD_CHANGE_REQUIRED",
    "SMS_MFA": "TEST_IDENTITY_TOTP_NOT_THE_MFA_METHOD",
    "EMAIL_OTP": "TEST_IDENTITY_TOTP_NOT_THE_MFA_METHOD",
}


class CognitoSignIn:
    def __init__(self, transport: Transport, *, region: str, pool_id: str, client_id: str,
                 evidence: Evidence, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], None] = lambda s: None,
                 random_bytes: Callable[[int], bytes] = os.urandom) -> None:
        self._transport = transport
        self._endpoint = f"https://cognito-idp.{region}.amazonaws.com/"
        self._pool_id = pool_id
        self._client_id = client_id
        self._evidence = evidence
        self._clock = clock
        self._sleep = sleep
        self._random = random_bytes

    def _call(self, step: str, target: str, payload: dict) -> dict:
        response = self._transport.request(
            "POST", self._endpoint,
            {"Content-Type": "application/x-amz-json-1.1",
             "X-Amz-Target": f"AWSCognitoIdentityProviderService.{target}"},
            json.dumps(payload).encode("utf-8"))
        self._evidence.add(step, "POST", f"cognito-idp:{target}", HttpResponse(response.status))
        body = response.json_object() if response.body else {}
        if response.status == 200:
            return body
        error = str(body.get("__type", "")).split("#")[-1] or f"HTTP_{response.status}"
        if error in _BLOCKING_ERRORS:
            raise SignInBlocked(_BLOCKING_ERRORS[error])
        raise SignInFailed(f"COGNITO_{error}")

    def sign_in(self, label: str, username: str, password: str, totp_secret: str) -> Identity:
        try:
            key = decode_base32_secret(totp_secret)
        except ValueError:
            raise SignInBlocked("TEST_IDENTITY_TOTP_SECRET_INVALID") from None
        srp = SrpClient(self._pool_id, self._random)
        start = self._call(f"{label}:initiate", "InitiateAuth", {
            "AuthFlow": "USER_SRP_AUTH", "ClientId": self._client_id,
            "AuthParameters": {"USERNAME": username, "SRP_A": srp.srp_a}})
        if start.get("ChallengeName") != "PASSWORD_VERIFIER":
            raise SignInFailed("UNEXPECTED_CHALLENGE_" + str(start.get("ChallengeName")))
        params = start.get("ChallengeParameters") or {}
        if not all(isinstance(params.get(k), str) for k in ("SALT", "SRP_B", "SECRET_BLOCK", "USER_ID_FOR_SRP")):
            raise SignInFailed("PASSWORD_VERIFIER_INCOMPLETE")
        user_id_for_srp = params["USER_ID_FOR_SRP"]
        step = self._call(f"{label}:password-verifier", "RespondToAuthChallenge", {
            "ChallengeName": "PASSWORD_VERIFIER", "ClientId": self._client_id,
            "ChallengeResponses": srp.password_claim(params, password, self._clock())})
        for _ in range(3):
            if "AuthenticationResult" in step:
                break
            challenge = step.get("ChallengeName")
            if challenge in _BLOCKING_CHALLENGES:
                raise SignInBlocked(_BLOCKING_CHALLENGES[challenge])
            if challenge == "SELECT_MFA_TYPE":
                step = self._call(f"{label}:select-mfa", "RespondToAuthChallenge", {
                    "ChallengeName": "SELECT_MFA_TYPE", "ClientId": self._client_id,
                    "Session": step.get("Session"),
                    "ChallengeResponses": {"USERNAME": user_id_for_srp, "ANSWER": "SOFTWARE_TOKEN_MFA"}})
                continue
            if challenge != "SOFTWARE_TOKEN_MFA":
                raise SignInFailed("UNEXPECTED_CHALLENGE_" + str(challenge))
            now = self._clock().timestamp()
            if seconds_left_in_step(now) < 3:  # avoid a code that expires in transit
                self._sleep(seconds_left_in_step(now) + 0.5)
                now = self._clock().timestamp()
            step = self._call(f"{label}:software-token-mfa", "RespondToAuthChallenge", {
                "ChallengeName": "SOFTWARE_TOKEN_MFA", "ClientId": self._client_id,
                "Session": step.get("Session"),
                "ChallengeResponses": {"USERNAME": user_id_for_srp,
                                       "SOFTWARE_TOKEN_MFA_CODE": totp(key, now)}})
        result = step.get("AuthenticationResult") or {}
        token = result.get("AccessToken")
        if not isinstance(token, str) or not token:
            raise SignInFailed("NO_ACCESS_TOKEN")
        claims = decode_claims(token)
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise SignInFailed("ACCESS_TOKEN_WITHOUT_SUBJECT")
        exp = claims.get("exp") if isinstance(claims.get("exp"), int) else 0
        return Identity(label, token, sub, str(claims.get("client_id", "")), str(claims.get("iss", "")), exp)
