variable "expected_account_id" {
  type        = string
  description = "Must be the WiseStay account 511831442607."

  validation {
    condition     = var.expected_account_id == "511831442607"
    error_message = "expected_account_id must be 511831442607."
  }
}

variable "region" {
  type        = string
  description = "Deployment region."

  validation {
    condition     = var.region == "ap-southeast-1"
    error_message = "region must be ap-southeast-1."
  }
}

variable "environment" {
  type        = string
  description = "Environment name; only dev exists in wave 2."

  validation {
    condition     = var.environment == "dev"
    error_message = "environment must be dev."
  }
}

variable "lambda_package_path" {
  type        = string
  description = "Path to dist/home-scanner-lambda.zip built by tools/build_lambda.py."

  validation {
    condition     = can(regex("\\.zip$", var.lambda_package_path))
    error_message = "lambda_package_path must point at a .zip archive."
  }
}

variable "lambda_package_sha256_b64" {
  type        = string
  description = "Base64 sha256 printed by tools/build_lambda.py."

  validation {
    condition     = can(regex("^[A-Za-z0-9+/]{43}=$", var.lambda_package_sha256_b64))
    error_message = "lambda_package_sha256_b64 must be a base64 sha256 digest."
  }
}

variable "central_issuer" {
  type        = string
  description = "Central WiseStay Cognito issuer, https://cognito-idp.ap-southeast-1.amazonaws.com/<pool id>."

  validation {
    condition     = can(regex("^https://cognito-idp\\.ap-southeast-1\\.amazonaws\\.com/ap-southeast-1_[A-Za-z0-9]+$", var.central_issuer))
    error_message = "central_issuer must be an ap-southeast-1 Cognito user pool issuer URL."
  }
}

variable "central_client_id" {
  type        = string
  description = "User Management app client id whose access tokens are accepted."

  validation {
    condition     = can(regex("^[A-Za-z0-9]{1,128}$", var.central_client_id))
    error_message = "central_client_id must be a Cognito app client id."
  }
}

variable "web_origin" {
  type        = string
  description = "Home Scanner web origin allowed by the asset bucket CORS rule (Q15)."

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+$", var.web_origin))
    error_message = "web_origin must be an https origin without a path."
  }
}

variable "api_hostname" {
  type        = string
  description = "Custom API hostname (Q15), for example home-scanner.dev.wizestay.com."

  validation {
    condition     = can(regex("^[a-z0-9-]+\\.dev\\.wizestay\\.com$", var.api_hostname))
    error_message = "api_hostname must be a dev.wizestay.com hostname."
  }
}

variable "hosted_zone_name" {
  type        = string
  description = "Public Route 53 zone holding api_hostname."
  default     = "wizestay.com"

  validation {
    condition     = var.hosted_zone_name == "wizestay.com"
    error_message = "hosted_zone_name must be wizestay.com."
  }
}

variable "resvanta_api_root" {
  type        = string
  description = "Resvanta API root (IDM WEB_APIS[\"resvanta\"])."

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+(/[A-Za-z0-9._-]+)*$", var.resvanta_api_root))
    error_message = "resvanta_api_root must be an https URL."
  }
}

variable "resvanta_credential_parameter" {
  type        = string
  description = "Name of the SSM SecureString holding the rv1 machine credential. Created out of band; Terraform never stores the value."

  validation {
    condition     = can(regex("^/[A-Za-z0-9/_.-]+$", var.resvanta_credential_parameter))
    error_message = "resvanta_credential_parameter must be an absolute SSM parameter name."
  }
}
