# Connecting to Prefect Cloud

Moving from a local Prefect server to Prefect Cloud for production coordination.

---

## The Problem with Local Server

**Current setup (what we did in Phase 5):**
```
Your Laptop ──► Local Prefect (:4200) ──► Deploy flows, trigger runs
     │
     │ (no connection)
     ▼
   EC2 ──► Temporary Prefect (:8992) ──► Can't receive work
```

**Issue:** Two separate Prefect servers that don't talk to each other.

---

## The Solution: Prefect Cloud

**Target setup:**
```
Your Laptop ──► Prefect Cloud (app.prefect.cloud) ──► Deploy flows, trigger runs
                              │
                              │ (same backend)
                              ▼
   EC2 ──► Prefect Cloud (app.prefect.cloud) ──► Receives and executes work
```

**Benefits:**
- ✅ Both use same coordination backend
- ✅ Web UI accessible from anywhere
- ✅ No need to expose your laptop to internet
- ✅ Automatic retries, queuing, observability
- ✅ Free tier: 10,000 runs/month

---

## Setup Steps

### Step 1: Get Prefect Cloud Credentials

1. Go to https://app.prefect.cloud
2. Sign up / log in
3. Create a workspace (or use default)
4. Go to **Settings** → **API**
5. Copy the **API URL** (looks like: `https://api.prefect.cloud/api/accounts/123/workspaces/456`)
6. Go to **Settings** → **API Keys**
7. Create new key, copy it (starts with `pnu_`)

---

### Step 2: Update Local Environment

**File: `.env`**
```bash
# Add these lines
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY
PREFECT_API_KEY=pnu_xxxxxxxxxxxxxxxx
```

**Activate:**
```bash
# Source the env file or restart terminal
source .env

# Verify
prefect config view | grep -E "PREFECT_API_URL|PREFECT_API_KEY"
```

**Login to Cloud:**
```bash
# Using the API key
prefect cloud login -k $PREFECT_API_KEY

# Or interactive
prefect cloud login
# Follow prompts to select workspace
```

---

### Step 3: Update EC2 Service

**SSH to EC2:**
```bash
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238
```

**Edit service file:**
```bash
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

# PREFECT CLOUD CONFIGURATION
Environment="PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY"
Environment="PREFECT_API_KEY=pnu_xxxxxxxxxxxxxxxx"

# MLflow and AWS
Environment="MLFLOW_TRACKING_URI=http://10.0.0.186:5000"
Environment="AWS_REGION=us-east-1"
Environment="S3_BUCKET=heart-disease-mlops-695074562426"

ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

**Restart agent:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart prefect-agent
sudo systemctl status prefect-agent --no-pager | head -10
```

---

### Step 4: Verify Connection

**On EC2 - Check logs:**
```bash
sudo journalctl -u prefect-agent -f
```

**Expected output:**
```
prefect[...]: Worker 'ProcessWorker ...' started in pool 'default'
prefect[...]: Polling for work from Prefect Cloud...
```

**NOT:**
```
prefect[...]: Starting temporary server on http://127.0.0.1:8992
```
(If you see this, PREFECT_API_URL isn't set correctly)

**In Prefect Cloud UI:**
1. Go to https://app.prefect.cloud
2. Click your workspace
3. Go to **Work Pools** → **default**
4. Should see your EC2 agent listed with status "Online"

---

### Step 5: Redeploy Flow to Cloud

**On your local machine:**
```bash
# Ensure connected to Cloud
export PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY
export PREFECT_API_KEY=pnu_xxxxxxxxxxxxxxxx

# Create work pool (if doesn't exist)
prefect work-pool create default --type process

# Deploy flow (this time to Cloud)
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project

prefect deploy heart_disease_prediction/prefect_flow.py:full_pipeline \
  --name heart-disease-pipeline \
  --pool default \
  --work-queue default \
  --cron "0 0 * * 0"
```

**Verify in Cloud UI:**
- Go to **Deployments**
- Should see `full-pipeline/heart-disease-pipeline`
- Click it → **Run** → **Quick Run**

---

### Step 6: Test End-to-End

**Trigger run from Cloud UI:**
1. Find your deployment
2. Click "Run" → "Quick Run"
3. Go to **Flow Runs** to watch progress

**Monitor on EC2:**
```bash
# Watch logs
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 \
  "sudo journalctl -u prefect-agent -f"
```

**Verify completion:**
- Flow run shows "Completed" in Cloud UI
- MLflow shows new experiment at http://32.196.26.238:5000
- S3 has new artifacts: `aws s3 ls s3://heart-disease-mlops-695074562426/artifacts/`

---

## Security Best Practices

### Don't Commit API Key

**`.env` file:**
```bash
# ✅ Good: .env is in .gitignore
echo ".env" >> .gitignore

# ✅ Good: Use .env.example for template
cp .env .env.example
# Then edit .env.example to remove real values
```

**`.env.example`:**
```bash
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY
PREFECT_API_KEY=pnu_xxxxxxxxxxxxxxxx
```

### Rotate Keys Regularly

```bash
# In Prefect Cloud UI:
# Settings → API Keys → Delete old key → Create new key

# Then update both local and EC2:
# 1. Update .env locally
# 2. Update systemd service on EC2
# 3. Restart EC2 agent
```

### Use Terraform for EC2

Instead of hardcoding in service file:

**terraform.tfvars:**
```hcl
prefect_api_url  = "https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY"
prefect_api_key  = "pnu_xxxxxxxxxxxxxxxx"
```

**user_data.sh.tftpl:**
```bash
%{ if prefect_api_url != "" }
Environment="PREFECT_API_URL=${prefect_api_url}"
%{ endif }
%{ if prefect_api_key != "" }
Environment="PREFECT_API_KEY=${prefect_api_key}"
%{ endif }
```

This way credentials never touch disk on your laptop (just S3 state with encryption).

---

## Troubleshooting Cloud Connection

### "Authentication failed"

**Cause:** Wrong API key

**Fix:**
```bash
# Verify key
prefect cloud login -k ACTUAL_KEY

# Or regenerate in Prefect Cloud UI
```

### "Cannot connect to Prefect Cloud"

**Cause:** Network/firewall blocking

**Fix:**
```bash
# Test connectivity from EC2
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 \
  "curl -I https://api.prefect.cloud"

# Should return HTTP/2 200
```

### "Worker started but no work received"

**Cause:** Pool/queue mismatch

**Check:**
```bash
# On EC2 - what pool is agent using?
sudo journalctl -u prefect-agent | grep "pool"

# Locally - what pool is deployment using?
prefect deployment inspect "full-pipeline/heart-disease-pipeline" | grep pool

# Must match!
```

---

## Migration Checklist

Moving from local server to Cloud:

- [ ] Sign up at app.prefect.cloud
- [ ] Get API URL and API key
- [ ] Add to local `.env` file
- [ ] Run `prefect cloud login`
- [ ] Update EC2 systemd service with credentials
- [ ] Restart EC2 agent
- [ ] Verify agent shows "Online" in Cloud UI
- [ ] Redeploy flow to Cloud
- [ ] Test manual run from Cloud UI
- [ ] Verify scheduled run works (wait for cron trigger)

---

## Cost Considerations

| Resource | Free Tier | Your Usage |
|----------|-----------|------------|
| Prefect Cloud runs | 10,000/month | ~4-8/month |
| Prefect Cloud storage | Unlimited (metadata only) | ~KB |
| Work pools | Unlimited | 1 (default) |
| **Total** | **$0** | **$0** |

**Always free** — Prefect Cloud's free tier is generous and won't be exceeded by this project.

---

## Next Steps

Once connected to Prefect Cloud:
1. Set up monitoring (Phase 6)
2. Configure CI/CD to auto-deploy flows (Phase 7)
3. Set up notifications for failed runs
4. Add custom work queues for different environments (dev/staging/prod)
