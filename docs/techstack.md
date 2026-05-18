# Tech Stack — AWS Free Tier MLOps

Complete inventory of every tool and service used in the pipeline, with free tier details and rationale.

---

## Pipeline Components

### 1. Experiment Tracking — MLflow (Self-Hosted)

| Detail | Value |
|--------|-------|
| **Tool** | MLflow 2.x |
| **Hosting** | Self-hosted on EC2 |
| **Backend Store** | RDS PostgreSQL (db.t3.micro) |
| **Artifact Store** | S3 bucket |
| **Access** | `http://<EC2-IP>:5000` |

**Why not SageMaker MLflow?**
SageMaker MLflow tracking server costs ~$0.10/hr ($72/month). No free tier. Self-hosted MLflow on EC2 + S3 + RDS is fully within free tier and more educational.

**Why not local SQLite?**
SQLite doesn't support concurrent access, can't run on a remote server reliably, and doesn't scale. PostgreSQL on RDS is production-grade and free for 12 months.

**RDS Configuration:**
- Engine: PostgreSQL 15.x
- Instance: db.t3.micro
- Storage: 20 GB gp2
- Single-AZ (free tier doesn't include Multi-AZ)
- Database: `mlflow`
- Public access: No (reachable only from EC2 via security group)

**MLflow Server Command:**
```bash
mlflow server \
  --backend-store-uri postgresql://mlflow:<password>@<rds-endpoint>:5432/mlflow \
  --default-artifact-root s3://heart-disease-mlops/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
```

---

### 2. Orchestration — Prefect Cloud

| Detail | Value |
|--------|-------|
| **Tool** | Prefect 3.x Cloud |
| **Agent** | Runs on EC2 |
| **Schedule** | Weekly (Sunday 00:00 UTC) |
| **Work Pool** | `heart-disease` |
| **Work Queue** | `default` |

**Why not AWS Step Functions?**
Step Functions Standard offers 4K free transitions/month (always free) and would work, but:
- Prefect is already integrated and working
- Prefect Cloud is free (10K runs/month) with zero AWS cost
- Step Functions would require rewriting all flows in ASL (Amazon States Language)
- Prefect provides better observability (UI, logs, retries)

**Why not MWAA (Managed Airflow)?**
MWAA has no free tier. Minimum cost ~$0.36/hr (~$260/month). Not viable.

**Why not self-hosted Airflow on EC2?**
Would consume the single EC2 instance's resources. Prefect Cloud offloads the orchestration layer entirely.

**Prefect Agent on EC2:**
```bash
prefect agent start --work-pool heart-disease --work-queue default
```
Runs as a systemd service, polls Prefect Cloud for scheduled runs.

---

### 3. Model Registry — MLflow Model Registry

| Detail | Value |
|--------|-------|
| **Tool** | MLflow Model Registry (built into MLflow) |
| **Storage** | S3 (artifacts) + RDS (metadata) |
| **Staging** | Alias-based ("champion" alias) |

**Why not SageMaker Model Registry?**
SageMaker Model Registry has no free tier and charges per model package group. MLflow Model Registry does the same job (versioning, stage transitions, metadata) at zero cost since it's built into MLflow.

**Workflow:**
1. `train.py` logs models as artifacts in MLflow runs
2. `register.py` finds best run by accuracy, registers model
3. `load_model.py` assigns "champion" alias to latest version
4. API server loads champion model at startup

---

### 4. Model Serving — FastAPI on EC2 (Docker)

| Detail | Value |
|--------|-------|
| **Framework** | FastAPI |
| **Container** | Docker (from ECR) |
| **Hosting** | EC2 t2.micro (same instance as MLflow) |
| **Port** | 8000 |
| **Model Loading** | Downloads from MLflow at container start |

**Why not Lambda + API Gateway?**
- Lambda has cold start latency (100ms-1s for ML models)
- 10 GB deployment package limit (Docker image may exceed)
- Requires packaging model as Lambda layer or container
- More complex setup for marginal savings

**Why not ECS Fargate?**
No free tier. ~$0.013/vCPU-hour minimum. Overkill for a single container.

**Why not SageMaker Endpoint?**
No free tier for endpoints. ml.t3.medium costs ~$0.047/hr. Overkill for this project.

**Docker on EC2:**
```bash
docker run -d \
  --name heart-api \
  -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://localhost:5000 \
  <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest
```

---

### 5. Monitoring — Evidently + CloudWatch

#### Evidently (Data & Concept Drift)

| Detail | Value |
|--------|-------|
| **Tool** | Evidently |
| **Hosting** | Cron job on EC2 |
| **Frequency** | Weekly (after pipeline run) |
| **Output** | HTML report → S3 |
| **Reference Data** | Training set snapshot in S3 |

**Checks Performed:**
- **Data Drift**: Feature distribution shift (KS test, chi-squared)
- **Concept Drift**: Prediction quality degradation over time
- **Data Quality**: Missing values, schema changes, type mismatches

**Why not SageMaker Model Monitor?**
SageMaker Model Monitor requires a SageMaker endpoint (paid) and has no free tier. Evidently is open source, works with any model, and runs on your existing EC2.

**Why not WhyLabs?**
WhyLabs free tier is limited. Evidently is fully open source with no usage limits.

#### CloudWatch (Infrastructure)

| Detail | Value |
|--------|-------|
| **Logs** | EC2 system + application logs |
| **Metrics** | CPU, memory, custom prediction metrics |
| **Dashboard** | 1 custom dashboard |
| **Alarm** | 1 alarm (CPU > 80%) |
| **Free Tier** | 5 GB logs, 10 custom metrics, 3 dashboards, 10 alarms |

**Setup:**
- Install CloudWatch Agent on EC2
- Configure log groups for MLflow, FastAPI, Prefect agent
- Create metric filter for prediction errors
- SNS topic for alarm notifications (email)

---

### 6. CI/CD — GitHub Actions

| Detail | Value |
|--------|-------|
| **Tool** | GitHub Actions |
| **Authentication** | OIDC (no stored AWS credentials) |
| **Free Tier** | 2,000 min/month (GitHub free account) |

**Why not AWS CodePipeline?**
CodePipeline V1 offers 1 free active pipeline/month (always free), but:
- GitHub Actions is already where the code lives
- OIDC integration is simpler with GitHub Actions
- 2,000 free minutes/month is generous
- CodePipeline would add another service to learn with minimal benefit

**Why OIDC instead of stored secrets?**
- No long-lived AWS access keys in GitHub
- Temporary credentials with automatic rotation
- Fine-grained IAM policies per workflow
- If repo is compromised, attacker can't extract permanent credentials

**Workflows:**

| Workflow | Trigger | Actions |
|----------|---------|---------|
| `ci.yml` | PR to main | Lint → format check → test |
| `cd.yml` | Push to main | Build Docker → push ECR → deploy to EC2 |
| `infra.yml` | Push to `infra/` | Terraform plan/apply |

---

### 7. Infrastructure as Code — Terraform

| Detail | Value |
|--------|-------|
| **Tool** | Terraform |
| **Version** | >= 1.5 |
| **State Backend** | S3 + DynamoDB (locking) |
| **Provider** | AWS (us-east-1) |

**Why not CloudFormation?**
- Terraform is cloud-agnostic (transferable skill)
- Better modularity and reusability
- Larger community and ecosystem
- Matches MLOps Zoomcamp curriculum
- HCL is more readable than YAML/JSON CloudFormation

**Why not CDK?**
- CDK generates CloudFormation under the hood
- Adds a compilation step
- Locks you into AWS-specific patterns
- Terraform is more widely used in industry

**Terraform Modules:**

| Module | Resources |
|--------|-----------|
| `ec2/` | Instance, security group, EBS, user_data, IAM instance profile |
| `rds/` | PostgreSQL instance, security group, subnet group |
| `s3/` | Bucket, versioning, lifecycle policy, IAM policy |
| `ecr/` | Repository, lifecycle policy |
| `iam/` | OIDC provider, GitHub Actions role, EC2 instance role |

---

### 8. Container Registry — ECR

| Detail | Value |
|--------|-------|
| **Tool** | Amazon ECR Private |
| **Repository** | `heart-disease-api` |
| **Free Tier** | 500 MB storage/month (12 months) |
| **Image Size** | ~300-400 MB (compressed) |

**Why ECR Private over Public?**
- Private ECR integrates with EC2 via IAM instance profile (no explicit credentials)
- Data transfer to EC2 in same region is free
- Public ECR images are publicly accessible (not appropriate for proprietary models)

**Why not Docker Hub?**
- Docker Hub free tier: 1 private repository, 200 pulls/6hrs
- ECR is native to AWS, no additional account needed
- IAM-based access control is more secure

---

### 9. Data Storage — S3

| Detail | Value |
|--------|-------|
| **Tool** | Amazon S3 |
| **Bucket** | `heart-disease-mlops-<account_id>` |
| **Free Tier** | 5 GB storage, 2K PUT, 20K GET (12 months) |
| **Structure** | Organized by purpose |

**S3 Structure:**
```
s3://heart-disease-mlops/
├── artifacts/                    # MLflow model artifacts
│   └── <experiment_id>/
│       └── <run_id>/
│           └── model/
│               ├── model.pkl
│               ├── MLmodel
│               └── ...
├── data/
│   ├── raw/
│   │   └── processed.cleveland.data
│   ├── processed/
│   │   └── processed_cleveland_data.csv
│   └── reference/
│       └── reference_data.csv    # For Evidently monitoring
├── monitoring/
│   └── reports/
│       └── <date>/
│           └── drift_report.html
└── terraform/
    └── tfstate                   # Remote state
```

---

### 10. Security — IAM + OIDC

| Detail | Value |
|--------|-------|
| **GitHub Auth** | OIDC trust relationship |
| **EC2 Auth** | IAM instance profile |
| **Local Dev** | AWS CLI with named profile |
| **Principle** | Least privilege per role |

**IAM Roles:**

| Role | Used By | Permissions |
|------|---------|-------------|
| `github-actions-deploy` | GitHub Actions OIDC | ECR push, EC2 deploy, SSM send-command |
| `ec2-mlflow-role` | EC2 instance profile | S3 read/write, ECR pull, CloudWatch logs |
| `rds-access-role` | EC2 via security group | PostgreSQL connect (port 5432) |

**OIDC Setup:**
1. Create OIDC provider in IAM for `token.actions.githubusercontent.com`
2. Create IAM role with trust policy scoped to repo + branch
3. Add GitHub secret `AWS_ROLE_ARN`
4. GitHub workflow assumes role via `aws-actions/configure-aws-credentials@v4`

---

## Complete Service Map

| # | Component | AWS Service | Free Tier Type | Free Tier Duration |
|---|-----------|-------------|----------------|-------------------|
| 1 | MLflow Server | EC2 t2.micro | 750 hrs/month | 12 months |
| 2 | MLflow Backend DB | RDS PostgreSQL db.t3.micro | 750 hrs/month + 20 GB | 12 months |
| 3 | MLflow Artifacts | S3 | 5 GB + 2K PUT / 20K GET | 12 months |
| 4 | Orchestration | Prefect Cloud | 10K runs/month | Always free |
| 5 | Model Serving | EC2 (same as #1) | Included above | 12 months |
| 6 | Container Images | ECR Private | 500 MB | 12 months |
| 7 | Drift Monitoring | Evidently on EC2 | Included in #1 | 12 months |
| 8 | Infra Monitoring | CloudWatch | 5 GB logs + 10 metrics | Always free |
| 9 | CI/CD | GitHub Actions | 2,000 min/month | Always free |
| 10 | IaC | Terraform | Open source | Always free |
| 11 | Secrets | IAM OIDC | No charge | Always free |
| 12 | Notifications | SNS | 1K emails/month | 12 months |
| 13 | Remote State | S3 + DynamoDB | Included in #3 + 25 GB + 25 WCU | 12 months |

**Monthly Cost: $0 (within free tier)**

**Post-Free-Tier Estimated Cost: ~$15-20/month**
- EC2 t2.micro: ~$8.50/month
- RDS db.t3.micro: ~$7.00/month
- S3: ~$0.25/month
- ECR: ~$0.04/month
- CloudWatch: ~$0.50/month

---

## Software Stack

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12 | Runtime |
| MLflow | 2.13.0 | Experiment tracking + model registry |
| Prefect | 3.4.10 | Workflow orchestration |
| FastAPI | 0.116.1 | Model serving API |
| scikit-learn | 1.4.2 | Model training (LR, RF, DT, HGB) |
| XGBoost | (to be added) | Gradient boosting model |
| pandas | 2.2.2 | Data manipulation |
| NumPy | 1.26.4 | Numerical computation |
| Pydantic | 2.11.7 | Input validation |
| Evidently | (to be added) | Data drift monitoring |
| boto3 | (to be added) | AWS SDK |
| psycopg2 | (to be added) | PostgreSQL adapter |
| Docker | Latest | Containerization |
| Terraform | >= 1.5 | Infrastructure as code |
| pytest | 8.4.1 | Testing |
| flake8 | (via setup.cfg) | Linting |
| black | (via pyproject.toml) | Code formatting |
| isort | (via pyproject.toml) | Import sorting |
