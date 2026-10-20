# WiseStay connected 3D platform — delegated provisional decision record (Q01–Q16)

Record ID: `WS-3D-DECISIONS-DELEGATED-2026-10-20` · Version 0.1 · Date 2026-10-20

## 0. Status, authority and how to read this record

- **Authority.** On 2026-10-20 the owner, Majid Samadi, explicitly delegated all open decisions Q01–Q16 to the engineering agent ("I am approving for everything"). Every answer below is **DELEGATED-PROVISIONAL**: the agent chose it under delegation. It is **not** the owner's original intent and must not be cited as an owner decision.
- **Reversible by design.** Each entry states how to reverse it. The owner, or any later reviewed evidence, can overturn any entry at any time. Overturning one entry moves only the work that consumes it (Delivery Plan §9).
- **Two entries carry earlier owner answers. Both are kept unchanged:**
  - **Q07 (first-slice content).** Owner answer: "Synthetic data + permitted unoccupied references". Record `Q07_FIRST_SLICE_CONTENT_HUMAN_20261014_210147`. The file is at `~/Documents/New project/coordination/wisestay-3d/WiseStay_Human_First_Slice_Content_2026-10-14_210147.json`, not in `~/Downloads` as the brief said.
  - **Q06 (result organisation).** Owner-relayed answer: ALT1, "Separate classification, reason and processing status". Record `Q06_RESULT_ORGANIZATION_HUMAN_20261015_073548`, in `WiseStay_F_Q06_Selected_Organization_v1.0.zip`.
  - The delegated parts of Q06 and Q07 extend these answers. They do not replace them.
- **What this record does not do.** It doesn't close any WBS task, package or release gate. It doesn't waive physical, QA, security or UX evidence. It doesn't authorise production activation, real customer data, spending beyond the Q09 ceiling, or activation of the optional packages P55–P64. Prototype or CI passes still do not close tasks.
- **Constraints carried forward unchanged (WBS §1):**
  - WebGPU as the visualisation target
  - Vue/Suha clients and the independent shared engine
  - Python backends
  - S3/AWS with Terraform
  - Central identity (User Management, `user.wizestay.com`)
  - Canonical property in Resvanta (REAL/VIRTUAL)
  - GitHub branch → main delivery
  - Local capture first and web-first rollout
  - No default training on customer data
  - Media rights are not inherited from IoT controller rights
- **Decision style.** Every choice favours the cheapest reversible option that fits the existing stack. Features that need real-world evidence stay **DISABLED**, not quietly faked.

### Sources read

| Source | Used for |
|---|---|
| `~/Downloads/WiseStay_3D_Platform_Implementation_Work_Breakdown_v1.0.pdf` §1, §2, §5, §6 | Q01–Q16 wording, required decision outputs, constraints |
| `~/Downloads/WiseStay_3D_Parallel_Delivery_Plan_v1.0.pdf` §9, §9.1, package list | Due windows, consuming packages (P01–P64) |
| `.agents/tasks/3d-platform-progress-audit-2026-10-20.md` | Current status: 0/119 complete, 21 PI; recorded Q06/Q07 answers |
| `WiseStay_Team_B_C_HANDOVER03_Reconciliation_v0.1.zip` → `WiseStay_Team_B_P03_Agreement_Reconciled_Draft_v0.3.md` | DELTA-01…21 decision dependencies (all `PROPOSED_NOT_FROZEN`) |
| `WiseStay_H_P04_Ownership_Reconcile_Candidate_01_v1.0.zip` | Unresolved `OBJECT_SCANNER_OWNERSHIP_MISSING`, website/OAuth controller alignment |
| `.agents/3d-work/three-dimension-view-arcore-backend/docs/DECISIONS_AND_ACCEPTANCE.md` | Earlier D01–D18 register and AT01–AT22 acceptance IDs |
| `.agents/3d-work/three-dimension-view-arcore/docs/DEVELOPMENT_PROFILE.md`, `sdk/src/viewer.ts` | TDVDEV01 is dev-only; the existing viewer is WebGL2 |
| `wisestay-infrastructure` @ `origin/main` 13c106c (local clone 6844363 is stale) | `contracts/ownership.json`, `environments/dev/config.example.json`, `applications/websites/main.tf`, `modules/foundation` budgets, `docs/SERVERLESS_COST_MODEL.md`, `docs/AUTOMATIC_REQUEST_DRIVEN_RELEASES.md` |
| `wisestay-user-management-backend/deployment/web_registration.py` | Website/API registration pattern; dev target account and region |
| `wisestay-resvanta` @ `origin/main` 7629dbd | REAL/VIRTUAL property rules; registry write path |
| `wisestay-core-backend`, `wisestay-worker` @ `origin/main` | Existing `notify(user, template, reference)` producer; Worker notification transport |

All repositories were read only. Nothing was edited, committed, pushed or deployed.

---

## 1. Decisions

Each entry has the same fields: Options · **Provisional answer** · Rationale · Cost / risk · Reverse by · Unblocks (WBS tasks / delivery packages) · Overturn if.

### Q01 · Service and shared-component design

**Options**
- (a) A new shared SDK/contracts repository.
- (b) The engine repo also hosts every cross-product contract.
- (c) Producer-owned contracts: consumers vendor pinned copies and check them in CI.
- (d) One monolithic 3D backend.

**Provisional answer: (c), plus the existing engine boundary.**
- `three-dimension-view-arcore` stays the single independent engine and SDK. No new repository is created (matches D17).
- Consumers pin the engine by exact commit or tag.
- Each schema lives in the repository that produces it:
  - engine output and asset envelope → ARC
  - home scene → HSB
  - object → OSB
  - design → HCB
  - finder result/location → WFB
- Consumers vendor a pinned copy plus a SHA-256 sync test that fails CI on drift. The same check replaces the three unchecked `web-session.mjs` copies.
- The four backends are separate Python ≥3.11 services. They follow the hexagonal domain/application/ports layout already used by `asset_reference.py`. Each runs as request-driven AWS Lambda behind API Gateway REST, matching `applications/serverless-edge-dev`.
- Apps call only their own backend. Cross-product reads go through a published reference, for example Composer resolving an Object version via OSB, never through direct table or bucket access.

**Rationale.** This needs no new repository. It reuses the existing engine and the existing `asset_reference` boundary code, and it keeps one owner per contract.

**Cost / risk.** Near zero. Risk: vendored copies drift. The hash test mitigates that.

**Reverse by.** Move the schemas into a shared package later. Consumers then change only their import path and pin.

**Unblocks.** ARC-02, HSB-01, OSB-01, HCB-01, WFB-01, INF-01 / P03 (draft freeze of DELTA-01…04, -14, -18), P09, P15.

**Overturn if.**
- Two or more consumers need a breaking contract change in the same release more than once.
- The sync-check cost outweighs a shared package.

### Q02 · Local capture and optional cloud refinement

**Options**
- (a) Local-only.
- (b) Local plus opt-in cloud refinement.
- (c) Cloud-mandatory.

**Provisional answer: (a).**
- Capture and reconstruction run on the device.
- Cloud refinement is **DISABLED**: no flag, no GPU resource, no raw-input upload path.
- Upload is an explicit user action. It sends only the processed representation (glTF + envelope, see Q05), never raw RGB/depth/IMU.
- P55/P56 stay inactive. An equal-input evaluation protocol (AT19) may be written as a document, but it is not run.

**Rationale.** This is the owner's recorded local-first direction. It costs nothing and avoids raw-imagery custody.

**Cost / risk.** $0 GPU spend. Risk: local quality may be insufficient. That is exactly what P05/P11/P12 must measure.

**Reverse by.** Activate P55 as a separate reviewed mode with its own consent screen. Local acceptance stays independent.

**Unblocks.** ARC-03…05, HSB-04, OSB-03, INF-01 / P11, P12 (local boundary). P55 remains blocked by design.

**Overturn if.** Measured local results on the P05 reference set fail the Q03 thresholds, and a same-input cloud candidate passes them.

### Q03 · Scale, accuracy and acceptance

**Options**
- (a) No numeric thresholds; descriptive only.
- (b) Provisional thresholds frozen before scoring.
- (c) Thresholds chosen after seeing results. This is prohibited.

**Provisional answer: (b).**

The thresholds below are **PROVISIONAL**. They must be hashed into the P05 harness case manifest before any scoring run. Changing them creates a new threshold version, and earlier scores do not carry over. **They need real measured data to validate.** They are engineering starting points, not measured capability.

**Reference method**
- A human measures with a laser distance meter (±2 mm class) and a steel tape before capture.
- The measurements are recorded and hashed.
- First profile: at least 5 rooms and at least 20 objects. Rooms are permitted and unoccupied, per Q07.

**Thresholds**

| Claim | Provisional threshold |
|---|---|
| Room dimension (wall-to-wall, ceiling height), "metric" scale claim | abs error ≤ max(5 cm, 2 %) on ≥ 90 % of measured spans |
| Object bounding dimensions, "verified" scale claim | abs error ≤ max(1 cm, 3 %) per axis |
| Room completeness | ≥ 90 % of reference floor area observed; unobserved areas are labelled, never filled as fact |
| Multi-session alignment | ≤ 5 cm RMS residual on ≥ 4 reference points |
| Verified fit / clearance (Composer) | Allowed only when combined uncertainty is less than the clearance margin. Otherwise "unverified fit" |
| Shelf location (curated finder) | ≥ 95 % correct at bay + shelf level on the curated reference shop |
| Exact-confirmed product match | false exact-confirm ≤ 1 % on the reference query set |
| Automated counts / live localisation | No threshold. These features are disabled (Q06, Q13) |

**Rationale.** These thresholds are conservative enough for furniture-fit usefulness and stop the system from claiming accuracy it can't support.

**Cost / risk.** Field time for measurements. Risk: the numbers may be too strict or too loose. Either way they are versioned and re-frozen, never tuned to results.

**Reverse by.** Issue a new threshold version before the next scoring run.

**Unblocks.** ARC-06, ARC-10, HCB-03…04, WFB-11 / P05 (manifest schema and frozen thresholds), P13. P28/P43 still need the physical data.

**Overturn if.**
- The reference instrument error is larger than assumed.
- Product review shows a function needs tighter tolerance, for example built-in furniture.

### Q04 · Devices and interaction delivery (includes ARC-08 fallback policy)

**Options**
- (a) WebGPU only.
- (b) WebGPU primary plus a labelled WebGL2 compatibility path.
- (c) Silent fallback. This is prohibited.

**Provisional answer: (b).**

**First declared profile**
- Capture: Android with ARCore Depth support through the existing Capacitor/native path. The first device is the dev OPPO CPH2603 already used by the arcore harness. Its depth support must be qualified, not assumed.
- View: Chrome stable desktop (Windows/macOS) and Chrome Android on the same device, using WebGPU.

**Compatibility path**
- The existing WebGL2 viewer (`sdk/src/viewer.ts`) is a user-visibly labelled "Compatibility view (WebGL2) — not WebGPU".
- It is off unless `navigator.gpu` is missing or adapter request fails.
- It is never counted as an AT15 pass.

**Unavailable behaviour**
- Every other browser/device combination, including Safari, Firefox and iOS capture, is **unqualified**. Those users see an explicit "not supported yet" state.
- Offline viewing covers only the user's own locally captured projects (existing local-first behaviour). There is no offline viewing of published assets.

**Rationale.** WebGPU stays the target. The WebGL2 code already exists, and labelling it is cheaper and more honest than blocking every non-WebGPU user.

**Cost / risk.** Low. Risk: users may treat the compatibility view as equivalent. The label and AT15 exclusion address that.

**Reverse by.** Remove the compatibility flag to make the product WebGPU-only, or add profiles as they are qualified.

**Unblocks.** ARC-08, HSA-08, OSA-08, MOB-03 / P09, P14 (first profile). P48 later.

**Overturn if.**
- The device matrix shows WebGPU unavailable on most target users' devices.
- The WebGL2 path can't preserve the required semantics (DELTA-13).

### Q05 · Asset representations and protected opening

**Options**
- (a) A custom container (extend TDVDEV01).
- (b) Reuse existing formats: glTF 2.0/GLB geometry plus a versioned JSON metadata envelope.
- (c) USDZ/other.
- (d) Point cloud / Gaussian splats.

**Provisional answer: (b).**

**Representation**
- Each asset version consists of one or more GLB components plus a `wisestay.asset-envelope.v1` JSON envelope. The envelope records:
  - asset ID, kind (home | object | shop), immutable version and producer
  - component list with SHA-256 digests and byte sizes
  - frame: right-handed, Y-up, metres (D02)
  - scale-claim class: unknown | estimated | seller-declared | reference-supported | independently-verified (DELTA-05)
  - provenance and audience projection ID
- No mesh compression (Draco/meshopt) in the first slice.

**Protection**
- No new cryptographic scheme.
- Assets sit in private S3. A service authorisation check precedes short-lived presigned GETs (Q15).
- TDVDEV01 stays development-only (DEVELOPMENT_PROFILE.md) and is never promoted by assertion.

**Recovery and legacy**
- Versions are immutable, and the envelope digests make tampering and partial copies detectable (DELTA-17).
- Legacy three-dimension-view `Project` v1 / GLB export is preserved for legacy local projects.
- New service assets have no portable export (Q10).

**Rationale.** This uses open, widely supported tooling and invents no codec or cryptography. Three.js and WebGPU loaders already read glTF.

**Cost / risk.** Low. Risk: protection is only access control, so a viewer with access can save the bytes. That is acceptable for synthetic/unoccupied first-slice content and is documented.

**Reverse by.** Envelope v2 can reference new component types or encryption. Readers reject unknown major versions explicitly.

**Unblocks.** ARC-07, HSB-03, HSB-06, OSB-06, HCB-08 / P03 (DELTA-07/08/17/21 wording), P15, P26, P27.

**Overturn if.**
- A threat review requires at-rest client-side protection before occupied-home content is admitted.
- glTF can't carry the required observation semantics.

### Q06 · Product, quantity and planning semantics

**Owner part kept:** result organisation ALT1, with classification, reason and processing status as separate facets.

**Options for the rest**
- (a) Automate counts and shortages from images.
- (b) Merchant-authoritative quantities, image observations as evidence only.
- (c) No quantities.

**Provisional answer: (b), with automation disabled.**
- **Match classification:** exact-confirmed | probable | similar | ambiguous | no-match.
- **"Unknown" is not a match class.** It goes in the separate processing-status/evidence facet. This is consistent with ALT1 and resolves DELTA-10 provisionally.
- Provider failure is a processing status, never "no-match".
- **Exact-confirmed** requires a merchant catalogue link to the exact variant (GTIN/merchant SKU) or explicit merchant confirmation. A similarity score never upgrades a class.
- **Quantities** are merchant-entered with a recorded basis. Image observations record only visible facings plus coverage and interval. The system never infers zero stock, shortage or a sale.
- **Shortage and recount recommendations are DISABLED.**
- **Fit** is "verified" only under the Q03 conditions; otherwise it is "unverified fit".

**Rationale.** This keeps the owner's ALT1 answer. It avoids false availability claims, which is the highest-harm failure.

**Cost / risk.** Merchant effort. Risk: less automation value early, which is accepted.

**Reverse by.** Enable automated counting only after a P40/P41 field qualification against frozen Q03 retail thresholds.

**Unblocks.** HCB-04, WFB-02, WFB-05, WFB-07…08 / P23, P31 (fit semantics), P40/P41 (definitions only).

**Overturn if.**
- Merchants reject manual counts.
- A measured observation engine passes a frozen count threshold.

### Q07 · Audience, rented-home privacy and sharing

**Owner part kept:** the first slice uses only synthetic data and explicitly permitted unoccupied references. No occupied-home content. Each unoccupied reference still needs identified permission and provenance before it is collected or used.

**Options**
- (a) Inherit IoT/property roles. This is prohibited by the WBS.
- (b) An explicit per-resource grant matrix.
- (c) Public by default.

**Provisional answer: (b).** "Creator" means the capturing account. Grants are per resource, explicit, and revocable.

| Action | Personal object / home | Owner–tenant home | Merchant shop / product | Composer design |
|---|---|---|---|---|
| Capture / upload | Creator | Owner of the canonical property, unoccupied only (first slice) | Merchant-org member with merchant role | — |
| Review / publish | Creator | Owner. Occupied-home publication **DISABLED** until consent rules are reviewed | Merchant-org reviewer | Design owner publishes revisions |
| View | Explicit grantees | Explicit grantees, for example prospective tenants named by the owner | Any signed-in shopper sees the published shop projection | viewer / commenter / editor grantees |
| Place in a design | Grantee with place right | Grantee with place right | Signed-in users, for published seller Object IDs | Editor |
| Comment / edit | — | — | — | Commenter / editor, granted by the design owner |

- An object-only share never exposes the home.
- IoT controller, tenancy or staff roles grant nothing on their own.
- Every grant needs a verified central-identity account. There are no anonymous or link-only grants in the first slice.

**Rationale.** These are minimal explicit rights. The privacy-hard occupied-home case stays disabled, consistent with the owner's first-slice answer.

**Cost / risk.** Low. Risk: grants are more work for users, which is accepted.

**Reverse by.** Add a reviewed occupied-home consent flow (tenant co-approval) as a new matrix version.

**Unblocks.** HSB-05, OSB-05, HCB-06, CORE-02 / P02, P25 (first slice), P32 (roles).

**Overturn if.**
- A privacy or legal review requires a different default.
- The owner states different intended audiences.

### Q08 · Retention, deletion and evidence reuse

**Options**
- (a) Keep everything.
- (b) Short, purpose-specific lifecycles with dependency-aware tombstones.
- (c) Immediate hard delete.

**Provisional answer: (b). All durations are PROVISIONAL and untested.**

| Data | Lifecycle |
|---|---|
| Raw capture (RGB/depth/IMU) | Never leaves the device (Q02), so the server keeps nothing. The local copy is under user control |
| Unfinalised upload staging | S3 lifecycle: abort incomplete multipart after 1 day; expire unfinalised objects after 7 days |
| Rejected candidates | 30 days, then deleted |
| Published asset versions | Kept until withdrawn. Withdrawal blocks new opens and grants immediately (AT17). Bytes are deleted 30 days later. Designs keep a tombstone reference, not bytes |
| Finder query photos | Processed, then deleted within 24 h (S3 expiry on the `query/` prefix). Never kept for training |
| Diagnostics / logs | CloudWatch log retention 14 days. No imagery or raw coordinates in logs |
| Collaboration history | Kept with the design. Deleted with the design. Comments on a withdrawn asset keep text but not asset bytes |
| Training on customer data | **None.** No training pipeline exists. Any future consent flag defaults to false |

**Rationale.** Smallest custody footprint, cheapest storage, and it matches the WBS rule of no default training.

**Cost / risk.** Minimal. Risk: 30-day windows may conflict with a legal hold or dispute need. The policy is versioned so that can be added.

**Reverse by.** Change the lifecycle rules (Terraform) and policy version. Already-deleted data can't be restored. That is the one irreversible effect, so dev uses synthetic data only.

**Unblocks.** HSB-08, OSB-07, WFB-10, IDM-02 / P15, P25 (first data-handling policy). P51 later.

**Overturn if.** A legal or privacy review, or a user dispute, requires longer retention or legal-hold support.

### Q09 · Workload, cost and responsiveness

**Options**
- (a) Always-on compute.
- (b) Request-driven serverless that idles to zero, under a tagged budget with alerts.
- (c) Unbounded.

**Provisional answer: (b).**

**Development budget ceiling: USD 25 / month for all 3D resources.** It is tracked by an AWS Budgets cost budget filtered on `CostAllocation = wisestay-dev-3d`, following the existing `modules/foundation` `aws_budgets_budget.environment` pattern.

**Alerts**
- ACTUAL 50 %, 80 % and 100 %, plus FORECASTED 100 %, by email.
- The existing account watchdog stays the account-wide backstop.

**This is alerting, not an invoice cap.** AWS Budgets doesn't stop charges, and no cap is claimed.

**Technical limits that bound spend**
- No GPU, NAT, ALB, provisioned concurrency or warming loops.
- Lambda reserved concurrency of 5 per 3D function.
- Request size limits: upload intent ≤ 200 MB per component, ≤ 10 components per version.
- S3 lifecycle rules from Q08.
- API Gateway stage throttling at 10 rps / burst 20 per API.

**Responsiveness.** No latency promises. Cold starts are recorded, not hidden (AUTOMATIC_REQUEST_DRIVEN_RELEASES.md).

**Rationale.** The account's observed spend was about $69 for 1–22 Sept with unrelated resources included. A separate small 3D budget makes 3D cost visible.

**Cost / risk.** About $0–5/month expected while idle (storage, logs). This is not measured. Risk: the cost-allocation tag may not be activated, in which case the tagged budget reads $0. The account watchdog still fires.

**Reverse by.** Change `monthly_usd` and the limits in config.

**Unblocks.** INF-01, INF-03, HSB-04, OSB-08, WFB-10 / P04, P08 (development budget). P52 later.

**Overturn if.**
- Measured dev usage approaches 80 % in a normal month.
- The owner sets a different ceiling.

### Q10 · Commercial viewing and portable delivery

**Options**
- (a) Invent plans/prices.
- (b) An explicit no-op commercial gate pending real pricing.
- (c) Free for all.

**Provisional answer: (b).** No plan names, prices, free tier or perpetual rights are created.

Every view, place and export path calls a `CommercialGate` port. Its first implementation is `NotConfiguredCommercialGate`:
- **View/place** returns `allowed_no_commercial_policy` for grant-authorised users in dev with synthetic or unoccupied content. The outcome is logged with its reason.
- **Portable export / paid download** returns `denied: export_not_available`.

Prospect, seller and developer exceptions: none. The gate can't be enabled in production. Production activation requires CORE-03 entitlements from Core, the existing owner of subscription records, and real pricing.

**Rationale.** The integration point exists and is testable without inventing commercial terms or duplicating Core ledgers.

**Cost / risk.** Zero. Risk: a dev "allowed" might be mistaken for an entitlement. The explicit outcome name prevents that.

**Reverse by.** Replace the gate implementation with a Core-entitlement adapter.

**Unblocks.** CORE-03 (interface only), HSB-06, OSB-06, HCB-08 / P25, P26, P27 (dev). P35 stays blocked.

**Overturn if.** The owner provides real pricing and entitlement rules.

### Q11 · External developer onboarding

**Options**
- (a) Public API keys.
- (b) Contracted organisations registered by an admin with scoped delegation.
- (c) Disabled for now.

**Provisional answer: (c) now, (b) as the target model.**
- External developer access is **DISABLED**. The SDK is consumed only by first-party WiseStay apps.
- Target model for P35, not built now:
  - an admin-registered organisation and application in User Management
  - explicit per-resource delegation, quotas, callback registration and revocation
  - a secretless browser SDK
  - no universal key (D10, AT20)

**Rationale.** No external party exists yet. Building onboarding now would be unverifiable.

**Cost / risk.** Zero. Risk: delays the developer reuse journey (R3), which is accepted.

**Reverse by.** Implement the target model and activate P35.

**Unblocks.** IDM-03 (first-party scope only), HSB-08, OSB-08, WFB-10 / none positive. P35/P37 remain blocked by an absent independent host.

**Overturn if.** A named contracted developer and host appear.

### Q12 · Notification and support ownership

**Options**
- (a) Each 3D backend sends its own email/push.
- (b) The owning domain produces events; delivery uses the existing Core `notify(user, template, reference)` → Worker `notifications` transport (SES/SNS/SMS, catalogue `contracts/notification-v1.json`).
- (c) In-app only.

**Provisional answer: (b) as the producer/transport split, with (c) as the only active channel in the first slice.**

**Producers**
- HCB: invitations, comments.
- HSB/OSB: upload, validation and publication job status.
- WFB: merchant review requests.

**First-slice channel.** In-app status only: apps poll their own backend. There is no outbound message, so there are no Worker or catalogue changes and P60 stays inactive.

**Support.** The existing admin web (ADM) gets read-only safe references later (P50). There is no new staff console.

**Rationale.** This reuses existing transports and avoids a third notification stack. In-app-only costs nothing now.

**Cost / risk.** Zero now. Risk: users miss invitations without email, which is acceptable for a synthetic dev slice.

**Reverse by.** Add catalogue templates and call Core's notify path, which activates P60.

**Unblocks.** HCB-07, ADM-01…03 (scope), WRK-01 (no-change finding) / P32, P50.

**Overturn if.** The pilot needs outbound invitations, which would mean activating P60.

### Q13 · Virtual routes versus live indoor navigation

**Options**
- (a) Virtual routes only.
- (b) Live positioning.
- (c) Both.

**Provisional answer: (a).**
- The route is drawn from a user-selected known start (for example the entrance) to the approved shelf location, on the approved map version.
- **Live positioning is DISABLED.** There is no moving-user marker and no sensor or positioning method is selected.
- Private or blocked areas are excluded.
- A map change invalidates routes (AT13/AT14).
- P57/P58 stay inactive.

**Rationale.** Virtual routes give value without localisation evidence. A live marker without qualification would be a false claim.

**Cost / risk.** Zero. Risk: lower perceived value, which is accepted.

**Reverse by.** Run P57 feasibility and use a separate live decision.

**Unblocks.** WFB-09, WFA-08, ARC-06 (route meaning only) / P44.

**Overturn if.** A measured localisation method qualifies on the reference shop.

### Q14 · Shop/property registration compatibility

**Options**
- (a) A new premises master in the Finder.
- (b) Reuse Resvanta REAL/VIRTUAL with no new type.
- (c) Add a Resvanta "premises use" type.

**Provisional answer: (b).**
- **Real shops** register as Resvanta `REAL` (address, ordinary operator review). Bookability comes only from accommodation listings and allocations. A shop with no listing is therefore not bookable. RSV-01 must verify this, not assume it.
- **Research and synthetic spaces** register as `VIRTUAL`. Null address; the code already forbids holds, bookings and blocks for VIRTUAL.
- **First slice.** Synthetic shops are VIRTUAL only, consistent with Q07.
- **Registration path.** The only machine registry write observed is `POST /v1/registry/iot-properties`, limited to IoT registry clients. Letting the Finder backend register shops needs a reviewed additive registry-client extension in Resvanta. That extension is **not** approved here. Until it is reviewed, real-shop registration stays blocked, and it is also blocked by the absence of a real merchant.

**Rationale.** This avoids a second editable property master, which the WBS prohibits, and reuses existing guards.

**Cost / risk.** Low. Risk: a REAL shop might surface in accommodation search. RSV-01 must test that.

**Reverse by.** Add option (c) if RSV-01 shows a false-bookability path.

**Unblocks.** RSV-01…03, WFB-01, RPA-01 (no-change finding) / P02, P07, P22 (synthetic). P59 stays inactive.

**Overturn if.** RSV-01 finds that REAL implies bookability or availability exposure anywhere.

### Q15 · Deployment and resource ownership

**Options**
- (a) A new AWS account or region.
- (b) The existing founder account and dev environment, following `wisestay-infrastructure` conventions.
- (c) Shared Aurora for 3D metadata.

**Provisional answer: (b).**

**Account and environment**
- Account `511831442607`, region `ap-southeast-1`, environment `dev`.
- Terraform state key: `wisestay/dev/{repository}/application.tfstate`, from the existing `state_key_template`. The 3D repos have no `wisestay-` prefix to strip.

**Compute, storage and metadata**
- Request-driven Lambda (Python) behind API Gateway REST, following the serverless-edge-dev pattern.
- One private S3 bucket per asset-producing backend: Block Public Access on, SSE-S3, versioning off. Immutable keys are content-addressed by SHA-256.
- Presigned PUT valid for 15 minutes and presigned GET for 5 minutes, both issued after an authorisation check. No CloudFront in dev, which means no signing-key custody.
- Metadata in per-service DynamoDB on-demand tables. This matches the existing Resvanta/Worker DynamoDB use and keeps ownership local. Shared Aurora (c) was rejected for now: it would put 3D schemas in the foundation-owned physical database.

**Identity.** Website-session path "W" (DELTA-14) through `user.wizestay.com`. Websites and APIs are registered in User Management `deployment/web_registration.py`. No per-app Cognito client.

**Websites.** Added to `applications/websites` `local.sites`, the observed current physical controller per the H-P04 clarification. The accountable owner is the app repository. The new sites must be excluded from `module "client"` the same way `resvanta` is, otherwise Cognito clients get created.

**Idle/resume.** Only storage and logs persist while idle. There are no claims about provider shutdown timing.

**Per-repository mapping**

| Repo (prefix) | `ownership.json` category / stacks | Resource owner of (dev) | Web origin / API origin |
|---|---|---|---|
| three-dimension-view-arcore (ARC) | **not added**: no AWS resources | None. SDK/WASM built in CI and consumed by pinned commit/tag | — |
| three-dimension-view-arcore-backend (HSB) | backend / `application` | Lambda + REST API + base-path mapping, regional ACM cert and own DNS record, bucket `wisestay-dev-home-scanner-assets-511831442607` (`staging/`, `versions/`), DynamoDB `wisestay-dev-home-scanner`, its runtime IAM role | API `https://home-scanner.dev.wizestay.com/api/v1` |
| three-dimension-object-backend (OSB) | backend / `application` | Same pattern; bucket `wisestay-dev-object-scanner-assets-511831442607`, DynamoDB `wisestay-dev-object-scanner`. Resolves H-P04 `OBJECT_SCANNER_OWNERSHIP_MISSING` provisionally | API `https://object-scanner.dev.wizestay.com/api/v1` |
| home-composer-backend (HCB) | backend / `application` | Lambda + API + DynamoDB `wisestay-dev-home-composer` (designs, revisions, grants, comments). No asset bucket: references only | API `https://composer.dev.wizestay.com/api/v1` |
| where-can-find-this-backend (WFB) | backend / `application` | Lambda + API + DynamoDB `wisestay-dev-finder`, bucket `wisestay-dev-finder-queries-511831442607` (`query/`, 24 h expiry) | API `https://finder.dev.wizestay.com/api/v1` |
| three-dimension-view (HSA) | web / `application` | Site content. Bucket `wisestay-web-home-scanner-511831442607` and its distribution sit in `applications/websites`. Native Capacitor builds are local/debug only | Web `https://home-scanner.wizestay.com` |
| three-dimension-object-app (OSA) | web / `application` | Site content, as above, `wisestay-web-object-scanner-…`. Resolves `OBJECT_SCANNER_WEBSITE_BINDING_MISSING` provisionally | Web `https://object-scanner.wizestay.com` |
| home-composer-app (HCA) | web / `application` | Site content, `wisestay-web-composer-…` | Web `https://composer.wizestay.com` |
| where-can-find-this-app (WFA) | web / `application` | Site content, `wisestay-web-finder-…` | Web `https://finder.wizestay.com` |

All 3D resources carry the tags `Project=WiseStay`, `CostAllocation=wisestay-dev-3d` and `Repository=<repo>`. Hostnames are provisional and cheap to change in dev.

**AWS inputs still required**

| Input | Discoverable from the infrastructure repo? |
|---|---|
| Account ID `511831442607` | **Yes**: `applications/websites/main.tf` (`allowed_account_ids`), `docs/SERVERLESS_COST_MODEL.md`, UM `web_registration.py` `TARGET` |
| Region `ap-southeast-1` (ACM for CloudFront in `us-east-1`) | **Yes**: same files |
| State bucket / KMS key, Route53 zone, Cognito pool | **Yes**: `applications/websites/main.tf` backend block and locals |
| Budget alert email addresses | **No**: `config.example.json` has placeholders, and the real config isn't in the repo |
| Per-repo GitHub OIDC deployment roles and plan/apply statements for the 8 deploying 3D repos | **No**: they must be added to foundation `deployment_repositories` (an INF change), and they don't exist yet |
| Whether the `CostAllocation` tag is activated in Billing | **No**: account state, not source |
| Usable AWS credentials for this agent | **Not verified**. Not read or tested in this step |

**Rationale.** This reuses the existing account, region, state, DNS and identity conventions. Everything idles to near zero.

**Cost / risk.** Low, within Q09. Risk: the shared website root couples 3D site changes to the infrastructure release lock.

**Reverse by.** Destroy the per-repo stacks. S3 data is synthetic in dev. Moving the sites to per-repo controllers is a later reconciliation (H-P04).

**Unblocks.** INF-01…03, IDM-01, all repository release tasks / P04, P08 (development inputs). P52 later.

**Overturn if.**
- DynamoDB access patterns can't serve design/finder queries (D03).
- The owner designates a different environment or account.

### Q16 · Application embedding and predecessor coverage

**Options**
- (a) Embed 3D features natively in unified mobile.
- (b) Unified mobile hands off to the 3D web apps; predecessor apps unchanged.
- (c) Add 3D features to the predecessor apps too.

**Provisional answer: (b).**
- Web-first remains.
- Owner and tenant websites (OWN/TEN) and unified `wisestay-mobile` link to the 3D apps by deep link with a return route. The handoff carries no tokens; the central SSO session applies.
- Native phone capture stays in the three-dimension-view Capacitor app.
- `wisestay-owner-mobile` and `wisestay-tenant-mobile` stay **unchanged**: no 3D features, and no users or data retired. P61/P62 stay inactive.

**Rationale.** No duplicate implementations, and it matches the recorded web-first preference.

**Cost / risk.** Low. Risk: handoff UX is weaker than embedding, which is accepted for the first slice.

**Reverse by.** Embed the reusable workspaces in unified mobile (P49) once web journeys pass.

**Unblocks.** MOB-01…03 (handoff), OWM-01, TNM-01 (no-change findings) / P06, P18. P49 later.

**Overturn if.** Usability testing shows the handoff breaks the journey, or the owner requires predecessor coverage.

---

## 2. What delegation cannot resolve

These need real-world inputs or third parties. They stay blocked whatever is decided above.

- **Physical captures.** Consented or permitted rooms, objects and a shop, measured independently. Needed for P05 real data, P10–P13, P28/P29, P40, P43, P46–P48 and P53, and to validate the Q03 thresholds.
- **A real merchant and shop.** A real catalogue and shelf authority (P38/P39), and real REAL-property shop registration (Q14).
- **An independent third-party developer host.** The genuinely separate consumer for P35/P37 and AT20.
- **App-store accounts.** Play/App Store signing and distribution for any native release.
- **AWS credentials, if absent.** Also the budget alert emails, OIDC deployment-role creation and cost-allocation tag activation (Q15 table).
- **Independent reviews.** Independent QA, security, privacy, legal and UX acceptance. Delegation lets the agent choose, but it can't make the agent its own independent reviewer.
- **Owner intent.** Whether any answer here matches what the owner would have chosen. Each entry stays revisable.

## 3. Machine-readable summary

```json
{
  "record_id": "WS-3D-DECISIONS-DELEGATED-2026-10-20",
  "delegated_by": "Majid Samadi",
  "delegated_on": "2026-10-20",
  "decided_by": "engineering agent (delegated)",
  "owner_answers_retained": ["Q06_RESULT_ORGANIZATION_HUMAN_20261015_073548", "Q07_FIRST_SLICE_CONTENT_HUMAN_20261014_210147"],
  "decisions": [
    {"id": "Q01", "status": "DELEGATED-PROVISIONAL", "answer": "Existing arcore engine as the single SDK (no new repo); producer-owned schemas vendored with SHA-256 sync tests; four Python Lambda/API Gateway REST backends", "unblocks": ["ARC-02", "HSB-01", "OSB-01", "HCB-01", "WFB-01", "INF-01", "P03", "P09", "P15"]},
    {"id": "Q02", "status": "DELEGATED-PROVISIONAL", "answer": "Local-only capture/reconstruction; cloud refinement DISABLED; explicit upload of processed representation only", "unblocks": ["ARC-03", "ARC-04", "ARC-05", "HSB-04", "OSB-03", "INF-01", "P11", "P12"]},
    {"id": "Q03", "status": "DELEGATED-PROVISIONAL", "answer": "Provisional thresholds frozen and hashed before scoring (room max(5cm,2%), object max(1cm,3%), coverage 90%, alignment 5cm RMS, shelf 95%, false exact-confirm <=1%); laser/tape reference; require real measured data", "unblocks": ["ARC-06", "ARC-10", "HCB-03", "HCB-04", "WFB-11", "P05", "P13"]},
    {"id": "Q04", "status": "DELEGATED-PROVISIONAL", "answer": "WebGPU primary on Chrome desktop/Android; labelled WebGL2 compatibility path never counted as WebGPU; Android ARCore-depth first capture profile; all else unqualified", "unblocks": ["ARC-08", "HSA-08", "OSA-08", "MOB-03", "P09", "P14"]},
    {"id": "Q05", "status": "DELEGATED-PROVISIONAL", "answer": "glTF 2.0/GLB components + versioned wisestay.asset-envelope.v1 JSON (digests, frame, scale class); no new crypto; private S3 + presigned access; TDVDEV01 dev-only", "unblocks": ["ARC-07", "HSB-03", "HSB-06", "OSB-06", "HCB-08", "P03", "P15", "P26", "P27"]},
    {"id": "Q06", "status": "DELEGATED-PROVISIONAL", "answer": "Owner ALT1 kept; unknown is a processing/evidence status not a match class; exact-confirmed needs merchant variant link; merchant-authoritative quantities; shortage/recount automation DISABLED", "unblocks": ["HCB-04", "WFB-02", "WFB-05", "WFB-07", "WFB-08", "P23", "P31"]},
    {"id": "Q07", "status": "DELEGATED-PROVISIONAL", "answer": "Owner first-slice content kept; explicit per-resource grant matrix; occupied-home publication DISABLED; no IoT-role inheritance", "unblocks": ["HSB-05", "OSB-05", "HCB-06", "CORE-02", "P02", "P25", "P32"]},
    {"id": "Q08", "status": "DELEGATED-PROVISIONAL", "answer": "Raw stays on device; staging 7d; rejected 30d; withdrawn assets blocked immediately, bytes deleted after 30d with tombstones; query photos 24h; logs 14d; no training", "unblocks": ["HSB-08", "OSB-07", "WFB-10", "IDM-02", "P15", "P25"]},
    {"id": "Q09", "status": "DELEGATED-PROVISIONAL", "answer": "USD 25/month tagged 3D dev budget with 50/80/100% actual and 100% forecast email alerts (not a cap); request-driven only; reserved concurrency 5; API throttles", "unblocks": ["INF-01", "INF-03", "HSB-04", "OSB-08", "WFB-10", "P04", "P08"]},
    {"id": "Q10", "status": "DELEGATED-PROVISIONAL", "answer": "No prices or plans; CommercialGate no-op (view allowed_no_commercial_policy in dev, export denied); production requires Core entitlements and real pricing", "unblocks": ["CORE-03", "HSB-06", "OSB-06", "HCB-08", "P25", "P26", "P27"]},
    {"id": "Q11", "status": "DELEGATED-PROVISIONAL", "answer": "External developer access DISABLED; first-party SDK use only; target model = admin-registered org/app with scoped delegation", "unblocks": ["IDM-03"]},
    {"id": "Q12", "status": "DELEGATED-PROVISIONAL", "answer": "Owning domain backend produces events; existing Core notify -> Worker transport for later; first slice in-app status only, no Worker change", "unblocks": ["HCB-07", "ADM-01", "ADM-02", "ADM-03", "WRK-01", "P32", "P50"]},
    {"id": "Q13", "status": "DELEGATED-PROVISIONAL", "answer": "Virtual routes from a selected known start only; live positioning DISABLED", "unblocks": ["WFB-09", "WFA-08", "ARC-06", "P44"]},
    {"id": "Q14", "status": "DELEGATED-PROVISIONAL", "answer": "Reuse Resvanta REAL (real shops, unlisted = not bookable, to be verified) and VIRTUAL (research/synthetic); first slice VIRTUAL only; Finder registry-client extension needs review", "unblocks": ["RSV-01", "RSV-02", "RSV-03", "WFB-01", "RPA-01", "P02", "P07", "P22"]},
    {"id": "Q15", "status": "DELEGATED-PROVISIONAL", "answer": "Account 511831442607 / ap-southeast-1 / dev; per-repo application stacks for 4 backends (Lambda, REST API, private S3, DynamoDB on-demand) and 4 sites in applications/websites; ARC owns no AWS resources; W session path via user.wizestay.com", "unblocks": ["INF-01", "INF-02", "INF-03", "IDM-01", "P04", "P08"]},
    {"id": "Q16", "status": "DELEGATED-PROVISIONAL", "answer": "Web-first; unified mobile and owner/tenant web hand off by deep link; native capture stays in three-dimension-view; predecessor owner/tenant mobile unchanged", "unblocks": ["MOB-01", "MOB-02", "MOB-03", "OWM-01", "TNM-01", "P06", "P18"]}
  ]
}
```
