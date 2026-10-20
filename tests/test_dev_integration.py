"""Dev integration suite helpers and journey sequencing (wave 3 plan §6.5.3).

Everything runs locally against stubs: a stub Cognito SRP server, the real Home Scanner
router in-process (``tests.fakes_wave2.Harness``) and small stateful stubs for the other
three services.  No network, no AWS.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from urllib.parse import parse_qsl, urlsplit

import yaml  # test-only: requirements-ci.txt

import tests  # noqa: F401  -- puts src/ on sys.path
from tests.fakes_wave2 import FakePropertyReference, Harness
from tools.dev_integration import cognito_srp, journeys, run, totp
from tools.dev_integration.cognito_srp import (
    CognitoSignIn,
    Identity,
    SignInBlocked,
    SrpClient,
    compute_hkdf,
    hex_hash,
    pad_hex,
)
from tools.dev_integration.http import Evidence, HttpResponse
from wisestay_home_backend.http.handlers import Request

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/dev-integration.yml"
NOW = datetime(2026, 10, 20, 1, 2, 3, tzinfo=timezone.utc)
CLIENT_ID = "stubcentralclient0000000000"
SHA = {site: f"{i}" * 40 for i, site in enumerate(journeys.SITES, start=1)}
PASSWORDS = {"A": "Synthetic-pass-A-0001", "B": "Synthetic-pass-B-0002"}
TOTP_SECRETS = {"A": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", "B": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"}
USERS = {"A": "USER-A", "B": "USER-B"}


def jwt(claims: dict) -> str:
    def seg(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'RS256', 'kid': 'stub'})}.{seg(claims)}.c2lnbmF0dXJl"


TOKENS = {label: jwt({"sub": USERS[label], "iss": journeys.ISSUER, "client_id": CLIENT_ID,
                      "token_use": "access", "exp": 1_900_000_000}) for label in ("A", "B")}
BEARERS = {"Bearer " + TOKENS[label]: USERS[label] for label in TOKENS}


def env_with_secrets() -> dict:
    env = {"WS3D_IT_RUN_ID": "4242", "WS3D_IT_EXPECTED_REVISIONS": json.dumps(SHA)}
    for label in ("A", "B"):
        env[f"WS3D_IT_{label}_USERNAME"] = f"synthetic-{label.lower()}@example.invalid"
        env[f"WS3D_IT_{label}_PASSWORD"] = PASSWORDS[label]
        env[f"WS3D_IT_{label}_TOTP_SECRET"] = TOTP_SECRETS[label]
    return env


def reply(status: int, body=None, content_type: str = "application/json") -> HttpResponse:
    raw = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    return HttpResponse(status, {"content-type": content_type}, raw)


def problem(status: int, code: str, **extras) -> HttpResponse:
    return reply(status, {"code": code, "status": status, **extras}, "application/problem+json")


# --- stub Cognito (server half of SRP-6a) -----------------------------------------------------

class StubCognito:
    def __init__(self, *, challenge_after_password: str = "SOFTWARE_TOKEN_MFA",
                 reject_password: bool = False) -> None:
        self.challenge_after_password = challenge_after_password
        self.reject_password = reject_password
        self.salt = "1f2e3d4c5b6a79880011223344556677"
        self.sessions: dict[str, dict] = {}
        self.calls: list[str] = []

    def _label(self, username: str) -> str:
        return "A" if username.startswith("synthetic-a") else "B"

    def handle(self, target: str, body: dict) -> HttpResponse:
        self.calls.append(target)
        srp = SrpClient(journeys.POOL_ID, lambda n: b"\x01" * n)  # group constants only
        n, g, k = srp.big_n, srp.g, srp.k
        if target == "InitiateAuth":
            label = self._label(body["AuthParameters"]["USERNAME"])
            user_id = f"stub-srp-{label}"
            x = srp.x_value(user_id, PASSWORDS[label], self.salt)
            v = pow(g, x, n)
            b = int.from_bytes(hashlib.sha256(f"server-b-{label}".encode()).digest() * 4, "big") % n
            big_b = (k * v + pow(g, b, n)) % n
            secret_block = base64.b64encode(f"secret-block-{label}".encode()).decode()
            self.sessions[label] = {"A": int(body["AuthParameters"]["SRP_A"], 16), "b": b, "B": big_b, "v": v,
                                    "user_id": user_id, "secret_block": secret_block}
            return reply(200, {"ChallengeName": "PASSWORD_VERIFIER", "ChallengeParameters": {
                "SALT": self.salt, "SRP_B": "%x" % big_b, "SECRET_BLOCK": secret_block,
                "USER_ID_FOR_SRP": user_id, "USERNAME": user_id}}, "application/x-amz-json-1.1")
        challenge = body["ChallengeName"]
        responses = body["ChallengeResponses"]
        label = "A" if responses["USERNAME"].endswith("A") else "B"
        session = self.sessions[label]
        if challenge == "PASSWORD_VERIFIER":
            if self.reject_password:
                return reply(400, {"__type": "NotAuthorizedException", "message": "Incorrect username or password."},
                             "application/x-amz-json-1.1")
            u = int(hex_hash(pad_hex(session["A"]) + pad_hex(session["B"])), 16)
            s = pow(session["A"] * pow(session["v"], u, n), session["b"], n)
            key = compute_hkdf(bytes.fromhex(pad_hex(s)), bytes.fromhex(pad_hex("%x" % u)))
            message = (journeys.POOL_ID.split("_")[1].encode() + session["user_id"].encode()
                       + base64.b64decode(session["secret_block"]) + responses["TIMESTAMP"].encode())
            expected = base64.b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode()
            if responses["PASSWORD_CLAIM_SIGNATURE"] != expected:
                return reply(400, {"__type": "NotAuthorizedException"}, "application/x-amz-json-1.1")
            return reply(200, {"ChallengeName": self.challenge_after_password, "Session": f"session-{label}"},
                         "application/x-amz-json-1.1")
        if challenge == "SOFTWARE_TOKEN_MFA":
            key = totp.decode_base32_secret(TOTP_SECRETS[label])
            if responses["SOFTWARE_TOKEN_MFA_CODE"] != totp.totp(key, NOW.timestamp()):
                return reply(400, {"__type": "CodeMismatchException"}, "application/x-amz-json-1.1")
            return reply(200, {"AuthenticationResult": {"AccessToken": TOKENS[label], "IdToken": "not-used",
                                                        "RefreshToken": "not-used"}}, "application/x-amz-json-1.1")
        return reply(400, {"__type": "InvalidParameterException"}, "application/x-amz-json-1.1")


# --- stub dev services ---------------------------------------------------------------------

class StubServices:
    """Object Scanner, Composer and Finder behaviour needed by the journeys; stateful."""

    def __init__(self, *, shop_problem: str | None = None, merchant_denied: bool = False) -> None:
        self.shop_problem = shop_problem
        self.merchant_denied = merchant_denied
        self.objects: dict = {}
        self.uploads: dict = {}
        self.shares: dict = {}
        self.designs: dict = {}
        self.design_shares: dict = {}
        self.object_shares: dict = {}
        self.queries: dict = {}
        self.blobs: dict = {}
        self.n = 0

    def new(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}_01HZYSYNTH{self.n:016d}"

    def object_access(self, object_id: str, user: str) -> tuple[str, tuple]:
        obj = self.objects.get(object_id)
        if obj is None:
            return "none", ()
        if obj["creator"] == user:
            return "creator", ("view", "place")
        shares = [s for s in self.shares.values() if s["object_id"] == object_id and s["grantee"] == user]
        if any(s["state"] == "active" for s in shares) and obj["published"]:
            return "grantee", ("view", "place")
        if any(s["state"] == "revoked" for s in shares):
            return "revoked", ()
        return "none", ()

    def osb(self, method, path, query, body, user):
        m = re.fullmatch(r"/objects(?:/([^/]+))?(?:/(.*))?", path)
        if path == "/objects" and method == "GET":
            return reply(200, {"items": [], "next_cursor": None})
        if path == "/objects" and method == "POST":
            object_id = self.new("obj")
            self.objects[object_id] = {"creator": user, "version": 1, "published": False, "upload": None}
            return reply(201, {"object_id": object_id, "record_version": 1, "state": "draft"})
        m = re.fullmatch(r"/uploads/([^/]+)(/finalize)?", path)
        if m:
            upload = self.uploads[m.group(1)]
            if m.group(2):
                if body.get("expected_version") != 1 or f"staging/{m.group(1)}/main" not in self.blobs:
                    return problem(409, "upload_incomplete")
                self.objects[upload["object_id"]]["version"] += 1
                return reply(201, {"object_id": upload["object_id"], "state": "validated", "version": "1"})
            return reply(200, {"record_version": 1, "state": "open"})
        m = re.fullmatch(r"/objects/([^/]+)(?:/(.*))?", path)
        object_id, rest = m.group(1), m.group(2) or ""
        obj = self.objects.get(object_id)
        access, uses = self.object_access(object_id, user)
        if rest == "uploads":
            upload_id = self.new("upl")
            self.uploads[upload_id] = {"object_id": object_id}
            component = body["components"][0]
            return reply(201, {"upload_id": upload_id, "components": [{
                "component_id": "main", "put_url": f"fake-s3://osb/staging/{upload_id}/main",
                "put_headers": {"content-length": str(component["bytes"]),
                                "x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(component["sha256"])).decode()}}]})
        if rest.startswith("versions/1/") or rest in ("publication", "withdrawal"):
            if access != "creator":
                return problem(404, "not_found")
            if body.get("expected_version") != obj["version"]:
                return problem(409, "version_conflict", current_version=obj["version"])
            obj["version"] += 1
            if rest == "publication":
                obj["published"] = True
                return reply(200, {"state": "published", "published_version": "1", "record_version": obj["version"]})
            return reply(201 if rest.endswith("dimension-evidence") else 200, {"ok": True})
        if rest == "shares":
            share_id = self.new("shr")
            self.shares[share_id] = {"object_id": object_id, "grantee": body["grantee_user_id"], "state": "active"}
            return reply(201, {"share_id": share_id, "state": "active"})
        if rest.startswith("shares/") and method == "DELETE":
            if query.get("expected_version") != "1":
                return problem(409, "version_conflict", current_version=1)
            self.shares[rest.split("/")[1]]["state"] = "revoked"
            return reply(200, {"state": "revoked"})
        if access == "revoked":
            return problem(403, "grant_revoked")
        if access == "none":
            return problem(404, "not_found")
        sha = hashlib.sha256(journeys.synthetic_glb()).hexdigest()
        if rest == "":
            return reply(200, {"object_id": object_id, "published_version": "1", "state": "published"})
        if rest == "versions/1":
            return reply(200, {"caller_allowed_use": list(uses), "envelope": {
                "asset_id": object_id, "components": [{"component_id": "main", "sha256": sha}]}})
        if rest == "use-grants":
            self.blobs[f"versions/{sha}"] = journeys.synthetic_glb()
            return reply(201, {"components": [{"component_id": "main", "get_url": f"fake-s3://osb/versions/{sha}"}]})
        return problem(404, "not_found")

    def hcb(self, method, path, query, body, user):
        if path == "/designs" and method == "GET":
            return reply(200, {"items": []})
        if path == "/designs":
            design_id = self.new("dsg")
            self.designs[design_id] = {"owner": user, "revision": 1, "record_version": 1, "kind": body["context_kind"]}
            return reply(201, {"design_id": design_id, "revision": 1, "branch_id": "main", "role": "owner"})
        if path == "/object-shares":
            share_id = self.new("shr")
            self.object_shares[share_id] = {"grantee": body["grantee_user_id"], "object_source": body["object_source"]}
            return reply(201, {"object_share_id": share_id, "object_source": body["object_source"],
                               "grantee_user_id": body["grantee_user_id"]})
        m = re.fullmatch(r"/object-shares/([^/]+)", path)
        if m:
            share = self.object_shares.get(m.group(1))
            if share is None or share["grantee"] != user:
                return problem(404, "not_found")
            access, _ = self.object_access(share["object_source"]["object_id"], user)
            return reply(200, {"object_source": share["object_source"],
                               "source_outcome": "accessible" if access in ("creator", "grantee") else "source_access_denied"})
        m = re.fullmatch(r"/design-shares/([^/]+)/accept", path)
        if m:
            share = self.design_shares.get(m.group(1))
            if share is None or share["grantee"] != user:
                return problem(404, "not_found")
            share.update(state="accepted", version=2)
            return reply(200, {"state": "accepted"})
        m = re.fullmatch(r"/designs/([^/]+)(?:/(.*))?", path)
        design_id, rest = m.group(1), m.group(2) or ""
        design = self.designs.get(design_id)
        shares = [s for s in self.design_shares.values() if s["design_id"] == design_id and s["grantee"] == user
                  and s["state"] == "accepted"]
        if design is None or (design["owner"] != user and not shares):
            return problem(404, "not_found")
        role = "owner" if design["owner"] == user else shares[0]["role"]
        if rest == "" and method == "GET":
            return reply(200, {"design_id": design_id, "role": role, "record_version": design["record_version"]})
        if role != "owner":
            return problem(403, "action_denied")
        if rest == "branches/main/placements":
            if body.get("expected_revision") != design["revision"]:
                return problem(409, "version_conflict", current_revision=design["revision"])
            design["revision"] += 1
            return reply(201, {"placement": {"placement_id": self.new("plc")}, "revision": design["revision"]})
        if rest == "shares":
            share_id = self.new("shr")
            self.design_shares[share_id] = {"design_id": design_id, "grantee": body["grantee_user_id"],
                                            "role": body["role"], "state": "invited", "version": 1}
            return reply(201, {"share_id": share_id, "state": "invited", "role": body["role"]})
        if rest.startswith("shares/") and method == "DELETE":
            share = self.design_shares[rest.split("/")[1]]
            if query.get("expected_version") != str(share["version"]):
                return problem(409, "version_conflict", current_version=share["version"])
            share["state"] = "revoked"
            return reply(200, {"state": "revoked"})
        if rest == "view-sessions":
            return reply(201, {"home": {"outcome": "accessible"}, "objects": [{"outcome": "accessible"}]})
        if rest == "archive":
            return reply(200, {"status": "archived"})
        return problem(404, "not_found")

    def wfb(self, method, path, query, body, user):
        if path == "/merchants":
            if self.merchant_denied:
                return problem(403, "action_denied")
            return reply(201, {"merchant_id": self.new("mer"), "role": "merchant_manager"})
        if re.fullmatch(r"/merchants/[^/]+/members/me", path):
            return reply(200, {"role": "merchant_manager", "user_id": user})
        if path == "/shops":
            if self.shop_problem:
                return problem(422 if self.shop_problem == "property_not_usable" else 503, self.shop_problem)
            return reply(201, {"shop_id": self.new("shp")})
        if path.endswith("/catalog/products"):
            return reply(201, {"product_id": self.new("prd")})
        if path.endswith("/variants"):
            return reply(201, {"variant_id": self.new("var")})
        if path.endswith("/object-links"):
            if self.object_access(body["object_id"], user)[0] != "creator":
                return problem(404, "not_found")
            return reply(201, {"link_id": self.new("lnk"), "link_status": "linked"})
        if path.endswith("/withdraw"):
            return reply(200, {"link_status": "withdrawn"})
        if path == "/queries":
            query_id = self.new("qry")
            self.queries[query_id] = user
            return reply(201, {"query_id": query_id, "state": "accepted"})
        m = re.fullmatch(r"/queries/([^/]+)(/results)?", path)
        if m and self.queries.get(m.group(1)) == user:
            if m.group(2):
                return reply(200, {"processing_status": {"state": "completed"}, "candidates": []})
            return reply(200, {"query_id": m.group(1), "state": "completed"})
        return problem(404, "not_found")


class DevStub:
    """The whole dev surface: sites, Account Centre config, Cognito, four APIs and fake S3."""

    def __init__(self, *, properties: FakePropertyReference | None = None, cognito: StubCognito | None = None,
                 services: StubServices | None = None, api_down: str | None = None) -> None:
        self.harness = Harness(properties=properties)
        self.harness.identity._tokens.update(BEARERS)
        self.cognito = cognito or StubCognito()
        self.services = services or StubServices()
        self.api_down = api_down
        self.log: list[tuple[str, str]] = []
        self.authorizations: list[str] = []
        self.auth_hosts: set[str] = set()

    def request(self, method, url, headers, body=None):
        parts = urlsplit(url)
        self.log.append((method, url))
        if "Authorization" in headers:
            self.authorizations.append(headers["Authorization"])
            self.auth_hosts.add(parts.hostname or parts.scheme)
        if parts.scheme == "fake-s3":
            key = parts.path.lstrip("/")
            if parts.netloc == "osb":
                if method == "PUT":
                    self.services.blobs[key] = body
                    return reply(200)
                return reply(200, self.services.blobs[key], "application/octet-stream")
            if method == "PUT":
                self.harness.storage.client_upload(key, body, headers.get("x-amz-checksum-sha256"))
                return reply(200)
            return reply(200, self.harness.storage.objects[key][0], "application/octet-stream")
        host = parts.hostname
        if host == "cognito-idp.ap-southeast-1.amazonaws.com":
            return self.cognito.handle(headers["X-Amz-Target"].split(".")[-1], json.loads(body))
        if host == "user.wizestay.com":
            return reply(200, {"app_client_id": CLIENT_ID, "issuer": journeys.ISSUER})
        if host == "api.github.com":
            return reply(404, {"message": "Not Found"})
        site = next((s for s, spec in journeys.SITES.items() if spec["origin"] == f"https://{host}"), None)
        if site:
            index = f"<html><title>{site}</title></html>".encode()
            if parts.path == "/":
                return reply(200, index, "text/html")
            if parts.path == "/release.json":
                return reply(200, {"revision": SHA[site], "files": {"index.html": hashlib.sha256(index).hexdigest()}})
            if parts.path.endswith("/readiness"):
                return reply(200, {"contract": journeys.SESSION_CONTRACT, "ready": True})
            return reply(404, b"", "application/xml")
        service = host.split(".")[0]
        if service == self.api_down:
            return reply(503, b"Service Unavailable", "text/plain")
        path = parts.path[len("/api/v1"):]
        query = dict(parse_qsl(parts.query))
        if service == "home-scanner":
            response = self.harness.composition.api.dispatch(
                Request(method, parts.path, dict(headers), query, body, "req-stub"))
            return HttpResponse(response.status, {k.lower(): v for k, v in response.headers.items()}, response.encoded())
        user = BEARERS.get(headers.get("Authorization", ""))
        if user is None:
            return problem(401, "identity_required")
        payload = json.loads(body) if body else {}
        handler = {"object-scanner": self.services.osb, "composer": self.services.hcb, "finder": self.services.wfb}[service]
        return handler(method, path, query, payload, user)


def context(stub: DevStub, env: dict | None = None) -> journeys.Context:
    config = run.config_from_env(env if env is not None else env_with_secrets())
    config.presigned_ok = lambda url: url.startswith("fake-s3://")
    return journeys.Context(config=config, transport=stub, clock=lambda: NOW)


def run_suite(stub: DevStub, env: dict | None = None) -> tuple[int, dict, str]:
    env = env_with_secrets() if env is None else env
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "dist/dev-integration-report.json"
        out = io.StringIO()
        factory = lambda config, transport: context(stub, env)  # noqa: E731
        with redirect_stdout(out):
            code = run.main(["--report", str(target)], env=env, transport=stub, context_factory=factory)
        return code, json.loads(target.read_text()), out.getvalue()


# --- tests ---------------------------------------------------------------------------------

class TotpTests(unittest.TestCase):
    def test_rfc6238_sha1_vectors(self):
        key = b"12345678901234567890"
        for unix_time, expected in ((59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                                    (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")):
            self.assertEqual(totp.totp(key, unix_time, digits=8), expected)

    def test_rfc4226_hotp_vectors_and_base32(self):
        key = totp.decode_base32_secret("gezd gnbv gy3t qojq gezd gnbv gy3t qojq")
        self.assertEqual(key, b"12345678901234567890")
        self.assertEqual([totp.hotp(key, c) for c in range(3)], ["755224", "287082", "359152"])
        with self.assertRaises(totp.TotpSecretError) as caught:
            totp.decode_base32_secret("not-base32!")
        self.assertNotIn("not-base32", str(caught.exception))


class SrpTests(unittest.TestCase):
    def test_group_is_the_3072_bit_safe_prime(self):
        n = int(cognito_srp.N_HEX, 16)
        self.assertEqual(n.bit_length(), 3072)
        for candidate in (n, (n - 1) // 2):  # Miller-Rabin, fixed bases
            d, r = candidate - 1, 0
            while d % 2 == 0:
                d, r = d // 2, r + 1
            for base in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
                x = pow(base, d, candidate)
                if x in (1, candidate - 1):
                    continue
                for _ in range(r - 1):
                    x = pow(x, 2, candidate)
                    if x == candidate - 1:
                        break
                else:
                    self.fail("N is not a safe prime")

    def test_client_key_equals_the_server_key_for_a_fixed_vector(self):
        client = SrpClient("ap-southeast-1_RbRHXUipk", lambda n: bytes(range(n)))
        salt, user, password = "00ab12", "stub-user", "Synthetic-pass-0001"
        v = pow(client.g, client.x_value(user, password, salt), client.big_n)
        b = int("1234567890abcdef" * 16, 16)
        big_b = (client.k * v + pow(client.g, b, client.big_n)) % client.big_n
        u = client.u_value(big_b)
        server_s = pow(client.large_a * pow(v, u, client.big_n), b, client.big_n)
        server_key = compute_hkdf(bytes.fromhex(pad_hex(server_s)), bytes.fromhex(pad_hex("%x" % u)))
        self.assertEqual(client.authentication_key(user, password, "%x" % big_b, salt), server_key)
        self.assertNotEqual(client.authentication_key(user, "wrong-password", "%x" % big_b, salt), server_key)

    def test_hkdf_matches_rfc5869_construction(self):
        ikm, salt = b"\x0b" * 22, bytes(range(13))
        prk = hmac.new(salt, ikm, hashlib.sha256).digest()
        self.assertEqual(prk.hex(), "077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5")
        expected = hmac.new(prk, b"Caldera Derived Key\x01", hashlib.sha256).digest()[:16]
        self.assertEqual(compute_hkdf(ikm, salt), expected)

    def test_padding_and_timestamp_follow_cognito(self):
        self.assertEqual(pad_hex(0xF), "0f")
        self.assertEqual(pad_hex(0x8F), "008f")
        self.assertEqual(pad_hex("7f"), "7f")
        self.assertEqual(cognito_srp.cognito_timestamp(datetime(2026, 10, 5, 3, 4, 5, tzinfo=timezone.utc)),
                         "Mon Oct 5 03:04:05 UTC 2026")

    def test_sign_in_against_a_stub_srp_server(self):
        cognito = StubCognito()
        evidence = Evidence()
        signer = CognitoSignIn(DevStub(cognito=cognito), region="ap-southeast-1", pool_id=journeys.POOL_ID,
                               client_id=CLIENT_ID, evidence=evidence, clock=lambda: NOW)
        identity = signer.sign_in("A", "synthetic-a@example.invalid", PASSWORDS["A"], TOTP_SECRETS["A"])
        self.assertEqual((identity.user_id, identity.client_id, identity.issuer), ("USER-A", CLIENT_ID, journeys.ISSUER))
        self.assertEqual(cognito.calls, ["InitiateAuth", "RespondToAuthChallenge", "RespondToAuthChallenge"])
        self.assertNotIn(TOKENS["A"], repr(identity))
        self.assertNotIn(TOKENS["A"], json.dumps(evidence.entries))

    def test_sign_in_reports_the_missing_human_step(self):
        for cognito, reason in ((StubCognito(challenge_after_password="MFA_SETUP"), "TEST_IDENTITY_MFA_NOT_ENROLLED"),
                                (StubCognito(challenge_after_password="NEW_PASSWORD_REQUIRED"),
                                 "TEST_IDENTITY_PASSWORD_CHANGE_REQUIRED"),
                                (StubCognito(reject_password=True), "TEST_IDENTITY_SIGN_IN_REJECTED")):
            signer = CognitoSignIn(DevStub(cognito=cognito), region="ap-southeast-1", pool_id=journeys.POOL_ID,
                                   client_id=CLIENT_ID, evidence=Evidence(), clock=lambda: NOW)
            with self.assertRaises(SignInBlocked) as caught:
                signer.sign_in("A", "synthetic-a@example.invalid", PASSWORDS["A"], TOTP_SECRETS["A"])
            self.assertEqual(caught.exception.reason, reason)
            self.assertNotIn(PASSWORDS["A"], str(caught.exception))


class RouteContractTests(unittest.TestCase):
    def test_route_table_matches_the_v0_4_fixtures(self):
        for (service, route_id), (method, path, idempotent) in journeys.ROUTES.items():
            routes = [r for r in journeys.load_api_fixture(service)["routes"]
                      if r["id"] == route_id and r["path"] == path]
            self.assertEqual(len(routes), 1, (service, route_id, path))
            self.assertEqual(routes[0]["method"], method, (service, route_id))
            self.assertEqual(routes[0]["idempotency_key"] == "required", idempotent, (service, route_id))

    def test_api_roots_and_sites_match_the_contract(self):
        for service, api in journeys.APIS.items():
            self.assertEqual(api["root"], journeys.load_api_fixture(service)["api_root"])
            self.assertEqual(journeys.SITES[service]["origin"], f"https://{service}.wizestay.com")
        self.assertEqual(json.loads((ROOT / "deployment/dev.config.json").read_text())["smoke_path"],
                         journeys.APIS["home-scanner"]["smoke"])

    def test_version_conflict_is_retried_once_with_the_server_version(self):
        sent = []

        class Scripted:
            def request(self, method, url, headers, body=None):
                sent.append(json.loads(body)["expected_version"])
                return problem(409, "version_conflict", current_version=7) if len(sent) == 1 else reply(200, {})

        ctx = journeys.Context(config=journeys.Config(run_id="1"), transport=Scripted())
        api = journeys.Api(ctx, "object-scanner", journeys.Result("x"))
        who = Identity("A", "token", "USER-A")
        self.assertEqual(api.versioned("O11", "withdraw", who=who, guess=3, params={"object_id": "obj_1"}).status, 200)
        self.assertEqual((sent, api.last_version), ([3, 7], 7))


class JourneyTests(unittest.TestCase):
    def test_every_journey_passes_against_the_local_stubs(self):
        stub = DevStub()
        code, report, out = run_suite(stub)
        failing = {k: v["reason"] for g in ("tiers", "journeys") for k, v in report[g].items() if v["status"] != "passed"}
        self.assertEqual(failing, {})
        self.assertEqual((code, report["result"]), (0, "passed"))
        self.assertEqual(report["summary"], {"passed": 8, "failed": 0, "blocked": 0})
        self.assertEqual({c["outcome"] for c in report["cleanup"]}, {"done"})
        self.assertEqual(report["label"], "synthetic-it-4242")
        home = report["journeys"]["home_scanner"]
        self.assertIn("revocation denies the second identity again", [s["step"] for s in home["steps"]])
        self.assertEqual([e["status"] for e in home["evidence"] if e["step"] == "H16 B view after revoke"], [403])
        self.assertTrue(stub.harness.storage.objects, "the GLB really reached the in-process store")
        text = json.dumps(report) + out
        for secret in list(env_with_secrets().values())[2:] + list(TOKENS.values()):
            self.assertNotIn(secret, text)

    def test_missing_secrets_block_every_identity_journey_and_exit_non_zero(self):
        env = {k: v for k, v in env_with_secrets().items() if k not in ("WS3D_IT_B_TOTP_SECRET", "WS3D_IT_A_PASSWORD")}
        stub = DevStub()
        code, report, _ = run_suite(stub, env)
        self.assertEqual(code, 1)
        self.assertEqual(report["tiers"]["T0"]["status"], "passed")
        t1 = report["tiers"]["T1"]
        self.assertEqual(t1["status"], "blocked")
        self.assertTrue(t1["reason"].startswith("BLOCKED_TEST_IDENTITIES_ABSENT"))
        self.assertEqual(t1["notes"], [{"missing_secrets": ["WS3D_IT_A_PASSWORD", "WS3D_IT_B_TOTP_SECRET"]}])
        for name, result in report["journeys"].items():
            self.assertEqual(result["status"], "blocked", name)
            self.assertIn("BLOCKED_TEST_IDENTITIES_ABSENT", result["reason"])
        self.assertEqual(report["result"], "blocked")
        self.assertFalse(stub.cognito.calls)
        self.assertFalse(stub.authorizations)

    def test_home_scanner_is_blocked_by_property_not_usable_and_dependents_follow(self):
        stub = DevStub(properties=FakePropertyReference({}))  # property id unknown -> not_found
        _, report, _ = run_suite(stub)
        home = report["journeys"]["home_scanner"]
        self.assertEqual(home["status"], "blocked")
        self.assertIn("property_not_usable at capture admission (Q14", home["reason"])
        placement = report["journeys"]["composer_home_placement"]
        self.assertEqual(placement["status"], "blocked")
        self.assertTrue(placement["reason"].startswith("DEPENDS_ON_HOME_SCANNER: home_scanner blocked"))
        for name in ("object_scanner", "composer", "finder_catalog_link", "finder_query"):
            self.assertEqual(report["journeys"][name]["status"], "passed", name)

    def test_home_scanner_is_blocked_by_dependency_unavailable(self):
        stub = DevStub(properties=FakePropertyReference(unavailable=frozenset({"PROP-VIRTUAL-1"})))
        _, report, _ = run_suite(stub)
        home = report["journeys"]["home_scanner"]
        self.assertEqual(home["status"], "blocked")
        self.assertIn("dependency_unavailable at capture admission", home["reason"])
        self.assertEqual(home["evidence"][-1]["problem_code"], "dependency_unavailable")

    def test_finder_merchant_role_403_and_q14_shop_are_blocked_with_reasons(self):
        _, report, _ = run_suite(DevStub(services=StubServices(merchant_denied=True)))
        link = report["journeys"]["finder_catalog_link"]
        self.assertEqual(link["status"], "blocked")
        self.assertTrue(link["reason"].startswith("MERCHANT_ROLE_NOT_GRANTED"))
        self.assertIn("[F01 create merchant: 403 action_denied]", link["reason"])
        _, report, _ = run_suite(DevStub(services=StubServices(shop_problem="property_not_usable")))
        self.assertIn("property_not_usable at shop registration (Q14", report["journeys"]["finder_catalog_link"]["reason"])
        self.assertEqual(report["journeys"]["finder_query"]["status"], "passed")

    def test_an_api_that_fails_its_smoke_fails_t0_and_blocks_its_journeys(self):
        code, report, _ = run_suite(DevStub(api_down="object-scanner"))
        self.assertEqual(code, 1)
        self.assertEqual(report["tiers"]["T0"]["status"], "failed")
        self.assertIn("object-scanner api smoke", report["tiers"]["T0"]["reason"])
        self.assertTrue(report["journeys"]["object_scanner"]["reason"].startswith("DEPENDS_ON_T0"))
        self.assertTrue(report["journeys"]["composer"]["reason"].startswith("DEPENDS_ON_T0"))
        self.assertEqual(report["result"], "failed")

    def test_unknown_expected_revision_is_blocked_not_passed(self):
        env = env_with_secrets()
        env.pop("WS3D_IT_EXPECTED_REVISIONS")
        _, report, _ = run_suite(DevStub(), env)
        t0 = report["tiers"]["T0"]
        self.assertEqual(t0["status"], "blocked")
        self.assertIn("EXPECTED_REVISION_NOT_AVAILABLE", t0["reason"])

    def test_bearer_tokens_go_only_to_the_four_api_hosts(self):
        stub = DevStub()
        run_suite(stub)
        self.assertTrue(stub.authorizations)
        self.assertTrue(all(a in BEARERS for a in stub.authorizations))
        self.assertEqual(stub.auth_hosts, {urlsplit(api["root"]).hostname for api in journeys.APIS.values()})


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.workflow = yaml.safe_load(cls.text)
        cls.triggers = cls.workflow.get("on", cls.workflow.get(True))
        cls.job = cls.workflow["jobs"]["integration"]

    def test_manual_dispatch_on_main_only_without_aws_or_oidc(self):
        self.assertEqual(list(self.triggers), ["workflow_dispatch"])
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.job["permissions"], {"contents": "read"})
        self.assertEqual(self.job["if"], "github.repository == 'majidsamadi/three-dimension-view-arcore-backend' "
                                         "&& github.ref == 'refs/heads/main'")
        self.assertNotIn("id-token", self.text)
        self.assertNotIn("configure-aws-credentials", self.text)
        self.assertNotIn("AWS_", self.text)

    def test_secrets_reach_the_suite_only_through_env(self):
        step = next(s for s in self.job["steps"] if s.get("name") == "Run the dev integration journeys")
        for name in journeys.SECRET_NAMES:
            self.assertEqual(step["env"][name], "${{ secrets.%s }}" % name)
        self.assertEqual(step["run"], "python -m tools.dev_integration.run --report dist/dev-integration-report.json")
        self.assertNotIn("${{", step["run"])

    def test_report_artifact_and_pinned_actions(self):
        uses = [s["uses"] for s in self.job["steps"] if "uses" in s]
        self.assertEqual(uses, ["actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
                                "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
                                "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"])
        upload = self.job["steps"][-1]
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"]["name"], "dev-integration-${{ github.sha }}-${{ github.run_id }}")
        self.assertEqual(upload["with"]["path"], "dist/dev-integration-report.json")


if __name__ == "__main__":
    unittest.main()
