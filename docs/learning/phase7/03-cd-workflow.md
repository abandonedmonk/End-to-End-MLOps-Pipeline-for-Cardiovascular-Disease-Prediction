# 03 — CD Workflow: Build, Push, Deploy

## What is Continuous Deployment (CD)?

**CD** automatically deploys code changes to production after they pass CI. Our workflow:

1. Build Docker image
2. Push to Amazon ECR
3. SSH to EC2
4. Deploy new container
5. Health check
6. Notify via SNS

---

## CD Workflow Overview

```yaml
# .github/workflows/cd.yml (simplified)
name: CD

on:
  push:
    branches: [main, aws_migration]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
      
      - uses: aws-actions/amazon-ecr-login@v2
        id: login-ecr
      
      - name: Build and push
        run: |
          docker build -t $ECR_REGISTRY/my-app:sha-${GITHUB_SHA::7} .
          docker push $ECR_REGISTRY/my-app:sha-${GITHUB_SHA::7}
      
      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.EC2_SSH_KEY }}
      
      - name: Deploy to EC2
        run: |
          ssh ubuntu@32.196.26.238 "docker pull ... && docker run ..."
      
      - name: Health check
        run: curl http://32.196.26.238:8000/health
      
      - name: Notify SNS
        if: always()
        run: aws sns publish ...
```

---

## Step-by-Step Breakdown

### Step 1: Trigger

```yaml
on:
  push:
    branches: [main, aws_migration]
```

**When it runs:**
- Every push to `main` branch
- Every push to `aws_migration` branch

**Why both:**
- `main` is the production branch
- `aws_migration` is our current development branch (will merge to main later)

---

### Step 2: OIDC Authentication

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
    aws-region: us-east-1
```

**What it does:**
1. Requests JWT token from GitHub OIDC provider
2. Exchanges token for AWS credentials via `sts:AssumeRoleWithWebIdentity`
3. Sets up AWS CLI environment

**Result:** AWS CLI commands work without explicit credentials.

---

### Step 3: ECR Login

```yaml
- uses: aws-actions/amazon-ecr-login@v2
  id: login-ecr
```

**What it does:**
- Gets ECR authorization token via `aws ecr get-login-password`
- Runs `docker login` with ECR registry

**Output:**
- `${{ steps.login-ecr.outputs.registry }}` → `695074562426.dkr.ecr.us-east-1.amazonaws.com`

---

### Step 4: Build and Tag

```yaml
- name: Build, tag, and push image
  id: build
  env:
    ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
    IMAGE_TAG: sha-${{ github.sha }}
  run: |
    # Build with commit SHA tag
    docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
    
    # Also tag as latest
    docker tag $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG \
               $ECR_REGISTRY/$ECR_REPOSITORY:latest
    
    # Push both tags
    docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
    docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest
```

**Why two tags?**

| Tag | Purpose |
|-----|---------|
| `sha-abc1234` | **Deterministic** — Exact version for rollback |
| `latest` | **Convenience** — Easy to pull latest for manual testing |

**Commit SHA:**
- `github.sha` → Full SHA: `a1b2c3d4e5f6...`
- `${GITHUB_SHA::7}` → Short SHA: `a1b2c3d`

---

### Step 5: SSH Setup

```yaml
- uses: webfactory/ssh-agent@v0.9.0
  with:
    ssh-private-key: ${{ secrets.EC2_SSH_KEY }}

- name: Add to known hosts
  run: ssh-keyscan -H 32.196.26.238 >> ~/.ssh/known_hosts
```

**Why needed:**
- GitHub Actions needs to SSH into EC2
- SSH agent holds the private key
- `ssh-keyscan` prevents "unknown host" prompts

**Alternative (less secure):**
```yaml
# DON'T DO THIS — disables host checking
run: |
  ssh -o StrictHostKeyChecking=no ubuntu@32.196.26.238 ...
```

---

### Step 6: Deploy to EC2

```yaml
- name: Deploy to EC2
  id: deploy
  run: |
    # Get currently running image for rollback
    PREVIOUS_IMAGE=$(ssh ubuntu@32.196.26.238 \
      "sudo docker ps --format '{{.Image}}' | grep heart-disease || echo 'none'")
    
    # Deploy via SSH
    ssh ubuntu@32.196.26.238 << 'EOF'
      # Login to ECR
      aws ecr get-login-password | sudo docker login --username AWS --password-stdin $ECR_REGISTRY
      
      # Pull new image
      sudo docker pull $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
      
      # Stop and remove old container
      sudo docker stop fastapi || true
      sudo docker rm fastapi || true
      
      # Start new container
      sudo docker run -d \
        --name fastapi \
        --restart always \
        -p 8000:8000 \
        -e MLFLOW_TRACKING_URI=http://10.0.0.186:5000 \
        -e MODEL_NAME=best_model_2025-07-30 \
        -e AWS_REGION=us-east-1 \
        $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
    EOF
```

**Key Points:**

| Element | Purpose |
|---------|---------|
| `sudo docker` | Docker requires root on this EC2 |
| `|| true` | Continue even if command fails (container might not exist) |
| `--restart always` | Auto-restart on crash or reboot |
| `-p 8000:8000` | Map host port to container port |
| `-e ...` | Environment variables for the application |

---

### Step 7: Health Check

```yaml
- name: Health Check
  id: healthcheck
  run: |
    # Wait for startup
    sleep 10
    
    # Retry up to 5 times
    for i in {1..5}; do
      RESPONSE=$(curl -s http://32.196.26.238:8000/health || echo "FAILED")
      
      # Check if model loaded
      if echo "$RESPONSE" | grep -q '"model_loaded": true'; then
        echo "✓ Health check passed"
        exit 0
      fi
      
      echo "Attempt $i/5 failed. Retrying..."
      sleep 10
    done
    
    echo "✗ Health check failed"
    exit 1
```

**Why important:**
- Container running ≠ Application working
- Model might fail to load from MLflow
- Health check verifies actual functionality

**Our `/health` endpoint:**
```json
{
  "status": "ok",
  "model_loaded": true,
  "model_name": "best_model_2025-07-30",
  "timestamp": "2025-07-30T12:34:56Z"
}
```

---

### Step 8: Notification

```yaml
- name: Notify SNS
  if: always()
  run: |
    if [ "${{ steps.healthcheck.outputs.status }}" == "success" ]; then
      MESSAGE="✅ Deploy SUCCESS: $IMAGE_TAG"
    else
      MESSAGE="❌ Deploy FAILED: $IMAGE_TAG"
    fi
    
    aws sns publish \
      --topic-arn ${{ secrets.SNS_TOPIC_ARN }} \
      --message "$MESSAGE" \
      --subject "MLOps Deploy"
```

**`if: always()`** — Runs even if previous steps failed.

---

## Complete Deployment Flow

```
Developer pushes to main
        │
        ▼
┌───────────────────┐
│ GitHub Actions    │
│ triggers CD       │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ OIDC Auth         │
│ (AWS credentials) │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Build Docker      │
│ image             │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Tag with SHA      │
│ Tag as latest     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Push to ECR       │
│ (both tags)       │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ SSH to EC2        │
│ 32.196.26.238     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Docker pull       │
│ new image         │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Stop old          │
│ container         │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Start new         │
│ container         │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Health check      │
│ /health endpoint  │
└─────────┬─────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌───────┐  ┌───────────┐
│ PASS  │  │   FAIL    │
└───┬───┘  └─────┬─────┘
    │            │
    ▼            ▼
┌────────┐  ┌──────────┐
│ SNS:   │  │ Rollback │
│ SUCCESS│  │ to prev  │
└────────┘  └────┬─────┘
                 │
                 ▼
            ┌──────────┐
            │ SNS:     │
            │ FAILED   │
            └──────────┘
```

---

## Environment Variables

The container needs these env vars:

| Variable | Value | Purpose |
|----------|-------|---------|
| `MLFLOW_TRACKING_URI` | `http://10.0.0.186:5000` | Connect to MLflow on EC2 |
| `MODEL_NAME` | `best_model_2025-07-30` | Which model to load at startup |
| `AWS_REGION` | `us-east-1` | AWS SDK default region |

**Why use private IP (10.0.0.186)?**

Containers have isolated network namespaces:
- `localhost` in container → container itself
- `localhost` on host → host machine
- Private IP (`10.0.0.186`) → host's network

So containers must use the EC2's private IP to reach MLflow.

---

## Rollback System

See [05 — Rollback & Notifications](05-rollback-and-notifications.md) for detailed rollback logic.

Quick overview:

```yaml
# Before deploying, save current state
- name: Save previous image
  id: save
  run: |
    PREVIOUS=$(ssh ubuntu@32.196.26.238 \
      "sudo docker ps --format '{{.Image}}' | grep heart-disease")
    echo "previous_image=$PREVIOUS" >> $GITHUB_OUTPUT

# After failed health check
- name: Rollback
  if: failure()
  run: |
    ssh ubuntu@32.196.26.238 \
      "sudo docker stop fastapi && sudo docker rm fastapi && \
       sudo docker run -d --name fastapi ... ${{ steps.save.outputs.previous_image }}"
```

---

## Timing Estimates

| Step | Typical Duration |
|------|------------------|
| OIDC auth | 5 seconds |
| Docker build | 2-4 minutes |
| ECR push | 30-60 seconds |
| SSH + deploy | 30 seconds |
| Health check | 10-50 seconds |
| **Total** | **3-5 minutes** |

---

## Verification Commands

### Check Workflow Runs

```bash
# List recent runs
gh run list --workflow=CD

# View specific run
gh run view <run-id>

# Watch live
gh run watch <run-id>

# View logs for specific job
gh run view <run-id> --job=deploy
```

### Check ECR Images

```bash
# List images
aws ecr describe-images \
  --repository-name heart-disease-mlops-api \
  --query 'imageDetails[*].{Tag:imageTags[0],PushedAt:imagePushedAt}'

# Example output:
# [
#   {"Tag": "sha-a1b2c3d", "PushedAt": "2025-07-30T12:00:00Z"},
#   {"Tag": "latest", "PushedAt": "2025-07-30T12:00:00Z"}
# ]
```

### Verify Deployment

```bash
# Check container is running
ssh ubuntu@32.196.26.238 "sudo docker ps | grep fastapi"

# Check container logs
ssh ubuntu@32.196.26.238 "sudo docker logs fastapi --tail 50"

# Test health endpoint
curl http://32.196.26.238:8000/health

# Test prediction endpoint
curl -X POST http://32.196.26.238:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"features": [63,1,1,145,233,1,2,150,0,2.3,3,0,6]}'
```

---

## Troubleshooting

### Issue: "Cannot connect to Docker daemon"

**Cause:** SSH user doesn't have Docker permissions.

**Fix:** Use `sudo docker` or add user to docker group.

### Issue: "Health check timeout"

**Cause:** Model loading from MLflow is slow.

**Fix:** Increase sleep time or retry count.

### Issue: "Permission denied (publickey)"

**Cause:** SSH key not set up correctly.

**Fix:**
1. Check `EC2_SSH_KEY` secret is correct
2. Ensure public key in EC2 `~/.ssh/authorized_keys`
3. Check SSH agent is configured

### Issue: "Image not found in ECR"

**Cause:** Build failed or wrong repository name.

**Fix:** Check `ECR_REPOSITORY` env var matches actual repo name.

---

## Key Takeaways

1. **Push triggers deploy** — Every commit to main deploys automatically
2. **Two tags** — SHA for rollback, latest for convenience
3. **Health checks** — Verify actual functionality, not just "running"
4. **SSH deployment** — Simple but effective for single EC2
5. **Notifications** — Know immediately if deploy succeeds or fails

---

## Next Steps

- ✅ Read [04 — Terraform Automation](04-terraform-automation.md) for infrastructure CI/CD
- ✅ Read [05 — Rollback & Notifications](05-rollback-and-notifications.md) for detailed rollback logic
- ✅ Push empty commit to test CD: `git commit --allow-empty -m "Test" && git push`
- ✅ Check SNS email for deploy notification
