# WiseStay Team B — P03 reconciled agreement draft v0.3

**Record:** WS-B-P03-C03-REVIEW-0.1. **Status:** draft, not frozen.

This document carries DELTA-01–16 unchanged from the prior v0.2 addendum and adds DELTA-17–21 from C-HANDOVER-03. Original v0.1 case bodies and v0.2 agreement bytes remain under inputs/. Historical no-receipt statements are not current: C has now supplied the limited semantic subset receipts identified below; none grants whole-case implementation acceptance.

## Scoped receipt incorporation

C accepted-for-contract-review the original B-RFX-03 foreign-revision/map examples, all four original B-RFX-04 examples with explicit owner/stage/scope, all six original B-RFX-06 negative boundaries, and DELTA-02’s distinct lifecycle/authority meanings. C requested a correction to B-RFX-03 missing-component wording. Revised example[0]/new example[3] in B-RFX-03 revision 0.2 now distinguish incomplete delivered V1 and candidate V2; C’s review of the revised bodies is pending. DELTA-01, WG02-02/03/06/07 ordering and entered-store settlement remain decision-needed.

C did not accept complete original B-P03-03/04/05/06/12/13/14/17 or the missing individual D/E artifacts. This packet supplies exact B originals for a narrow review, not a replacement receipt. HCTX and byte-projection runtime evidence remain outside C’s reviewed scope.

## Source boundary

Shared implementation anchor: `majidsamadi/three-dimension-view-arcore@91af17dc230e9aa34d424cac6b2956259937e5ac`, `sdk/src/web-runtime.ts`, `scene.ts`, `types.ts`, `security.ts` and the prior exact source register. This is contract documentation, not a repository patch. Home/Object C commits in the supplied register are documentation-only according to C’s review; no AWS absence is inferred.

## Effective proposed wording

### DELTA-01 — Lifecycle ordering

A state event reports a transition request/state, not by itself completed cleanup. Define the completion boundary for every successful pause, duplicate pause, resume, stop and cancel call. Specify whether conflicting calls serialize or reject and whether a pending frame drains/commits or is discarded with explicit engine-state consequences. The WG02 traces characterize the old runtime; neither alternative is selected.

WBS: ARC-02.1. Decisions: Q01. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-02 — Durability and operation identity

Keep local capture finalization, protected checkpoint persistence, native-to-app transfer, selected service upload, validation, review and publication distinct. Record the original operation/resource/version and whether each effect is pending, durably accepted or uncertain. Cancellation neither proves rollback/deletion nor cancels a different remote operation. A store.put already entered may finish after stop/cancel; define how its scoped receipt is settled/reconciled. Never fabricate a new operation to hide lost acknowledgement.

WBS: ARC-02.1, ARC-07.2. Decisions: Q01, Q05. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-03 — Context changes

Bind pending callbacks and receipts to the original account/application/organization/resource and application property/workspace/shop context. On a context change, old geometry, labels and callbacks cannot be applied to the new context. A legitimate old-context durable receipt remains distinct from permission to display its contents. Require reviewed immutable-scope and host-generation behavior; do not mutate an in-flight RuntimeOptions object to implement SSO or a property switch.

WBS: ARC-02.1, ARC-08.1. Decisions: Q01. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-04 — Authority and canonical association

Local project names and engine correlation IDs are not canonical people/properties/assets. Define the reviewed mapping for locally unbound capture without silently requiring online admission; canonical association is deliberate and revalidated at the relevant service boundary. Independent personal objects do not require a property. Non-bookable shops and addressless non-IoT research authoring remain unqualified until the applicable registry decision; do not invent booking/IoT authority or a second master.

WBS: ARC-02.2, ARC-07.2. Decisions: Q01, Q06, P02/Q14. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-05 — Scale and frame evidence

Preserve home and object scale independently. A known-size object does not make an unknown-scale home metric, and vice versa. Keep unknown/estimated/seller-declared/reference-supported/independently verified claims distinguishable without finalizing their serialization. Carry units, orientation, reference points, per-source frame/timebase and transform provenance. Synthetic dimensions and a 'Metres / Y up' label are not physical evidence; select unknown-scale trial/refusal behavior separately.

WBS: ARC-06.1, ARC-02.2, ARC-07.1, ARC-07.2. Decisions: Q03, Q05, Q06. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-06 — Pinned references and correction

Pin scene/object/design/map versions and occurrence identity. Keep independent placement transforms/removal without modifying source assets or stock. A map correction or explicit upgrade requires a versioned relationship and revalidation of design/shelf/comment anchors; ambiguous or absent alignment stays unresolved. Do not infer common origins, synchronization or retained tracking from independently captured or reopened geometry.

WBS: ARC-06.1, ARC-07.2, ARC-08.1. Decisions: Q03, Q05, Q06. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-07 — Component and audience bytes

Validate the declared exact version and required component set without changing an already accepted V1. Distinguish incomplete real capture coverage from missing required files. Publication/review concerns the exact approved audience projection bytes; local crop visibility is not byte-level privacy, and no private raw/home/seller material may leak via delivery or backup. Degraded projections need explicit reviewed membership/capability rules.

WBS: ARC-07.1, ARC-07.2, ARC-08.1. Decisions: Q05, P02/Q07. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-08 — Separate reader/authority profiles

Track native research diagnostics, experimental SDK protected checkpoints, existing Vue archives/imports, and future controlled service assets as distinct profiles. Preserve original readers/signing/keys and data. Two separately atomic native mesh/JSON writes are not a pair transaction. New restricted assets cannot use unrestricted legacy export/backup/debug paths; PNG policy is a separate reviewed question. Missing keys/pair members fail recoverably without deletion or universal substitute keys.

WBS: ARC-07.2, ARC-08.1. Decisions: Q05. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-09 — Observation and stock meanings

Separate product family, exact variant, pack/unit, reusable asset, observation, physical-instance hypothesis and design occurrence. Preserve observed/inferred/unseen and fused/separable distinctions. Record observation interval, coverage, quantity basis, association/dedup uncertainty and current reviewed availability separately. Withdrawing an asset or missing/stale/unvisited/partial/unavailable evidence does not prove product absence, zero stock, shortage or theft.

WBS: ARC-02.2, ARC-07.1, ARC-08.1. Decisions: Q06. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-10 — Match vocabulary correction

Retain WFB-05.1/WFA-03.1 exact-confirmed, probable, similar, ambiguous and no-match meanings. Preserve the relayed 'unknown' requirement without silently aliasing it to ambiguous, no-match or provider failure. Request F's examples distinguishing no candidate, multiple unresolved candidates, unknown identity and unavailable provider; decide whether unknown is an additional outcome or a separate identity/evidence dimension. No final enum is selected.

WBS: ARC-02.2, ARC-08.1. Decisions: Q06. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-11 — Current rights and restoration

Keep capture, review, publication, view, placement and export authority separate; an SDK identifier/client paid flag is not an issuer. Old T1 metadata restored after T2 withdrawal must not revive current access. Retained commercial rules, an explicitly authorized bounded pilot and deferral of positive commercial actions remain decision options; do not infer free/perpetual use. Negative validation/denial examples can proceed independently.

WBS: ARC-07.2, ARC-08.1. Decisions: Q05, P02/Q07, P15/Q10. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-12 — Two-account proof boundary

The later same-version two-account test requires the capturing phone to be offline while the authorized second account opens the exact accepted asset. That does not require the second viewer to be offline. An offline second viewer needs its own explicit capability/rights/recovery decision and evidence; no offline duration is inferred.

WBS: ARC-07.2, ARC-08.1. Decisions: Q04, Q05. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-13 — Viewer behavior and honest failure

Bind viewing/selection/focus to the exact authorized asset/occurrence/shop/map/target. Display declared selection precision and uncertainty with authorized text alternatives. Device loss, unsupported rendering, provider failure and missing alignment are distinct; do not gain alternate access, choose an unapproved renderer fallback or fabricate an exact marker/physical position/clearance result.

WBS: ARC-08.1, ARC-07.1. Decisions: Q04, Q05, Q06. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-14 — Current first-party entry

Consume the existing wisestay.sso-session.v1 boundary once its exact source/configuration is supplied. Website-session extension W and confidential-consumer integration C remain alternatives, not a new OIDC/JWT issuer. Four application identifiers/origins/callbacks/environments are unset. Preserve existing registrations; review the reported catalogue-count and proxy-size gaps without treating them as observed failures or as a bulk-asset design.

WBS: ARC-02.1, ARC-07.2. Decisions: Q01, P07/Q11. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-15 — Deliberate local evidence

Preserve deliberate local capture and explicitly selected upload. Optional raw-input/cloud processing consent cannot become a mandatory local-capture dependency. Diagnostic image sampling, even the relayed up-to-60 set, does not establish a synchronized equal-input replay or physical accuracy. No optional mode is activated.

WBS: ARC-02.1, ARC-02.2, ARC-06.1. Decisions: Q01, Q03, Q04. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-16 — Separate later developer proof

Review only minimal first-party prerequisites before P07. Keep full external organization/delegation/onboarding and independent-host proof separate for P35/P37. This reconciliation and its isolated fixtures do not satisfy ARC-02.4 or ARC-02's two-distinct-consumer completion criterion.

WBS: ARC-02.1, ARC-02.2, ARC-07.2. Decisions: P07/Q11, P35/Q11. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-17 — Complete accepted V1, incomplete candidate V2, and incomplete delivered V1

Keep three explicitly different semantic states. Accepted source V1 has its complete required coherent component set. Candidate V2 missing a required V2 component is incomplete and cannot replace or modify accepted V1. A delivered copy claiming V1 but missing a required V1 component cannot open as that asset; the accepted source V1 is not thereby relabelled incomplete or granted new rights. Never fill V1 with V2 geometry/appearance, mix required component revisions, or rename version labels to pass. Matching source history and E/F reference versions remain unchanged. Any separate reduced-capability projection needs its own reviewed membership/capability and audience meaning.

WBS: ARC-07.1, ARC-07.2, ARC-08.1. Decisions: Q05. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-18 — Original owner/stage/scope reconciliation without selecting settlement policy

Carry explicit original owner, stage and scope across local session/epoch, local checkpoint, native-to-app transfer, backend capture, selected transfer/recovery, immutable asset version, review/publication and current grant. Status evolution is not an asset-version change. Reconcile a lost acknowledgement using its original effect and current authorization; do not create a new asset/Object ID or retry E’s design save as C’s upload. Changed component set, target, selected raw-input consent or expected version under the same repeated operation is conflict rather than duplicate-success. Local stop/cancel, remote cancel request, confirmed remote termination, accepted input and publication are distinct. Preserve whichever durable facts are confirmed and original-scope late receipts; unknown remote acceptance remains unknown. This wording does not select command serialization/rejection, drain/discard/delete, finish mapping or entered-store promise settlement.

WBS: ARC-02.1, ARC-02.2, ARC-07.2. Decisions: Q01, Q05. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-19 — Publication revision and historical receipt are not current use authority

Validation produces no publication. Review binds the exact candidate and audience; publication has its own confirmed revision and original operation under applicable current checks. Asset, publication and design revisions are different. A later H-A@8 publication does not update an E arrangement pinned to H-A@7/O-A@3, its placements/comments, or F’s map/shelf anchors. Lost publication acknowledgement is reconciled against the original publication operation; its historical receipt is not a new/current view, place, export or key-release grant. Object publication, listing association and composition publication retain their separate owning boundaries.

WBS: ARC-07.2, ARC-08.1. Decisions: Q05, Q06, P02/Q07, P15/Q10. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-20 — Current T2 authority versus restored T1 history

Restoring a T1 publication/grant record after T2 withdrawal preserves permitted historical facts but cannot create a new open, renewal or key release. Current authority governs; unavailable current authority yields an explicit unavailable/reconciliation outcome rather than restored allow. Historical asset/reference preservation is subject to the still-unselected policy and never implies perpetual retention. E retains only permitted restricted history; F cannot infer zero stock or product absence from withdrawal. Do not promise instant erasure or revocation of every previously issued offline/delivery capability. Residual bounds and custody remain undecided.

WBS: ARC-07.2, ARC-08.1. Decisions: Q05, Q08, P15/Q10. Status: `PROPOSED_NOT_FROZEN`.

### DELTA-21 — Required meanings survive validation and explicit reader mapping

Validation is not verification of unknown scale, seller dimensions, inferred surfaces, ambiguous variants or map/association evidence. Keep home/object/observation/occurrence identities distinct; preserve observation interval, coverage and count basis without interpreting two views as two units or an unvisited region as zero. Retain exact-confirmed/probable/similar/ambiguous/no-match meanings while F’s mapping of unknown remains unresolved; provider/source failure is not a no-match. The experimental validateScene key set and provenance.qualified=false do not define the complete service package. An unsupported required meaning requires explicit reviewed mapping or refusal, not stripping/coercion merely to satisfy the old reader. Audience projection separately excludes private bytes according to its reviewed scope without inventing missing required semantic evidence.

WBS: ARC-02.2, ARC-07.1, ARC-07.2, ARC-08.1. Decisions: Q03, Q05, Q06. Status: `PROPOSED_NOT_FROZEN`.

## Decision-dependent fields and fixtures that may proceed

Q01: request versus completion and competing-command/duplicate outcomes; live continuation and original-scope entered-store settlement. Q03/Q04: evidence/support profiles, not synthesized physical correctness. Q05: coherent component membership, exact reader/projection/integrity/custody/recovery behavior. Q06: distinct variant/occurrence/observation/map meanings and F’s unresolved unknown mapping. Applicable Q07/Q08/Q10: audience/consent, purpose-specific lifecycle/residual bounds and action-positive entitlement interpretation; no new predecessor or policy is selected.

Independent descriptive preparation can proceed for complete V1/incomplete candidate V2/incomplete delivered V1, foreign/mixed versions, original-operation replay/conflict/late receipt, T1/T2 restore denial, and required-meaning mapping/refusal. Positive use rows remain conditional on actual authority decisions. These are not executable service/renderer implementations.

## Schedule and completion

P03: B-led relative W2, logical P01/P02, no fixed-slot predecessor, A01; B01 B02; C02; G01. Applicable gates Q01/Q03/Q04/Q05/Q06 remain open unless a separate receipt supplies them. P15: C01/C02 relative W3–W4, P03 logical/P04 fixed-slot. Staged Q10 precedes affected positive actions; minimal first-party Q11 is not external onboarding approval. No changes to crews, specialists, optional P55–P64 or the ARC-02 two-consumer criterion.
