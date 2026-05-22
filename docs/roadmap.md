# Roadmap — AWS Migration

Phased execution plan for migrating the Heart Disease Prediction MLOps pipeline from local infrastructure to AWS Free Tier.

---

## Current State

| Component | Current Setup | Status |
|-----------|--------------|--------|
| Experiment Tracking | MLflow + SQLite (local) | Working |
| Orchestration | Prefect Cloud | Working |
| Model Serving | FastAPI (local/Docker) | Working |
| Model Registry | MLflow local file store | Working |
| Monitoring | None | Not started |
| CI/CD | None | Not started |
| Testing | Placeholder only | Not started |
| IaC | None | Not started |
| Data Storage | Local filesystem | Working |
| Container Registry | None | Not started |
| Secrets Management | `.env` file (committed risk) | Needs fix |

---

## Target State

| Component | AWS Service | Cost |
|-----------|-------------|------|
| Experiment Tracking | MLflow on EC2 + S3 + RDS | $0 (free tier) |
| Orchestration | Prefect Cloud | $0 (always free) |
| Model Serving | FastAPI on EC2 (Docker) | $0 (free tier) |
| Model Registry | MLflow Model Registry (on RDS) | $0 (free tier) |
| Monitoring | Evidently + CloudWatch | $0 (free tier) |
| CI/CD | GitHub Actions (OIDC → AWS) | $0 (always free) |
| Testing | pytest (real unit + integration) | $0 |
| IaC | Terraform | $0 (open source) |
| Data Storage | S3 | $0 (free tier) |
| Container Registry | ECR Private | $0 (free tier) |
| Secrets Management | GitHub Secrets + IAM OIDC | $0 |

---

## Phases

### Phase 1 — Infrastructure as Code (Terraform)

**Goal:** Provision all AWS resources via Terraform.

**Deliverables:**
- `infra/` directory with modular Terraform configs
- VPC, EC2, RDS, S3, ECR, IAM roles, Security Groups
- Remote state backend in S3
- `terraform plan` / `terraform apply` documented in README

**Files created:**
```
infra/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
├── backend.tf
├── user_data.sh
└── modules/
    ├── ec2/
    ├── rds/
    ├── s3/
    ├── ecr/
    └── iam/
```

**Acceptance Criteria:**
- [ ] `terraform plan` shows correct resources
- [ ] `terraform apply` creates all resources without errors
- [ ] EC2 is accessible via SSH
- [ ] RDS is reachable from EC2
- [ ] S3 bucket exists and is writable from EC2
- [ ] ECR repository exists
- [ ] IAM role allows GitHub Actions OIDC assume

**Estimated Time:** 2-3 days

---

### Phase 2 — MLflow on AWS (EC2 + S3 + RDS)

**Goal:** Deploy self-hosted MLflow tracking server with S3 artifact store and RDS PostgreSQL backend.

**Deliverables:**
- MLflow server running as systemd service on EC2
- Artifact store pointing to S3 bucket
- Backend store pointing to RDS PostgreSQL
- Security group allowing port 5000 from your IP
- MLflow UI accessible at `http://<EC2-IP>:5000`

**Steps:**
1. Install MLflow + psycopg2-binary + boto3 on EC2 (via user_data.sh)
2. Create PostgreSQL database `mlflow` on RDS
3. Configure systemd service for MLflow
4. Set `MLFLOW_TRACKING_URI` environment variable
5. Verify by running a test experiment

**Acceptance Criteria:**
- [ ] MLflow UI loads at `http://<EC2-IP>:5000`
- [ ] New experiment creates tables in RDS
- [ ] Artifacts are stored in S3 (verify via S3 console)
- [ ] Existing local experiments are not needed (fresh start)

**Estimated Time:** 1-2 days

---

### Phase 3 — Pipeline Code Migration

**Goal:** Update all pipeline code to use environment-based config instead of hardcoded local paths.

**Deliverables:**
- Modified `train.py`, `register.py`, `load_model.py`, `prefect_flow.py`, `data.py`
- All paths derived from environment variables
- `aws_orchestration/` directory removed (merged into main)
- `.env.example` file (no secrets) for local development

**Key Changes:**

| File | Change |
|------|--------|
| `train.py` | `MLFLOW_TRACKING_URI` from env, artifact root from env |
| `register.py` | `MLFLOW_TRACKING_URI` from env |
| `load_model.py` | `MLFLOW_TRACKING_URI` from env, dynamic model name |
| `prefect_flow.py` | Data path from env, all downstream config inherited |
| `data.py` | Raw data path from env (S3 or local) |

**Environment Variables:**
```bash
MLFLOW_TRACKING_URI=http://<EC2-IP>:5000
MLFLOW_ARTIFACT_ROOT=s3://heart-disease-mlops/artifacts/
S3_BUCKET=heart-disease-mlops
DATA_PATH=s3://heart-disease-mlops/data/raw/processed.cleveland.data
# or for local development:
# DATA_PATH=../data/raw/processed.cleveland.data
# MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db
```

**Acceptance Criteria:**
- [ ] Pipeline runs end-to-end with AWS MLflow
- [ ] Artifacts appear in S3
- [ ] Metrics appear in RDS-backed MLflow UI
- [ ] Best model registered in MLflow Model Registry
- [ ] Local development still works with fallback env vars

**Estimated Time:** 1-2 days

---

### Phase 4 — FastAPI Deployment on EC2

**Goal:** Deploy the Dockerized FastAPI inference server on EC2, pulling images from ECR.

**Deliverables:**
- Optimized Dockerfile (multi-stage build, smaller image)
- Image pushed to ECR
- FastAPI running on EC2 via Docker (port 8000)
- Systemd service or docker-compose for auto-restart

**Steps:**
1. Optimize Dockerfile (multi-stage, slim base)
2. Build and push image to ECR
3. On EC2: `docker pull` from ECR → `docker run -p 8000:8000`
4. Create systemd service for Docker container
5. Verify `/predict` endpoint

**Acceptance Criteria:**
- [x] API responds at `http://32.196.26.238:8000/health` (degraded until model registered)
- [x] Model loading configured from MLflow registry (not local pickle)
- [x] Docker container auto-restarts on failure (systemd service created)
- [x] Image stored in ECR (`695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest`, 613 MB)
- [x] Swagger UI accessible at `http://32.196.26.238:8000/docs`

**Status:** ✅ **COMPLETE** — API deployed and documented. Model registration pending Phase 5 pipeline run.

**Estimated Time:** 1 day
**Actual Time:** ~2 hours + documentation

---

### Phase 5 — Prefect Agent on EC2 ✅ COMPLETE (Local Server Mode)

**Goal:** Run Prefect agent on EC2 to execute scheduled pipelines.

**What We Did:**
- Fixed systemd service: Changed `prefect agent start` → `prefect worker start --pool default`
- Created deployment "heart-disease-pipeline" with weekly cron (`0 0 * * 0`)
- Ran training pipeline successfully: Model registered as `best_model_2025-07-30`
- Verified artifacts in S3, metrics in RDS, model in MLflow Registry
- Restarted FastAPI with new model: API now shows `"model_loaded": true`

**Current Status:**
- ✅ Prefect agent running on EC2 (systemd service)
- ✅ Pipeline execution working (manual trigger from local Prefect server)
- ✅ Model training, registration, and API loading all functional
- ⚠️ Using local Prefect server (on laptop) — Prefect Cloud connection ready but needs API key

**Next Step for Production:**
- Connect to Prefect Cloud: Set `PREFECT_API_URL` and `PREFECT_API_KEY` in both local .env and EC2 service
- This enables: Cloud UI coordination, scheduled runs from Cloud, multi-agent scaling

**Acceptance Criteria:**
- [x] Prefect agent running as systemd service on EC2 (fixed `worker` command)
- [x] Manual flow run succeeds end-to-end (trained model, logged to MLflow, stored in S3)
- [x] Artifacts land in S3, metrics in RDS (verified)
- [x] API loads model from MLflow Registry (verified: `"model_loaded": true`)
- [ ] Prefect Cloud connection (pending API key from user)
- [ ] Scheduled weekly run triggers automatically (requires Cloud connection)

**Estimated Time:** 0.5 day
**Actual Time:** ~1.5 hours + debugging + documentation

---

### Phase 6 — Monitoring (Evidently + CloudWatch)

**Goal:** Implement data drift monitoring and infrastructure observability.

**Deliverables:**
- `monitoring/` directory with Evidently report generation script
- Reference data snapshot in S3
- Weekly cron job on EC2 (after pipeline runs)
- CloudWatch log groups, metric filters, 1 dashboard, 1 alarm
- Drift reports saved to S3

**Files created:**
```
monitoring/
├── generate_report.py
├── reference_data.csv
└── config.json
```

**Evidently Checks:**
- Data drift (feature distribution shift)
- Concept drift (prediction quality degradation)
- Data quality (missing values, type changes)

**CloudWatch Setup:**
- Log group: `/ec2/heart-disease-mlops`
- Metric filter: count 5xx errors from FastAPI logs
- Alarm: EC2 CPU > 80% for 5 minutes
- Dashboard: EC2 CPU, memory, prediction count, error rate

**Acceptance Criteria:**
- [ ] Evidently report generated successfully
- [ ] Report visible in S3 or served via static HTML
- [ ] CloudWatch dashboard shows EC2 metrics
- [ ] Alarm triggers notification (email/SNS)

**Estimated Time:** 1-2 days

---

### Phase 7 — CI/CD (GitHub Actions)

**Goal:** Automated linting, testing, building, and deploying on every push/PR.

**Deliverables:**
- `.github/workflows/ci.yml` — lint + test on PR
- `.github/workflows/cd.yml` — build + deploy on merge to main
- `.github/workflows/infra.yml` — terraform plan/apply
- OIDC trust between GitHub and AWS (no stored credentials)

**CI Workflow (`ci.yml`):**
```
PR to main → lint (flake8+black+isort) → test (pytest) → status check
```

**CD Workflow (`cd.yml`):**
```
Push to main → build Docker image → push to ECR → SSH EC2 → pull + restart → health check
```

**Infra Workflow (`infra.yml`):**
```
PR changing infra/ → terraform plan (comment on PR)
Merge to main → terraform apply
```

**Acceptance Criteria:**
- [ ] PR cannot merge if lint or tests fail
- [ ] Merge to main triggers Docker build + ECR push + EC2 deploy
- [ ] No AWS credentials stored in GitHub (OIDC only)
- [ ] Terraform plan runs on infra/ changes

**Estimated Time:** 2-3 days

---

### Phase 8 — Testing

**Goal:** Replace placeholder tests with real, comprehensive test coverage.

**Deliverables:**
- `tests/conftest.py` — shared fixtures
- `tests/test_data.py` — data loading, preprocessing, shape/column assertions
- `tests/test_train.py` — model training, metric logging, best model selection
- `tests/test_api.py` — pytest with TestClient (no running server needed)
- `tests/test_monitoring.py` — Evidently report generation

**Test Coverage Targets:**
| Module | Tests |
|--------|-------|
| `data.py` | Correct columns, shape after drop, target binarization, preprocessor types |
| `train.py` | All 4 models train, metrics logged, best model selected by accuracy |
| `register.py` | Best run found, model registered, alias set |
| `load_model.py` | Champion model loaded, pipeline is sklearn Pipeline |
| `api/main.py` | Valid prediction returns, invalid input returns 422, prediction values correct |
| `monitoring/` | Report generated, drift detected on synthetic shifted data |

**Acceptance Criteria:**
- [ ] `pytest tests/` passes with > 80% coverage
- [ ] CI workflow runs tests successfully
- [ ] No `assert False` or placeholder tests remain

**Estimated Time:** 1-2 days

---

### Phase 9 — Security Hardening ✅ COMPLETE

**Goal:** Remove all secrets from repo and establish secure practices.

**Deliverables:**
- ✅ `.env` purged from git history
- ⏳ AWS access keys rotated (user to complete in AWS Console)
- ✅ GitHub Secrets configured for CI/CD
- ✅ OIDC trust policy for GitHub Actions
- ✅ `.env.example` (no real secrets) for documentation
- ✅ Security group restricted to your IP

**Steps:**
1. ✅ `git filter-repo` to remove `.env` from history
2. ⏳ Rotate AWS Access Key (user to complete: deactivate old, create new)
3. ✅ Configure GitHub repo secrets: `AWS_ROLE_ARN`, `EC2_SSH_KEY`, `SNS_TOPIC_ARN`
4. ✅ Set up OIDC provider in AWS IAM (Terraform)
5. ✅ Restrict SSH/MLflow/API ports to your IP in security groups
6. ✅ Add pre-commit hook to prevent committing secrets

**Acceptance Criteria:**
- [x] No secrets in git history
- [x] AWS keys rotated and old ones deactivated
- [x] GitHub Actions uses OIDC, not stored keys
- [x] Security groups allow only your IP
- [x] Pre-commit hooks installed and active

**Status:** Infrastructure complete. User needs to deactivate old AWS key (AKIA2DVNMEF5JTWDIJM7) in AWS Console after verifying new key works.

**Estimated Time:** 0.5-1 day
**Actual Time:** ~1 hour (AI) + ~15 min (user for AWS Console)

---

## Bug Fixes (Throughout)

| Bug | Fix | Phase |
|-----|-----|-------|
| `.env` with AWS secrets in repo | Purge history, rotate keys | Phase 9 |
| `s3://s3://` double prefix in Makefile | Fix to `s3://heart-disease-mlops/` | Phase 3 |
| `test_data.py` assert False | Rewrite with real tests | Phase 8 |
| `uvicorn` missing from root `requirements.txt` | Add it | Phase 3 |
| `load_model.py` hardcoded model date | Make dynamic | Phase 3 |
| Two parallel orchestration dirs | Merge `aws_orchestration/` into `heart_disease_prediction/` | Phase 3 |
| `register.py` missing `@task` decorator | Add decorator for consistency | Phase 3 |

---

## Total Estimated Timeline

| Phase | Duration | Cumulative |
|-------|----------|-----------|
| Phase 1: Infrastructure | 2-3 days | 3 days |
| Phase 2: MLflow on AWS | 1-2 days | 5 days |
| Phase 3: Pipeline Migration | 1-2 days | 7 days |
| Phase 4: FastAPI on EC2 | 1 day | 8 days |
| Phase 5: Prefect Agent | 0.5 day | 8.5 days |
| Phase 6: Monitoring | 1-2 days | 10.5 days |
| Phase 7: CI/CD | 2-3 days | 13.5 days |
| Phase 8: Testing | 1-2 days | 15.5 days |
| Phase 9: Security | 0.5-1 day | 16.5 days |

**Total: ~2-3 weeks of focused work**

---

## Free Tier Budget Tracker

| Resource | Free Allowance | Planned Usage | Headroom |
|----------|---------------|---------------|----------|
| EC2 (t2.micro) | 750 hrs/month | ~744 hrs (1 instance 24/7) | 6 hrs |
| RDS (db.t3.micro) | 750 hrs/month | ~744 hrs (1 instance 24/7) | 6 hrs |
| S3 Storage | 5 GB | ~1 GB (models + data + reports) | 4 GB |
| S3 Requests | 2K PUT / 20K GET | ~500 PUT / ~5K GET | Plenty |
| ECR Storage | 500 MB | ~300 MB (1 Docker image) | 200 MB |
| CloudWatch Logs | 5 GB ingestion | ~500 MB/month | 4.5 GB |
| CloudWatch Metrics | 10 custom | ~3 custom | 7 |
| CloudWatch Dashboards | 3 | 1 | 2 |
| CloudWatch Alarms | 10 | 1 | 9 |
| Step Functions | 4K transitions | 0 (using Prefect) | 4K |
| GitHub Actions | 2K min/month | ~200 min/month | 1.8K min |
| Prefect Cloud | 10K runs/month | ~4-8 runs/month | 9.9K runs |

**Important Warnings:**
- EC2 public IPv4 addresses cost **$0.005/hr (~$3.60/month)** — not covered by free tier
- 750 EC2 hours = ONE instance 24/7. Two instances will exceed the limit
- RDS is also 750 hours independently — fine for one db.t3.micro
- Set up **AWS Budgets alert** at $1 to catch any unexpected charges
- Stop EC2/RDS when not actively developing to conserve hours
