# 07 — Debugging Playbook

Practical guide for when things break on your AWS MLOps stack.

---

## Quick Reference: SSH Into EC2

```bash
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 "command"
```

Always use `-T` to disable pseudo-terminal allocation (avoids the `QSocketNotifier` warning).

---

## Problem: Can't SSH Into EC2

### Symptom
```
ssh: connect to host 32.196.26.238 port 22: Connection refused
ssh: connect to host 32.196.26.238 port 22: Connection timed out
```

### Debug Steps

```bash
# 1. Is the instance running?
aws ec2 describe-instances --instance-ids i-0bda8692493c15a77 \
  --query 'Reservations[0].Instances[0].State.Name'

# 2. Is your IP in the security group?
aws ec2 describe-security-groups --group-ids sg-00b5c4fac1f30ede2 \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`22`].IpRanges[*].CidrIp'

# 3. Has your IP changed?
curl https://checkip.amazonaws.com
# Compare with the IP in your security group
```

### Fixes

| Cause | Fix |
|-------|-----|
| Instance stopped | `aws ec2 start-instances --instance-ids i-xxx` |
| Your IP changed | Update `your_ip` in tfvars, `terraform apply` |
| Wrong key file | Verify `~/.ssh/id_ed25519` matches the key pair |
| Instance just launched | Wait 1-2 min for user_data to enable SSH |

### Host Key Changed Warning

After recreating an EC2 instance, you'll see:
```
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

Fix:
```bash
ssh-keygen -f "$HOME/.ssh/known_hosts" -R "32.196.26.238"
```

---

## Problem: MLflow Not Accessible from Browser

### Symptom
```
curl: (7) Failed to connect to host port 5000: Connection refused
```

### Debug Steps (From Your Machine)

```bash
# Test connectivity (distinguishes SG issue vs service issue)
nc -zv 32.196.26.238 5000
# "Connection refused" = security group allows it, service not running
# "Connection timed out" = security group blocks it
# "Connected" = both work
```

### Debug Steps (From EC2)

```bash
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238 "
  systemctl is-active mlflow
  sudo ss -tlnp | grep 5000
  sudo journalctl -u mlflow --no-pager -n 10
"
```

### Fixes

| Cause | Fix |
|-------|-----|
| MLflow not running | `sudo systemctl start mlflow` |
| MLflow crash-looping | Check `journalctl` for Python errors |
| Listening on 127.0.0.1 only | Change `--host 0.0.0.0` in service file |
| Security group blocks your IP | Update `your_ip` in tfvars |
| Your IP changed | `curl checkip.amazonaws.com` and update |

---

## Problem: MLflow Crash-Looping

### Symptom
```bash
systemctl is-active mlflow
# "activating" (restarting after failure)
```

### Debug

```bash
# Get the actual error
sudo journalctl -u mlflow --no-pager -n 30
```

### Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'pkg_resources'` | `setuptools >= 71` removed `pkg_resources` | `/opt/uv/uv pip install --python /opt/mlflow-venv/bin/python 'setuptools<71' && sudo systemctl restart mlflow` |
| `ModuleNotFoundError: No module named 'X'` | Missing Python package | Install with uv: `/opt/uv/uv pip install --python /opt/mlflow-venv/bin/python X` |
| `could not connect to server: Connection refused` (PostgreSQL) | RDS not reachable | Check RDS SG, check RDS is running |
| `FATAL: password authentication failed` | Wrong password in connection string | Check the systemd service file: `cat /etc/systemd/system/mlflow.service` |
| `Access Denied` (S3) | IAM instance profile missing or wrong | Check: `aws sts get-caller-identity` |
| `Address already in use` | Port 5000 occupied by another process | `sudo lsof -i :5000` then kill or change port |

---

## Problem: RDS Not Reachable

### Symptom
MLflow log shows `could not connect to server: Connection refused`

### Debug

```bash
# From EC2 — test connectivity
/opt/mlflow-venv/bin/python -c "
import psycopg2, sys
try:
    conn = psycopg2.connect(
        host='heart-disease-mlops-db.ckryi8i2m30f.us-east-1.rds.amazonaws.com',
        port=5432, dbname='mlflow',
        user='mlflowadmin', password='YOUR_PASSWORD',
        connect_timeout=5
    )
    print('Connected!')
    conn.close()
except Exception as e:
    print(f'Failed: {e}')
    sys.exit(1)
"

# Check RDS status
aws rds describe-db-instances \
  --db-instance-identifier heart-disease-mlops-db \
  --query 'DBInstances[0].DBInstanceStatus'
```

### Common Causes

| Cause | Fix |
|-------|-----|
| RDS stopped (auto-stop after 7 days idle) | `aws rds start-db-instance --db-instance-identifier heart-disease-mlops-db` |
| RDS still creating | Wait — RDS creation takes 5-7 minutes |
| Security group wrong | Check RDS SG allows port 5432 from EC2 SG |
| Wrong endpoint | Check output of `terraform output rds_endpoint` |
| Password has special chars | RDS rejects `@`, `/`, `"`, spaces in passwords |

### The RDS Auto-Stop Gotcha

RDS on free tier auto-stops after 7 consecutive days with **zero connections**. When MLflow tries to connect:
1. RDS detects the connection attempt
2. RDS starts up (takes 30-60 seconds)
3. MLflow's connection times out before RDS is ready
4. MLflow crashes, systemd restarts it after 10 seconds
5. Second attempt usually succeeds

The systemd `Restart=on-failure` handles this automatically, but the first MLflow start after a long idle period will take 1-2 minutes.

---

## Problem: S3 Access Denied

### Symptom
MLflow can't write artifacts, or `aws s3 ls` returns Access Denied

### Debug

```bash
# From EC2 — check who you are
aws sts get-caller-identity
# Should show: "assumed-role/heart-disease-mlops-ec2-role/..."
# If it shows "user/firstuser" → using CLI creds, not instance profile

# Test S3 access
aws s3 ls s3://heart-disease-mlops-695074562426/

# Simulate specific permissions
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::695074562426:role/heart-disease-mlops-ec2-role \
  --action-names s3:PutObject \
  --resource-arns arn:aws:s3:::heart-disease-mlops-695074562426/artifacts/test
```

### Fixes

| Cause | Fix |
|-------|-----|
| No instance profile | Check `iam_instance_profile` in Terraform EC2 config |
| Wrong policy ARN scope | Ensure policy includes both bucket and `bucket/*` |
| AWS CLI using wrong credentials | Unset `AWS_ACCESS_KEY_ID`, rely on instance profile |
| Bucket doesn't exist | `aws s3 mb s3://heart-disease-mlops-695074562426` |

---

## Problem: User Data Script Failed

### Symptom
Services not running, packages not installed, but EC2 is "running"

### Debug

```bash
# Check if user data ran
cat /var/log/user-data.log

# Check cloud-init status
cloud-init status --long

# If status is "disabled" or "error":
cloud-init status --wait
```

### Common Failures

| Failure | Cause | Fix |
|---------|-------|-----|
| `Package 'awscli' has no installation candidate` | Ubuntu 24.04 removed awscli from apt | Install via pip/uv instead |
| `Permission denied` writing to venv | venv created by root, service runs as ubuntu | `sudo chown -R ubuntu:ubuntu /opt/mlflow-venv` |
| Script hangs at `pip install` | Slow network on t2.micro | Use `uv` instead (14s vs 5min) |
| RDS not reachable during bootstrap | RDS still creating | User data retries 30x with 10s sleep |

### Running User Data Manually

If you need to re-run parts of the bootstrap:

```bash
# Download and execute a fixed script
curl -o /tmp/fix.sh https://your-server/fix.sh
bash /tmp/fix.sh

# Or run commands directly
/opt/uv/uv pip install --python /opt/mlflow-venv/bin/python new-package
sudo systemctl restart mlflow
```

---

## Problem: EC2 Out of Memory (OOM)

### Symptom
Services randomly die, `dmesg` shows "Out of memory: Killed process"

### Debug

```bash
# Check current memory
free -h

# Check if OOM killer struck
dmesg | grep -i "out of memory" | tail -5

# Check swap usage
swapon --show
```

### Fixes

```bash
# Add more swap (2 GB instead of 1 GB)
sudo fallocate -l 2G /swapfile2
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2

# Reduce MLflow workers (each worker uses ~40 MB)
# Edit /etc/systemd/system/mlflow.service
# Add --gunicorn-opts "--workers 2" to ExecStart
sudo systemctl daemon-reload
sudo systemctl restart mlflow
```

---

## Problem: Terraform State Is Broken

### Symptom
`terraform plan` shows resources that should exist as "will create" (duplicate)

### Debug

```bash
# List all resources in state
terraform state list

# Show details of a specific resource
terraform state show module.ec2.aws_instance.main
```

### Fixes

```bash
# Import an existing resource into state
terraform import module.s3.aws_s3_bucket.main heart-disease-mlops-695074562426

# Remove a resource from state (without deleting it in AWS)
terraform state rm module.ec2.aws_instance.main

# Full reset (nuclear option — use with caution)
rm terraform.tfstate
terraform plan    # Will show everything as "create"
terraform apply   # Will fail for existing resources — import them first
```

---

## General Debugging Checklist

When anything is broken, check these in order:

1. **Is EC2 running?** → `aws ec2 describe-instances`
2. **Can you SSH?** → `ssh -i key ubuntu@IP`
3. **Is the service running?** → `systemctl status mlflow`
4. **What's the error?** → `journalctl -u mlflow -n 30`
5. **Is RDS reachable?** → Python psycopg2 test
6. **Is S3 writable?** → `aws s3 ls bucket`
7. **Is your IP in the SG?** → `curl checkip.amazonaws.com` + compare
8. **Is memory OK?** → `free -h`
9. **What changed?** → `git diff` on Terraform files
10. **Check Terraform state** → `terraform plan` to see drift
