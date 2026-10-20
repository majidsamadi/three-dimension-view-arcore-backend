"""Deterministic Lambda package (plan X.10).  Status: component-tested."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tools.build_lambda import build


class BuildLambdaTests(unittest.TestCase):
    def test_archive_is_deterministic_and_source_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a.zip", Path(tmp) / "b.zip"
            digest = build(first)
            self.assertEqual(build(second), digest)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertTrue(all(n.startswith("wisestay_home_backend/") and n.endswith(".py")
                                    for n in names), names)
                self.assertFalse([n for n in names if "__pycache__" in n or "tests" in n.split("/")])
                self.assertIn("wisestay_home_backend/entrypoints/lambda_handler.py", names)
                self.assertEqual({i.date_time for i in archive.infolist()}, {(1980, 1, 1, 0, 0, 0)})

    def test_handler_importable_from_zip_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pkg.zip"
            build(out)
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "import wisestay_home_backend.entrypoints.lambda_handler as m; "
                    "assert m.__file__.startswith(sys.argv[1]); "
                    "assert 'boto3' not in sys.modules; print(callable(m.handler))")
            result = subprocess.run([sys.executable, "-I", "-c", code, str(out)],
                                    capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "True")


if __name__ == "__main__":
    unittest.main()
