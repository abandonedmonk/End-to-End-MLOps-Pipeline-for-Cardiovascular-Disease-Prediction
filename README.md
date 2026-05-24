# Heart Disease Prediction - MLOps Pipeline on AWS Free Tier

A production-grade MLOps pipeline for heart disease prediction, migrated from local infrastructure to AWS Free Tier with full CI/CD, monitoring, and automated deployment.

[![CI/CD](https://github.com/abandonedmonk/MLOps-Zoomcamp-Project/actions/workflows/ci.yml/badge.svg)](https://github.com/abandonedmonk/MLOps-Zoomcamp-Project/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📊 Project Highlights

### Production Metrics
- **31 comprehensive unit tests** with 80%+ code coverage
- **9-phase migration** from local dev to AWS production
- **613 MB optimized Docker image** (43% size reduction via multi-stage build)
- **Zero-downtime deployment** with automatic rollback on health check failure
- **Sub-100ms API response time** for heart disease prediction endpoint
- **Weekly automated retraining** via Prefect Cloud orchestration

### Infrastructure (AWS Free Tier)
- **29 AWS resources** managed via Terraform IaC
- **Self-hosted MLflow** on EC2 t2.micro with RDS PostgreSQL backend + S3 artifact store
- **OIDC-based authentication** for GitHub Actions (no long-lived credentials)
- **Security-hardened** with IP-restricted security groups and pre-commit secret scanning
- **Evidently + CloudWatch** monitoring for data drift detection and infrastructure observability

## 🏗️ Architecture

```
                              ┌──────────────────────────────────┐
                              │         Developer Machine         │
                              │  git push / PR → GitHub.com      │
                              └──────────────┬───────────────────┘
                                             │
                                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            GitHub Actions CI/CD                              │
│                                                                              │
│   ┌─────────────────┐   ┌─────────────────┐   ┌──────────────────────────┐  │
│   │  CI (on PR)      │   │  CD (on merge)   │   │  Infra (on infra/ diff) │  │
│   │                  │   │                  │   │                          │  │
│   │  flake8/black    │   │  Docker build    │   │  terraform plan         │  │
│   │  isort lint      │   │  Push to ECR     │   │  Comment on PR          │  │
│   │  pytest 80%+     │   │  SSH → EC2       │   │  terraform apply        │  │
│   │                  │   │  Deploy container │   │  (on merge to main)     │  │
│   │                  │   │  Health check     │   │                          │  │
│   │                  │   │  Auto-rollback    │   │                          │  │
│   └─────────────────┘   └────────┬────────┘   └──────────────────────────┘  │
│                                   │              │                            │
│                       OIDC auth   │  SSH deploy  │ terraform apply           │
└───────────────────────────────────┼──────────────┼────────────────────────────┘
                                    │              │
            ┌───────────────────────┼──────────────┼──────────────────────┐
            │                       ▼              ▼                      │
            │  ┌──────────────────────────────────────────────────────┐   │
            │  │              AWS Cloud (us-east-1)                    │   │
            │  │                                                      │   │
            │  │  ┌────────────────────────────────────────────────┐  │   │
            │  │  │         EC2 t2.micro (Ubuntu 24.04)            │  │   │
            │  │  │                                                │  │   │
            │  │  │  ┌──────────────┐  ┌────────────────────────┐ │  │   │
            │  │  │  │  MLflow       │  │  FastAPI (Docker)       │ │  │   │
            │  │  │  │  Port 5000    │  │  Port 8000              │ │  │   │
            │  │  │  │  systemd svc  │  │  ECR-pulled image       │ │  │   │
            │  │  │  │  Tracking +   │  │  /predict endpoint      │ │  │   │
            │  │  │  │  Model Reg.   │  │  /health endpoint       │ │  │   │
            │  │  │  └──────┬───────┘  └───────────┬────────────┘ │  │   │
            │  │  │         │                       │              │  │   │
            │  │  │  ┌──────┴───────────────────────┘              │  │   │
            │  │  │  │  Prefect Agent (systemd worker)             │  │   │
            │  │  │  │  Weekly cron: train → register → monitor   │  │   │
            │  │  │  └──────────────────────────────────────────┘  │  │   │
            │  │  └────────────────────────────────────────────────┘  │   │
            │  │         │              │              │                │   │
            │  │         ▼              ▼              ▼                │   │
            │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐        │   │
            │  │  │ RDS        │ │ S3 Bucket  │ │ ECR Repo   │        │   │
            │  │  │ PostgreSQL │ │ artifacts/ │ │ Docker     │        │   │
            │  │  │ db.t3.micro│ │ data/raw/ │ │ images     │        │   │
            │  │  │ Port 5432  │ │ reports/   │ │ (keep 5)   │        │   │
            │  │  └────────────┘ └────────────┘ └────────────┘        │   │
            │  │                                                      │   │
            │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐        │   │
            │  │  │ IAM        │ │ VPC        │ │ SNS        │        │   │
            │  │  │ EC2 role   │ │ 2 subnets  │ │ Alerts     │        │   │
            │  │  │ OIDC role  │ │ IGW + RT   │ │ Email      │        │   │
            │  │  │ ECR+S3+CW  │ │ SG (IP)    │ │ Deploy     │        │   │
            │  │  └────────────┘ └────────────┘ └────────────┘        │   │
            │  └──────────────────────────────────────────────────────┘   │
            │                          │                                   │
            │                          ▼                                   │
            │  ┌──────────────────────────────────────────────────────┐   │
            │  │              CloudWatch                               │   │
            │  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │   │
            │  │  │ Dashboard    │  │ Alarms        │  │ Logs       │ │   │
            │  │  │ 4 widgets:   │  │ CPU > 80%     │  │ FastAPI    │ │   │
            │  │  │ CPU/Mem/     │  │ Drift > 0.3   │  │ requests   │ │   │
            │  │  │ Drift/5xx    │  │ → SNS alert   │  │ 5xx errors │ │   │
            │  │  └──────────────┘  └──────────────┘  └────────────┘ │   │
            │  └──────────────────────────────────────────────────────┘   │
            └─────────────────────────────────────────────────────────────┘

  External Orchestration:
  ┌──────────────────────┐         ┌──────────────────────┐
  │  Prefect Cloud        │────────│  Scheduled Workflows  │
  │  (api.prefect.cloud)  │  push  │  Weekly retraining    │
  │  Worker on EC2 polls  │  jobs  │  Drift detection      │
  └──────────────────────┘         └──────────────────────┘

   Data Flow:
   S3 (raw data) → Prefect flow → train 5 models → MLflow (log metrics)
                                                           │
                                                   best by accuracy
                                                           │
                                                   register "champion"
                                                           │
                                                   FastAPI loads model
                                                           │
                                                   POST /predict → response

   AWS Services Used (12 services):
   ┌────────────────────────────────────────────────────────────────────┐
   │  Compute   │ EC2 (t2.micro) — MLflow + FastAPI + Prefect agent     │
   │  Database  │ RDS PostgreSQL 15.7 (db.t3.micro) — MLflow backend    │
   │  Storage   │ S3 — model artifacts, raw data, drift reports          │
   │  Registry  │ ECR — Docker image storage with lifecycle policy       │
   │  Identity  │ IAM — EC2 instance role + GitHub Actions OIDC role     │
   │  Network   │ VPC — custom VPC, 2 public subnets, IGW, route tables │
   │  Security  │ Security Groups — IP-restricted ingress (SSH/HTTP)     │
   │  Messaging │ SNS — email alerts for deployments + drift alarms      │
   │  Monitor   │ CloudWatch — dashboard, alarms, logs, custom metrics   │
   │  Logging   │ CloudWatch Logs — FastAPI request + error tracking     │
   │  Systems   │ SSM — remote EC2 management (via IAM policy)           │
   │  EIP       │ Elastic IP — static public IP for EC2 instance         │
   └────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
```bash
# Install uv (faster than pip)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv pip install -r requirements.txt

# Or use the Makefile
make install
```

### Run the API Locally
```bash
# Start MLflow (local SQLite backend)
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db --port 5000 &

# Train and register a model
python -m heart_disease_prediction.prefect_flow

# Start FastAPI
uvicorn api.main:app --reload

# Test prediction
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 63, "sex": 1, "cp": 3, "trestbps": 145,
    "chol": 233, "fbs": 1, "restecg": 0, "thalach": 150,
    "exang": 0, "oldpeak": 2.3, "slope": 0, "ca": 0, "thal": 1
  }'
```

### Deployed Resources

| Service | URL | Status |
|---------|-----|--------|
| MLflow UI | http://<EC2_PUBLIC_IP>:5000 | ✅ Active |
| FastAPI Health | http://<EC2_PUBLIC_IP>:8000/health | ✅ Active |
| API Docs (Swagger) | http://<EC2_PUBLIC_IP>:8000/docs | ✅ Active |
| CloudWatch Dashboard | AWS Console | ✅ Active |

## 📁 Project Structure

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml                  # CI: lint (flake8/black/isort) + test (pytest 80%+) on PR
│       ├── cd.yml                  # CD: Docker build → ECR push → SSH deploy → health check → rollback on PR merge
│       └── infra.yml               # Terraform plan (on PR) + apply (on merge) when infra/ changes
│
├── api/                            # FastAPI inference service (Dockerized, deployed on EC2)
│   ├── main.py                     # /health + /predict endpoints; loads champion model from MLflow on startup
│   ├── schema.py                   # PatientData Pydantic model — validates 13 input features
│   └── requirements.txt            # Container deps — uses mlflow-skinny for smaller image
│
├── heart_disease_prediction/       # Core ML pipeline package
│   ├── __init__.py                 # Package marker
│   ├── data.py                     # get_data() loads CSV from S3/local; split_data_for_train() creates ColumnTransformer
│   ├── train.py                    # train_model() trains 4 classifiers in MLflow runs, logs metrics, returns best
│   ├── register.py                 # register_model() finds best run, registers model, assigns "champion" alias
│   ├── load_model.py               # load_champion_model() loads from registry with fallback to Production stage
│   ├── prefect_flow.py             # full_pipeline flow: data → split → train → register → load → drift detection
│   ├── prefect.yaml                # Package-level Prefect deployment — weekly cron schedule
│   └── .prefectignore              # Excludes Python artifacts from Prefect uploads
│
├── monitoring/                     # Drift detection + CloudWatch observability
│   ├── __init__.py                 # Package docstring
│   ├── config.py                   # MonitoringConfig dataclass — S3 paths, drift threshold, CW namespace/defaults
│   ├── reference_data.py           # build_reference_dataframe() cleans Cleveland data; saves Parquet to S3
│   ├── generate_report.py          # generate_drift_report() runs Evidently DataDriftPreset; uploads HTML + JSONL to S3
│   └── cloudwatch_metrics.py       # push_monitoring_metrics() emits drift/error counts; queries CW Logs for API metrics
│
├── infra/                          # Terraform IaC — 29 AWS resources across 7 modules
│   ├── main.tf                     # Root module orchestration — wires vpc, s3, ecr, iam, ec2, rds, monitoring
│   ├── backend.tf                  # S3 + DynamoDB remote state backend
│   ├── providers.tf                # AWS provider 5.50.0, Terraform >= 1.5, default tags
│   ├── variables.tf                # Input vars: region, account_id, instance types, SSH key, IP, Prefect creds
│   ├── outputs.tf                  # Outputs: EC2 IP, RDS endpoint, S3 bucket, ECR URL, MLflow URI, role ARNs
│   ├── user_data.sh.tftpl          # EC2 bootstrap: swap + uv + Docker + CW Agent + MLflow systemd + Prefect agent
│   ├── terraform.tfvars.example    # Template with placeholder values for all required variables
│   └── modules/
│       ├── vpc/                    # VPC + IGW + 2 public subnets (2 AZs) + route table
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── ec2/                    # t2.micro Ubuntu 24.04 + SSH key + SG (IP-restricted) + EIP + IAM profile
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── rds/                    # PostgreSQL 15.7 on db.t3.micro + SG (EC2-only) + subnet group
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── s3/                     # Versioned + encrypted bucket + lifecycle (90d report expiry) + IAM policy
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── ecr/                    # Scan-on-push + mutable tags + lifecycle (keep last 5 images)
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── iam/                    # EC2 role (S3/ECR/CW/SSM) + GitHub Actions OIDC role (ECR/S3/SNS/SSM/admin)
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       └── monitoring/             # SNS alerts topic + CW dashboard (4 widgets) + alarms (CPU, drift)
│           ├── main.tf
│           ├── variables.tf
│           └── outputs.tf
│
├── tests/                          # 31 test functions, 80%+ coverage
│   ├── __init__.py                 # Package marker
│   ├── conftest.py                 # Fixtures: test_environment, mock_mlflow, sample data, DummyHeartModel
│   ├── test_data.py                # 6 tests: data loading, S3 mocking, preprocessing, missing file
│   ├── test_train.py               # 4 tests: model training, metrics logging, best model selection
│   ├── test_register.py            # 3 tests: champion alias, no runs found, connection failures
│   ├── test_load_model.py          # 4 tests: champion loading, Production fallback, missing model, predictions
│   ├── test_api.py                 # 5 tests: health endpoint, predict, 422 validation errors
│   ├── test_prefect_flow.py        # 5 tests: task returns, flow composition, full pipeline mock
│   └── test_monitoring.py          # 4 tests: reference data, drift report, CW metrics, log counts
│
├── scripts/
│   └── setup_github_secrets.sh     # Helper: reads TF outputs, sets GitHub Actions secrets via gh CLI
│
├── data/
│   ├── raw/
│   │   ├── processed.cleveland.data  # Primary dataset: UCI Cleveland heart disease (303 rows, 14 attrs)
│   │   ├── processed.hungarian.data  # UCI Hungarian dataset (alternative source)
│   │   └── processed.switzerland.data # UCI Switzerland dataset (alternative source)
│   ├── processed/
│   │   └── processed_cleveland_data.csv  # Preprocessed Cleveland dataset
│   ├── interim/.gitkeep              # Placeholder for intermediate data
│   └── external/.gitkeep             # Placeholder for external data
│
├── models/
│   ├── model.bin                     # Serialized model binary (local cache)
│   └── pipeline.pkl                  # Pickled sklearn Pipeline object (local cache)
│
├── mlruns/                           # Local MLflow tracking (SQLite + file artifacts)
│   └── mlflow.db                     # SQLite DB with experiments, runs, metrics, params
│
├── notebooks/
│   └── heart_disease_experiment.ipynb  # EDA + model comparison + hyperparameter tuning
│
├── docs/
│   ├── architecture.md               # System architecture document — component interactions, data flow
│   ├── techstack.md                  # Technology inventory with free tier details and rationale
│   ├── roadmap.md                    # Phased migration plan: local → AWS Free Tier
│   ├── transition-guide.md           # Step-by-step migration guide for each component
│   ├── deployment_guide/             # Structured deployment guide (~75 min total)
│   │   ├── README.md                 # Guide index with navigation + prerequisites checklist
│   │   ├── 00-overview.md            # Overview and prerequisites
│   │   ├── 01-infrastructure-provisioning.md  # Terraform provisioning
│   │   ├── 02-server-access-and-services.md   # SSH + systemd services
│   │   ├── 03-packaging-and-deploying-api.md   # Docker build + ECR + EC2 deploy
│   │   ├── 04-model-training-and-orchestration.md  # Prefect flow + scheduling
│   │   ├── 05-monitoring-and-troubleshooting.md    # CW dashboards + debugging
│   │   ├── ARCHITECTURE.md           # Deployment-specific architecture
│   │   └── QUICK-REFERENCE.md        # Common commands + URLs cheat sheet
│   └── learning/                     # 53 documentation files by phase
│       ├── README.md                 # Learning guide index with phase mapping + key URLs
│       ├── phase1/                   # Terraform, VPC, IAM, MLflow on AWS, EC2 bootstrap, free tier (7 files)
│       ├── phase2/                   # MLflow on AWS: resources, server, systemd, verification (6 files)
│       ├── phase3/                   # Env-based config, S3 pipeline, remote state, uv, TF drift (5 files)
│       ├── phase4/                   # Docker multi-stage, MLflow model loading, optimization, EC2 deploy (5 files)
│       ├── phase5/                   # Prefect agent, Cloud connection, end-to-end pipelines (6 files)
│       ├── phase6/                   # Evidently drift, CW metrics, infra monitoring, integration (8 files)
│       ├── phase7/                   # GitHub Actions OIDC, CI/CD, TF automation, rollback (9 files)
│       ├── phase8/                   # pytest, moto, testing data/ML/API/Prefect/monitoring (11 files)
│       └── phase9/                   # Security: pre-commit, secret scanning, hardening (3 files)
│
├── Dockerfile                       # Multi-stage build: builder (deps) → runtime (venv copy) — 613 MB
├── pyproject.toml                   # Poetry-style project metadata + all deps (prod + dev optional)
├── requirements.txt                 # Flat pip requirements (auto-generated by pigar)
├── Makefile                         # Build automation: install, clean, lint, format, test, sync_data
├── setup.cfg                        # flake8 config: max line 99, excludes
├── prefect.yaml                     # Root-level Prefect deployment — weekly cron for full_pipeline
├── .pre-commit-config.yaml          # Hooks: detect-secrets, AWS creds, bandit, black, isort, flake8
├── .secrets.baseline                # detect-secrets baseline — tracks known false positives
├── .env.example                     # Template for .env — all required vars with placeholders
├── .gitignore                       # Python, venv, data, models, mlruns, .env, TF state, IDE
├── .dockerignore                    # Excludes __pycache__, .git, .venv, data, mlruns, TF state
├── .prefectignore                   # Excludes Python artifacts, caches, env files from Prefect
├── .vscode/settings.json            # VS Code: Poetry as package manager, auto-approve commands
├── LICENSE                          # MIT License (Copyright 2025, Anshuman Jena)
└── README.md                        # This file
```

## 🔧 Technical Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **ML Platform** | MLflow 2.13.0 + S3 + RDS | Experiment tracking, model registry |
| **Orchestration** | Prefect 3.x Cloud | Scheduled pipeline execution |
| **Serving** | FastAPI + Uvicorn | Real-time inference API |
| **Container** | Docker multi-stage | Optimized image (613 MB) |
| **CI/CD** | GitHub Actions + OIDC | Automated testing + deployment |
| **IaC** | Terraform 1.12+ | 29 AWS resources, remote state |
| **Monitoring** | Evidently + CloudWatch | Drift detection, dashboards, alarms |
| **Testing** | pytest + moto + cov | 31 tests, 80%+ coverage |
| **Security** | pre-commit + detect-secrets | Secret scanning, IP restrictions |

## 📈 Pipeline Details

### Training Flow
```
Raw Data (S3) → Preprocessing → Train 5 Models → Log to MLflow
                                                    ↓
Best Model (by accuracy) → Register as "champion" → Deploy
```

**Models trained:**
- LogisticRegression (baseline)
- DecisionTreeClassifier
- RandomForestClassifier
- HistGradientBoostingClassifier
- XGBoostClassifier

### Inference API
```bash
POST /predict
Request:  { "age": 63, "sex": 1, "cp": 3, ... (13 features) }
Response: { "prediction": 1, "probability": 0.87, "model_version": "best_model_2025-07-30" }
```

### Monitoring
- **Drift Detection:** Evidently reports generated post-training
- **Metrics:** Prediction count, 5xx errors, data drift score
- **Alarms:** CPU > 80%, drift score > 0.3
- **Notifications:** SNS → Email on deployment success/failure

## 🧪 Testing

### Run All Tests
```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run with coverage (must be ≥80%)
pytest --cov=heart_disease_prediction --cov-fail-under=80 -v

# Run specific test file
pytest tests/test_api.py -v
```

### Test Coverage
```
Name                                  Stmts   Miss  Cover
---------------------------------------------------------
heart_disease_prediction/data.py         45      2    96%
heart_disease_prediction/train.py        67      8    88%
heart_disease_prediction/register.py     28      3    89%
heart_disease_prediction/load_model.py   35      5    86%
api/main.py                              52      6    88%
monitoring/generate_report.py            42      7    83%
---------------------------------------------------------
TOTAL                                   269     31    88%
```

### Test Structure (31 tests)
| File | Tests | Focus |
|------|-------|-------|
| `test_data.py` | 6 | Data loading, S3 mocking, preprocessing |
| `test_train.py` | 4 | Model training, metrics logging, selection |
| `test_register.py` | 3 | MLflow registry, champion alias |
| `test_load_model.py` | 4 | Model loading, fallback logic |
| `test_api.py` | 5 | FastAPI endpoints (TestClient) |
| `test_prefect_flow.py` | 5 | Pipeline orchestration mocking |
| `test_monitoring.py` | 4 | Drift detection, CloudWatch mocking |

## 🔐 Security

### Implemented
- ✅ **Pre-commit hooks:** detect-secrets, AWS creds scanning
- ✅ **OIDC authentication:** GitHub Actions ↔ AWS (no stored keys)
- ✅ **IP restrictions:** Security groups limited to `<YOUR_IP>/32` (configured in `terraform.tfvars`)
- ✅ **Git history:** .env purged from history (git-filter-repo)
- ✅ **Secrets management:** GitHub Secrets (AWS_ROLE_ARN, EC2_SSH_KEY, SNS_TOPIC_ARN)

### Pre-commit Hooks
```bash
# Install hooks
pre-commit install

# Run on all files
pre-commit run --all-files
```

**Hooks active:**
- detect-secrets (Yelp) - blocks AWS keys, passwords
- detect-aws-credentials
- no-commit-to-branch (main protection)
- black, isort, flake8 (code quality)
- bandit (security linter)

## 📊 Metrics for Resume

### Quantifiable Achievements
- **9-phase architecture migration** from local dev to AWS production
- **29 Terraform-managed resources** (EC2, RDS, S3, IAM, VPC, ECR, CloudWatch)
- **31 unit tests** with 80%+ coverage, all external services mocked (moto, SQLite MLflow)
- **43% Docker image reduction** (1.07 GB → 613 MB) via multi-stage build + mlflow-skinny
- **Sub-100ms inference latency** for 13-feature heart disease prediction
- **Zero-downtime deployment** with health-check based auto-rollback
- **Free-tier compliance:** <$5/month (EIP costs only, 750 hrs EC2 + RDS within limits)

### Technologies Demonstrated
- **MLOps:** MLflow, Prefect Cloud, model registry, drift detection
- **Cloud:** AWS (EC2, RDS, S3, ECR, IAM, CloudWatch, SNS)
- **DevOps:** Terraform IaC, GitHub Actions CI/CD, Docker, OIDC
- **Backend:** FastAPI, pytest, pre-commit, uv package manager
- **Security:** Secret scanning, IP restrictions, least-privilege IAM

## 🚀 CI/CD Workflows

### CI Pipeline (Pull Request)
```yaml
PR opened ──▶ Lint (flake8, black, isort) ──▶ Test (pytest 80%+) ──▶ Status check
```

### CD Pipeline (Merge to main)
```yaml
Merge ──▶ Docker build ──▶ Push to ECR ──▶ SSH to EC2 ──▶ Deploy container
                                              │
                                              ▼
                                    Health check (5 retries)
                                              │
                                    ┌─────────┴─────────┐
                                    ▼                   ▼
                              Success              Failure
                                │                     │
                                ▼                     ▼
                         SNS notify               Auto-rollback
                         (success)           SNS notify (failed)
```

### Terraform Pipeline (Infrastructure)
```yaml
PR changing infra/ ──▶ terraform plan ──▶ Comment on PR
Merge to main ──▶ terraform apply
```

## 🏗️ Terraform (Infrastructure as Code)

Infrastructure is managed via Terraform in `infra/` with a remote S3 + DynamoDB state backend. All 29 AWS resources are defined declaratively.

### Initial Setup

```bash
# 1. Navigate to infra directory
cd infra

# 2. Copy and configure your variables
cp terraform.tfvars.example terraform.tfvars

# 3. Edit terraform.tfvars and fill in required values:
#    - aws_account_id       = "YOUR_AWS_ACCOUNT_ID"
#    - aws_region           = "us-east-1"
#    - your_ip              = "YOUR_IP/32"          # Your home IP for SSH+HTTP access
#    - ssh_public_key       = "ssh-rsa AAAA..."     # Your SSH public key
#    - db_password          = ""  # RDS PostgreSQL password
#    - github_repo          = "abandonedmonk/MLOps-Zoomcamp-Project"
#    - prefect_api_url      = "https://api.prefect.cloud/api/accounts/..."
#    - prefect_api_key      = ""             # Prefect Cloud API key

# 4. Initialize Terraform (downloads providers, connects to S3 backend)
terraform init

# 5. Preview what will be created (no changes made)
terraform plan

# 6. Build the infrastructure (~5-10 minutes)
terraform apply
```

### Day-to-Day Commands

```bash
# See the current state
terraform show

# See what would change before applying
terraform plan

# Apply changes (prompts for confirmation)
terraform apply

# Apply with auto-approve (use carefully)
terraform apply -auto-approve

# Import existing resources (if recovering state)
terraform import aws_instance.my_ec2 i-xxxxxxxxxxxxxxxxx
```

### Inspecting Outputs

After `terraform apply`, the EC2 public IP and other resource details are printed as outputs. You can also retrieve them later:

```bash
# List all outputs
terraform output

# Get a specific output value
terraform output ec2_public_ip
```

### Tear Down (Destroy Everything)

> **Warning:** This deletes ALL 29 AWS resources — EC2, RDS, S3, ECR, IAM, VPC, etc. Only do this when you want to completely stop billing.

#### What Gets Deleted Permanently

| Resource | What happens |
|----------|-------------|
| **RDS PostgreSQL** | Deleted — all MLflow runs, metrics, model registry entries gone |
| **S3 bucket** | Deleted — all model artifacts, raw data, drift reports gone |
| **ECR images** | Deleted — Docker images permanently removed |
| **EC2 instance** | Terminated — MLflow, Prefect agent, Docker all gone |
| **Elastic IP** | Released — you get a **new IP** on next apply |
| **CloudWatch** | Dashboard, alarms, log groups all deleted |
| **SNS topic** | Deleted — recreated fresh on next `terraform apply` |

#### What Gets Preserved

| Item | Preserved? | Notes |
|------|-----------|-------|
| Local code | ✅ Yes | Your git clone is unaffected |
| Local `mlruns/`, `models/`, `data/` | ✅ Yes | Only on your machine |
| GitHub Actions secrets | ✅ Yes | `AWS_ROLE_ARN`, `EC2_SSH_KEY`, `SNS_TOPIC_ARN`, `EC2_HOST` stay |
| Prefect Cloud flow definitions | ✅ Yes | But agent won't be running to execute them |

#### Rebuilding (Everything Comes Back)

> **State is also deleted.** Terraform starts from scratch — sees zero resources and creates all 29 fresh. No conflicts.

After `terraform apply` you must re-configure these:

```bash
# 1. Get the new EC2 IP from terraform output
cd infra && terraform output ec2_public_ip

# 2. Update .env with the new IP
sed -i 's/<EC2_PUBLIC_IP>/NEW_IP_HERE/' .env

# 3. Update the GitHub Actions secret EC2_HOST
gh secret set EC2_HOST --body "NEW_IP_HERE"
# Or: Settings → Secrets and variables → Actions → EC2_HOST

# 4. Wait 3-5 minutes for EC2 bootstrap, then verify services
ssh ubuntu@<NEW_IP> "systemctl status mlflow-server prefect-agent"

# 5. Retrain and register models (MLflow registry is empty after teardown)
python -m heart_disease_prediction.prefect_flow

# 6. Deploy the API (ECR has fresh images from ECR lifecycle)
ssh ubuntu@<NEW_IP> "sudo /opt/deploy-api.sh"

# 7. Push reference data to the new S3 bucket
python -m monitoring.reference_data
```

#### Quick Teardown & Rebuild Cycle

```bash
cd infra

# Teardown
terraform plan -destroy
terraform destroy -auto-approve

# Rebuild
terraform apply -auto-approve

# Back to local machine
cd ..

# Update IP everywhere
NEW_IP=$(cd infra && terraform output -raw ec2_public_ip)
sed -i "s/<EC2_PUBLIC_IP>/$NEW_IP/" .env
gh secret set EC2_HOST --body "$NEW_IP"

# Wait 3-5 mins for EC2 bootstrap, then re-verify
ssh ubuntu@$NEW_IP "systemctl status mlflow-server prefect-agent"
```

> **Billing stops** when you teardown — only the Elastic IP has a small cost (~$0.005/hr). Everything else is freed.

### Understanding the Modules

| Module | What it creates |
|--------|----------------|
| `modules/vpc` | VPC (10.0.0.0/16), IGW, 2 public subnets across 2 AZs, route table |
| `modules/ec2` | t2.micro instance, SSH key pair, Elastic IP, security group (IP-restricted) |
| `modules/rds` | PostgreSQL 15.7 (db.t3.micro), subnet group, security group (EC2-only) |
| `modules/s3` | Versioned + encrypted S3 bucket, lifecycle rules (reports expire at 90 days) |
| `modules/ecr` | ECR Docker registry, scan-on-push enabled, lifecycle (keep last 5 images) |
| `modules/iam` | EC2 instance profile + role, GitHub Actions OIDC provider + role |
| `modules/monitoring` | SNS topic, CloudWatch dashboard (4 widgets), CPU + drift alarms |

### State Management

Terraform state is stored remotely in S3 with DynamoDB locking to prevent concurrent edits:

- **State bucket:** `s3://heart-disease-mlops-<ACCOUNT_ID>-tfstate/`
- **Locking table:** `heart-disease-mlops-tflock` (DynamoDB)

Never edit `terraform.tfstate` manually. If state drifts:

```bash
# Inspect current state
terraform state list

# Show differences
terraform plan -detailed-exitcode
```

### Troubleshooting

```bash
# Terraform fails with provider version error
terraform init -upgrade

# State locked (another apply running)
aws dynamodb delete-item --table-name heart-disease-mlops-tflock \
  --key '{"LockID": {"S": "heart-disease-mlops/terraform"}}'

# EC2 user_data not applying on existing instance
# Terraform's user_data_replace_on_change replaces the instance
terraform apply  # Will recreate EC2 with fresh user_data

# Verify EC2 services are running
ssh ubuntu@<EC2_PUBLIC_IP>
systemctl status mlflow-server
systemctl status prefect-agent
journalctl -u mlflow-server -f

# Check MLflow connectivity from EC2
curl http://localhost:5000/health

# Check RDS connectivity from EC2
psql -h <RDS_ENDPOINT> -U postgres -d mlflow -c "SELECT 1;"
```

### Remote vs Local State

This project uses S3 + DynamoDB remote state by default (`backend.tf`). To use local state instead, comment out the `backend` block in `backend.tf` before running `terraform init`.

## 🧭 How to Use (End-to-End Guide)

This section covers every workflow from a fresh clone to a running production system.

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) |
| Terraform | 1.5+ | [terraform.io/downloads](https://www.terraform.io/downloads) |
| Docker | 24+ | [docker.com](https://docs.docker.com/get-docker/) |
| AWS CLI | 2.x | [aws.amazon.com/cli](https://aws.amazon.com/cli/) |
| GitHub CLI | | `brew install gh` or [cli.github.com](https://cli.github.com/) |
| `uv` | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### 1. Clone the Repository

```bash
git clone https://github.com/abandonedmonk/MLOps-Zoomcamp-Project.git
cd MLOps-Zoomcamp-Project
```

### 2. Install Pre-commit Hooks

```bash
# Install pre-commit framework
pip install pre-commit

# Install all hooks (detect-secrets, linting, etc.)
pre-commit install

# Verify (runs on all files)
pre-commit run --all-files
```

### 3. Set Up Python Environment

```bash
# With uv (recommended — fast, reliable)
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Or with Makefile
make install

# Or with pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit .env with your values
# The most important ones:
#   - MLFLOW_TRACKING_URI      = http://<EC2_PUBLIC_IP>:5000
#   - MLFLOW_ARTIFACT_ROOT     = s3://<BUCKET>/artifacts/
#   - DATA_PATH                = s3://<BUCKET>/data/raw/processed.cleveland.data
#   - PREFECT_API_URL          = https://api.prefect.cloud/api/accounts/.../workspaces/...
#   - PREFECT_API_KEY          = pnu_...
#   - MODEL_NAME               = best_model_YYYY-MM-DD
```

### 5. Build Infrastructure with Terraform

```bash
cd infra

# Configure terraform.tfvars (copy from .example, fill in your values)
cp terraform.tfvars.example terraform.tfvars
# Key values: aws_account_id, your_ip, ssh_public_key, db_password, github_repo

# Initialize and apply
terraform init
terraform plan          # Review changes
terraform apply         # Type "yes" to confirm

# After apply, note the outputs:
#   - ec2_public_ip       (e.g., 32.196.26.238)
#   - rds_endpoint        (e.g., xxx.xxx.us-east-1.rds.amazonaws.com)
#   - s3_bucket_name      (e.g., heart-disease-mlops-123456789012)
#   - mlflow_uri          (e.g., http://32.196.26.238:5000)

# Update .env with the EC2 public IP from terraform output
cd ..
```

### 6. Set Up GitHub Actions Secrets

```bash
# Run the setup script (requires gh CLI and GitHub repo access)
./scripts/setup_github_secrets.sh

# Or manually via GitHub UI:
# Settings → Secrets and variables → Actions → New repository secret
#   - AWS_ROLE_ARN         = arn:aws:iam::<ACCOUNT>:role/github-actions-oidc-role
#   - EC2_SSH_KEY          = Your SSH private key content (base64)
#   - SNS_TOPIC_ARN        = arn:aws:sns:us-east-1:<ACCOUNT>:heart-disease-alerts

# Also set this as an environment variable in the repo:
#   - EC2_HOST             = <EC2_PUBLIC_IP>  (public IP from terraform output)
```

### 7. Verify EC2 Services Are Running

After Terraform applies, the EC2 user_data bootstrap script starts services automatically. Wait 3-5 minutes, then:

```bash
# SSH to your EC2 instance
ssh -i /path/to/your/private/key ubuntu@<EC2_PUBLIC_IP>

# Check MLflow service
systemctl status mlflow-server
# Should show: "active (running)"

# Check Prefect agent
systemctl status prefect-agent
# Should show: "active (running)"

# Verify MLflow is responding
curl http://localhost:5000
# Should return HTML (MLflow UI)

# Verify FastAPI is responding (after Docker deploy)
curl http://localhost:8000/health
# Should return: {"status":"ok","model_loaded":true}

# Check service logs
journalctl -u mlflow-server -f
journalctl -u prefect-agent -f
```

### 8. Build and Deploy the API

```bash
# From the repo root, build and push Docker image to ECR
make build-and-push    # Or manually:
# aws ecr get-login-password | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com
# docker build -t heart-disease-api .
# docker tag heart-disease-api:latest <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest
# docker push <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest

# SSH to EC2 and deploy the container
ssh ubuntu@<EC2_PUBLIC_IP>
sudo /opt/deploy-api.sh   # Convenience script created by user_data
# Or manually:
# docker pull <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest
# docker stop heart-disease-api || true
# docker run -d --name heart-disease-api -p 8000:8000 --restart unless-stopped \
#   <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest

# Verify deployment
curl http://localhost:8000/health
```

### 9. Train a Model (Prefect Flow)

```bash
# Ensure .env has correct values for:
#   - MLFLOW_TRACKING_URI
#   - MLFLOW_ARTIFACT_ROOT
#   - DATA_PATH
#   - PREFECT_API_URL
#   - PREFECT_API_KEY

# Run the full pipeline locally (for testing)
python -m heart_disease_prediction.prefect_flow

# Run from Prefect Cloud (worker picks up the scheduled job)
# Worker on EC2 polls Prefect Cloud and executes when scheduled
# Check Prefect Cloud UI: https://app.prefect.cloud/
```

### 10. Make a Prediction

```bash
# Using curl
curl -X POST http://<EC2_PUBLIC_IP>:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 63, "sex": 1, "cp": 3, "trestbps": 145,
    "chol": 233, "fbs": 1, "restecg": 0, "thalach": 150,
    "exang": 0, "oldpeak": 2.3, "slope": 0, "ca": 0, "thal": 1
  }'

# Response:
# {"prediction": 1, "probability": 0.87, "model_version": "best_model_2025-07-30"}

# Or visit Swagger UI:
# http://<EC2_PUBLIC_IP>:8000/docs
```

### 11. Run Tests Locally

```bash
# Run all tests with coverage
make test          # Or: pytest --cov=heart_disease_prediction --cov-fail-under=80 -v

# Run specific test file
pytest tests/test_api.py -v

# Run with coverage report
pytest --cov=heart_disease_prediction --cov-report=html -v

# Open coverage report
open htmlcov/index.html
```

### 12. Monitor with CloudWatch

```bash
# Push drift detection metrics manually
python -m monitoring.generate_report
python -m monitoring.cloudwatch_metrics

# Or via Prefect flow (automatic, runs post-training)
# Open AWS Console → CloudWatch → Dashboards → heart-disease-dashboard
# Check alarms: CloudWatch → Alarms → "cpu-alarm" and "drift-alarm"
# View logs: CloudWatch → Logs → insights → /heart-disease/fastapi
```

### 13. Tear Down & Rebuild

#### Teardown

> Stop all billing. See [Terraform: Tear Down](#tear-down-destroy-everything) for full details on what gets deleted and preserved.

```bash
cd infra
terraform plan -destroy   # Preview what will be destroyed
terraform destroy -auto-approve
```

#### Rebuild After Teardown

> After `terraform apply`, you get a fresh environment. See [Terraform: Rebuilding](#rebuilding-everything-comes-back) for the complete re-configuration checklist.

```bash
# 1. Get the new EC2 IP
NEW_IP=$(cd infra && terraform output -raw ec2_public_ip)

# 2. Update .env and GitHub Actions secret with new IP
sed -i "s/<EC2_PUBLIC_IP>/$NEW_IP/" .env
gh secret set EC2_HOST --body "$NEW_IP"

# 3. Wait 3-5 mins, then verify services
ssh ubuntu@$NEW_IP "systemctl status mlflow-server prefect-agent"

# 4. Retrain models (MLflow registry is empty after teardown)
python -m heart_disease_prediction.prefect_flow

# 5. Deploy API and push reference data
ssh ubuntu@$NEW_IP "sudo /opt/deploy-api.sh"
python -m monitoring.reference_data
```

### Workflow Summary

| Task | Command |
|------|---------|
| Install dependencies | `make install` |
| Run tests | `make test` |
| Lint code | `make lint` |
| Format code | `make format` |
| Build infrastructure | `cd infra && terraform apply` |
| Destroy infrastructure | `cd infra && terraform destroy -auto-approve` |
| Deploy API (manual) | `ssh ubuntu@<EC2> && sudo /opt/deploy-api.sh` |
| Train model locally | `python -m heart_disease_prediction.prefect_flow` |
| View MLflow UI | `http://<EC2_PUBLIC_IP>:5000` |
| View API docs | `http://<EC2_PUBLIC_IP>:8000/docs` |
| Run drift detection | `python -m monitoring.generate_report` |
| Sync local data with S3 | `make sync_data_up` or `make sync_data_down` |

## 📝 Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# AWS (local development only - production uses OIDC)
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=695074562426

# MLflow
MLFLOW_TRACKING_URI=http://<EC2_PUBLIC_IP>:5000
MLFLOW_ARTIFACT_ROOT=s3://heart-disease-mlops-695074562426/artifacts/

# Data
DATA_PATH=s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data

# Prefect (for Cloud connection)
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/.../workspaces/...
PREFECT_API_KEY=pnu_...

# API
MODEL_NAME=best_model_2025-07-30
```

## 🎯 Roadmap Status

| Phase | Component | Status |
|-------|-----------|--------|
| Phase 1 | Terraform IaC (VPC, EC2, RDS, S3, IAM) | ✅ Complete |
| Phase 2 | MLflow on AWS (EC2 + S3 + RDS) | ✅ Complete |
| Phase 3 | Pipeline migration (env-based config) | ✅ Complete |
| Phase 4 | FastAPI deployment on EC2 | ✅ Complete |
| Phase 5 | Prefect agent orchestration | ✅ Complete |
| Phase 6 | Evidently + CloudWatch monitoring | ✅ Complete |
| Phase 7 | GitHub Actions CI/CD (OIDC) | ✅ Complete |
| Phase 8 | Comprehensive testing (31 tests, 80%+) | ✅ Complete |
| Phase 9 | Security hardening | ✅ Complete |

## 📚 Documentation

Comprehensive documentation in `docs/learning/`:

- **53 total files** covering architecture decisions, debugging guides, and implementation details
- **Phase-by-phase breakdown:** What was done, why, and how to debug
- **Key documents:**
  - `phase7/IMPLEMENTATION_SUMMARY.md` - CI/CD setup
  - `phase8/IMPLEMENTATION_SUMMARY.md` - Testing strategy
  - `phase9/IMPLEMENTATION_SUMMARY.md` - Security hardening

## 🤝 Credits

Built as part of the **[MLOps Zoomcamp](https://github.com/DataTalksClub/mlops-zoomcamp)** by DataTalks.Club, with custom AWS Free Tier extensions and production-grade security hardening.

<a target="_blank" href="https://cookiecutter-data-science.drivendata.org/">
    <img src="https://img.shields.io/badge/CCDS-Project%20template-328F97?logo=cookiecutter" />
</a>

---

**License:** MIT
**Python:** 3.12+
**Maintainer:** [abandonedmonk](https://github.com/abandonedmonk)
