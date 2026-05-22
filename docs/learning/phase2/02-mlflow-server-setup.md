# 02 — MLflow Server Setup on EC2

Install and configure MLflow server on your EC2 instance with S3 artifact store and RDS backend.

## Prerequisites

- EC2 instance running and accessible via SSH
- RDS instance created and available (from Step 6 of phase 1)
- S3 bucket created (from Step 2)
- Configuration file from previous phase: `source ~/.mlflow-aws-config`

## Step 1: SSH into EC2

```bash
source ~/.mlflow-aws-config
ssh -i "${EC2_KEY_NAME}.pem" ubuntu@"${EC2_PUBLIC_IP}"
```

You should now have a shell prompt on the EC2 instance.

## Step 2: Update System and Install Python

```bash
# On EC2
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git build-essential libpq-dev
python3 --version
```

## Step 3: Create Virtual Environment

```bash
# On EC2
cd /home/ubuntu
python3 -m venv mlflow-venv
source mlflow-venv/bin/activate
pip install --upgrade pip setuptools wheel
```

## Step 4: Install MLflow and Dependencies

```bash
# On EC2 (venv activated)
pip install mlflow==2.10.0 boto3==1.34.0 psycopg2-binary==2.9.9 gunicorn==21.2.0
pip list | grep -E 'mlflow|boto3|psycopg2|gunicorn'
```

Verify output shows all four packages installed.

## Step 5: Create PostgreSQL Database for MLflow

By default, RDS creates a database, but we verify connectivity and create tables.

```bash
# On your laptop (with RDS host saved)
# Test connection from laptop (replace with EC2-IP and credentials from config)
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT version();"
# Enter password when prompted: $DB_PASSWORD
```

If connection succeeds, RDS is ready. If it fails, verify:
- RDS is "available" in AWS console
- Your IP is allowed in RDS security group (check if RDS uses the same security group as EC2)
- Database `mlflow` exists

## Step 6: Set Up MLflow Server Environment

On EC2, create an environment file for the MLflow systemd service:

```bash
# On EC2
cat > /home/ubuntu/mlflow-env.sh <<'EOF'
#!/bin/bash
export MLFLOW_TRACKING_URI="http://0.0.0.0:5000"
export MLFLOW_BACKEND_STORE_URI="postgresql://mlflow_user:MySecurePass123!@DB_HOST:5432/mlflow"
export MLFLOW_DEFAULT_ARTIFACT_ROOT="s3://S3_BUCKET/artifacts/"
export AWS_DEFAULT_REGION="us-east-1"
EOF
```

**Replace placeholders:**
```bash
# On EC2
sed -i "s/DB_HOST/$DB_HOST/g" /home/ubuntu/mlflow-env.sh
sed -i "s/S3_BUCKET/$S3_BUCKET/g" /home/ubuntu/mlflow-env.sh
sed -i "s/MySecurePass123!/$DB_PASSWORD/g" /home/ubuntu/mlflow-env.sh
sed -i "s/us-east-1/$AWS_REGION/g" /home/ubuntu/mlflow-env.sh

chmod +x /home/ubuntu/mlflow-env.sh
cat /home/ubuntu/mlflow-env.sh
```

## Step 7: Test MLflow Server (Manual Start)

```bash
# On EC2
source /home/ubuntu/mlflow-env.sh
mlflow server \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --default-artifact-root "$MLFLOW_DEFAULT_ARTIFACT_ROOT" \
  --host 0.0.0.0 \
  --port 5000
```

Expected output:
```
[YYYY-MM-DD HH:MM:SS +0000] [PID] [INFO] Starting gunicorn X.X.X
[YYYY-MM-DD HH:MM:SS +0000] [PID] [INFO] Listening at: http://0.0.0.0:5000
```

**Test from your laptop (in another terminal):**
```bash
curl -I http://$EC2_PUBLIC_IP:5000
# Should return: HTTP/1.1 200 OK
```

**Stop the manual server (on EC2):**
```bash
# Press Ctrl+C
```

## Step 8: Create Systemd Service

On EC2, create the service file:

```bash
# On EC2
sudo tee /etc/systemd/system/mlflow.service > /dev/null <<'EOF'
[Unit]
Description=MLflow Tracking Server
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/home/ubuntu
EnvironmentFile=/home/ubuntu/mlflow-env.sh
ExecStart=/home/ubuntu/mlflow-venv/bin/mlflow server \
  --backend-store-uri postgresql://mlflow_user:MySecurePass123!@DB_HOST:5432/mlflow \
  --default-artifact-root s3://S3_BUCKET/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

**Replace placeholders in the service file:**
```bash
# On EC2
sudo sed -i "s/DB_HOST/$DB_HOST/g" /etc/systemd/system/mlflow.service
sudo sed -i "s/S3_BUCKET/$S3_BUCKET/g" /etc/systemd/system/mlflow.service
sudo sed -i "s/MySecurePass123!/$DB_PASSWORD/g" /etc/systemd/system/mlflow.service

# Verify replacements
sudo cat /etc/systemd/system/mlflow.service | grep -E 'ExecStart|postgresql|s3://'
```

## Step 9: Enable and Start MLflow Service

```bash
# On EC2
sudo systemctl daemon-reload
sudo systemctl enable mlflow
sudo systemctl start mlflow

# Check status
sudo systemctl status mlflow

# View logs (last 50 lines)
sudo journalctl -u mlflow -n 50 --no-pager
```

Expected final status: `active (running)` with a green dot.

## Step 10: Verify MLflow UI

**From your laptop:**
```bash
open "http://$EC2_PUBLIC_IP:5000"
# or
curl -s http://$EC2_PUBLIC_IP:5000 | head -20
```

You should see the MLflow UI in browser or HTML response.

## Step 11: Configure Local Environment Variables

On your laptop, set environment variables to point to the MLflow server:

```bash
# On your laptop
cat >> ~/.bashrc <<EOF

# MLflow AWS Configuration
export MLFLOW_TRACKING_URI="http://$EC2_PUBLIC_IP:5000"
export MLFLOW_ARTIFACT_ROOT="s3://$S3_BUCKET/artifacts/"
export MLFLOW_S3_ENDPOINT_URL=""  # Leave empty for standard AWS S3
EOF

source ~/.bashrc
```

**Verify:**
```bash
echo $MLFLOW_TRACKING_URI
# Should print: http://<EC2-IP>:5000
```

## Step 12: Test MLflow Tracking (End-to-End)

From your laptop, log an experiment:

```bash
python3 <<'PYEOF'
import mlflow
import random

with mlflow.start_run(run_name="test-run"):
    mlflow.log_param("test_param", 42)
    mlflow.log_metric("test_metric", random.random())
    mlflow.log_artifact("/etc/hostname", "system")

print("✓ Experiment logged successfully")
PYEOF
```

**Verify in MLflow UI:**
1. Open `http://<EC2-IP>:5000`
2. Click "Default" experiment
3. You should see "test-run" with param and metric
4. Check S3 bucket: `aws s3 ls s3://$S3_BUCKET/artifacts/` — you should see artifact folder

## Troubleshooting

**MLflow service fails to start:**
```bash
# On EC2
sudo journalctl -u mlflow -n 100 --no-pager
```
Common issues:
- PostgreSQL connection string typo → check `sudo cat /etc/systemd/system/mlflow.service`
- Database doesn't exist → verify `psql` connection manually from EC2
- S3 bucket name wrong → verify `aws s3 ls s3://$S3_BUCKET/`
- IAM role not attached → verify EC2 instance profile in AWS console

**Cannot access MLflow UI from laptop:**
- Verify security group allows port 5000 from your IP: `aws ec2 describe-security-groups --group-ids $SG_ID`
- Verify EC2 and MLflow process are running: `sudo systemctl status mlflow`
- Verify firewall on EC2 allows outbound traffic: `sudo iptables -L` (should show no DROP rules)

**S3 artifacts not uploading:**
- Verify EC2 has S3 permissions: `aws s3 ls s3://$S3_BUCKET/` (from EC2)
- If permissions denied, check IAM role is attached to instance: AWS console > EC2 > Instance details > IAM role

**Database connection timeout:**
- RDS may require a DB subnet group for private networking. For testing, use public RDS (less secure but simpler).
- Verify RDS security group allows port 5432 from EC2's security group

---

**Next:** Proceed to [03-systemd-service.md](03-systemd-service.md) for service hardening (optional, for production).
