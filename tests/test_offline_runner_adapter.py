"""Separate adapter regressions, not included in H's 26/24 primary case list."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from tools.run_boundary_tests import ObservedResults, encode_junit, write_outputs
from tools.prepare_offline_test_package import source_spec, outside_checkout, prepare, invoke


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


    def test_wrong_complete_checkout_pin_is_rejected_before_writing_spec(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            output = Path(tmp) / "outside"
            with patch("tools.prepare_offline_test_package.current_head", return_value="a" * 40):
                with self.assertRaisesRegex(ValueError, "HEAD differs"):
                    prepare(checkout, output, "b" * 40)
            self.assertFalse(output.exists())

    def test_wrong_h_tool_hash_is_refused_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "wrong_h_checker.py"
            wrong.write_text("print('not the pinned H tool')\n")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                invoke(Path(tmp), wrong, Path(tmp) / "spec.json",
                       Path(tmp) / "out.json", Path(tmp) / "out.zip")
            self.assertFalse((Path(tmp) / "out.json").exists())
            self.assertFalse((Path(tmp) / "out.zip").exists())

    def test_zero_tests_cannot_create_fabricated_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_outputs(ObservedResults(), Path(tmp))
            self.assertFalse((Path(tmp) / "junit.xml").exists())

if __name__ == "__main__":
    unittest.main()
