"""API Gateway REST proxy (v1) Lambda entrypoint.

Status: component-tested (synthetic events, in-memory fakes only).
"""
from __future__ import annotations

import base64
import json
import unittest

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import scenario_wave2 as s
from tests.fakes_wave2 import Harness
from wisestay_home_backend.entrypoints import lambda_handler


def event(method: str, path: str, body=None, *, token: str | None = "token-A", b64: bool = False,
          key: str | None = None, query: dict | None = None, raw: str | None = None) -> dict:
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    if key:
        headers["idempotency-key"] = key
    text = raw if raw is not None else (None if body is None else json.dumps(body))
    if b64 and text is not None:
        text = base64.b64encode(text.encode()).decode()
    return {"resource": "/{proxy+}", "path": path, "httpMethod": method, "headers": headers,
            "multiValueHeaders": {}, "queryStringParameters": query, "pathParameters": None,
            "requestContext": {"requestId": "apigw-req-0001", "stage": "dev"},
            "body": text, "isBase64Encoded": b64}


class LambdaHandlerTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.api = self.h.composition.api

    def _assert_problem(self, result: dict, status: int, code: str) -> None:
        self.assertEqual(result["statusCode"], status)
        self.assertEqual(result["headers"]["Content-Type"], "application/problem+json")
        body = json.loads(result["body"])
        self.assertEqual((body["code"], body["status"]), (code, status))
        self.assertNotIn("Traceback", result["body"])
        self.assertNotIn('File "', result["body"])

    def test_success_events_and_request_id(self):
        created = lambda_handler.handle_event(
            event("POST", "/api/v1/home-captures", s.example_body("H01"), key="idem-capture-0001"),
            self.api)
        self.assertEqual(created["statusCode"], 201)
        self.assertEqual(created["headers"]["X-Request-Id"], "apigw-req-0001")
        self.assertEqual(created["headers"]["Content-Type"], "application/json")
        self.assertFalse(created["isBase64Encoded"])
        listed = lambda_handler.handle_event(event("GET", "/api/v1/home-scenes", query={"limit": "5"}),
                                             self.api)
        self.assertEqual(json.loads(listed["body"]), {"items": [], "next_cursor": None})

    def test_base64_body(self):
        result = lambda_handler.handle_event(
            event("POST", "/api/v1/home-captures", s.example_body("H01"), b64=True,
                  key="idem-capture-0002"), self.api)
        self.assertEqual(result["statusCode"], 201, result["body"])
        bad = event("POST", "/api/v1/home-captures", raw="%%%not-base64", b64=True, key="idem-capture-0003")
        self._assert_problem(lambda_handler.handle_event(bad, self.api), 400, "invalid_request")

    def test_missing_bearer_401(self):
        result = lambda_handler.handle_event(event("GET", "/api/v1/home-scenes", token=None), self.api)
        self._assert_problem(result, 401, "identity_required")
        self.assertEqual(json.loads(result["body"])["request_id"], "apigw-req-0001")

    def test_unknown_route_404(self):
        for method, path in (("GET", "/api/v1/nope"), ("PUT", "/api/v1/home-captures"),
                             ("POST", "/api/v1/home-scenes/scn_x/jobs")):
            self._assert_problem(lambda_handler.handle_event(event(method, path, {}), self.api),
                                 404, "not_found")

    def test_two_megabyte_body_cap(self):
        big = json.dumps({"pad": "x" * 2_000_000})
        result = lambda_handler.handle_event(
            event("POST", "/api/v1/home-captures", raw=big, key="idem-capture-0004"), self.api)
        self._assert_problem(result, 413, "limit_exceeded")
        huge = lambda_handler.handle_event(
            event("POST", "/api/v1/home-captures", raw="x" * 3_000_000), self.api)
        self._assert_problem(huge, 413, "limit_exceeded")

    def test_invalid_json_and_internal_errors_hide_details(self):
        bad = lambda_handler.handle_event(
            event("POST", "/api/v1/home-captures", raw="{not json", key="idem-capture-0005"), self.api)
        self._assert_problem(bad, 400, "invalid_request")

        class Exploding:
            def verify(self, authorization):
                raise RuntimeError("secret internal detail")

        self.api._identity = Exploding()
        with self.assertLogs("wisestay_home_backend.http", level="ERROR"):
            result = lambda_handler.handle_event(event("GET", "/api/v1/home-scenes"), self.api)
        self._assert_problem(result, 503, "dependency_unavailable")
        self.assertNotIn("secret internal detail", result["body"])

    def test_cold_start_without_configuration_is_503(self):
        lambda_handler._API = None
        with self.assertLogs("wisestay_home_backend.lambda", level="ERROR"):
            result = lambda_handler.handler(event("GET", "/api/v1/home-scenes"), None)
        self._assert_problem(result, 503, "dependency_unavailable")
        self.assertIsNone(lambda_handler._API)

    def test_etag_on_get(self):
        ids = s.finalized_scene(self.h)
        result = lambda_handler.handle_event(event("GET", f"/api/v1/home-scenes/{ids['scene_id']}"), self.api)
        self.assertEqual(result["headers"]["ETag"], '"1"')


if __name__ == "__main__":
    unittest.main()
