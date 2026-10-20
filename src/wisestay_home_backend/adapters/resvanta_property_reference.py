"""Live Resvanta property-reference adapter (plan X.7, RSV-01/02).

``GET {api_root}/properties/{property_id}`` with the ``rv1`` machine
credential.  Mapping: 200 with ``property_type`` REAL/VIRTUAL -> current;
401/403/404 -> not_found (fail closed, never disclosed); 5xx, timeout or a
malformed body -> unavailable.  Bookability is never read (Q14).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request

from wisestay_home_backend.ports.property_reference import CredentialSource, PropertyReferenceFact

TIMEOUT_S = 3
_PROPERTY_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# transport(method, url, headers, timeout_s) -> (status, body bytes)
Transport = Callable[[str, str, dict, float], tuple[int, bytes]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirects are refused", headers, fp)


def urllib_transport(method: str, url: str, headers: dict, timeout_s: float) -> tuple[int, bytes]:
    if not url.startswith("https://"):
        raise ValueError("Resvanta API root must be https")
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout_s) as response:  # noqa: S310 - https enforced
            return response.status, response.read(64 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, b""


class SsmCredentialSource:
    """Reads the SecureString once per cold start; the value is never logged."""

    def __init__(self, parameter_name: str, client=None) -> None:
        self._parameter_name = parameter_name
        self._client = client
        self._value: str | None = None

    def get(self) -> str:
        if self._value is None:
            if self._client is None:
                import boto3  # noqa: PLC0415 - lazy: never imported by tests

                self._client = boto3.client("ssm")
            response = self._client.get_parameter(Name=self._parameter_name, WithDecryption=True)
            self._value = response["Parameter"]["Value"]
        return self._value


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ResvantaHttpPropertyReference:
    def __init__(self, api_root: str, credential: CredentialSource,
                 transport: Transport = urllib_transport, *,
                 clock: Callable[[], str] = _now_iso) -> None:
        self._api_root = api_root.rstrip("/")
        self._credential = credential
        self._transport = transport
        self._clock = clock

    def resolve(self, property_id: str) -> PropertyReferenceFact:
        if not isinstance(property_id, str) or not _PROPERTY_ID.match(property_id):
            return PropertyReferenceFact("not_found", str(property_id), None, None, None)
        unavailable = PropertyReferenceFact("unavailable", property_id, None, None, None)
        try:
            token = self._credential.get()
        except Exception:
            return unavailable
        url = f"{self._api_root}/properties/{urllib.parse.quote(property_id, safe='')}"
        try:
            status, body = self._transport(
                "GET", url, {"Authorization": f"Bearer {token}", "Accept": "application/json"},
                TIMEOUT_S)
        except Exception:  # timeout, connection or TLS failure
            return unavailable
        if status in (401, 403, 404):
            return PropertyReferenceFact("not_found", property_id, None, None, None)
        if status != 200:
            return unavailable
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return unavailable
        if not isinstance(document, dict):
            return unavailable
        property_type = document.get("property_type")
        version = document.get("version")
        if (document.get("id") != property_id or property_type not in ("REAL", "VIRTUAL")
                or not isinstance(version, int) or isinstance(version, bool)):
            return unavailable
        return PropertyReferenceFact("current", property_id, property_type, version, self._clock())
