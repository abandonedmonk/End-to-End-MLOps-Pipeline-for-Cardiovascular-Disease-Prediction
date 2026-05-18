output "ec2_public_ip" {
  description = "Public IP of the EC2 instance (static via Elastic IP)"
  value       = module.ec2.public_ip
}

output "ec2_instance_id" {
  description = "EC2 instance ID"
  value       = module.ec2.instance_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.endpoint
}

output "s3_bucket_name" {
  description = "S3 bucket name for artifacts and data"
  value       = module.s3.bucket_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for Docker images"
  value       = module.ecr.repository_url
}

output "mlflow_uri" {
  description = "MLflow tracking URI"
  value       = "http://${module.ec2.public_ip}:${var.mlflow_port}"
}

output "api_url" {
  description = "FastAPI inference endpoint"
  value       = "http://${module.ec2.public_ip}:${var.api_port}"
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC (empty if github_repo not set)"
  value       = module.iam.github_actions_role_arn
}
