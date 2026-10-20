locals {
  account_id    = "511831442607"
  component     = "home-scanner"
  name          = "wisestay-${var.environment}-${local.component}"
  bucket_name   = "wisestay-${var.environment}-${local.component}-assets-${local.account_id}"
  table_name    = local.name
  function_name = "${local.name}-api"
  runtime_role  = "${local.name}-runtime"
  log_group     = "/aws/lambda/${local.function_name}"
  handler       = "wisestay_home_backend.entrypoints.lambda_handler.handler"

  # Shared naming contract (wave 3 plan §3.1): the wizestay.com zone holds the dev hosts.
  zone_id             = "Z03297312TXBV0HYHORFM"
  user_pool_id        = "ap-southeast-1_RbRHXUipk"
  central_client_name = "wisestay-accounts-dev-web"

  # D7: the accepted client id is resolved at plan time by exact name.
  central_client_ids = [
    for index, name in data.aws_cognito_user_pool_clients.central.client_names :
    data.aws_cognito_user_pool_clients.central.client_ids[index] if name == local.central_client_name
  ]
  # Exactly one match is enforced by the terraform_data.guard precondition.
  central_client_id = length(local.central_client_ids) == 1 ? local.central_client_ids[0] : ""

  # D8: no Resvanta credential parameter exists yet, so the grant and env var are omitted.
  resvanta_configured = var.resvanta_credential_parameter != ""
  ssm_parameter       = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${var.resvanta_credential_parameter}"
}
