# Troubleshooting Prefect Issues

Common errors and their solutions.

---

## Quick Diagnostics

Run this on EC2 to check everything:

```bash
#!/bin/bash
# diagnose.sh

echo "=== 1. Prefect Agent Status ==="
sudo systemctl status prefect-agent --no-pager | head -5

echo -e "\n=== 2. Prefect Agent Logs (last 20 lines) ==="
sudo journalctl -u prefect-agent --no-pager | tail -20

echo -e "\n=== 3. MLflow Status ==="
curl -s http://localhost:5000/ | head -1

echo -e "\n=== 4. API Health ==="
curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/health

echo -e "\n=== 5. S3 Access ==="
aws s3 ls s3://heart-disease-mlops-695074562426/ | head -5

echo -e "\n=== 6. Disk Space ==="
df -h / | tail -1

echo -e "\n=== 7. Memory ==="
free -h | grep "Mem:"

echo -e "\n=== 8. Prefect Version ==="
/opt/mlflow-venv/bin/prefect --version
```

---

## Error: "Unknown command 'agent'"

**Symptom:**
```
prefect[31143]: ╭─ Error ───────────────────────────────────────────────────────╮
prefect[31143]: │ Unknown command "agent". Did you mean "event"? Available ... │
╰──────────────────────────────────────────────────────────────────────────────╯
```

**Cause:** Using Prefect 2.x command with Prefect 3.x binary.

**Fix:**
```bash
# Edit service file
sudo nano /etc/systemd/system/prefect-agent.service

# Change this:
ExecStart=/opt/mlflow-venv/bin/prefect agent start --pool default

# To this:
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default

# Restart
sudo systemctl daemon-reload
sudo systemctl restart prefect-agent
```

**Prevention:** Always check version first:
```bash
/opt/mlflow-venv/bin/prefect --version  # Should show 3.x
```

---

## Error: Service restarts continuously

**Symptom:**
```
$ sudo systemctl status prefect-agent
Active: activating (auto-restart) (Result: exit-code)
NRestarts: 5883  # Very high number!
```

**Causes:**

### A. Wrong command (see above)
**Fix:** Update ExecStart to use `worker` not `agent`

### B. Missing PATH
**Symptom:**
```
python3: command not found
```

**Fix:** Add PATH to service file:
```ini
[Service]
Environment="PATH=/opt/mlflow-venv/bin:/usr/local/bin:/usr/bin:/bin"
```

### C. Wrong Python environment
**Symptom:**
```
ModuleNotFoundError: No module named 'prefect'
```

**Fix:** Use full path to prefect binary:
```ini
ExecStart=/opt/mlflow-venv/bin/prefect worker start ...
# Not just: prefect worker start
```

---

## Error: "Starting temporary server"

**Symptom:**
```
prefect[...]: Starting temporary server on http://127.0.0.1:8992
```

**Cause:** No `PREFECT_API_URL` set, so agent creates its own isolated server.

**Impact:** Agent won't receive work from your Prefect Cloud or local server.

**Fix:**
```bash
# Add to service file
sudo nano /etc/systemd/system/prefect-agent.service

# Add these lines:
Environment="PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY"
Environment="PREFECT_API_KEY=pnu_xxxxxxxxxxxxxxxx"

# Restart
sudo systemctl daemon-reload
sudo systemctl restart prefect-agent

# Verify
sudo journalctl -u prefect-agent -f
# Should show: "Polling for work from Prefect Cloud..."
```

---

## Error: "Authentication failed"

**Symptom:**
```
prefect[...]: Authentication failed. Please check your API key.
```

**Causes:**

### A. Wrong API key
**Fix:** Regenerate in Prefect Cloud UI:
1. https://app.prefect.cloud → Settings → API Keys
2. Delete old key, create new one
3. Update service file with new key
4. Restart agent

### B. API key expired
Prefect Cloud API keys don't expire by default, but workspace admins can revoke them.

---

## Error: "Cannot connect to Prefect Cloud"

**Symptom:**
```
prefect[...]: Connection error. Retrying in 10 seconds...
```

**Diagnosis:**
```bash
# From EC2, test connectivity
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 \
  "curl -I https://api.prefect.cloud"

# Should return: HTTP/2 200
```

**Causes:**

### A. No internet access
**Check:**
```bash
# From EC2
curl -I https://google.com
```

**Fix:** Check security group allows outbound HTTPS (port 443). It should by default (egress -1).

### B. DNS resolution fails
**Check:**
```bash
nslookup api.prefect.cloud
```

**Fix:** 
```bash
# Temporarily use Google's DNS
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

---

## Error: Flow runs stay in "Scheduled" state

**Symptom:** In Prefect Cloud UI, run shows "Scheduled" (yellow) forever, never starts.

**Diagnosis:**
```bash
# Check if agent is polling
sudo journalctl -u prefect-agent -f

# Good: "Polling for work..."
# Bad: "Starting temporary server" or errors
```

**Causes:**

### A. Wrong pool name
**Check deployment:**
```bash
# Locally
prefect deployment inspect "full-pipeline/heart-disease-pipeline" | grep pool
# Shows: pool_name: default
```

**Check agent:**
```bash
# On EC2
sudo journalctl -u prefect-agent | grep "pool"
# Should show: "Worker '...' started in pool 'default'"
```

**Fix:** They must match! Update service file:
```ini
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default
```

### B. Wrong work queue
**Fix:**
```ini
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
```

### C. Not connected to same server
**Symptom:** Agent shows "Polling..." but Cloud doesn't assign work.

**Check:**
- Cloud deployment shows "Scheduled"
- But agent is in "temporary server" mode

**Fix:** Set `PREFECT_API_URL` to point to Cloud (see above).

---

## Error: "Resource already exists" during model registration

**Symptom:** Pipeline fails at register step:
```
mlflow.exceptions.MlflowException: Registered Model ... already exists
```

**Cause:** Model name collision. Using `best_model_2025-07-30` but that model already exists.

**Fix:** Use timestamp or UUID in model name, or update existing version:

**In `register.py`:**
```python
# Option 1: Use run ID (unique)
model_name = f"best_model_{mlflow.active_run().info.run_id[:8]}"

# Option 2: Use timestamp + random
import time
model_name = f"best_model_{int(time.time())}"

# Option 3: Use date only, but check existence first
existing = mlflow.search_registered_models(filter_string=f"name='{model_name}'")
if existing:
    # Archive old versions or increment version
    pass
```

---

## Error: API shows "model_loaded": false

**Symptom:**
```bash
curl http://32.196.26.238:8000/health
# {"status": "degraded", "model_loaded": false, ...}
```

**Causes:**

### A. Wrong model name in env
**Check:**
```bash
# On EC2
cat /opt/app/.env
# MODEL_NAME=heart-disease-model  ← Wrong!

# Should match MLflow registry
curl http://localhost:5000/api/2.0/mlflow/registered-models/list
```

**Fix:**
```bash
# Update env file
sudo tee /opt/app/.env > /dev/null << 'EOF'
MLFLOW_TRACKING_URI=http://10.0.0.186:5000
MODEL_NAME=best_model_2025-07-30  # ← Correct name from MLflow
AWS_REGION=us-east-1
EOF

# Recreate container (restart doesn't pick up new env!)
docker stop fastapi
docker rm fastapi
docker run -d --name fastapi ...
```

### B. Model not in Production stage
**API code looks for:**
1. `models:/MODEL_NAME@champion` (alias)
2. `models:/MODEL_NAME/Production` (stage)

**Fix in MLflow UI:**
1. Go to http://32.196.26.238:5000
2. Models → Click model name
3. Click version → Transition to "Production"

Or via code (already in register.py):
```python
mlflow.transition_model_version_stage(
    name=model_name,
    version=version,
    stage="Production"
)
```

### C. Can't reach MLflow
**Check:**
```bash
# From inside container
docker exec fastapi python3 -c "
import urllib.request
try:
    urllib.request.urlopen('http://10.0.0.186:5000', timeout=5)
    print('OK')
except Exception as e:
    print(f'Error: {e}')
"
```

**Fix:** Use private IP, not localhost (see Phase 4 docs).

---

## Error: S3 permission denied

**Symptom:** Pipeline fails:
```
botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation
```

**Check IAM:**
```bash
# From EC2
aws sts get-caller-identity
# Should show assumed-role, not error

aws s3 cp /tmp/test.txt s3://heart-disease-mlops-695074562426/
```

**Fix:**
```bash
# Check instance profile attached
aws ec2 describe-instances --instance-ids i-0bda8692493c15a77 \
  --query 'Reservations[0].Instances[0].IamInstanceProfile.Arn'

# Should show: .../instance-profile/heart-disease-mlops-ec2-profile

# If missing, need to attach via AWS console or terminate and recreate with Terraform
```

---

## Error: Container won't start after env update

**Symptom:** Changed `/opt/app/.env`, ran `docker restart fastapi`, but old model still loaded.

**Cause:** `docker restart` doesn't reload environment variables.

**Fix:**
```bash
# Must recreate container, not restart
docker stop fastapi
docker rm fastapi
docker run -d --name fastapi --env-file /opt/app/.env ...

# Not:
docker restart fastapi  # ← Won't pick up new env!
```

---

## Performance: Pipeline takes 30+ minutes

**Symptom:** Training 4 models takes 30+ minutes on t2.micro.

**Expected:** Should take 2-5 minutes for this dataset.

**Diagnosis:**
```bash
# On EC2
htop
# Or
docker stats --no-stream
```

**Causes:**

### A. Out of memory, using swap
**Check:**
```bash
free -h
# Swap usage > 500MB = bad
```

**Fix:** Stop other services:
```bash
# Check what's running
docker ps
ps aux | grep python

# If swap high, restart EC2 or stop MLflow temporarily
sudo systemctl stop mlflow  # Don't do this!
```

### B. Too many concurrent runs
**Check:**
```bash
sudo journalctl -u prefect-agent | grep "run" | tail -20
```

**Fix:** Cancel stuck runs in Prefect Cloud UI.

---

## Prevention Checklist

Before running pipeline:

- [ ] EC2 has instance profile attached (`aws sts get-caller-identity`)
- [ ] Prefect service uses `worker` not `agent`
- [ ] Prefect service has `PREFECT_API_URL` and `PREFECT_API_KEY` set (for Cloud)
- [ ] MLflow running (`curl localhost:5000`)
- [ ] Disk space > 20% free (`df -h`)
- [ ] Memory available > 200MB (`free -h`)
- [ ] API has correct model name in `/opt/app/.env`

---

## Emergency Commands

```bash
# Reset everything (last resort)

# On EC2
sudo systemctl stop prefect-agent
sudo systemctl stop mlflow
docker stop fastapi

# Clean up
docker rm fastapi 2>/dev/null
sudo rm -rf /home/ubuntu/.prefect/*  # Clear Prefect cache

# Restart
sudo systemctl start mlflow
sudo systemctl start prefect-agent

# Redeploy container
docker run -d --name fastapi ...
```

---

## Getting Help

**Prefect:**
- Docs: https://docs.prefect.io
- Community Slack: https://prefect.io/slack
- Discourse: https://discourse.prefect.io

**MLflow:**
- Docs: https://mlflow.org/docs/latest/index.html
- GitHub Issues: https://github.com/mlflow/mlflow/issues

**AWS:**
- Free tier limits: https://aws.amazon.com/free/
- Support: https://support.console.aws.amazon.com
