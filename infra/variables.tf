variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS account ID (used for S3 bucket naming and IAM policies)"
  type        = string
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "heart-disease-mlops"
}

variable "ec2_instance_type" {
  description = "EC2 instance type (t2.micro for free tier)"
  type        = string
  default     = "t2.micro"
}

variable "rds_instance_class" {
  description = "RDS instance class (db.t3.micro for free tier)"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_username" {
  description = "RDS master username"
  type        = string
  default     = "mlflowadmin"
}

variable "rds_password" {
  description = "RDS master password (store in terraform.tfvars, NEVER commit)"
  type        = string
  sensitive   = true
}

variable "rds_db_name" {
  description = "RDS database name for MLflow backend"
  type        = string
  default     = "mlflow"
}

variable "ssh_public_key" {
  description = "Your SSH public key for EC2 access"
  type        = string
}

variable "your_ip" {
  description = "Your public IP address (CIDR notation) for security group access"
  type        = string
}

variable "github_repo" {
  description = "GitHub repo in org/repo format for OIDC trust policy"
  type        = string
  default     = ""
}

variable "mlflow_port" {
  description = "Port for MLflow tracking server"
  type        = number
  default     = 5000
}

variable "api_port" {
  description = "Port for FastAPI inference server"
  type        = number
  default     = 8000
}

variable "prefect_api_url" {
  description = "Prefect API URL for the EC2 agent/worker"
  type        = string
  default     = ""
}

variable "prefect_api_key" {
  description = "Prefect API key for the EC2 agent/worker"
  type        = string
  default     = ""
  sensitive   = true
}

variable "drift_threshold" {
  description = "CloudWatch alarm threshold for data drift score"
  type        = number
  default     = 0.3
}
