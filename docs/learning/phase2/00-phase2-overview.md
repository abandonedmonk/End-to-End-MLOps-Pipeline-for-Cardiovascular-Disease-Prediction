# Phase 2 — MLflow on AWS (EC2 + S3 + RDS)

## Overview

Phase 2 deploys a self-hosted MLflow tracking server on AWS with persistent storage. This replaces local SQLite and laptop-only artifacts with cloud-hosted infrastructure suitable for team collaboration and production use.

## Target Architecture

```
┌─────────────┐
│  Your Code  │  (local or CI/CD)
└──────┬──────┘
       │ MLFLOW_TRACKING_URI=http://<EC2-IP>:5000
       │
       ▼
   [EC2 Instance]           [S3 Bucket]
   MLflow Server      ←→     Artifacts
   Gunicorn/MLflow         (models, plots)
       │
       │ psycopg2
       ▼
   [RDS Postgres]
   Backend Store
   (runs, metrics, params)
```

## Prerequisites

- AWS account with free tier available
- AWS CLI configured with credentials (`aws configure`)
- SSH client (pre-installed on macOS/Linux; use PuTTY or WSL on Windows)
- A public IP or dynamic DNS (for security group access rules)

## Components Deployed

| Component | AWS Service | Purpose |
|-----------|-------------|---------|
| **EC2** | t3.micro | Compute: runs MLflow server & gunicorn |
| **RDS** | db.t3.micro PostgreSQL | Backend store: runs, metrics, parameters, metadata |
| **S3** | General purpose bucket | Artifact store: model files, plots, datasets |
| **IAM Role** | EC2 instance profile | Allows EC2 to read/write S3 without keys |
| **Security Groups** | VPC | Network ACLs: restrict SSH & port 5000 to your IP |

## Key Environment Variables

Once deployed, configure these on your local machine and any CI/CD:

```bash
MLFLOW_TRACKING_URI=http://<EC2-PUBLIC-IP>:5000
MLFLOW_ARTIFACT_ROOT=s3://your-bucket-name/artifacts/
```

## Phases Within Phase 2

1. **01-aws-resources-setup.md** — Create S3, RDS, IAM, security groups, and launch EC2
2. **02-mlflow-server-setup.md** — SSH into EC2, install dependencies, configure MLflow
3. **03-systemd-service.md** — Create & enable systemd service for automatic restarts
4. **04-verification-and-troubleshooting.md** — Test MLflow UI, S3 artifacts, RDS connectivity

## Expected Outcomes

✅ MLflow UI accessible at `http://<EC2-IP>:5000`  
✅ Experiments logged to RDS (visible in UI)  
✅ Artifacts uploaded to S3 (verify via S3 console)  
✅ EC2 secured: SSH + port 5000 restricted to your IP  
✅ MLflow restarts automatically on EC2 reboot  

## Free Tier Warnings

- **EC2 public IPv4**: Costs ~$3.60/month (not free tier)
- **RDS & EC2 compute**: 750 hrs/month each — enough for 24/7 one instance
- **S3 storage**: 5 GB free — models + artifacts typically use < 1 GB
- Set an AWS Budget alert at $1 to catch unexpected charges

## Total Estimated Time

**1–2 days** depending on AWS account age and email verification delays for RDS.

---

**Next:** Start with [01-aws-resources-setup.md](01-aws-resources-setup.md)
