# Decisions pending — Home Scanner backend (HSB)

Source: WBS §6 "Decisions to make later" (Q01–Q16). This file records which work in this repository waits on each decision. It does not answer any of them.

- Q01–Q05 and Q08–Q16 have no recorded owner answer (`.agents/tasks/3d-platform-progress-audit-2026-10-20.md`, P02 row).
- The agent-authored record `WS-3D-DECISIONS-DELEGATED-2026-10-20` (DELEGATED-PROVISIONAL) is not an owner decision and is not applied in this repository.
- Owner approval to merge `feature/3d-r0-foundation` into `main`: **OPEN**.

Status of this slice: component-tested only. Nothing here is integrated, accepted or deployed.

| ID | WBS title | Status | Source of status | Blocked in this repo | Left null / unset in this slice |
|---|---|---|---|---|---|
| Q01 | Service and shared-component design | OPEN | No owner answer recorded | HSB-01.3 onward (live identity/resource/authority adapters, persistence, operations); freeze of `contracts/draft/v0.3` | Ports in `src/wisestay_home_backend/ports/reference_authority.py` have no live implementation. Fixture location is a per-repo checksum-pinned draft copy, not a decided shared-contract home. |
| Q02 | Local capture and optional cloud refinement | OPEN | No owner answer recorded | HSB-04 (upload/processing) | No upload, staging or refinement route. B-RFX-06 "selected upload versus raw input" is skipped. |
| Q03 | Scale, accuracy and acceptance | OPEN | No owner answer recorded | Freeze of `contracts/draft/v0.3` | No thresholds. Every `physical_measurement_receipts` is `[]`; B-RFX-02 examples are skipped (no HSB consumer). |
| Q04 | Devices and interaction delivery | OPEN | No owner answer recorded | Freeze of `contracts/draft/v0.3` | No device profile. B-RFX-07 "device loss while opening exact asset" is skipped. |
| Q05 | Asset representations and protected opening | OPEN | No owner answer recorded | HSB-03, HSB-06; freeze of `contracts/draft/v0.3` | `codec`, `protection_scheme` and `coordinate_convention` stay `null`. B-RFX-03 "missing required opaque test component" is skipped (no component-set validator). |
| Q06 | Product, quantity and planning semantics | OPEN — result organisation ALT1 recorded only | `WiseStay_F_Q06_Selected_Organization_v1.0` ("Separate classification, reason and processing status") | Freeze of `contracts/draft/v0.3` | No schema, encoding, threshold, algorithm or precedence chosen. B-RFX-05 examples are skipped. |
| Q07 | Audience, rented-home privacy and sharing | OPEN — first-slice content scope recorded only | `WiseStay_Human_First_Slice_Content_2026-10-14_210147.json` ("Synthetic data + permitted unoccupied references") | HSB-01.3 onward (action/audience matrix), HSB-05 | `ReferenceAction` stays limited to the existing `read_metadata` / `view_reference`. No audience, consent or sharing model. |
| Q08 | Retention, deletion and evidence reuse | OPEN | No owner answer recorded | HSB-08 | No retention period. B-RFX-06 "restored metadata after withdrawal" is tested only as "withdrawn stays withdrawn". |
| Q09 | Workload, cost and responsiveness | OPEN | No owner answer recorded | HSB-04 | No quotas, timeouts or budgets. |
| Q10 | Commercial viewing and portable delivery | OPEN | No owner answer recorded | HSB-06 | No commercial flag, price or export right. |
| Q11 | External developer onboarding | OPEN | No owner answer recorded | HSB-08 (developer access) | B-RFX-08 examples are skipped; no registration or client credential. |
| Q12 | Notification and support ownership | OPEN | No owner answer recorded | None identified in this slice | — |
| Q13 | Virtual routes versus live indoor navigation | OPEN | No owner answer recorded | None identified in this slice | B-RFX-03 "map correction invalidates target/anchor assumption" is skipped. |
| Q14 | Shop/property registration compatibility | OPEN | No owner answer recorded | Property binding beyond an exact caller-supplied `property_id` | No property lookup or creation. A local project label never becomes a property (B-RFX-01 test). |
| Q15 | Deployment and resource ownership | OPEN | No owner answer recorded | All HSB deployment/release tasks | CI (`.github/workflows/ci.yml`) runs tests only; no deployment, AWS resource or environment. |
| Q16 | Application embedding and predecessor coverage | OPEN | No owner answer recorded | None identified in this slice | — |

## Fixture freeze

`contracts/draft/v0.3` stays DRAFT / SYNTHETIC — NOT FROZEN until Q01, Q03, Q04, Q05 and Q06 are answered by the owner. The skip list is produced by `tests/test_contract_fixtures_v0_3.py` (`test_draft_every_example_is_mapped_or_explicitly_skipped`).
