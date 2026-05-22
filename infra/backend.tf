terraform {
  backend "s3" {
    bucket         = "heart-disease-mlops-695074562426-tfstate"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "heart-disease-mlops-tflock"
  }
}
