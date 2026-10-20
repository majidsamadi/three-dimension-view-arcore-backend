"""Verify the DRAFT / SYNTHETIC B-RFX v0.3 contract fixture copy (P03).

Stdlib only.  The same file is kept in every Python consumer repository so the
copies cannot drift silently:

1. every file named in ``contracts/draft/v0.3/SHA256SUMS`` must exist and match
   its sha256, and no unlisted file may appear under ``fixtures/`` or
   ``corrections/``;
2. sha256(``SHA256SUMS``) must equal ``SET_DIGEST``.  Changing any fixture byte
   therefore requires changing this constant in every repository;
3. ``--compare <repo-root> ...`` repeats 1-2 for sibling clones and fails if
   any copy differs from this one.

This is a component-level integrity check.  It does not freeze, accept or
publish the draft contracts (freeze needs owner Q01/Q03/Q04/Q05/Q06).
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PurePosixPath("contracts/draft/v0.3")
SET_DIGEST = "945c37d59266ec214717eb76b92ed2170f56bf1f756936d7a393bf7554d58ba0"
EXPECTED_FILE_COUNT = 12
# Only these subtrees are checksum-closed; README.md and SHA256SUMS are per-repo
# or self-describing files outside the set.
CLOSED_SUBTREES = ("fixtures", "corrections")
_LINE = re.compile(r"^([0-9a-f]{64})  ([^\s].*)$")


class FixtureDriftError(ValueError):
    """The fixture copy differs from the pinned draft set."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_sums(raw: bytes) -> list[tuple[str, str]]:
    if b"\r" in raw:
        raise FixtureDriftError("SHA256SUMS must use LF line endings only")
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise FixtureDriftError("SHA256SUMS must end with exactly one newline")
    entries: list[tuple[str, str]] = []
    for number, line in enumerate(raw.decode("utf-8").split("\n")[:-1], start=1):
        match = _LINE.match(line)
        if match is None:
            raise FixtureDriftError(f"SHA256SUMS line {number} is malformed")
        digest, rel = match.groups()
        posix = PurePosixPath(rel)
        if posix.is_absolute() or ".." in posix.parts or "\\" in rel:
            raise FixtureDriftError(f"SHA256SUMS line {number} names an unsafe path")
        entries.append((digest, rel))
    paths = [rel for _, rel in entries]
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise FixtureDriftError("SHA256SUMS paths must be unique and in sorted order")
    return entries


def verify_copy(repo_root: Path) -> list[tuple[str, str]]:
    """Return the verified (sha256, path) entries or raise FixtureDriftError."""
    base = Path(repo_root) / FIXTURE_DIR
    sums = base / "SHA256SUMS"
    if not sums.is_file():
        raise FixtureDriftError(f"missing {FIXTURE_DIR}/SHA256SUMS under {repo_root}")
    raw = sums.read_bytes()
    actual_set = hashlib.sha256(raw).hexdigest()
    if actual_set != SET_DIGEST:
        raise FixtureDriftError(
            f"set digest mismatch under {repo_root}: {actual_set} != {SET_DIGEST}"
        )
    entries = _parse_sums(raw)
    if len(entries) != EXPECTED_FILE_COUNT:
        raise FixtureDriftError(
            f"expected {EXPECTED_FILE_COUNT} listed files, found {len(entries)}"
        )
    listed = set()
    for digest, rel in entries:
        target = base / rel
        if not target.is_file():
            raise FixtureDriftError(f"missing fixture file {rel} under {repo_root}")
        if _sha256(target) != digest:
            raise FixtureDriftError(f"sha256 mismatch for {rel} under {repo_root}")
        listed.add(rel)
    for subtree in CLOSED_SUBTREES:
        for path in sorted((base / subtree).rglob("*")):
            if path.is_file():
                rel = path.relative_to(base).as_posix()
                if rel not in listed:
                    raise FixtureDriftError(f"unlisted file {rel} under {repo_root}")
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to verify")
    parser.add_argument(
        "--compare", nargs="+", type=Path, default=[], metavar="REPO_ROOT",
        help="sibling repository roots whose copies must be identical",
    )
    args = parser.parse_args(argv)
    try:
        entries = verify_copy(args.root)
        for other in args.compare:
            if verify_copy(other) != entries:
                raise FixtureDriftError(f"copy under {other} differs from {args.root}")
    except FixtureDriftError as exc:
        print(f"contract fixtures v0.3: FAILED: {exc}", file=sys.stderr)
        return 1
    message = f"contract fixtures v0.3: {len(entries)} files verified, set {SET_DIGEST[:8]}…"
    if args.compare:
        message += f", compared {len(args.compare)} copies"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
