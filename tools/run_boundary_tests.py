"""Execute the real pinned internal asset-reference suite and write genuine JUnit.

This is a stdlib-only component test entry, not a public API, authorization
adapter, deployment, source-storage adapter, or independent QA qualification.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from xml.etree.ElementTree import Element, SubElement, tostring

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

SUITE = "tests.test_resolve_asset_reference"
EXPECTED_CASES = 26
OUTPUT = Path("out")


class ObservedResults(unittest.TestResult):
    """Record each actual executed unittest case, never invent passes."""

    def __init__(self) -> None:
        super().__init__()
        self.events: dict[str, tuple[str, str | None]] = {}

    def addSuccess(self, test) -> None:
        super().addSuccess(test)
        self.events[test.id()] = ("success", None)

    def addFailure(self, test, err) -> None:
        super().addFailure(test, err)
        self.events[test.id()] = ("failure", self._exc_info_to_string(err, test))

    def addError(self, test, err) -> None:
        super().addError(test, err)
        self.events[test.id()] = ("error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason) -> None:
        super().addSkip(test, reason)
        self.events[test.id()] = ("skipped", str(reason))


def encode_junit(result: ObservedResults) -> bytes:
    """Serialize only cases actually seen by unittest's callbacks."""
    if result.testsRun <= 0 or len(result.events) != result.testsRun:
        raise ValueError("zero or unaccounted-for unit tests cannot be packaged")
    failed = sum(status == "failure" for status, _ in result.events.values())
    errors = sum(status == "error" for status, _ in result.events.values())
    skipped = sum(status == "skipped" for status, _ in result.events.values())
    root = Element("testsuite", {
        "name": SUITE,
        "tests": str(result.testsRun),
        "failures": str(failed),
        "errors": str(errors),
        "skipped": str(skipped),
    })
    for identifier, (status, detail) in sorted(result.events.items()):
        classname, _, name = identifier.rpartition(".")
        case = SubElement(root, "testcase", {"classname": classname, "name": name})
        if status != "success":
            SubElement(case, status).text = detail or status
    return tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def write_outputs(result: ObservedResults, root: Path = OUTPUT) -> dict:
    """JUnit and summary are generated from actual result objects, never fixture XML."""
    content = encode_junit(result)
    root.mkdir(parents=True, exist_ok=True)
    (root / "junit.xml").write_bytes(content)
    summary = {
        "evidence_class": "LOCAL_UNIT_SYNTHETIC_EVIDENCE_ONLY",
        "suite": SUITE,
        "expected_tests": EXPECTED_CASES,
        "executed_tests": result.testsRun,
        "failed_tests": [ident for ident, (status, _) in sorted(result.events.items())
                         if status in ("failure", "error")],
        "skipped_tests": [ident for ident, (status, _) in sorted(result.events.items())
                          if status == "skipped"],
        "case_ids": sorted(result.events),
        "no_live_authority": True,
        "no_service_or_physical_acceptance": True,
    }
    (root / "synthetic_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromName(SUITE)
    result = ObservedResults()
    suite.run(result)
    try:
        summary = write_outputs(result)
    except ValueError:
        return 3
    if (
        summary["executed_tests"] != EXPECTED_CASES
        or not result.wasSuccessful()
        or result.skipped
    ):
        return 2
    print(f"{SUITE}: {result.testsRun} executed, 0 failures, 0 errors, 0 skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
