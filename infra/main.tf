data "aws_caller_identity" "current" {}

module "vpc" {
  source      = "./modules/vpc"
  project_name = var.project_name
  aws_region   = var.aws_region
}

module "s3" {
  source         = "./modules/s3"
  bucket_name    = "${var.project_name}-${var.aws_account_id}"
  aws_account_id = var.aws_account_id
}

module "ecr" {
  source          = "./modules/ecr"
  repository_name = "${var.project_name}-api"
}

module "iam" {
  source             = "./modules/iam"
  project_name       = var.project_name
  aws_account_id     = var.aws_account_id
  aws_region         = var.aws_region
  github_repo        = var.github_repo
  s3_bucket_arn      = module.s3.bucket_arn
  ecr_repository_arn = module.ecr.repository_arn
}

module "ec2" {
  source                = "./modules/ec2"
  project_name          = var.project_name
  instance_type         = var.ec2_instance_type
  ssh_public_key        = var.ssh_public_key
  your_ip               = var.your_ip
  mlflow_port           = var.mlflow_port
  api_port              = var.api_port
  instance_profile_name = module.iam.ec2_instance_profile_name
  user_data_script      = local.user_data_rendered
  vpc_id                = module.vpc.vpc_id
  subnet_id             = module.vpc.subnet_ids[0]
  prefect_api_url = var.prefect_api_url
  prefect_api_key = var.prefect_api_key

  depends_on = [module.iam]
}

module "rds" {
  source                = "./modules/rds"
  identifier            = "${var.project_name}-db"
  db_name               = var.rds_db_name
  username              = var.rds_username
  password              = var.rds_password
  instance_class        = var.rds_instance_class
  ec2_security_group_id = module.ec2.security_group_id
  subnet_ids            = module.vpc.subnet_ids
  vpc_id                = module.vpc.vpc_id
}

module "monitoring" {
  source          = "./modules/monitoring"
  project_name    = var.project_name
  aws_region      = var.aws_region
  ec2_instance_id = module.ec2.instance_id
  drift_threshold = var.drift_threshold

  depends_on = [module.ec2]
}

locals {
  user_data_rendered = templatefile(
    "${path.module}/user_data.sh.tftpl",
    {
      rds_endpoint   = module.rds.endpoint
      rds_db_name    = var.rds_db_name
      rds_username   = var.rds_username
      rds_password   = var.rds_password
      s3_bucket_name = module.s3.bucket_name
      mlflow_port    = var.mlflow_port
      api_port       = var.api_port
      project_name   = var.project_name
      aws_region     = var.aws_region
      prefect_api_url = var.prefect_api_url
      prefect_api_key = var.prefect_api_key
    }
  )
}
