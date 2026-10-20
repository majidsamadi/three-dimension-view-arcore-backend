data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  depends_on         = [terraform_data.guard]
}

# Least privilege (plan X.10): the table and its index, objects in the asset
# bucket, the single Resvanta credential parameter and this function's logs.
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

  statement {
    sid       = "ResvantaCredential"
    actions   = ["ssm:GetParameter"]
    resources = [local.ssm_parameter]
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
    variables = {
      WISESTAY_ENVIRONMENT          = var.environment
      TABLE_NAME                    = aws_dynamodb_table.service.name
      ASSET_BUCKET                  = aws_s3_bucket.assets.bucket
      CENTRAL_ISSUER                = var.central_issuer
      CENTRAL_CLIENT_ID             = var.central_client_id
      RESVANTA_API_ROOT             = var.resvanta_api_root
      RESVANTA_CREDENTIAL_PARAMETER = var.resvanta_credential_parameter
    }
  }

  depends_on = [terraform_data.guard, aws_iam_role_policy.api, aws_cloudwatch_log_group.api]
}
