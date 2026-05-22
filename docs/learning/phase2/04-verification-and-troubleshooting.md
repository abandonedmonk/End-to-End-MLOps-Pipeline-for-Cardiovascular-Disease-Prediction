# 04 — Verification & End-to-End Testing

Complete testing checklist and troubleshooting guide for Phase 2 deployment.

## Acceptance Criteria Checklist

Before considering Phase 2 complete, verify all of the following:

- [ ] MLflow UI loads at `http://<EC2-IP>:5000`
- [ ] New experiments create tables in RDS PostgreSQL
- [ ] Artifacts (models, plots, datasets) are stored in S3
- [ ] MLflow service restarts automatically on EC2 reboot
- [ ] Security group restricts access to your IP only
- [ ] No AWS credentials stored on EC2 (uses IAM role)

## Test 1: MLflow UI Accessibility

**From your laptop:**

```bash
# Simple HTTP check
curl -I http://$EC2_PUBLIC_IP:5000
# Expected: HTTP/1.1 200 OK

# Open in browser
open "http://$EC2_PUBLIC_IP:5000"
# You should see MLflow UI with "Default" experiment listed
```

**If fails:**
- Verify EC2 is running: `aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name'`
- Verify MLflow service is active: `ssh -i key.pem ubuntu@$EC2_PUBLIC_IP "sudo systemctl status mlflow"`
- Check security group rule for port 5000: `aws ec2 describe-security-groups --group-ids $SG_ID | grep -A5 IpPermissions`
- Review MLflow logs on EC2: `sudo journalctl -u mlflow -n 100`

---

## Test 2: Logging an Experiment

**From your laptop**, run a simple MLflow tracking script:

```bash
# Ensure env vars are set
source ~/.mlflow-aws-config
echo "MLFLOW_TRACKING_URI: $MLFLOW_TRACKING_URI"

python3 <<'PYEOF'
import mlflow
import os
import tempfile

# Verify env vars
print(f"Tracking URI: {os.environ.get('MLFLOW_TRACKING_URI', 'NOT SET')}")
print(f"Artifact root: {os.environ.get('MLFLOW_ARTIFACT_ROOT', 'NOT SET')}")

# Set client explicitly
mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])

# Start an experiment
with mlflow.start_run(run_name="test-phase2"):
    mlflow.log_param("test_param", 123)
    mlflow.log_metric("test_metric", 0.95)
    
    # Create and log a file artifact
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test artifact from Phase 2 verification")
        temp_file = f.name
    
    mlflow.log_artifact(temp_file, "test_artifacts")
    os.remove(temp_file)

print("✓ Experiment logged successfully")
PYEOF
```

**Expected output:**
```
Tracking URI: http://<EC2-IP>:5000
Artifact root: s3://...
✓ Experiment logged successfully
```

**If fails:**
- Check network connectivity to EC2: `ping $EC2_PUBLIC_IP`
- Verify MLflow backend connection from EC2: `ssh -i key.pem ubuntu@$EC2_PUBLIC_IP "curl http://localhost:5000"`
- Check Python dependencies: `pip list | grep mlflow`

---

## Test 3: Verify RDS Backend Store

**Check that metrics are in RDS (not just local files):**

```bash
# Connect to RDS from your laptop
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" <<'SQLEOF'
-- List MLflow tables
\dt

-- Count runs in metric table
SELECT COUNT(*) as run_count FROM runs;

-- View recent experiments
SELECT experiment_id, name FROM experiments LIMIT 5;

-- View recent runs
SELECT run_uuid, experiment_id, status FROM runs ORDER BY start_time DESC LIMIT 5;
SQLEOF
```

**Expected output:**
```
        List of relations
 Name | Type |  Owner
------+------+--------
 alembic_version | table | mlflow_user
 experiments | table | mlflow_user
 runs | table | mlflow_user
 metrics | table | mlflow_user
 params | table | mlflow_user
 ...

run_count
-----------
          1
(1 row)
```

**If connection fails:**
- Verify RDS is available: `aws rds describe-db-instances --db-instance-identifier $DB_IDENTIFIER --query 'DBInstances[0].DBInstanceStatus'`
- Check RDS security group allows port 5432 from your IP
- Verify credentials in `~/.mlflow-aws-config`

---

## Test 4: Verify S3 Artifacts

**Check that artifacts are uploaded to S3 (not stored locally):**

```bash
# List S3 artifacts
aws s3 ls s3://$S3_BUCKET/artifacts/ --recursive

# Expected output (after test-phase2 experiment):
# 2024-05-22 10:15:30 0 artifacts/.../<run-id>/artifacts/test_artifacts/test-file.txt
# 2024-05-22 10:15:30 100 artifacts/.../artifacts/test_artifacts/test-file.txt
```

**If bucket is empty:**
- Verify MLflow logged artifacts (check UI at `http://$EC2_PUBLIC_IP:5000/`)
- Verify EC2 has S3 permissions: `ssh -i key.pem ubuntu@$EC2_PUBLIC_IP "aws s3 ls s3://$S3_BUCKET/"`
- Check MLflow logs for S3 errors: `sudo journalctl -u mlflow | grep -i s3`

---

## Test 5: MLflow UI Experiment Visibility

**Open `http://<EC2-IP>:5000` in browser:**

1. Click "Default" experiment (or find your experiment from Test 2)
2. You should see "test-phase2" run with:
   - Parameters: `test_param = 123`
   - Metrics: `test_metric = 0.95`
   - Artifacts: folder with test_artifacts/test-file.txt
3. Click the artifact to verify it's retrievable from S3

**If experiment not visible:**
- Verify MLflow is using RDS backend: `ssh -i key.pem ubuntu@$EC2_PUBLIC_IP "env | grep MLFLOW_BACKEND_STORE_URI"`
- Check mlflow.service file: `sudo cat /etc/systemd/system/mlflow.service | grep backend-store`
- Restart MLflow: `sudo systemctl restart mlflow`

---

## Test 6: Service Auto-Restart on EC2 Reboot

**Reboot EC2 and verify MLflow comes back:**

```bash
# SSH into EC2
ssh -i key.pem ubuntu@$EC2_PUBLIC_IP

# Reboot
sudo reboot

# Wait 2 minutes for EC2 to come back up
sleep 120

# SSH back in
ssh -i key.pem ubuntu@$EC2_PUBLIC_IP

# Check MLflow status
sudo systemctl status mlflow
# Should show: active (running)

# Test the UI
curl -I http://localhost:5000
# Should return: HTTP/1.1 200 OK
```

**If MLflow doesn't restart:**
- Check service is enabled: `sudo systemctl is-enabled mlflow` (should print "enabled")
- Review logs after reboot: `sudo journalctl -u mlflow --since "5 minutes ago"`
- Manually start: `sudo systemctl start mlflow`

---

## Test 7: Security Group Access Control

**Verify only your IP can access MLflow (port 5000):**

```bash
# From your laptop (inside your network)
curl -I http://$EC2_PUBLIC_IP:5000
# Should return: HTTP/1.1 200 OK

# Check security group rules
aws ec2 describe-security-groups --group-ids $SG_ID --query 'SecurityGroups[0].IpPermissions[]' --output table

# Expected output should show:
# Port 5000 (MLflow) from $MY_IP/32 only
# Port 22 (SSH) from $MY_IP/32 only
```

**If security group is too open:**
- Remove overly permissive rules: 
  ```bash
  aws ec2 revoke-security-group-ingress --group-id $SG_ID --protocol tcp --port 5000 --cidr 0.0.0.0/0
  ```
- Re-add with your IP only:
  ```bash
  aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 5000 --cidr $MY_IP
  ```

---

## Test 8: No Embedded AWS Credentials on EC2

**Verify EC2 uses IAM role (not credentials file):**

```bash
# SSH into EC2
ssh -i key.pem ubuntu@$EC2_PUBLIC_IP

# Check for AWS credentials files (should be empty or not exist)
cat ~/.aws/credentials
# Should print: No such file or directory (or be empty)

# Verify IAM role is attached
curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
# Should return the IAM role name (e.g., EC2S3AccessRole)

# Verify S3 access via role
aws s3 ls s3://$S3_BUCKET/
# Should work without explicit credentials
```

**If credentials are embedded:**
- Remove them: `rm -f ~/.aws/credentials`
- Verify IAM role is attached to instance: AWS console > EC2 > Instance details > IAM role

---

## Common Issues & Fixes

### Issue: "Connection refused" when accessing MLflow UI

**Diagnosis:**
```bash
ssh -i key.pem ubuntu@$EC2_PUBLIC_IP
curl -v http://localhost:5000
# Check if connection is refused
```

**Fix:**
- Verify MLflow service is running: `sudo systemctl status mlflow`
- Restart if needed: `sudo systemctl restart mlflow`
- Check port isn't in use: `sudo lsof -i :5000`

### Issue: "Authentication failed for RDS"

**Diagnosis:**
```bash
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;"
# Check if you can connect manually
```

**Fix:**
- Verify credentials in `mlflow-env.sh` on EC2: `cat /home/ubuntu/mlflow-env.sh | grep postgresql`
- Test credentials: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1;"`
- Reset password if needed: AWS console > RDS > Modify

### Issue: "Access Denied" when uploading to S3

**Diagnosis:**
```bash
# SSH into EC2
ssh -i key.pem ubuntu@$EC2_PUBLIC_IP
aws s3 ls s3://$S3_BUCKET/
# Check if you get "Access Denied"
```

**Fix:**
- Verify IAM role is attached: AWS console > EC2 > Instance > IAM role
- Verify policy allows S3: `aws iam get-role-policy --role-name EC2S3AccessRole --policy-name AmazonS3FullAccess`
- Detach and reattach role if needed (requires EC2 restart)

---

## Final Verification Summary

Run this checklist script on your laptop:

```bash
#!/bin/bash
set -e

echo "=== Phase 2 Verification ==="

# Test 1: UI
echo "1. Testing MLflow UI..."
curl -s -o /dev/null -w "%{http_code}" http://$EC2_PUBLIC_IP:5000 | grep -q 200 && echo "   ✓ UI accessible" || echo "   ✗ UI not accessible"

# Test 2: RDS
echo "2. Testing RDS connection..."
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT COUNT(*) FROM experiments;" 2>/dev/null && echo "   ✓ RDS accessible" || echo "   ✗ RDS not accessible"

# Test 3: S3
echo "3. Testing S3 access..."
aws s3 ls s3://$S3_BUCKET/ 2>/dev/null && echo "   ✓ S3 accessible" || echo "   ✗ S3 not accessible"

# Test 4: Security group
echo "4. Checking security group rules..."
aws ec2 describe-security-groups --group-ids $SG_ID | grep -q "5000" && echo "   ✓ Port 5000 configured" || echo "   ✗ Port 5000 not configured"

echo "=== All checks complete ==="
```

---

**Phase 2 Complete!**

Once all tests pass, you're ready for Phase 3 (Pipeline Migration).
