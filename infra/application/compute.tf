data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Runtime role (wave 3 plan §3.2): fixed path and the INFRA-owned permissions
# boundary, so the deploy role can only create it inside that boundary.
resource "aws_iam_role" "api" {
  name                 = local.runtime_role
  path                 = "/wisestay/3d/dev/"
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = var.runtime_permissions_boundary_arn
  depends_on           = [terraform_data.guard]
}

# Least privilege (plan X.10): the table and its index, objects in the asset
# bucket, the single Resvanta credential parameter (only when configured, D8)
# and this function's logs.
data "aws_iam_policy_document" "api" {
  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:ConditionCheckItem",
      "dynamodb:TransactWriteItems",
    ]
    resources = [aws_dynamodb_table.service.arn, "${aws_dynamodb_table.service.arn}/index/gsi1"]
  }

  statement {
    sid       = "AssetObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:GetObjectAttributes"]
    resources = ["${aws_s3_bucket.assets.arn}/*"]
  }

  statement {
    sid       = "AssetBucketList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.assets.arn]
  }

  dynamic "statement" {
    for_each = local.resvanta_configured ? [local.ssm_parameter] : []
    content {
      sid       = "ResvantaCredential"
      actions   = ["ssm:GetParameter"]
      resources = [statement.value]
    }
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name       = "${local.function_name}-least-privilege"
  role       = aws_iam_role.api.id
  policy     = data.aws_iam_policy_document.api.json
  depends_on = [terraform_data.guard]
}

resource "aws_cloudwatch_log_group" "api" {
  name              = local.log_group
  retention_in_days = 14
  depends_on        = [terraform_data.guard]
}

resource "aws_lambda_function" "api" {
  function_name                  = local.function_name
  role                           = aws_iam_role.api.arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"]
  handler                        = local.handler
  memory_size                    = 512
  timeout                        = 28
  reserved_concurrent_executions = 5
  filename                       = var.lambda_package_path
  source_code_hash               = var.lambda_package_sha256_b64

  environment {
    variables = merge(
      {
        WISESTAY_ENVIRONMENT = var.environment
        TABLE_NAME           = aws_dynamodb_table.service.name
        ASSET_BUCKET         = aws_s3_bucket.assets.bucket
        CENTRAL_ISSUER       = var.central_issuer
        CENTRAL_CLIENT_ID    = local.central_client_id
        RESVANTA_API_ROOT    = var.resvanta_api_root
      },
      # Without the parameter the backend composes UnconfiguredPropertyReference (Q14).
      local.resvanta_configured ? { RESVANTA_CREDENTIAL_PARAMETER = var.resvanta_credential_parameter } : {},
    )
  }

  depends_on = [terraform_data.guard, aws_iam_role_policy.api, aws_cloudwatch_log_group.api]
}
