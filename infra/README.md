# Home Scanner application stack (`infra/application/`)

Status: component-tested (synthetic data only). Validated locally with `terraform fmt -check` and `terraform validate` after `init -backend=false`. Never planned or applied; nothing is deployed.

Follows the `wisestay-infrastructure` application-stack conventions (plan X.10, Q15):

- Terraform `= 1.15.8`, `hashicorp/aws = 6.57.1`, partial S3 backend (`backend.hcl.example`, state key `wisestay/dev/three-dimension-view-arcore-backend/application.tfstate`).
- Account guard in both forms: `provider.allowed_account_ids = ["511831442607"]`, a `check "approved_account"` block and a `terraform_data.guard` precondition that every resource depends on. `expected_account_id`, `region` and `environment` are validated to `511831442607`, `ap-southeast-1` and `dev`.
- Default tags: Project, CostAllocation `wisestay-dev-3d`, Repository, Environment, Component `home-scanner`, ManagedBy.

| File | Resources |
|---|---|
| `storage.tf` | Private bucket `wisestay-dev-home-scanner-assets-511831442607`: BucketOwnerEnforced, all public access blocked, AES256, versioning off, lifecycle (abort multipart 1 d, `staging/` 7 d, `rejected/` 30 d), CORS PUT/GET/HEAD from `var.web_origin` only, TLS-only bucket policy |
| `table.tf` | `wisestay-dev-home-scanner`: on-demand, `pk`/`sk`, GSI `gsi1`, TTL `ttl_epoch`, SSE on. PITR off: the table holds synthetic dev data only in wave 2 |
| `compute.tf` | Lambda role and least-privilege policy (table + index, bucket objects, `ListBucket`, one SSM parameter, own log group), log group (14 d), `python3.13` arm64 function, 512 MB, 28 s, reserved concurrency 5 |
| `api.tf` | Regional REST API, `{proxy+}` ANY → AWS_PROXY, stage `dev`, throttling 10 rps / burst 20, ACM certificate (DNS), custom domain `var.api_hostname` (TLS 1.2), base-path mapping with no base path, Route 53 alias |
| `outputs.tf` | `api_root`, `rest_api_id`, `table_name`, `bucket_name` |

Expected values: `api_hostname = "home-scanner.dev.wizestay.com"`, `web_origin = "https://home-scanner.wizestay.com"`. `lambda_package_path` / `lambda_package_sha256_b64` come from `python3 tools/build_lambda.py`.

## Security note

API Gateway uses `authorization = "NONE"`. Authentication happens inside the Lambda: every route requires a central WiseStay access token, verified by `CentralJwtIdentityVerifier` (RS256 against the central Cognito JWKS, issuer, `token_use = access`, `client_id`, expiry). The REST endpoint is publicly reachable, throttled at 10/20 rps and capped at 5 concurrent executions. There is no online token revocation check: tokens are honoured until `exp`.

The Resvanta `rv1` machine credential lives in the SSM SecureString named by `var.resvanta_credential_parameter`. The operator creates it out of band; Terraform only grants `ssm:GetParameter` on that exact ARN and never stores the value.

## Not in this stack (INF follow-ups)

Website bucket and distribution (`wisestay-infrastructure` `applications/websites`), the USD 25 budget (foundation module), CI OIDC deploy roles (foundation `deployment_repositories`).

## Local verification

```sh
TF=/tmp/wisestay-tf-1.15.8/terraform
export TF_PLUGIN_CACHE_DIR=/tmp/wisestay-tf-plugin-cache
"$TF" -chdir=infra/application fmt -check -recursive
"$TF" -chdir=infra/application init -backend=false -input=false -lockfile=readonly
"$TF" -chdir=infra/application validate -no-color
```
