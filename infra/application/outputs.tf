output "api_root" {
  description = "Home Scanner API root (Q15)."
  value       = "https://${var.api_hostname}/api/v1"
}

output "rest_api_id" {
  value = aws_api_gateway_rest_api.api.id
}

output "table_name" {
  value = aws_dynamodb_table.service.name
}

output "bucket_name" {
  value = aws_s3_bucket.assets.bucket
}
