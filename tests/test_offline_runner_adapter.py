"""Separate adapter regressions, not included in H's 26/24 primary case list."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from tools.run_boundary_tests import ObservedResults, encode_junit, write_outputs
from tools.prepare_offline_test_package import source_spec, outside_checkout


class OfflineRunnerAdapterTests(unittest.TestCase):
    def test_zero_executed_tests_cannot_emit_junit(self):
        with self.assertRaises(ValueError):
            encode_junit(ObservedResults())

    def test_actual_failing_unittest_is_recorded_as_failure(self):
        def fail_case():
            self.assertEqual("actual", "expected")
        suite = unittest.TestSuite([unittest.FunctionTestCase(fail_case)])
        result = ObservedResults()
        suite.run(result)
        with tempfile.TemporaryDirectory() as tmp:
            summary = write_outputs(result, Path(tmp))
            junit = (Path(tmp) / "junit.xml").read_text()
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(summary["failed_tests"]), 1)
        self.assertIn("<failure>", junit)

    def test_incorrect_expected_commit_is_rejected_by_spec_builder(self):
        with self.assertRaises(ValueError):
            source_spec("invalid-or-branch-name")

    def test_receipt_output_cannot_live_inside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with self.assertRaises(ValueError):
                outside_checkout(work, work / "evidence")


if __name__ == "__main__":
    unittest.main()
