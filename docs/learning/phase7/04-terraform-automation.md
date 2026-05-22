# 04 — Terraform Automation

## What is Infrastructure as Code (IaC)?

**IaC** manages infrastructure using code instead of manual configuration. Terraform is our IaC tool.

**Benefits:**
- ✅ Version controlled (git history)
- ✅ Reproducible (same infra every time)
- ✅ Reviewable (PRs for infrastructure changes)
- ✅ Automated (CI/CD for infrastructure)

---

## Why Automate Terraform?

### Manual Terraform

```bash
# Developer 1: Makes changes
cd infra
terraform plan  # Review
terraform apply  # Apply

# Developer 2: Wants to make changes
# ... but doesn't know about Developer 1's changes
terraform plan  # Shows unexpected differences
# Chaos ensues
```

**Problems:**
- No review process
- Conflicts between team members
- No audit trail
- Easy to make mistakes

---

### Automated Terraform

```bash
# Developer 1: Creates PR with infra changes
# GitHub Actions: terraform plan → Comments on PR
# Team: Reviews plan in PR
# Maintainer: Approves PR
# GitHub Actions: terraform apply on merge

# Developer 2: Creates separate PR
# GitHub Actions: terraform plan based on updated state
# Clean, reviewed, safe
```

**Benefits:**
- ✅ PR review for all changes
- ✅ Plan preview before apply
- ✅ Audit trail in git
- ✅ No direct AWS console access needed

---

## Our Terraform Workflow

```yaml
# .github/workflows/infra.yml
name: Infrastructure

on:
  pull_request:
    paths:
      - 'infra/**'          # Only when infra/ changes
      - '.github/workflows/infra.yml'
  push:
    branches: [main]       # Only on main
    paths:
      - 'infra/**'

jobs:
  terraform:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      pull-requests: write  # Required for PR comments
    
    steps:
      - uses: actions/checkout@v4
      
      # Authenticate via OIDC
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
      
      # Setup Terraform
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.5.7"
      
      - name: Terraform Init
        working-directory: infra
        run: terraform init
      
      # Format check
      - name: Terraform Format
        working-directory: infra
        run: terraform fmt -check
      
      # Plan (on PR)
      - name: Terraform Plan
        if: github.event_name == 'pull_request'
        working-directory: infra
        run: terraform plan -no-color
        continue-on-error: true
      
      # Comment plan on PR
      - name: Comment PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            // ... post plan as PR comment
      
      # Apply (on merge to main)
      - name: Terraform Apply
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        working-directory: infra
        run: terraform apply -auto-approve
```

---

## How It Works

### On Pull Request (Plan Mode)

```
Developer creates PR
        │
        ▼
┌───────────────────┐
│ Filter: infra/**  │  ← Only run if infra/ files changed
│ files changed?    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Checkout code     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ OIDC Auth         │
│ (AWS credentials) │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ terraform init    │
│ (remote state)    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ terraform fmt     │
│ -check            │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ terraform plan    │
│ -no-color         │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Post plan as PR   │
│ comment           │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ ❌ Block merge    │
│ if plan fails     │
└───────────────────┘
```

**The PR Comment:**

> #### Terraform Plan
> 
> ❌ Plan failed
> 
> <details><summary>Show Plan</summary>
> 
> ```
> Terraform will perform the following actions:
> 
>   # aws_iam_role.example will be created
>   + resource "aws_iam_role" "example" {
>       + arn                   = (known after apply)
>       + assume_role_policy    = jsonencode(...)
>       + name                  = "example-role"
>     }
> 
> Plan: 1 to add, 0 to change, 0 to destroy.
> ```
> 
> </details>

---

### On Merge to Main (Apply Mode)

```
PR merged to main
        │
        ▼
┌───────────────────┐
│ Filter: infra/**  │
│ files changed?    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Checkout code     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ OIDC Auth         │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ terraform init    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ terraform apply   │
│ -auto-approve     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Infrastructure    │
│ updated!          │
└───────────────────┘
```

---

## Permissions Required

The GitHub Actions role needs extra permissions for Terraform:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "s3:*",
        "rds:*",
        "iam:*",
        "sns:*",
        "cloudwatch:*",
        "dynamodb:*",
        "logs:*"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::heart-disease-mlops-*-tfstate",
        "arn:aws:s3:::heart-disease-mlops-*-tfstate/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/heart-disease-mlops-tflock"
    }
  ]
}
```

**Note:** This is broad for simplicity. In production, scope to specific resources.

---

## Terraform Plan Output

The workflow captures the plan output and posts it as a PR comment.

**Example Plan Output:**

```
Terraform will perform the following actions:

  # aws_iam_openid_connect_provider.github will be created
  + resource "aws_iam_openid_connect_provider" "github" {
      + arn                     = (known after apply)
      + client_id_list          = [
          + "sts.amazonaws.com",
        ]
      + id                      = (known after apply)
      + tags                    = {
          + "Environment" = "dev"
          + "Name"        = "heart-disease-mlops"
        }
      + tags_all                = {
          + "Environment" = "dev"
          + "Name"        = "heart-disease-mlops"
        }
      + thumbprint_list         = [
          + "6938fd4e98bab03faadb97b34396831e3780aea1",
        ]
      + url                     = "https://token.actions.githubusercontent.com"
    }

  # aws_iam_role.github_actions will be created
  + resource "aws_iam_role" "github_actions" {
      + arn                   = (known after apply)
      + assume_role_policy    = jsonencode(
            {
              + Statement = [
                  + {
                      + Action    = "sts:AssumeRoleWithWebIdentity"
                      + Condition = {
                          + StringEquals = { ... }
                          + StringLike   = { ... }
                        }
                      + Effect    = "Allow"
                      + Principal = {
                          + Federated = (known after apply)
                        }
                    },
                ]
              + Version   = "2012-10-17"
            }
        )
      + name                  = "heart-disease-mlops-github-actions"
    }

Plan: 2 to add, 0 to change, 0 to destroy.
```

**What to Review:**

| Element | Check |
|---------|-------|
| `to add` | Are these expected new resources? |
| `to change` | Will this modify existing resources? |
| `to destroy` | Is anything being deleted? (Risky!) |
| Resource types | Are these the right AWS services? |
| Names/tags | Do they match our naming convention? |

---

## Path Filtering

The workflow only runs when `infra/` files change:

```yaml
on:
  pull_request:
    paths:
      - 'infra/**'          # All files in infra/
      - '.github/workflows/infra.yml'  # The workflow itself
```

**Why:**
- Don't waste CI minutes on unrelated changes
- Don't comment "No changes" on every PR
- Keep feedback focused

---

## State Locking

Our Terraform uses remote state with DynamoDB locking:

```hcl
# infra/backend.tf
terraform {
  backend "s3" {
    bucket         = "heart-disease-mlops-695074562426-tfstate"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "heart-disease-mlops-tflock"
    encrypt        = true
  }
}
```

**What locking does:**

```
Developer 1: terraform apply ──┐
                                 │
                                 ▼
                        ┌────────────────┐
                        │ DynamoDB       │
                        │ Lock Table     │
                        │                │
                        │ LockID:        │
                        │ "terraform"    │
                        │ Info:          │
                        │ "User 1, 2025-..."
                        │ Expires:       │
                        │ 2025-07-30...  │
                        └────────────────┘
                                 ▲
                                 │
Developer 2: terraform apply ────┘
        "Lock already held by User 1"
        Developer 2 waits or forces unlock
```

**Prevents:**
- Two people applying simultaneously
- State corruption
- Lost changes

---

## Common Terraform in CI Issues

### Issue 1: State Lock

**Error:**
```
Error: Error acquiring the state lock
Error message: ConditionalCheckFailedException: The conditional request failed
Lock Info:
  ID:        abc123
  Path:      heart-disease-mlops-tfstate/terraform.tfstate
  Operation: OperationTypeApply
  Who:       ubuntu@runner
```

**Cause:** Previous run didn't release lock (crashed or cancelled).

**Fix:**
```bash
# Unlock (requires lock ID from error)
terraform force-unlock abc123

# Or in CI, use -force flag (dangerous!)
terraform force-unlock -force abc123
```

---

### Issue 2: Provider Download Timeout

**Error:**
```
Error: Failed to query available provider packages
Could not retrieve the list of available versions for provider aws
```

**Cause:** Large provider binaries (~500MB) time out on slow connections.

**Fix:**
1. Commit `.terraform.lock.hcl` to git
2. Use `terraform init -plugin-cache=/tmp/terraform-cache`

---

### Issue 3: No Changes Detected

**Output:**
```
No changes. Your infrastructure matches the configuration.
```

**Cause:** Path filtering or no actual changes to infra files.

**Fix:** Ensure you're changing files in `infra/` directory.

---

### Issue 4: Plan Comment Not Posted

**Cause:** Missing `pull-requests: write` permission.

**Fix:**
```yaml
permissions:
  id-token: write      # For OIDC
  pull-requests: write # For commenting
  contents: read       # For checkout
```

---

## Testing Infrastructure Changes

### Safe Workflow

1. **Branch:** `git checkout -b add-new-resource`
2. **Code:** Make changes to `infra/modules/...`
3. **Local test:** `terraform plan` (not apply!)
4. **Commit:** `git add . && git commit -m "Add X"`
5. **Push:** `git push origin add-new-resource`
6. **PR:** Open PR on GitHub
7. **Review:** Check plan output in PR comment
8. **Merge:** Maintainer merges
9. **Apply:** GitHub Actions applies automatically

---

## Verification Commands

### Check Workflow Status

```bash
# List infrastructure runs
gh run list --workflow=Infrastructure

# View specific run
gh run view <run-id>

# Check if workflow triggered
gh run list --workflow=Infrastructure --limit 5
```

### Check Terraform State

```bash
cd infra

# Verify remote state
cat backend.tf

# Check state exists
aws s3 ls s3://heart-disease-mlops-695074562426-tfstate/

# List state contents (careful - don't modify!)
terraform state list

# View specific resource
terraform state show aws_iam_role.github_actions
```

### Check Lock Table

```bash
# View current locks
aws dynamodb scan \
  --table-name heart-disease-mlops-tflock \
  --query 'Items[*].LockID'

# Force unlock (if needed)
terraform force-unlock <lock-id>
```

---

## Key Takeaways

1. **Plan on PR** — See changes before applying
2. **Apply on merge** — Only after review
3. **Path filtering** — Don't run for unrelated changes
4. **State locking** — Prevents conflicts
5. **PR comments** — Transparency for the team
6. **OIDC auth** — No stored AWS credentials

---

## Next Steps

- ✅ Read [05 — Rollback & Notifications](05-rollback-and-notifications.md) for deploy safety
- ✅ Read [06 — Troubleshooting CI/CD](06-troubleshooting-cicd.md) for common issues
- ✅ Create test PR with minor infra change
- ✅ Verify plan appears as PR comment
- ✅ Merge and verify apply runs automatically
