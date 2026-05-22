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
┌─────────────────────────────────────────────────────────────────────────┐
│                           CI/CD Pipeline                                │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐     │
│  │ GitHub PR    │────▶│ Lint + Test  │────▶│ Docker Build + Push  │     │
│  │ (CI)         │     │ (pytest 80%) │     │ (ECR)                │     │
│  └──────────────┘     └──────────────┘     └──────────────────────┘     │
│         │                                                │              │
│         ▼                                                ▼              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                   EC2 t2.micro (us-east-1)                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │   │
│  │  │ MLflow 5000  │  │ FastAPI 8000 │  │ Prefect Agent (Worker)  │   │   │
│  │  │ (Tracking)   │  │ (Inference)  │  │ (Pipeline Runner)       │   │   │
│  │  └──────────────┘  └──────────────┘  └─────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│         │              │              │                                 │
│         ▼              ▼              ▼                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                           │
│  │ RDS      │    │ S3       │    │ ECR      │                           │
│  │ (pg14)   │    │ Artifacts│    │ Images   │                           │
│  └──────────┘    └──────────┘    └──────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ CloudWatch         │
                    │ ├─ Dashboard     │
                    │ ├─ Alarms (CPU)   │
                    │ └─ Drift Metrics  │
                    └──────────────────┘
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
| MLflow UI | http://32.196.26.238:5000 | ✅ Active |
| FastAPI Health | http://32.196.26.238:8000/health | ✅ Active |
| API Docs (Swagger) | http://32.196.26.238:8000/docs | ✅ Active |
| CloudWatch Dashboard | AWS Console | ✅ Active |

## 📁 Project Structure

```
.
├── .github/workflows/           # CI/CD pipelines
│   ├── ci.yml                   # Lint, test, coverage (on PR)
│   ├── cd.yml                   # Build, deploy, rollback (on merge)
│   └── infra.yml                # Terraform plan/apply
├── api/                         # FastAPI inference service
│   ├── main.py                  # Health + predict endpoints
│   ├── schema.py                # Pydantic request validation
│   └── requirements.txt         # Container dependencies
├── heart_disease_prediction/    # Core ML pipeline
│   ├── data.py                  # S3 data loading + preprocessing
│   ├── train.py                 # Multi-model training (5 algorithms)
│   ├── register.py              # MLflow model registry
│   ├── load_model.py            # Champion model loading
│   └── prefect_flow.py          # Orchestrated pipeline
├── monitoring/                  # Drift detection + CloudWatch
│   ├── generate_report.py       # Evidently drift reports
│   ├── cloudwatch_metrics.py    # Custom metrics push
│   └── config.py                # Monitoring configuration
├── infra/                       # Terraform IaC (29 resources)
│   ├── modules/                 # ec2, rds, s3, iam, vpc, ecr, monitoring
│   ├── main.tf                  # Root orchestration
│   └── backend.tf               # S3 + DynamoDB remote state
├── tests/                       # 31 test functions, 80%+ coverage
│   ├── conftest.py              # Shared fixtures
│   ├── test_*.py                # Unit + integration tests
├── docs/learning/               # 53 documentation files
│   ├── phase1/                  # Terraform, VPC, IAM
│   ├── phase3/                  # Env-based config, S3
│   ├── phase4/                  # Docker, FastAPI deploy
│   ├── phase5/                  # Prefect agent setup
│   ├── phase6/                  # Evidently + CloudWatch
│   ├── phase7/                  # GitHub Actions CI/CD
│   ├── phase8/                  # Testing (31 tests)
│   └── phase9/                  # Security hardening
├── Dockerfile                   # Multi-stage build (613 MB)
├── pyproject.toml               # Poetry-style deps + tool configs
└── README.md                    # This file
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
- ✅ **IP restrictions:** Security groups limited to 103.224.7.24/32
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

## 📝 Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# AWS (local development only - production uses OIDC)
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=695074562426

# MLflow
MLFLOW_TRACKING_URI=http://32.196.26.238:5000
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
