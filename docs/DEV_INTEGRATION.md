# Dev integration journeys (wave 3, D9)

Status: implemented and locally verified against stubs. Nothing has run against dev yet. A journey counts as `paired-integrated (dev)` only when a dispatched run's report marks it `passed`.

`.github/workflows/dev-integration.yml` runs `python -m tools.dev_integration.run` by manual dispatch on `main`. It exercises the four deployed dev services end to end with synthetic data only (Q07 first slice). It makes no claim about physical accuracy: the asset is the 1 m synthetic unit box from `contracts/draft/v0.4`, and its declared dimensions are a synthetic declaration, not a measurement.

## What it checks

| Tier / journey | Steps | Expected in dev today |
|---|---|---|
| T0 (no identity) | Each API's deploy smoke route returns 401 `application/problem+json` `identity_required`. Each site's `/` returns 200 HTML whose sha256 matches `release.json`. `release.json.revision` equals the app's main SHA. `/assets/missing.js` returns 403/404. `/api/v1/web-session/<site>/readiness` returns JSON 200. | Needs the deploy pipelines to have run |
| T1 (identities) | Discovers the central client id from the public Account Centre config (`https://user.wizestay.com/api/v1/config`, issuer must be the dev pool). Signs in A and B with Cognito `USER_SRP_AUTH` plus TOTP. Checks token `iss`/`client_id`, and that each API turns 401 into an authenticated answer. | BLOCKED until the secrets below exist |
| `home_scanner` | H01 admit capture → H02 upload → presigned PUT of the synthetic GLB → H03/H06 finalize → H10 review → H11/H12 publish → B denied (H08/H16 404) → H14 grant → B views (H16 + presigned GET, digest checked) → H15 revoke → B denied (403 `grant_revoked`) | BLOCKED at H01 (`dependency_unavailable` or `property_not_usable`): Q14, no Resvanta `rv1` credential |
| `object_scanner` | O01 → O02 → presigned PUT → O03/O06 finalize → O07 synthetic dimensions → O09 review → O10 publish (named share) → Object ID resolution (O12/O13) → B denied (O12/O17 404) → O15 share → B views (O13/O17 + presigned GET) → O16 revoke → B denied (403 `grant_revoked`) | Feasible once identities exist |
| `composer` | C01 sandbox design → C06 place the object by Object ID → B denied (C03 404) → C18 object-only share (+ O15) → B opens it (C19), which names no design or home → B still denied the design → C14 design share → C15 accept → B opens the design → C17 revoke → B denied | Feasible once identities exist |
| `composer_home_placement` | C01 `property_home` design over the published scene → C06 place the object → C23 view session | BLOCKED while `home_scanner` is blocked |
| `finder_catalog_link` | F01 merchant (A becomes `merchant_manager`) → F02 → F04 shop on the synthetic property → F05/F06 catalog → F09 link the Object ID | BLOCKED at F04 (Q14). A 403 is reported as `MERCHANT_ROLE_NOT_GRANTED` |
| `finder_query` | F16 identifier query → F17/F19 → B denied (F17 404) | Feasible once identities exist. No candidates while no shop projection exists |

Cleanup runs at the end, in reverse order: H13 withdraw, O11 withdraw, O16 revoke, C05 archive, F10 withdraw link. Merchant, shop and catalog rows have no delete route and stay as synthetic dev records. Finder queries expire after 24 h.

## Report

The artifact `dev-integration-<sha>-<run_id>` holds `dist/dev-integration-report.json` (contract `wisestay.3d.dev-integration-report.v1`). Each tier and journey has:
- `status`: `passed`, `failed` or `blocked`
- `reason`: the exact cause
- `steps`
- HTTP `evidence`: step, method, path template, status and problem `code`; never a token, header value, URL query or body
- `created` ids and `notes`

The report also has a `cleanup` log, `summary` and `result`. The run exits 0 only if every tier and journey passed. Before writing, the runner refuses to write a report that would contain any secret or token value.

## Owner steps for test identities (needs a human)

Test identities cannot be created without a human:
- The pool `ap-southeast-1_RbRHXUipk` requires MFA, signs users in by e-mail and verifies the e-mail.
- No CI role holds `cognito-idp:AdminCreateUser`, and this wave adds none.
- User Management has no automated test-account mechanism. Its documented route is an operator-supplied synthetic account through private execution inputs (`docs/FIRST_PARTY_SESSIONS.md`), so no User Management code change is made.

Steps:
1. At `https://user.wizestay.com`, create two synthetic accounts (A and B) on inboxes you control. Plus-addressing is fine, for example `you+ws3d-a@…` and `you+ws3d-b@…`. Use no customer data.
2. Confirm each e-mail address. Then enrol an authenticator app (TOTP) for each account. While enrolling, record the base32 secret shown under "enter this key manually".
3. In GitHub, go to `majidsamadi/three-dimension-view-arcore-backend` → Settings → Secrets and variables → Actions. Add the repository secrets `WS3D_IT_A_USERNAME`, `WS3D_IT_A_PASSWORD`, `WS3D_IT_A_TOTP_SECRET`, `WS3D_IT_B_USERNAME`, `WS3D_IT_B_PASSWORD` and `WS3D_IT_B_TOTP_SECRET`.
4. Dispatch **Dev integration journeys** on `main`. Optionally pass `expected_revisions` as JSON (`{"home-scanner":"<HSA main sha>", …}`) when the app repositories' main SHAs are not publicly readable.

When a secret is missing, T1 reports `BLOCKED_TEST_IDENTITIES_ABSENT` and lists the missing names. Other sign-in problems are also reported as `blocked` with the human step that is missing:
- `TEST_IDENTITY_MFA_NOT_ENROLLED`
- `TEST_IDENTITY_EMAIL_NOT_CONFIRMED`
- `TEST_IDENTITY_SIGN_IN_REJECTED`
- `TEST_IDENTITY_TOTP_REJECTED`
- `TEST_IDENTITY_PASSWORD_CHANGE_REQUIRED`

## Security notes

- The job uses `permissions: contents: read`, has no `id-token` and holds no AWS credentials, so there is no AWS caller identity to check. Instead it pins the dev pool issuer, the central client name `wisestay-accounts-dev-web` and the four dev API hosts.
- The transport is HTTPS only and never follows redirects. Bearer tokens are sent only to the four API hosts. Presigned URLs must be HTTPS `*.amazonaws.com`.
- Secrets reach the process only through `env`. Dispatch inputs are passed through `env` too, never interpolated into the script.

## Local verification

`PYTHONPATH=src:. python3 -m unittest tests.test_dev_integration -v` runs the suite with no network. It uses:
- a stub Cognito SRP server (the server half of SRP-6a plus TOTP)
- the real Home Scanner router in-process (`tests/fakes_wave2.Harness`)
- stateful stubs for Object Scanner, Composer and Finder

It covers RFC 6238/4226 vectors, the SRP group and key agreement, route-table drift against the v0.4 fixtures, every blocked reason and the workflow shape. Not verifiable locally: the live Cognito SRP exchange, the public Account Centre config route, and the deployed services.
