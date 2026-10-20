"""HTTPS transport and evidence recording for the dev integration suite (stdlib only).

The transport never follows redirects, so a bearer token can never be forwarded to another
host.  Evidence keeps the method, the path *template*, the status and the problem ``code``;
never a URL query, a header value, a token or a body.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import http.client
import json
import socket
import ssl
from typing import Protocol
from urllib.parse import urlsplit

MAX_BODY_BYTES = 4 * 1024 * 1024
TIMEOUT_S = 20.0


class TransportError(Exception):
    """Network-level failure.  ``kind`` is a closed label; no URL or provider text is kept."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict = field(default_factory=dict)  # lower-case names
    body: bytes = b""

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    def json(self):
        if self.content_type not in ("application/json", "application/problem+json",
                                     "application/x-amz-json-1.1"):
            return None
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None

    def json_object(self) -> dict:
        value = self.json()
        return value if isinstance(value, dict) else {}

    @property
    def problem_code(self) -> str | None:
        if self.content_type != "application/problem+json":
            return None
        code = self.json_object().get("code")
        return code if isinstance(code, str) else None


class Transport(Protocol):
    def request(self, method: str, url: str, headers: dict, body: bytes | None = None) -> HttpResponse:
        ...


class HttpsTransport:
    """``http.client`` over TLS with certificate verification; HTTPS only; no redirects."""

    def __init__(self, timeout_s: float = TIMEOUT_S) -> None:
        self._timeout = timeout_s
        self._context = ssl.create_default_context()

    def request(self, method: str, url: str, headers: dict, body: bytes | None = None) -> HttpResponse:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise TransportError("NON_HTTPS_URL_REFUSED")
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443,
                                                 timeout=self._timeout, context=self._context)
        try:
            connection.request(method, target, body=body, headers=dict(headers))
            response = connection.getresponse()
            data = response.read(MAX_BODY_BYTES + 1)
            if len(data) > MAX_BODY_BYTES:
                raise TransportError("RESPONSE_TOO_LARGE")
            return HttpResponse(response.status,
                                {name.lower(): value for name, value in response.getheaders()}, data)
        except ssl.SSLError:
            raise TransportError("TLS_ERROR") from None
        except socket.gaierror:
            raise TransportError("DNS_ERROR") from None
        except (socket.timeout, TimeoutError):
            raise TransportError("TIMEOUT") from None
        except (OSError, http.client.HTTPException):
            raise TransportError("CONNECTION_ERROR") from None
        finally:
            connection.close()


@dataclass
class Evidence:
    """Per-journey HTTP evidence; safe to publish."""

    entries: list = field(default_factory=list)

    def add(self, step: str, method: str, path_template: str, response: HttpResponse | None,
            error: str | None = None) -> None:
        entry = {"step": step, "method": method, "path": path_template,
                 "status": None if response is None else response.status}
        if response is not None and response.problem_code:
            entry["problem_code"] = response.problem_code
        if error:
            entry["error"] = error
        self.entries.append(entry)
