# Running Pipelines End-to-End

Complete workflow: from code change to deployed model.

---

## The Full Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Code      │────►│   Prefect   │────►│    EC2      │
│   Change    │     │   Cloud     │     │   Agent     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
       ┌────────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Training   │────►│   MLflow    │────►│    S3       │
│  Pipeline   │     │  Registry   │     │ Artifacts  │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   FastAPI   │
                    │  Restarts   │
                    └─────────────┘
```

---

## Scenario: Weekly Retraining

### 1. Deployment Configuration

**Already done:**
```yaml
# prefect.yaml (auto-generated)
deployments:
- name: heart-disease-pipeline
  entrypoint: heart_disease_prediction/prefect_flow.py:full_pipeline
  work_pool:
    name: default
    work_queue_name: default
  schedules:
  - cron: 0 0 * * 0  # Every Sunday at midnight
    timezone: UTC
```

**What this means:**
- Every Sunday at 00:00 UTC, Prefect Cloud triggers a new run
- EC2 agent picks up the work
- Pipeline trains on latest data, registers best model

---

### 2. Manual Run (Testing)

**From Prefect Cloud UI:**
```
1. Go to https://app.prefect.cloud
2. Workspaces → Your workspace
3. Deployments → full-pipeline/heart-disease-pipeline
4. Click "Run" → "Quick Run"
```

**From CLI (local):**
```bash
# Ensure connected to Cloud
export PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY
prefect cloud login

# Trigger run
prefect deployment run "full-pipeline/heart-disease-pipeline"
```

**What happens:**
1. Prefect Cloud creates a flow run
2. Notifies EC2 agent via long-polling
3. EC2 agent downloads flow code (from Git repo storage)
4. Executes `full_pipeline()` function
5. Reports status, logs, artifacts back to Cloud

---

### 3. Pipeline Execution on EC2

**What the agent does:**
```bash
# (Automatically by Prefect agent)
1. Git clone repo (from prefect.yaml pull section)
2. Install dependencies (from pyproject.toml/requirements.txt)
3. Execute flow code
4. Stream logs back to Cloud
```

**Pipeline steps executed:**
```python
@flow
def full_pipeline():
    # 1. Download data from S3
    data = get_data()
    
    # 2. Split into train/test
    X_train, X_test, y_train, y_test = split_data(data)
    
    # 3. Train 4 models
    best_run = train_model(X_train, X_test, y_train, y_test)
    #    └─ Logs to MLflow (http://10.0.0.186:5000)
    #    └─ Stores artifacts in S3
    
    # 4. Register best model
    register_model(best_run)
    #    └─ Creates model version in MLflow Registry
    #    └─ Transitions to "Production" stage
```

**Timing:**
- Data download: ~5 seconds (S3 → EC2)
- Training 4 models: ~2-3 minutes (t2.micro is slow)
- Model registration: ~10 seconds
- **Total: ~3-4 minutes**

---

### 4. Verification Steps

**A. Check Prefect Cloud:**
```
Go to: Flow Runs → Find your run
Status should be: ✅ Completed (green checkmark)
```

**B. Check MLflow:**
```bash
# From local machine
curl http://32.196.26.238:5000/api/2.0/mlflow/experiments/list | python3 -m json.tool

# Or open in browser: http://32.196.26.238:5000
# Should see new experiment with runs and metrics
```

**C. Check S3:**
```bash
aws s3 ls s3://heart-disease-mlops-695074562426/artifacts/ --recursive | tail -20

# Should see:
# artifacts/.../model/model.pkl
# artifacts/.../model/MLmodel
# artifacts/.../model/conda.yaml
```

**D. Check Model Registry:**
```bash
# From EC2 or local
curl http://32.196.26.238:5000/api/2.0/mlflow/registered-models/list | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('registered_models', []):
    print(f\"Model: {m['name']}\")
    for v in m.get('latest_versions', []):
        print(f\"  v{v['version']}: {v['current_stage']}\")
"
```

**Output:**
```
Model: best_model_2025-07-30
  v1: Production
```

---

### 5. Update FastAPI with New Model

**Automatic?**
No — FastAPI loads model at startup. You need to restart it.

**In Phase 7 (CI/CD), this will be automatic.**

**Manual update:**
```bash
# SSH to EC2
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238

# Update env file with new model name
sudo tee /opt/app/.env > /dev/null << 'EOF'
MLFLOW_TRACKING_URI=http://10.0.0.186:5000
MODEL_NAME=best_model_2025-07-30  # ← Updated!
AWS_REGION=us-east-1
EOF

# Recreate container (restart doesn't pick up new env)
docker stop fastapi
docker rm fastapi
docker run -d \
  --name fastapi \
  --restart always \
  -p 8000:8000 \
  --env-file /opt/app/.env \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest

# Wait for model loading (30-60 seconds)
sleep 45

# Verify
curl http://localhost:8000/health | python3 -m json.tool
```

**Expected response:**
```json
{
  "status": "ok",
  "model_loaded": true,
  "model_name": "best_model_2025-07-30",
  "tracking_uri_set": true
}
```

---

### 6. Test Prediction

```bash
# Test from local machine
curl -X POST http://32.196.26.238:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 63, "sex": 1, "cp": 3, "trestbps": 145,
    "chol": 233, "fbs": 1, "restecg": 0, "thalach": 150,
    "exang": 0, "oldpeak": 2.3, "slope": 0, "ca": "0.0", "thal": "6.0"
  }'

# Expected: {"prediction": 0} or {"prediction": 1}
# (0 = no heart disease, 1 = heart disease detected)
```

---

## Complete Command Sequence

```bash
#!/bin/bash
# run_pipeline.sh — Complete end-to-end workflow

set -e  # Exit on error

echo "=== 1. Trigger Prefect run ==="
export PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY
prefect deployment run "full-pipeline/heart-disease-pipeline"

echo "=== 2. Wait for completion (monitor in Cloud UI) ==="
echo "Pipeline running... check https://app.prefect.cloud"
read -p "Press Enter when flow shows 'Completed'..."

echo "=== 3. Get registered model name ==="
MODEL_NAME=$(curl -s http://32.196.26.238:5000/api/2.0/mlflow/registered-models/list | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d['registered_models'][0]['name'])")
echo "Latest model: $MODEL_NAME"

echo "=== 4. Update EC2 API ==="
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 << EOF
  sudo tee /opt/app/.env > /dev/null << ENVFILE
MLFLOW_TRACKING_URI=http://10.0.0.186:5000
MODEL_NAME=$MODEL_NAME
AWS_REGION=us-east-1
ENVFILE
  
  docker stop fastapi
  docker rm fastapi
  docker run -d \
    --name fastapi \
    --restart always \
    -p 8000:8000 \
    --env-file /opt/app/.env \
    695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest
EOF

echo "=== 5. Wait for model loading ==="
sleep 45

echo "=== 6. Verify API ==="
curl -s http://32.196.26.238:8000/health | python3 -m json.tool

echo "=== Done! ==="
```

---

## Monitoring the Pipeline

### Real-Time Logs

**From Prefect Cloud UI:**
- Go to **Flow Runs** → Click your run
- See live logs streaming from EC2

**From EC2 (backup):**
```bash
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 \
  "sudo journalctl -u prefect-agent -f"
```

### Common Pipeline Failures

| Failure | Symptom | Fix |
|---------|---------|-----|
| Data download fails | S3 permission error | Check IAM instance profile has S3 access |
| MLflow connection fails | "Connection refused" | Verify MLflow running: `curl localhost:5000` |
| Model training hangs | 10+ min on training | Normal for t2.micro, just slow |
| Model registration fails | "Resource already exists" | Model name collision, check date |
| API won't load model | `"model_loaded": false` | Wrong model name in env, or model not in Production stage |

---

## Optimizations for Phase 7 (CI/CD)

**Current (Phase 5):**
- Manual trigger → Wait → Manual API update

**Future (Phase 7):**
- Git push → GitHub Actions → Auto-trigger run → Auto-update API

**How:**
```yaml
# .github/workflows/retrain.yml (Phase 7)
on:
  schedule:
    - cron: "0 0 * * 0"  # Same as Prefect schedule
  workflow_dispatch:  # Manual trigger

jobs:
  retrain:
    steps:
      - name: Trigger Prefect run
        run: |
          curl -X POST https://api.prefect.cloud/api/... \
            -H "Authorization: Bearer $PREFECT_API_KEY" \
            -d '{"deployment_id": "..."}'
      
      - name: Wait for completion
        run: |
          # Poll until status = completed
          
      - name: Update EC2 API
        run: |
          ssh ubuntu@32.196.26.238 "docker restart fastapi"
```

---

## Summary

**End-to-End Flow:**

1. **Trigger**: Prefect Cloud (UI or scheduled) → EC2 agent
2. **Execute**: EC2 downloads code, runs pipeline
3. **Log**: MLflow receives metrics, S3 receives artifacts
4. **Register**: Best model promoted to "Production"
5. **Update**: Restart FastAPI to load new model
6. **Serve**: API responds with predictions

**Your Current Status:**
- ✅ Pipeline code works
- ✅ MLflow configured
- ✅ S3 storage working
- ✅ FastAPI serving
- ✅ Model registered and loaded
- ⚠️ Prefect agent connected to temp server (not Cloud yet)
- ⚠️ API update is manual (not automated)

**Next**: Phase 6 (Monitoring) and Phase 7 (CI/CD) will automate the remaining manual steps.
