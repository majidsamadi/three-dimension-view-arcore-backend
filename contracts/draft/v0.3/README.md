# DRAFT / SYNTHETIC — NOT FROZEN

B-RFX-01..08 reconciled draft fixtures, v0.3 (P03). **Reference copy** for Group B; the Object Scanner backend holds a byte-identical consumer copy.

- Packet record: `WS-B-P03-C03-REVIEW-0.1` (see `WiseStay_Team_B_P03_Agreement_Reconciled_Draft_v0.3.md`).
- Source: `WiseStay_Team_B_C_HANDOVER03_Reconciliation_v0.1.zip`, sha256 `b550b4f592210856b5c9df970c2c85909d6477c0070d080ed7c9ad5964258549`. The 12 files are copied byte-for-byte; their sha256 values match the packet `MANIFEST.json`.
- Set digest, sha256 of `SHA256SUMS`: `945c37d59266ec214717eb76b92ed2170f56bf1f756936d7a393bf7554d58ba0`. The same constant is hard-coded in `tools/check_contract_fixtures.py` in every consumer repository.
- `status: PREPARED_NOT_EXECUTED_NOT_ACCEPTED` inside each fixture is authoritative. Every DELTA record in `corrections/DELTA_records_v0.3.json` is `PROPOSED_NOT_FROZEN`.
- No field here is a deployed API schema, codec, protection scheme, coordinate convention or measurement receipt. Labels such as `H-A@7` or `PART-A` are opaque synthetic labels.
- Freezing needs owner answers to Q01, Q03, Q04, Q05 and Q06 (see `docs/DECISIONS_PENDING.md`). Until then these files must not be edited in place.

## Effective revision

B-RFX-03 has two files. `fixtures/revised/B-RFX-03_version-component.v0.2.json` (fixture revision `0.2`, correction `BC03-COR-01`, DELTA-17) is effective. `fixtures/original/B-RFX-03_version-component.json` is kept for history and is treated as superseded by `tests/contract_fixtures.py`.

## Checking

```sh
python3 tools/check_contract_fixtures.py
python3 tools/check_contract_fixtures.py --compare ../three-dimension-object-backend
```

`SHA256SUMS` lists the 12 files in sorted order (LF only). `README.md` and `SHA256SUMS` sit outside the checksum set; an unlisted file under `fixtures/` or `corrections/` fails the check. `.gitattributes` marks this tree `-text` so git never rewrites the bytes.

Status: component-tested only (`tests/test_contract_fixture_sync.py`, `tests/test_contract_fixtures_v0_3.py`).

A stray `.DS_Store` (or any other unlisted file) under a checksum-closed subtree fails the checker by design; `.gitignore` ignores `.DS_Store` so it is never committed.
