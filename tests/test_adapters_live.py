"""Live adapters against injected stubs only (HSB-01.3+, X.6, X.7, X.9).

No network and no boto3 import: JWKS fetch, Resvanta transport, SSM, DynamoDB
and S3 clients are all stubs that record their calls.
Status: component-tested (synthetic data only).
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import sys
import unittest

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import rsa_test_key as key
from wisestay_home_backend.adapters import rs256
from wisestay_home_backend.adapters.central_identity import CentralJwtIdentityVerifier
from wisestay_home_backend.adapters.dynamodb_repository import DynamoDbRepository
from wisestay_home_backend.adapters.jwks import HttpJwksSource, StaticJwksSource
from wisestay_home_backend.adapters.request_identity_facts import RequestIdentityFacts
from wisestay_home_backend.adapters.resvanta_property_reference import (
    ResvantaHttpPropertyReference,
    SsmCredentialSource,
)
from wisestay_home_backend.adapters.s3_object_storage import S3ObjectStorage
from wisestay_home_backend.domain.asset_reference import IdentityFactStatus, IdentityRequired
from wisestay_home_backend.entrypoints.composition import build_live
from wisestay_home_backend.ports.commercial_gate import ConfigurationError
from wisestay_home_backend.ports.identity import IdentityUnavailable, RsaPublicKey
from wisestay_home_backend.ports.property_reference import UnconfiguredPropertyReference
from wisestay_home_backend.ports.repository import (
    Check,
    ConditionFailed,
    Item,
    Put,
    RepositoryUnavailable,
)

ISSUER = "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_SYNTHETIC"
CLIENT = "synthetic-um-client"
NOW = 1_792_454_400
PUBLIC = RsaPublicKey(key.N, key.E)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign(claims: dict, *, header: dict | None = None, d: int = key.D) -> str:
    head = b64url(json.dumps(header or {"alg": "RS256", "kid": key.KID}).encode())
    body = b64url(json.dumps(claims).encode())
    signing_input = f"{head}.{body}".encode()
    k = (key.N.bit_length() + 7) // 8
    em = rs256.emsa_pkcs1_v1_5_sha256(signing_input, k)
    signature = pow(int.from_bytes(em, "big"), d, key.N).to_bytes(k, "big")
    return f"Bearer {head}.{body}.{b64url(signature)}"


def claims(**overrides) -> dict:
    base = {"iss": ISSUER, "token_use": "access", "client_id": CLIENT, "sub": "USER-A",
            "exp": NOW + 600, "iat": NOW - 10}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def verifier(jwks=None) -> CentralJwtIdentityVerifier:
    return CentralJwtIdentityVerifier(ISSUER, CLIENT, "home-scanner",
                                      jwks or StaticJwksSource({key.KID: PUBLIC}), lambda: NOW)


def jwks_document(kid: str = key.KID) -> bytes:
    def enc(n: int) -> str:
        return b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))
    return json.dumps({"keys": [{"kty": "RSA", "kid": kid, "alg": "RS256", "use": "sig",
                                 "n": enc(key.N), "e": enc(key.E)}]}).encode()


class CentralIdentityTests(unittest.TestCase):
    def test_good_token_verifies_and_maps_to_identity_facts(self):
        verified = verifier().verify(sign(claims()))
        self.assertEqual((verified.user_id, verified.application_id, verified.client_id,
                          verified.expires_at), ("USER-A", "home-scanner", CLIENT, NOW + 600))
        fact = RequestIdentityFacts(verified).current_identity()
        self.assertEqual(fact.status, IdentityFactStatus.CURRENT)
        self.assertEqual((fact.context.user_id, fact.context.application_id), ("USER-A", "home-scanner"))

    def test_rejections_are_identity_required(self):
        good = sign(claims())
        head, body, sig = good[len("Bearer "):].split(".")
        flipped = b64url(bytes([base64.urlsafe_b64decode(sig + "==")[0] ^ 1])
                         + base64.urlsafe_b64decode(sig + "==")[1:])
        cases = {
            "missing": None, "not bearer": "Basic abc", "two segments": f"Bearer {head}.{body}",
            "too long": "Bearer " + "a" * 12_001,
            "bad signature": f"Bearer {head}.{body}.{flipped}",
            "wrong key": sign(claims(), d=key.D - 2),
            "wrong iss": sign(claims(iss=ISSUER + "x")),
            "wrong client_id": sign(claims(client_id="other-client")),
            "id token": sign(claims(token_use="id")),
            "expired": sign(claims(exp=NOW - 61)),
            "future iat": sign(claims(iat=NOW + 61)),
            "future nbf": sign(claims(nbf=NOW + 61)),
            "empty sub": sign(claims(sub="")),
            "hs256": sign(claims(), header={"alg": "HS256", "kid": key.KID}),
            "no kid": sign(claims(), header={"alg": "RS256"}),
            "unknown kid": sign(claims(), header={"alg": "RS256", "kid": "other"}),
        }
        for name, authorization in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(IdentityRequired):
                    verifier().verify(authorization)
        verifier().verify(sign(claims(exp=NOW - 59)))  # inside the 60 s leeway

    def test_small_or_wrong_exponent_key_rejected(self):
        self.assertFalse(rs256.acceptable_key(key.N >> 1100, 65537))
        self.assertFalse(rs256.acceptable_key(key.N, 3))
        weak = StaticJwksSource({key.KID: RsaPublicKey(key.N, 3)})
        with self.assertRaises(IdentityRequired):
            verifier(weak).verify(sign(claims()))

    def test_unknown_kid_refreshes_once_then_rate_limited(self):
        fetched = []
        documents = [jwks_document("old-kid"), jwks_document(key.KID)]
        clock = [0.0]

        def fetch(url, timeout):
            fetched.append((url, timeout))
            return documents[min(len(fetched) - 1, 1)]

        jwks = HttpJwksSource(ISSUER + "/.well-known/jwks.json", fetch=fetch, clock=lambda: clock[0])
        self.assertEqual(verifier(jwks).verify(sign(claims())).user_id, "USER-A")
        self.assertEqual(fetched, [(ISSUER + "/.well-known/jwks.json", 3)] * 2)
        unknown = sign(claims(), header={"alg": "RS256", "kid": "never"})
        with self.assertRaises(IdentityRequired):
            verifier(jwks).verify(unknown)
        self.assertEqual(len(fetched), 2)  # the refresh 0 s ago is within the 60 s window
        clock[0] = 61.0
        with self.assertRaises(IdentityRequired):
            verifier(jwks).verify(unknown)
        self.assertEqual(len(fetched), 3)

    def test_jwks_failure_is_identity_unavailable_503(self):
        def broken(url, timeout):
            raise OSError("synthetic network failure")

        with self.assertRaises(IdentityUnavailable):
            verifier(HttpJwksSource(ISSUER + "/.well-known/jwks.json", fetch=broken)).verify(sign(claims()))
        with self.assertRaises(IdentityUnavailable):
            verifier(HttpJwksSource("x", fetch=lambda u, t: b"not json")).verify(sign(claims()))


class StubDynamo:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.error = error
        self.items: dict = {}

    def transact_write_items(self, **kwargs):
        self.calls.append(("transact_write_items", kwargs))
        if self.error:
            raise self.error

    def get_item(self, **kwargs):
        self.calls.append(("get_item", kwargs))
        return {"Item": self.items} if self.items else {}

    def query(self, **kwargs):
        self.calls.append(("query", kwargs))
        return {"Items": [], "LastEvaluatedKey": {"pk": {"S": "a"}, "sk": {"S": "b"}}}


class AwsError(Exception):
    def __init__(self, code: str, reasons=None) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}
        if reasons is not None:
            self.response["CancellationReasons"] = reasons


class DynamoDbAdapterTests(unittest.TestCase):
    def test_transact_items_carry_condition_expressions(self):
        stub = StubDynamo()
        repo = DynamoDbRepository("wisestay-dev-home-scanner", stub, clock=lambda: NOW)
        repo.transact([
            Put(Item("SCENE#s", "META", 1, {"a": [1, 2.5, None, True, {"b": "c"}]},
                     gsi1pk="OWNER#u", gsi1sk="SCENE#t#s"), "absent"),
            Put(Item("UPLOAD#u", "META", 9, {"state": "open"}, ttl_epoch=NOW + 5), "version", 3),
            Check("CAPTURE#c", "META", 2),
        ])
        items = stub.calls[0][1]["TransactItems"]
        absent, versioned, check = items
        self.assertEqual(absent["Put"]["ConditionExpression"],
                         "attribute_not_exists(pk) OR (attribute_exists(ttl_epoch) AND ttl_epoch <= :now)")
        self.assertEqual(absent["Put"]["Item"]["data"]["M"]["a"]["L"][1], {"N": "2.5"})
        self.assertEqual(absent["Put"]["Item"]["gsi1pk"], {"S": "OWNER#u"})
        self.assertEqual(versioned["Put"]["ConditionExpression"], "#v = :expected")
        self.assertEqual(versioned["Put"]["ExpressionAttributeValues"], {":expected": {"N": "3"}})
        self.assertEqual(versioned["Put"]["Item"]["version"], {"N": "4"})
        self.assertEqual(versioned["Put"]["Item"]["ttl_epoch"], {"N": str(NOW + 5)})
        self.assertEqual(check["ConditionCheck"]["Key"], {"pk": {"S": "CAPTURE#c"}, "sk": {"S": "META"}})
        self.assertEqual({i[next(iter(i))]["TableName"] for i in items}, {"wisestay-dev-home-scanner"})

    def test_errors_map_to_condition_failed_or_unavailable(self):
        cancelled = AwsError("TransactionCanceledException", [{"Code": "None"}, {"Code": "ConditionalCheckFailed"}])
        with self.assertRaises(ConditionFailed):
            DynamoDbRepository("t", StubDynamo(cancelled)).transact([Check("a", "b", 1)])
        throttled = AwsError("TransactionCanceledException", [{"Code": "ThrottlingError"}])
        for error in (throttled, AwsError("ProvisionedThroughputExceededException"), OSError("x")):
            with self.assertRaises(RepositoryUnavailable):
                DynamoDbRepository("t", StubDynamo(error)).transact([Check("a", "b", 1)])

    def test_get_treats_expired_ttl_as_absent_and_query_cursor_round_trips(self):
        stub = StubDynamo()
        stub.items = {"pk": {"S": "IDEMP#x"}, "sk": {"S": "META"}, "version": {"N": "1"},
                      "data": {"M": {"n": {"N": "7"}}}, "ttl_epoch": {"N": str(NOW)}}
        self.assertIsNone(DynamoDbRepository("t", stub, clock=lambda: NOW).get("IDEMP#x", "META"))
        live = DynamoDbRepository("t", stub, clock=lambda: NOW - 1).get("IDEMP#x", "META")
        self.assertEqual(live.data, {"n": 7})
        repo = DynamoDbRepository("t", stub)
        _, cursor = repo.query_gsi1("OWNER#u", "SCENE#", limit=5, cursor=None)
        repo.query("SCENE#s", "GRANT#", limit=5, cursor=cursor)
        gsi_call, base_call = stub.calls[-2][1], stub.calls[-1][1]
        self.assertEqual(gsi_call["IndexName"], "gsi1")
        self.assertEqual(base_call["ExclusiveStartKey"], {"pk": {"S": "a"}, "sk": {"S": "b"}})
        self.assertTrue(base_call["ConsistentRead"])


class StubS3:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803 - boto3 names
        self.calls.append((operation, {"Params": Params, "ExpiresIn": ExpiresIn}))
        return f"https://bucket.s3.example.invalid/{Params['Key']}?X-Amz-Signature=synthetic"

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        if kwargs["Key"] == "missing":
            raise AwsError("404")
        return {"ContentLength": 812, "ChecksumSHA256": "abc="}

    def copy_object(self, **kwargs):
        self.calls.append(("copy_object", kwargs))


class S3AdapterTests(unittest.TestCase):
    def test_presigned_put_binds_checksum_and_length(self):
        stub = StubS3()
        storage = S3ObjectStorage("wisestay-dev-home-scanner-assets-511831442607", stub,
                                  clock=lambda: datetime(2026, 10, 20, tzinfo=timezone.utc))
        digest = base64.b64encode(hashlib.sha256(b"x").digest()).decode()
        signed = storage.presign_put("staging/u/main", sha256_b64=digest, content_length=1)
        operation, call = stub.calls[0]
        self.assertEqual(operation, "put_object")
        self.assertEqual(call, {"Params": {"Bucket": "wisestay-dev-home-scanner-assets-511831442607",
                                           "Key": "staging/u/main", "ChecksumSHA256": digest,
                                           "ContentLength": 1}, "ExpiresIn": 900})
        self.assertEqual(signed.headers, {"x-amz-checksum-sha256": digest, "content-length": "1"})
        self.assertEqual(signed.expires_at, "2026-10-20T00:15:00Z")
        storage.presign_get("versions/abc")
        self.assertEqual(stub.calls[1], ("get_object", {"Params": {
            "Bucket": "wisestay-dev-home-scanner-assets-511831442607", "Key": "versions/abc"},
            "ExpiresIn": 300}))

    def test_head_uses_checksum_mode_and_missing_is_none(self):
        stub = StubS3()
        storage = S3ObjectStorage("b", stub)
        self.assertEqual(storage.head("k").checksum_sha256_b64, "abc=")
        self.assertEqual(stub.calls[0][1]["ChecksumMode"], "ENABLED")
        self.assertIsNone(storage.head("missing"))
        storage.copy("staging/u/main", "versions/abc")
        self.assertEqual(stub.calls[-1][1]["CopySource"], {"Bucket": "b", "Key": "staging/u/main"})


class ResvantaAdapterTests(unittest.TestCase):
    def _adapter(self, status: int = 200, body: bytes = b"", error: Exception | None = None):
        calls = []

        def transport(method, url, headers, timeout):
            calls.append((method, url, headers, timeout))
            if error:
                raise error
            return status, body

        class Credential:
            reads = 0

            def get(self):
                Credential.reads += 1
                return "rv1.synthetic"

        credential = Credential()
        adapter = ResvantaHttpPropertyReference(
            "https://1noccvrfkk.execute-api.ap-southeast-1.amazonaws.com/v1", credential, transport,
            clock=lambda: "2026-10-20T00:00:00Z")
        return adapter, calls, credential

    def test_status_mapping(self):
        real = json.dumps({"id": "PROP-REAL-UNLISTED-1", "property_type": "REAL", "version": 2,
                           "bookable": True}).encode()
        adapter, calls, _ = self._adapter(200, real)
        fact = adapter.resolve("PROP-REAL-UNLISTED-1")
        self.assertEqual((fact.status, fact.property_type, fact.record_version, fact.bookable),
                         ("current", "REAL", 2, False))
        method, url, headers, timeout = calls[0]
        self.assertEqual((method, url, timeout), (
            "GET", "https://1noccvrfkk.execute-api.ap-southeast-1.amazonaws.com/v1/properties/PROP-REAL-UNLISTED-1", 3))
        self.assertEqual(headers["Authorization"], "Bearer rv1.synthetic")
        for status in (401, 403, 404):
            self.assertEqual(self._adapter(status)[0].resolve("PROP-1").status, "not_found")
        unavailable = [self._adapter(500)[0], self._adapter(503)[0], self._adapter(200, b"{bad")[0],
                       self._adapter(200, json.dumps({"id": "PROP-1", "property_type": "HOTEL",
                                                       "version": 1}).encode())[0],
                       self._adapter(error=TimeoutError("3 s"))[0]]
        for adapter in unavailable:
            self.assertEqual(adapter.resolve("PROP-1").status, "unavailable")
        self.assertEqual(self._adapter(200, real)[0].resolve("../etc").status, "not_found")
        self.assertEqual(UnconfiguredPropertyReference().resolve("PROP-1").status, "unavailable")

    def test_ssm_credential_read_once(self):
        class StubSsm:
            calls = []

            def get_parameter(self, **kwargs):
                self.calls.append(kwargs)
                return {"Parameter": {"Value": "rv1.synthetic"}}

        stub = StubSsm()
        source = SsmCredentialSource("/wisestay/dev/home-scanner/resvanta-credential", stub)
        self.assertEqual((source.get(), source.get()), ("rv1.synthetic", "rv1.synthetic"))
        self.assertEqual(stub.calls, [{"Name": "/wisestay/dev/home-scanner/resvanta-credential",
                                       "WithDecryption": True}])


class CompositionTests(unittest.TestCase):
    def test_build_live_refuses_missing_or_wrong_environment(self):
        with self.assertRaises(ConfigurationError):
            build_live({})
        env = {"WISESTAY_ENVIRONMENT": "production", "TABLE_NAME": "t", "ASSET_BUCKET": "b",
               "CENTRAL_ISSUER": ISSUER, "CENTRAL_CLIENT_ID": CLIENT}
        with self.assertRaises(ConfigurationError):
            build_live(env)
        with self.assertRaises(ConfigurationError):
            build_live({**env, "WISESTAY_ENVIRONMENT": "dev", "CENTRAL_ISSUER": "https://evil.example"})

    def test_no_test_imports_boto3(self):
        self.assertNotIn("boto3", sys.modules)


if __name__ == "__main__":
    unittest.main()
