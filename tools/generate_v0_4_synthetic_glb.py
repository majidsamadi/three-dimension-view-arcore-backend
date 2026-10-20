"""Generate the DRAFT / SYNTHETIC v0.4 unit-box GLB and its facts file (P03, S0.2).
Stdlib only and deterministic: running it twice writes the same bytes.
The box is 1 m on every axis, axis-aligned, standing on the floor
(min [-0.5, 0, -0.5], max [0.5, 1, 0.5]), right-handed, +Y up, metres.
It has 8 float32 positions, 36 uint16 indices (12 triangles, outward
counter-clockwise winding), one mesh, one node named ``unit-box``, no
extensions and no URIs.  It is a test asset only, never a captured scene.
Usage::
    python3 tools/generate_v0_4_synthetic_glb.py            # write into contracts/draft/v0.4
    python3 tools/generate_v0_4_synthetic_glb.py --check    # fail if the committed bytes differ
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "contracts/draft/v0.4/fixtures/assets"
GLB_NAME = "synthetic-unit-box.glb"
FACTS_NAME = "synthetic-unit-box.facts.json"
NODE_NAME = "unit-box"
BOUNDS_MIN = [-0.5, 0.0, -0.5]
BOUNDS_MAX = [0.5, 1.0, 0.5]
# Corner i has x = max when bit 0 is set, y = max for bit 1, z = max for bit 2.
POSITIONS = [
    [BOUNDS_MAX[a] if (i >> a) & 1 else BOUNDS_MIN[a] for a in range(3)] for i in range(8)
]
# Two triangles per face, counter-clockwise seen from outside the box.
INDICES = [
    0, 4, 6, 0, 6, 2,  # -X
    1, 3, 7, 1, 7, 5,  # +X
    0, 1, 5, 0, 5, 4,  # -Y
    2, 6, 7, 2, 7, 3,  # +Y
    0, 2, 3, 0, 3, 1,  # -Z
    4, 5, 7, 4, 7, 6,  # +Z
]
_GLB_MAGIC = 0x46546C67  # "glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942
def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * (-len(data) % 4)
def build_glb() -> bytes:
    positions = b"".join(struct.pack("<3f", *p) for p in POSITIONS)
    indices = struct.pack(f"<{len(INDICES)}H", *INDICES)
    binary = _pad(positions + indices, b"\x00")
    gltf = {
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(POSITIONS), "type": "VEC3",
             "min": BOUNDS_MIN, "max": BOUNDS_MAX},
            {"bufferView": 1, "componentType": 5123, "count": len(INDICES), "type": "SCALAR"},
        ],
        "asset": {"generator": "wisestay generate_v0_4_synthetic_glb.py (synthetic)", "version": "2.0"},
        "bufferViews": [
            {"buffer": 0, "byteLength": len(positions), "byteOffset": 0, "target": 34962},
            {"buffer": 0, "byteLength": len(indices), "byteOffset": len(positions), "target": 34963},
        ],
        "buffers": [{"byteLength": len(binary)}],
        "meshes": [{"name": NODE_NAME, "primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "nodes": [{"mesh": 0, "name": NODE_NAME}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }
    json_chunk = _pad(json.dumps(gltf, sort_keys=True, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return b"".join([
        struct.pack("<III", _GLB_MAGIC, 2, total),
        struct.pack("<II", len(json_chunk), _CHUNK_JSON), json_chunk,
        struct.pack("<II", len(binary), _CHUNK_BIN), binary,
    ])
def build_facts(glb: bytes) -> bytes:
    facts = {
        "bounds_m": {"max": BOUNDS_MAX, "min": BOUNDS_MIN},
        "bytes": len(glb),
        "node_names": [NODE_NAME],
        "sha256": hashlib.sha256(glb).hexdigest(),
        "triangles": len(INDICES) // 3,
    }
    return (json.dumps(facts, indent=2, sort_keys=True) + "\n").encode("utf-8")
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ASSET_DIR, help="output directory")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args(argv)
    glb = build_glb()
    outputs = {GLB_NAME: glb, FACTS_NAME: build_facts(glb)}
    if args.check:
        drift = [name for name, data in outputs.items()
                 if not (args.out / name).is_file() or (args.out / name).read_bytes() != data]
        if drift:
            print(f"synthetic unit box: FAILED: differs: {', '.join(drift)}", file=sys.stderr)
            return 1
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, data in outputs.items():
            (args.out / name).write_bytes(data)
    print(f"synthetic unit box: {len(glb)} bytes, sha256 {hashlib.sha256(glb).hexdigest()}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
