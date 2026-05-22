# 05 — Rollback & Notifications

## Why Rollback Matters

Production deployments can fail:
- Code bugs
- Missing environment variables
- Configuration errors
- Dependency issues
- External service failures (MLflow down, DB unavailable)

**Without rollback:**
- Service stays down until manual fix
- Production impact extended
- Emergency debugging under pressure

**With rollback:**
- Automatic revert to last working state
- Service restored in ~30 seconds
- Time to debug without pressure

---

## Our Rollback Strategy

### Commit SHA Tagging

Every Docker image gets two tags:

```bash
# Build
docker build -t $ECR_REGISTRY/my-app:sha-a1b2c3d .
docker tag $ECR_REGISTRY/my-app:sha-a1b2c3d $ECR_REGISTRY/my-app:latest
docker push $ECR_REGISTRY/my-app:sha-a1b2c3d
docker push $ECR_REGISTRY/my-app:latest
```

**Tag purposes:**

| Tag | Use Case |
|-----|----------|
| `sha-a1b2c3d` | **Rollback** — Exact version, never changes |
| `latest` | **Convenience** — Always current, moves forward |

**Why SHA tagging works:**
- Every commit produces a unique image
- Previous versions are preserved
- No ambiguity about "what was running before"

---

### Rollback Mechanism

```yaml
# .github/workflows/cd.yml (relevant sections)

jobs:
  deploy:
    outputs:
      previous_image: ${{ steps.save.outputs.previous_image }}
    
    steps:
      # 1. Save current state BEFORE deploying
      - name: Save previous image
        id: save
        run: |
          PREVIOUS=$(ssh ubuntu@32.196.26.238 \
            "sudo docker ps --format '{{.Image}}' | grep heart-disease || echo 'none'")
          echo "previous_image=$PREVIOUS" >> $GITHUB_OUTPUT
      
      # 2. Deploy new image
      - name: Deploy new image
        run: |
          ssh ubuntu@32.196.26.238 << 'EOF'
            sudo docker pull $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
            sudo docker stop fastapi || true
            sudo docker rm fastapi || true
            sudo docker run -d --name fastapi ... $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          EOF
      
      # 3. Health check
      - name: Health check
        id: healthcheck
        run: |
          for i in {1..5}; do
            if curl -s http://32.196.26.238:8000/health | grep -q '"model_loaded": true'; then
              echo "success" >> $GITHUB_OUTPUT
              exit 0
            fi
            sleep 10
          done
          echo "failed" >> $GITHUB_OUTPUT
          exit 1
      
      # 4. ROLLBACK if health check failed
      - name: Rollback
        if: failure() && steps.healthcheck.outputs.status == 'failed'
        env:
          PREVIOUS: ${{ steps.save.outputs.previous_image }}
        run: |
          echo "🚨 Rolling back to: $PREVIOUS"
          
          ssh ubuntu@32.196.26.238 << 'EOF'
            # Stop failed container
            sudo docker stop fastapi || true
            sudo docker rm fastapi || true
            
            # If we have a previous image, use it
            if [ "$PREVIOUS" != "none" ] && [ -n "$PREVIOUS" ]; then
              sudo docker run -d --name fastapi --restart always -p 8000:8000 \
                -e MLFLOW_TRACKING_URI=http://10.0.0.186:5000 \
                -e MODEL_NAME=best_model_2025-07-30 \
                $PREVIOUS
            else
              # Fallback to ECR latest
              sudo docker run -d --name fastapi --restart always -p 8000:8000 \
                -e MLFLOW_TRACKING_URI=http://10.0.0.186:5000 \
                -e MODEL_NAME=best_model_2025-07-30 \
                $ECR_REGISTRY/$ECR_REPOSITORY:latest
            fi
          EOF
          
          echo "✅ Rollback complete"
```

---

## Rollback Flow Diagram

```
Deploy Workflow
        │
        ▼
┌───────────────────┐
│ 1. Save current   │◄──┐
│    image tag      │   │
└─────────┬─────────┘   │
          │             │
          ▼             │
┌───────────────────┐   │
│ 2. Pull & deploy  │   │
│    new image      │   │
└─────────┬─────────┘   │
          │             │
          ▼             │
┌───────────────────┐   │
│ 3. Health check   │   │
│    (5 retries)    │   │
└─────────┬─────────┘   │
          │             │
     ┌────┴────┐        │
     │         │        │
     ▼         ▼        │
┌────────┐  ┌────────┐  │
│ PASS   │  │ FAIL   │  │
└───┬────┘  └───┬────┘  │
    │           │       │
    ▼           ▼       │
┌────────┐  ┌────────┐  │
│ Success│  │ Rollback│──┘
│ notify │  │ to saved│
└────────┘  │ image   │
            └────┬───┘
                 │
                 ▼
            ┌────────┐
            │ Failure│
            │ notify │
            └────────┘
```

---

## Rollback Scenarios

### Scenario 1: Code Bug

**What happened:**
```python
# Broken code deployed
@app.get("/health")
def health():
    model = load_model()  # Always reloads - slow!
    return {"model_loaded": model is not None}  # Bug: None check wrong
```

**Health check:**
```bash
curl http://32.196.26.238:8000/health
# {"model_loaded": false}  ← FAIL
```

**Rollback:**
```bash
# Stop broken container
sudo docker stop fastapi

# Start previous (working) image
sudo docker run -d ... $ECR_REGISTRY/my-app:sha-previous123

# Verify
curl http://32.196.26.238:8000/health
# {"model_loaded": true}  ← SUCCESS
```

---

### Scenario 2: Missing Environment Variable

**What happened:**
```yaml
# Forgot to include MODEL_NAME in deployment
- name: Deploy
  run: |
    docker run -d ... \\
      -e MLFLOW_TRACKING_URI=http://10.0.0.186:5000 \\
      # Missing: -e MODEL_NAME=...
      $IMAGE
```

**Result:**
```python
# api/main.py tries to load model
model_name = os.getenv("MODEL_NAME")  # None
mlflow.pyfunc.load_model(f"models:/{model_name}@champion")  # Fails!
```

**Health check:** Fails, rollback triggered.

---

### Scenario 3: MLflow Unavailable

**What happened:**
- MLflow service crashed on EC2
- FastAPI container can't load model

**Health check:**
```json
{
  "status": "error",
  "model_loaded": false,
  "error": "Connection refused to MLflow at 10.0.0.186:5000"
}
```

**Rollback:** Reverts to previous container, but it also fails (same MLflow issue).

**Result:** Rollback fails, SNS alert sent, manual intervention required.

**Lesson:** Rollback helps with application bugs, not infrastructure failures.

---

## SNS Notifications

### What Gets Notified

Every CD workflow run sends a notification:

| Outcome | Email Subject | Email Body |
|---------|---------------|------------|
| Success | ✅ Deploy SUCCESS | Image tag, timestamp, commit SHA |
| Failure + Rollback | ⚠️ Deploy FAILED (rolled back) | Error details, rollback image |
| Failure (no rollback) | ❌ Deploy FAILED | Error details, manual action needed |

---

### Notification Configuration

**SNS Topic:** Already created in Phase 6

```bash
# Verify topic exists
aws sns list-topics --query 'Topics[*].TopicArn'

# Verify email subscription
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:695074562426:heart-disease-mlops-alarms

# Output:
# {
#   "Subscriptions": [
#     {
#       "SubscriptionArn": "arn:aws:sns:...:heart-disease-mlops-alarms:abc123",
#       "Owner": "695074562426",
#       "Protocol": "email",
#       "Endpoint": "your-email@example.com",
#       "TopicArn": "arn:aws:sns:...:heart-disease-mlops-alarms"
#     }
#   ]
# }
```

---

### CD Workflow Notification

```yaml
- name: Notify SNS
  if: always()  # Run even if previous steps failed
  env:
    STATUS: ${{ steps.healthcheck.outputs.status }}
    IMAGE_TAG: sha-${{ github.sha }}
    SNS_TOPIC: ${{ secrets.SNS_TOPIC_ARN }}
  run: |
    # Build message based on outcome
    if [ "$STATUS" == "success" ]; then
      MESSAGE=$(cat <<EOF
✅ **Deploy SUCCESS**

Repository: abandonedmonk/MLOps-Zoomcamp-Project
Branch: ${{ github.ref_name }}
Commit: ${{ github.sha }}
Image: $IMAGE_TAG
Environment: http://32.196.26.238:8000
Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
EOF
)
      SUBJECT="✅ MLOps Deploy SUCCESS"
      
    elif [ "$STATUS" == "failed" ] && [ "${{ steps.rollback.outcome }}" == "success" ]; then
      MESSAGE=$(cat <<EOF
⚠️ **Deploy FAILED - Auto Rollback**

Repository: abandonedmonk/MLOps-Zoomcamp-Project
Branch: ${{ github.ref_name }}
Commit: ${{ github.sha }}
Failed Image: $IMAGE_TAG
Rollback Image: ${{ steps.save.outputs.previous_image }}
Error: Health check failed after deployment
Action: Automatically rolled back to previous image
Environment: http://32.196.26.238:8000 (operational)
Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
EOF
)
      SUBJECT="⚠️ MLOps Deploy FAILED (Rolled Back)"
      
    else
      MESSAGE=$(cat <<EOF
❌ **Deploy FAILED - Manual Action Required**

Repository: abandonedmonk/MLOps-Zoomcamp-Project
Branch: ${{ github.ref_name }}
Commit: ${{ github.sha }}
Failed Image: $IMAGE_TAG
Error: Health check failed AND rollback failed
Environment: http://32.196.26.238:8000 (DOWN)
Action Required: Investigate and manually deploy
Run ID: ${{ github.run_id }}
Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
EOF
)
      SUBJECT="❌ MLOps Deploy FAILED (Manual Action Required)"
    fi
    
    # Send notification
    aws sns publish \
      --topic-arn "$SNS_TOPIC" \
      --subject "$SUBJECT" \
      --message "$MESSAGE"
```

---

### Sample Email (Success)

```
From: AWS Notifications <no-reply@sns.amazonaws.com>
To: your-email@example.com
Subject: ✅ MLOps Deploy SUCCESS

✅ **Deploy SUCCESS**

Repository: abandonedmonk/MLOps-Zoomcamp-Project
Branch: aws_migration
Commit: a1b2c3d4e5f6...
Image: sha-a1b2c3d
Environment: http://32.196.26.238:8000
Timestamp: 2025-07-30 14:32:10 UTC

The new version is live and responding to health checks.
```

### Sample Email (Rollback)

```
From: AWS Notifications <no-reply@sns.amazonaws.com>
To: your-email@example.com
Subject: ⚠️ MLOps Deploy FAILED (Rolled Back)

⚠️ **Deploy FAILED - Auto Rollback**

Repository: abandonedmonk/MLOps-Zoomcamp-Project
Branch: aws_migration
Commit: a1b2c3d4e5f6...
Failed Image: sha-a1b2c3d
Rollback Image: 695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:sha-previous456
Error: Health check failed after deployment
Action: Automatically rolled back to previous image
Environment: http://32.196.26.238:8000 (operational)
Timestamp: 2025-07-30 14:33:45 UTC

The service is operational on the previous version.
Please review the failed deployment at:
https://github.com/abandonedmonk/MLOps-Zoomcamp-Project/actions/runs/123456789
```

---

## Testing Rollback

### Create a Broken Deployment

```bash
# 1. Create broken code branch
git checkout -b test-rollback

# 2. Introduce a bug
cat > api/main.py << 'EOF'
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    # Intentionally broken
    return {"model_loaded": False, "error": "Test rollback"}
EOF

# 3. Commit and push
git add api/main.py
git commit -m "BREAK: Test rollback system"
git push origin test-rollback

# 4. Merge to aws_migration (simulates bad deploy)
git checkout aws_migration
git merge test-rollback
git push origin aws_migration
```

**Expected:**
1. CD workflow triggers
2. Docker builds successfully
3. Deploys to EC2
4. Health check fails (returns `"model_loaded": false`)
5. Rollback to previous image
6. SNS email: "⚠️ Deploy FAILED (Rolled Back)"
7. Service operational on previous version

### Verify Rollback

```bash
# Check which image is running
ssh ubuntu@32.196.26.238 "sudo docker ps --format '{{.Image}}'"

# Should show previous SHA, not the broken one

# Check health
curl http://32.196.26.238:8000/health
# {"model_loaded": true}  ← Working!

# Check email
# Look for "⚠️ Deploy FAILED (Rolled Back)" message
```

---

## Rollback Limitations

### What Rollback Handles

✅ Application code bugs  
✅ Configuration errors  
✅ Missing dependencies  
✅ Wrong environment variables  
✅ Build issues

### What Rollback Doesn't Handle

❌ Infrastructure failures (MLflow down, DB unavailable)  
❌ Data corruption (bad model artifacts)  
❌ External API changes  
❌ Security vulnerabilities (rollback keeps them too)

---

## Best Practices

### 1. Small, Frequent Deployments

```
❌ Big bang deployment: 100 changes at once
   → If rollback needed, lose 100 changes worth of work

✅ Small deployments: 5-10 changes at once
   → Rollback loses minimal work
   → Easier to identify culprit
```

### 2. Feature Flags

```python
# Instead of all-or-nothing deployment
@app.post("/predict")
def predict(request: PredictionRequest):
    if os.getenv("NEW_MODEL_ENABLED") == "true":
        return new_model.predict(request.features)
    else:
        return old_model.predict(request.features)
```

Enable new model gradually, rollback by flipping flag.

### 3. Database Migrations

```
Problem: DB migration runs, then app deployment fails
Result: Can't rollback app without breaking DB

Solution: Make migrations backward compatible
- Add columns (nullable) before using them
- Don't drop columns immediately
- Maintain backward compatibility
```

### 4. Health Check Coverage

```python
@app.get("/health")
def health():
    checks = {
        "model_loaded": model is not None,
        "mlflow_reachable": check_mlflow_connection(),
        "db_reachable": check_database_connection(),  # If we had one
        "disk_space": check_disk_space(),
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "ok" if all_healthy else "degraded",
        "checks": checks
    }
```

More comprehensive checks = earlier failure detection.

---

## Key Metrics

| Metric | Target | Current |
|--------|--------|---------|
| **Rollback time** | < 1 minute | ~30 seconds |
| **Health check timeout** | < 60 seconds | 50 seconds (5 retries × 10s) |
| **Image retention** | Last 30 versions | ECR default |
| **Notification delay** | < 1 minute | Immediate |

---

## Key Takeaways

1. **SHA tagging** enables deterministic rollback
2. **Health checks** verify actual functionality
3. **Automatic rollback** restores service quickly
4. **SNS notifications** keep you informed
5. **Test rollback** regularly to ensure it works
6. **Rollback has limits** — infrastructure failures need different handling

---

## Next Steps

- ✅ Read [06 — Troubleshooting CI/CD](06-troubleshooting-cicd.md)
- ✅ Test rollback with broken deployment
- ✅ Verify SNS email received
- ✅ Document rollback time in runbook
- ✅ Move to Phase 8: Real Testing
