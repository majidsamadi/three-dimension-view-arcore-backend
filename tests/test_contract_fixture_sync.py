"""Checksum sync-check for the DRAFT B-RFX v0.3 fixture copy (P03).

The repository copy must verify; a temp-dir copy with any drift must fail.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.check_contract_fixtures import (
    EXPECTED_FILE_COUNT,
    FIXTURE_DIR,
    SET_DIGEST,
    FixtureDriftError,
    main,
    verify_copy,
)

ROOT = Path(__file__).resolve().parents[1]
SIBLING_COPIES = ("three-dimension-view-arcore-backend", "three-dimension-object-backend")


def _copy_repo_fixtures(dest: Path) -> Path:
    shutil.copytree(ROOT / FIXTURE_DIR, dest / FIXTURE_DIR)
    return dest / FIXTURE_DIR


def _run_main(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class ContractFixtureSyncTests(unittest.TestCase):
    def test_draft_repository_copy_matches_pinned_set_digest(self):
        entries = verify_copy(ROOT)
        self.assertEqual(len(entries), EXPECTED_FILE_COUNT)
        code, out, _ = _run_main(["--root", str(ROOT)])
        self.assertEqual(code, 0)
        self.assertIn(f"12 files verified, set {SET_DIGEST[:8]}", out)

    def test_draft_tampered_fixture_byte_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            target = base / "fixtures/original/B-RFX-06_authority-privacy-profiles.json"
            target.write_bytes(target.read_bytes().replace(b"withdrawn", b"withdrawm", 1))
            with self.assertRaisesRegex(FixtureDriftError, "sha256 mismatch"):
                verify_copy(Path(tmp))
            code, _, err = _run_main(["--root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("FAILED", err)

    def test_draft_missing_fixture_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            (base / "fixtures/revised/B-RFX-03_version-component.v0.2.json").unlink()
            with self.assertRaisesRegex(FixtureDriftError, "missing fixture file"):
                verify_copy(Path(tmp))

    def test_draft_unlisted_extra_fixture_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            (base / "fixtures/revised/B-RFX-09_unreviewed.json").write_text("{}\n")
            with self.assertRaisesRegex(FixtureDriftError, "unlisted file"):
                verify_copy(Path(tmp))

    def test_draft_rewritten_checksum_list_fails_set_digest(self):
        """Editing a fixture and its SHA256SUMS line together still fails the set digest."""
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            rel = "fixtures/original/B-RFX-07_viewer-and-second-account.json"
            target = base / rel
            old_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            target.write_bytes(target.read_bytes() + b"\n")
            new_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            sums = base / "SHA256SUMS"
            sums.write_bytes(sums.read_bytes().replace(old_digest.encode(), new_digest.encode()))
            with self.assertRaisesRegex(FixtureDriftError, "set digest mismatch"):
                verify_copy(Path(tmp))

    def test_draft_compare_detects_a_drifted_sibling_copy(self):
        with tempfile.TemporaryDirectory() as good, tempfile.TemporaryDirectory() as bad:
            _copy_repo_fixtures(Path(good))
            base = _copy_repo_fixtures(Path(bad))
            target = base / "corrections/DELTA_records_v0.3.json"
            target.write_bytes(target.read_bytes() + b" ")
            code, out, _ = _run_main(["--root", str(ROOT), "--compare", good])
            self.assertEqual(code, 0)
            self.assertIn("compared 1 copies", out)
            code, _, err = _run_main(["--root", str(ROOT), "--compare", good, bad])
            self.assertEqual(code, 1)
            self.assertIn("sha256 mismatch", err)

    def test_draft_local_sibling_clones_match_when_present(self):
        siblings = [
            ROOT.parent / name for name in SIBLING_COPIES
            if (ROOT.parent / name).resolve() != ROOT and (ROOT.parent / name / FIXTURE_DIR).is_dir()
        ]
        if not siblings:
            self.skipTest("no sibling Group B clone with contracts/draft/v0.3 next to this checkout")
        code, _, err = _run_main(["--root", str(ROOT), "--compare", *map(str, siblings)])
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
