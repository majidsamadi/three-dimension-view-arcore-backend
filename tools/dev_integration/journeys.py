"""Tiers and cross-service journeys for the dev integration suite (plan §6.5.3).

Every journey ends ``passed``, ``failed`` or ``blocked`` with an exact reason.  ``blocked``
is used only when a named prerequisite outside the suite is missing (test identities, the
Resvanta property adapter under Q14, a dependency journey); it is never a disguised pass.
Payloads are synthetic and labelled ``synthetic-it-<run_id>``.  Nothing here claims
physical accuracy: the GLB is the 1 m synthetic unit box and declared dimensions are
synthetic declarations, not measurements.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote, urlencode, urlsplit

from tools.dev_integration.cognito_srp import (
    CognitoSignIn,
    Identity,
    SignInBlocked,
    SignInFailed,
)
from tools.dev_integration.http import Evidence, HttpResponse, Transport, TransportError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts/draft/v0.4/fixtures"

ACCOUNT = "511831442607"
REGION = "ap-southeast-1"
ENVIRONMENT = "dev"
POOL_ID = "ap-southeast-1_RbRHXUipk"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
CENTRAL_CLIENT_NAME = "wisestay-accounts-dev-web"
ACCOUNT_CONFIG_URL = "https://user.wizestay.com/api/v1/config"
SESSION_CONTRACT = "wisestay.web-session.v1"
REPORT_CONTRACT = "wisestay.3d.dev-integration-report.v1"

SECRET_NAMES = (
    "WS3D_IT_A_USERNAME", "WS3D_IT_A_PASSWORD", "WS3D_IT_A_TOTP_SECRET",
    "WS3D_IT_B_USERNAME", "WS3D_IT_B_PASSWORD", "WS3D_IT_B_TOTP_SECRET",
)

# Smoke routes are the backends' deploy smoke paths (hs/os/hc/wf notes "Contract interface").
APIS = {
    "home-scanner": {"root": "https://home-scanner.dev.wizestay.com/api/v1",
                     "smoke": "/home-scenes", "auth_probe": ("/home-scenes", 200)},
    "object-scanner": {"root": "https://object-scanner.dev.wizestay.com/api/v1",
                       "smoke": "/objects", "auth_probe": ("/objects", 200)},
    "composer": {"root": "https://composer.dev.wizestay.com/api/v1",
                 "smoke": "/designs", "auth_probe": ("/designs", 200)},
    "finder": {"root": "https://finder.dev.wizestay.com/api/v1",
               "smoke": "/queries/wave3-smoke-probe",
               # F17 for an unknown id: 404 proves the token was accepted (401 means it was not).
               "auth_probe": ("/queries/qry_synthetic-it-probe", 404)},
}
SITES = {
    "home-scanner": {"origin": "https://home-scanner.wizestay.com", "repository": "majidsamadi/three-dimension-view"},
    "object-scanner": {"origin": "https://object-scanner.wizestay.com",
                       "repository": "majidsamadi/three-dimension-object-app"},
    "composer": {"origin": "https://composer.wizestay.com", "repository": "majidsamadi/home-composer-app"},
    "finder": {"origin": "https://finder.wizestay.com", "repository": "majidsamadi/where-can-find-this-app"},
}

# (service, route id) -> (method, path template, idempotency key required).  Checked against
# the v0.4 fixtures by tests/test_dev_integration.py so the suite cannot drift from the contract.
ROUTES = {
    ("home-scanner", "H01"): ("POST", "/home-captures", True),
    ("home-scanner", "H02"): ("POST", "/home-captures/{capture_id}/uploads", True),
    ("home-scanner", "H03"): ("GET", "/uploads/{upload_id}", False),
    ("home-scanner", "H06"): ("POST", "/uploads/{upload_id}/finalize", True),
    ("home-scanner", "H08"): ("GET", "/home-scenes/{scene_id}", False),
    ("home-scanner", "H10"): ("POST", "/home-scenes/{scene_id}/versions/{version}/review", True),
    ("home-scanner", "H11"): ("GET", "/home-scenes/{scene_id}/versions/{version}/audience-projection", False),
    ("home-scanner", "H12"): ("POST", "/home-scenes/{scene_id}/publication", True),
    ("home-scanner", "H13"): ("POST", "/home-scenes/{scene_id}/withdrawal", True),
    ("home-scanner", "H14"): ("POST", "/home-scenes/{scene_id}/grants", True),
    ("home-scanner", "H15"): ("DELETE", "/home-scenes/{scene_id}/grants/{grant_id}", False),
    ("home-scanner", "H16"): ("POST", "/home-scenes/{scene_id}/view-grants", True),
    ("object-scanner", "O01"): ("POST", "/objects", True),
    ("object-scanner", "O02"): ("POST", "/objects/{object_id}/uploads", True),
    ("object-scanner", "O03"): ("GET", "/uploads/{upload_id}", False),
    ("object-scanner", "O06"): ("POST", "/uploads/{upload_id}/finalize", True),
    ("object-scanner", "O07"): ("POST", "/objects/{object_id}/versions/{version}/dimension-evidence", True),
    ("object-scanner", "O09"): ("POST", "/objects/{object_id}/versions/{version}/review", True),
    ("object-scanner", "O10"): ("POST", "/objects/{object_id}/publication", True),
    ("object-scanner", "O11"): ("POST", "/objects/{object_id}/withdrawal", True),
    ("object-scanner", "O12"): ("GET", "/objects/{object_id}", False),
    ("object-scanner", "O13"): ("GET", "/objects/{object_id}/versions/{version}", False),
    ("object-scanner", "O15"): ("POST", "/objects/{object_id}/shares", True),
    ("object-scanner", "O16"): ("DELETE", "/objects/{object_id}/shares/{share_id}", False),
    ("object-scanner", "O17"): ("POST", "/objects/{object_id}/use-grants", True),
    ("composer", "C01"): ("POST", "/designs", True),
    ("composer", "C03"): ("GET", "/designs/{design_id}", False),
    ("composer", "C05"): ("POST", "/designs/{design_id}/archive", True),
    ("composer", "C06"): ("POST", "/designs/{design_id}/branches/{branch_id}/placements", True),
    ("composer", "C14"): ("POST", "/designs/{design_id}/shares", True),
    ("composer", "C15"): ("POST", "/design-shares/{share_id}/accept", True),
    ("composer", "C17"): ("DELETE", "/designs/{design_id}/shares/{share_id}", False),
    ("composer", "C18"): ("POST", "/object-shares", True),
    ("composer", "C19"): ("GET", "/object-shares/{object_share_id}", False),
    ("composer", "C23"): ("POST", "/designs/{design_id}/view-sessions", True),
    ("finder", "F01"): ("POST", "/merchants", True),
    ("finder", "F02"): ("GET", "/merchants/{merchant_id}/members/me", False),
    ("finder", "F04"): ("POST", "/shops", True),
    ("finder", "F05"): ("POST", "/shops/{shop_id}/catalog/products", True),
    ("finder", "F06"): ("POST", "/shops/{shop_id}/catalog/products/{product_id}/variants", True),
    ("finder", "F09"): ("POST", "/shops/{shop_id}/catalog/variants/{variant_id}/object-links", True),
    ("finder", "F10"): ("POST", "/object-links/{link_id}/withdraw", True),
    ("finder", "F16"): ("POST", "/queries", True),
    ("finder", "F17"): ("GET", "/queries/{query_id}", False),
    ("finder", "F18"): ("POST", "/queries/{query_id}/cancel", True),
    ("finder", "F19"): ("GET", "/queries/{query_id}/results", False),
}

Q14_REASON = "Q14: the Resvanta property adapter is fail-closed in dev (no rv1 credential)"
MERCHANT_REASON = ("MERCHANT_ROLE_NOT_GRANTED: synthetic account A does not hold merchant_manager "
                   "for the merchant it created; no API grants it otherwise")


def load_api_fixture(service: str) -> dict:
    return json.loads((FIXTURES / f"api/{service}.v0.4.json").read_text(encoding="utf-8"))


def fixture_body(service: str, route_id: str, path: str) -> dict:
    for route in load_api_fixture(service)["routes"]:
        if route["id"] == route_id and route["path"] == path:
            return copy.deepcopy(route["request_example"]["body"])
    raise KeyError((service, route_id))


def synthetic_glb() -> bytes:
    return (FIXTURES / "assets/synthetic-unit-box.glb").read_bytes()


# --- outcomes ------------------------------------------------------------------------------

class Blocked(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Failed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Result:
    name: str
    status: str = "passed"
    reason: str | None = None
    steps: list = field(default_factory=list)
    evidence: Evidence = field(default_factory=Evidence)
    created: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def step(self, name: str, outcome: str = "passed", note: str | None = None) -> None:
        entry = {"step": name, "outcome": outcome}
        if note:
            entry["note"] = note
        self.steps.append(entry)

    def to_dict(self) -> dict:
        return {"status": self.status, "reason": self.reason, "steps": self.steps,
                "evidence": self.evidence.entries, "created": self.created, "notes": self.notes}


@dataclass
class Config:
    run_id: str
    secrets: dict = field(repr=False, default_factory=dict)
    expected_revisions: dict = field(default_factory=dict)
    property_id: str = "PROP-VIRTUAL-1"
    client_id_override: str | None = None
    apis: dict = field(default_factory=lambda: copy.deepcopy(APIS))
    sites: dict = field(default_factory=lambda: copy.deepcopy(SITES))
    # Presigned S3 URLs only (real runs); tests inject a stub check.
    presigned_ok: Callable[[str], bool] = field(
        default=lambda url: urlsplit(url).scheme == "https"
        and (urlsplit(url).hostname or "").endswith(".amazonaws.com"))

    @property
    def label(self) -> str:
        return f"synthetic-it-{self.run_id}"


@dataclass
class Context:
    config: Config
    transport: Transport
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    sleep: Callable[[float], None] = lambda seconds: None
    a: Identity | None = None
    b: Identity | None = None
    identity_block: str | None = None
    api_ok: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    cleanups: list = field(default_factory=list)  # (journey, label, callable)
    _key: int = 0

    def idempotency_key(self) -> str:
        self._key += 1
        return f"sit-{self.config.run_id}-{self._key:05d}"

    def rfc3339(self, delta_s: int = 0) -> str:
        return (self.clock() + timedelta(seconds=delta_s)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Api:
    """One service's dev API, driven by the contract route table."""

    def __init__(self, ctx: Context, service: str, result: Result) -> None:
        self.ctx = ctx
        self.service = service
        self.root = ctx.config.apis[service]["root"]
        self.result = result
        self.last_version: int | None = None

    def call(self, route_id: str, step: str, *, who: Identity | None, params: dict | None = None,
             body: dict | None = None, query: dict | None = None) -> HttpResponse:
        method, template, idempotent = ROUTES[(self.service, route_id)]
        path = re.sub(r"\{(\w+)\}", lambda m: quote(str((params or {})[m.group(1)]), safe=""), template)
        url = self.root + path + (("?" + urlencode(query)) if query else "")
        headers = {"Accept": "application/json"}
        if who is not None:
            headers["Authorization"] = who.authorization
        if idempotent:
            headers["Idempotency-Key"] = self.ctx.idempotency_key()
        raw = None
        if method in ("POST", "PATCH"):
            headers["Content-Type"] = "application/json"
            raw = json.dumps(body if body is not None else {}).encode("utf-8")
        label = f"{route_id} {step}"
        try:
            response = self.ctx.transport.request(method, url, headers, raw)
        except TransportError as exc:
            self.result.evidence.add(label, method, template, None, exc.kind)
            raise Failed(f"{label}: network {exc.kind}") from None
        self.result.evidence.add(label, method, template, response)
        return response

    def versioned(self, route_id: str, step: str, *, who: Identity, guess: int, params: dict | None = None,
                  body: dict | None = None, field_name: str = "expected_version", in_query: bool = False):
        """Send with a computed expected version; on 409 version_conflict retry once with the
        server's ``current_version``/``current_revision``.  Read routes do not always expose the
        record version, so this is the contract's own concurrency mechanism, not a bypass."""

        def send(version: int) -> HttpResponse:
            if in_query:
                return self.call(route_id, step, who=who, params=params, query={field_name: version})
            return self.call(route_id, step, who=who, params=params, body={**(body or {}), field_name: version})

        self.last_version = guess
        response = send(guess)
        if response.status == 409 and response.problem_code == "version_conflict":
            extras = response.json_object()
            current = extras.get("current_version", extras.get("current_revision"))
            if isinstance(current, int) and not isinstance(current, bool) and current != guess:
                self.last_version = current
                response = send(current)
        return response


def expect(response: HttpResponse, step: str, statuses, *, codes: tuple = (), block: dict | None = None) -> dict:
    """Return the JSON body when the status (and, if given, the problem code) is expected."""
    statuses = (statuses,) if isinstance(statuses, int) else tuple(statuses)
    code = response.problem_code
    if response.status in statuses and (not codes or code in codes):
        return response.json_object()
    if block and code in block:
        raise Blocked(f"{block[code]} [{step}: {response.status} {code}]")
    got = code or response.content_type or "no body"
    raise Failed(f"{step}: expected {'/'.join(map(str, statuses))}"
                 f"{' ' + '/'.join(codes) if codes else ''}, got {response.status} {got}")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Failed(reason)


def _put_component(ctx: Context, result: Result, component: dict, data: bytes, step: str) -> None:
    url = component.get("put_url")
    headers = component.get("put_headers") or {}
    if not isinstance(url, str) or not ctx.config.presigned_ok(url):
        raise Failed(f"{step}: presigned PUT URL is not an HTTPS S3 URL")
    template = "presigned:staging/{upload_id}/{component_id}"
    try:
        response = ctx.transport.request("PUT", url, {str(k): str(v) for k, v in headers.items()}, data)
    except TransportError as exc:
        result.evidence.add(step, "PUT", template, None, exc.kind)
        raise Failed(f"{step}: network {exc.kind}") from None
    result.evidence.add(step, "PUT", template, response)
    require(response.status in (200, 201, 204), f"{step}: presigned PUT returned {response.status}")


def _download_matches(ctx: Context, result: Result, url, expected_sha256: str, step: str) -> None:
    if not isinstance(url, str) or not ctx.config.presigned_ok(url):
        raise Failed(f"{step}: presigned GET URL is not an HTTPS S3 URL")
    try:
        response = ctx.transport.request("GET", url, {}, None)
    except TransportError as exc:
        result.evidence.add(step, "GET", "presigned:versions/{sha256}", None, exc.kind)
        raise Failed(f"{step}: network {exc.kind}") from None
    result.evidence.add(step, "GET", "presigned:versions/{sha256}", response)
    require(response.status == 200, f"{step}: presigned GET returned {response.status}")
    require(hashlib.sha256(response.body).hexdigest() == expected_sha256,
            f"{step}: downloaded component digest differs from the synthetic GLB")


def _no_design_or_home(value, path: str = "") -> bool:
    """True when a JSON value names no design or home (object-only share check)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("design_id", "home_source", "scene_id", "property_id", "branch_id"):
                return False
            if not _no_design_or_home(item):
                return False
        return True
    if isinstance(value, list):
        return all(_no_design_or_home(item) for item in value)
    if isinstance(value, str):
        return not value.startswith(("dsg_", "scn_"))
    return True


# --- T0: no identity ---------------------------------------------------------------------

def _revision_for(ctx: Context, site: str, result: Result) -> tuple[str | None, str]:
    expected = ctx.config.expected_revisions.get(site)
    if isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{40}", expected):
        return expected, "dispatch_input"
    repository = ctx.config.sites[site]["repository"]
    url = f"https://api.github.com/repos/{repository}/commits/main"
    try:
        response = ctx.transport.request("GET", url, {"Accept": "application/vnd.github.sha",
                                                      "User-Agent": "wisestay-dev-integration"}, None)
    except TransportError as exc:
        result.evidence.add(f"{site} main revision", "GET", "github:/repos/{repository}/commits/main", None, exc.kind)
        return None, "unavailable"
    result.evidence.add(f"{site} main revision", "GET", "github:/repos/{repository}/commits/main", response)
    text = response.body.decode("ascii", "replace").strip()
    if response.status == 200 and re.fullmatch(r"[0-9a-f]{40}", text):
        return text, "github_public_api"
    return None, "unavailable"


def tier0(ctx: Context) -> Result:
    result = Result("T0")
    failures, blocks = [], []
    for service, api in ctx.config.apis.items():
        name = f"{service} api smoke"
        try:
            response = ctx.transport.request("GET", api["root"] + api["smoke"], {"Accept": "application/json"}, None)
        except TransportError as exc:
            result.evidence.add(name, "GET", api["smoke"], None, exc.kind)
            result.step(name, "failed", exc.kind)
            failures.append(f"{name}: {exc.kind}")
            ctx.api_ok[service] = False
            continue
        result.evidence.add(name, "GET", api["smoke"], response)
        ok = response.status == 401 and response.problem_code == "identity_required"
        ctx.api_ok[service] = ok
        if ok:
            result.step(name)
        else:
            note = f"expected 401 identity_required problem+json, got {response.status} {response.problem_code or response.content_type}"
            result.step(name, "failed", note)
            failures.append(f"{name}: {note}")
    for site, spec in ctx.config.sites.items():
        origin = spec["origin"]

        def get(path: str, step: str, headers: dict | None = None) -> HttpResponse | None:
            try:
                response = ctx.transport.request("GET", origin + path, headers or {"Accept": "*/*"}, None)
            except TransportError as exc:
                result.evidence.add(f"{site} {step}", "GET", path, None, exc.kind)
                result.step(f"{site} {step}", "failed", exc.kind)
                failures.append(f"{site} {step}: {exc.kind}")
                return None
            result.evidence.add(f"{site} {step}", "GET", path, response)
            return response

        def check(step: str, ok: bool, note: str) -> None:
            result.step(f"{site} {step}", "passed" if ok else "failed", None if ok else note)
            if not ok:
                failures.append(f"{site} {step}: {note}")

        index = get("/", "index")
        if index is not None:
            check("index", index.status == 200 and index.content_type == "text/html",
                  f"got {index.status} {index.content_type}")
        release = get("/release.json", "release", {"Accept": "application/json"})
        if release is not None:
            manifest = release.json_object()
            check("release", release.status == 200 and isinstance(manifest.get("files"), dict),
                  f"got {release.status} {release.content_type}")
            if index is not None and isinstance(manifest.get("files"), dict):
                check("index hash", hashlib.sha256(index.body).hexdigest() == manifest["files"].get("index.html"),
                      "index.html digest differs from release.json")
            expected, source = _revision_for(ctx, site, result)
            if expected is None:
                result.step(f"{site} revision", "blocked",
                            "EXPECTED_REVISION_NOT_AVAILABLE: pass expected_revisions at dispatch "
                            "(the app repository main SHA is not publicly readable)")
                blocks.append(f"{site} revision: EXPECTED_REVISION_NOT_AVAILABLE")
            else:
                check("revision", manifest.get("revision") == expected,
                      f"release.json revision differs from main ({source})")
        missing = get("/assets/missing.js", "missing asset")
        if missing is not None:
            check("missing asset", missing.status in (403, 404), f"got {missing.status}")
        readiness = get(f"/api/v1/web-session/{site}/readiness", "session readiness",
                        {"Accept": "application/json", "Origin": origin, "Sec-Fetch-Site": "same-origin",
                         "X-WiseStay-Web-Session": SESSION_CONTRACT})
        if readiness is not None:
            check("session readiness",
                  readiness.status == 200 and readiness.content_type == "application/json"
                  and isinstance(readiness.json(), dict),
                  f"got {readiness.status} {readiness.content_type}")
    if failures:
        result.status, result.reason = "failed", "; ".join(failures[:8])
    elif blocks:
        result.status, result.reason = "blocked", "; ".join(blocks)
    return result


# --- T1: identities ----------------------------------------------------------------------

def _discover_client_id(ctx: Context, result: Result) -> str:
    if ctx.config.client_id_override:
        result.step("client id", note="from WS3D_IT_CLIENT_ID (non-secret override)")
        return ctx.config.client_id_override
    try:
        response = ctx.transport.request("GET", ACCOUNT_CONFIG_URL, {"Accept": "application/json"}, None)
    except TransportError as exc:
        result.evidence.add("account centre config", "GET", "user.wizestay.com:/api/v1/config", None, exc.kind)
        raise Failed(f"ACCOUNT_CONFIG_UNAVAILABLE: {exc.kind}") from None
    result.evidence.add("account centre config", "GET", "user.wizestay.com:/api/v1/config", response)
    config = response.json_object()
    client_id = config.get("app_client_id")
    require(response.status == 200 and isinstance(client_id, str) and client_id,
            f"ACCOUNT_CONFIG_UNAVAILABLE: got {response.status}")
    require(config.get("issuer") == ISSUER, "ACCOUNT_CONFIG_ISSUER_MISMATCH: not the dev pool")
    result.step("client id", note=f"public Account Centre config ({CENTRAL_CLIENT_NAME})")
    return client_id


def tier1(ctx: Context) -> Result:
    result = Result("T1")
    missing = [name for name in SECRET_NAMES if not ctx.config.secrets.get(name)]
    if missing:
        ctx.identity_block = "BLOCKED_TEST_IDENTITIES_ABSENT"
        result.status = "blocked"
        result.reason = ("BLOCKED_TEST_IDENTITIES_ABSENT: missing repository secrets "
                         + ", ".join(missing)
                         + ". A human must create two synthetic accounts at https://user.wizestay.com, "
                           "confirm their e-mail, enrol TOTP and add the secrets (docs/DEV_INTEGRATION.md).")
        result.notes.append({"missing_secrets": missing})
        return result
    try:
        client_id = _discover_client_id(ctx, result)
        signer = CognitoSignIn(ctx.transport, region=REGION, pool_id=POOL_ID, client_id=client_id,
                               evidence=result.evidence, clock=ctx.clock, sleep=ctx.sleep)
        identities = {}
        for label in ("A", "B"):
            try:
                identity = signer.sign_in(label, ctx.config.secrets[f"WS3D_IT_{label}_USERNAME"],
                                          ctx.config.secrets[f"WS3D_IT_{label}_PASSWORD"],
                                          ctx.config.secrets[f"WS3D_IT_{label}_TOTP_SECRET"])
            except SignInBlocked as exc:
                raise Blocked(f"{exc.reason} for identity {label}: a human must fix this account "
                              "(docs/DEV_INTEGRATION.md)") from None
            except SignInFailed as exc:
                raise Failed(f"SIGN_IN_FAILED for identity {label}: {exc.reason}") from None
            except TransportError as exc:
                raise Failed(f"SIGN_IN_FAILED for identity {label}: network {exc.kind}") from None
            require(identity.issuer == ISSUER, f"identity {label}: token issuer is not the dev pool")
            require(identity.client_id == client_id, f"identity {label}: token client_id differs from the central client")
            identities[label] = identity
            result.step(f"sign-in {label}", note="SRP + TOTP")
        require(identities["A"].user_id != identities["B"].user_id, "TEST_IDENTITIES_NOT_DISTINCT")
        ctx.a, ctx.b = identities["A"], identities["B"]
        for service, api in ctx.config.apis.items():
            if not ctx.api_ok.get(service):
                result.step(f"{service} token accepted", "blocked", "T0 smoke did not pass")
                continue
            path, status = api["auth_probe"]
            try:
                response = ctx.transport.request("GET", api["root"] + path,
                                                 {"Accept": "application/json", "Authorization": ctx.a.authorization}, None)
            except TransportError as exc:
                result.evidence.add(f"{service} token accepted", "GET", path, None, exc.kind)
                raise Failed(f"{service} token accepted: network {exc.kind}") from None
            result.evidence.add(f"{service} token accepted", "GET", path, response)
            require(response.status == status,
                    f"TOKEN_NOT_ACCEPTED_BY_{service.upper()}: 401 -> expected {status}, got {response.status}")
            result.step(f"{service} token accepted", note=f"401 without token -> {status} with token")
    except Blocked as exc:
        ctx.identity_block = exc.reason
        result.status, result.reason = "blocked", exc.reason
    except Failed as exc:
        ctx.identity_block = "T1 failed"
        result.status, result.reason = "failed", exc.reason
    return result


# --- identity journeys -------------------------------------------------------------------

def _needs(ctx: Context, *services: str) -> None:
    if ctx.a is None or ctx.b is None:
        raise Blocked(f"DEPENDS_ON_T1: {ctx.identity_block or 'test identities unavailable'}")
    for service in services:
        if not ctx.api_ok.get(service):
            raise Blocked(f"DEPENDS_ON_T0: the {service} API smoke did not pass")


def home_scanner(ctx: Context, result: Result) -> None:
    _needs(ctx, "home-scanner")
    api = Api(ctx, "home-scanner", result)
    a, b, glb = ctx.a, ctx.b, synthetic_glb()
    sha = hashlib.sha256(glb).hexdigest()
    body = fixture_body("home-scanner", "H01", "/home-captures")
    body.update(property_id=ctx.config.property_id, local_draft_ref=ctx.config.label)
    capture = expect(api.call("H01", "admit capture", who=a, body=body), "H01 admit capture", 201,
                     block={"property_not_usable": f"property_not_usable at capture admission ({Q14_REASON})",
                            "dependency_unavailable": f"dependency_unavailable at capture admission ({Q14_REASON})"})
    capture_id = capture["capture_id"]
    result.created["capture_id"] = capture_id
    result.step("admit capture")
    upload_body = fixture_body("home-scanner", "H02", "/home-captures/{capture_id}/uploads")
    upload = expect(api.call("H02", "create upload", who=a, params={"capture_id": capture_id}, body=upload_body),
                    "H02 create upload", 201)
    upload_id = upload["upload_id"]
    result.created["upload_id"] = upload_id
    _put_component(ctx, result, upload["components"][0], glb, "presigned PUT GLB")
    result.step("presigned upload of synthetic GLB + v0.4 envelope")
    state = expect(api.call("H03", "read upload", who=a, params={"upload_id": upload_id}), "H03 read upload", 200)
    finalized = expect(api.versioned("H06", "finalize", who=a, guess=int(state.get("record_version", 1)),
                                     params={"upload_id": upload_id}), "H06 finalize", 201)
    require(finalized.get("state") == "validated", f"H06 finalize: version state {finalized.get('state')}")
    scene_id, version = finalized["scene_id"], finalized["version"]
    result.created.update(scene_id=scene_id, version=version)
    result.step("finalize")
    ctx.cleanups.append(("home_scanner", "H13 withdraw scene", lambda: _withdraw_scene(ctx, result, scene_id)))

    def scene_version() -> int:
        return int(expect(api.call("H08", "read scene", who=a, params={"scene_id": scene_id}),
                          "H08 read scene", 200).get("record_version", 1))

    review = fixture_body("home-scanner", "H10", "/home-scenes/{scene_id}/versions/{version}/review")
    review["review_inputs"]["quality_note"] = ctx.config.label
    expect(api.versioned("H10", "review", who=a, guess=scene_version(), body=review,
                         params={"scene_id": scene_id, "version": version}), "H10 review", 200)
    projection = expect(api.call("H11", "audience projection", who=a, params={"scene_id": scene_id, "version": version}),
                        "H11 audience projection", 200)
    expect(api.versioned("H12", "publish", who=a, guess=scene_version(),
                         body={"version": version, "projection_id": projection["projection_id"]},
                         params={"scene_id": scene_id}), "H12 publish", 200)
    result.step("review and publish")
    expect(api.call("H08", "B before grant", who=b, params={"scene_id": scene_id}), "H08 B before grant", 404)
    expect(api.call("H16", "B view before grant", who=b, params={"scene_id": scene_id}, body={"version": version}),
           "H16 B view before grant", 404)
    result.step("wrong-account denial before grant")
    grant = expect(api.call("H14", "grant B", who=a, params={"scene_id": scene_id},
                            body={"grantee_user_id": b.user_id, "expires_at": ctx.rfc3339(86400)}), "H14 grant B", 201)
    grant_id = grant["grant_id"]
    result.created["grant_id"] = grant_id
    expect(api.call("H08", "B after grant", who=b, params={"scene_id": scene_id}), "H08 B after grant", 200)
    view = expect(api.call("H16", "B view grant", who=b, params={"scene_id": scene_id}, body={"version": version}),
                  "H16 B view grant", 201)
    _download_matches(ctx, result, (view.get("components") or [{}])[0].get("get_url"), sha, "B presigned GET GLB")
    result.step("second identity views the published scene")
    expect(api.versioned("H15", "revoke grant", who=a, guess=1, in_query=True,
                         params={"scene_id": scene_id, "grant_id": grant_id}), "H15 revoke grant", 200)
    expect(api.call("H16", "B view after revoke", who=b, params={"scene_id": scene_id}, body={"version": version}),
           "H16 B view after revoke", 403, codes=("grant_revoked",))
    result.step("revocation denies the second identity again")
    ctx.state["home"] = {"scene_id": scene_id, "version": version, "property_id": ctx.config.property_id}


def _withdraw_scene(ctx: Context, result: Result, scene_id: str) -> None:
    api = Api(ctx, "home-scanner", result)
    current = expect(api.call("H08", "cleanup read scene", who=ctx.a, params={"scene_id": scene_id}),
                     "H08 cleanup read scene", 200)
    expect(api.versioned("H13", "cleanup withdraw", who=ctx.a, guess=int(current.get("record_version", 1)),
                         params={"scene_id": scene_id}, body={"reason": f"{ctx.config.label} cleanup"}),
           "H13 cleanup withdraw", 200)


def object_scanner(ctx: Context, result: Result) -> None:
    _needs(ctx, "object-scanner")
    api = Api(ctx, "object-scanner", result)
    a, b, glb = ctx.a, ctx.b, synthetic_glb()
    sha = hashlib.sha256(glb).hexdigest()
    body = fixture_body("object-scanner", "O01", "/objects")
    body["title"] = f"{ctx.config.label} unit box"
    created = expect(api.call("O01", "create object", who=a, body=body), "O01 create object", 201)
    object_id = created["object_id"]
    result.created["object_id"] = object_id
    upload_body = fixture_body("object-scanner", "O02", "/objects/{object_id}/uploads")
    upload_body["envelope"]["asset_id"] = object_id
    upload = expect(api.call("O02", "create upload", who=a, params={"object_id": object_id}, body=upload_body),
                    "O02 create upload", 201)
    upload_id = upload["upload_id"]
    result.created["upload_id"] = upload_id
    _put_component(ctx, result, upload["components"][0], glb, "presigned PUT GLB")
    result.step("admit object session and presigned upload of synthetic GLB + v0.4 envelope")
    state = expect(api.call("O03", "read upload", who=a, params={"upload_id": upload_id}), "O03 read upload", 200)
    finalized = expect(api.versioned("O06", "finalize", who=a, guess=int(state.get("record_version", 1)),
                                     params={"upload_id": upload_id}), "O06 finalize", 201)
    require(finalized.get("state") == "validated", f"O06 finalize: version state {finalized.get('state')}")
    version = finalized["version"]
    result.created["version"] = version
    result.step("finalize")
    meta_version = 2
    evidence = fixture_body("object-scanner", "O07", "/objects/{object_id}/versions/{version}/dimension-evidence")
    evidence.pop("expected_version", None)
    response = api.versioned("O07", "declare synthetic dimensions", who=a, guess=meta_version,
                             params={"object_id": object_id, "version": version}, body=evidence)
    expect(response, "O07 declare synthetic dimensions", 201)
    result.notes.append("O07 records the synthetic unit box's declared 1 m dimensions; not a physical measurement")
    meta_version = api.last_version + 1
    response = api.versioned("O09", "review", who=a, guess=meta_version,
                             params={"object_id": object_id, "version": version}, body={"decision": "approved"})
    expect(response, "O09 review", 200)
    meta_version = api.last_version + 1
    published = expect(api.versioned("O10", "publish", who=a, guess=meta_version, params={"object_id": object_id},
                                     body={"allowed_use": ["view", "place"], "audience": "named_share",
                                           "merchant_id": None, "version": version}), "O10 publish", 200)
    result.step("review and publish (named share)")
    ctx.cleanups.append(("object_scanner", "O11 withdraw object",
                         lambda: _withdraw_object(ctx, result, object_id, int(published.get("record_version", 1)))))
    resolved = expect(api.call("O12", "resolve Object ID", who=a, params={"object_id": object_id}),
                      "O12 resolve Object ID", 200)
    require(resolved.get("object_id") == object_id and resolved.get("published_version") == version,
            "O12 resolve Object ID: id or published version differs")
    detail = expect(api.call("O13", "resolve Object ID version", who=a, params={"object_id": object_id, "version": version}),
                    "O13 resolve Object ID version", 200)
    components = (detail.get("envelope") or {}).get("components") or []
    require(detail.get("envelope", {}).get("asset_id") == object_id and any(c.get("sha256") == sha for c in components),
            "O13: envelope does not resolve to this Object ID and GLB")
    result.step("Object ID resolution (O12/O13)")
    expect(api.call("O12", "B before share", who=b, params={"object_id": object_id}), "O12 B before share", 404)
    expect(api.call("O17", "B use before share", who=b, params={"object_id": object_id},
                    body={"action": "view", "version": version}), "O17 B use before share", 404)
    result.step("wrong-account denial before share")
    share = expect(api.call("O15", "share to B", who=a, params={"object_id": object_id},
                            body={"allowed_use": ["view", "place"], "expires_at": ctx.rfc3339(86400),
                                  "grantee_user_id": b.user_id}), "O15 share to B", 201)
    share_id = share["share_id"]
    result.created["share_id"] = share_id
    seen = expect(api.call("O13", "B resolve after share", who=b, params={"object_id": object_id, "version": version}),
                  "O13 B resolve after share", 200)
    require("view" in (seen.get("caller_allowed_use") or []), "O13 B: view is not in caller_allowed_use")
    use = expect(api.call("O17", "B view grant", who=b, params={"object_id": object_id},
                          body={"action": "view", "version": version}), "O17 B view grant", 201)
    _download_matches(ctx, result, (use.get("components") or [{}])[0].get("get_url"), sha, "B presigned GET GLB")
    result.step("second identity views the shared object")
    expect(api.versioned("O16", "revoke share", who=a, guess=1, in_query=True,
                         params={"object_id": object_id, "share_id": share_id}), "O16 revoke share", 200)
    expect(api.call("O13", "B after revoke", who=b, params={"object_id": object_id, "version": version}),
           "O13 B after revoke", 403, codes=("grant_revoked",))
    result.step("revocation denies the second identity again")
    ctx.state["object"] = {"object_id": object_id, "version": version}


def _withdraw_object(ctx: Context, result: Result, object_id: str, guess: int) -> None:
    api = Api(ctx, "object-scanner", result)
    expect(api.versioned("O11", "cleanup withdraw", who=ctx.a, guess=guess, params={"object_id": object_id},
                         body={"reason": f"{ctx.config.label} cleanup"}), "O11 cleanup withdraw", 200)


def composer(ctx: Context, result: Result) -> None:
    _needs(ctx, "composer", "object-scanner")
    obj = ctx.state.get("object")
    if obj is None:
        raise Blocked("DEPENDS_ON_OBJECT_SCANNER: no published synthetic object from the Object Scanner journey")
    api, osb = Api(ctx, "composer", result), Api(ctx, "object-scanner", result)
    a, b = ctx.a, ctx.b
    design = expect(api.call("C01", "create sandbox design", who=a,
                             body={"title": f"{ctx.config.label} sandbox", "context_kind": "non_property_sandbox"}),
                    "C01 create sandbox design", 201)
    design_id = design["design_id"]
    result.created["design_id"] = design_id
    ctx.cleanups.append(("composer", "C05 archive design", lambda: _archive_design(ctx, result, design_id)))
    placed = expect(api.versioned("C06", "place object by Object ID", who=a, guess=int(design.get("revision", 1)),
                                  field_name="expected_revision", params={"design_id": design_id, "branch_id": "main"},
                                  body={"illustrative_scale": None, "object_source": obj, "scale_mode": "real",
                                        "transform": {"position_m": [1.0, 0.0, 1.0], "rotation_deg_y": 90}}),
                    "C06 place object by Object ID", 201)
    result.created["placement_id"] = (placed.get("placement") or {}).get("placement_id")
    result.step("create design and place the object by Object ID")
    expect(api.call("C03", "B before any share", who=b, params={"design_id": design_id}), "C03 B before any share", 404)
    result.step("wrong-account denial of the design")
    os_share = expect(osb.call("O15", "object share to B", who=a, params={"object_id": obj["object_id"]},
                               body={"allowed_use": ["view", "place"], "expires_at": ctx.rfc3339(86400),
                                     "grantee_user_id": b.user_id}), "O15 object share to B", 201)
    ctx.cleanups.append(("composer", "O16 revoke object share",
                         lambda: _revoke_object_share(ctx, result, obj["object_id"], os_share["share_id"])))
    object_share = expect(api.call("C18", "share Object ID only", who=a,
                                   body={"grantee_user_id": b.user_id, "note": ctx.config.label, "object_source": obj}),
                          "C18 share Object ID only", 201)
    require(_no_design_or_home({k: v for k, v in object_share.items() if k != "grantee_user_id"}),
            "C18: the object share names a design or home")
    seen = expect(api.call("C19", "B opens object share", who=b,
                           params={"object_share_id": object_share["object_share_id"]}), "C19 B opens object share", 200)
    require(seen.get("source_outcome") == "accessible", f"C19: source_outcome {seen.get('source_outcome')}")
    require(_no_design_or_home(seen), "C19: the object share exposes a design or home")
    expect(api.call("C03", "B with Object ID only", who=b, params={"design_id": design_id}),
           "C03 B with Object ID only", 404)
    result.step("sharing the Object ID alone exposes neither the design nor a home")
    share = expect(api.call("C14", "share Design ID to B", who=a, params={"design_id": design_id},
                            body={"expires_at": None, "grantee_user_id": b.user_id, "role": "viewer"}),
                   "C14 share Design ID to B", 201)
    expect(api.call("C15", "B accepts design share", who=b, params={"share_id": share["share_id"]}, body={}),
           "C15 B accepts design share", 200)
    opened = expect(api.call("C03", "B opens design", who=b, params={"design_id": design_id}), "C03 B opens design", 200)
    require(opened.get("design_id") == design_id and opened.get("role") == "viewer", "C03 B: not a viewer of the design")
    result.step("sharing the Design ID gives the second identity the design")
    expect(api.versioned("C17", "revoke design share", who=a, guess=2, in_query=True,
                         params={"design_id": design_id, "share_id": share["share_id"]}), "C17 revoke design share", 200)
    expect(api.call("C03", "B after revoke", who=b, params={"design_id": design_id}), "C03 B after revoke", 404)
    result.step("design share revocation denies the second identity again")


def composer_home_placement(ctx: Context, result: Result) -> None:
    _needs(ctx, "composer", "home-scanner", "object-scanner")
    home, obj = ctx.state.get("home"), ctx.state.get("object")
    if home is None:
        raise Blocked(f"DEPENDS_ON_HOME_SCANNER: {ctx.state.get('home_reason') or 'no published synthetic home scene'}")
    if obj is None:
        raise Blocked("DEPENDS_ON_OBJECT_SCANNER: no published synthetic object")
    api = Api(ctx, "composer", result)
    design = expect(api.call("C01", "create home design", who=ctx.a,
                             body={"title": f"{ctx.config.label} home plan", "context_kind": "property_home",
                                   "home_source": {"scene_id": home["scene_id"], "version": home["version"]},
                                   "property_id": home["property_id"]}),
                    "C01 create home design", 201,
                    block={"dependency_unavailable": f"dependency_unavailable at design creation ({Q14_REASON})"})
    design_id = design["design_id"]
    result.created["design_id"] = design_id
    ctx.cleanups.append(("composer_home_placement", "C05 archive design", lambda: _archive_design(ctx, result, design_id)))
    placed = expect(api.versioned("C06", "place object in home", who=ctx.a, guess=int(design.get("revision", 1)),
                                  field_name="expected_revision", params={"design_id": design_id, "branch_id": "main"},
                                  body={"illustrative_scale": None, "object_source": obj, "scale_mode": "real",
                                        "transform": {"position_m": [0.0, 0.0, 0.0], "rotation_deg_y": 0}}),
                    "C06 place object in home", 201)
    session = expect(api.call("C23", "view session", who=ctx.a, params={"design_id": design_id},
                              body={"branch_id": "main", "revision": int(placed.get("revision", 2))}),
                     "C23 view session", 201)
    require((session.get("home") or {}).get("outcome") == "accessible", "C23: home is not accessible to its owner")
    require(all(o.get("outcome") == "accessible" for o in session.get("objects") or [{}]),
            "C23: placed object is not accessible to its owner")
    result.step("object placed in the synthetic home and viewable")


def _archive_design(ctx: Context, result: Result, design_id: str) -> None:
    api = Api(ctx, "composer", result)
    current = expect(api.call("C03", "cleanup read design", who=ctx.a, params={"design_id": design_id}),
                     "C03 cleanup read design", 200)
    expect(api.versioned("C05", "cleanup archive", who=ctx.a, guess=int(current.get("record_version", 1)),
                         params={"design_id": design_id}), "C05 cleanup archive", 200)


def _revoke_object_share(ctx: Context, result: Result, object_id: str, share_id: str) -> None:
    api = Api(ctx, "object-scanner", result)
    expect(api.versioned("O16", "cleanup revoke", who=ctx.a, guess=1, in_query=True,
                         params={"object_id": object_id, "share_id": share_id}), "O16 cleanup revoke", 200)


def finder_catalog_link(ctx: Context, result: Result) -> None:
    _needs(ctx, "finder", "object-scanner")
    obj = ctx.state.get("object")
    if obj is None:
        raise Blocked("DEPENDS_ON_OBJECT_SCANNER: no published synthetic object to link")
    api, a = Api(ctx, "finder", result), ctx.a
    merchant = expect(api.call("F01", "create merchant", who=a, body={"name": f"{ctx.config.label} merchant"}),
                      "F01 create merchant", 201, block={"action_denied": MERCHANT_REASON})
    merchant_id = merchant["merchant_id"]
    result.created["merchant_id"] = merchant_id
    member = expect(api.call("F02", "own membership", who=a, params={"merchant_id": merchant_id}), "F02 own membership", 200)
    if member.get("role") != "merchant_manager":
        raise Blocked(f"{MERCHANT_REASON} [F02: role {member.get('role')}]")
    result.step("merchant created; A holds merchant_manager")
    shop = expect(api.call("F04", "register shop", who=a,
                           body={"merchant_id": merchant_id, "name": f"{ctx.config.label} shop",
                                 "premises": {"property_id": ctx.config.property_id}}),
                  "F04 register shop", 201,
                  block={"property_not_usable": f"property_not_usable at shop registration ({Q14_REASON})",
                         "dependency_unavailable": f"dependency_unavailable at shop registration ({Q14_REASON})",
                         "action_denied": MERCHANT_REASON})
    shop_id = shop["shop_id"]
    result.created["shop_id"] = shop_id
    product = expect(api.call("F05", "catalog product", who=a, params={"shop_id": shop_id},
                              body={"brand": "Synthetic", "family_name": f"{ctx.config.label} box", "model": "Box-1"}),
                     "F05 catalog product", 201, block={"action_denied": MERCHANT_REASON})
    variant = expect(api.call("F06", "catalog variant", who=a,
                              params={"shop_id": shop_id, "product_id": product["product_id"]},
                              body=fixture_body("finder", "F06", "/shops/{shop_id}/catalog/products/{product_id}/variants")),
                     "F06 catalog variant", 201, block={"action_denied": MERCHANT_REASON})
    link = expect(api.call("F09", "link object", who=a,
                           params={"shop_id": shop_id, "variant_id": variant["variant_id"]}, body=obj),
                  "F09 link object", 201)
    require(link.get("link_status") == "linked", f"F09: link_status {link.get('link_status')}")
    result.created.update(product_id=product["product_id"], variant_id=variant["variant_id"], link_id=link["link_id"])
    ctx.cleanups.append(("finder_catalog_link", "F10 withdraw link", lambda: _withdraw_link(ctx, result, link["link_id"])))
    result.step("catalog variant linked to the Object ID")
    result.notes.append("Merchant, shop and catalog rows have no delete route; they stay as synthetic dev records")


def _withdraw_link(ctx: Context, result: Result, link_id: str) -> None:
    api = Api(ctx, "finder", result)
    expect(api.versioned("F10", "cleanup withdraw link", who=ctx.a, guess=1, params={"link_id": link_id},
                         body={"reason": f"{ctx.config.label} cleanup"}), "F10 cleanup withdraw link", 200)


def finder_query(ctx: Context, result: Result) -> None:
    _needs(ctx, "finder")
    api = Api(ctx, "finder", result)
    gtin = fixture_body("finder", "F06", "/shops/{shop_id}/catalog/products/{product_id}/variants")["gtin"]
    query = expect(api.call("F16", "submit query", who=ctx.a,
                            body={"consent": {"process_query": True}, "input": {"kind": "identifier", "value": gtin}}),
                   "F16 submit query", 201)
    query_id = query["query_id"]
    result.created["query_id"] = query_id
    status = expect(api.call("F17", "query status", who=ctx.a, params={"query_id": query_id}), "F17 query status", 200)
    require(status.get("state") in ("accepted", "processing", "completed"), f"F17: state {status.get('state')}")
    results = expect(api.call("F19", "query results", who=ctx.a, params={"query_id": query_id}), "F19 query results", 200)
    require(isinstance(results.get("processing_status"), dict) and isinstance(results.get("candidates"), list),
            "F19: results lack processing_status or candidates")
    result.notes.append(f"identifier query returned {len(results['candidates'])} candidate(s); "
                        "candidates need a published shop projection, which Q14 blocks in dev")
    expect(api.call("F17", "B reads A's query", who=ctx.b, params={"query_id": query_id}), "F17 B reads A's query", 404)
    result.step("query submitted, read and kept private to its owner")
    result.notes.append("Query records expire after 24 h (Q08 lifecycle); no cancel is sent so results stay readable")


JOURNEYS = (
    ("home_scanner", home_scanner),
    ("object_scanner", object_scanner),
    ("composer", composer),
    ("composer_home_placement", composer_home_placement),
    ("finder_catalog_link", finder_catalog_link),
    ("finder_query", finder_query),
)


def run_journey(ctx: Context, name: str, fn) -> Result:
    result = Result(name)
    try:
        fn(ctx, result)
    except Blocked as exc:
        result.status, result.reason = "blocked", exc.reason
    except Failed as exc:
        result.status, result.reason = "failed", exc.reason
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        result.status, result.reason = "failed", f"UNEXPECTED_RESPONSE_SHAPE: {type(exc).__name__}"
    if name == "home_scanner" and result.status != "passed":
        ctx.state["home_reason"] = f"home_scanner {result.status}: {result.reason}"
    return result


def run_all(ctx: Context) -> dict:
    started = ctx.clock()
    tiers = {"T0": tier0(ctx), "T1": tier1(ctx)}
    journeys = {name: run_journey(ctx, name, fn) for name, fn in JOURNEYS}
    cleanup = []
    for journey, label, action in reversed(ctx.cleanups):
        try:
            action()
            cleanup.append({"journey": journey, "action": label, "outcome": "done"})
        except (Blocked, Failed) as exc:
            cleanup.append({"journey": journey, "action": label, "outcome": "failed", "reason": exc.reason})
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            cleanup.append({"journey": journey, "action": label, "outcome": "failed",
                            "reason": f"UNEXPECTED_RESPONSE_SHAPE: {type(exc).__name__}"})
    everything = list(tiers.values()) + list(journeys.values())
    counts = {s: sum(1 for r in everything if r.status == s) for s in ("passed", "failed", "blocked")}
    overall = "passed" if counts["passed"] == len(everything) else ("failed" if counts["failed"] else "blocked")
    return {
        "contract": REPORT_CONTRACT,
        "label": ctx.config.label,
        "environment": {"account": ACCOUNT, "region": REGION, "environment": ENVIRONMENT,
                        "cognito_pool": POOL_ID, "central_client": CENTRAL_CLIENT_NAME},
        "data_policy": "synthetic data only (Q07 first slice); no physical-accuracy claim",
        "started_at": started.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": ctx.rfc3339(),
        "tiers": {name: r.to_dict() for name, r in tiers.items()},
        "journeys": {name: r.to_dict() for name, r in journeys.items()},
        "cleanup": cleanup,
        "summary": counts,
        "result": overall,
    }
