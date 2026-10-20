# Credential-free stack tests (wave 3 plan §6.2). Every AWS call is mocked:
# `terraform test` here never reaches an AWS endpoint.
mock_provider "aws" {
  override_during = plan

  # Policy documents render locally; the mock only needs syntactically valid JSON.
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:ap-southeast-1:511831442607:certificate/00000000-0000-0000-0000-000000000000"
      domain_validation_options = [{
        domain_name           = "home-scanner.dev.wizestay.com"
        resource_record_name  = "_abc.home-scanner.dev.wizestay.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_def.acm-validations.aws."
      }]
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::511831442607:role/wisestay/3d/dev/wisestay-dev-home-scanner-runtime"
    }
  }
  mock_resource "aws_lambda_function" {
    defaults = {
      arn        = "arn:aws:lambda:ap-southeast-1:511831442607:function:wisestay-dev-home-scanner-api"
      invoke_arn = "arn:aws:apigateway:ap-southeast-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ap-southeast-1:511831442607:function:wisestay-dev-home-scanner-api/invocations"
    }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:ap-southeast-1:511831442607:log-group:/aws/lambda/wisestay-dev-home-scanner-api"
    }
  }
  mock_resource "aws_dynamodb_table" {
    defaults = {
      arn = "arn:aws:dynamodb:ap-southeast-1:511831442607:table/wisestay-dev-home-scanner"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::wisestay-dev-home-scanner-assets-511831442607"
      id  = "wisestay-dev-home-scanner-assets-511831442607"
    }
  }
  mock_resource "aws_api_gateway_rest_api" {
    defaults = {
      execution_arn = "arn:aws:execute-api:ap-southeast-1:511831442607:abcdef1234"
    }
  }
  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "511831442607"
      arn        = "arn:aws:sts::511831442607:assumed-role/wisestay-dev-home-scanner-deploy/test"
    }
  }
  override_data {
    target = data.aws_cognito_user_pool_clients.central
    values = {
      client_ids   = ["1example0000000000000000000", "2othercl1ent00000000000000"]
      client_names = ["wisestay-accounts-dev-web", "wisestay-other-client"]
    }
  }
}

variables {
  expected_account_id       = "511831442607"
  region                    = "ap-southeast-1"
  environment               = "dev"
  lambda_package_path       = "dist/home-scanner-lambda.zip"
  lambda_package_sha256_b64 = "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
  web_origin                = "https://home-scanner.wizestay.com"
  api_hostname              = "home-scanner.dev.wizestay.com"
  resvanta_api_root         = "https://1noccvrfkk.execute-api.ap-southeast-1.amazonaws.com/v1"
}

run "contract_names_limits_and_tags" {
  command = plan

  assert {
    condition     = aws_lambda_function.api.function_name == "wisestay-dev-home-scanner-api"
    error_message = "Function name must follow the shared naming contract."
  }
  assert {
    condition     = aws_lambda_function.api.reserved_concurrent_executions == 5
    error_message = "Reserved concurrency must be 5 (Q09)."
  }
  assert {
    condition     = aws_lambda_function.api.runtime == "python3.13" && aws_lambda_function.api.architectures == tolist(["arm64"]) && aws_lambda_function.api.memory_size == 512 && aws_lambda_function.api.timeout == 28
    error_message = "Lambda runtime, architecture, memory and timeout must match the contract."
  }
  assert {
    condition     = aws_dynamodb_table.service.name == "wisestay-dev-home-scanner" && aws_dynamodb_table.service.billing_mode == "PAY_PER_REQUEST"
    error_message = "Table must be the on-demand contract table."
  }
  assert {
    condition     = aws_s3_bucket.assets.bucket == "wisestay-dev-home-scanner-assets-511831442607"
    error_message = "Asset bucket name must follow the contract."
  }
  assert {
    condition     = aws_cloudwatch_log_group.api.name == "/aws/lambda/wisestay-dev-home-scanner-api" && aws_cloudwatch_log_group.api.retention_in_days == 14
    error_message = "Log group must be the function log group with 14-day retention."
  }
  assert {
    condition     = aws_api_gateway_rest_api.api.name == "wisestay-dev-home-scanner-api" && aws_api_gateway_stage.dev.stage_name == "dev"
    error_message = "REST API and stage names must follow the contract."
  }
  assert {
    condition     = aws_api_gateway_method_settings.all.method_path == "*/*" && aws_api_gateway_method_settings.all.settings[0].throttling_rate_limit == 10 && aws_api_gateway_method_settings.all.settings[0].throttling_burst_limit == 20
    error_message = "Stage throttling must be 10 rps / burst 20 for every method (Q09)."
  }
  assert {
    condition     = aws_api_gateway_domain_name.api.domain_name == "home-scanner.dev.wizestay.com" && aws_acm_certificate.api.domain_name == "home-scanner.dev.wizestay.com"
    error_message = "Custom domain and certificate must be the contract API host."
  }
  assert {
    condition     = aws_route53_record.api.zone_id == "Z03297312TXBV0HYHORFM" && aws_route53_record.api.type == "A"
    error_message = "The API alias must live in the wizestay.com zone."
  }
  assert {
    condition     = aws_iam_role.api.name == "wisestay-dev-home-scanner-runtime" && aws_iam_role.api.path == "/wisestay/3d/dev/"
    error_message = "Runtime role name and path must follow the contract."
  }
  assert {
    condition     = aws_iam_role.api.permissions_boundary == "arn:aws:iam::511831442607:policy/wisestay/3d/dev/wisestay-dev-home-scanner-runtime-boundary"
    error_message = "Runtime role must carry the INFRA-owned permissions boundary."
  }
  assert {
    condition     = [for rule in aws_s3_bucket_cors_configuration.assets.cors_rule : rule.allowed_origins] == [toset(["https://home-scanner.wizestay.com"])]
    error_message = "Bucket CORS must allow only the paired web origin."
  }
  assert {
    condition     = aws_lambda_function.api.environment[0].variables["CENTRAL_CLIENT_ID"] == "1example0000000000000000000"
    error_message = "The central client id must be resolved by exact name (D7)."
  }
  assert {
    condition     = aws_lambda_function.api.environment[0].variables["CENTRAL_ISSUER"] == "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RbRHXUipk"
    error_message = "The issuer must default to the central pool."
  }
  assert {
    condition     = !contains(keys(aws_lambda_function.api.environment[0].variables), "RESVANTA_CREDENTIAL_PARAMETER")
    error_message = "Without a credential parameter the env var must be omitted (D8)."
  }
  assert {
    condition     = !contains([for statement in data.aws_iam_policy_document.api.statement : statement.sid], "ResvantaCredential")
    error_message = "Without a credential parameter no SSM statement may be granted (D8)."
  }
  assert {
    condition     = output.function_name == "wisestay-dev-home-scanner-api" && output.api_root == "https://home-scanner.dev.wizestay.com/api/v1"
    error_message = "Outputs must expose the contract function name and API root."
  }
}

run "resvanta_parameter_adds_exact_grant" {
  command = plan

  variables {
    resvanta_credential_parameter = "/wisestay/dev/3d/home-scanner/resvanta-rv1"
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables["RESVANTA_CREDENTIAL_PARAMETER"] == "/wisestay/dev/3d/home-scanner/resvanta-rv1"
    error_message = "A configured parameter must reach the function environment."
  }
  assert {
    condition     = contains([for statement in data.aws_iam_policy_document.api.statement : statement.sid], "ResvantaCredential")
    error_message = "A configured parameter must add the single SSM grant."
  }
}

run "client_must_match_exactly_once" {
  command = plan

  override_data {
    target = data.aws_cognito_user_pool_clients.central
    values = {
      client_ids   = ["2othercl1ent00000000000000"]
      client_names = ["wisestay-other-client"]
    }
  }

  expect_failures = [terraform_data.guard]
}

run "rejects_other_boundary" {
  command = plan

  variables {
    runtime_permissions_boundary_arn = "arn:aws:iam::511831442607:policy/other"
  }

  expect_failures = [var.runtime_permissions_boundary_arn]
}
