"""Guarded dev deployment (wave 3 plan §6.2.2). Fake gh/aws/terraform only: no network, no AWS."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import tests  # noqa: F401  -- puts src/ on sys.path
from deployment.deploy import (
    ACCOUNT,
    Completed,
    Deployment,
    Stop,
    admit_plan,
    package_digest,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "deployment" / "dev.config.json").read_text(encoding="utf-8"))
ACTIVATION = json.loads((ROOT / "deployment" / "activation.json").read_text(encoding="utf-8"))
SHA = "0123456789abcdef0123456789abcdef01234567"
ROLE_SESSION = "arn:aws:sts::511831442607:assumed-role/wisestay-dev-home-scanner-deploy/home-scanner-deploy-1"


def change(kind: str, name: str, actions: list[str], after: dict, unknown: dict | None = None) -> dict:
    return {"address": f"{kind}.{name}", "mode": "managed", "type": kind, "name": name,
            "change": {"actions": actions, "after": after, "after_unknown": unknown or {}}}


def first_plan() -> dict:
    """A first-apply plan shaped like `terraform show -json` for infra/application."""
    res = CONFIG["resources"]
    host = CONFIG["api_host"]
    zone = res["hosted_zone_id"]
    return {"prior_state": {"values": {"root_module": {}}}, "resource_changes": [
        {"address": "data.aws_caller_identity.current", "mode": "data", "type": "aws_caller_identity",
         "change": {"actions": ["read"]}},
        change("terraform_data", "guard", ["create"], {"input": ACCOUNT}),
        change("aws_iam_role", "api", ["create"], {"name": res["runtime_role"]}),
        change("aws_iam_role_policy", "api", ["create"], {"name": res["runtime_policy"]}, {"role": True}),
        change("aws_cloudwatch_log_group", "api", ["create"], {"name": res["log_group"]}),
        change("aws_lambda_function", "api", ["create"], {"function_name": res["function"]}),
        change("aws_lambda_permission", "api_gateway", ["create"], {"function_name": res["function"]}),
        change("aws_dynamodb_table", "service", ["create"], {"name": res["table"]}),
        change("aws_s3_bucket", "assets", ["create"], {"bucket": res["bucket"]}),
        change("aws_s3_bucket_policy", "assets", ["create"], {}, {"bucket": True}),
        change("aws_s3_bucket_cors_configuration", "assets", ["create"], {}, {"bucket": True}),
        change("aws_api_gateway_rest_api", "api", ["create"], {"name": res["function"]}),
        change("aws_api_gateway_deployment", "api", ["create"], {}),
        change("aws_api_gateway_stage", "dev", ["create"], {"stage_name": "dev"}),
        change("aws_acm_certificate", "api", ["create"], {"domain_name": host}),
        change("aws_route53_record", "certificate_validation", ["create"], {"zone_id": zone}, {"name": True}),
        change("aws_api_gateway_domain_name", "api", ["create"], {"domain_name": host}),
        change("aws_api_gateway_base_path_mapping", "api", ["create"], {}, {"domain_name": True}),
        change("aws_route53_record", "api", ["create"], {"zone_id": zone, "name": host}),
    ]}


class FakeTools:
    """Answers gh/aws/terraform argv like the runner does; records every call."""

    def __init__(self, root: Path):
        self.root = root
        self.calls: list[list[str]] = []
        self.main_sha = [SHA, SHA]
        self.caller = {"Account": ACCOUNT, "Arn": ROLE_SESSION}
        self.unreserved = 900
        self.function_exists = False
        self.plan = first_plan()
        self.code_sha = None
        self.fail_phase: str | None = None
        self.fail_text = ""

    def __call__(self, argv: list[str], *, env=None, timeout=0) -> Completed:  # noqa: ARG002
        self.calls.append(list(argv))
        tool = argv[0]
        if tool == "gh":
            return Completed(0, self.main_sha.pop(0) + "\n", "")
        if tool == "aws":
            return self.aws(argv[1:])
        return self.terraform(argv[2:])

    def aws(self, args: list[str]) -> Completed:
        if args[:2] == ["sts", "get-caller-identity"]:
            return Completed(0, json.dumps(self.caller), "")
        if args[:2] == ["lambda", "get-account-settings"]:
            return Completed(0, json.dumps({"AccountLimit": {"UnreservedConcurrentExecutions": self.unreserved}}), "")
        if args[:2] == ["lambda", "get-function-concurrency"]:
            if not self.function_exists:
                return Completed(254, "", "An error occurred (ResourceNotFoundException) when calling the "
                                          "GetFunctionConcurrency operation: Function not found")
            return Completed(0, json.dumps({"ReservedConcurrentExecutions": 5}), "")
        if args[:2] == ["lambda", "get-function-configuration"]:
            return Completed(0, json.dumps({"CodeSha256": self.code_sha, "LastModified": "2026-10-20T00:00:00Z"}), "")
        raise AssertionError(args)

    def terraform(self, args: list[str]) -> Completed:
        phase = args[0]
        if phase == self.fail_phase:
            return Completed(1, "", self.fail_text)
        if phase == "apply":
            self.function_exists = True
        if phase == "show":
            return Completed(0, json.dumps(self.plan), "")
        if phase == "output":
            return Completed(0, json.dumps({"function_name": {"value": CONFIG["resources"]["function"]},
                                            "api_root": {"value": CONFIG["api_root"]},
                                            "rest_api_id": {"value": "abc123"}}), "")
        return Completed(0, "ok", "provider detail that must stay private")


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "dist").mkdir()
        self.package = self.root / CONFIG["lambda_package"]
        self.package.write_bytes(b"synthetic lambda package")
        self.activation = self.root / "activation.json"
        self.write_activation(ACTIVATION)
        self.tools = FakeTools(self.root)
        self.tools.code_sha = package_digest(self.package)
        self.probes: list[tuple[int | None, str]] = [(401, "application/problem+json")]
        self.sleeps: list[float] = []
        self.clock = [0.0]
        self.env = {"GITHUB_REPOSITORY": CONFIG["repository"], "GITHUB_REF": "refs/heads/main",
                    "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "77", "GITHUB_RUN_ATTEMPT": "1",
                    "RUNNER_TEMP": str(self.root)}

    def write_activation(self, value: dict) -> None:
        self.activation.write_text(json.dumps(value), encoding="utf-8")

    def probe(self, url: str):
        self.assertEqual(url, "https://home-scanner.dev.wizestay.com/api/v1/home-scenes")
        return self.probes.pop(0) if len(self.probes) > 1 else self.probes[0]

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock[0] += seconds

    def deploy(self) -> tuple[int, dict]:
        receipt = self.root / "dist" / "deployment-receipt.json"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = Deployment(config=CONFIG, activation_path=self.activation, terraform="terraform",
                              receipt_path=receipt, env=self.env, run=self.tools, probe=self.probe,
                              sleep=self.sleep, monotonic=lambda: self.clock[0], root=self.root).main()
        stored = json.loads(receipt.read_text(encoding="utf-8"))
        # The job log carries only the result and the closed failure label.
        self.assertEqual(json.loads(printed.getvalue()), {"result": stored["result"], "failure": stored["failure"]})
        return code, stored

    def phases(self) -> list[str]:
        return [call[2] for call in self.tools.calls if call[0] == "terraform"]

    def test_happy_path_applies_saved_plan_and_writes_receipt(self):
        code, receipt = self.deploy()
        self.assertEqual(code, 0)
        self.assertEqual(receipt["result"], "deployed")
        self.assertIsNone(receipt["failure"])
        self.assertEqual(self.phases(), ["init", "plan", "show", "apply", "output"])
        apply = next(call for call in self.tools.calls if call[:1] == ["terraform"] and call[2] == "apply")
        plan = next(call for call in self.tools.calls if call[:1] == ["terraform"] and call[2] == "plan")
        saved = next(arg for arg in plan if arg.startswith("-out=")).removeprefix("-out=")
        self.assertEqual(apply[-1], saved)
        self.assertFalse(Path(saved).parent.exists(), "private plan directory must be removed")
        init = next(call for call in self.tools.calls if call[:1] == ["terraform"] and call[2] == "init")
        self.assertIn("-lockfile=readonly", init)
        self.assertEqual(receipt["contract"], "wisestay.3d.deployment-receipt.v1")
        self.assertEqual(receipt["state_key"], "wisestay/dev/three-dimension-view-arcore-backend/application.tfstate")
        self.assertEqual(receipt["caller_arn"], ROLE_SESSION)
        self.assertEqual(receipt["account"], ACCOUNT)
        self.assertEqual(receipt["revision"], SHA)
        self.assertEqual(receipt["run_id"], "77")
        self.assertEqual(receipt["account_unreserved_concurrency_before"], 900)
        self.assertEqual(receipt["lambda_package_sha256_b64"], self.tools.code_sha)
        self.assertEqual(receipt["function_last_modified"], "2026-10-20T00:00:00Z")
        self.assertEqual(receipt["plan_summary"]["aws_lambda_function"], {"create": 1})
        self.assertEqual(receipt["smoke"]["result"], "passed")
        self.assertEqual(receipt["smoke"]["status"], 401)
        self.assertNotIn("provider detail", json.dumps(receipt))
        # The second main check runs after admission and before apply.
        gh_calls = [index for index, call in enumerate(self.tools.calls) if call[0] == "gh"]
        apply_index = self.tools.calls.index(apply)
        self.assertEqual(len(gh_calls), 2)
        self.assertLess(gh_calls[1], apply_index)

    def test_activation_disabled_is_held_before_any_tool(self):
        self.write_activation({**ACTIVATION, "enabled": False})
        code, receipt = self.deploy()
        self.assertEqual(code, 0)
        self.assertEqual(receipt["result"], "held")
        self.assertEqual(receipt["failure"]["label"], "ACTIVATION_DISABLED")
        self.assertEqual(self.tools.calls, [])

    def test_wrong_approval_reference_is_held(self):
        self.write_activation({**ACTIVATION, "approval_reference": "something-else"})
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["result"]), (0, "held"))
        self.assertEqual(self.tools.calls, [])

    def test_wrong_account_refused_before_init(self):
        self.tools.caller = {"Account": "443217925086", "Arn": "arn:aws:sts::443217925086:assumed-role/x/y"}
        code, receipt = self.deploy()
        self.assertEqual(code, 1)
        self.assertEqual(receipt["failure"]["label"], "WRONG_ACCOUNT")
        self.assertEqual(self.phases(), [])

    def test_wrong_role_refused_before_init(self):
        self.tools.caller = {"Account": ACCOUNT, "Arn": "arn:aws:sts::511831442607:assumed-role/wisestay-dev-finder-deploy/x"}
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "WRONG_DEPLOY_ROLE"))
        self.assertEqual(self.phases(), [])

    def test_superseded_main_refused_before_credentials_are_used(self):
        self.tools.main_sha = ["f" * 40]
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "SUPERSEDED_MAIN"))
        self.assertFalse([call for call in self.tools.calls if call[0] in ("aws", "terraform")])

    def test_main_superseded_during_plan_blocks_apply(self):
        self.tools.main_sha = [SHA, "e" * 40]
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "SUPERSEDED_MAIN"))
        self.assertNotIn("apply", self.phases())

    def test_branch_run_refused(self):
        self.env["GITHUB_REF"] = "refs/heads/feature/3d-wave3"
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "NOT_MAIN_OF_REPOSITORY"))
        self.assertEqual(self.tools.calls, [])

    def test_concurrency_floor_holds_new_function(self):
        self.tools.unreserved = 104
        code, receipt = self.deploy()
        self.assertEqual(code, 1)
        self.assertEqual(receipt["result"], "held")
        self.assertEqual(receipt["failure"]["label"], "ACCOUNT_CONCURRENCY_FLOOR")
        self.assertEqual(receipt["account_unreserved_concurrency_before"], 104)
        self.assertEqual(self.phases(), [])

    def test_existing_reservation_is_not_counted_twice(self):
        self.tools.unreserved = 100
        self.tools.function_exists = True
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["result"]), (0, "deployed"))

    def test_plan_with_delete_refused(self):
        self.tools.plan["resource_changes"].append(
            change("aws_dynamodb_table", "service", ["delete"], None))
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "PLAN_DESTRUCTIVE_CHANGE"))
        self.assertNotIn("apply", self.phases())

    def test_replacement_refused_except_api_deployment(self):
        plan = first_plan()
        plan["resource_changes"].append(change("aws_api_gateway_deployment", "api", ["create", "delete"], {}))
        self.assertEqual(admit_plan(plan, CONFIG)["aws_api_gateway_deployment"], {"create": 1, "replace": 1})
        plan["resource_changes"].append(change("aws_lambda_function", "api", ["delete", "create"],
                                               {"function_name": CONFIG["resources"]["function"]}))
        with self.assertRaises(Stop) as stop:
            admit_plan(plan, CONFIG)
        self.assertEqual(stop.exception.label, "PLAN_DESTRUCTIVE_CHANGE")

    def test_foreign_name_refused(self):
        self.tools.plan["resource_changes"].append(
            change("aws_s3_bucket", "other", ["create"], {"bucket": "someone-elses-bucket"}))
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "PLAN_FOREIGN_NAME"))
        self.assertNotIn("apply", self.phases())

    def test_foreign_record_and_unknown_primary_name_refused(self):
        plan = first_plan()
        plan["resource_changes"].append(change("aws_route53_record", "x", ["create"],
                                               {"zone_id": CONFIG["resources"]["hosted_zone_id"],
                                                "name": "owner.wizestay.com"}))
        with self.assertRaises(Stop):
            admit_plan(plan, CONFIG)
        plan = first_plan()
        plan["resource_changes"].append(change("aws_lambda_function", "y", ["create"], {}, {"function_name": True}))
        with self.assertRaises(Stop):
            admit_plan(plan, CONFIG)

    def test_unexpected_type_and_module_refused(self):
        plan = first_plan()
        plan["resource_changes"].append(change("aws_iam_user", "x", ["create"], {"name": "x"}))
        with self.assertRaises(Stop) as stop:
            admit_plan(plan, CONFIG)
        self.assertEqual(stop.exception.label, "PLAN_UNEXPECTED_TYPE")
        plan = first_plan()
        moved = copy.deepcopy(plan["resource_changes"][2])
        moved["address"] = "module.other." + moved["address"]
        plan["resource_changes"].append(moved)
        with self.assertRaises(Stop) as stop:
            admit_plan(plan, CONFIG)
        self.assertEqual(stop.exception.label, "PLAN_FOREIGN_STATE")

    def test_smoke_200_without_auth_fails(self):
        self.probes = [(200, "application/json")]
        code, receipt = self.deploy()
        self.assertEqual(code, 1)
        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(receipt["failure"]["label"], "SMOKE_UNAUTHENTICATED_ACCESS")
        self.assertEqual(receipt["smoke"]["status"], 200)

    def test_smoke_retries_through_dns_and_tls_propagation(self):
        self.probes = [(None, ""), (403, "application/json"), (401, "application/problem+json; charset=utf-8")]
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["result"]), (0, "deployed"))
        self.assertEqual(receipt["smoke"]["attempts"], 3)
        self.assertEqual(self.sleeps, [20, 20])

    def test_smoke_times_out_after_fifteen_minutes(self):
        self.probes = [(None, "")]
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "SMOKE_TIMEOUT"))
        self.assertLessEqual(sum(self.sleeps), 15 * 60)
        self.assertEqual(receipt["smoke"]["result"], "failed")

    def test_apply_denial_reports_closed_label_and_denied_actions_only(self):
        self.tools.fail_phase = "apply"
        self.tools.fail_text = ("Error: creating IAM Role: AccessDenied: User: arn:aws:sts::511831442607:assumed-role/"
                                "wisestay-dev-home-scanner-deploy/x is not authorized to perform: iam:CreateRole on "
                                "resource secret-ish-detail with an explicit deny")
        code, receipt = self.deploy()
        self.assertEqual(code, 1)
        self.assertEqual(receipt["failure"], {"label": "TERRAFORM_APPLY_FAILED", "denied_actions": ["iam:CreateRole"]})
        self.assertNotIn("secret-ish-detail", json.dumps(receipt))

    def test_deployed_package_digest_must_match(self):
        self.tools.code_sha = "A" * 43 + "="
        code, receipt = self.deploy()
        self.assertEqual((code, receipt["failure"]["label"]), (1, "DEPLOYED_PACKAGE_MISMATCH"))

    def test_committed_configuration_matches_the_contract(self):
        self.assertEqual(ACTIVATION["contract"], "wisestay.3d.activation.v1")
        self.assertIs(ACTIVATION["enabled"], True)
        self.assertEqual(ACTIVATION["approval_reference"], "owner-3d-dev-deployment-2026-10-20")
        self.assertEqual(CONFIG["deploy_role_arn"],
                         "arn:aws:iam::511831442607:role/wisestay/deploy/dev/wisestay-dev-home-scanner-deploy")
        self.assertEqual(CONFIG["state"]["bucket"], "wisestay-state-511831442607-ap-southeast-1")
        self.assertEqual(CONFIG["resources"]["function"], "wisestay-dev-home-scanner-api")
        self.assertEqual(CONFIG["reserved_concurrency"], 5)
        self.assertEqual(CONFIG["resvanta_credential_parameter"], "")
        self.assertEqual(CONFIG["web_origin"], "https://home-scanner.wizestay.com")

    def test_smoke_path_is_a_real_token_protected_route(self):
        from wisestay_home_backend.http import router  # noqa: PLC0415

        found = router.match("GET", "/api/v1" + CONFIG["smoke_path"])
        self.assertIsNotNone(found)
        self.assertEqual(found[0].route_id, "H07")


if __name__ == "__main__":
    unittest.main()
