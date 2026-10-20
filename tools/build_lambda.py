"""Build the deterministic Home Scanner Lambda package (plan X.10).

Stdlib ``zipfile`` only.  The archive holds ``src/wisestay_home_backend/**/*.py``
(no tests, no bytecode) with fixed 1980-01-01 timestamps and sorted entries, so
the same source always gives the same bytes.  Prints the base64 sha256 used
as ``lambda_package_sha256_b64`` (Terraform ``source_code_hash``).

Usage::

    python3 tools/build_lambda.py                 # writes dist/home-scanner-lambda.zip
    python3 tools/build_lambda.py --out /tmp/x.zip
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "wisestay_home_backend"
DEFAULT_OUT = ROOT / "dist" / "home-scanner-lambda.zip"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def package_files(src: Path = ROOT / "src") -> list[Path]:
    files = [p for p in (src / PACKAGE).rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(files, key=lambda p: p.relative_to(src).as_posix())


def build(out: Path = DEFAULT_OUT, src: Path = ROOT / "src") -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in package_files(src):
            info = zipfile.ZipInfo(path.relative_to(src).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes())
    return base64.b64encode(hashlib.sha256(out.read_bytes()).digest()).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    digest = build(args.out)
    print(f"{args.out} sha256(base64) {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
