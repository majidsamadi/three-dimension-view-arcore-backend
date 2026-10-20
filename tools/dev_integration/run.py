"""CLI: ``python -m tools.dev_integration.run --report dist/dev-integration-report.json``.

Inputs come from the environment only (the workflow maps repository secrets and dispatch
inputs into it).  The report is machine-readable JSON with per-tier and per-journey
``passed``/``failed``/``blocked`` and the exact reason.  Exit status is 0 only when every tier
and journey passed; a missing test identity is ``blocked`` and exits 1, never a pass.
The console shows only the per-journey status lines; tokens and secrets are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from tools.dev_integration.http import HttpsTransport
from tools.dev_integration.journeys import SECRET_NAMES, Config, Context, run_all


def config_from_env(env) -> Config:
    raw = (env.get("WS3D_IT_EXPECTED_REVISIONS") or "").strip()
    try:
        expected = json.loads(raw) if raw else {}
    except ValueError:
        expected = {}
    if not isinstance(expected, dict):
        expected = {}
    return Config(
        run_id=(env.get("WS3D_IT_RUN_ID") or "local").strip() or "local",
        secrets={name: env.get(name, "") for name in SECRET_NAMES},
        expected_revisions={str(k): str(v) for k, v in expected.items()},
        property_id=(env.get("WS3D_IT_PROPERTY_ID") or "PROP-VIRTUAL-1").strip() or "PROP-VIRTUAL-1",
        client_id_override=(env.get("WS3D_IT_CLIENT_ID") or "").strip() or None,
    )


def summarize(report: dict) -> list[str]:
    lines = []
    for group in ("tiers", "journeys"):
        for name, result in report[group].items():
            reason = f" - {result['reason']}" if result.get("reason") else ""
            lines.append(f"{name}: {result['status']}{reason}")
    lines.append(f"result: {report['result']} {json.dumps(report['summary'], sort_keys=True)}")
    return lines


def main(argv=None, env=None, transport=None, context_factory=Context) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    config = config_from_env(env)
    ctx = context_factory(config=config, transport=transport or HttpsTransport())
    report = run_all(ctx)
    report.update(repository=env.get("GITHUB_REPOSITORY"), revision=env.get("GITHUB_SHA"),
                  run_id=env.get("GITHUB_RUN_ID"), run_attempt=env.get("GITHUB_RUN_ATTEMPT"))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    sensitive = [config.secrets.get(name) for name in SECRET_NAMES]
    sensitive += [identity.access_token for identity in (ctx.a, ctx.b) if identity is not None]
    if any(value and len(value) >= 8 and value in text for value in sensitive):  # never expected
        text = json.dumps({"contract": report["contract"], "result": "failed",
                           "reason": "REPORT_WITHHELD: it would have contained a secret or token"}) + "\n"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
        print("result: failed (report withheld: it would have contained a secret or token)")
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    for line in summarize(report):
        print(line)
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
