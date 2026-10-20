"""Router contract test against ``contracts/draft/v0.4/fixtures/api/home-scanner.v0.4.json``.

This is the cross-repo contract the HSA fake client relies on: the route set
must equal the fixture exactly, and every ``request_example`` replayed against
``build_for_tests()`` (seeded by replaying the earlier fixture requests) must
return the fixture status and the fixture response key set.
Status: component-tested (synthetic data, in-memory fakes only).
"""
from __future__ import annotations

import json
import unittest

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import scenario_wave2 as s
from tests.fakes_wave2 import Harness
from tools.check_contract_fixtures_v0_4 import load_fixture
from wisestay_home_backend.domain.scene import ERROR_STATUS
from wisestay_home_backend.http import router
from wisestay_home_backend.http.handlers import Request

FIXTURE = load_fixture("api/home-scanner.v0.4.json")
CONVENTIONS = load_fixture("common/conventions.v0.4.json")
ROUTES = {r["id"]: r for r in FIXTURE["routes"]}

_PUBLISHED = ["H01", "H02", "upload", "H06", "H10", "H12"]
SEEDS = {
    "H01": [], "H02": ["H01"], "H03": ["H01", "H02", "upload"], "H04": ["H01", "H02"],
    "H05": ["H01", "H02"], "H06": ["H01", "H02", "upload"], "H07": _PUBLISHED,
    "H08": _PUBLISHED, "H09": _PUBLISHED, "H10": ["H01", "H02", "upload", "H06"],
    "H11": ["H01", "H02", "upload", "H06", "H10"], "H12": ["H01", "H02", "upload", "H06", "H10"],
    "H13": _PUBLISHED, "H14": _PUBLISHED, "H15": _PUBLISHED + ["H14"],
    "H16": _PUBLISHED + ["H14"],
}


def replay(h: Harness, route_id: str):
    if route_id == "upload":
        h.storage.client_upload("staging/upl_01HZYSYNTH0000000000000001/main", s.GLB)
        return None
    route = ROUTES[route_id]
    example = route["request_example"]
    path = route["path"]
    for name, value in example["path_params"].items():
        path = path.replace("{" + name + "}", value)
    body = example["body"]
    request = Request(route["method"], router.API_PREFIX + path, dict(example["headers"]),
                      {k: str(v) for k, v in example["query"].items()},
                      None if body is None else json.dumps(body).encode(), "req-contract")
    return h.composition.api.dispatch(request)


class HomeScannerContractTests(unittest.TestCase):
    def test_HSB_routes_match_v0_4_fixture(self):
        fixture_routes = {(r["id"], r["method"], r["path"]) for r in FIXTURE["routes"]}
        self.assertEqual(fixture_routes, {(r.route_id, r.method, r.path) for r in router.ROUTES})
        for route in router.ROUTES:
            spec = ROUTES[route.route_id]
            with self.subTest(route=route.route_id):
                self.assertEqual(route.idempotent, spec["idempotency_key"] == "required")
                self.assertEqual(route.status, spec["response_status"])
                segments = set(spec["path"].strip("/").split("/"))
                self.assertFalse(segments & set(CONVENTIONS["bff"]["forbidden_path_segments"]))
                self.assertIn(route.method, CONVENTIONS["bff"]["methods"])

    def test_HSB_request_examples_replay_with_fixture_status_and_keys(self):
        for route_id, spec in ROUTES.items():
            with self.subTest(route=route_id):
                h = Harness()
                for step in SEEDS[route_id]:
                    seeded = replay(h, step)
                    if seeded is not None:
                        self.assertLess(seeded.status, 300, (step, seeded.body))
                response = replay(h, route_id)
                self.assertEqual(response.status, spec["response_status"], response.body)
                expected = spec["response_example"]
                self.assertEqual(set(response.body), set(expected))
                for key, value in expected.items():
                    if key.endswith("_id") and isinstance(value, str):
                        self.assertEqual(response.body[key], value, key)
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        self.assertEqual([set(i) for i in response.body[key]], [set(i) for i in value])
                if route_id == "H16":
                    self.assertEqual(response.body["expires_at"], expected["expires_at"])
                self.assertEqual(response.headers["Content-Type"], "application/json")

    def test_HSB_error_codes_are_in_closed_table(self):
        table = {code: int(status) for status, codes in CONVENTIONS["error_codes"].items()
                 for code in codes}
        self.assertEqual(table, ERROR_STATUS)
        for spec in FIXTURE["routes"]:
            for error in spec["errors"]:
                with self.subTest(route=spec["id"], code=error["code"]):
                    self.assertEqual(ERROR_STATUS[error["code"]], error["status"])

    def test_HSB_absent_jobs_route_and_unknown_paths_404(self):
        h = Harness()
        for path in ("/api/v1/home-scenes/scn_01HZYSYNTH0000000000000001/jobs", "/api/v1/health",
                     "/home-captures", "/api/v2/home-captures"):
            with self.subTest(path=path):
                response = h.composition.api.dispatch(Request("POST", path, {}, {}, b"{}", "r"))
                self.assertEqual((response.status, response.body["code"]), (404, "not_found"))

    def test_HSB_idempotency_conventions(self):
        h = Harness()
        missing = h.call("POST", "/home-captures", s.example_body("H01"), key=None)
        self.assertEqual((missing.status, missing.body["code"]), (400, "idempotency_key_required"))
        short = h.call("POST", "/home-captures", s.example_body("H01"), key="short")
        self.assertEqual(short.status, 400)
        first = h.call("POST", "/home-captures", s.example_body("H01"), key="idem-capture-0001")
        again = h.call("POST", "/home-captures", s.example_body("H01"), key="idem-capture-0001")
        self.assertEqual((first.status, first.body), (again.status, again.body))
        reuse = h.call("POST", "/home-captures", {**s.example_body("H01"), "purpose": "planning"},
                       key="idem-capture-0001")
        self.assertEqual((reuse.status, reuse.body["code"]), (409, "idempotency_key_reuse"))
        other_user = h.call("POST", "/home-captures", s.example_body("H01"), key="idem-capture-0001",
                            token="token-B")
        self.assertEqual(other_user.status, 201)
        self.assertNotEqual(other_user.body["capture_id"], first.body["capture_id"])
        h.clock.advance(24 * 3600)
        expired = h.call("POST", "/home-captures", s.example_body("H01"), key="idem-capture-0001")
        self.assertNotEqual(expired.body["capture_id"], first.body["capture_id"])

    def test_HSB_problem_shape_and_identity(self):
        h = Harness()
        unauth = h.call("GET", "/home-scenes", token=None)
        self.assertEqual(unauth.status, 401)
        self.assertEqual(unauth.headers["Content-Type"], "application/problem+json")
        self.assertEqual(unauth.body, {"type": "https://wizestay.com/problems/identity_required",
                                       "title": "Sign-in is required", "status": 401,
                                       "code": "identity_required", "request_id": "req-test"})
        h.identity.unavailable = True
        down = h.call("GET", "/home-scenes")
        self.assertEqual((down.status, down.body["code"]), (503, "identity_unavailable"))

    def test_HSB_list_pagination_without_totals(self):
        h = Harness()
        for _ in range(3):
            s.finalized_scene(h)
        page = h.call("GET", "/home-scenes", query={"limit": 2})
        self.assertEqual(len(page.body["items"]), 2)
        self.assertIsNotNone(page.body["next_cursor"])
        rest = h.call("GET", "/home-scenes", query={"limit": 2, "cursor": page.body["next_cursor"]})
        self.assertEqual(len(rest.body["items"]), 1)
        self.assertIsNone(rest.body["next_cursor"])
        ids = [i["scene_id"] for i in page.body["items"] + rest.body["items"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(set(page.body), {"items", "next_cursor"})
        for bad in ({"limit": 0}, {"limit": 51}, {"cursor": "!!"}):
            self.assertEqual(h.call("GET", "/home-scenes", query=bad).status, 400)


if __name__ == "__main__":
    unittest.main()
