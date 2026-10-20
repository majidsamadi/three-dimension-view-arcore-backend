# Home Scanner application stack (`infra/application/`)

Status: component-tested (synthetic data only). Dev deploy pipeline configured: implemented and locally verified (`terraform fmt -check`, `validate` after `init -backend=false`, mocked `terraform test`). It has not run against AWS yet; nothing is deployed until a deployment receipt exists (see "Wave 3 deployment").

Follows the `wisestay-infrastructure` application-stack conventions (plan X.10, Q15):

- Terraform `= 1.15.8`, `hashicorp/aws = 6.57.1`, partial S3 backend (`backend.hcl.example`, state key `wisestay/dev/three-dimension-view-arcore-backend/application.tfstate`).
- Account guard in both forms: `provider.allowed_account_ids = ["511831442607"]`, a `check "approved_account"` block and a `terraform_data.guard` precondition that every resource depends on. `expected_account_id`, `region` and `environment` are validated to `511831442607`, `ap-southeast-1` and `dev`.
- Default tags: Project, CostAllocation `wisestay-dev-3d`, Repository, Environment, Component `home-scanner`, ManagedBy.

| File | Resources |
|---|---|
| `storage.tf` | Private bucket `wisestay-dev-home-scanner-assets-511831442607`: BucketOwnerEnforced, all public access blocked, AES256, versioning off, lifecycle (abort multipart 1 d, `staging/` 7 d, `rejected/` 30 d), CORS PUT/GET/HEAD from `var.web_origin` only, TLS-only bucket policy |
| `table.tf` | `wisestay-dev-home-scanner`: on-demand, `pk`/`sk`, GSI `gsi1`, TTL `ttl_epoch`, SSE on. PITR off: the table holds synthetic dev data only |
| `compute.tf` | Runtime role `/wisestay/3d/dev/wisestay-dev-home-scanner-runtime` with the INFRA-owned permissions boundary `wisestay-dev-home-scanner-runtime-boundary`, least-privilege inline policy (table + index, bucket objects, `ListBucket`, own log group; the SSM statement only when a Resvanta parameter is configured), log group (14 d), `python3.13` arm64 function, 512 MB, 28 s, reserved concurrency 5 |
| `api.tf` | Regional REST API, `{proxy+}` ANY → AWS_PROXY, stage `dev`, throttling 10 rps / burst 20, ACM certificate (DNS), custom domain `var.api_hostname` (TLS 1.2), base-path mapping with no base path, Route 53 alias in zone `Z03297312TXBV0HYHORFM` (`wizestay.com`) |
| `versions.tf` | Providers, account guard and `data "aws_cognito_user_pool_clients"`: the accepted client id is the one client named `wisestay-accounts-dev-web` in pool `ap-southeast-1_RbRHXUipk` (exactly one match required) |
| `outputs.tf` | `api_root`, `function_name`, `rest_api_id`, `table_name`, `bucket_name` |
| `tests/stack.tftest.hcl` | `mock_provider "aws"` tests: contract names, runtime path and boundary, reserved concurrency 5, throttles 10/20, CORS origin, D7 client selection, no SSM grant or env var without a parameter (D8) |

Expected values (committed in `deployment/dev.config.json`): `api_hostname = "home-scanner.dev.wizestay.com"`, `web_origin = "https://home-scanner.wizestay.com"`, `resvanta_credential_parameter = ""`. `lambda_package_path` / `lambda_package_sha256_b64` come from `python3 tools/build_lambda.py`.

## Security note

API Gateway uses `authorization = "NONE"`. Authentication happens inside the Lambda: every route requires a central WiseStay access token, verified by `CentralJwtIdentityVerifier` (RS256 against the central Cognito JWKS, issuer, `token_use = access`, `client_id`, expiry). The REST endpoint is publicly reachable, throttled at 10/20 rps and capped at 5 concurrent executions. There is no online token revocation check: tokens are honoured until `exp`.

Resvanta stays fail-closed (Q14, D8). No `rv1` machine credential exists yet, so `resvanta_credential_parameter` is `""`: Terraform grants no SSM read, the function gets no `RESVANTA_CREDENTIAL_PARAMETER`, and the backend composes `UnconfiguredPropertyReference`. Capture admission (H01) therefore answers `property_not_usable`/`dependency_unavailable` in dev. When an operator later creates the SecureString out of band, setting its name adds `ssm:GetParameter` on that exact ARN only; Terraform never stores the value.

## Wave 3 deployment

Pipeline: the `deploy` job of `.github/workflows/ci.yml`. It runs only on a push to `main` of `majidsamadi/three-dimension-view-arcore-backend` (or a `workflow_dispatch` with `deploy: true` on `main`), after the `boundary` and `terraform` jobs pass. `deployment/deploy.py` then runs these steps in order:

1. `deployment/activation.json` must be enabled with approval `owner-3d-dev-deployment-2026-10-20`. Otherwise the result is `held` (`ACTIVATION_DISABLED`).
2. The run must be on `refs/heads/main` and `GITHUB_SHA` must equal the current main. This is checked before credentials are used and again just before apply.
3. GitHub OIDC is the only credential. `configure-aws-credentials` sets `allowed-account-ids: '511831442607'`. Both the workflow and `deploy.py` require caller account `511831442607` and the session prefix `arn:aws:sts::511831442607:assumed-role/wisestay-dev-home-scanner-deploy/` before `terraform init`.
4. Lambda account concurrency must keep at least 100 unreserved executions after this function reserves 5. Otherwise the result is `held` (`ACCOUNT_CONCURRENCY_FLOOR`). Fixing that means changing Q09, which needs the owner; it is never relaxed automatically.
5. `init` uses remote state `wisestay-state-511831442607-ap-southeast-1`, key `wisestay/dev/three-dimension-view-arcore-backend/application.tfstate`, the state KMS key and the S3 lockfile. Then `plan -out` runs and the saved plan is admitted in-process. Only creates, updates and no-ops of the frozen resource types with the contract names pass. A REST API deployment is the only resource that may be replaced. Any delete, foreign name, module or unexpected type is refused.
6. `apply` runs exactly the saved plan. `deploy.py` then checks the outputs, the deployed `CodeSha256` against the built package, and the reserved concurrency.
7. Smoke test: an unauthenticated `GET https://home-scanner.dev.wizestay.com/api/v1/home-scenes` (H07, token-protected) must answer `401` with `application/problem+json`. It retries every 20 s for up to 15 min to allow for DNS and certificate propagation. Any `2xx` fails the run at once.
8. The receipt `dist/deployment-receipt.json` (`wisestay.3d.deployment-receipt.v1`) is uploaded as artifact `deployment-receipt-<sha>` for 30 days. It holds the caller ARN, account, state key, plan counts per type (never values), package digest, function `LastModified`, unreserved concurrency before, the smoke result, and `result` (`deployed`/`held`/`failed`). Failures carry a closed label and at most four denied IAM action names. Provider output, plans and tfvars stay in a private temporary directory that is removed.

IAM scope: the deploy role, its two managed policies and the runtime permissions boundary are owned by `wisestay-infrastructure` `applications/three-d-dev` (owner bootstrap, never CI). This repository cannot widen them. Everything here is request-driven and idles to zero: Lambda (no provisioned concurrency, no warmers), REST API, DynamoDB on demand and S3. There is no NAT, ALB or GPU.

Rollback: revert the merge on `main`. The next main run plans and applies the previous configuration. Never restore, edit or import state by hand; a state problem is reported, not repaired locally.

Status: component-tested until a green deploy run, its receipt with `result: "deployed"` and a passing smoke all exist. Only then may docs say the stack is deployed to dev.

## Not in this stack

Website bucket and distribution, the Q09 budget `wisestay-dev-3d-monthly`, the deploy role and the runtime boundary are all in `wisestay-infrastructure` `applications/three-d-dev`.

## Local verification

```sh
TF=/tmp/wisestay-tf-1.15.8/terraform
export TF_PLUGIN_CACHE_DIR=/tmp/wisestay-tf-plugin-cache
"$TF" -chdir=infra/application fmt -check -recursive
"$TF" -chdir=infra/application init -backend=false -input=false -lockfile=readonly
"$TF" -chdir=infra/application validate -no-color
"$TF" -chdir=infra/application test -no-color   # mock_provider only, no AWS calls
```

Never run `plan`, `apply`, `import` or `state`, or `init` with a backend, from a workstation.
