# Learning Guide — AWS MLOps Migration

Practical notes from migrating a Heart Disease Prediction MLOps pipeline from local infrastructure to AWS Free Tier. Each file covers **what we did, why, the theory, and how to debug it**.

---

## Phase 1 — Infrastructure as Code

| File | Topic |
|------|-------|
| [01-terraform-on-aws.md](phase1/01-terraform-on-aws.md) | Why Terraform, module structure, state management, common errors |
| [02-aws-networking.md](phase1/02-aws-networking.md) | VPC, subnets, internet gateways, security groups, the "no default VPC" problem |
| [03-iam-roles-and-policies.md](phase1/03-iam-roles-and-policies.md) | IAM roles, instance profiles, OIDC, least privilege, policy debugging |
| [04-mlflow-on-aws.md](phase1/04-mlflow-on-aws.md) | Self-hosted MLflow with S3 + RDS, vs SageMaker MLflow, systemd services |
| [05-ec2-bootstrap.md](phase1/05-ec2-bootstrap.md) | user_data scripts, cloud-init, systemd, uv, swap, debugging boot failures |
| [06-aws-free-tier.md](phase1/06-aws-free-tier.md) | What's actually free, hidden costs (EIP!), budget alerts, hour tracking |
| [07-debugging-playbook.md](phase1/07-debugging-playbook.md) | SSH tricks, journalctl, security group debugging, RDS connectivity, S3 permissions |

## Phase 3 — Pipeline Migration & Remote State

| File | Topic |
|------|-------|
| [01-env-based-config.md](phase3/01-env-based-config.md) | 12-factor apps, os.getenv pattern, .env files, dotenv, dynamic model names |
| [02-s3-data-pipeline.md](phase3/02-s3-data-pipeline.md) | boto3 S3 integration, data resolution, S3 CLI, Makefile sync, auth |
| [03-remote-state-backend.md](phase3/03-remote-state-backend.md) | S3 + DynamoDB state backend, state locking, migration process, versioning |
| [04-uv-local-dev.md](phase3/04-uv-local-dev.md) | uv setup, venv creation, setuptools fix locally, pyproject.toml |
| [05-terraform-drift-and-safety.md](phase3/05-terraform-drift-and-safety.md) | user_data_replace_on_change, state drift, lock files, Prefect agent env vars |

---

## How to Use These

- **Before doing something** → read the relevant file to understand the theory
- **When something breaks** → check [07-debugging-playbook.md](phase1/07-debugging-playbook.md) first
- **During code review** → use as reference for "why did we do it this way"

---

## Key URLs (Your Deployment)

| Service | URL |
|---------|-----|
| MLflow UI | http://32.196.26.238:5000 |
| FastAPI (after Phase 4) | http://32.196.26.238:8000 |
| AWS Console | https://console.aws.amazon.com |
| Prefect Cloud | https://app.prefect.cloud |

## Quick SSH

```bash
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238
```
