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

## Phase 4 — FastAPI Deployment on EC2 ✅ COMPLETE

| File | Topic |
|------|-------|
| [Phase 4 Overview](phase4/phase4-overview.md) | Where this phase fits in the project architecture |
| [01 — Containerizing for Production](phase4/01-containerizing-for-production.md) | Multi-stage Docker builds, builder vs runtime stages, build context |
| [02 — Loading Models from MLflow](phase4/02-loading-models-from-mlflow.md) | Model registry loading, champion aliases, /health endpoint, fallbacks |
| [03 — Sizing and Optimization](phase4/03-sizing-and-optimization.md) | .dockerignore, mlflow-skinny, image size reduction, ECR costs |
| [04 — Deployment to EC2](phase4/04-deployment-to-ec2.md) | **Full deployment guide**: ECR push, EC2 deploy, systemd, troubleshooting |

## Phase 5 — Prefect Agent on EC2 ✅ COMPLETE (Local Server)

| File | Topic |
|------|-------|
| [Phase 5 Overview](phase5/phase5-overview.md) | Pipeline orchestration, agent setup, what was done |
| [01 — Prefect Agent Setup](phase5/01-prefect-agent-setup.md) | Systemd service, `worker` vs `agent`, environment variables |
| [02 — Connecting to Prefect Cloud](phase5/02-connecting-to-prefect-cloud.md) | Moving from local server to Prefect Cloud coordination |
| [03 — Running Pipelines End-to-End](phase5/03-running-pipelines-end-to-end.md) | Complete workflow: trigger → execute → register → serve |
| [04 — Troubleshooting Prefect](phase5/04-troubleshooting-prefect.md) | Common errors and fixes for agent, Cloud, pipeline execution |

## Phase 6 — Monitoring with Evidently + CloudWatch ✅ COMPLETE

| File | Topic |
|------|-------|
| [Phase 6 Overview](phase6/README.md) | Architecture, quick start, verification checklist |
| [Phase 6 Implementation Summary](phase6/phase6-overview.md) | What was built, how it works, key decisions |
| [01 — Evidently Drift Detection](phase6/01-evidently-drift-detection.md) | Setting up Evidently, reference data, drift reports, S3 storage |
| [02 — CloudWatch Metrics](phase6/02-cloudwatch-metrics.md) | Custom metrics, namespace design, metric pushing from Python |
| [03 — Infrastructure Monitoring](phase6/03-infrastructure-monitoring.md) | Dashboards, alarms, SNS notifications via Terraform |
| [04 — Pipeline Integration](phase6/04-pipeline-integration.md) | Adding monitoring to Prefect flows, task design, error handling |
| [05 — Troubleshooting Monitoring](phase6/05-troubleshooting-monitoring.md) | Common errors, debugging techniques, fixes |

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
| FastAPI Health | http://32.196.26.238:8000/health |
| FastAPI Swagger | http://32.196.26.238:8000/docs |
| CloudWatch Dashboard | AWS Console → CloudWatch → Dashboards → heart-disease-mlops |
| AWS Console | https://console.aws.amazon.com |
| Prefect Cloud | https://app.prefect.cloud |

## Quick SSH

```bash
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238
```
