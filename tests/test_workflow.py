"""ci.yml deploy gating (wave 3 plan §6.2.3). Parses the workflow; never runs it."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml  # test-only: requirements-ci.txt

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ROLE = "arn:aws:iam::511831442607:role/wisestay/deploy/dev/wisestay-dev-home-scanner-deploy"
PINS = {
    "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "aws-actions/configure-aws-credentials": "61815dcd50bd041e203e49132bacad1fd04d2708",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
}


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.workflow = yaml.safe_load(cls.text)
        # PyYAML reads the bare key `on` as boolean True.
        cls.triggers = cls.workflow.get("on", cls.workflow.get(True))
        cls.jobs = cls.workflow["jobs"]
        cls.deploy = cls.jobs["deploy"]

    def test_triggers_push_main_and_deploy_dispatch(self):
        self.assertEqual(self.triggers["push"]["branches"], ["main"])
        deploy_input = self.triggers["workflow_dispatch"]["inputs"]["deploy"]
        self.assertEqual((deploy_input["type"], deploy_input["default"]), ("boolean", False))
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.workflow["concurrency"]["cancel-in-progress"],
                         "${{ github.event_name == 'pull_request' }}")

    def test_deploy_job_is_gated_on_verified_main(self):
        self.assertEqual(self.deploy["needs"], ["boundary", "terraform"])
        self.assertEqual(self.deploy["if"],
                         "github.repository == 'majidsamadi/three-dimension-view-arcore-backend' && "
                         "github.ref == 'refs/heads/main' && (github.event_name == 'push' || "
                         "(github.event_name == 'workflow_dispatch' && inputs.deploy == true))")
        self.assertEqual(self.deploy["permissions"], {"contents": "read", "id-token": "write"})
        self.assertEqual(self.deploy["concurrency"],
                         {"group": "wisestay-dev-home-scanner-deploy", "cancel-in-progress": False})
        self.assertEqual(self.deploy["timeout-minutes"], 45)

    def test_only_the_deploy_job_can_request_an_oidc_token(self):
        for name, job in self.jobs.items():
            if name != "deploy":
                self.assertNotIn("id-token", job.get("permissions") or {}, name)
        self.assertNotIn("secrets.AWS", self.text)
        self.assertNotIn("aws-access-key-id", self.text)

    def test_every_action_is_pinned_to_the_contract_sha(self):
        for name, job in self.jobs.items():
            for step in job["steps"]:
                if "uses" not in step:
                    continue
                action, _, ref = step["uses"].partition("@")
                self.assertIn(action, PINS, (name, step["uses"]))
                self.assertEqual(ref, PINS[action], (name, step["uses"]))

    def test_credentials_are_the_literal_role_in_the_allowed_account(self):
        steps = self.deploy["steps"]
        credentials = [step for step in steps if step.get("uses", "").startswith("aws-actions/")]
        self.assertEqual(len(credentials), 1)
        settings = credentials[0]["with"]
        self.assertEqual(settings["role-to-assume"], ROLE)
        self.assertEqual(settings["aws-region"], "ap-southeast-1")
        self.assertEqual(settings["allowed-account-ids"], "511831442607")
        self.assertEqual(settings["role-duration-seconds"], 3600)
        self.assertIs(settings["unset-current-credentials"], True)
        self.assertEqual(settings["role-session-name"], "home-scanner-deploy-${{ github.run_id }}")

    def test_step_order_checks_main_and_caller_before_terraform(self):
        steps = self.deploy["steps"]

        def index(predicate) -> int:
            return next(position for position, step in enumerate(steps) if predicate(step))

        main_check = index(lambda step: "git/ref/heads/main" in step.get("run", ""))
        credentials = index(lambda step: step.get("uses", "").startswith("aws-actions/"))
        caller = index(lambda step: "get-caller-identity" in step.get("run", ""))
        deploy = index(lambda step: "deployment/deploy.py" in step.get("run", ""))
        self.assertLess(main_check, credentials)
        self.assertLess(credentials, caller)
        self.assertLess(caller, deploy)
        self.assertIn('= "511831442607"', steps[caller]["run"])
        self.assertIn("assumed-role/wisestay-dev-home-scanner-deploy/*", steps[caller]["run"])
        self.assertTrue(re.search(r"--terraform \"\$RUNNER_TEMP/terraform-bin/terraform\"", steps[deploy]["run"]))

    def test_receipt_is_uploaded_and_private_files_removed_always(self):
        steps = self.deploy["steps"]
        upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact"))
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"]["name"], "deployment-receipt-${{ github.sha }}")
        self.assertEqual(upload["with"]["path"], "dist/deployment-receipt.json")
        self.assertEqual(upload["with"]["retention-days"], 30)
        cleanup = steps[-1]
        self.assertEqual(cleanup["if"], "always()")
        self.assertIn("infra/application/.terraform", cleanup["run"])

    def test_terraform_job_runs_mocked_tests(self):
        runs = " ".join(step.get("run", "") for step in self.jobs["terraform"]["steps"])
        self.assertIn("-chdir=infra/application test", runs)
        self.assertNotIn(" plan", runs)
        self.assertNotIn(" apply", runs)


if __name__ == "__main__":
    unittest.main()
