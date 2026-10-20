locals {
  account_id    = "511831442607"
  component     = "home-scanner"
  name          = "wisestay-${var.environment}-${local.component}"
  bucket_name   = "wisestay-${var.environment}-${local.component}-assets-${local.account_id}"
  table_name    = local.name
  function_name = "${local.name}-api"
  log_group     = "/aws/lambda/${local.function_name}"
  handler       = "wisestay_home_backend.entrypoints.lambda_handler.handler"
  ssm_parameter = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${var.resvanta_credential_parameter}"
}
