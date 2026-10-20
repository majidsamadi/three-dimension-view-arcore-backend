"""Checksum sync-check for the DRAFT v0.4 contract fixture copy (P03, S0.2).
The repository copy must verify; a temp-dir copy with any drift must fail.
This file is byte-identical in HSB, OSB, HCB and WFB.
"""
from __future__ import annotations
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tools.check_contract_fixtures_v0_4 import (
    EXPECTED_FILE_COUNT,
    FIXTURE_DIR,
    SET_DIGEST,
    FixtureDriftError,
    load_fixture,
    main,
    verify_copy,
)
ROOT = Path(__file__).resolve().parents[1]
SIBLING_COPIES = (
    "three-dimension-view-arcore", "three-dimension-view", "three-dimension-view-arcore-backend",
    "three-dimension-object-backend", "three-dimension-object-app", "home-composer-backend",
    "home-composer-app", "where-can-find-this-backend", "where-can-find-this-app",
)
def _copy_repo_fixtures(dest: Path) -> Path:
    shutil.copytree(ROOT / FIXTURE_DIR, dest / FIXTURE_DIR)
    return dest / FIXTURE_DIR
def _run_main(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()
class ContractFixtureSyncV04Tests(unittest.TestCase):
    def test_P03_v0_4_repository_copy_matches_pinned_set_digest(self):
        entries = verify_copy(ROOT)
        self.assertEqual(len(entries), EXPECTED_FILE_COUNT)
        self.assertEqual(EXPECTED_FILE_COUNT, 17)
        code, out, _ = _run_main(["--root", str(ROOT)])
        self.assertEqual(code, 0)
        self.assertIn(f"contract fixtures v0.4: 17 files verified, set {SET_DIGEST[:8]}", out)
    def test_P03_v0_4_fixtures_are_draft_and_glb_facts_match(self):
        for rel in ("api/home-scanner.v0.4.json", "api/object-scanner.v0.4.json",
                    "api/composer.v0.4.json", "api/finder.v0.4.json"):
            fixture = load_fixture(rel, ROOT)
            self.assertEqual(fixture["status"], "DRAFT_SYNTHETIC_NOT_FROZEN", rel)
            self.assertEqual(fixture["version"], "0.4-draft", rel)
        facts = load_fixture("assets/synthetic-unit-box.facts.json", ROOT)
        glb = (ROOT / FIXTURE_DIR / "fixtures/assets/synthetic-unit-box.glb").read_bytes()
        self.assertEqual(facts["sha256"], hashlib.sha256(glb).hexdigest())
        self.assertEqual(facts["bytes"], len(glb))
        self.assertEqual(glb[:4], b"glTF")
    def test_P03_v0_4_tampered_fixture_byte_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            target = base / "fixtures/api/home-scanner.v0.4.json"
            target.write_bytes(target.read_bytes().replace(b"home-captures", b"home-capturez", 1))
            with self.assertRaisesRegex(FixtureDriftError, "sha256 mismatch"):
                verify_copy(Path(tmp))
            code, _, err = _run_main(["--root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("FAILED", err)
    def test_P03_v0_4_missing_fixture_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            (base / "fixtures/assets/synthetic-unit-box.glb").unlink()
            with self.assertRaisesRegex(FixtureDriftError, "missing fixture file"):
                verify_copy(Path(tmp))
    def test_P03_v0_4_unlisted_extra_fixture_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            (base / "fixtures/api/.DS_Store").write_bytes(b"\x00")
            with self.assertRaisesRegex(FixtureDriftError, "unlisted file"):
                verify_copy(Path(tmp))
    def test_P03_v0_4_rewritten_checksum_list_fails_set_digest(self):
        """Editing a fixture and its SHA256SUMS line together still fails the set digest."""
        with tempfile.TemporaryDirectory() as tmp:
            base = _copy_repo_fixtures(Path(tmp))
            rel = "fixtures/common/policy-limits.v0.4.json"
            target = base / rel
            old_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            data = json.loads(target.read_text(encoding="utf-8"))
            data["limits"]["components_per_upload"]["value"] = 11
            target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            new_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            sums = base / "SHA256SUMS"
            sums.write_bytes(sums.read_bytes().replace(old_digest.encode(), new_digest.encode()))
            with self.assertRaisesRegex(FixtureDriftError, "set digest mismatch"):
                verify_copy(Path(tmp))
    def test_P03_v0_4_compare_detects_a_drifted_sibling_copy(self):
        with tempfile.TemporaryDirectory() as good, tempfile.TemporaryDirectory() as bad:
            _copy_repo_fixtures(Path(good))
            base = _copy_repo_fixtures(Path(bad))
            target = base / "fixtures/viewer/viewer-interface.v0.4.json"
            target.write_bytes(target.read_bytes() + b" ")
            code, out, _ = _run_main(["--root", str(ROOT), "--compare", good])
            self.assertEqual(code, 0)
            self.assertIn("compared 1 copies", out)
            code, _, err = _run_main(["--root", str(ROOT), "--compare", good, bad])
            self.assertEqual(code, 1)
            self.assertIn("sha256 mismatch", err)
    def test_P03_v0_4_local_sibling_clones_match_when_present(self):
        siblings = [
            ROOT.parent / name for name in SIBLING_COPIES
            if (ROOT.parent / name).resolve() != ROOT and (ROOT.parent / name / FIXTURE_DIR).is_dir()
        ]
        if not siblings:
            self.skipTest("no sibling 3D clone with contracts/draft/v0.4 next to this checkout")
        code, _, err = _run_main(["--root", str(ROOT), "--compare", *map(str, siblings)])
        self.assertEqual(code, 0, err)
if __name__ == "__main__":
    unittest.main()
