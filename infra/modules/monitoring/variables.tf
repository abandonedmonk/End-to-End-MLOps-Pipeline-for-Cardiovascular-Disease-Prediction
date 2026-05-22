variable "project_name" {
  description = "Project name used as prefix for monitoring resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region for CloudWatch resources"
  type        = string
}

variable "ec2_instance_id" {
  description = "EC2 instance ID monitored by the dashboard and CPU alarm"
  type        = string
}

variable "drift_threshold" {
  description = "Maximum acceptable share of drifted model features"
  type        = number
  default     = 0.3
}

variable "metric_namespace" {
  description = "CloudWatch namespace for application monitoring metrics"
  type        = string
  default     = "HeartDisease/Monitoring"
}
