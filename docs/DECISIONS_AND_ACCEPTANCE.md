# Decisions, acceptance and source register

**Document:** TDV-DECISIONS-001 · **Version:** 1.0 · **Date:** 14 October 2026  
Requirements and proposed engineering controls only. No acceptance below is marked executed or passed by this publication. The [platform specification](PLATFORM_REQUIREMENTS.md) defines C/E labels; the [contracts](CONTRACTS.md) are proposals until executable schemas and consumers are qualified.

## 1. Decisions that are already explicit

The owner chose WebGPU as the current visualization target; reusable Home Scanner and Object Scanner services; separate app/backend repositories; reusable S3 assets; Home Composer Object-ID and arrangement sharing; Where Can Find This product discovery and shop visualization; Vue/Suha for our interfaces, Python for backends, Terraform/AWS and branch-to-main GitHub delivery. Canonical people remain in Account Centre; REAL and VIRTUAL properties remain in Resvanta. These are not invitations to replace the existing identity provider or create duplicate property databases.

Owner direction is not evidence that the new features are implemented. Backend/cloud-refinement recommendations are recorded below without treating prior assistant suggestions as deployment or algorithm approval.

## 2. Open decision register

| ID | Decision required | Proposed safe direction | Gate / decision owner |
|---|---|---|---|
| D01 | Production scene/object container, crypto/key custody and cross-device recovery | Authenticated component manifest and per-revision encryption; explicit native/browser grant delivery; never reuse development TDVDEV01 as production by assertion | Security + product; blocks production protected distribution |
| D02 | Coordinate/scale profile and confidence semantics | Right-handed Y-up, explicit quaternion order and verified metres conversion; preserve legacy relative coordinates | Engine + asset/Composer owners; blocks dimensionally reliable composition |
| D03 | Metadata database for each backend | Review DynamoDB on-demand versus existing approved transactional serverless options against concurrency/query requirements; no universal database choice by template | Architecture; blocks physical schema/IaC selection |
| D04 | AWS account, region, buckets, CDN domain, residency and Terraform ownership | Founder-designated account; private source/published namespaces; one state owner per resource; no invented account ID/domain | Product + infrastructure; blocks deployment |
| D05 | Cloud reconstruction mode, input contract and algorithms | Local capture remains; cloud is explicit opt-in refinement; compare candidate pipelines against measured same-input baselines | Product + engine; blocks mandatory cloud processing/model adoption |
| D06 | GPU cost/availability and idle behavior | Asynchronous bounded GPU jobs with no warm pool; record provider scale-down and cold-start limits; exact 300-second inactivity cannot be promised for provider-controlled GPU lifecycle | Product + infrastructure; blocks GPU spend and any exception to five-minute-idle target |
| D07 | Supported devices, browsers/WebViews, sensors and runtimes | Qualify named combinations separately; WebGPU first, optional explicitly labelled fallback; no universal scanning or WebGPU claim | QA + product; blocks released compatibility matrix |
| D08 | Quality thresholds and evaluation dataset | Freeze measured dimension/surface/coverage/recognition/count/localization thresholds before scoring; separate appearance from measurement | Product + independent QA; blocks accuracy/fit/stock claims |
| D09 | Subscription, free previews, seller/shopping seats and paid-download policy | Preserve subscription viewing and separate paid portable export; any free shopper/guest preview is an explicit exception, not a default | Product + finance; blocks commercial entitlement activation |
| D10 | External developer onboarding and delegations | Contracted/approved integrations, explicit scopes, consent, quotas, callback registration and revocation; no universal API key | Product + security; blocks third-party production access |
| D11 | Home sharing while rented and public listing audiences | Media/design rights are explicit and separate from physical IoT control; owner status alone does not publish occupants' private content | Product + privacy; blocks cross-party publication/sharing |
| D12 | Raw-capture/diagnostic/query retention and training consent | Short, purpose-specific policies; no default customer training or automatic public upload; deletion handles every retained version and legal hold | Privacy + product; blocks live personal-data ingestion |
| D13 | Product matching and stock authority | Separate exact-confirmed/probable/similar results; merchant/POS truth and image observations retain different bases and freshness | Discovery product + merchants; blocks exact-availability claims |
| D14 | Indoor navigation and position source | Virtual route first; live positioning only after calibrated source, map alignment, route constraints and uncertainty validation | Discovery + QA; blocks live turn-by-turn claims |
| D15 | Dependency/model/dataset/asset licence terms | Review code, trained weights, datasets and output-use rights separately; public availability is not commercial permission | Product/legal + engineering; blocks dependency adoption/distribution |
| D16 | Public repository policy and purchased Suha distribution | Do not change visibility in this task. Review public repositories before proprietary implementation; never publish purchased template archives or customer scans | Repository owner; blocks accidental public proprietary/material delivery |
| D17 | Shared SDK/module hosting and release package names | Reuse the existing independent engine boundary; versioned object/home profiles and viewer/codec libraries; new SDK repository only if separately decided | Architecture; blocks duplicated scanner implementations |
| D18 | Quotas, latency, recovery and cost budgets | Define per-org upload/job/storage/egress budgets, quality-profile timeouts, concurrency, RPO/RTO and alert ownership with measured values | Product + operations; blocks production sizing/SLA claims |

No undecided item implies permission to weaken another requirement. A decision can remain open for a disabled expansion feature, but not for a feature advertised as live. Record decision date, options, reason, affected requirements/contracts and migration plan when resolved.

## 3. Acceptance matrix

| Scenario | Required result | Main repositories | Stage |
|---|---|---|---|
| AT01 Central SSO | Unauthenticated first-party entry redirects to central sign-in and returns to an allowlisted original route; wrong-account/expired/revoked session denied | All apps/backends | Foundation |
| AT02 Canonical property | A home/shop references Resvanta; local fake property/profile fallbacks are absent; REAL/VIRTUAL distinction preserved | Home backend/app, discovery, Composer | Foundation |
| AT03 Authorized cross-device viewing | Owner publishes one complete revision; two permitted viewer accounts open it while owner phone is offline; other account denied | Home app/backend, viewer, identity adapter | Pilot |
| AT04 Interrupted and adversarial upload | Resume same multipart intent, validate exact accepted versions/digests, reject replay overwrite and publish only after review | Both scanner backends/apps | Foundation |
| AT05 Local capture honesty | Provisioned offline scan yields actual observations or explicit failure; source and output are saved with true scale/calibration status | Engine, both scanner apps | Pilot |
| AT06 One object, many consumers | Same Object ID opens in scanner library, two Composer designs and an approved minimal SDK host without duplicated core code | Engine, object app/backend, Composer | Pilot |
| AT07 Real-size placement | Measured object in independently measured room preserves units/transforms; unknown scale disables verified-fit status | Scanner services, Composer | Pilot |
| AT08 Furnished-room replacement | Add/replace/hide operations distinguish separable existing furniture from inseparable geometry; no unexplained double chair or invented wall | Home/engine, Composer | Pilot/expansion |
| AT09 Owner–tenant collaboration | Object-only share exposes no home; design share pins placement; comment/edit roles are separate; concurrent edits conflict predictably | Composer app/backend, asset services | Pilot |
| AT10 Seller variant | Seller Object ID links the correct size/color/package; buyer can place without exposing their home to seller | Object service, Composer, discovery | Pilot |
| AT11 Product search | Exact-confirmed, probable, similar and no-match states have evidence; wrong size/brand/multipack and uncertain barcode are not silently accepted | Discovery app/backend | Pilot |
| AT12 Daily stock | Repeated passes/occlusion/unvisited zones retain unknown/count-basis distinctions; no duplicate count or inferred sale; merchant reviews publication | Discovery, observation SDK | Pilot/expansion |
| AT13 Location and map change | Product remains attached to correct shop/shelf/map; changed map invalidates or explicitly migrates poses/routes | Discovery, home service, viewer | Pilot |
| AT14 Route modes | Known start supports virtual path; absent/uncertain localization produces no exact moving-user marker; private/blocked areas excluded | Discovery, viewer | Expansion |
| AT15 WebGPU | Actual device rendering, orbit/zoom/top view/object selection and device-loss recovery; labelled fallback never counted as WebGPU pass | Viewer, all 3D apps | Pilot |
| AT16 Protected compatibility | Native/browser authorized open with scoped keys; legacy free-export routes cannot expose new protected data; corruption and expired rights denied | Engine, consumer, backends | Commercial gate |
| AT17 Deletion/revocation | Withdrawn object/home blocks new use; designs retain auditable tombstones; CDN/lease expiry residual windows disclosed | All backends/viewers | Foundation |
| AT18 Cloud jobs | Duplicate submit, uncertain provider response, GPU interruption, retry budget, cancellation and output validation preserve one intended job and no automatic publish | Scanner backends, cloud adapters | Optional expansion |
| AT19 Measured algorithm comparison | Same consented capture, frozen configuration, held-out measurements and failures for local/cloud candidates; imagery fidelity does not replace dimension evidence | Engine + scanner services | Accuracy gate |
| AT20 Developer isolation | Wrong integration/org/scope rejected; secretless browser SDK, approved callbacks and per-resource delegation; quotas/revocation tested | Both services + identity integrations | Developer release |
| AT21 Delivery and restore | Exact reviewed artifact, Terraform account guards, main CI, rollback without authority downgrade, restoration of metadata/keys/references | All implementation repos | Deployment gate |
| AT22 Data protection | Raw home images/IMU/private stock excluded from tenant/CDN projections; query retention enforced; no training or identity surveillance by default | All products | Privacy gate |

Each execution record must identify source/asset/model/configuration hashes, runtime and device, input rights, measured metrics and units, reference methodology, pass/fail/skips, known limitations, reviewer and timestamp. Keep real cloud, real phone, emulator, synthetic, schema-only and historical evidence separate.

## 4. Required project deliverables before implementation release

Each repository must add executable interface schemas, requirement-to-test mapping, architecture boundaries, controlled fixtures, reproduction instructions, error/recovery flows, threat model, data lifecycle, operations/rollback and its applicable deployment package. Apps also require full loading/empty/denied/offline/conflict states and accessibility evidence. Scanner outputs need camera/scale/coverage provenance. Backend release needs request-driven idle/resume evidence and no production activation until required D decisions close.

ChatGPT remains design/development coordinator; Codex may execute bounded tests or resolve an identified blockage and report actual evidence. Documentation authorship is not permission to run a new experiment, GPU campaign, customer data upload or live payment. Existing research approvals do not transfer to new configurations.

## 5. Source register and limitations

### Owner/source decisions

O1 — Owner discussion in this project, 14 October 2026: WebGPU now; Home Scanner as a reusable service; private S3 publication to multiple tenants.

O2 — Owner's Object Scanner and Home Composer examples: scan store furniture, reuse Object IDs, seller-provided IDs, owner–tenant review, furnished or unfurnished home.

O3 — Owner's Where Can Find This discussion: query by product scan, merchant daily stock observations, exact shop-interior location and WebGPU navigation; scanner remains a reusable service/SDK.

O4 — Owner project practices: Python backends; Vue/Suha clients; no Ionic/React; Terraform/request-driven AWS; five-minute idle/resume goal; branch -> main -> GitHub Actions -> designated AWS account; preserve SOLID and architectural ownership.

O5 — October 2026 centralization decisions: Resvanta owns all REAL/VIRTUAL properties; User Management owns canonical accounts/profiles and user.wizestay.com is the sole first-party human sign-in entry point.

R1 — Existing engine main was read at commit `6d9b35393aee297f345b9506982fd15361f29a8e`, including README, docs/REQUIREMENTS.md and docs/RESEARCH_DEBUG.md. Relative scale, limited keyframes, raw-IMU-only logging and no blueprint solver remain recorded. Existing requirements and research histories are not overwritten.

R2 — Existing consumer main was read at `4a2762ef9aa80ee7b123223ccfa1b723cb887aba`. Its earlier ARKit/Google ARCore/WebXR paths and local exports require explicit migration rather than being called independent-engine integration.

R3 — Account Centre README read 14 October 2026 describes existing canonical identity, current live validation and distinct consumer registration. New repositories must integrate the released contract rather than assume SSO connection is automatic.

### Primary technical references checked 14 October 2026

- W1 WebGPU specification: https://www.w3.org/TR/webgpu/ — rendering/compute interfaces, limits and device-loss behavior; not device compatibility or scanner-accuracy certification.
- W2 S3 temporary upload/download authority: https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html — URLs can be reused until expiry and existing keys can be replaced; this motivates immutable staging/finalization controls.
- W3 S3 integrity: https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html — checksum algorithms/types and multipart distinctions; no universal ETag-as-hash assumption.
- W4 CloudFront signed URLs/cookies: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-choosing-signed-urls-cookies.html — per-file and multi-file access choices; delivery grants are not scene decryption rights.
- W5 AWS Batch Fargate limitations: https://docs.aws.amazon.com/batch/latest/userguide/fargate-job-definitions.html — GPU resources are not available for Fargate jobs; evaluate an appropriate GPU compute path separately.
- W6 AWS 3D reconstruction guidance: https://docs.aws.amazon.com/solutions/open-source-3d-reconstruction-toolbox-for-gaussian-splats-on-aws/ — an evaluation candidate with GPU job and Terraform paths, not adopted software or certified architectural geometry.

These references describe capabilities and constraints; they do not choose a vendor/model licence, guarantee cost/quality or authorize deployment. Do not copy upstream code, model weights, private research images, purchased Suha archives, secrets, font files or customer capture artifacts into requirements commits.
