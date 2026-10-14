# Shared 3D platform requirements

**Document:** TDV-PLATFORM-SRS-001 · **Version:** 1.0 · **Date:** 14 October 2026  
**Owner:** Majid Samadi · **Status:** requirements baseline; not implementation, physical qualification or deployment evidence.

This is the common specification for the nine repositories below. Repository-specific requirements add responsibilities; they do not create competing user, property, asset or inventory masters. Companion documents: [contracts](CONTRACTS.md), [decisions and acceptance](DECISIONS_AND_ACCEPTANCE.md), [Home Scanner backend](REQUIREMENTS.md).

## 1. Authority and interpretation

C = explicit owner-confirmed requirement. E = proposed engineering requirement, requiring review before implementation or live activation where a decision remains open. C+E combines confirmed intent with the stated engineering safeguards. F = shared foundation; P = first integrated pilot; X = expansion. SHALL describes a target, never a claim that the repository already implements it.

The owner requested reusable Home Scanner and 3D Object Scanner services, separately usable apps, S3-backed assets, Home Composer, product discovery through Where Can Find This, and WebGPU as the current visualization target. Earlier proprietary scenes, paid portable downloads, subscription-controlled viewing, Vue/Suha interfaces, Python backends, Terraform, SOLID and GitHub delivery rules remain unless explicitly amended. The 25 September room-research priority pauses furniture detection/recognition in new Android research captures; it does not delete future object and retail requirements. Cloud reconstruction was discussed as an option, not approved as a mandatory replacement for local capture.

## 2. Product and repository map

| Repository under majidsamadi | Responsibility | Must not own |
|---|---|---|
| three-dimension-view | Existing Vue/Suha Home Scanner consumer; guided capture, review, library, publication and viewing | A second reconstruction engine or property master |
| three-dimension-view-arcore | Independent C++ engine, platform adapters, framework-independent SDK and scanning research | Google ARCore dependency, user passwords, stock ledger |
| three-dimension-view-arcore-backend | Home scan sessions, scene revisions, reconstruction orchestration, home-scene publication and access | Editable property records, object-library master, design placements |
| three-dimension-object-app | Standalone individual-object capture app using the reusable scanner SDK/service | Its own exclusive scanner or authoritative product inventory |
| three-dimension-object-backend | Reusable Object IDs, object revisions, rights, processing and authorized asset delivery | Merchant stock quantities or home placements |
| home-composer-app | WebGPU-first visual composition, alternatives, measurements and collaboration UX | Rebuilding assets for every placement |
| home-composer-backend | Design IDs, pinned asset references, placements, comments, sharing and revisions | Duplicate home/object binaries or new property/user masters |
| where-can-find-this-app | Shopper identification/search and merchant observation/location workflows | Unverified exact-stock or indoor-position claims |
| where-can-find-this-backend | Merchant catalog links, product matches, observations, availability projections, locations and route data | Core scanner algorithms, finances, canonical property/profile data |

Shared infrastructure components may be reused through versioned libraries and Terraform modules. Reuse does not mean two Terraform states own the same bucket, identity pool or signing key. A new shared-runtime repository is not required by this baseline. Physical scans of shops and homes reference canonical Resvanta properties; shop business records and internal aisle/shelf graphs belong to discovery, not another address database.

## 3. Confirmed user journeys

**UJ-01 Home publication.** An authorized owner scans a furnished or unfurnished home on a phone, reviews the result, deliberately uploads and publishes an approved version. Eligible prospective tenants later view that version without the owner's phone being online. An existing tenancy is not required merely to view a published listing.

**UJ-02 Independent object capture.** A person scans a table or another object and receives a reusable Object ID. The asset can be used in multiple authorized applications. Capturing structure and objects may be separate parallel workflows; synchronized multi-camera capture is not assumed.

**UJ-03 In-store try-before-buy.** With permission to capture the product, an owner scans it in a store and places it at verified physical size in a previously saved home. Approximate dimensions and incomplete geometry remain visible.

**UJ-04 Owner–tenant design review.** Sharing an Object ID means try this asset. Sharing a Design ID means review this asset in this location in this home. Participants discuss, propose alternatives and save versions without silently changing the owner's source scan or the published listing.

**UJ-05 Seller-published asset.** A seller scans a product variant and publishes an approved Object ID with an online listing. A shopper copies the ID into Home Composer. Resolving the ID needs no marketplace integration, but permission and licensing checks still apply. No seller receives the shopper's home data by default.

**UJ-06 Product discovery.** A buyer photographs/scans a desired item, receives exact-confirmed, probable, similar or no-match candidates, and finds merchant-approved availability and shelf locations. A full 3D scan is not required for a quick identification query.

**UJ-07 Daily merchant observations.** Staff scan stock by zone. Reuse existing product assets, associate observations with a map revision, review changes and publish a fresh projection. Missing visibility is not zero stock; observed fronts are not hidden units.

**UJ-08 Shop exploration.** The viewer opens the shop, highlights the product's approved shelf, and can play a virtual route from a known starting point. Live physical navigation additionally requires a qualified positioning and route system.

**UJ-09 Developer integration.** An approved external developer embeds the SDK and calls scoped APIs. Their app need not use Vue/Suha. They receive neither AWS account credentials nor implicit access to other customers' assets. This expands approved consumers, not unrestricted redistribution or free export rights.

## 4. Common requirements and acceptance

| ID | Basis / stage | Required behavior | Acceptance evidence |
|---|---|---|---|
| 3DP-001 | C / F | Treat both scanners as reusable SDK/service products; standalone apps are consumers. | The same versioned scanner runs in an app and a minimal approved HTML/JS or native test host without copied business logic. |
| 3DP-002 | C / F | Keep the independent engine free of Google ARCore and wrappers that invoke it in the target path. | Dependency/runtime audit plus qualified capture without the Google ARCore service; legacy consumer code remains visibly separate until migration. |
| 3DP-003 | C / F | Use Vue SPA and licensed Suha assets for our web/mobile interfaces; no Ionic, React or React Native. | Dependency and UI review; third-party SDK consumers are not forced to adopt our UI framework. |
| 3DP-004 | C+E / F | Use shared C++ processing and JavaScript SDK interfaces with platform adapters; Python for backend/domain and research orchestration. | Build/interface tests distinguish browser WASM, native code and backend jobs; no mandatory Python interpreter on a customer's phone. |
| 3DP-005 | C / P | Make WebGPU the primary browser visualization target now. | Actual WebGPU render/interaction tests on the qualified device matrix; WebGL2 fallback, if retained, is labelled and is not counted as WebGPU acceptance. |
| 3DP-006 | C+E / F | Use central User Management for people, profiles and SSO. Preserve the established identity/session contract. | First-party unauthenticated entry redirects to user.wizestay.com and returns safely after sign-in; existing central sessions avoid another credential prompt. No new password/user-profile master. |
| 3DP-007 | C / F | Use Resvanta as sole master for REAL and VIRTUAL properties. | Home/property creation, retrieval and search call the authoritative API; no editable local property/address fallback; virtual spaces cannot masquerade as bookable dwellings. |
| 3DP-008 | C+E / F | Separate scanning, media, product catalog, physical instances, placements and inventory authority. | Tests show one object asset used in multiple designs/shops without changing stock or home ownership. |
| 3DP-009 | C+E / F | Authorize every resource/action, not possession of a Home ID, Object ID, Design ID or product ID. | Cross-account, cross-organization, stale-share and guessed-ID negative tests cover metadata, binaries, comments, routes and uploads. |
| 3DP-010 | C+E / P | Keep capture and a qualified local preview available without mandatory reconstruction-server calls after provisioning and within valid offline rights. | Block network during the released local capture profile; unavailable capabilities remain unavailable rather than silently switching to cloud. |
| 3DP-011 | E / X | Offer cloud refinement only as an explicit opt-in mode after capture, privacy, algorithm, cost and GPU decisions are approved. | Local original remains usable; upload/processing consent is recorded; result is a new candidate, not an automatic overwrite or accuracy guarantee. |
| 3DP-012 | C+E / F | Separate raw input, diagnostics, working checkpoints, review outputs and tenant-facing published assets. | A viewer's grant cannot fetch raw household frames, IMU data, private annotations or diagnostic ZIPs. |
| 3DP-013 | C+E / F | Store large assets in private S3 and keep ownership/version/status/digest references in the owning backend. | No binary model in ordinary API JSON/database rows; denied direct S3 access and authorized CDN delivery tests. |
| 3DP-014 | E / F | Use direct, narrowly scoped temporary uploads with resumable multipart recovery and server-side validation. | Interrupted transfer resumes the same intent; expiry/replay cannot overwrite a published version or publish unvalidated data. |
| 3DP-015 | E / F | Make successful upload, successful reconstruction, owner approval and publication distinct states. | A partial upload or failed/low-quality job never produces a published-success state. |
| 3DP-016 | E / F | Publish immutable asset revisions; replace only an authoritative published-version pointer transactionally. | Concurrent publish conflicts and clients cannot mix geometry from one revision with textures/placement coordinates from another. |
| 3DP-017 | C+E / P | Support one-to-many authorized scene delivery independent of the capturing phone. | Two distinct eligible accounts open the same approved revision on separate devices while the source phone is offline. |
| 3DP-018 | C+E / F | Keep structural geometry, captured furniture, reusable object assets and design placement layers distinct. | Replacing a chair does not mutate walls or duplicate an embedded chair; inseparable legacy geometry exposes an editing limitation. |
| 3DP-019 | E / F | Use explicit coordinate frames, units, gravity alignment, scale status and uncertainty. | Cross-service fixtures preserve handedness, quaternion order and physical dimensions; unknown scale never silently becomes metres. |
| 3DP-020 | C+E / P | Place real products at their recorded physical size by default. | Nonuniform or illustrative scaling is labelled; fit results are unavailable/approximate when home or object scale is unverified. |
| 3DP-021 | E / P | Retain observed, inferred, manually supplied and catalog-supplied evidence separately. | A generated wall or texture does not increase measured coverage or confer verified dimensions/inventory. |
| 3DP-022 | E / P | Make scan-quality gates independent of rendering appearance. | Held-out real measurements and geometric completeness are evaluated separately from visual fidelity and frame rate. |
| 3DP-023 | E / F | Reject corrupt/unbounded assets before unsafe allocation or model execution. | Archive traversal, duplicate entries, decompression bombs, invalid floats, indices, textures and unsupported schemas fail within budgets. |
| 3DP-024 | E / F | Keep cameras, workers, CPU/GPU buffers and temporary decrypted data bounded and lifecycle-owned. | Cancel, navigation, account switch, memory pressure and GPU loss cannot leave hidden capture, leaked private scenes or stale callbacks. |
| 3DP-025 | C+E / P | Treat product identity, product variant, reusable Object ID and physical-unit identity as different records. | Visually similar sizes/colors/multipacks are not silently merged; absent serial evidence leaves cross-day unit identity uncertain. |
| 3DP-026 | C+E / P | Distinguish current merchant stock, manually verified counts, observed counts, shelf facings and unknown quantities. | Repeated viewpoints do not inflate counts; unvisited/occluded stock is unknown; incompatible count bases cannot be summed. |
| 3DP-027 | C+E / P | Attach freshness, scope, evidence and review state to availability and location. | Daily observations cannot be presented as continuously live stock; stale or revoked merchant projections disappear or are labelled. |
| 3DP-028 | C+E / P | Store product location against a specific map revision and human-readable shop/floor/aisle/shelf hierarchy. | Map correction causes an explicit location migration/review; similarly named shelves in different shops cannot collide. |
| 3DP-029 | E / X | Separate virtual scene travel from live indoor positioning and route safety. | No start-position evidence means no exact live-user marker; routes exclude known blocked/private/unmapped paths and are not emergency guidance. |
| 3DP-030 | C+E / P | Permit scoped object and design sharing with distinct view, use/place, comment, edit, publish and export rights. | An Object ID share reveals no home; a commenter cannot move items; a design viewer cannot extract unauthorized underlying assets. |
| 3DP-031 | C+E / P | Keep source scenes and design alternatives independent and reproducible. | A design pins asset revisions; changed assets require explicit upgrade/revalidation rather than silent replacement. |
| 3DP-032 | C+E / F | Preserve subscription-controlled protected viewing and separately paid portable downloads. | Client paid flags, asset possession and S3 upload success grant no subscription/export entitlement; purchase alone is not perpetual viewing. |
| 3DP-033 | E / F | Define production scene encryption, per-asset key custody, scoped grants, revocation, recovery and browser/native interoperability before distribution. | Cross-device authorized open works without a universal key; legacy phone-only keys are not assumed exportable or remotely recoverable. |
| 3DP-034 | E / F | Separate content-delivery authorization from decryption/viewing rights and describe residual copying risk. | No plaintext key in CDN cache, URL, manifest, logs or browser bundle; revoked grants cannot be renewed; authorized hostile clients are not claimed copy-proof. |
| 3DP-035 | E / F | Define finite offline leases and preserve already-captured data on expiry. | New protected use stops at expiry; safe checkpoint finalization does not renew access; disconnected revocation is not advertised as instant. |
| 3DP-036 | C+E / F | Register external developer organizations/apps, approved purposes, scopes, origins/callbacks and quotas. | Public SDK/app identifiers are not secrets; unauthorized integrations cannot impersonate users, enumerate assets or issue licences. |
| 3DP-037 | E / F | Use idempotent commands, optimistic concurrency and durable event delivery. | Duplicate requests/reordered events and uncertain cloud submission reconcile the original operation rather than duplicate jobs, publications or charges. |
| 3DP-038 | E / F | Version schemas, events, codecs, SDKs, models and calibration profiles together. | Unsupported combinations fail before capture/open; readers preserve declared compatibility and migrations never reinterpret units silently. |
| 3DP-039 | C+E / F | Use request-driven AWS services and Terraform in Majid's designated AWS account only. | Account/region guards, least-privilege OIDC and one-state resource ownership tests; no unrelated employer account or credentials. |
| 3DP-040 | C+E / F | Preserve the five-minute-idle/automatic-request-resume goal without inventing provider controls. | No provisioned API concurrency or keep-warm loop by default; configurable database pause is 300 seconds where supported. Provider-managed Lambda freeze is not an exact timer. GPU scale-down exception needs D06. |
| 3DP-041 | E / X | Keep GPU reconstruction in asynchronous, bounded jobs, not API request handlers. | Concurrency, duration, input size, spend allowance, retry and queue-age limits; authorized cancellation/reconciliation and checkpoints for interruptions. |
| 3DP-042 | C / F | Deliver source through a feature branch, review and main merge, with GitHub Actions deployment for implementation releases. | Verify candidate and merge identity; docs-only delivery changes no deployment activation, secrets, workflows or live resources. |
| 3DP-043 | C+E / F | Apply SOLID, separation of domain/application/adapters, dependency injection and explicit interfaces. | Architecture tests forbid UI/database/vendor coupling across ownership boundaries; avoid a mandatory microservice per table. |
| 3DP-044 | E / F | Protect privacy through consent, scoped capture, minimization, retention and deletion workflows. | No default audio, face identification, staff/shopper tracking or use of customer scans for training; rights to photograph a shop/product are not assumed. |
| 3DP-045 | E / F | Make deletion and rights withdrawal reference-aware and auditable. | A design with a removed asset shows a tombstone/blocked reference; legal holds and retained versions are explicit; revoked authority is never restored by backup. |
| 3DP-046 | E / F | Bound search, processing, uploads, egress, logs and storage by customer/project. | Quotas and admission stop new expensive jobs; cost alerts are not represented as a guaranteed billing cap or free-tier promise. |
| 3DP-047 | E / P | Supply accessible alternatives to 3D interaction. | Keyboard and screen-reader object lists, placement forms, text locations, progress and unavailable states allow meaningful use without dragging in 3D. |
| 3DP-048 | E / F | Record reproducible evidence for source, format security, integration, cloud and actual devices separately. | No mock, generated room, emulator result or stored historical report is relabelled real-house accuracy or completed deployment. |
| 3DP-049 | E / F | Preserve existing engine, research branches, local scans and signed-app update compatibility. | Additive requirements do not delete source or keys, merge unaccepted experiments, uninstall the existing phone app or overwrite old standards. |
| 3DP-050 | E / F | Maintain traceability from each local requirement to shared contracts, tests, decisions and release evidence. | Every enabled capability has an owner and acceptance result; unresolved decision gates remain visible, not default-approved. |

## 5. Architecture and ownership decisions

Proposed backend control plane: Python API Gateway/Lambda, an application-owned metadata store (DynamoDB is a candidate, not a mandate for all domains), private S3, CloudFront, KMS, durable queue/outbox and job coordination. Reuse existing Account Centre and Resvanta APIs, not their database credentials. Optional CPU/GPU pipelines are adapters with immutable container/model/configuration identities and explicit billing limits. The exact storage engine, schema, region and processing provider require the companion decisions.

Object and home services have separate asset namespaces and ownership. Shared upload/codec/key-delivery libraries must be versioned, not copied and edited independently. Composer stores references and transforms, not authoritative duplicates. Discovery stores catalog/location/observation facts; financial stock ledgers remain external unless separately scoped. A published design references exact home, object and map revisions; no service may silently migrate coordinates by changing a label.

## 6. Rollout and non-goals

First integrated pilot: one owned/authorized measured room, one independently scanned object, secure upload, two-account viewing, physical-scale placement and a shared design comment. Object-only scans can also complete independently. Next: developer SDK integration, seller-published Object IDs, merchant-reviewed location discovery, then qualified larger-space/daily-inventory workflows.

This baseline does not deliver or approve an algorithm, production cryptosystem, automatic furniture removal, survey-grade floor plan, exact inventory from occluded video, universal device support, live indoor positioning, physical AR overlays, public source licensing, real payments, third-party model rights or cloud deployment. These are requirements and decisions to prove, not conveniences to simulate as success.

## 7. Source precedence

The owner's 14 October 2026 product/service discussion and WebGPU decision, the 3–12 October Resvanta/SSO decisions, and the 25 September room-debug priority take precedence over conflicting older delivery-order assumptions. Existing `three-dimension-view-arcore/docs/REQUIREMENTS.md` v1.1 is preserved as the historical full-scope baseline. The new service addendum in that repository records amendments and responsibility transfers. [DECISIONS_AND_ACCEPTANCE.md](DECISIONS_AND_ACCEPTANCE.md) contains the external technical source register and unresolved policy gates.
