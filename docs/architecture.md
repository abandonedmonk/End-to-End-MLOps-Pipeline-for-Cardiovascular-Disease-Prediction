# Architecture — AWS MLOps Pipeline

System architecture, data flow, and component interactions for the Heart Disease Prediction MLOps pipeline on AWS Free Tier.

---

## System Architecture Diagram

```
                            ┌──────────────────────┐
                            │    GitHub Repository  │
                            │  (Source Code + IaC)  │
                            └──────────┬───────────┘
                                       │
                          ┌────────────┴────────────┐
                          │   GitHub Actions (CI/CD) │
                          │   OIDC → Assume IAM Role │
                          └─────┬──────────────┬─────┘
                                │              │
                     Build+Push │              │ Deploy
                                ▼              │
                    ┌───────────────────┐      │
                    │   ECR Private     │      │
                    │  heart-disease-api│      │
                    └───────────────────┘      │
                                               │
┌──────────────────────────────────────────────┼──────────────────────────┐
│                         AWS Cloud (us-east-1)│                          │
│                                              ▼                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    EC2 t2.micro                                 │   │
│  │                                                                 │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │   │
│  │  │  MLflow      │  │  FastAPI     │  │  Prefect Agent       │  │   │
│  │  │  Server      │  │  (Docker)   │  │  (systemd service)   │  │   │
│  │  │  :5000       │  │  :8000      │  │                      │  │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │   │
│  │         │                 │                      │              │   │
│  │         │    ┌────────────┘                      │              │   │
│  │         │    │  Load champion model               │              │   │
│  │         │    │  from MLflow                       │              │   │
│  │         │    │                                    │              │   │
│  │  ┌──────┴────┴────────────────────────────────────┴──────────┐  │   │
│  │  │                   Evidently (cron)                        │  │   │
│  │  │          Weekly drift report generation                    │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                                 │   │
│  │  IAM Instance Profile → S3 + ECR + CloudWatch access           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────────┐   │
│  │  RDS PostgreSQL  │    │  S3 Bucket      │    │  CloudWatch      │   │
│  │  db.t3.micro     │    │                 │    │                  │   │
│  │  (MLflow DB)     │    │  /artifacts/    │    │  Logs + Metrics  │   │
│  │                  │    │  /data/         │    │  + Alarms        │   │
│  │  Port 5432       │    │  /monitoring/   │    │  + Dashboard     │   │
│  │  (EC2 SG only)   │    │  /terraform/    │    │                  │   │
│  └─────────────────┘    └─────────────────┘    └──────────────────┘   │
│                                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                           │
│  │  IAM OIDC       │    │  SNS Topic      │                           │
│  │  (GitHub→AWS)   │    │  (Alerts)       │                           │
│  └─────────────────┘    └─────────────────┘                           │
└───────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────┐
                    │   Prefect Cloud      │
                    │   (Orchestration)    │
                    │   Free: 10K runs/mo  │
                    └──────────┬───────────┘
                               │
                    Scheduled runs trigger
                    Prefect Agent on EC2
```

---

## Data Flow

### Training Pipeline (Weekly via Prefect)

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Step 1  │───►│  Step 2  │───►│  Step 3  │───►│  Step 4  │───►│  Step 5  │
│ Load Data│    │Split Data│    │  Train   │    │ Register │    │Set Alias │
│ from S3  │    │+Preproc  │    │4 Models  │    │Best Model│    │"champion"│
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │                              │               │               │
     ▼                              ▼               ▼               ▼
  S3 Bucket                    MLflow+S3      MLflow Registry  MLflow Alias
  /data/raw/                   (metrics+      (model_name,     (champion)
                               artifacts)      version)
```

**Step-by-step:**

1. **Load Data** — `data.py:get_data()` downloads raw data from S3
2. **Split + Preprocess** — `data.py:split_data_for_train()` splits 80/20, defines ColumnTransformer
3. **Train Models** — `train.py:train_model()` trains LR, RF, HGB, DT; logs metrics + artifacts to MLflow (S3 artifacts, RDS metrics)
4. **Register Best** — `register.py:register_model()` finds best run by accuracy, registers in MLflow Model Registry
5. **Set Alias** — `load_model.py:load_model()` assigns "champion" alias to latest version

### Inference Flow (Real-time via FastAPI)

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Client   │────►│  FastAPI     │────►│  sklearn     │────►│ Response │
│  (HTTP)   │     │  /predict    │     │  Pipeline    │     │ JSON     │
└──────────┘     └──────────────┘     └──────────────┘     └──────────┘
                       │                     │
                       │                     │
                  Load pipeline.pkl    Preprocess + Predict
                  (from MLflow or        in single step
                   container image)
```

**Key detail:** The `pipeline.pkl` combines ColumnTransformer + classifier, so preprocessing and prediction happen in one `.predict()` call.

### Monitoring Flow (Weekly via Cron)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Reference   │     │  Current     │     │  Evidently   │     │  S3      │
│  Data (S3)   │────►│  Data (S3)   │────►│  Report      │────►│  Report  │
│  /reference/ │     │  /processed/ │     │  Generation  │     │  HTML    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────┘
```

### CI/CD Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Developer   │────►│  GitHub      │────►│  GitHub      │────►│  ECR     │
│  git push    │     │  Actions CI  │     │  Actions CD  │     │  + EC2   │
└──────────────┘     │  (lint+test) │     │  (build+push)│     │  Deploy  │
                     └──────────────┘     └──────────────┘     └──────────┘
```

---

## Network Architecture

```
                        Internet
                           │
                    ┌──────┴──────┐
                    │  Security   │
                    │  Group:     │
                    │  SSH (22)   │── Your IP only
                    │  MLflow(5K) │── Your IP only
                    │  API (8K)   │── Your IP or 0.0.0.0/0
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │  EC2        │
                    │  t2.micro   │
                    │  (Public IP)│
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │  Security   │
                    │  Group:     │
                    │  PG (5432)  │── EC2 SG only
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │  RDS        │
                    │  PostgreSQL │
                    │  (Private)  │
                    └─────────────┘
```

**Security Group Rules:**

| Security Group | Inbound | Source | Port |
|---------------|---------|--------|------|
| EC2-SG | SSH | Your IP | 22 |
| EC2-SG | MLflow UI | Your IP | 5000 |
| EC2-SG | FastAPI | Your IP (or 0.0.0.0/0) | 8000 |
| RDS-SG | PostgreSQL | EC2-SG | 5432 |

**No inbound rules for:** S3, ECR, CloudWatch, IAM (all accessed via AWS API, not network)

---

## Component Resource Usage on EC2

The single `t2.micro` (1 vCPU, 1 GB RAM) hosts 4 services. Estimated resource usage:

| Service | CPU | RAM | Disk |
|---------|-----|-----|------|
| MLflow Server | ~5% idle, ~15% during run | ~200 MB | ~50 MB |
| FastAPI (Docker) | ~1% idle, ~10% per request | ~150 MB | ~300 MB (image) |
| Prefect Agent | ~1% idle, ~30% during pipeline | ~100 MB | ~50 MB |
| Evidently (cron) | ~50% during report gen | ~300 MB | ~50 MB |
| **Total** | **~7% idle** | **~750 MB** | **~450 MB** |

**Warning:** t2.micro has 1 GB RAM. With all services running, you're at ~750 MB. This is tight but workable since ML training on EC2 is brief (small dataset, 303 rows). If memory becomes an issue:
- Stop MLflow when not training (save ~200 MB)
- Use `t3.micro` instead of `t2.micro` (if available in your free tier — newer accounts may get t3)
- Add swap space: `sudo fallocate -l 1G /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`

---

## Model Lifecycle

```
┌───────────────────────────────────────────────────────────────┐
│                    MLflow Model Registry                      │
│                                                               │
│  Experiment Run ──► Register ──► Version ──► Alias            │
│                                                               │
│  Run A (acc=0.85) ──►                        │                │
│  Run B (acc=0.90) ──► best_model ──► v1 ──► champion         │
│  Run C (acc=0.88) ──►                        │                │
│                                               │                │
│  Next week:                                    │                │
│  Run D (acc=0.87) ──► best_model ──► v2 ──► champion (v2)   │
│                                    v1 ──► (no alias)          │
│                                                               │
│  API server always loads model with "champion" alias           │
└───────────────────────────────────────────────────────────────┘
```

**Champion Model Selection:**
1. `train.py` trains 4 models, logs all to MLflow
2. `register.py` finds best run by accuracy DESC
3. `load_model.py` assigns "champion" alias to latest version
4. API loads champion model from MLflow on startup (or from baked-in `pipeline.pkl` in Docker image)

**Model Update Strategy:**
- Weekly pipeline creates new version
- New version gets "champion" alias
- Old version loses "champion" alias
- API must be restarted to load new model (or implement hot-reload via MLflow)

---

## Environment Variables Summary

All configuration is driven by environment variables, enabling the same code to work locally or on AWS:

| Variable | Local Default | AWS Value |
|----------|--------------|-----------|
| `MLFLOW_TRACKING_URI` | `sqlite:///mlruns/mlflow.db` | `http://localhost:5000` (from EC2) |
| `MLFLOW_ARTIFACT_ROOT` | `file://mlruns/` | `s3://heart-disease-mlops/artifacts/` |
| `MLFLOW_EXPERIMENT_NAME` | `heart-disease-experiment-pipeline` | Same |
| `MLFLOW_MODEL_NAME` | `best_model_<today>` | Same |
| `DATA_PATH` | `../data/raw/processed.cleveland.data` | `s3://heart-disease-mlops/data/raw/processed.cleveland.data` |
| `S3_BUCKET` | (unused) | `heart-disease-mlops` |
| `AWS_REGION` | (unused) | `us-east-1` |

**Where each variable is set:**

| Context | How |
|---------|-----|
| Local development | `.env` file loaded by `python-dotenv` |
| EC2 services | Systemd `Environment=` directives |
| Prefect agent | Systemd `Environment=` directives |
| GitHub Actions | GitHub Secrets + workflow `env:` block |
| Docker container | `-e` flag in `docker run` |

---

## Failure Modes and Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| EC2 instance down | CloudWatch alarm (CPU=0 for 5 min) | SNS email → manual restart or auto-recovery |
| MLflow server crash | Systemd auto-restart | `systemctl restart mlflow` |
| FastAPI container crash | Docker `--restart unless-stopped` | Auto-restarts within seconds |
| Prefect agent crash | Systemd auto-restart | `systemctl restart prefect-agent` |
| RDS connection loss | MLflow 500 errors in logs | RDS auto-failover (if Multi-AZ, but not on free tier) |
| S3 access denied | boto3 exception in logs | Check IAM instance profile |
| Model drift detected | Evidently report flag | Review report → retrain → redeploy |
| Pipeline failure | Prefect Cloud UI shows failed run | Debug logs → manual rerun |

---

## Cost Guardrails

1. **AWS Budgets Alert** — Set at $1/month. Alerts via email if spending exceeds threshold.
2. **EC2 Auto-Stop** — Consider Lambda function to stop EC2 after N hours of idle (optional).
3. **S3 Lifecycle Policy** — Auto-delete old monitoring reports after 90 days.
4. **ECR Lifecycle Policy** — Keep only last 5 images, delete older ones.
5. **RDS Auto-Stop** — RDS auto-stops after 7 days of no connections (free tier limitation, restarts on next connection).
6. **No Multi-AZ** — Single-AZ for RDS saves ~50% cost vs Multi-AZ.
