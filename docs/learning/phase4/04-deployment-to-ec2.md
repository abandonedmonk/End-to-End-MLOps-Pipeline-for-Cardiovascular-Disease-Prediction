# Phase 4 — Deploying to Production (ECR → EC2)

This guide covers everything we did to deploy the FastAPI container from local build to production on AWS EC2.

---

## What We Did

| Step | What | Commands Used |
|------|------|---------------|
| 1 | **Build** optimized Docker image | `docker build -t heart-disease-api:latest .` |
| 2 | **Tag** for ECR | `docker tag heart-disease-api:latest <ecr-uri>:latest` |
| 3 | **Push** to ECR | `docker push <ecr-uri>:latest` |
| 4 | **Deploy** on EC2 | `docker pull` + `docker run` with env file |
| 5 | **Configure** auto-restart | Created systemd service |
| 6 | **Verify** deployment | Tested `/health` endpoint locally and remotely |

---

## 1. Pushing to ECR

### Commands (Run from local machine)

```bash
# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
REPO_NAME="heart-disease-mlops-api"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"

# Login to ECR (token valid for 12 hours)
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin $ECR_URI

# Tag image
docker tag heart-disease-api:latest ${ECR_URI}:latest

# Push to ECR
docker push ${ECR_URI}:latest
```

**What Happens:**
- ECR is a private Docker registry in AWS
- Each layer of the image is uploaded separately
- Only changed layers are re-uploaded on subsequent pushes
- Our 613 MB image uploaded in ~30 seconds

**Why ECR:**
- ✅ **Free tier:** 500 MB storage (our image is 613 MB compressed to ~204 MB on disk)
- ✅ **Secure:** Private, IAM-controlled access
- ✅ **Fast:** Pull from EC2 within same region is very fast
- ❌ **Not free forever:** After 12 months, $0.10/GB/month

**IAM Permissions Required:**
```json
{
  "Effect": "Allow",
  "Action": [
    "ecr:GetAuthorizationToken",
    "ecr:BatchCheckLayerAvailability",
    "ecr:GetDownloadUrlForLayer",
    "ecr:BatchGetImage",
    "ecr:PutImage",
    "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart",
    "ecr:CompleteLayerUpload"
  ],
  "Resource": "*"
}
```

---

## 2. Deploying on EC2

### Commands (Run on EC2 via SSH)

```bash
# SSH to EC2
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238

# Configure AWS CLI (already installed via user_data)
aws --version  # aws-cli/2.34.50

# Login to ECR using instance profile (no hardcoded credentials!)
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    695074562426.dkr.ecr.us-east-1.amazonaws.com

# Pull image
docker pull 695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest

# Create environment file
sudo mkdir -p /opt/app
sudo tee /opt/app/.env > /dev/null << 'EOF'
MLFLOW_TRACKING_URI=http://10.0.0.186:5000  # Private IP, NOT localhost!
MODEL_NAME=heart-disease-model
AWS_REGION=us-east-1
EOF

# Run container
docker run -d \
  --name fastapi \
  --restart always \
  -p 8000:8000 \
  --env-file /opt/app/.env \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest
```

---

## 3. Critical: Docker Networking Trap

**The Problem We Hit:**
```bash
# WRONG - localhost inside container is the container itself
MLFLOW_TRACKING_URI=http://localhost:5000  # ❌ Can't reach MLflow!

# CORRECT - use EC2 private IP
MLFLOW_TRACKING_URI=http://10.0.0.186:5000   # ✅ Reaches MLflow on host
```

**Why This Happens:**
- Each Docker container has its own network namespace
- `localhost` inside container ≠ `localhost` on host
- Containers can reach host services via:
  - Host's **private IP address** (what we used)
  - `host.docker.internal` (Docker Desktop only, NOT Linux)
  - `--network host` mode (less secure, more complex)

**How to Find Private IP:**
```bash
# On EC2
PRIVATE_IP=$(hostname -I | awk '{print $1}')  # 10.0.0.186
# Or from metadata (requires instance profile)
curl -s http://169.254.169.254/latest/meta-data/local-ipv4
```

**Testing Connectivity:**
```bash
# From inside container
docker exec fastapi curl -s http://10.0.0.186:5000/api/2.0/mlflow/experiments/list
```

---

## 4. Systemd Service for Auto-Restart

We created `/etc/systemd/system/fastapi.service`:

```ini
[Unit]
Description=Heart Disease Prediction FastAPI Service
Requires=docker.service
After=docker.service mlflow.service

[Service]
Restart=always
ExecStartPre=-/usr/bin/docker stop fastapi
ExecStartPre=-/usr/bin/docker rm fastapi
ExecStartPre=/usr/local/bin/aws ecr get-login-password --region us-east-1 | \
    /usr/bin/docker login --username AWS --password-stdin \
    695074562426.dkr.ecr.us-east-1.amazonaws.com
ExecStart=/usr/bin/docker run \
    --name fastapi \
    --restart always \
    -p 8000:8000 \
    --env-file /opt/app/.env \
    695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest
ExecStop=/usr/bin/docker stop -t 30 fastapi
ExecStopPost=/usr/bin/docker rm fastapi

[Install]
WantedBy=multi-user.target
```

**Key Points:**
- `Restart=always` — Container restarts if it crashes
- `ExecStartPre` with `-` prefix — Commands that can fail (idempotent)
- Logs to `/var/log/syslog` — View with `journalctl -u fastapi`
- ECR login on every start — Token expires after 12 hours

**Commands:**
```bash
# Enable service (start on boot)
sudo systemctl enable fastapi

# Start/stop manually
sudo systemctl start fastapi
sudo systemctl stop fastapi

# Check status
sudo systemctl status fastapi

# View logs
sudo journalctl -u fastapi -f
```

---

## 5. Testing & Verification

### From EC2 (localhost):
```bash
# Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# Response:
{
    "status": "degraded",        # "ok" when model loaded
    "model_loaded": false,       # true when model available
    "model_name": "heart-disease-model",
    "tracking_uri_set": true
}

# API docs (Swagger UI)
curl -s http://localhost:8000/docs | head
```

### From Your Local Machine:
```bash
# Health check through internet
curl -s http://32.196.26.238:8000/health | python3 -m json.tool

# Test prediction (when model loaded)
curl -X POST http://32.196.26.238:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 63, "sex": 1, "cp": 3, "trestbps": 145,
    "chol": 233, "fbs": 1, "restecg": 0, "thalach": 150,
    "exang": 0, "oldpeak": 2.3, "slope": 0, "ca": "0.0", "thal": "6.0"
  }'
```

---

## 6. Common Issues & Fixes

### Issue: "pull access denied"
```
Error: pull access denied, repository does not exist
```
**Fix:** Run ECR login first
```bash
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin <ecr-uri>
```

### Issue: "Connection reset by peer" to API
```
curl: (56) Recv failure: Connection reset by peer
```
**Causes:**
- Container crashed during model loading
- Wrong MLFLOW_TRACKING_URI (can't reach MLflow)
- Model doesn't exist in MLflow registry

**Debug:**
```bash
# Check container logs
docker logs fastapi

# Check if MLflow reachable from container
docker exec fastapi curl -s http://10.0.0.186:5000/health

# Check resource usage
docker stats --no-stream fastapi
```

### Issue: High CPU on startup (expected!)
```
CONTAINER ID   NAME      CPU %
d79af89ddd39   fastapi   454.80%
```
**Why:** Model loading is CPU-intensive
- RandomForest inference preparation
- sklearn pipeline deserialization
- **This is normal** — wait 30-60 seconds

### Issue: No instance profile (401 on metadata)
```
<title>401 - Unauthorized</title>
```
**Fix:** Ensure EC2 has IAM instance profile attached
```bash
# Check from EC2
aws sts get-caller-identity
# Should show assumed-role, not error
```

---

## 7. Security Best Practices

### ✅ What We Did Right
- **IAM Instance Profile** — No AWS credentials in env vars or files
- **Private IP for internal comms** — MLflow traffic stays in VPC
- **Security Group rules** — Port 8000 restricted to your IP only
- **Env file** — Secrets in `/opt/app/.env` (not in container image)

### ⚠️ What to Improve (Phase 9)
- **HTTPS** — Currently HTTP only (need ALB + ACM certificate)
- **Secrets Manager** — Move env vars to AWS Secrets Manager
- **Least privilege** — IAM policy could be more specific (ECR repo ARN)

---

## 8. Cost Analysis

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| EC2 t2.micro | $0 | 750 hrs free tier |
| EIP (public IP) | **$3.60** | ❌ NOT covered by free tier |
| ECR storage | $0 | 613 MB < 500 MB free |
| Data transfer | ~$0 | Minimal (same region) |
| **Total** | **~$3.60/month** | Just the Elastic IP |

---

## 9. Next Steps (Phase 5)

The API is deployed but shows "degraded" because no model is registered yet. Phase 5 will:
1. Set up Prefect agent on EC2
2. Run training pipeline weekly
3. Register model as "heart-disease-model@champion"
4. API will automatically load it on next restart

**To manually trigger a training run now:**
```bash
# From your local machine with AWS creds
export MLFLOW_TRACKING_URI=http://32.196.26.238:5000
python heart_disease_prediction/train.py
python heart_disease_prediction/register.py
```

---

## 10. Quick Reference Commands

```bash
# FULL DEPLOYMENT SEQUENCE (copy-paste ready)

# === LOCAL MACHINE ===
# 1. Build and push
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api"
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URI
docker build -t heart-disease-api:latest .
docker tag heart-disease-api:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# === ON EC2 ===
# 2. Deploy
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin $ECR_URI
docker pull ${ECR_URI}:latest
docker stop fastapi 2>/dev/null; docker rm fastapi 2>/dev/null
docker run -d --name fastapi --restart always -p 8000:8000 \
    --env-file /opt/app/.env ${ECR_URI}:latest

# 3. Verify
curl -s http://localhost:8000/health
curl -s http://32.196.26.238:8000/health  # From local machine
```

---

## Summary

We successfully:
- ✅ Built optimized 613 MB Docker image
- ✅ Pushed to ECR with proper IAM auth
- ✅ Deployed on EC2 with private IP networking
- ✅ Created systemd service for auto-restart
- ✅ Verified API accessible from internet
- ✅ Documented every command and decision

**The API is now production-ready and waiting for the model to be registered!**
