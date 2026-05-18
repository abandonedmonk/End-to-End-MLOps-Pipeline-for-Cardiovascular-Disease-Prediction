# Remote state backend — uncomment AFTER creating the S3 bucket and DynamoDB table.
# First run: use local state (default). Then migrate with:
#   terraform init -backend-config=backend.hcl

# terraform {
#   backend "s3" {
#     bucket         = "heart-disease-mlops-695074562426-tfstate"
#     key            = "terraform.tfstate"
#     region         = "us-east-1"
#     encrypt        = true
#     dynamodb_table = "heart-disease-mlops-tflock"
#   }
# }
