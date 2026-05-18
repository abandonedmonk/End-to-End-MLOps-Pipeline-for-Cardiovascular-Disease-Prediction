# Transition Guide — Local to AWS

Step-by-step guide for migrating each component from local infrastructure to AWS Free Tier.

---

## Prerequisites

Before starting, ensure you have:

- [ ] AWS account with free tier active (1st year)
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Terraform >= 1.5 installed
- [ ] Docker installed locally
- [ ] GitHub repository admin access
- [ ] Prefect Cloud account and API key
- [ ] Your public IP address (for security group rules)

```bash
# Verify tools
aws --version
terraform version
docker --version

# Get your public IP
curl -s https://checkip.amazonaws.com
```

---

## Step 1: Create the S3 State Backend (Manual)

Terraform needs an S3 bucket to store state before we can automate everything.

```bash
# Create S3 bucket for Terraform state
aws s3api create-bucket \
  --bucket heart-disease-tfstate-<your_account_id> \
  --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket heart-disease-tfstate-<your_account_id> \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name heart-disease-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

---

## Step 2: Deploy Infrastructure with Terraform

### 2.1 Create Terraform Configuration

The `infra/` directory will contain:

```
infra/
├── main.tf                 # Root module, wires everything together
├── variables.tf            # Input variables
├── outputs.tf              # Exported values (EC2 IP, RDS endpoint, etc.)
├── providers.tf            # AWS provider config
├── backend.tf              # S3 state backend
├── user_data.sh            # EC2 bootstrap script
└── modules/
    ├── ec2/                # EC2 instance + security group
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── rds/                # PostgreSQL for MLflow
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── s3/                 # Artifact + data bucket
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── ecr/                # Container registry
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── iam/                # OIDC + instance roles
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

### 2.2 Initialize and Apply

```bash
cd infra/

# Initialize with remote backend
terraform init \
  -backend-config="bucket=heart-disease-tfstate-<your_account_id>" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=heart-disease-tfstate-lock"

# Review the plan
terraform plan -out=tfplan

# Apply (creates all resources)
terraform apply tfplan
```

### 2.3 Note the Outputs

After apply, record these values:

```bash
terraform output ec2_public_ip
terraform output rds_endpoint
terraform output s3_bucket_name
terraform output ecr_repository_url
```

---

## Step 3: Upload Data to S3

Transfer your local data to S3 so the pipeline can access it from EC2.

```bash
# Upload raw data
aws s3 cp data/raw/processed.cleveland.data \
  s3://heart-disease-mlops/data/raw/processed.cleveland.data

# Upload processed data
aws s3 cp data/processed/processed_cleveland_data.csv \
  s3://heart-disease-mlops/data/processed/processed_cleveland_data.csv

# Upload reference data for Evidently monitoring
aws s3 cp data/processed/processed_cleveland_data.csv \
  s3://heart-disease-mlops/data/reference/reference_data.csv
```

---

## Step 4: Set Up MLflow on EC2

SSH into your EC2 instance and configure MLflow.

```bash
# SSH into EC2
ssh -i ~/.ssh/<your-key>.pem ubuntu@<ec2_public_ip>

# MLflow should already be installed via user_data.sh
# Verify
mlflow --version

# The MLflow systemd service should be running
sudo systemctl status mlflow

# If not running, start it
sudo systemctl start mlflow

# Check MLflow UI
curl http://localhost:5000/health
```

### MLflow Systemd Service

The `user_data.sh` bootstrap script creates this service:

```ini
# /etc/systemd/system/mlflow.service
[Unit]
Description=MLflow Tracking Server
After=network.target

[Service]
Type=simple
User=ubuntu
Environment=MLFLOW_TRACKING_URI=http://localhost:5000
ExecStart=/usr/local/bin/mlflow server \
  --backend-store-uri postgresql://mlflow:<password>@<rds-endpoint>:5432/mlflow \
  --default-artifact-root s3://heart-disease-mlops/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Verify MLflow

From your local machine:

```bash
# Set MLflow tracking URI
export MLFLOW_TRACKING_URI=http://<ec2_public_ip>:5000

# Test creating an experiment
python -c "
import mlflow
mlflow.set_tracking_uri('http://<ec2_public_ip>:5000')
experiment_id = mlflow.create_experiment('test-experiment')
print(f'Experiment created: {experiment_id}')
mlflow.delete_experiment(experiment_id)
print('Test passed!')
"
```

---

## Step 5: Migrate Pipeline Code

### 5.1 Environment Variables Strategy

Instead of hardcoded paths, all config comes from environment variables with local fallbacks:

```python
import os

MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "sqlite:///mlruns/mlflow.db"  # local fallback
)

ARTIFACT_ROOT = os.getenv(
    "MLFLOW_ARTIFACT_ROOT",
    "file://mlruns/"  # local fallback
)

DATA_PATH = os.getenv(
    "DATA_PATH",
    "../data/raw/processed.cleveland.data"  # local fallback
)
```

### 5.2 Changes Per File

#### `data.py`

```python
# BEFORE
@task
def get_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, header=None)
    ...

# AFTER
@task
def get_data(path: str = None) -> pd.DataFrame:
    if path is None:
        path = os.getenv("DATA_PATH", "../data/raw/processed.cleveland.data")
    
    if path.startswith("s3://"):
        # Download from S3 to temp file
        s3 = boto3.client("s3")
        bucket = path.replace("s3://", "").split("/")[0]
        key = "/".join(path.replace("s3://", "").split("/")[1:])
        local_path = "/tmp/processed.cleveland.data"
        s3.download_file(bucket, key, local_path)
        df = pd.read_csv(local_path, header=None)
    else:
        df = pd.read_csv(path, header=None)
    ...
```

#### `train.py`

```python
# BEFORE
paths = {
    "mlflow_db_path": f"sqlite:///{project_root}/mlruns/mlflow.db",
    "artifact_loc": f"file://{project_root}/mlruns/",
    "experiment_name": "heart-disease-experiment-pipeline",
    "final_save_dir": f"{project_root}/models/"
}
experiment_id = get_or_create_experiment_id(name=paths["experiment_name"], project_root=project_root)
mlflow.set_tracking_uri(paths["mlflow_db_path"])

# AFTER
tracking_uri = os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{project_root}/mlruns/mlflow.db")
artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT", f"file://{project_root}/mlruns/")
experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline")

mlflow.set_tracking_uri(tracking_uri)
mlflow.set_experiment(experiment_name=experiment_name)

# Remove get_or_create_experiment_id() — MLflow handles this automatically
# Remove paths dict — use env vars directly
```

#### `register.py`

```python
# BEFORE
mlflow.set_tracking_uri(paths["mlflow_db_path"])
mlflow.set_experiment(experiment_name=paths["experiment_name"])

# AFTER
mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db"))
mlflow.set_experiment(experiment_name=os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline"))
```

#### `load_model.py`

```python
# BEFORE
paths = {
    "model_name": "best_model_2025-07-30",  # HARDCODED DATE!
    "mlflow_db_path": f"sqlite:///{project_root}/mlruns/mlflow.db",
    ...
}

# AFTER
mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db"))
model_name = os.getenv("MLFLOW_MODEL_NAME", f"best_model_{date.today()}")
```

#### `prefect_flow.py`

```python
# BEFORE
df = get_data(path="../data/raw/processed.cleveland.data")

# AFTER
df = get_data()  # path comes from DATA_PATH env var
```

### 5.3 Remove `aws_orchestration/`

The `aws_orchestration/` directory was a separate copy of the pipeline for AWS. With env-based config, we don't need two copies. Merge any unique logic and delete:

```bash
rm -rf aws_orchestration/
```

### 5.4 Create `.env.example`

```bash
# .env.example (commit this, NOT .env)
# Copy to .env and fill in values for your environment

# MLflow
MLFLOW_TRACKING_URI=http://<EC2_IP>:5000
MLFLOW_ARTIFACT_ROOT=s3://heart-disease-mlops/artifacts/
MLFLOW_EXPERIMENT_NAME=heart-disease-experiment-pipeline
MLFLOW_MODEL_NAME=best_model

# Data
DATA_PATH=s3://heart-disease-mlops/data/raw/processed.cleveland.data

# AWS
AWS_REGION=us-east-1
S3_BUCKET=heart-disease-mlops

# For local development, use these instead:
# MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db
# MLFLOW_ARTIFACT_ROOT=file://mlruns/
# DATA_PATH=../data/raw/processed.cleveland.data
```

---

## Step 6: Build and Deploy FastAPI Docker Image

### 6.1 Update Dockerfile

```dockerfile
# Multi-stage build for smaller image
FROM python:3.12-slim AS builder
WORKDIR /build
COPY api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY api/main.py api/schema.py ./
COPY models/pipeline.pkl ./
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2 Build and Push to ECR

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <account_id>.dkr.ecr.us-east-1.amazonaws.com

# Build
docker build -t heart-disease-api .

# Tag
docker tag heart-disease-api:latest \
  <account_id>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest

# Push
docker push <account_id>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest
```

### 6.3 Run on EC2

```bash
# SSH into EC2
ssh -i ~/.ssh/<key>.pem ubuntu@<ec2_ip>

# Login to ECR from EC2
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <account_id>.dkr.ecr.us-east-1.amazonaws.com

# Pull and run
docker pull <account_id>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest

docker run -d \
  --name heart-api \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://localhost:5000 \
  <account_id>.dkr.ecr.us-east-1.amazonaws.com/heart-disease-api:latest

# Test
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"age":54,"sex":1,"cp":1,"trestbps":140,"chol":239,"fbs":0,"restecg":1,"thalach":160,"exang":0,"oldpeak":1.2,"slope":1,"ca":2,"thal":3}'
```

---

## Step 7: Set Up Prefect Agent on EC2

```bash
# SSH into EC2
ssh -i ~/.ssh/<key>.pem ubuntu@<ec2_ip>

# Prefect should already be installed via user_data.sh

# Login to Prefect Cloud
prefect cloud login -k <your_prefect_api_key>

# Start the agent
prefect agent start --work-pool heart-disease --work-queue default &

# Or set up as systemd service for persistence
sudo tee /etc/systemd/system/prefect-agent.service <<EOF
[Unit]
Description=Prefect Agent
After=network.target

[Service]
Type=simple
User=ubuntu
Environment=MLFLOW_TRACKING_URI=http://localhost:5000
Environment=MLFLOW_ARTIFACT_ROOT=s3://heart-disease-mlops/artifacts/
Environment=DATA_PATH=s3://heart-disease-mlops/data/raw/processed.cleveland.data
Environment=AWS_REGION=us-east-1
Environment=S3_BUCKET=heart-disease-mlops
ExecStart=/usr/local/bin/prefect agent start --work-pool heart-disease --work-queue default
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable prefect-agent
sudo systemctl start prefect-agent
```

---

## Step 8: Set Up Monitoring

### 8.1 CloudWatch Agent

```bash
# On EC2, install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard

# Start
sudo systemctl start amazon-cloudwatch-agent
```

### 8.2 Evidently Monitoring Script

Create `monitoring/generate_report.py`:

```python
import pandas as pd
import boto3
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, DataQualityPreset
from datetime import date
import os

s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
bucket = os.getenv("S3_BUCKET", "heart-disease-mlops")

# Download reference data
s3.download_file(bucket, "data/reference/reference_data.csv", "/tmp/reference.csv")
reference = pd.read_csv("/tmp/reference.csv")

# Download current production data (latest predictions)
# This would be populated by the API logging predictions
s3.download_file(bucket, "data/processed/processed_cleveland_data.csv", "/tmp/current.csv")
current = pd.read_csv("/tmp/current.csv")

# Generate drift report
report = Report(metrics=[DataDriftPreset(), DataQualityPreset()])
report.run(reference_data=reference, current_data=current)

# Save to S3
report_path = f"/tmp/drift_report_{date.today()}.html"
report.save_html(report_path)
s3.upload_file(report_path, bucket, f"monitoring/reports/{date.today()}/drift_report.html")
print(f"Drift report saved to s3://{bucket}/monitoring/reports/{date.today()}/drift_report.html")
```

### 8.3 Schedule with Cron

```bash
# On EC2, add weekly cron (runs Monday 01:00, after Sunday pipeline)
(crontab -l 2>/dev/null; echo "0 1 * * 1 /usr/local/bin/python /home/ubuntu/monitoring/generate_report.py") | crontab -
```

---

## Step 9: Set Up CI/CD with GitHub Actions

### 9.1 Configure OIDC Trust

This is handled by the Terraform `iam` module. The output gives you the role ARN.

```bash
terraform output github_actions_role_arn
```

Add this as a GitHub repository secret: `AWS_ROLE_ARN`

### 9.2 GitHub Secrets to Configure

| Secret | Value |
|--------|-------|
| `AWS_ROLE_ARN` | From Terraform output |
| `EC2_HOST` | EC2 public IP |
| `ECR_REGISTRY` | `<account_id>.dkr.ecr.us-east-1.amazonaws.com` |
| `PREFECT_API_KEY` | Your Prefect Cloud API key |

### 9.3 Create Workflow Files

See `.github/workflows/` — these will be created in Phase 7 of the roadmap.

---

## Step 10: Security Cleanup

### 10.1 Purge `.env` from Git History

```bash
# WARNING: This rewrites history. Coordinate with any collaborators.
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all

# Force push
git push origin --force --all
```

### 10.2 Rotate AWS Credentials

1. Go to AWS IAM → Users → Security credentials
2. Deactivate the old access key (the one in `.env`)
3. Create new access key
4. Configure locally: `aws configure` (use new key)
5. DO NOT commit the new key anywhere

### 10.3 Restrict Security Groups

In Terraform, security groups are already scoped to your IP:
- Port 22 (SSH): Your IP only
- Port 5000 (MLflow): Your IP only
- Port 8000 (API): Your IP only (or 0.0.0.0/0 if you want public access)
- Port 5432 (RDS): EC2 security group only

---

## Post-Migration Checklist

- [ ] MLflow UI accessible at `http://<EC2-IP>:5000`
- [ ] Pipeline runs end-to-end via Prefect
- [ ] Artifacts stored in S3 (verify in S3 console)
- [ ] Metrics visible in MLflow UI
- [ ] Best model registered with "champion" alias
- [ ] FastAPI responds at `http://<EC2-IP>:8000/predict`
- [ ] Prediction returns correct result
- [ ] Evidently report generated and saved to S3
- [ ] CloudWatch dashboard shows EC2 metrics
- [ ] GitHub Actions CI workflow passes
- [ ] GitHub Actions CD workflow deploys successfully
- [ ] No secrets in git history
- [ ] Old AWS access key deactivated
- [ ] AWS Budgets alert configured at $1

---

## Rollback Plan

If anything goes wrong, you can always fall back to local development:

```bash
# Set local env vars
export MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db
export DATA_PATH=../data/raw/processed.cleveland.data
export MLFLOW_ARTIFACT_ROOT=file://mlruns/

# Run locally
cd heart_disease_prediction
python prefect_flow.py

# Run API locally
uvicorn api.main:app --reload
```

The env-based config ensures local development always works as a fallback.
