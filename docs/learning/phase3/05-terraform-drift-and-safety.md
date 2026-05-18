# 05 — Terraform Drift, Safety, and the Lock File

## What We Did

1. Added `user_data_replace_on_change = false` to the EC2 module to prevent accidental instance rebuilds
2. Committed `.terraform.lock.hcl` to version control (removed from `.gitignore`)
3. Fixed the Prefect agent systemd service in the user_data template to include `PREFECT_API_URL` and `PREFECT_API_KEY` environment variables
4. Ran `terraform apply` to sync the state after template changes (update-in-place, no EC2 recreation)

## Why `user_data_replace_on_change = false`

### The Problem

Terraform tracks the `user_data` field as a hashed value in state. When the `user_data.sh.tftpl` template changes (even a single line), the hash changes. By default, this means Terraform would **replace** the EC2 instance — destroying and recreating it from scratch.

This is dangerous because:
- EC2 recreation means **5-10 minutes of downtime** (bootstrap, package install, service start)
- Any manually installed packages or configuration changes are lost
- The Elastic IP stays the same, but SSH host keys change
- Running containers are killed
- RDS may auto-stop during the downtime window

### The Fix

```hcl
resource "aws_instance" "main" {
  ami                    = data.aws_ami.ubuntu_2404.id
  instance_type          = var.instance_type
  user_data              = var.user_data_script
  user_data_replace_on_change = false  # KEY LINE
  ...
}
```

With this setting:
- `terraform plan` will show `user_data` as a changed attribute
- But the change is **update-in-place** — just the state's hash is updated
- The running EC2 instance is **not** recreated
- You must manually apply template changes (SSH in, run commands, restart services)

### When You WANT to Recreate

If you need the user_data changes to actually take effect (e.g., fresh bootstrap):

```bash
# Force recreation despite user_data_replace_on_change = false
terraform taint module.ec2.aws_instance.main
terraform apply
# This marks the resource for recreation on the next apply
```

Or temporarily remove the flag:

```hcl
# user_data_replace_on_change = false  # Temporarily comment out
```

## Theory: Terraform Drift

### What Is Drift?

Drift = the actual state of resources in AWS doesn't match what Terraform expects.

| Source of Drift | Example |
|----------------|---------|
| Manual AWS Console changes | Someone changed the security group |
| Out-of-band scripts | A deploy script updated the Docker container |
| Auto-scaling | AWS launched/replaced instances |
| Service updates | RDS auto-minor-version-upgrade |
| External tools | Someone ran `aws s3 mb` outside Terraform |

### Detecting Drift

```bash
# Plan shows all drift
terraform plan

# Refresh state without planning (useful to see current reality)
terraform refresh  # Deprecated in newer Terraform — use plan instead

# Check a specific resource
terraform state show module.ec2.aws_instance.main
```

### The user_data Drift We Had

After manually fixing things on EC2 (installing packages, changing service configs), the running instance diverged from the template. When we updated the template to include `PREFECT_API_URL`/`PREFECT_API_KEY` and ran `terraform plan`, it showed:

```
~ user_data = (sensitive value)  # hash changed
```

This is expected — the template changed. With `user_data_replace_on_change = false`, Terraform just updates the hash in state (update-in-place) without touching the actual EC2.

### Handling Drift in Production

| Strategy | When to Use |
|----------|------------|
| Ignore it | For ephemeral resources (dev environments) |
| `terraform taint` + apply | When you want a clean slate |
| Manual sync | Fix the AWS resource to match Terraform config |
| Import | If someone created a resource outside Terraform that you want to manage |
| `lifecycle ignore_changes` | For attributes that change frequently (like AMI IDs) |

The `lifecycle` meta-argument:

```hcl
resource "aws_instance" "main" {
  ...

  lifecycle {
    ignore_changes = [user_data]  # Never detect user_data drift
    # OR
    prevent_deletion = true        # Refuse to destroy this resource
  }
}
```

## The `.terraform.lock.hcl` File

### What It Does

```hcl
provider "registry.terraform.io/hashicorp/aws" {
  version     = "5.50.0"
  constraints = "5.50.0"
  hashes = [
    "h1:ABC123...",    # Platform-specific hash
    "zh1:DEF456...",   # Zip hash
  ]
}
```

This file records:
- The **exact version** of each provider (not just the constraint)
- **Cryptographic hashes** of the provider binary
- Which **platform** the provider was downloaded for

### Why We Committed It

Without the lock file in version control:
- Two developers running `terraform init` might get different provider versions
- A compromised provider binary could be substituted (no hash verification)
- CI/CD might resolve a different version than what you tested locally

With the lock file committed:
- Everyone gets the exact same provider binary
- Hash verification ensures the binary hasn't been tampered with
- Reproducible builds across all environments

### We Had It in .gitignore — Why That Was Wrong

Our `.gitignore` had:
```
infra/.terraform.lock.hcl
```

This is a common mistake. The `.terraform/` directory (which contains the downloaded provider binaries) should be gitignored — it's large and machine-specific. But the **lock file** is a tiny text file that should be committed.

Fix: Added `!infra/.terraform.lock.hcl` to `.gitignore` to un-ignore it:

```
infra/.terraform/
infra/*.tfstate
...
!infra/.terraform.lock.hcl   # Commit this for provider integrity
```

## The Prefect Agent Service Fix

### What Was Missing

The Prefect agent systemd service in `user_data.sh.tftpl` originally didn't have `PREFECT_API_URL` and `PREFECT_API_KEY` environment variables. Without these, `prefect agent start --work-queue default` would try to connect to a local Prefect server (which doesn't exist on EC2) and fail silently.

### The Fix

```ini
[Service]
User=ubuntu
Group=ubuntu
Environment=MLFLOW_TRACKING_URI=http://localhost:${mlflow_port}
Environment=AWS_REGION=${aws_region}
Environment=PREFECT_API_URL=${prefect_api_url}
Environment=PREFECT_API_KEY=${prefect_api_key}
Environment=S3_BUCKET=${s3_bucket_name}
ExecStart=/opt/mlflow-venv/bin/prefect agent start --work-queue default
Restart=on-failure
RestartSec=15
```

The `${prefect_api_url}` and `${prefect_api_key}` are Terraform template variables — they get their values from `terraform.tfvars`:

```hcl
variable "prefect_api_url" {
  type    = string
  default = ""
}

variable "prefect_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
```

### How to Activate the Prefect Agent

1. Set values in `terraform.tfvars`:
   ```hcl
   prefect_api_url  = "https://api.prefect.cloud/api/accounts/YOUR_ACCOUNT/workspaces/YOUR_WORKSPACE"
   prefect_api_key  = "your-prefect-api-key"
   ```

2. Apply Terraform (this only updates the state hash, not the running EC2):
   ```bash
   terraform apply
   ```

3. SSH into EC2 and restart the service with the new env vars:
   ```bash
   ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238
   # The systemd service file should now have the env vars
   sudo systemctl daemon-reload
   sudo systemctl start prefect-agent
   systemctl status prefect-agent
   ```

Or, if you want a clean bootstrap:
```bash
terraform taint module.ec2.aws_instance.main
terraform apply  # Recreates EC2 with new user_data
```

## How to Debug

### `terraform plan` Wants to Replace EC2

```bash
terraform plan | grep -A5 "replace"
```

If you see `forces replacement`:
1. Check if it's because of `user_data` — add `user_data_replace_on_change = false`
2. Check if it's because of `ami` — add `lifecycle { ignore_changes = [ami] }`
3. Check if it's intentional — `terraform taint` was used

### Stale DynamoDB Lock After Ctrl+C

```bash
# Find the lock ID in the error message
terraform force-unlock <lock-id>
```

Always use this carefully — make sure no other Terraform process is running.

### Prefect Agent Not Starting on EC2

```bash
# Check service status
sudo systemctl status prefect-agent

# Read the logs
sudo journalctl -u prefect-agent --no-pager -n 30

# Common errors:
# "Connection refused" → PREFECT_API_URL is wrong or empty
# "401 Unauthorized" → PREFECT_API_KEY is wrong
# "No such file" → /opt/mlflow-venv/bin/prefect doesn't exist
```

### Provider Hash Mismatch

If `terraform init` fails with a hash mismatch:

```bash
# Update the lock file (only after verifying the provider is legitimate)
terraform providers lock -platform=linux_amd64
```

## Practical Tips

### The Safe `terraform apply` Workflow

```bash
# 1. Always plan first
terraform plan -out=tfplan

# 2. Review the plan — look for "replace" or "destroy"
terraform show tfplan

# 3. Apply only the reviewed plan
terraform apply tfplan
```

### Protect Critical Resources

```hcl
resource "aws_db_instance" "main" {
  ...
  lifecycle {
    prevent_deletion = true  # terraform destroy will skip this
  }
}
```

### Check What Changed Since Last Apply

```bash
# State serial number tells you how many times state was updated
terraform state pull | python3 -c "import json,sys; print(json.load(sys.stdin)['serial'])"
```

### The Terraform State Bucket Security Checklist

After migration, verify:

```bash
# Versioning enabled?
aws s3api get-bucket-versioning --bucket heart-disease-mlops-695074562426-tfstate

# Encryption enabled?
aws s3api get-bucket-encryption --bucket heart-disease-mlops-695074562426-tfstate

# Public access blocked?
aws s3api get-public-access-block --bucket heart-disease-mlops-695074562426-tfstate

# State file exists?
aws s3 ls s3://heart-disease-mlops-695074562426-tfstate/
```

All four should return affirmative results.
