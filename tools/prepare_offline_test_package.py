"""Prepare exact source list/spec and invoke H's pinned Linux offline packager.

This source is C-owned glue only. It never imports/copies/rewrites H's checker
and never chooses a repository's latest default branch. Receipts/specs/packages
are always outside the Git checkout. All command invocations use argv arrays.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

H_TOOL_SHA256 = "2ca1cd8c27123f7417a477de135cce10b853480c966ca2b0a5ce2eba82c84bb3"

SOURCE_PATHS = (
    "tools/run_boundary_tests.py",
    "tests/__init__.py",
    "tests/fakes.py",
    "tests/test_resolve_asset_reference.py",
    "src/wisestay_home_backend/__init__.py",
    "src/wisestay_home_backend/domain/__init__.py",
    "src/wisestay_home_backend/domain/asset_reference.py",
    "src/wisestay_home_backend/application/__init__.py",
    "src/wisestay_home_backend/application/resolve_asset_reference.py",
    "src/wisestay_home_backend/ports/__init__.py",
    "src/wisestay_home_backend/ports/reference_authority.py",
)


def outside_checkout(checkout: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if resolved == checkout or checkout in resolved.parents:
        raise ValueError("package/spec/receipt must be outside checkout")
    return resolved


def source_spec(commit: str) -> dict:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("expected_commit must be an exact 40-character source commit")
    return {
        "schema_version": 1,
        "kind": "test_build",
        "sources": list(SOURCE_PATHS),
        "argv": ["python3", "-B", "tools/run_boundary_tests.py"],
        "results_file": "out/junit.xml",
        "artifacts": ["out/synthetic_summary.json"],
        "expected_commit": commit,
    }


def current_head(checkout: Path) -> str:
    command = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--verify", "HEAD^{commit}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=10,
    )
    if command.returncode:
        raise ValueError("cannot read local checkout HEAD")
    return command.stdout.strip()


def prepare(checkout: Path, output: Path, expected_commit: str) -> tuple[Path, Path, Path]:
    checkout = checkout.resolve(strict=True)
    output = outside_checkout(checkout, output)
    if current_head(checkout) != expected_commit:
        raise ValueError("current checkout HEAD differs from requested source pin")
    output.mkdir(parents=True, exist_ok=False)  # do not overwrite a prior receipt
    spec = output / "spec.json"
    spec.write_text(json.dumps(source_spec(expected_commit), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return spec, output / "run.json", output / "run.zip"


def invoke(checkout: Path, packager: Path, spec: Path, receipt: Path, package: Path) -> int:
    exact_tool = packager.resolve(strict=True)
    if hashlib.sha256(exact_tool.read_bytes()).hexdigest() != H_TOOL_SHA256:
        raise ValueError("H packaging tool SHA-256 does not match the exact pinned source")
    command = [sys.executable, "-B", str(exact_tool),
               "--checkout", str(checkout.resolve(strict=True)),
               "--spec", str(spec), "--receipt", str(receipt),
               "--package", str(package), "--timeout-seconds", "60"]
    return subprocess.run(command, check=False, timeout=90).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--h-tool", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        spec, receipt, package = prepare(args.checkout, args.output_dir, args.expected_commit)
        return invoke(args.checkout, args.h_tool, spec, receipt, package)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"offline package input failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
