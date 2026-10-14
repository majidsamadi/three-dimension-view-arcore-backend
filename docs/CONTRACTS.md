# Cross-service data and API contracts

**Document:** TDV-CONTRACTS-001 · **Version:** 1.0 · **Date:** 14 October 2026  
**Status:** E — proposed logical interfaces, not deployed endpoints or executable schemas. Implementations must produce reviewed OpenAPI/JSON schemas and interoperability tests before activation. Read [shared requirements](PLATFORM_REQUIREMENTS.md) and [decision gates](DECISIONS_AND_ACCEPTANCE.md).

## 1. Authority and identifiers

The authenticated context supplies `user_id`, approved application and organization scope. Clients cannot set owner/admin/paid flags. First-party human identities come from the existing WiseStay Account Centre and its current session-validation contract. Machine callers need independently scoped credentials; an API key may meter usage but is not proof of end-user access. A partner's product ID, an external SKU, a Resvanta property ID and an Object ID are different identifiers.

| Identifier | Authority | Meaning |
|---|---|---|
| user_id | User Management | Existing canonical person identity; never regenerated from email by a scanner |
| property_id | Resvanta | REAL or VIRTUAL property identity; no local editable address/property master |
| scene_id + scene_revision | Home Scanner backend | A home/shop scan and an immutable reconstruction/publication revision |
| capture_id | Owning scanner backend | One intended capture and its recovery/upload history |
| object_id + object_revision | Object Scanner backend | Reusable captured asset; not a stock quantity or a physical unit |
| product_id + variant_id | Discovery catalog/integration boundary | Seller-approved product/variant identity; external catalog keys are namespaced |
| instance_id | Observation/association domain | Evidence-backed physical-instance hypothesis; optional/uncertain across days |
| design_id + design_revision | Composer backend | A saved arrangement and collaboration history |
| placement_id | Composer backend | One occurrence of a pinned Object ID inside a design |
| shop_id / location_id / map_revision | Discovery backend | Merchant/shop context, internal shelf/zone and coordinate version; property address comes from Resvanta |
| observation_id / snapshot_id | Discovery backend | Time-scoped observed evidence and reviewed publication, not a sale or reservation |
| upload_id / job_id / grant_id | Owning backend | Transfer intent, asynchronous processing operation and scoped access grant |

Opaque IDs must be unpredictable enough to resist easy enumeration but are not secrets or authorization. Names/labels are editable presentation; IDs remain stable. API path IDs are validated as typed bounded strings, not used directly as arbitrary filesystem/S3 paths.

## 2. Asset manifest and coordinate profile

`tdv.asset-manifest/1` is the proposed manifest family. Required fields: `schema_version`, `asset_kind` (home_scene or object), `asset_id`, `revision`, `created_at`, owning authority reference, `representation`, `coordinate_profile`, `bounds`, `components`, `quality`, `provenance`, `visibility`, and supported reader/codec versions. Home manifests include `property_id`; an independent object does not require a property. Service-only fields and private provenance must not leak into the distributed audience projection.

Each component records a backend-controlled relative key, content type, byte count, full-file SHA-256, representation role, codec version, encryption/key-reference metadata and optional LOD/region bounds. Readers reject traversal, absolute/foreign URLs, executable references, unknown required codecs and oversized allocations. Component keys never contain presigned URLs or actual decryption keys. A manifest authenticates the component set and binds geometry, texture, collision and semantic revisions; a partial set is not publishable.

Proposed canonical spatial profile: right-handed, Y-up world frame; metric coordinates only after verified scale conversion; translation `[x,y,z]`, rotation quaternion `[x,y,z,w]`, normalized finite rotations and explicit unit scale. Capture-camera/IMU frames retain their actual conventions and transform chains. The exact profile is D02 until cross-runtime golden vectors are accepted. Raw legacy relative-unit data is never re-labelled metres. Store `scale_status` (unknown, estimated, reference_calibrated, independently_verified), `metres_per_unit` nullable, uncertainty/method, and measured-reference provenance. A UI may show estimated size but cannot return a verified-fit result from unknown scale.

A geometry/appearance representation may be mesh, point cloud, splat or a reviewed combination. These are not interchangeable for collision, measurements or navigation. A splat-only asset can be visually inspectable while dimension/clearance checks remain unsupported. Every representation must preserve visible limitations and indicate observed versus inferred parts. File extensions and a final commercial codec are unresolved D01, not inferred from development `.tdvscene`, `.tdvdebug.zip` or `TDVDEV01` names.

## 3. Logical records

### CaptureSession

Fields: `capture_id`, verified actor/org/app scope, property or object target, device/runtime/engine/calibration IDs, capture mode, UTC start/end, monotonic observation timeline, coverage, consent receipts, local checkpoint reference, upload references, `state`, `version`. Do not store reusable credentials. Sensor timestamps and server receipt times remain separate; gap/camera-change flags are explicit. Intended local sequence: created -> capturing -> paused/resumed -> finalized or cancelled/interrupted; an interrupted checkpoint is recoverable only to its recorded scope. Finalized does not mean uploaded or geometrically accepted.

### AssetRevision

Fields: immutable asset/revision/parent identities, input digest set, representation/manifest digest, object bounds or structural graph, quality report, algorithm/container/model/config versions, privacy projection, source retention class, current review state. Lifecycle: uploading -> uploaded -> validating -> processing (optional) -> review_ready; validation/processing can fail, be cancelled or become reconciliation_required. Only reviewed candidates can become published. Superseded/withdrawn/deleting/deleted are distinct from failed. Published means permitted release, not measured accuracy beyond the attached quality evidence.

### UploadIntent

Fields: server-assigned resource prefix, actor/action scope, expected components and limits, encryption/storage class policy, expiry, multipart identifiers, content binding, completed component versions, finalize idempotency and validation status. A temporary PUT URL may be reusable until expiry; do not call it one-use merely because the app invokes it once. Upload only to a private staging key. Server binds exact S3 object versions/checksums, freezes the accepted set, then writes or copies immutable accepted keys. Published keys are never client-writable. ETags are not generally full-file hashes; multipart checksums can be composite. Verify the manifest's full-file SHA-256 independently when necessary and preserve the provider checksum type.

### ProcessingJob

Fields: job/idempotency ID, input snapshot digests, approved pipeline profile, pinned artifacts, requested/estimated budget, admission decision, provider job reference, attempts, stage/status, progress evidence, cancellation state, output references, billed/estimated cost provenance. States: requested -> admitted -> queued -> starting -> running -> validating_output -> succeeded; rejected/failed/cancel_requested/cancelled/timed_out/reconciliation_required remain distinct. A lost submit response is reconciled by the original operation token; no blind new GPU job. Cancellation acknowledges a request before it confirms provider termination. An output completed after cancellation cannot silently publish.

### Design and Placement

Design: `design_id`, owner/org, `property_id` when tied to a property, pinned `scene_id/revision`, coordinate profile, title, visibility, members/roles, revision and status. A design can be an explicitly labelled sandbox without inventing a new physical property. Placement: `placement_id`, `object_id/revision`, authorized variant/reference, transform, visibility, anchor/room reference, provenance, scale mode and fit status. Multiple placements of one model are distinct occurrences, not extra asset copies or inventory transactions. Coordinates and comments refer to the same immutable design revision. Comment anchors include placement ID and scene/design revision, with an orphaned-anchor state after removal.

### Product, Observation, Location and Availability

Product/variant: merchant-scoped source identifiers, brand/model/size/color/package/unit, Object ID mapping, supporting evidence and match/review status. Exact-confirmed requires defined evidence such as verified catalog identifiers; a high visual similarity score alone remains probable/similar.

Observation: session/frame/zone/map references, event time interval, source type, candidate products, quantity basis/value/range, coverage/occlusion, association uncertainty, reviewer corrections. Location: canonical property reference plus shop/floor/aisle/bay/shelf label and stable ID, map revision, pose/bounds and confidence. Published availability: approved audience projection, source observed/manual/POS, value or state, unit, last_observed_at, last_confirmed_at, valid_until/freshness policy, review revision and source lineage. No observed evidence is represented as continuously available or as hidden backroom stock.

Route: map/graph revision, source anchor, destination location revision, allowed audience, accessibility constraints, blocking/freshness evidence and route mode (virtual_preview or qualified_live_navigation). A moving phone position requires separate calibrated localization with uncertainty; no WebGPU shader or product recognition result supplies it automatically.

## 4. Common transport conventions

Proposed HTTP APIs are versioned `/v1`. Mutations carry an `Idempotency-Key` plus a normalized request digest; reusing the key with different content returns conflict. Updates use `If-Match` or explicit `expected_version`; stale edits return conflict rather than silently replacing changes. Lists use bounded cursor pagination, stable sort and permission-filtered totals. Identifiers in cursors cannot bypass scope. Server timestamps are aware UTC; UI displays local context.

Error body: `code`, safe `message`, `operation_id`, `retryable`, optional `field_errors`, and recovery reference. Error vocabulary includes unauthenticated, forbidden, not_found, conflict, invalid_state, unsupported_schema, unsupported_capability, missing_asset, checksum_mismatch, incomplete_upload, quality_review_required, quota_exceeded, dependency_unavailable, expired_grant, cancelled and reconciliation_required. Do not return private existence/details through a forbidden resource error. Retries follow operation semantics, not a universal exponential-retry wrapper around effects.

No current Account Centre or Resvanta endpoint is renamed by the proposed paths below. Integration adapters consume their actual released schemas and live validation rules. Separate adapter compatibility evidence is mandatory.

## 5. Proposed API families by owning backend

| Home Scanner backend | Required input / result / rule |
|---|---|
| POST /v1/home-captures | Authorized canonical property and capture profile -> capture_id; verify scan/publication authority separately |
| POST /v1/home-captures/{id}/uploads | Expected bounded component manifest -> staging upload intent |
| POST /v1/uploads/{id}/parts | Authorized part numbers/digests -> temporary part upload URLs |
| POST /v1/uploads/{id}/complete | Frozen component versions/checksums -> validation operation; not publication |
| GET /v1/uploads/{id} | Recover the original transfer and missing parts without creating a new capture |
| POST /v1/home-scenes/{id}/jobs | Approved opt-in processing profile/input revision -> asynchronous job_id |
| GET /v1/jobs/{id}; POST /v1/jobs/{id}/cancel | Safe progress/reconciliation and scoped cancel request |
| POST /v1/home-scenes/{id}/revisions/{rev}/publication | Expected publication version and reviewed audience -> published revision pointer |
| POST /v1/home-scenes/{id}/view-grants | Current scene/identity/subscription checks -> bounded delivery and key-access grant |
| GET /v1/home-scenes; GET /v1/home-scenes/{id} | Permission-scoped metadata and versions; property search remains Resvanta |
| POST /v1/home-scenes/{id}/withdrawal | Stop new grants, preserve history and expose bounded outstanding-grant lifetime |

| Object Scanner backend | Required input / result / rule |
|---|---|
| POST /v1/objects | Object metadata and rights attestation -> object_id/draft revision; actor derived from authentication |
| POST /v1/objects/{id}/captures | Capture/representation profile -> scoped session |
| POST /v1/objects/{id}/uploads | Same upload contract, object namespace only |
| POST /v1/objects/{id}/jobs | Frozen capture inputs -> bounded processing job if enabled |
| POST /v1/objects/{id}/revisions/{rev}/publication | Reviewed object/variant/scale evidence and audience -> immutable published asset |
| GET /v1/objects/{id}; GET /v1/objects | ID resolution and bounded authorized library discovery |
| POST /v1/objects/{id}/use-grants | Requested view/place/reference/download action -> separately scoped entitlement |
| POST /v1/objects/{id}/shares; DELETE /v1/objects/{id}/shares/{share} | Audience/action/expiry and revocation; link possession alone does not grant home access |
| POST /v1/objects/{id}/deletion-requests | Reference-aware withdrawal/retention/erasure workflow, not immediate blind S3 deletion |

| Composer backend | Required input / result / rule |
|---|---|
| POST /v1/designs | Authorized home revision or labelled sandbox -> design_id |
| GET /v1/designs/{id}; GET /v1/designs | Versioned permitted design and library |
| POST /v1/designs/{id}/placements | Authorized pinned Object ID/version and transform -> placement_id |
| PATCH /v1/designs/{id}/placements/{pid} | Finite transform, scale mode and expected design version -> new revision |
| DELETE /v1/designs/{id}/placements/{pid} | Remove an occurrence, not the global asset |
| POST /v1/designs/{id}/alternatives | Explicit fork/base revision -> independent alternative |
| POST /v1/designs/{id}/asset-upgrades | Explicit reviewed revision mappings -> revalidated fit/anchors |
| POST /v1/designs/{id}/comments | Permitted text and versioned anchor -> append/edit-history record |
| POST /v1/designs/{id}/shares | Named audience and view/comment/edit rights; no inherited asset ownership |
| POST /v1/designs/{id}/view-sessions | Recheck every referenced resource and issue bounded delegated media grants |
| POST /v1/designs/{id}/publication | Publish composition separately from the source home's listing publication |

| Discovery backend | Required input / result / rule |
|---|---|
| POST /v1/product-queries | Consented bounded image/identifier query -> search operation; temporary retention |
| GET /v1/product-queries/{id}/results | Ranked candidates with exact/probable/similar/unknown classification |
| GET /v1/products/{id}/locations | Merchant-published availability, freshness and canonical location projection |
| POST /v1/shops | Verified merchant and canonical property reference -> shop business context |
| POST /v1/shops/{id}/catalog-imports | Scoped catalog mappings -> preview/errors before commit |
| POST /v1/shops/{id}/observation-sessions | Authorized zone/map -> observation session |
| POST /v1/observation-sessions/{id}/batches | Stable observation IDs and evidence -> durable review state |
| POST /v1/shops/{id}/snapshot-reviews | Bounded corrections and expected version -> reviewed snapshot |
| POST /v1/shops/{id}/publications | Approved snapshot/audience/freshness policy -> customer projection |
| POST /v1/routes | Known start, destination/version and restrictions -> virtual route or unsupported state |

## 6. Events and consistency

Proposed envelope `tdv.event/1`: event_id, event_type, schema_version, owning service, aggregate_id/version, operation_id, occurred_at, correlation_id, causation_id and minimal typed payload. Producer commits domain change plus outbox atomically; consumers deduplicate by event identity and reject conflicting payloads. Events contain references, not raw customer photographs, usable keys or credentials. Events never independently grant access.

Home emits `home.scene.review_ready`, `home.scene.published`, `home.scene.withdrawn`, `home.scene.deleted`. Object emits `object.revision.published`, `object.access.changed`, `object.deleted`. Composer emits `design.revision.created`, `design.shared`, `design.access.changed`. Discovery emits `inventory.snapshot.published`, `product.location.changed`, `route.graph.changed`. Common job/transfer states have explicit owner-qualified events. Consumers keep revision ordering/tombstones and re-authorize before effects. A removed asset blocks dependent open/use without erasing the design's audit record.

## 7. S3, distribution and key-access contract

Illustrative private prefixes: `staging/{scope}/{upload_id}/`, `home-scenes/{scene_id}/{revision}/`, `objects/{object_id}/{revision}/`, `private-inputs/{capture_id}/`, `quarantine/{operation_id}/`. Exact bucket ownership and region are D03/D04. Names are examples, not deployed locations. Object service owns object binaries; home service owns home binaries; Composer references both. Do not grant a whole property prefix just to read one revision.

Authorize staging creation and completion separately. Validate content, dimensions, total bytes, hashes, representation and permitted privacy projection before copying to accepted immutable keys. Client replacement of a staging key after verification must not alter the pinned accepted S3 version. Abort orphaned multipart uploads through a bounded lifecycle policy; private source retention and published-version retention are distinct.

CloudFront signed access controls ciphertext delivery; private origins use Origin Access Control. Decryption/opening also needs current asset/action entitlement. A valid CDN link is not sufficient to issue a content key. Per-revision content keys are wrapped with approved backend custody and delivered only through authenticated TLS to authorized clients, never placed in manifests or CDN caches. Native device-bound delivery and browser custody are D01. Signed-cookie scope, CORS, credentials, same-site policies and native cookie limitations must be qualified; URLs are an alternative where appropriate. No fixed TTL is approved here.

## 8. Required cross-service contract tests

Golden fixtures must cover physical-scale transforms, unknown units, quaternion sign/equivalence, home+object same-frame composition, incompatible codecs, manifest tampering, mismatched asset components, nested external URLs, expired keys/leases, cross-user grant requests, repeated transfers/jobs, stale publication pointers, concurrent design edits, deleted asset references, same Object ID in two shops, map-version changes, observation count bases, wrong product variants, route uncertainty and legacy-protected-export refusal. Provider mocks establish only local contract behavior; real cloud/device acceptance is separate.
