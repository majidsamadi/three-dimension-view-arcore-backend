# Home Scanner application stack (plan X.10, Q15). Planned and applied only by
# deployment/deploy.py inside the guarded ci.yml deploy job (GitHub OIDC,
# account 511831442607); locally it is limited to fmt, validate and test.
terraform {
  required_version = "= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.57.1"
    }
  }

  # Partial configuration: see backend.hcl.example.
  backend "s3" {}
}

provider "aws" {
  region              = var.region
  allowed_account_ids = ["511831442607"]

  default_tags {
    tags = {
      Project        = "WiseStay"
      CostAllocation = "wisestay-dev-3d"
      Repository     = "majidsamadi/three-dimension-view-arcore-backend"
      Environment    = var.environment
      Component      = "home-scanner"
      ManagedBy      = "Terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

# D7: the central Account Centre client, discovered in the shared pool by exact name.
data "aws_cognito_user_pool_clients" "central" {
  user_pool_id = local.user_pool_id
}

# Account guard, both forms (wisestay-infrastructure application-stack convention).
check "approved_account" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == "511831442607"
    error_message = "This stack may only run against WiseStay account 511831442607."
  }
}

resource "terraform_data" "guard" {
  input = var.expected_account_id

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "511831442607" && data.aws_caller_identity.current.account_id == var.expected_account_id
      error_message = "Caller account must be 511831442607 and equal expected_account_id."
    }
    precondition {
      condition     = length(local.central_client_ids) == 1
      error_message = "Exactly one wisestay-accounts-dev-web client must exist in the central user pool."
    }
  }
}
