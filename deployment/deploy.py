"""Guarded dev deployment of ``infra/application`` (wave 3 plan §6.2, HSB-01.3, X.10).

Run only by the ``deploy`` job of ``.github/workflows/ci.yml`` after the verification
jobs pass, with GitHub OIDC credentials for
``wisestay/deploy/dev/wisestay-dev-home-scanner-deploy`` in account 511831442607.
Stdlib only; it shells out to ``gh``, ``aws`` and ``terraform``.

Order (each step must pass before the next):
  a. source activation (``deployment/activation.json``), else ``held``/ACTIVATION_DISABLED
  b. repository, ``refs/heads/main`` and the current main SHA
  c. STS caller: account 511831442607 and the exact deploy-role session prefix
  d. account unreserved-concurrency floor (100) for the reserved concurrency of 5
  e. ``terraform init`` against the private remote-state backend file
  f. ``terraform plan -out`` with the committed non-secret configuration
  g. in-process plan admission (frozen types, contract names, no destruction)
  h. current main re-check, then ``apply`` of exactly the saved plan
  i. outputs and the deployed package digest
  j. unauthenticated smoke: the token-protected route must answer 401 problem+json
  k. ``dist/deployment-receipt.json``

Plans, state, tfvars and provider output stay in a private temporary directory that is
removed on exit. Nothing here prints plan values or provider text: failures are closed
labels plus at most four denied IAM action names.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "infra" / "application"
RECEIPT_CONTRACT = "wisestay.3d.deployment-receipt.v1"
ACTIVATION_CONTRACT = "wisestay.3d.activation.v1"
APPROVAL_REFERENCE = "owner-3d-dev-deployment-2026-10-20"
ACCOUNT = "511831442607"
SMOKE_INTERVAL_S = 20
SMOKE_DEADLINE_S = 15 * 60

# Frozen resource inventory of infra/application (plan §6.2.1).
FROZEN_TYPES = frozenset({
    "aws_iam_role", "aws_iam_role_policy", "aws_cloudwatch_log_group", "aws_lambda_function",
    "aws_lambda_permission", "aws_dynamodb_table", "aws_s3_bucket",
    "aws_s3_bucket_ownership_controls", "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_lifecycle_configuration",
    "aws_s3_bucket_cors_configuration", "aws_s3_bucket_policy", "aws_api_gateway_rest_api",
    "aws_api_gateway_resource", "aws_api_gateway_method", "aws_api_gateway_integration",
    "aws_api_gateway_deployment", "aws_api_gateway_stage", "aws_api_gateway_method_settings",
    "aws_api_gateway_domain_name", "aws_api_gateway_base_path_mapping", "aws_acm_certificate",
    "aws_acm_certificate_validation", "aws_route53_record", "terraform_data",
})
# Only a REST API deployment may be replaced (it is create_before_destroy by design).
REPLACEABLE_TYPES = frozenset({"aws_api_gateway_deployment"})
_DENIED = re.compile(r"not authorized to perform: ([a-z0-9-]+:[A-Za-z0-9*]+)")


class Stop(Exception):
    """A closed failure label; ``held`` marks a deliberate, non-error stop."""

    def __init__(self, label: str, *, held: bool = False, denied: list[str] | None = None):
        super().__init__(label)
        self.label = label
        self.held = held
        self.denied = (denied or [])[:4]


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., Completed]
Probe = Callable[[str], tuple[int | None, str]]


def subprocess_runner(argv: list[str], *, env: Mapping[str, str] | None = None,
                      timeout: int = 1800) -> Completed:
    result = subprocess.run(argv, env=dict(env) if env is not None else None, capture_output=True,
                            text=True, timeout=timeout, check=False)
    return Completed(result.returncode, result.stdout, result.stderr)


def http_probe(url: str) -> tuple[int | None, str]:
    """Unauthenticated GET. Returns (status, content type); (None, "") when unreachable."""
    request = Request(url, method="GET", headers={"Accept": "application/problem+json",
                                                  "User-Agent": "wisestay-3d-deploy-smoke"})
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed https contract URL
            return response.status, response.headers.get("Content-Type", "")
    except HTTPError as error:
        return error.code, error.headers.get("Content-Type", "") if error.headers else ""
    except (URLError, OSError, ValueError):
        return None, ""


def denied_actions(text: str) -> list[str]:
    return sorted(set(_DENIED.findall(text)))[:4]


def package_digest(path: Path) -> str:
    return base64.b64encode(hashlib.sha256(path.read_bytes()).digest()).decode("ascii")


def check_activation(value: Mapping) -> None:
    if not (value.get("contract") == ACTIVATION_CONTRACT and value.get("enabled") is True
            and value.get("environment") == "dev" and value.get("account") == ACCOUNT
            and value.get("approval_reference") == APPROVAL_REFERENCE):
        raise Stop("ACTIVATION_DISABLED", held=True)


def _planned(change: Mapping, attribute: str) -> tuple[str, object]:
    """("value", v) when known at plan, ("unknown", None) when computed, else ("null", None)."""
    after = change.get("after") or {}
    if after.get(attribute) is not None:
        return "value", after[attribute]
    if (change.get("after_unknown") or {}).get(attribute) is True:
        return "unknown", None
    return "null", None


def _name_rules(config: Mapping) -> dict[str, list[tuple[str, Callable[[object], bool], bool]]]:
    """type -> [(attribute, accepts(value), must_be_known_at_plan)]."""
    res = config["resources"]
    host = config["api_host"]
    validation = re.compile(r"^_[a-z0-9]+\." + re.escape(host) + r"$")

    def equals(expected: str) -> Callable[[object], bool]:
        return lambda value: value == expected

    def record_name(value: object) -> bool:
        name = str(value).rstrip(".").lower()
        return name == host or bool(validation.match(name))

    bucket = [("bucket", equals(res["bucket"]), False)]
    return {
        "aws_iam_role": [("name", equals(res["runtime_role"]), True)],
        "aws_iam_role_policy": [("name", equals(res["runtime_policy"]), True)],
        "aws_cloudwatch_log_group": [("name", equals(res["log_group"]), True)],
        "aws_lambda_function": [("function_name", equals(res["function"]), True)],
        "aws_lambda_permission": [("function_name", equals(res["function"]), False)],
        "aws_dynamodb_table": [("name", equals(res["table"]), True)],
        "aws_s3_bucket": [("bucket", equals(res["bucket"]), True)],
        "aws_s3_bucket_ownership_controls": bucket,
        "aws_s3_bucket_public_access_block": bucket,
        "aws_s3_bucket_server_side_encryption_configuration": bucket,
        "aws_s3_bucket_lifecycle_configuration": bucket,
        "aws_s3_bucket_cors_configuration": bucket,
        "aws_s3_bucket_policy": bucket,
        "aws_api_gateway_rest_api": [("name", equals(res["function"]), True)],
        "aws_acm_certificate": [("domain_name", equals(host), True)],
        "aws_api_gateway_domain_name": [("domain_name", equals(host), True)],
        "aws_api_gateway_base_path_mapping": [("domain_name", equals(host), False)],
        "aws_route53_record": [("zone_id", equals(res["hosted_zone_id"]), True),
                               ("name", record_name, False)],
    }


def admit_plan(plan: Mapping, config: Mapping) -> dict[str, dict[str, int]]:
    """Admit only creates/updates/no-ops of the frozen inventory with contract names.

    Returns per-type action counts (never values)."""
    rules = _name_rules(config)
    summary: dict[str, dict[str, int]] = {}
    prior = ((plan.get("prior_state") or {}).get("values") or {}).get("root_module") or {}
    if prior.get("child_modules"):
        raise Stop("PLAN_FOREIGN_STATE")
    for item in plan.get("resource_changes") or []:
        if item.get("mode") == "data":
            continue
        kind = item.get("type", "")
        if item.get("mode") != "managed" or str(item.get("address", "")).startswith("module."):
            raise Stop("PLAN_FOREIGN_STATE")
        if kind not in FROZEN_TYPES:
            raise Stop("PLAN_UNEXPECTED_TYPE")
        change = item.get("change") or {}
        actions = list(change.get("actions") or [])
        if actions in (["create"], ["update"], ["no-op"]):
            label = actions[0]
        elif sorted(actions) == ["create", "delete"] and kind in REPLACEABLE_TYPES:
            label = "replace"
        else:
            raise Stop("PLAN_DESTRUCTIVE_CHANGE")
        for attribute, accepts, required in rules.get(kind, []):
            state, value = _planned(change, attribute)
            if state == "value" and not accepts(value):
                raise Stop("PLAN_FOREIGN_NAME")
            # Names of primary resources are literal in the stack, so they must be known now;
            # child resources may reference a not-yet-created parent id.
            if state == "null" or (state == "unknown" and required):
                raise Stop("PLAN_FOREIGN_NAME")
        counts = summary.setdefault(kind, {})
        counts[label] = counts.get(label, 0) + 1
    return {kind: summary[kind] for kind in sorted(summary)}


class Deployment:
    def __init__(self, *, config: Mapping, activation_path: Path, terraform: str, receipt_path: Path,
                 env: Mapping[str, str], run: Runner = subprocess_runner, probe: Probe = http_probe,
                 sleep: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic, root: Path = ROOT):
        self.config = config
        self.activation_path = activation_path
        self.terraform = terraform
        self.receipt_path = receipt_path
        self.env = env
        self.run = run
        self.probe = probe
        self.sleep = sleep
        self.monotonic = monotonic
        self.root = root
        self.receipt: dict = {
            "contract": RECEIPT_CONTRACT,
            "repository": config["repository"],
            "revision": env.get("GITHUB_SHA", ""),
            "run_id": env.get("GITHUB_RUN_ID", ""),
            "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
            "approval_reference": None,
            "caller_arn": None,
            "account": None,
            "state_key": config["state"]["key"],
            "plan_summary": None,
            "lambda_package_sha256_b64": None,
            "function_last_modified": None,
            "account_unreserved_concurrency_before": None,
            "smoke": None,
            "result": "failed",
            "failure": None,
        }

    # -- helpers -------------------------------------------------------------------------
    def _activation(self) -> Mapping:
        try:
            value = json.loads(self.activation_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Stop("ACTIVATION_DISABLED", held=True) from None
        check_activation(value)
        return value

    def _cli(self, label: str, argv: list[str], *, allow: tuple[str, ...] = ()) -> Completed:
        result = self.run(argv, env=self.env, timeout=120)
        if result.returncode and not any(code in result.stderr for code in allow):
            raise Stop(label, denied=denied_actions(result.stderr))
        return result

    def _json(self, label: str, argv: list[str]) -> Mapping:
        try:
            return json.loads(self._cli(label, argv).stdout)
        except ValueError:
            raise Stop(label) from None

    def _current_main(self) -> None:
        repository = self.config["repository"]
        if self.env.get("GITHUB_REPOSITORY") != repository or self.env.get("GITHUB_REF") != "refs/heads/main":
            raise Stop("NOT_MAIN_OF_REPOSITORY")
        head = self._cli("MAIN_LOOKUP_FAILED", ["gh", "api", f"repos/{repository}/git/ref/heads/main",
                                                "--jq", ".object.sha"]).stdout.strip()
        if not head or head != self.env.get("GITHUB_SHA"):
            raise Stop("SUPERSEDED_MAIN")

    def _caller(self) -> None:
        identity = self._json("STS_CALLER_UNAVAILABLE", ["aws", "sts", "get-caller-identity", "--output", "json"])
        self.receipt["account"] = identity.get("Account")
        self.receipt["caller_arn"] = identity.get("Arn")
        if identity.get("Account") != ACCOUNT or self.config["account"] != ACCOUNT:
            raise Stop("WRONG_ACCOUNT")
        if not str(identity.get("Arn", "")).startswith(self.config["deploy_session_prefix"]):
            raise Stop("WRONG_DEPLOY_ROLE")

    def _function_reservation(self) -> int:
        function = self.config["resources"]["function"]
        result = self._cli("LAMBDA_CONCURRENCY_UNAVAILABLE",
                           ["aws", "lambda", "get-function-concurrency", "--function-name", function,
                            "--output", "json"], allow=("ResourceNotFoundException",))
        if result.returncode:
            return 0
        try:
            return int(json.loads(result.stdout or "{}").get("ReservedConcurrentExecutions") or 0)
        except (ValueError, TypeError):
            raise Stop("LAMBDA_CONCURRENCY_UNAVAILABLE") from None

    def _concurrency_floor(self) -> None:
        settings = self._json("LAMBDA_ACCOUNT_SETTINGS_UNAVAILABLE",
                              ["aws", "lambda", "get-account-settings", "--output", "json"])
        unreserved = (settings.get("AccountLimit") or {}).get("UnreservedConcurrentExecutions")
        if not isinstance(unreserved, int):
            raise Stop("LAMBDA_ACCOUNT_SETTINGS_UNAVAILABLE")
        self.receipt["account_unreserved_concurrency_before"] = unreserved
        additional = max(int(self.config["reserved_concurrency"]) - self._function_reservation(), 0)
        if unreserved - additional < int(self.config["unreserved_concurrency_floor"]):
            raise Stop("ACCOUNT_CONCURRENCY_FLOOR", held=True)

    def _tf(self, private: Path, phase: str, *args: str) -> Completed:
        env = {**self.env, "TF_IN_AUTOMATION": "1", "TF_INPUT": "0"}
        result = self.run([self.terraform, f"-chdir={self.root / 'infra' / 'application'}", *args],
                          env=env, timeout=1800)
        with (private / "terraform.log").open("a", encoding="utf-8") as log:  # private, never uploaded
            log.write(result.stdout + "\n" + result.stderr + "\n")
        if result.returncode:
            raise Stop(f"TERRAFORM_{phase}_FAILED", denied=denied_actions(result.stdout + result.stderr))
        return result

    def _smoke(self) -> None:
        url = self.config["api_root"] + self.config["smoke_path"]
        smoke = {"url": url, "status": None, "content_type": None, "attempts": 0, "result": "failed"}
        self.receipt["smoke"] = smoke
        deadline = self.monotonic() + SMOKE_DEADLINE_S
        while True:
            status, content_type = self.probe(url)
            smoke.update(status=status, content_type=content_type.split(";")[0].strip() or None,
                         attempts=smoke["attempts"] + 1)
            if status is not None and 200 <= status < 300:
                raise Stop("SMOKE_UNAUTHENTICATED_ACCESS")
            if status == 401 and smoke["content_type"] == "application/problem+json":
                smoke["result"] = "passed"
                return
            if self.monotonic() + SMOKE_INTERVAL_S > deadline:
                raise Stop("SMOKE_TIMEOUT")
            self.sleep(SMOKE_INTERVAL_S)

    # -- the ordered steps ----------------------------------------------------------------
    def execute(self) -> dict:
        approval = self._activation()                                    # a
        self.receipt["approval_reference"] = approval["approval_reference"]
        self._current_main()                                             # b
        self._caller()                                                   # c
        self._concurrency_floor()                                        # d
        package = self.root / self.config["lambda_package"]
        if not package.is_file():
            raise Stop("LAMBDA_PACKAGE_MISSING")
        digest = package_digest(package)
        self.receipt["lambda_package_sha256_b64"] = digest
        base = self.env.get("RUNNER_TEMP") or None
        private = Path(tempfile.mkdtemp(prefix="home-scanner-deploy-", dir=base))
        try:
            os.chmod(private, 0o700)
            state = self.config["state"]
            backend = {"bucket": state["bucket"], "key": state["key"], "region": state["region"],
                       "encrypt": True, "use_lockfile": True, "kms_key_id": state["kms_key_id"],
                       "allowed_account_ids": [ACCOUNT]}
            (private / "backend.json").write_text(json.dumps(backend), encoding="utf-8")
            self._tf(private, "INIT", "init", "-reconfigure", "-input=false", "-lockfile=readonly",
                     f"-backend-config={private / 'backend.json'}")       # e
            tfvars = {
                "expected_account_id": ACCOUNT, "region": self.config["region"],
                "environment": self.config["environment"], "lambda_package_path": str(package),
                "lambda_package_sha256_b64": digest, "web_origin": self.config["web_origin"],
                "api_hostname": self.config["api_host"],
                "resvanta_api_root": self.config["resvanta_api_root"],
                "resvanta_credential_parameter": self.config["resvanta_credential_parameter"],
            }
            (private / "dev.tfvars.json").write_text(json.dumps(tfvars), encoding="utf-8")
            plan_file = private / "approved.tfplan"
            self._tf(private, "PLAN", "plan", "-input=false", "-lock-timeout=5m",
                     f"-out={plan_file}", f"-var-file={private / 'dev.tfvars.json'}")  # f
            try:
                plan = json.loads(self._tf(private, "SHOW", "show", "-json", str(plan_file)).stdout)
            except ValueError:
                raise Stop("TERRAFORM_SHOW_FAILED") from None
            self.receipt["plan_summary"] = admit_plan(plan, self.config)  # g
            self._current_main()                                         # h
            self._activation()
            self._tf(private, "APPLY", "apply", "-input=false", "-auto-approve", "-lock-timeout=5m",
                     str(plan_file))
            try:                                                         # i
                outputs = json.loads(self._tf(private, "OUTPUT", "output", "-json").stdout)
            except ValueError:
                raise Stop("TERRAFORM_OUTPUT_FAILED") from None
            if ((outputs.get("function_name") or {}).get("value") != self.config["resources"]["function"]
                    or (outputs.get("api_root") or {}).get("value") != self.config["api_root"]):
                raise Stop("OUTPUT_MISMATCH")
        finally:
            shutil.rmtree(private, ignore_errors=True)
        function = self._json("LAMBDA_CONFIGURATION_UNAVAILABLE",
                              ["aws", "lambda", "get-function-configuration", "--function-name",
                               self.config["resources"]["function"], "--output", "json"])
        self.receipt["function_last_modified"] = function.get("LastModified")
        if function.get("CodeSha256") != digest:
            raise Stop("DEPLOYED_PACKAGE_MISMATCH")
        if self._function_reservation() != int(self.config["reserved_concurrency"]):
            raise Stop("RESERVED_CONCURRENCY_MISMATCH")
        self._smoke()                                                    # j
        self.receipt["result"] = "deployed"
        return self.receipt

    def main(self) -> int:
        code = 0
        try:
            self.execute()
        except Stop as stop:
            self.receipt["result"] = "held" if stop.held else "failed"
            self.receipt["failure"] = {"label": stop.label, "denied_actions": stop.denied}
            code = 0 if stop.label == "ACTIVATION_DISABLED" else 1
        except Exception as error:  # noqa: BLE001 - never publish provider or runtime detail
            self.receipt["result"] = "failed"
            self.receipt["failure"] = {"label": "DEPLOYMENT_OPERATION_FAILED", "denied_actions": [],
                                       "type": type(error).__name__}
            code = 1
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)       # k
        self.receipt_path.write_text(json.dumps(self.receipt, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
        print(json.dumps({"result": self.receipt["result"], "failure": self.receipt["failure"]}))
        return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--config", type=Path, default=ROOT / "deployment" / "dev.config.json")
    parser.add_argument("--activation", type=Path, default=ROOT / "deployment" / "activation.json")
    parser.add_argument("--receipt", type=Path, default=ROOT / "dist" / "deployment-receipt.json")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    return Deployment(config=config, activation_path=args.activation, terraform=args.terraform,
                      receipt_path=args.receipt, env=dict(os.environ)).main()


if __name__ == "__main__":
    sys.exit(main())
