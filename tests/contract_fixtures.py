"""Loader for the DRAFT / SYNTHETIC B-RFX v0.3 contract fixtures (P03).

The loader verifies the checksum-pinned copy first, then exposes the effective
fixture set.  B-RFX-03 revision 0.2 supersedes the original B-RFX-03 file; the
original is kept for history only.  Nothing here freezes or accepts a contract.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# `python3 -m unittest discover -s tests` puts only the repo root on sys.path.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tools.check_contract_fixtures import FIXTURE_DIR, verify_copy  # noqa: E402

FIXTURE_IDS = tuple(f"B-RFX-0{n}" for n in range(1, 9))
# fixture_id -> the only revised fixture revision this consumer understands.
SUPPORTED_REVISIONS = {"B-RFX-03": "0.2"}
DRAFT_STATUS = "PREPARED_NOT_EXECUTED_NOT_ACCEPTED"


class IncompatibleFixtureVersion(ValueError):
    """A revised fixture is not the revision this consumer was written against."""


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def select_effective(
    originals: dict[str, tuple[dict, str]],
    revisions: list[dict],
) -> dict[str, dict]:
    """Return fixture_id -> effective fixture.

    ``originals`` maps fixture_id to (fixture, sha256 of its bytes).  A revision
    replaces an original only when it names that fixture, the exact predecessor
    sha256 and a supported fixture revision; anything else fails closed.
    """
    effective = {fixture_id: fixture for fixture_id, (fixture, _) in originals.items()}
    for revision in revisions:
        fixture_id = revision.get("fixture_id")
        revises = revision.get("revises") or {}
        if fixture_id not in originals or revises.get("fixture_id") != fixture_id:
            raise IncompatibleFixtureVersion(f"revision does not revise a known fixture: {fixture_id}")
        if revision.get("fixture_revision") != SUPPORTED_REVISIONS.get(fixture_id):
            raise IncompatibleFixtureVersion(
                f"{fixture_id} revision {revision.get('fixture_revision')!r} is not supported"
            )
        if revises.get("predecessor_sha256") != originals[fixture_id][1]:
            raise IncompatibleFixtureVersion(f"{fixture_id} revision names a different predecessor")
        effective[fixture_id] = revision
    return effective


class DraftContractFixtures:
    """Verified, effective B-RFX v0.3 draft fixtures for one repository copy."""

    def __init__(self, repo_root: Path = ROOT) -> None:
        verify_copy(repo_root)
        self.base = Path(repo_root) / FIXTURE_DIR
        self.originals: dict[str, tuple[dict, str, str]] = {}
        for path in sorted((self.base / "fixtures/original").glob("*.json")):
            raw = path.read_bytes()
            fixture = json.loads(raw.decode("utf-8"))
            self.originals[fixture["fixture_id"]] = (fixture, hashlib.sha256(raw).hexdigest(), path.name)
        revisions = [_read_json(p) for p in sorted((self.base / "fixtures/revised").glob("*.json"))]
        self.effective = select_effective(
            {fid: (fixture, digest) for fid, (fixture, digest, _) in self.originals.items()},
            revisions,
        )
        self.delta_records = _read_json(self.base / "corrections/DELTA_records_v0.3.json")

    def fixture(self, fixture_id: str) -> dict:
        return self.effective[fixture_id]

    def example(self, fixture_id: str, example: str) -> dict:
        matches = [e for e in self.effective[fixture_id]["examples"] if e["example"] == example]
        if len(matches) != 1:
            raise KeyError(f"{fixture_id}/{example}")
        return matches[0]

    def example_keys(self) -> set[tuple[str, str]]:
        return {
            (fixture_id, item["example"])
            for fixture_id, fixture in self.effective.items()
            for item in fixture["examples"]
        }


def split_label(label: str) -> tuple[str, str]:
    """Split an opaque synthetic `ID@REVISION` label; it is not an ID format."""
    identifier, _, revision = label.partition("@")
    if not identifier or not revision:
        raise ValueError(f"not an ID@REVISION label: {label!r}")
    return identifier, revision
