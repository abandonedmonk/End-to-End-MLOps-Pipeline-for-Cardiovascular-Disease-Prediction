# Learning Guide — AWS MLOps Migration

Practical notes from migrating a Heart Disease Prediction MLOps pipeline from local infrastructure to AWS Free Tier. Each file covers **what we did, why, the theory, and how to debug it**.

---

## Files

| File | Topic |
|------|-------|
| [01-terraform-on-aws.md](01-terraform-on-aws.md) | Why Terraform, module structure, state management, common errors |
| [02-aws-networking.md](02-aws-networking.md) | VPC, subnets, internet gateways, security groups, the "no default VPC" problem |
| [03-iam-roles-and-policies.md](03-iam-roles-and-policies.md) | IAM roles, instance profiles, OIDC, least privilege, policy debugging |
| [04-mlflow-on-aws.md](04-mlflow-on-aws.md) | Self-hosted MLflow with S3 + RDS, vs SageMaker MLflow, systemd services |
| [05-ec2-bootstrap.md](05-ec2-bootstrap.md) | user_data scripts, cloud-init, systemd, uv, swap, debugging boot failures |
| [06-aws-free-tier.md](06-aws-free-tier.md) | What's actually free, hidden costs (EIP!), budget alerts, hour tracking |
| [07-debugging-playbook.md](07-debugging-playbook.md) | SSH tricks, journalctl, security group debugging, RDS connectivity, S3 permissions |

---

## How to Use These

- **Before doing something** → read the relevant file to understand the theory
- **When something breaks** → check [07-debugging-playbook.md](07-debugging-playbook.md) first
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
ssh -i ~/.ssh/id_ed25519 ubuntu@32.196.26.238
```
