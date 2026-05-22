# Phase 9 — Security Hardening ✅ COMPLETE

**Goal:** Remove all secrets from the repository and establish secure development practices.

This phase implements pre-commit hooks, git history cleanup procedures, AWS key rotation steps, and security group hardening.

---

## What Was Implemented (AI)

### 1. Pre-commit Hooks (✅ Automated)
Installed security-focused pre-commit hooks that run on every commit:

- **detect-secrets** — Blocks commits containing AWS keys, passwords, tokens
- **detect-aws-credentials** — Catches AWS credential files
- **no-commit-to-branch** — Prevents accidental commits to main
- **check-added-large-files** — Blocks files > 1MB (prevents credential bundles)
- **check-merge-conflict** — Prevents committing unresolved conflicts
- **bandit** — Python security linter (checks for security anti-patterns)
- **black, isort, flake8** — Code quality (from Phase 7)

**Files created:**
- `.pre-commit-config.yaml` — Hook configuration
- `.secrets.baseline` — Baseline of known non-secrets (committed intentionally)

### 2. Enhanced .gitignore (✅ Automated)
Added comprehensive patterns for:
- Environment files (`.env*`, `.envrc`)
- Credential files (`*.pem`, `*.key`, `id_rsa`, `id_ed25519`)
- AWS/GCP credential directories (`.aws/`, service account files)
- SSH files (`.ssh/`, `known_hosts`)

### 3. Terraform IP Restrictions (✅ Already Configured)
The infrastructure is already designed to restrict access by IP:
- Security groups use `var.your_ip` variable
- SSH (22), MLflow (5000), API (8000) all restricted to your IP only
- **You just need to set your IP in terraform.tfvars**

---

## What You Need to Do Manually

### Step 1: Get Your Current IP Address

```bash
# Check your public IP
curl https://checkip.amazonaws.com

# Or use ifconfig.me
curl ifconfig.me

# Or ipinfo.io
curl ipinfo.io/ip
```

**Output example:** `203.0.113.50`

**Remember to add /32:** Use `203.0.113.50/32` in terraform.tfvars

---

### Step 2: Purge .env from Git History

**⚠️ WARNING:** This rewrites git history. Coordinate with team members if collaborating.

```bash
# Install git-filter-repo (modern replacement for filter-branch)
pip install git-filter-repo

# Create backup of repo
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project
cp -r . ../MLOps-Zoomcamp-Project-backup-$(date +%Y%m%d)

# Remove .env from entire history
git filter-repo --path .env --invert-paths

# Verify .env is gone from history
git log --all --full-history -- .env
# Should return nothing

# Force push to rewrite history on GitHub
git push origin --force --all

# Clean up backup when satisfied
rm -rf ../MLOps-Zoomcamp-Project-backup-*
```

**Alternative (if git-filter-repo not available):**
```bash
# Using built-in filter-branch (slower, deprecated but works)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all

git push origin --force --all
```

---

### Step 3: Rotate AWS Access Keys

**In AWS Console:**
1. Go to IAM → Users → firstuser → Security credentials
2. Find the access key ending in `JM7` (AKIA2DVNMEF5JTWDIJM7)
3. Click "Make inactive" (don't delete yet, in case of issues)
4. Click "Create access key"
5. Copy Access Key ID and Secret Access Key

**Update your local .env:**
```bash
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project

# Update .env file
# Change these lines:
# AWS_ACCESS_KEY_ID=AKIA2DVNMEF5JTWDIJM7  # ← OLD, EXPOSED
# AWS_SECRET_ACCESS_KEY=...

# To:
# AWS_ACCESS_KEY_ID=AKIA...NEWKEY...
# AWS_SECRET_ACCESS_KEY=...new secret...
```

**Test new credentials:**
```bash
# Source .env
export $(cat .env | xargs)

# Verify AWS CLI works
aws sts get-caller-identity

# Should show:
# {
#     "UserId": "AIDA...",
#     "Account": "695074562426",
#     "Arn": "arn:aws:iam::695074562426:user/firstuser"
# }
```

**After 24 hours (once everything works):**
1. Go back to IAM Console
2. Delete the old access key (AKIA2DVNMEF5JTWDIJM7)

---

### Step 4: Configure GitHub Secrets

**Using GitHub CLI (gh):**
```bash
# Install gh if not present
# See: https://github.com/cli/cli#installation

# Authenticate (if not already)
gh auth login

# Set repository secrets
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project

# 1. AWS_ROLE_ARN — Get from Terraform output
gh secret set AWS_ROLE_ARN \
  --body "arn:aws:iam::695074562426:role/heart-disease-mlops-github-actions"

# 2. EC2_SSH_KEY — Your private key for SSH access
# (copy contents of ~/.ssh/id_ed25519)
cat ~/.ssh/id_ed25519 | gh secret set EC2_SSH_KEY

# 3. SNS_TOPIC_ARN — Get from Terraform output
gh secret set SNS_TOPIC_ARN \
  --body "arn:aws:sns:us-east-1:695074562426:heart-disease-mlops-alarms"

# Verify secrets are set
gh secret list
```

**Using GitHub Web UI (if gh CLI not available):**
1. Go to https://github.com/abandonedmonk/MLOps-Zoomcamp-Project/settings/secrets/actions
2. Click "New repository secret"
3. Add each secret:
   - `AWS_ROLE_ARN`: `arn:aws:iam::695074562426:role/heart-disease-mlops-github-actions`
   - `EC2_SSH_KEY`: (copy entire contents of `~/.ssh/id_ed25519`)
   - `SNS_TOPIC_ARN`: `arn:aws:sns:us-east-1:695074562426:heart-disease-mlops-alarms`

---

### Step 5: Apply Terraform IP Restrictions

```bash
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project/infra

# 1. Get your IP
curl https://checkip.amazonaws.com
# Example: 203.0.113.50

# 2. Edit terraform.tfvars
# Change:
# your_ip = "0.0.0.0/0"  # ← OPEN TO WORLD (BAD)
# To:
# your_ip = "203.0.113.50/32"  # ← YOUR IP ONLY (GOOD)

# 3. Plan changes
terraform plan -target=module.ec2

# 4. Apply (only updates security group rules, no EC2 rebuild)
terraform apply -target=module.ec2

# 5. Verify in AWS Console
# EC2 → Security Groups → heart-disease-mlops-ec2-sg
# Should show your IP in inbound rules, not 0.0.0.0/0
```

---

### Step 6: Install Pre-commit Hooks Locally

```bash
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project

# Install hooks (run once per clone)
pre-commit install

# Test on all files (first run will be slow)
pre-commit run --all-files

# Expected output:
# detect-secrets.........................................................Passed
# no-commit-to-branch....................................................Passed
# check-added-large-files................................................Passed
# check-merge-conflict...................................................Passed
# black..................................................................Passed
# isort (python).........................................................Passed
# flake8.................................................................Passed
# bandit.................................................................Passed
```

**Test that secrets are blocked:**
```bash
# Create test file with fake AWS key
echo "AKIAIOSFODNN7EXAMPLE" > /tmp/test_secret.txt
git add /tmp/test_secret.txt
git commit -m "test secret"

# Should FAIL with:
# detect-secrets.........................................................Failed
# - hook id: detect-secrets
# - exit code: 1
#
# Potential secrets found:
# /tmp/test_secret.txt:1:AKIAIOSFODNN7EXAMPLE

# Clean up test
git reset HEAD /tmp/test_secret.txt
rm /tmp/test_secret.txt
```

---

### Step 7: Update Pre-commit Baseline (If Needed)

If pre-commit flags files that are NOT actually secrets (e.g., notebook outputs):

```bash
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project

# Audit the flagged secrets
detect-secrets audit .secrets.baseline

# This opens interactive editor to mark false positives as "not secret"

# After marking, regenerate baseline
detect-secrets scan > .secrets.baseline

# Commit updated baseline
git add .secrets.baseline
git commit -m "Update secrets baseline with verified non-secrets"
```

---

## Verification Checklist

After completing all steps:

```bash
# 1. Verify .env is not in git
git log --all --full-history -- .env
# Should return: "fatal: ambiguous argument '.env': unknown revision or path"

# 2. Verify .env is in .gitignore
grep "^\.env$" .gitignore
# Should show: .env

# 3. Verify pre-commit hooks work
pre-commit run detect-secrets --all-files
# Should show: Passed

# 4. Verify AWS key rotated
aws sts get-caller-identity --query 'Arn' --output text
# Should show new key (different from AKIA2DVNMEF5JTWDIJM7)

# 5. Verify GitHub secrets
gh secret list
# Should show: AWS_ROLE_ARN, EC2_SSH_KEY, SNS_TOPIC_ARN

# 6. Verify IP restrictions in AWS Console
aws ec2 describe-security-groups \
  --group-names heart-disease-mlops-ec2-sg \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`22`].IpRanges[0].CidrIp' \
  --output text
# Should show your IP/32, not 0.0.0.0/0
```

---

## Files Added/Modified

### New Files (Auto-created)
- `.pre-commit-config.yaml` — Hook configuration
- `.secrets.baseline` — Known non-secrets tracking

### Modified Files (Auto-updated)
- `.gitignore` — Enhanced security patterns

### Files You Must Update (Manual)
- `.env` — Rotate AWS keys
- `infra/terraform.tfvars` — Set your IP
- GitHub Secrets — Configure via CLI or UI

---

## Common Issues

### Issue: "git filter-repo: not a git repository"
**Fix:** Make sure you're in the repo root:
```bash
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project
```

### Issue: "detect-secrets: command not found"
**Fix:** Install detect-secrets:
```bash
pip install detect-secrets
```

### Issue: "pre-commit not found"
**Fix:** Install pre-commit:
```bash
pip install pre-commit
pre-commit install
```

### Issue: Git push rejected after history rewrite
**Fix:** Force push (coordinate with team first):
```bash
git push origin --force --all
```

### Issue: Can't SSH to EC2 after IP restriction
**Fix:** If your IP changed (e.g., on WiFi), update terraform.tfvars:
```bash
curl https://checkip.amazonaws.com
# Update infra/terraform.tfvars with new IP
terraform apply -target=module.ec2
```

---

## Security Best Practices Going Forward

1. **Never commit `.env`** — Pre-commit hooks will block this now
2. **Rotate keys every 90 days** — Set calendar reminder
3. **Use IP restrictions** — Don't leave ports open to 0.0.0.0/0
4. **Review `terraform plan`** — Always check what changes before applying
5. **Monitor AWS IAM** — Check CloudTrail for unexpected API calls
6. **Enable MFA** — On your AWS IAM user and GitHub account
7. **Audit pre-commit** — Run `pre-commit run --all-files` before major commits

---

## Phase 9 Complete When:
- ✅ `.env` purged from git history
- ✅ AWS keys rotated, old key deactivated
- ✅ Pre-commit hooks installed and working
- ✅ GitHub Secrets configured
- ✅ Security groups restricted to your IP
- ✅ All verification checks pass

**Estimated Time:** 30-60 minutes (mostly waiting for AWS/Github)
