# Phase 5 — Prefect Agent on EC2

Running scheduled ML pipelines automatically on AWS infrastructure.

---

## What We Did

| Step | What | Result |
|------|------|--------|
| 1 | Fixed systemd service | Changed `prefect agent start` → `prefect worker start --pool default` |
| 2 | Deployed flow locally | Created deployment "heart-disease-pipeline" with weekly cron |
| 3 | Ran training pipeline | Model trained, registered as `best_model_2025-07-30` |
| 4 | Verified artifacts | Models stored in S3, metrics in RDS |
| 5 | Restarted API | FastAPI now shows `"model_loaded": true` |

---

## Current Status

### ✅ Working

| Component | URL/Status | Details |
|-----------|-----------|---------|
| **Prefect Agent** | Active on EC2 | `prefect-agent.service` running |
| **Deployment** | Local Prefect server | `full-pipeline/heart-disease-pipeline` |
| **MLflow UI** | http://32.196.26.238:5000 | Model registered |
| **FastAPI** | http://32.196.26.238:8000 | `"status": "ok"` |
| **S3 Artifacts** | `s3://heart-disease-mlops-695074562426/` | Model files stored |

### ⚠️ Pending Prefect Cloud Connection

The current setup uses a **local Prefect server** (on your laptop). For production:
- Need to connect to **Prefect Cloud** (app.prefect.cloud)
- Both local CLI and EC2 agent must use same `PREFECT_API_URL`
- See [02-connecting-to-prefect-cloud.md](02-connecting-to-prefect-cloud.md)

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    YOUR LOCAL MACHINE                          │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │ Prefect Server      │  │ Prefect CLI                     │  │
│  │ (temporary, :4200)  │  │ • Deploy flows                  │  │
│  │                     │  │ • Trigger runs                  │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTP API
                               ▼
┌────────────────────────────────────────────────────────────────┐
│                         EC2 (t2.micro)                         │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Prefect Agent (systemd)                                 │  │
│  │ └─ Runs: prefect worker start --pool default            │  │
│  │                                                         │  │
│  │ Currently NOT connected (no PREFECT_API_URL set)      │  │
│  │ Starts its own temp server on :8992                    │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ MLflow Server (:5000)                                   │  │
│  │ └─ Receives pipeline metrics & model artifacts         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ FastAPI Container (:8000)                               │  │
│  │ └─ Loads model from MLflow registry                    │  │
│  │     Model: best_model_2025-07-30                       │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**Current Gap:** Local Prefect server and EC2 agent aren't talking to each other. They're each running their own temporary servers.

---

## Commands Used

### Fix Prefect Service on EC2

```bash
# SSH to EC2
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238

# Stop old service
sudo systemctl stop prefect-agent
sudo systemctl disable prefect-agent

# Create corrected service file
sudo tee /etc/systemd/system/prefect-agent.service > /dev/null << 'EOF'
[Unit]
Description=Prefect Agent
After=network.target mlflow.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu
Environment="PATH=/opt/mlflow-venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PREFECT_HOME=/home/ubuntu/.prefect"
Environment="MLFLOW_TRACKING_URI=http://10.0.0.186:5000"
Environment="AWS_REGION=us-east-1"
Environment="S3_BUCKET=heart-disease-mlops-695074562426"
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload and start
sudo systemctl daemon-reload
sudo systemctl enable prefect-agent
sudo systemctl start prefect-agent
sudo systemctl status prefect-agent
```

### Deploy Flow (Local)

```bash
# Start local Prefect server
prefect server start

# In another terminal, deploy the flow
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project
prefect deploy heart_disease_prediction/prefect_flow.py:full_pipeline \
  --name heart-disease-pipeline \
  --pool default \
  --work-queue default \
  --cron "0 0 * * 0"  # Weekly on Sunday midnight

# Verify deployment
prefect deployment ls
```

### Run Pipeline (Local)

```bash
# Set environment
export MLFLOW_TRACKING_URI=http://32.196.26.238:5000
export DATA_PATH=s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data

# Run via Prefect
prefect deployment run "full-pipeline/heart-disease-pipeline"

# Or run directly
python heart_disease_prediction/prefect_flow.py
```

### Verify & Restart API

```bash
# On EC2 - check MLflow has model
curl -s http://localhost:5000/api/2.0/mlflow/registered-models/list

# Update API env file
sudo tee /opt/app/.env > /dev/null << 'EOF'
MLFLOW_TRACKING_URI=http://10.0.0.186:5000
MODEL_NAME=best_model_2025-07-30
AWS_REGION=us-east-1
EOF

# Recreate container (to pick up new env)
docker stop fastapi
docker rm fastapi
docker run -d \
  --name fastapi \
  --restart always \
  -p 8000:8000 \
  --env-file /opt/app/.env \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest

# Test
sleep 30
curl http://localhost:8000/health
```

---

## Key Issues Fixed

### 1. `prefect agent` → `prefect worker`

**Error:**
```
Unknown command "agent". Did you mean "event"?
```

**Fix:** Prefect 3.x uses `worker` not `agent`:
```bash
# Old (broken)
prefect agent start --pool heart-disease

# New (working)
prefect worker start --pool default --work-queue default
```

### 2. Missing `PREFECT_API_URL`

**Symptom:** Agent starts its own temporary server instead of connecting to yours.

**Fix:** Set `PREFECT_API_URL` in systemd service (for Prefect Cloud connection).

### 3. Docker Restart vs Recreate

**Issue:** `docker restart` doesn't pick up new environment variables.

**Fix:** Must stop, remove, and recreate container:
```bash
docker stop fastapi
docker rm fastapi
docker run -d --name fastapi ...
```

---

## Next Steps for Production

To complete Phase 5 for production use:

1. **Connect to Prefect Cloud** ([02-connecting-to-prefect-cloud.md](02-connecting-to-prefect-cloud.md))
   - Get API URL and key from app.prefect.cloud
   - Update both local .env and EC2 systemd service
   - Both will use same coordination backend

2. **Update Terraform** for future EC2s
   - Add `prefect_api_url` and `prefect_api_key` variables
   - Pass to user_data template
   - New instances will auto-connect

3. **Test Scheduled Runs**
   - Deployment has weekly cron: `0 0 * * 0`
   - Will auto-trigger every Sunday at midnight
   - Monitor in Prefect Cloud UI

---

## Verification Checklist

- [x] Prefect agent service running (`systemctl status prefect-agent`)
- [x] Flow deployed locally (`prefect deployment ls`)
- [x] Pipeline executed successfully
- [x] Model registered in MLflow (visible at :5000)
- [x] Artifacts stored in S3 (`aws s3 ls s3://.../artifacts/`)
- [x] FastAPI restarted with new model
- [x] API health shows `"model_loaded": true`
- [ ] Prefect Cloud connected (both local + EC2)
- [ ] Scheduled run triggers automatically
- [ ] EC2 agent picks up work from Prefect Cloud

---

## Documentation Files

| File | Topic |
|------|-------|
| [01-prefect-agent-setup.md](01-prefect-agent-setup.md) | Installing and configuring the systemd service |
| [02-connecting-to-prefect-cloud.md](02-connecting-to-prefect-cloud.md) | Moving from local server to Prefect Cloud |
| [03-running-pipelines-end-to-end.md](03-running-pipelines-end-to-end.md) | Complete execution workflow |
| [04-troubleshooting-prefect.md](04-troubleshooting-prefect.md) | Common errors and fixes |

---

## Quick Commands Reference

```bash
# === LOCAL MACHINE ===
# Start Prefect server
prefect server start

# Deploy flow
prefect deploy heart_disease_prediction/prefect_flow.py:full_pipeline \
  --name heart-disease-pipeline --pool default --cron "0 0 * * 0"

# Trigger run
prefect deployment run "full-pipeline/heart-disease-pipeline"

# === EC2 ===
# Check agent
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 \
  "sudo systemctl status prefect-agent"

# View agent logs
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 \
  "sudo journalctl -u prefect-agent -f"

# Check API
curl http://32.196.26.238:8000/health
```
