"""Docs check for the DELEGATED-PROVISIONAL decisions register (S0.3, Q01-Q16).
Parses docs/DECISIONS_PENDING.md and checks every Qnn row links to a heading
that exists in the pinned verbatim copy of the delegated record.
This file is byte-identical in HSB, OSB, HCB and WFB.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/DECISIONS_PENDING.md"
RECORD_SHA256 = "5bf4fb3dc3cd787da3c262e382a09334ae0a4a5ebf05a10ab79bd9c3ccef1b2d"
RECORD_REL = "decisions/WS-3D-DECISIONS-DELEGATED-2026-10-20.md"
Q06_OWNER = ('Owner answer kept: ALT1 "Separate classification, reason and processing status" '
             "(Q06_RESULT_ORGANIZATION_HUMAN_20261015_073548).")
Q07_OWNER = ('Owner answer kept: "Synthetic data + permitted unoccupied references" '
             "(Q07_FIRST_SLICE_CONTENT_HUMAN_20261014_210147).")
_LINK = re.compile(r"\[§(Q\d\d)\]\(([^)#]+)#([^)]+)\)")
def github_slug(heading: str) -> str:
    """GitHub heading anchor: lowercase, drop chars outside [\\w\\- ], spaces -> '-'."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower(), flags=re.ASCII).replace(" ", "-")
def register_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if re.match(r"^\| Q\d\d \|", line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows
class DecisionsRegisterTests(unittest.TestCase):
    def test_S0_decisions_register_links_resolve(self):
        text = REGISTER.read_text(encoding="utf-8")
        rows = register_rows(text)
        self.assertEqual([row[0] for row in rows], [f"Q{n:02d}" for n in range(1, 17)])
        record = REGISTER.parent / RECORD_REL
        self.assertTrue(record.is_file(), record)
        raw = record.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), RECORD_SHA256)
        headings = {
            match.group(1): github_slug(match.group(0)[4:])
            for match in re.finditer(r"^### (Q\d\d) ·.*$", raw.decode("utf-8"), flags=re.M)
        }
        self.assertEqual(sorted(headings), [f"Q{n:02d}" for n in range(1, 17)])
        for row in rows:
            qid, status = row[0], row[2]
            self.assertTrue(status.startswith("DELEGATED-PROVISIONAL"), (qid, status))
            links = _LINK.findall(row[4])
            self.assertEqual(len(links), 1, (qid, row[4]))
            link_q, target, anchor = links[0]
            self.assertEqual(link_q, qid)
            self.assertEqual(target, RECORD_REL)
            self.assertTrue((REGISTER.parent / target).is_file(), target)
            self.assertEqual(anchor, headings[qid], qid)
        by_id = {row[0]: row for row in rows}
        self.assertTrue(by_id["Q06"][3].startswith(Q06_OWNER), by_id["Q06"][3])
        self.assertTrue(by_id["Q07"][3].startswith(Q07_OWNER), by_id["Q07"][3])
        self.assertEqual(by_id["Q06"][2], "DELEGATED-PROVISIONAL (extends owner answer)")
        self.assertEqual(by_id["Q07"][2], "DELEGATED-PROVISIONAL (extends owner answer)")
if __name__ == "__main__":
    unittest.main()
