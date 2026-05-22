variable "project_name" {
  type = string
}

variable "aws_account_id" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "github_repo" {
  type    = string
  default = ""
}

variable "github_actions_enabled" {
  type    = bool
  default = false
}

variable "sns_topic_arn" {
  type    = string
  default = ""
}

variable "s3_bucket_arn" {
  type = string
}

variable "ecr_repository_arn" {
  type = string
}
