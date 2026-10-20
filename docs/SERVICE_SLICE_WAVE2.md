# Home Scanner service slice (wave 2)

Status: component-tested (synthetic data only). In-memory fakes and stub AWS clients only. Not deployed and not paired with the Home Scanner app (HSA). Decisions Q01–Q16 are DELEGATED-PROVISIONAL (see [DECISIONS_PENDING.md](DECISIONS_PENDING.md)).

WBS: HSB-02.1–02.4, HSB-03.1–03.4, HSB-04.1, HSB-05.1–05.4, HSB-06.1/06.2/06.4 (06.3 through fakes only), HSB-01.3+ live identity and Resvanta adapters.

## Routes (root `https://home-scanner.dev.wizestay.com/api/v1`)

The route set equals `contracts/draft/v0.4/fixtures/api/home-scanner.v0.4.json` exactly (`tests/test_http_contract_v0_4.py`).

| ID | Route | Purpose |
|---|---|---|
| H01 | `POST /home-captures` | Capture admission: Resvanta property must be `current`; REAL needs `permission_record_id`; occupied content refused |
| H02 | `POST /home-captures/{capture_id}/uploads` | Upload session: envelope draft validation, ≤ 10 components, ≤ 200 MiB each, presigned PUTs bound to sha256 and length |
| H03 | `GET /uploads/{upload_id}` | Component state reconciled from storage HEAD (a lost acknowledgement shows `confirmed`) |
| H04 | `POST /uploads/{upload_id}/component-urls` | Reissue URLs for non-confirmed components only |
| H05 | `POST /uploads/{upload_id}/cancel` | Cancel (repeat is a no-op) |
| H06 | `POST /uploads/{upload_id}/finalize` | Full-read digest check, GLB + envelope validation, one immutable version in one transaction |
| H07–H09 | `GET /home-scenes…` | Lists, scene detail, version detail (no URLs) |
| H10 | `POST …/versions/{version}/review` | Review decision plus review inputs (HSB-04.1) |
| H11 | `GET …/versions/{version}/audience-projection` | Geometry-only projection of an approved version |
| H12 / H13 | `POST …/publication`, `POST …/withdrawal` | Publish / replace / withdraw with `expected_version` |
| H14 / H15 | `POST …/grants`, `DELETE …/grants/{grant_id}` | Named-viewer grants (≤ 90 days) and revocation |
| H16 | `POST …/view-grants` | 300 s presigned GETs for the projection only, through the CommercialGate |

Every route requires a verified central access token. POSTs need `Idempotency-Key`; replays return the stored body, a different body gives 409 `idempotency_key_reuse`. Errors are `application/problem+json` from the closed X.1 table. Unknown resources, and resources the caller may not see, are 404.

## State machines

- Upload: `open` → `finalized` | `cancelled`; `open` past 7 days answers 410 `upload_expired`. Component: `pending` → `confirmed` | `failed` (`size_mismatch`, `digest_mismatch`); a failed component returns to `pending` when its URL is reissued.
- Finalize: a digest or size mismatch creates no version. The first success writes the version, the scene and the upload in one transaction. A repeat with the same key replays; a new key gets 409 `already_finalized`.
- Version: `validated` or `quarantined` (with `reasons[]`). Quarantined bytes go to `rejected/` (30-day expiry); validated bytes go to content-addressed `versions/<sha256>`. Version items are never rewritten.
- Review: `draft` → `review_ready` | `approved` | `rejected`; `review_ready` → `approved` | `rejected`; `rejected` → `review_ready`; `approved` is final. Quarantined versions cannot be reviewed. Approval writes the audience-projection envelope.
- Publication: `unpublished` → `published` (replacement supersedes the previous version) → `withdrawn`. Withdrawal blocks new view grants and grants immediately; outstanding view-grant URLs expire within 300 s.

Reads go through the existing `HomeReferenceResolver` (exact scene, version and property), with `RequestIdentityFacts` for the verified identity.

## Disabled or not implemented

- Cloud review jobs (HSB-04.2–04.4): DISABLED by Q02. `/home-scenes/{id}/jobs` returns 404.
- Occupied-home capture and publication (Q07): refused with `occupied_home_publication_disabled`.
- Export: the not-configured CommercialGate always denies it (Q10). The gate refuses to run in `production`.
- Byte deletion after withdrawal: not implemented. Withdrawn scene bytes stay in `versions/`; only `staging/` and `rejected/` expire through lifecycle rules.
- Online token revocation: not implemented. Tokens are honoured until `exp`.
- No live positioning, cloud refinement, external developer access, prices or ML model selection.

## Infrastructure

See [infra/README.md](../infra/README.md). Validated locally only; never planned or applied.
