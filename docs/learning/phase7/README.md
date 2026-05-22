# Phase 7 — CI/CD with GitHub Actions

Automating your entire MLOps workflow: code linting, Docker builds, ECR pushes, EC2 deployments, and infrastructure updates — all triggered by git events.

---

## What This Phase Covers

| Component | Purpose | Tool |
|-----------|---------|------|
| **CI** | Lint code on every PR | GitHub Actions |
| **CD** | Build Docker → ECR → EC2 deploy | GitHub Actions |
| **Rollback** | Auto-revert on failed health checks | GitHub Actions + Docker |
| **Notifications** | Email alerts on deploy success/failure | SNS |
| **IaC** | Terraform plan/apply via PRs | GitHub Actions + OIDC |
| **Security** | No stored AWS credentials | OIDC Authentication |

---

## Documentation Index

| File | What You'll Learn |
|------|-------------------|
| [Phase 7 Overview](phase7-overview.md) | Architecture, what we built, how it all connects |
| [01 — GitHub Actions & OIDC](01-github-actions-oidc.md) | GitHub Actions basics, OIDC vs stored credentials, IAM trust |
| [02 — CI Workflow](02-ci-workflow.md) | Linting with flake8, black, isort; placeholder tests |
| [03 — CD Workflow](03-cd-workflow.md) | Docker builds, ECR push, SSH deploy, health checks |
| [04 — Terraform Automation](04-terraform-automation.md) | Automated plan/apply, PR comments, OIDC permissions |
| [05 — Rollback & Notifications](05-rollback-and-notifications.md) | Auto-rollback logic, SNS email alerts, commit SHA tagging |
| [06 — Troubleshooting CI/CD](06-troubleshooting-cicd.md) | SSH issues, OIDC errors, health check failures |

---

## Quick Start

```bash
# 1. Apply Terraform to create OIDC provider and role
cd infra
terraform apply

# 2. Get the role ARN
terraform output github_actions_role_arn

# 3. Set GitHub Secrets (use gh CLI or GitHub UI)
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::...:role/..."
gh secret set EC2_SSH_KEY < ~/.ssh/id_ed25519
gh secret set SNS_TOPIC_ARN --body "arn:aws:sns:..."

# 4. Push to aws_migration to test CD
git commit --allow-empty -m "Test CD workflow"
git push origin aws_migration

# 5. Check workflow status
gh run list --workflow=CD
gh run view <run-id>
```

---

## Key URLs

| Service | URL |
|---------|-----|
| MLflow UI | http://32.196.26.238:5000 |
| FastAPI Health | http://32.196.26.238:8000/health |
| GitHub Actions | https://github.com/abandonedmonk/MLOps-Zoomcamp-Project/actions |
| AWS Console IAM | https://console.aws.amazon.com/iam/home#/roles |

---

## Architecture

```
Developer Workflow
        │
        ├──► Create PR ──────────────────────┐
        │           │                          │
        │           ▼                          │
        │    ┌──────────────┐                 │
        │    │  CI Workflow  │                 │
        │    │  ├─ flake8    │                 │
        │    │  ├─ black      │                 │
        │    │  ├─ isort      │                 │
        │    │  └─ placeholder │                │
        │    └──────────────┘                 │
        │           │                          │
        │           ▼ (FAIL)                   │
        │    ❌ Block merge                    │
        │           │                          │
        │           ▼ (PASS)                   │
        │    ✅ Status check passes            │
        │           │                          │
        ▼           │                          ▼
   Merge to main ───────────────────────────────►
                              │
                              ▼
                    ┌──────────────────┐
                    │  CD Workflow      │
                    │  ├─ OIDC auth      │
                    │  ├─ Build image    │
                    │  ├─ Tag: sha-xxx   │
                    │  ├─ Tag: latest    │
                    │  ├─ Push to ECR    │
                    │  ├─ SSH to EC2     │
                    │  ├─ Deploy new     │
                    │  └─ Health check   │
                    └──────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │                    │
                    ▼                    ▼
            ┌──────────────┐      ┌──────────────┐
            │  HEALTH OK   │      │  HEALTH FAIL │
            └──────┬───────┘      └──────┬───────┘
                   │                     │
                   ▼                     ▼
            ┌──────────────┐      ┌──────────────┐
            │ SNS: Success │      │ Rollback to  │
            └──────────────┘      │ previous img │
                                  └──────┬───────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │ SNS: Failed  │
                                  └──────────────┘
```

---

## Files Created

```
.github/workflows/
├── ci.yml              # Lint on PR to main/aws_migration
├── cd.yml              # Deploy on push to main/aws_migration
└── infra.yml           # Terraform plan/apply on infra changes

infra/modules/iam/
├── main.tf             # OIDC provider + GitHub Actions role
├── variables.tf        # New: github_actions_enabled, sns_topic_arn
└── outputs.tf          # github_actions_role_arn

tests/
└── test_placeholder.py # Always passes (Phase 8 adds real tests)

docs/learning/phase7/
├── README.md
├── phase7-overview.md
├── 01-github-actions-oidc.md
├── 02-ci-workflow.md
├── 03-cd-workflow.md
├── 04-terraform-automation.md
├── 05-rollback-and-notifications.md
├── 06-troubleshooting-cicd.md
└── IMPLEMENTATION_SUMMARY.md
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Authentication** | OIDC over stored keys | No long-lived AWS credentials in GitHub |
| **Image Tagging** | SHA + latest | Deterministic rollback, operational convenience |
| **Rollback Method** | Previous container image | Exact state, not inferred from tags |
| **Health Check** | API `/health` endpoint | Real verification, not just "container running" |
| **Notifications** | SNS email | Simple, already set up in Phase 6 |
| **Infra Workflow** | Plan on PR, apply on merge | Review changes before applying |
| **Test Strategy** | Placeholder only | Phase 8 adds real pytest coverage |
| **Branch Targets** | main + aws_migration | Supports migration branch during development |

---

## GitHub Secrets Required

| Secret | Source | Command |
|--------|--------|---------|
| `AWS_ROLE_ARN` | Terraform output | `terraform output github_actions_role_arn` |
| `EC2_SSH_KEY` | SSH private key | `cat ~/.ssh/id_ed25519` |
| `SNS_TOPIC_ARN` | Terraform output | `terraform output sns_topic_arn` |

---

## Free Tier Impact

| Resource | Usage | Allowance | Headroom |
|----------|-------|-----------|----------|
| GitHub Actions Minutes | ~200 min/month | 2,000 free | ~1,800 |
| ECR Storage | ~1 GB (1 image) | 500 MB free | None (slight overage) |
| OIDC Provider | 1 | Free | Unlimited |
| IAM Roles | 1 | Free | Unlimited |
| SNS Notifications | ~10/month | 1M publishes free | ~999,990 |

**Total additional monthly cost: ~$0.10** (ECR overage only)

---

## Verification Checklist

- [ ] OIDC provider created in AWS IAM
- [ ] GitHub Actions role created with ECR + SNS permissions
- [ ] GitHub secrets configured (AWS_ROLE_ARN, EC2_SSH_KEY, SNS_TOPIC_ARN)
- [ ] CI workflow runs on PR and passes
- [ ] CD workflow runs on push and deploys successfully
- [ ] Docker image tagged with commit SHA
- [ ] Health check verifies model is loaded
- [ ] SNS notification received on success
- [ ] Auto-rollback tested with broken image
- [ ] Terraform plan comments appear on PRs with infra changes
- [ ] Terraform apply runs only on merge to main

---

## Next Phase

**Phase 8: Testing & Quality**
- Real pytest test coverage
- Integration tests against deployed API
- Data validation tests
- Performance benchmarks

See `docs/learning/phase8/` (coming next).
