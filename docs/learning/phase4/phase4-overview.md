# Phase 4 — FastAPI Deployment on EC2

**Where This Fits in the Project**

---

## The Big Picture

You've built the infrastructure (Phase 1-2) and migrated your pipeline (Phase 3). Now you're deploying your **prediction API** to serve models in production.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AWS FREE TIER ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      YOUR LOCAL MACHINE                           │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │  │
│  │  │ Terraform   │  │  Docker      │  │  Prefect Cloud Agent     │  │  │
│  │  │ (control)   │  │  (build)     │  │  (deploys pipelines)     │  │  │
│  │  └──────┬──────┘  └──────┬───────┘  └───────────┬──────────────┘  │  │
│  │         │                  │                      │               │  │
│  │         ▼                  ▼                      ▼               │  │
│  │    Creates infra      Builds image          Triggers runs         │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│                                    ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                         AWS CLOUD                                │   │
│  │                                                                  │   │
│  │  ┌─────────────────┐     ┌───────────────────────────────────┐   │   │
│  │  │   ECR           │     │   EC2 (t2.micro)                  │   │   │
│  │  │   (stores       │◄────┤   ┌────────────────────────────┐  │   │   │
│  │  │    Docker       │     │   │  MLflow Server (port 5000) │  │   │   │
│  │  │    images)      │     │   │  - S3 artifact store       │  │   │   │
│  │  └─────────────────┘     │   │  - RDS PostgreSQL backend  │  │   │   │
│  │           │              │   └────────────────────────────┘  │   │   │
│  │           │ docker pull  │   ┌─────────────────────────────┐ │   │   │
│  │           ▼              │   │  ★ FastAPI Container       │  │   │   │
│  │  ┌─────────────────┐     │   │  - Port 8000                │ │   │   │
│  │  │   S3 Bucket     │◄────┼───┤  - Loads model from MLflow  │ │   │   │
│  │  │   (artifacts,   │     │   │  - /health endpoint         │ │   │   │
│  │  │    data)        │     │   │  - /predict endpoint        │ │   │   │
│  │  └─────────────────┘     │   └─────────────────────────────┘ │   │   │
│  │           ▲              │                                   │   │   │
│  │           │              │   ┌─────────────────────────────┐ │   │   │
│  │  ┌─────────────────┐     │   │  Prefect Agent (systemd)    │ │   │   │
│  │  │   RDS           │◄────┼───┤  - Runs scheduled pipelines │ │   │   │
│  │  │   PostgreSQL    │     │   │  - Pulls from Prefect Cloud │ │   │   │
│  │  │   (MLflow       │     │   └─────────────────────────────┘ │   │   │
│  │  │    backend)     │     │                                   │   │   │
│  │  └─────────────────┘     └───────────────────────────────────┘   │   │
│  │                                                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    │   HTTP requests                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     USERS / CLIENTS                             │    │
│  │                    curl / browser / frontend                    │    │
│  │                         http://32.196.26.238:8000               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Phase 4 Focus:** The ★ **FastAPI Container** — model serving in production

---

## Why This Phase Matters

### Without Phase 4 (Local Only)

```
Your model is trained and registered in MLflow on AWS,
but predictions still happen on your laptop.

Problems:
- ❌ Laptop must be online 24/7
- ❌ No shared access (only you can predict)
- ❌ No scaling (one user at a time)
- ❌ Pipeline can't trigger predictions automatically
```

### With Phase 4 (Production API)

```
Your model is available via HTTP endpoint on AWS 24/7.

Benefits:
- ✅ Always available (EC2 runs 24/7)
- ✅ Shared access (anyone with URL can call API)
- ✅ Prefect can trigger predictions automatically
- ✅ Frontend apps can integrate
- ✅ Health monitoring via /health endpoint
```

---

## What We Built

| Component | Purpose | Key Decision |
|-----------|---------|--------------|
| **Multi-stage Dockerfile** | Build optimized image | Split builder/runtime, reduced size 43% |
| **MLflow model loading** | Get production model | Load "@champion" alias at startup |
| **/health endpoint** | Monitor API status | Shows model load status, not just "200 OK" |
| **.dockerignore** | Fast builds | Exclude data/, mlruns/, .git/, venv/ |
| **mlflow-skinny** | Smaller image | Client-only package vs full MLflow server |

---

## The Journey So Far

### Phase 1: Infrastructure ✅
**You created:**
- VPC, EC2, RDS, S3, ECR, IAM with Terraform

**What it enables:** Everything runs on AWS, not your laptop

### Phase 2: MLflow Server ✅
**You deployed:**
- MLflow tracking server on EC2 (port 5000)
- S3 for artifacts, RDS for metadata

**What it enables:** Centralized experiment tracking and model registry

### Phase 3: Pipeline Migration ✅
**You updated:**
- All scripts to use env vars (not hardcoded paths)
- Remote state backend (S3 + DynamoDB)

**What it enables:** Same code runs locally and on AWS

### Phase 4: FastAPI Container ✅
**You built:**
- Docker image that loads model from MLflow
- 613 MB optimized image (down from 1.07 GB)
- Health endpoint for monitoring

**What it enables:** Model predictions via HTTP API 24/7

---

## What Comes Next

### Phase 5: Prefect Agent on EC2
**Goal:** Run scheduled training pipelines automatically

**You'll do:**
- Deploy Prefect agent as systemd service
- Configure `prefect_api_url` and `prefect_api_key`
- Schedule weekly retraining

**Why:** Keep models fresh with new data automatically

### Phase 6: Monitoring (Evidently + CloudWatch)
**Goal:** Detect when models degrade

**You'll do:**
- Set up Evidently for data/concept drift detection
- Create CloudWatch dashboards for infrastructure
- Set alarms for errors, CPU, memory

**Why:** Know immediately when something breaks

### Phase 7: CI/CD (GitHub Actions)
**Goal:** Automatic deployment on every code change

**You'll do:**
- Build and push Docker image automatically
- Run tests before deploying
- Deploy to EC2 via SSH

**Why:** No manual steps = fewer mistakes, faster iteration

### Phase 8: Real Testing
**Goal:** Replace placeholder tests with real ones

**You'll do:**
- Test data loading, preprocessing
- Test model training and registration
- Test API endpoints with TestClient

**Why:** Confidence that changes don't break things

### Phase 9: Security Hardening
**Goal:** Remove secrets from git history

**You'll do:**
- Purge `.env` from git history
- Rotate AWS keys
- Set up OIDC for GitHub Actions (no stored credentials)

**Why:** Prevent credential leaks

---

## Key Concepts You Learned

### 1. Multi-Stage Docker Builds
**Concept:** Separate compilation from runtime
**Why it matters:** Smaller images, faster deploys, less attack surface

### 2. MLflow Model Registry
**Concept:** Load models by alias (`@champion`) not by file path
**Why it matters:** Decouple API deployment from model updates

### 3. Container Health Checks
**Concept:** `/health` endpoint shows internal state, not just "alive"
**Why it matters:** Load balancers and monitors need to know if service is usable

### 4. Build Context Optimization
**Concept:** `.dockerignore` prevents sending unnecessary files to Docker daemon
**Why it matters:** Faster builds, especially in CI/CD

### 5. Library Selection
**Concept:** `mlflow-skinny` vs `mlflow` — choose minimal viable dependencies
**Why it matters:** Smaller images = lower storage costs, faster pulls

---

## Production Checklist

Before Phase 4 is "done":

- [x] Dockerfile uses multi-stage build
- [x] Image size < 650 MB (target achieved: 613 MB)
- [x] Model loads from MLflow at startup
- [x] `/health` endpoint returns model status
- [x] `.dockerignore` excludes data/, mlruns/, .git/
- [x] Image pushed to ECR (`695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api`)
- [x] Container running on EC2 (accessible at http://32.196.26.238:8000)
- [x] Systemd service for auto-restart (`/etc/systemd/system/fastapi.service`)
- [ ] `/predict` endpoint tested with real data (pending model registration)
- [x] `/health` endpoint verified (returns degraded until model registered)

---

## Quick Reference: Phase 4 Files

| File | What Changed | Why |
|------|--------------|-----|
| `Dockerfile` | New multi-stage build at root | Optimized production image |
| `.dockerignore` | New file | Exclude unnecessary files from build |
| `api/main.py` | MLflow loading, /health endpoint | Load model from registry, expose status |
| `api/requirements.txt` | Added mlflow-skinny, boto3, python-dotenv | MLflow client dependencies |
| `api/schema.py` | No change | Pydantic model for request validation |

---

## Next: Phase 5

Continue to [Phase 5 — Prefect Agent on EC2](../phase5/) to enable automatic pipeline execution.

Or dive deeper into Phase 4 concepts:
- [01 — Containerizing for Production](01-containerizing-for-production.md)
- [02 — Loading Models from MLflow](02-loading-models-from-mlflow.md)
- [03 — Sizing and Optimization](03-sizing-and-optimization.md)
- [04 — Deployment to EC2](04-deployment-to-ec2.md) ← **Full command reference**
