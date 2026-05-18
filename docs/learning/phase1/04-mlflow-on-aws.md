# 04 — MLflow on AWS (Self-Hosted)

## What We Did

Deployed a self-hosted MLflow tracking server on EC2, backed by:
- **RDS PostgreSQL** for the backend store (experiment metadata, metrics, parameters)
- **S3** for the artifact store (model files, plots, serialized objects)
- **systemd** for process management (auto-restart on failure, start on boot)

Result: `http://32.196.26.238:5000` — a fully functional MLflow UI.

## Why Self-Hosted (Not SageMaker MLflow)

| Aspect | Self-Hosted | SageMaker MLflow |
|--------|-------------|------------------|
| Cost | $0 (free tier EC2 + RDS + S3) | ~$0.10/hr = $72/month |
| Free tier? | Yes (12 months) | No |
| Control | Full (you manage everything) | AWS manages server |
| Customization | Install any plugins, custom auth | Limited to AWS options |
| Learning value | High (you understand every layer) | Low (black box) |
| Uptime | Your responsibility | AWS managed |
| Effort | Moderate setup, ongoing maintenance | Zero setup |

**Our choice**: Self-hosted — zero cost within free tier, more educational, and we're already running EC2 24/7 for other services.

## Theory: MLflow Architecture

### Backend Store vs Artifact Store

MLflow has two separate storage concerns:

| | Backend Store | Artifact Store |
|---|--------------|----------------|
| Stores | Metrics, parameters, tags, run metadata | Model files, plots, serialized objects |
| Query pattern | Frequent reads/writes, structured | Infrequent writes, large blobs |
| Storage type | Relational DB (PostgreSQL) | Object storage (S3) |
| Size | Small (KB per run) | Large (MB per model) |

```
                    MLflow Server
                         │
            ┌────────────┴────────────┐
            │                         │
     Backend Store              Artifact Store
   (PostgreSQL on RDS)         (S3 Bucket)
            │                         │
   experiment metadata         model.pkl, MLmodel
   metrics (accuracy=0.90)     conda.yaml, requirements.txt
   parameters (n_estimators)   evaluation plots
```

### Why Not SQLite?

SQLite works for local development but fails for production:

| | SQLite | PostgreSQL |
|---|--------|------------|
| Concurrent writes | One at a time (locks) | Multiple simultaneous |
| Remote access | File path only | Network endpoint |
| Crash recovery | Prone to corruption | ACID compliant, WAL |
| Free tier | Always free | 12 months on RDS |

### The MLflow Server Command

```bash
mlflow server \
  --backend-store-uri postgresql://mlflowadmin:PASSWORD@rds-endpoint:5432/mlflow \
  --default-artifact-root s3://heart-disease-mlops-695074562426/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
```

| Flag | Purpose |
|------|---------|
| `--backend-store-uri` | Where to store metrics/params (PostgreSQL connection string) |
| `--default-artifact-root` | Where to store model files (S3 prefix) |
| `--host 0.0.0.0` | Listen on all network interfaces (not just localhost) |
| `--port 5000` | Port number |

**Critical**: `--host 0.0.0.0` is required for external access. If you use `--host 127.0.0.1`, MLflow only accepts connections from within the EC2 instance — you can't reach the UI from your browser.

### How S3 Artifact Storage Works

When a model is logged:

```
mlflow.log_model(model, "model")
```

MLflow:
1. Serializes the model to a temporary local directory
2. Uploads all files to `s3://bucket/artifacts/<experiment_id>/<run_id>/artifacts/model/`
3. Stores the S3 path in the backend store (RDS)
4. Deletes the temporary local files

The EC2 instance needs IAM permissions to write to S3 — this comes from the instance profile we set up.

### How Model Registry Works with S3

1. `mlflow.register_model("runs:/<run_id>/model", "best_model")` — registers the model
2. The model's artifact location stays in S3 (no copy)
3. When loading: `mlflow.pyfunc.load_model("models:/best_model/champion")` — downloads from S3
4. The download uses the EC2's instance profile credentials

## The `setuptools` Problem We Hit

### Symptom

```
ModuleNotFoundError: No module named 'pkg_resources'
```

### Root Cause

MLflow 2.13.0 still imports `pkg_resources` (deprecated). Python 3.12's `venv` no longer bundles `setuptools` by default. And `setuptools >= 71` removed `pkg_resources` from the package.

### The Fix Chain

1. `python3 -m venv` on Python 3.12 → no `setuptools` installed
2. `pip install mlflow` → installs `setuptools >= 82` (latest)
3. `setuptools >= 71` → no `pkg_resources` module
4. `mlflow` crashes on import

Fix: Install `setuptools<71` before MLflow:

```bash
uv pip install 'setuptools<71' mlflow==2.13.0 ...
```

This is a known compatibility issue. MLflow 2.14+ may fix it.

### Why We Switched to `uv`

| | pip | uv |
|---|-----|-----|
| Install 149 packages | ~5 minutes | ~14 seconds |
| Dependency resolution | Can get stuck | Fast Rust-based solver |
| venv creation | `python3 -m venv` (no setuptools) | `uv venv` (leaner) |
| Global cache | No | Yes (shared across venvs) |

`uv` is 10-100x faster than pip for dependency resolution and installation. On a t2.micro with limited CPU, this matters — less time installing = less time EC2 is burning free tier hours during bootstrap.

## How to Debug

### MLflow Won't Start

```bash
# Check service status
sudo systemctl status mlflow

# Read the actual error
sudo journalctl -u mlflow --no-pager -n 30

# Common errors:
# "ModuleNotFoundError" → missing Python package (our setuptools issue)
# "could not connect to server" → RDS not reachable
# "Permission denied" → S3 access denied (check instance profile)
```

### RDS Connection Refused

```bash
# From EC2, test RDS connectivity
/opt/mlflow-venv/bin/python -c "
import psycopg2
conn = psycopg2.connect(
    host='heart-disease-mlops-db.ckryi8i2m30f.us-east-1.rds.amazonaws.com',
    port=5432, dbname='mlflow',
    user='mlflowadmin', password='YOUR_PASSWORD'
)
print('Connected!')
conn.close()
"
```

If this fails:
1. Check security group — RDS SG must allow port 5432 from EC2 SG
2. Check RDS is running — `aws rds describe-db-instances`
3. Check you're connecting from EC2 (not your local machine) — RDS is private

### S3 Access Denied

```bash
# From EC2
aws s3 ls s3://heart-disease-mlops-695074562426/
# If "Access Denied" → IAM instance profile missing or policy wrong
```

### MLflow UI Not Accessible from Browser

1. Check `--host 0.0.0.0` in the ExecStart command
2. Check security group allows port 5000 from your IP
3. Check MLflow is actually running: `curl http://localhost:5000/` from EC2

## Practical Tips

### Quick Experiment Test

```python
import mlflow
mlflow.set_tracking_uri("http://32.196.26.238:5000")
with mlflow.start_run():
    mlflow.log_param("test", 1)
    mlflow.log_metric("accuracy", 0.95)
print("MLflow + RDS + S3 working!")
```

### Restarting MLflow After Config Changes

```bash
sudo systemctl restart mlflow
# Wait 5 seconds
systemctl is-active mlflow  # Should show "active"
```

### RDS Auto-Stop Warning

RDS on free tier **auto-stops after 7 days of no connections**. When MLflow tries to connect after this, it will fail initially. RDS auto-restarts on the next connection attempt, but this takes 30-60 seconds.

Workaround: Set up a cron job that pings RDS periodically:
```bash
# On EC2 — add to crontab
crontab -e
# Add: 0 */6 * * * /opt/mlflow-venv/bin/python -c "import psycopg2; psycopg2.connect('postgresql://mlflow:pass@host/mlflow')" 2>/dev/null
```

### Checking Artifact Storage

```bash
# Verify artifacts are in S3
aws s3 ls s3://heart-disease-mlops-695074562426/artifacts/ --recursive
# Should show model files after a training run
```
