# 01 — Terraform on AWS

## What We Did

Provisioned 28 AWS resources using Terraform with a modular structure:

```
infra/
├── main.tf              # Wires all modules, uses templatefile() for user_data
├── variables.tf         # 12 input variables (region, IPs, passwords, ports)
├── outputs.tf           # 7 outputs (IPs, endpoints, URIs)
├── providers.tf         # AWS provider pinned to 5.50.0
├── backend.tf           # S3 remote state (commented until bootstrap)
├── user_data.sh.tftpl   # EC2 bootstrap script (template, not plain bash)
├── terraform.tfvars     # Your real values (NEVER commit this)
└── modules/
    ├── vpc/   # Custom VPC + 2 public subnets + IGW + route tables
    ├── ec2/   # Instance + security group + EIP + key pair
    ├── rds/   # PostgreSQL 15.7 + security group (EC2-only access)
    ├── s3/    # Bucket + versioning + encryption + lifecycle rules
    ├── ecr/   # Private Docker registry + keep-last-5 policy
    └── iam/   # EC2 instance profile + GitHub OIDC role
```

## Why Terraform (Not CDK or CloudFormation)

| Aspect | Terraform | CloudFormation | CDK |
|--------|-----------|---------------|-----|
| Language | HCL (declarative) | YAML/JSON | TypeScript/Python |
| Cloud | Multi-cloud | AWS only | AWS only |
| State | External (.tfstate) | Managed by AWS | Managed by AWS |
| Community | Largest | AWS-specific | Growing |
| Learning curve | Moderate | Steep (YAML verbosity) | Requires programming |
| Zoomcamp alignment | Taught in course | Not covered | Not covered |

**Our choice**: Terraform — cloud-agnostic, matches the MLOps Zoomcamp curriculum, HCL is more readable than CloudFormation YAML, and the state file gives us a plan/apply workflow.

## Theory: How Terraform Works

### The Core Loop

```
terraform init    → Download providers, initialize backend, resolve modules
terraform plan    → Read state → compare with config → show diff
terraform apply   → Execute the diff → update state → provision resources
terraform destroy → Read state → plan deletion → remove all resources
```

### State Management

Terraform tracks everything in `terraform.tfstate`. This file maps your `.tf` config to real AWS resources.

**Local state** (what we have now):
- Stored in `infra/terraform.tfstate`
- Works for solo dev, but risky (no locking, no history)
- If you lose the file, Terraform loses track of your resources

**Remote state** (what we should move to):
```hcl
terraform {
  backend "s3" {
    bucket         = "heart-disease-mlops-695074562426-tfstate"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "heart-disease-mlops-tflock"  # State locking
  }
}
```

Why remote state matters:
- **Locking**: Prevents two people from applying simultaneously (DynamoDB lock)
- **Encryption**: S3 server-side encryption protects secrets in state
- **History**: S3 versioning lets you rollback state
- **Team access**: Shared state file instead of local copies

### Provider Versioning

We pin `aws = "5.50.0"` instead of `~> 5.0`. Here's why:

- `~> 5.0` resolves to the latest 5.x (currently 5.100.0)
- The AWS provider binary is ~500 MB — downloading it every `terraform init` times out on slow connections
- Pinning to a specific version makes builds reproducible and fast
- The `.terraform.lock.hcl` file records the exact version and hashes

### Module Design Principles

1. **Each module owns one resource type** — ec2/ only creates EC2-related things
2. **Modules communicate via variables and outputs** — no cross-module references inside modules
3. **The root main.tf is the orchestrator** — it passes outputs from one module as inputs to another
4. **Dependency order matters** — IAM must exist before EC2 (instance profile), VPC before everything

### The `templatefile()` Function

```hcl
locals {
  user_data_rendered = templatefile(
    "${path.module}/user_data.sh.tftpl",
    {
      rds_endpoint   = module.rds.endpoint
      rds_password   = var.rds_password
      s3_bucket_name = module.s3.bucket_name
    }
  )
}
```

This injects Terraform variables into a bash script **at plan time**, not at runtime. The `${rds_password}` in the template becomes the actual password value. This means:
- The rendered script is stored in Terraform state (sensitive values are marked)
- Changing any template variable recreates the EC2 instance's user_data
- Use `$$` to escape literal `$` in bash variables inside the template (e.g., `$${2:-latest}`)

## How to Debug

### `terraform plan` Shows Wrong Resources

```bash
terraform plan -var-file=terraform.tfvars -out=tfplan
terraform show tfplan   # Inspect the full plan
```

### State Drift (Someone Changed AWS Console)

```bash
terraform refresh      # Re-reads all resource states from AWS
terraform plan         # Will now show the drift as changes
```

### Resource Creation Fails

Common failures and fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| `InvalidParameterValue` (RDS password) | Password contains `@`, `/`, `"`, or space | Use only alphanumeric + `!#$%^&*()` |
| `no matching EC2 VPC found` | Account has no default VPC | Add a VPC module (we had to do this) |
| `InsufficientInstanceCapacity` | t2.micro unavailable in that AZ | Change AZ or use t3.micro |
| `IAM instance profile not found` | Race condition — IAM propagation delay | Add `depends_on = [module.iam]` |
| `aws_subnet_ids not found` | Deprecated data source in provider 5.x | Use `aws_subnets` instead |

### Fixing User Data Without Recreating EC2

When user_data has a bug, you can either:

1. **Fix in-place** (faster, what we did): SSH in, fix the script manually, restart services
2. **Taint and recreate** (cleaner): `terraform taint module.ec2.aws_instance.main && terraform apply`

### Importing Existing Resources

If you create something in the AWS Console and want Terraform to manage it:

```bash
terraform import module.s3.aws_s3_bucket.main heart-disease-mlops-695074562426
```

### Removing Resources From State (Without Deleting)

```bash
terraform state rm module.ec2.aws_instance.main
# Resource still exists in AWS, but Terraform no longer tracks it
```

## Practical Tips

### Always Run Plan Before Apply

```bash
terraform plan -var-file=terraform.tfvars -out=tfplan
terraform apply tfplan
```

### Pin Provider Versions

```hcl
required_providers {
  aws = {
    source  = "hashicorp/aws"
    version = "5.50.0"  # Not ~> 5.0
  }
}
```

### Use `sensitive` for Secrets

```hcl
variable "rds_password" {
  type      = string
  sensitive = true  # Hides from plan output
}
```

Note: `sensitive` only hides from terminal output. The value is still in the state file. Use remote state with encryption for real security.

### Use `depends_on` for Cross-Module Dependencies

```hcl
module "ec2" {
  source     = "./modules/ec2"
  depends_on = [module.iam]  # IAM must be ready before EC2
}
```

Without this, Terraform might try to launch EC2 before the instance profile exists, getting an "IAM instance profile not found" error.

### Use `prevent_deletion` for Critical Resources

```hcl
resource "aws_db_instance" "main" {
  deletion_protection = true  # Prevents accidental `terraform destroy`
}
```

We set this to `false` for development, but production should use `true`.
