# Home Scanner Service — backend requirements

**Document:** HSB-SRS-001 · **Version:** 1.0 · **Date:** 14 October 2026  
**Repository:** majidsamadi/three-dimension-view-arcore-backend  
**Status:** requirements only. This repository was uninitialized before this documentation delivery; no scanning service, database, AWS deployment or cloud-accuracy result is claimed.

Read the common [platform requirements](PLATFORM_REQUIREMENTS.md), [data/API contracts](CONTRACTS.md), and [decisions and acceptance](DECISIONS_AND_ACCEPTANCE.md). C = owner-confirmed; E = engineering proposal; C+E = confirmed goal with proposed controls. F/P/X indicate foundation/pilot/expansion. All shared 3DP requirements apply where relevant.

## 1. Purpose and boundary

Provide the service behind a reusable Home Scanner: register authorized scan sessions, accept private capture/scene uploads, maintain immutable home/shop scene revisions, optionally orchestrate approved reconstruction/refinement jobs, and deliver approved scenes to permitted consumers. The owner's phone need not be online when a tenant views a published home.

This service owns media and scan lifecycle, not property identity, user profiles, bookings, tenancy/IoT authority, reusable object-library assets, Composer placements, product inventory or payment settlement. Every physical home/shop uses its canonical Resvanta property reference. A virtual research scene must preserve its declared type and cannot become a real accommodation listing. Human identity and first-party SSO come from the existing Account Centre.

## 2. Actors and permissions

Owner/uploader may create a capture only for an authorized target; capture, review, publish and withdraw are distinct permissions. A collaborator may review without being allowed to publish. A prospective tenant may view the approved listing projection with the applicable subscription/audience entitlement without already renting it. A current tenant may have private design/media rights but receives no blanket export permission. Registered developers and processing workers use scoped application/service identities, not impersonated people. Support can inspect redacted operations; it cannot issue arbitrary content keys or publish a customer's house.

Rented-home privacy and publication consent remain D11. Legal ownership is not automatic permission to expose occupants' belongings. Media/design rights never grant physical lock or IoT control.

## 3. End-to-end service workflows

### HSJ-01 Local capture to publication

1. The app authenticates centrally, resolves a property through Resvanta and requests a scoped capture session.
2. The phone captures locally with a declared scale/calibration profile; a local preview can remain usable even without upload.
3. After explicit consent, the backend creates an upload intent for exact expected components; the phone uploads directly to private S3 staging.
4. The backend verifies exact S3 versions, checksums, size and schema, and checks private versus publishable content. Validation failure remains private and recoverable.
5. An approved local result can enter review without a cloud job. Optional refinement requires a separately authorized profile and budget.
6. The owner/reviewer examines quality and privacy, then publishes an immutable revision. The service atomically moves the current publication pointer only after the complete accepted manifest is available.

### HSJ-02 Multi-tenant delivery

A consumer requests a specific scene or current published revision. The service checks current identity, listing/media visibility and viewing entitlement, returns a bounded authorized manifest/grant, and permits private CloudFront delivery plus separate key access. Each viewer independently fetches/render assets; the owner phone is not involved. No direct access to raw frames, diagnostics or source keys is included.

### HSJ-03 Optional refinement and rollback

Freeze input versions/digests, approved algorithm/container/model configuration and budget. Submit one idempotent asynchronous job, report actual progress, handle cancellation and uncertain provider outcomes, validate outputs and retain the source result. A refined result becomes a new review candidate. Rejection or rollback changes the publication pointer under version control; it never overwrites the original or restores expired access.

### HSJ-04 SDK/developer use

An approved client registers its application through the approved identity/delegation flow, requests only its authorized resources and receives the same versioned scan APIs as our app. The backend enforces per-organization quotas and current permissions regardless of the SDK's UI. Onboarding does not create a competing login system.

## 4. Functional requirements

| ID | Basis / stage | Requirement | Acceptance |
|---|---|---|---|
| HSB-001 | C / F | Expose a versioned service independent of the Home Scanner UI. | Our app and an approved minimal host complete equivalent scoped API journeys. |
| HSB-002 | C / F | Validate canonical user identity through the released Account Centre adapter and resolve property identity only from Resvanta. | Missing/revoked sessions and foreign or fabricated properties fail without local fallback. |
| HSB-003 | E / F | Separate capture, input-read, scene-view, review, publish, withdraw and portable-export scopes. | A reviewer cannot publish; a tenant-view grant cannot read raw images or acquire export authority. |
| HSB-004 | C+E / F | Register capture/session metadata and device/engine/calibration provenance with stable operation IDs. | Duplicate create requests resolve one session; changed content under the same idempotency key conflicts. |
| HSB-005 | C+E / P | Accept furnished and unfurnished scan results without claiming automatic furniture removal. | Manifest identifies structural, embedded-furniture, separable and unknown regions; inseparable scans expose limitations to Composer. |
| HSB-006 | E / F | Validate input manifest, allowed types, quotas, total size, codec compatibility and ownership before allocating upload scope. | Oversized/foreign/executable/external-reference submissions are refused without broad S3 permissions. |
| HSB-007 | E / F | Support direct private S3 uploads with bounded multipart status/resume/abort. | Network interruption resumes existing parts; credentials and URLs are redacted; no published key is writable by clients. |
| HSB-008 | E / F | Finalize only the exact accepted object versions/digests and complete component set. | A late staging overwrite, false ETag, missing texture or repeated complete cannot change the validated accepted artifact. |
| HSB-009 | E / F | Validate archives, geometry, numeric values, bounds, textures and compression under resource limits. | Traversal, NaN/Inf, bad triangle indices, unsupported compression and parser exhaustion fail in isolation. |
| HSB-010 | C+E / P | Accept local scene results without forcing cloud reconstruction. | The end-to-end local-output publication journey completes with cloud jobs disabled. |
| HSB-011 | E / X | Gate cloud refinement on explicit mode/consent, sufficient capture inputs, approved pipeline and cost admission. | No consent, unresolved D05/D06 or insufficient frames produces a typed refusal, not an automatic upload or job. |
| HSB-012 | E / X | Run long reconstruction asynchronously with immutable inputs and job-specific IAM scope. | Request API returns an operation; workers cannot read another capture or publish output directly. |
| HSB-013 | E / X | Reconcile uncertain submission, retries, duplicate events and interruptions durably. | Lost provider response does not create a second intended GPU job; retries have bounded attempts and retained checkpoint lineage. |
| HSB-014 | E / X | Distinguish cancel_requested, actual cancelled, failed, timed_out and output-ready states. | Cancellation race cannot mark a running job stopped or publish a late output; cost/status remain attributable. |
| HSB-015 | C+E / P | Store quality and scale status independently from processing success. | A completed but inaccurate job is review_ready/quality-limited, not survey-verified; metres remain unknown until supported. |
| HSB-016 | E / P | Require held-out real measurements for a qualified metric/floor-plan profile. | Report dimension and surface/coverage results separately from visual fidelity; a top-down picture alone fails floor-plan acceptance. |
| HSB-017 | C+E / P | Maintain immutable scenes/revisions with coherent structural graphs and representation capabilities. | Mesh/point/splat support is declared; collision/fit/navigation are unavailable when unsupported. |
| HSB-018 | C+E / P | Keep raw captures, debug ZIPs, private details and publishable derivatives separate. | Distributed scene inspection confirms private regions/data are removed from bytes, not merely hidden in UI. |
| HSB-019 | E / F | Publish only complete reviewed revisions and update the current pointer with optimistic concurrency. | Concurrent publication yields one winner/conflict; existing viewer pins remain coherent. |
| HSB-020 | C+E / P | Issue per-scene/revision/audience view grants after current entitlement checks. | Two eligible devices view without the owner phone; unrelated accounts and expired shares are denied. |
| HSB-021 | E / F | Deliver private assets through scoped CDN authority and distinct protected-key access. | Direct origin reads fail; expired/foreign grants cannot obtain decryption keys; no key or bearer is cached publicly. |
| HSB-022 | C+E / P | Allow Composer and discovery to reference published scene revisions without transferring source ownership. | Design creation and shop-route viewing neither mutate the home nor copy authoritative assets into another service. |
| HSB-023 | E / X | Version map-coordinate corrections and provide explicit migration metadata. | Dependent placements/shelves/routes are revalidated; old coordinates never silently attach to a changed room. |
| HSB-024 | E / F | Withdraw/revoke new access and expose remaining issued-grant lifetime. | No renewal after withdrawal; offline/CDN residual access is bounded and documented, not falsely instant. |
| HSB-025 | E / F | Implement reference-aware deletion, retention, legal hold and backup recovery. | All relevant object versions are tracked; deleted scene references become tombstones; restoration cannot revive withdrawn permissions. |
| HSB-026 | E / F | Provide cursor-paginated scoped libraries and redacted operation diagnostics. | Pagination cannot disclose private existence/counts; logs contain no raw household imagery, keys or signed URLs. |
| HSB-027 | C+E / F | Integrate subscription and portable-download authority without implementing another payment ledger. | Test paid flags or upload success cannot issue commercial rights; download recovery preserves the original entitlement. |
| HSB-028 | E / F | Publish transactional outbox events with immutable aggregate versions. | Replays are idempotent and older events cannot republish a withdrawn scene. |
| HSB-029 | C+E / F | Meter storage, transfer and processing per customer; enforce admission/concurrency quotas. | Over-quota work is rejected predictably; cost alerts alone are not treated as a hard limit. |
| HSB-030 | C+E / F | Deliver request-driven Python infrastructure with Terraform, SOLID boundaries and main-merge GitHub deployment. | Exact artifact/account/state/rollback checks; no warm API or custom property/identity master; docs commit creates no AWS resources. |

## 5. API, schema and state requirements

Use the Home Scanner endpoint family and common error/idempotency contracts in [CONTRACTS.md](CONTRACTS.md). Required API groups: capture admission/status, transfer/resume/finalize, processing request/status/cancel, scene/version metadata, publication/withdrawal, view/key grants, deletion and developer usage. All mutations require permission and current expected version; publication and expensive jobs require separate admission from file upload. Webhooks, if introduced, require registered destinations, signing, retry/deduplication and SSRF-safe configuration, not payload-selected arbitrary URLs.

Metadata records: CaptureSession, UploadIntent, SceneRevision, Publication, ProcessingJob, QualityReport, ConsentReceipt, AccessGrant, RetentionTask, OutboxEvent and UsageRecord. Property and user IDs are foreign service references; labels may be cached non-authoritatively with freshness, never independently edited. Metadata database selection is D03. Published manifest, component digests, source lineage and policy version must survive restart/restore. A stage can be failed without deleting its captured evidence.

## 6. Proposed AWS architecture and safeguards

API Gateway -> Python Lambda -> metadata adapter. Authorized direct uploads -> private S3 staging -> validation/queue -> reviewed accepted scene. Optional Step Functions/job adapter -> GPU-capable AWS Batch or another explicitly approved compute path. CloudFront -> private published objects with Origin Access Control and separate entitlement/key service. KMS, CloudWatch and durable event processing remain least-privilege adapters. These are proposed services, not deployed infrastructure or approved reconstruction algorithms.

Terraform must define ownership/import contracts, encryption, no public S3 access, minimal CORS, version/lifecycle rules, queue/DLQ, log retention, alarms, OIDC repository/environment restrictions and account/region guards. Do not duplicate existing Cognito/User Management or shared DNS ownership. No API-key-only protection for human content. No model/customer input in build logs or public CI artifacts.

Preserve the 300-second idle/resume objective for configurable resources; no provisioned Lambda concurrency or keep-warm polling. Provider-controlled Lambda lifecycle and GPU shutdown timing must be disclosed rather than claimed exact. CPU APIs and GPU jobs have different capacity/timeout needs. D06 approval is required for any GPU exception. A job request wakes/adopts capacity asynchronously, with visible queue delay; it cannot promise immediate full-house reconstruction.

## 7. Verification, operations and completion

Implement AT01–05, AT07–08, AT13 and AT16–22 as applicable. Required negative fixtures include tampered manifests, legacy relative units, cross-property upload, revoked publish authority, concurrent version change, replayed S3 upload, uncertain job submission, revoked share after CDN grant, mismatched decryption key, orphaned component, incomplete map correction and recovery from a failed publication transaction.

Operational runbooks must cover upload reconciliation, parser quarantine, provider outage, GPU interruption, budget exhaustion, key rotation, withdrawal, retention/deletion, restore and rollback. Capture content remains recoverable under the approved policy; operations cannot fix a failure with a force-success flag. Support access is purpose-scoped and audited.

Completion requires source/schema/unit/integration/security evidence, real S3/CDN/identity qualification, real-phone/cross-device results and independent measured-room quality for any metric claim. An AWS job finishing, a CI build, stored debug report or a visible point cloud is insufficient. No implementation or deployment is part of this requirements publication.
