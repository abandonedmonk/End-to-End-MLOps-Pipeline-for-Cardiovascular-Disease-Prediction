resource "aws_s3_bucket" "main" {
  bucket = var.bucket_name

  force_destroy = true  # Allows terraform destroy to delete non-empty buckets

  tags = {
    Name = var.bucket_name
  }
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "monitoring_reports" {
  bucket = aws_s3_bucket.main.id

  rule {
    id     = "expire-old-monitoring-reports"
    status = "Enabled"

    filter {
      prefix = "monitoring/reports/"
    }

    expiration {
      days = 90
    }
  }
}

data "aws_iam_policy_document" "ec2_s3_access" {
  statement {
    sid    = "EC2S3ReadWrite"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.aws_account_id}:root"]
    }

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.main.arn,
      "${aws_s3_bucket.main.arn}/*",
    ]
  }
}
