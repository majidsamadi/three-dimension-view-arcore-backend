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

    def _symlink_dir(self, alias: Path, target: Path) -> None:
        try:
            alias.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")

    def test_exact_checkout_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            with self.assertRaises(ValueError):
                outside_checkout(checkout, checkout)
            with self.assertRaises(ValueError):
                outside_checkout(checkout, checkout / ".")

    def test_nested_checkout_output_is_rejected_even_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            output = checkout / "new" / "nested" / "receipt.json"
            with self.assertRaises(ValueError):
                outside_checkout(checkout, output)
            self.assertFalse(output.exists())

    def test_aliased_checkout_and_real_root_names_are_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "real-checkout"
            checkout.mkdir()
            alias = Path(tmp) / "checkout-alias"
            self._symlink_dir(alias, checkout)
            for referenced_checkout, candidate in (
                (alias, checkout),
                (checkout, alias),
                (alias, checkout / "output"),
                (checkout, alias / "output"),
            ):
                with self.subTest(reference=referenced_checkout, output=candidate):
                    with self.assertRaises(ValueError):
                        outside_checkout(referenced_checkout, candidate)

    def test_symlinked_child_from_external_path_back_into_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout = base / "checkout"
            internal = checkout / "saved-results"
            internal.mkdir(parents=True)
            external = base / "external"
            external.mkdir()
            redirect = external / "redirect-into-checkout"
            self._symlink_dir(redirect, internal)
            with self.assertRaises(ValueError):
                outside_checkout(checkout, redirect / "future" / "junit.xml")

    def test_symlinked_ancestor_into_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout = base / "checkout"
            checkout.mkdir()
            redirected_parent = base / "alias-parent"
            self._symlink_dir(redirected_parent, checkout)
            with self.assertRaises(ValueError):
                outside_checkout(checkout, redirected_parent / "future" / "receipt.json")

    def test_lexically_inside_symlink_redirected_outside_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout = base / "checkout"
            checkout.mkdir()
            sibling = base / "external"
            sibling.mkdir()
            redirected_child = checkout / "outbound-symlink"
            self._symlink_dir(redirected_child, sibling)
            with self.assertRaises(ValueError):
                outside_checkout(checkout, redirected_child / "future-receipt.json")

    def test_external_sibling_destination_is_accepted_and_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout = base / "checkout"
            checkout.mkdir()
            sibling = base / "checkout-results"  # prefix does not make it a child
            output = sibling / "future-run.json"
            self.assertEqual(outside_checkout(checkout, output), output.resolve())
            self.assertFalse(sibling.exists())

    def test_prepare_refuses_output_via_checkout_alias_without_writing(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout = base / "checkout"
            checkout.mkdir()
            alias = base / "checkout-alias"
            self._symlink_dir(alias, checkout)
            with patch("tools.prepare_offline_test_package.current_head", return_value="a" * 40):
                with self.assertRaises(ValueError):
                    prepare(checkout, alias / "new-packet", "a" * 40)
            self.assertFalse((checkout / "new-packet").exists())


if __name__ == "__main__":
    unittest.main()
