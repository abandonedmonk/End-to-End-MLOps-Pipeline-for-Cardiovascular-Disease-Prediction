# Phase 7 — Overview

## What We Built

Phase 7 transforms our MLOps pipeline from manual deployments to fully automated CI/CD. Every code change now flows through automated linting, testing, building, and deployment — with built-in rollback safety.

---

## The Three Workflows

### 1. CI (Continuous Integration)

**Trigger:** Pull request to `main` or `aws_migration`

**Purpose:** Ensure code quality before merge

**Steps:**
1. Checkout code
2. Set up Python 3.12
3. Install linting tools
4. Run `flake8` (style guide enforcement)
5. Run `black --check` (formatting verification)
6. Run `isort --check` (import sorting)
7. Run placeholder tests (Phase 8 adds real ones)

**Outcome:** 
- ✅ Pass → PR can be merged
- ❌ Fail → Block merge, fix issues

---

### 2. CD (Continuous Deployment)

**Trigger:** Push to `main` or `aws_migration`

**Purpose:** Build and deploy automatically

**Steps:**
1. **Authenticate** via OIDC (no stored AWS keys)
2. **Build** Docker image with FastAPI
3. **Tag** with commit SHA and `latest`
4. **Push** both tags to Amazon ECR
5. **SSH** to EC2 instance
6. **Deploy** new container (pull, stop old, start new)
7. **Health check** API endpoint
8. **Notify** via SNS (success or failure)

**Rollback on Failure:**
- If health check fails → stop new container
- Start previous image from `docker inspect`
- Send failure notification

---

### 3. Infrastructure

**Trigger:** 
- PR changing `infra/**` → Plan
- Push to `main` changing `infra/**` → Apply

**Purpose:** Automate infrastructure changes

**Steps:**
1. Authenticate via OIDC
2. Run `terraform plan`
3. Comment plan output on PR
4. On merge → `terraform apply`

---

## The Security Model: OIDC

### Old Way (Insecure)

```yaml
# DON'T DO THIS
- name: Configure AWS
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}  # ❌ Long-lived
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

**Problems:**
- Keys never expire
- If leaked, attacker has permanent access
- Must rotate manually
- Stored in GitHub (trust issue)

---

### New Way (OIDC)

```yaml
# DO THIS
permissions:
  id-token: write  # Required for OIDC

- name: Configure AWS
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}  # ✅ Short-lived
    aws-region: us-east-1
```

**How It Works:**

```
GitHub Actions          AWS IAM OIDC
     │                        │
     │  1. Request token      │
     │───────────────────────>│
     │                        │
     │  2. JWT token issued   │
     │<───────────────────────│
     │                        │
     │  3. Exchange for creds │
     │  (sts:AssumeRoleWithWebIdentity)
     │───────────────────────>│
     │                        │
     │  4. Temporary creds    │
     │<───────────────────────│
     │     (15 min expiry)    │
```

**Benefits:**
- ✅ No stored credentials
- ✅ Tokens expire automatically (15 min default)
- ✅ Role permissions control what Actions can do
- ✅ Trust relationship limits which repos can assume role

---

## The Rollback System

### Why Rollback Matters

Deployments can fail:
- Bug introduced in code
- Environment variable missing
- Database connection issue
- Model file corrupted

Without rollback: Site stays down until manual fix  
With rollback: Automatically revert to last working version

---

### How Rollback Works

```bash
# Before deploying, capture current state
PREVIOUS_IMAGE=$(docker ps --format '{{.Image}}' | grep heart-disease)
# → "695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:sha-abc1234"

# Deploy new image
docker run -d --name fastapi NEW_IMAGE

# Health check
curl http://32.196.26.238:8000/health
# ❌ Returns: {"model_loaded": false}

# ROLLBACK!
docker stop fastapi
docker rm fastapi
docker run -d --name fastapi $PREVIOUS_IMAGE

# Verify
curl http://32.196.26.238:8000/health
# ✅ Returns: {"model_loaded": true}
```

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| GitHub OIDC Provider | ✅ Created | AWS IAM |
| GitHub Actions Role | ✅ Created | AWS IAM |
| CI Workflow | ✅ Active | `.github/workflows/ci.yml` |
| CD Workflow | ✅ Active | `.github/workflows/cd.yml` |
| Infra Workflow | ✅ Active | `.github/workflows/infra.yml` |
| Docker Image | ✅ Pushed | ECR (`sha-xxx` + `latest`) |
| Auto-Rollback | ✅ Implemented | CD workflow |
| SNS Notifications | ✅ Working | Email alerts |
| GitHub Secrets | ⚠️ Need Setup | 3 secrets required |

---

## What You Need to Do

### 1. Apply Terraform (Creates OIDC + Role)

```bash
cd infra
terraform plan   # Review changes
terraform apply  # Creates OIDC provider and IAM role

# Get outputs
cd ..
terraform -chdir=infra output github_actions_role_arn
# → arn:aws:iam::695074562426:role/heart-disease-mlops-github-actions

terraform -chdir=infra output sns_topic_arn
# → arn:aws:sns:us-east-1:695074562426:heart-disease-mlops-alarms
```

### 2. Configure GitHub Secrets

```bash
# Using gh CLI
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::...:role/..."
gh secret set EC2_SSH_KEY < ~/.ssh/id_ed25519
gh secret set SNS_TOPIC_ARN --body "arn:aws:sns:..."

# Or via GitHub UI:
# Settings → Secrets and variables → Actions → New repository secret
```

### 3. Test the Workflows

```bash
# Test CI: Create a PR
git checkout -b test-ci
echo "# test" >> README.md
git add . && git commit -m "Test CI"
git push origin test-ci

# Open PR on GitHub → CI should run automatically

# Test CD: Push to aws_migration
git checkout aws_migration
git merge test-ci
git push origin aws_migration

# Watch CD workflow run
gh run list --workflow=CD
gh run watch <run-id>

# Verify deployment
curl http://32.196.26.238:8000/health
```

---

## Key Metrics

| Metric | Value |
|--------|-------|
| **Time to Deploy** | ~3-5 minutes (Docker build is the bottleneck) |
| **Deployment Frequency** | Unlimited (each push triggers) |
| **Rollback Time** | ~30 seconds (stop old, start previous) |
| **Manual Steps** | 0 (fully automated after initial setup) |
| **Security Risk** | Low (no long-lived credentials) |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GITHUB REPOSITORY                            │
│              abandonedmonk/MLOps-Zoomcamp-Project                   │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                         │
│  │  ci.yml  │  │  cd.yml  │  │infra.yml │                         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                         │
│       │              │              │                                 │
│       │  PR          │  Push        │  PR (infra)                     │
│       ▼              ▼              ▼                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                         │
│  │  flake8  │  │  Docker  │  │Terraform │                         │
│  │  black   │  │  build   │  │  plan    │                         │
│  │  isort   │  │  ECR push│  │  comment │                         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                         │
│       │              │              │                                 │
│       │ Pass/Fail    │              │ Merge                           │
└───────┼──────────────┼──────────────┼─────────────────────────────────┘
        │              │              │
        │              │              │
        ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AWS (via OIDC)                               │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  IAM Role    │    │     ECR      │    │   Terraform  │          │
│  │  (temporary) │───>│  Repository  │    │   Backend    │          │
│  │  15 min      │    │              │    │   S3+DynamoDB│          │
│  └──────────────┘    └──────┬───────┘    └──────────────┘          │
│                             │                                      │
│                             ▼                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  EC2 Instance│<───│  SSH + Docker│    │     SNS      │          │
│  │  32.196.26.238    │  pull & run  │    │  Email Alert │          │
│  │  :8000       │    │              │    │              │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Lint and test on PR |
| `.github/workflows/cd.yml` | Build, deploy, health check, rollback |
| `.github/workflows/infra.yml` | Terraform automation |
| `infra/modules/iam/main.tf` | OIDC provider + GitHub role |
| `tests/test_placeholder.py` | Always passes (until Phase 8) |
| `pyproject.toml` | Dev dependencies (flake8, black, etc.) |

---

## Design Principles

1. **Security First** — OIDC authentication, no stored keys
2. **Fail Fast** — Health checks verify deployment before declaring success
3. **Self-Healing** — Auto-rollback on failure
4. **Observable** — SNS notifications on every deploy outcome
5. **Transparent** — Terraform plan comments on PRs
6. **Deterministic** — Commit SHA tags for exact rollback

---

## Common Questions

### Why not use AWS CodePipeline?

CodePipeline is AWS-native but:
- ❌ More complex configuration
- ❌ Vendor lock-in
- ❌ Harder to integrate with GitHub (needs webhooks)
- ✅ GitHub Actions is simpler for GitHub-hosted repos
- ✅ Better community, more actions marketplace

### Why placeholder tests instead of real ones?

Phase 8 is dedicated to comprehensive testing:
- Unit tests
- Integration tests
- API endpoint tests
- Data validation tests

Skipping real tests in Phase 7:
- ✅ Keeps scope focused (CI/CD infrastructure)
- ✅ Prevents blocking deployments while test suite is immature
- ✅ Allows iterative test development in Phase 8

### What if the rollback also fails?

Worst-case scenario:
1. Deploy fails → attempt rollback
2. Rollback fails → container stays stopped
3. SNS sends critical failure notification
4. Manual intervention required

**Mitigation:** Rollback uses the exact same image that was running before. If it worked then, it should work now (barring external changes like DB outages).

---

## Next Steps

1. ✅ Read [01 — GitHub Actions & OIDC](01-github-actions-oidc.md)
2. ✅ Read [02 — CI Workflow](02-ci-workflow.md)
3. ✅ Read [03 — CD Workflow](03-cd-workflow.md)
4. ✅ Configure GitHub Secrets
5. ✅ Test with empty commit
6. ✅ Verify auto-rollback works

Then move to **Phase 8: Testing & Quality** for real test coverage.
