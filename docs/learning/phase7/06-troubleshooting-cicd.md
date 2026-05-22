# 06 — Troubleshooting CI/CD

Common issues and how to fix them.

---

## Table of Contents

1. [OIDC Authentication Issues](#oidc-authentication-issues)
2. [Docker Build Issues](#docker-build-issues)
3. [ECR Push Issues](#ecr-push-issues)
4. [SSH Connection Issues](#ssh-connection-issues)
5. [Deployment Issues](#deployment-issues)
6. [Health Check Issues](#health-check-issues)
7. [Rollback Issues](#rollback-issues)
8. [Terraform Issues](#terraform-issues)
9. [General Debugging](#general-debugging)

---

## OIDC Authentication Issues

### Error: "Could not assume role"

**Full error:**
```
Error: Could not assume role with OIDC provider
Error: Not authorized to perform sts:AssumeRoleWithWebIdentity
```

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Wrong role ARN in GitHub secret | `terraform -chdir=infra output github_actions_role_arn` and update secret |
| Trust policy doesn't match repo | Check `sub` condition matches `abandonedmonk/MLOps-Zoomcamp-Project` |
| Missing `id-token: write` permission | Add to job permissions |
| OIDC provider not created | Run `terraform apply` in `infra/` |

**Debug:**
```bash
# Check trust policy
aws iam get-role --role-name heart-disease-mlops-github-actions \
  --query 'Role.AssumeRolePolicyDocument'

# Should contain:
# "sub": "repo:abandonedmonk/MLOps-Zoomcamp-Project:*"
```

---

### Error: "Unable to request token"

**Full error:**
```
Error: Unable to get ID token
Error: make sure to give write permissions for id-token
```

**Fix:**
```yaml
jobs:
  deploy:
    permissions:
      id-token: write      # REQUIRED
      contents: read
```

---

### Error: "The security token included in the request is expired"

**Cause:** Job ran longer than role duration (default 1 hour).

**Fix:**
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
    role-duration-seconds: 7200  # 2 hours
```

Or split long jobs into smaller ones.

---

## Docker Build Issues

### Error: "Cannot connect to Docker daemon"

**Full error:**
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
Is the docker daemon running?
```

**Cause:** GitHub Actions runner doesn't have Docker.

**Fix:** Use `ubuntu-latest` runner (has Docker pre-installed).

**Wrong:**
```yaml
runs-on: self-hosted  # Might not have Docker
```

**Right:**
```yaml
runs-on: ubuntu-latest  # Has Docker
```

---

### Error: "Build takes too long"

**Problem:** Docker builds 5+ minutes every time.

**Solutions:**

1. **Layer caching:**
```yaml
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: myapp:latest
    cache-from: type=gha  # GitHub Actions cache
    cache-to: type=gha,mode=max
```

2. **Optimize Dockerfile:**
```dockerfile
# Good: Copy requirements first (cached layer)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bad: Copy everything first (invalidates cache)
COPY . .
RUN pip install -r requirements.txt  # Reinstalls on every code change
```

---

### Error: "No space left on device"

**Cause:** Docker layer cache filled disk.

**Fix:**
```yaml
- name: Clean up Docker
  run: |
    docker system prune -af
    docker volume prune -f
```

Or use smaller base images:
```dockerfile
# Bad: 1+ GB
FROM python:3.12

# Good: ~50 MB
FROM python:3.12-slim
```

---

## ECR Push Issues

### Error: "denied: Not Authorized"

**Full error:**
```
denied: Not Authorized
unauthorized: authentication required
```

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Not logged in | Ensure `amazon-ecr-login` step runs before push |
| Wrong registry URL | Check `ECR_REGISTRY` matches login output |
| IAM permissions | Role needs `ecr:PutImage`, `ecr:InitiateLayerUpload`, etc. |

**Debug:**
```bash
# Verify login
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

# Should show: Login Succeeded
```

---

### Error: "name unknown: The repository with name 'xxx' does not exist"

**Cause:** ECR repository doesn't exist.

**Fix:**
1. Create via Terraform: `terraform apply` in `infra/`
2. Or manually: AWS Console → ECR → Create repository

**Verify:**
```bash
aws ecr describe-repositories --repository-names heart-disease-mlops-api
```

---

## SSH Connection Issues

### Error: "Permission denied (publickey)"

**Full error:**
```
ubuntu@32.196.26.238: Permission denied (publickey).
Error: Process completed with exit code 255.
```

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Wrong SSH key in GitHub secret | Verify `cat ~/.ssh/id_ed25519` matches `EC2_SSH_KEY` |
| Public key not on EC2 | SSH manually and add key to `~/.ssh/authorized_keys` |
| Wrong EC2 user | Should be `ubuntu` (not `ec2-user` or `root`) |
| EC2 IP changed | Update `EC2_HOST` secret to new Elastic IP |

**Verify:**
```bash
# Test from local machine
ssh -i ~/.ssh/id_ed25519 ubuntu@32.196.26.238 echo "Success"

# If that works, the key is correct
```

---

### Error: "Host key verification failed"

**Full error:**
```
Host key verification failed.
```

**Fix:** Add host to known hosts in workflow:
```yaml
- name: Setup SSH
  uses: webfactory/ssh-agent@v0.9.0
  with:
    ssh-private-key: ${{ secrets.EC2_SSH_KEY }}

- name: Add to known hosts
  run: ssh-keyscan -H 32.196.26.238 >> ~/.ssh/known_hosts
```

**Less secure alternative (not recommended):**
```bash
ssh -o StrictHostKeyChecking=no ubuntu@32.196.26.238 ...
```

---

### Error: "Connection refused" or "Connection timed out"

**Causes:**
1. EC2 is down or rebooting
2. Security group blocks SSH (port 22)
3. Wrong IP address
4. Network issues

**Debug:**
```bash
# Check if EC2 is running
aws ec2 describe-instances --instance-ids <id> --query 'Reservations[0].Instances[0].State.Name'

# Check security group allows SSH
aws ec2 describe-security-groups --group-ids <sg-id> --query 'SecurityGroups[0].IpPermissions'

# Test connectivity
telnet 32.196.26.238 22
```

---

## Deployment Issues

### Error: "Cannot connect to Docker daemon" on EC2

**Full error:**
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
Got permission denied while trying to connect
```

**Fix:** Use `sudo`:
```bash
ssh ubuntu@32.196.26.238 "sudo docker ps"
```

Or add user to docker group (requires re-login):
```bash
sudo usermod -aG docker ubuntu
# Logout and back in
```

---

### Error: "Container name already in use"

**Full error:**
```
docker: Error response from daemon: Conflict. The container name "/fastapi" is already in use.
```

**Fix:** Remove old container first:
```bash
docker stop fastapi || true
docker rm fastapi || true
docker run -d --name fastapi ...
```

---

### Error: "Port already in use"

**Full error:**
```
docker: Error response from daemon: driver failed programming external connectivity: 
Bind for 0.0.0.0:8000 failed: port is already allocated.
```

**Fix:** Stop container using the port:
```bash
# Find container using port
sudo docker ps --filter "publish=8000"

# Stop it
sudo docker stop <container-id>

# Or use different port (not recommended, breaks API URL)
docker run -p 8001:8000 ...
```

---

### Error: "Image not found locally"

**Cause:** Didn't pull from ECR before running.

**Fix:**
```bash
# Login and pull first
aws ecr get-login-password | sudo docker login --username AWS --password-stdin <registry>
sudo docker pull <image-uri>

# Then run
sudo docker run ... <image-uri>
```

---

## Health Check Issues

### Error: "Health check timeout"

**Full error:**
```
Attempt 1/5 failed. Retrying...
...
Health check failed after 5 attempts
```

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Container hasn't started | Increase initial sleep (e.g., `sleep 20`) |
| Model loading slow | Increase retry count or sleep between retries |
| Wrong health URL | Verify `http://32.196.26.238:8000/health` |
| Container crashed | Check logs: `docker logs fastapi` |
| MLflow unreachable | Verify MLflow at `http://10.0.0.186:5000` |

**Debug:**
```bash
# Check container status
ssh ubuntu@32.196.26.238 "sudo docker ps -a"

# Check logs
ssh ubuntu@32.196.26.238 "sudo docker logs fastapi --tail 100"

# Test manually
ssh ubuntu@32.196.26.238 "curl -s http://localhost:8000/health"

# Check MLflow
ssh ubuntu@32.196.26.238 "curl -s http://10.0.0.186:5000/health"
```

---

### Error: "model_loaded: false"

**Cause:** Model failed to load.

**Check logs:**
```bash
ssh ubuntu@32.196.26.238 "sudo docker logs fastapi"
```

**Common causes:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| `MLflowException: Model not found` | Wrong `MODEL_NAME` | Update to registered model name |
| `Connection refused` | MLflow down | Restart MLflow service |
| `Permission denied` | IAM role missing S3 permissions | Add `s3:GetObject` |
| `Module not found` | Missing dependencies | Update `requirements.txt` |

---

## Rollback Issues

### Error: "Rollback step skipped after failure"

**Cause:** GitHub Actions skips subsequent steps after failure.

**Fix:** Use `if: failure()`:
```yaml
- name: Rollback
  if: failure()  # Run even if previous step failed
  run: |
    # rollback commands
```

---

### Error: "Previous image is 'none'"

**Cause:** No container was running before deployment.

**Fix:** Check for running container before capturing:
```bash
PREVIOUS=$(ssh ubuntu@32.196.26.238 \
  "sudo docker ps --format '{{.Image}}' | grep heart-disease || echo 'none'")

if [ "$PREVIOUS" == "none" ]; then
  echo "No previous container found, using ECR:latest as fallback"
  PREVIOUS="$ECR_REGISTRY/$ECR_REPOSITORY:latest"
fi
```

---

### Rollback succeeds but service still broken

**Cause:** Infrastructure failure (not code issue).

**Check:**
```bash
# Is MLflow running?
ssh ubuntu@32.196.26.238 "sudo docker ps | grep mlflow"

# Is RDS accessible?
ssh ubuntu@32.196.26.238 "nc -zv heart-disease-mlops-db... 5432"

# Is S3 reachable?
ssh ubuntu@32.196.26.238 "aws s3 ls s3://heart-disease-mlops-*"
```

**Note:** Rollback helps with code bugs, not infrastructure failures.

---

## Terraform Issues

### Error: "Failed to query available provider packages"

**Cause:** Terraform can't download providers (timeout).

**Fix:**
1. Commit `.terraform.lock.hcl` to git
2. Use GitHub cache:
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.terraform.d/plugin-cache
    key: terraform-${{ hashFiles('**/*.tf') }}
```

---

### Error: "Error acquiring the state lock"

**Full error:**
```
Error: Error acquiring the state lock
Lock Info:
  ID:        abc123
  Operation: OperationTypeApply
  Who:       ubuntu@runner
```

**Fix:** Force unlock (careful!):
```bash
cd infra
terraform force-unlock abc123
```

**Prevention:**
- Don't cancel workflows mid-apply
- Use `continue-on-error: true` for plan steps
- Enable graceful shutdown in GitHub Actions

---

### Error: "No changes detected" when there should be changes

**Causes:**
1. Path filter wrong (workflow didn't trigger)
2. Files in wrong directory
3. State already applied

**Debug:**
```bash
# Check if workflow triggered
git log --oneline -5

# Check what files changed
git diff HEAD~1 --name-only

# Manual plan
cd infra
terraform plan
```

---

### Error: "Insufficient permissions"

**Cause:** GitHub Actions role missing Terraform permissions.

**Fix:** Add to IAM role policy:
```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:*",
    "s3:*",
    "rds:*",
    "iam:*",
    "sns:*",
    "cloudwatch:*",
    "dynamodb:*"
  ],
  "Resource": "*"
}
```

**Note:** Scope down for production (specific resources, not `*`).

---

## General Debugging

### Enable Debug Logging

In GitHub Actions workflow:
```yaml
env:
  ACTIONS_STEP_DEBUG: true
  ACTIONS_RUNNER_DEBUG: true
```

Or set secret:
```bash
gh secret set ACTIONS_STEP_DEBUG --body "true"
```

---

### SSH Into Running Job

Use `tmate` action for interactive debugging:
```yaml
- name: Setup tmate
  uses: mxschmitt/action-tmate@v3
  if: failure()
  timeout-minutes: 30
```

This gives you an SSH URL to connect to the runner and debug live.

---

### View Step Outputs

```yaml
- name: Build
  id: build
  run: |
    echo "image_tag=sha-abc123" >> $GITHUB_OUTPUT

- name: Debug
  run: |
    echo "Image tag: ${{ steps.build.outputs.image_tag }}"
```

---

### Check GitHub Actions Logs

```bash
# List recent runs
gh run list --limit 10

# View specific run
gh run view <run-id>

# View specific job logs
gh run view <run-id> --job=deploy

# Download logs
gh run download <run-id>
```

---

### Test Workflows Locally

Use `act` tool:
```bash
# Install act
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | bash

# Run workflow locally
act push -j deploy --secret-file .env

# Run specific workflow
act -W .github/workflows/ci.yml
```

**Note:** `act` doesn't support OIDC authentication (use stored keys instead).

---

## Quick Diagnostic Checklist

When a workflow fails, check in order:

1. **GitHub Actions logs** — Which step failed?
2. **Error message** — What exactly went wrong?
3. **Secrets** — Are they set correctly?
4. **Permissions** — Does role have required permissions?
5. **Infrastructure** — Is EC2/MLflow/RDS running?
6. **Network** — Can runner reach EC2? Can EC2 reach AWS services?
7. **Resources** — Disk space, memory, ports available?
8. **State** — Terraform locked? Docker containers running?

---

## Emergency Procedures

### Manual Rollback (if auto-rollback fails)

```bash
# SSH to EC2
ssh -i ~/.ssh/id_ed25519 ubuntu@32.196.26.238

# Stop failed container
sudo docker stop fastapi
sudo docker rm fastapi

# List available images
sudo docker images | grep heart-disease

# Run previous known-good image
sudo docker run -d \
  --name fastapi \
  --restart always \
  -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://10.0.0.186:5000 \
  -e MODEL_NAME=best_model_2025-07-30 \
  -e AWS_REGION=us-east-1 \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:sha-<previous>

# Verify
curl http://localhost:8000/health
```

### Emergency Deploy (skip CI/CD)

```bash
# Build locally
docker build -t heart-disease-api:latest .

# Tag and push manually
docker tag heart-disease-api:latest \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:emergency-$(date +%s)

aws ecr get-login-password | docker login --username AWS --password-stdin 695074562426.dkr.ecr.us-east-1.amazonaws.com
docker push 695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:emergency-$(date +%s)

# Deploy manually
ssh ubuntu@32.196.26.238 "sudo docker pull <image> && sudo docker stop fastapi && sudo docker run -d ... <image>"
```

### Disable Auto-Deploy

To stop CD from deploying on push:

1. Temporarily modify workflow:
```yaml
# Add this condition to all jobs
if: false  # DISABLED for emergency
```

2. Or delete the workflow file:
```bash
git rm .github/workflows/cd.yml
git commit -m "EMERGENCY: Disable auto-deploy"
git push
```

---

## Key Takeaways

1. **Logs are your friend** — GitHub Actions logs + EC2 logs tell the story
2. **Test locally first** — If it fails in CI, try the same commands locally
3. **Verify assumptions** — Is EC2 running? Is MLflow up? Are secrets correct?
4. **Use tmate for debugging** — Interactive access to the runner
5. **Have a manual backup plan** — Know how to deploy/rollback manually if CI/CD fails
6. **Document fixes** — Update this troubleshooting guide when you find solutions

---

## Next Steps

- ✅ Test rollback system
- ✅ Set up monitoring for CI/CD (track failure rates)
- ✅ Move to Phase 8: Real Testing
