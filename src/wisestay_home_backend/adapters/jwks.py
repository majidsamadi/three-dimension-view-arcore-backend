"""JWKS sources for the central Cognito user pool (plan X.6).

``HttpJwksSource`` fetches ``<issuer>/.well-known/jwks.json`` with
``urllib.request`` (redirects refused), caches keys for ``ttl_s`` and refreshes
at most once per 60 s on an unknown ``kid``.  Network or parse failures raise
``IdentityUnavailable``.  The fetch function is injectable so tests never use
the network.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Callable
import urllib.error
import urllib.request

from wisestay_home_backend.ports.identity import IdentityUnavailable, RsaPublicKey

UNKNOWN_KID_REFRESH_INTERVAL_S = 60


def b64url_to_int(value: str) -> int:
    padded = value + "=" * (-len(value) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded.encode("ascii")), "big")


def parse_jwks(raw: bytes) -> dict[str, RsaPublicKey]:
    document = json.loads(raw.decode("utf-8"))
    keys: dict[str, RsaPublicKey] = {}
    for jwk in document["keys"]:
        if jwk.get("kty") != "RSA" or not isinstance(jwk.get("kid"), str):
            continue
        if jwk.get("use") not in (None, "sig") or jwk.get("alg") not in (None, "RS256"):
            continue
        keys[jwk["kid"]] = RsaPublicKey(b64url_to_int(jwk["n"]), b64url_to_int(jwk["e"]))
    return keys


class StaticJwksSource:
    """Fixed keys (tests and local composition only)."""

    def __init__(self, keys: dict[str, RsaPublicKey]) -> None:
        self._keys = dict(keys)

    def key(self, kid: str) -> RsaPublicKey | None:
        return self._keys.get(kid)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise urllib.error.HTTPError(req.full_url, code, "redirects are refused", headers, fp)


def urllib_fetch(url: str, timeout_s: float) -> bytes:
    if not url.startswith("https://"):
        raise IdentityUnavailable("JWKS URL must be https")
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with opener.open(request, timeout=timeout_s) as response:  # noqa: S310 - https enforced above
        if response.status != 200:
            raise IdentityUnavailable("JWKS endpoint did not return 200")
        return response.read(256 * 1024)


class HttpJwksSource:
    def __init__(self, url: str, timeout_s: float = 3, ttl_s: int = 3600, *,
                 fetch: Callable[[str, float], bytes] = urllib_fetch,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._url = url
        self._timeout_s = timeout_s
        self._ttl_s = ttl_s
        self._fetch = fetch
        self._clock = clock
        self._keys: dict[str, RsaPublicKey] = {}
        self._loaded_at: float | None = None
        self._last_unknown_refresh: float | None = None

    def _refresh(self) -> None:
        try:
            keys = parse_jwks(self._fetch(self._url, self._timeout_s))
        except IdentityUnavailable:
            raise
        except Exception as exc:  # network, HTTP, JSON or key-format failure
            raise IdentityUnavailable("JWKS could not be loaded") from exc
        self._keys = keys
        self._loaded_at = self._clock()

    def key(self, kid: str) -> RsaPublicKey | None:
        now = self._clock()
        if self._loaded_at is None or now - self._loaded_at >= self._ttl_s:
            self._refresh()
            now = self._clock()
        if kid in self._keys:
            return self._keys[kid]
        if (self._last_unknown_refresh is None
                or now - self._last_unknown_refresh >= UNKNOWN_KID_REFRESH_INTERVAL_S):
            self._last_unknown_refresh = now
            self._refresh()
        return self._keys.get(kid)
