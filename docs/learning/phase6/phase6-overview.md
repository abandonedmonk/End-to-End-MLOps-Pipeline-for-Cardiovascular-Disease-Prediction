# Phase 6 — Monitoring Overview

What we built, how it works, and where it fits in the MLOps architecture.

---

## Current State

**Phase 6 is COMPLETE** — Full monitoring infrastructure operational.

| Component | Status | Location |
|-----------|--------|----------|
| Evidently Drift Detection | ✅ Working | `monitoring/generate_report.py` |
| Reference Data (S3) | ✅ Created | `s3://heart-disease-mlops-695074562426/data/reference/` |
| CloudWatch Metrics | ✅ Pushing | `HeartDisease/Monitoring` namespace |
| CloudWatch Dashboard | ✅ Deployed | `heart-disease-mlops` dashboard |
| CloudWatch Alarms | ✅ Active | `high-cpu`, `high-drift` |
| SNS Topic | ✅ Ready | `heart-disease-mlops-alarms` |
| Pipeline Integration | ✅ Integrated | Final task in Prefect flow |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MONITORING SYSTEM                             │
└─────────────────────────────────────────────────────────────────────┘

                              S3
                 ┌──────────────────────────┐
                 │  data/reference/           │
                 │    reference_data.parquet  │  ◄── Training baseline
                 │                          │
                 │  monitoring/reports/     │
                 │    YYYY-MM-DD/             │  ◄── HTML drift reports
                 │      drift_report.html     │
                 │                          │
                 │  monitoring/metrics/     │
                 │    drift_scores.jsonl    │  ◄── Historical scores
                 └──────────────────────────┘
                           │
                           │ Read/Write
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Prefect Flow (EC2)                                │
│  ┌─────────────────┐    ┌──────────────┐    ┌──────────────────────┐│
│  │  Train Model    │───►│ Register     │───►│ Drift Detection      ││
│  │                 │    │ Champion     │    │ (monitoring/)        ││
│  └─────────────────┘    └──────────────┘    └──────────────────────┘│
│                                                      │              │
│              ┌─────────────────────────────────────┘              │
│              │                                                    │
│              ▼                                                    │
│  ┌───────────────────────────────────────────────────────────────┐│
│  │  Evidently Report                                            ││
│  │  ├─ Data Drift (13 features)                                 ││
│  │  ├─ Data Quality (missing values, types)                     ││
│  │  └─ HTML → S3                                                ││
│  └───────────────────────────────────────────────────────────────┘│
│                           │                                       │
│                           ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐│
│  │  CloudWatch Metrics                                          ││
│  │  ├─ DataDriftScore (0-1)                                     ││
│  │  ├─ DriftDetected (0/1)                                     ││
│  │  └─ FastAPI metrics (requests, errors)                      ││
│  └───────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
              CloudWatch Dashboard
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │  EC2 CPU    │ │ Data Drift  │ │ FastAPI     │
    │  Memory     │ │ Score       │ │ Requests    │
    └─────────────┘ └─────────────┘ └─────────────┘
                           │
           ┌───────────────┴───────────────┐
           │                               │
           ▼                               ▼
   ┌───────────────┐              ┌───────────────┐
   │  high-cpu     │              │  high-drift   │
   │  alarm        │              │  alarm        │
   └───────┬───────┘              └───────┬───────┘
           │                              │
           └──────────────┬───────────────┘
                          │
                          ▼
               SNS Topic: heart-disease-mlops-alarms
                          │
                          ▼
                   (email subscription)
```

---

## What We Built

### 1. Monitoring Package (`monitoring/`)

| File | Purpose | Key Function |
|------|---------|--------------|
| `config.py` | Central configuration | Thresholds, S3 paths, feature columns |
| `reference_data.py` | Create baseline | Saves training data to S3 |
| `generate_report.py` | Drift detection | Evidently reports + S3 upload |
| `cloudwatch_metrics.py` | Metric pushing | Custom CloudWatch metrics |

### 2. Terraform Module (`infra/modules/monitoring/`)

| Resource | Purpose |
|----------|---------|
| `aws_cloudwatch_dashboard` | Visualize all metrics |
| `aws_cloudwatch_metric_alarm` | CPU > 80%, Drift > 0.3 |
| `aws_sns_topic` | Email notifications |
| `aws_cloudwatch_log_metric_filter` | Parse FastAPI logs |

### 3. Pipeline Integration (`prefect_flow.py`)

```python
@task(name="drift_detection")
def run_drift_detection():
    # Generate drift report
    # Upload to S3
    # Push to CloudWatch
    # Create Prefect artifact
    # Alert if drift > 0.3
```

---

## How It Works

### Weekly Pipeline Run

1. **Monday 00:00 UTC** — Prefect schedules pipeline run
2. **Train** — Models trained on latest data
3. **Register** — Best model registered, champion alias set
4. **Drift Check** — Compare production data vs. reference
5. **Report** — HTML saved to S3: `s3://bucket/monitoring/reports/2025-08-04/drift_report.html`
6. **Metrics** — Drift score pushed to CloudWatch
7. **Alert** — If drift > 0.3, SNS notification sent

### Drift Detection Process

```python
# 1. Load reference (training) data
reference_df = load_from_s3("data/reference/reference_data.parquet")

# 2. Load current (production) data
current_df = load_from_s3("monitoring/current/current_data.parquet")
# Falls back to raw data if not available

# 3. Normalize categoricals (handle type mismatches)
for col in CATEGORICAL_COLUMNS:
    df[col] = df[col].astype(str)

# 4. Generate Evidently report
report = Report(metrics=[DatasetDriftMetric(), DataDriftPreset()])
report.run(reference_data=reference_df, current_data=current_df)

# 5. Extract drift score
drift_score = report.as_dict()['metrics'][0]['result']['dataset_drift']
drift_detected = drift_score > 0.3

# 6. Save and notify
report.save_html("/tmp/report.html")
upload_to_s3("/tmp/report.html", f"reports/{date}/drift_report.html")
push_to_cloudwatch(drift_score, drift_detected)
```

---

## Key Design Decisions

### Drift Threshold: 0.3 (30%)

**Why:**
- Too low (0.1) = False alarms, alert fatigue
- Too high (0.5) = Miss real drift, model degrades
- 0.3 catches significant drift without noise

**When to adjust:**
- Increase if getting too many false positives
- Decrease if missing actual drift

### Features Monitored: All 13 Inputs

**Why:** Comprehensive, simple, no feature selection complexity

```python
FEATURE_COLUMNS = [
    "age", "sex", "cp", "trestbps", "chol", "fbs",
    "restecg", "thalach", "exang", "oldpeak",
    "slope", "ca", "thal"
]
```

### Alert Strategy: Warning, Not Blocking

```python
if drift_score > 0.3:
    logger.warning("Drift detected, consider retraining")
    
if drift_score > 0.8:
    raise ValueError("Catastrophic drift, model unreliable")
```

**Why:** Monitoring shouldn't break production.

### Report Storage: S3 Private + Presigned URLs

**Why:**
- Private bucket = secure
- Presigned URLs = shareable (1 hour expiry)
- No public bucket = no accidental data exposure

```bash
# Generate shareable URL
aws s3 presign s3://bucket/monitoring/reports/2025-08-04/drift_report.html \
    --expires-in 3600
```

---

## Free Tier Usage

| Resource | Usage | Free Allowance | Monthly Cost |
|----------|-------|----------------|--------------|
| CloudWatch Custom Metrics | 3 metrics | 10 | $0 |
| CloudWatch Dashboards | 1 | 3 | $0 |
| CloudWatch Alarms | 2 | 10 | $0 |
| CloudWatch Logs | ~100 MB | 5 GB | $0 |
| S3 Reports | ~40 MB | 5 GB | $0 |
| SNS Notifications | ~4/month | 1M publishes | $0 |

**Total:** $0/month (within free tier)

---

## Key URLs

| Resource | URL / Path |
|----------|------------|
| MLflow UI | http://32.196.26.238:5000 |
| FastAPI Health | http://32.196.26.238:8000/health |
| CloudWatch Dashboard | [AWS Console](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=heart-disease-mlops) |
| Drift Reports | `s3://heart-disease-mlops-695074562426/monitoring/reports/` |
| Drift History | `s3://heart-disease-mlops-695074562426/monitoring/metrics/drift_scores.jsonl` |

---

## Verification Commands

```bash
# Check latest drift report
aws s3 ls s3://heart-disease-mlops-695074562426/monitoring/reports/ | tail -1

# View drift history
aws s3 cp s3://heart-disease-mlops-695074562426/monitoring/metrics/drift_scores.jsonl - | tail -10

# List CloudWatch metrics
aws cloudwatch list-metrics --namespace HeartDisease/Monitoring

# Get alarm status
aws cloudwatch describe-alarms --alarm-names heart-disease-mlops-high-drift

# Check SNS topic
aws sns list-subscriptions-by-topic \
    --topic-arn $(aws sns list-topics --query 'Topics[?contains(TopicArn, `heart-disease-mlops-alarms`)].TopicArn' --output text)

# Generate presigned URL for report
aws s3 presign s3://heart-disease-mlops-695074562426/monitoring/reports/$(date +%F)/drift_report.html --expires-in 3600
```

---

## Common Tasks

### Manually Trigger Drift Detection

```bash
python -m monitoring.generate_report
```

### View Latest Report

```bash
# Download latest
LATEST=$(aws s3 ls s3://heart-disease-mlops-695074562426/monitoring/reports/ | tail -1 | awk '{print $2}')
aws s3 cp s3://heart-disease-mlops-695074562426/monitoring/reports/${LATEST}drift_report.html /tmp/
open /tmp/drift_report.html  # or xdg-open on Linux
```

### Recreate Reference Data

```bash
python -m monitoring.reference_data
```

### Subscribe Email to Alerts

```bash
aws sns subscribe \
    --topic-arn $(terraform -chdir=infra output -raw sns_topic_arn) \
    --protocol email \
    --notification-endpoint your-email@example.com

# Then check email and click confirm link
```

---

## Troubleshooting Quick Reference

| Issue | Command | Fix |
|-------|---------|-----|
| No drift reports | `aws s3 ls s3://$S3_BUCKET/monitoring/reports/` | Run `python -m monitoring.generate_report` |
| No CloudWatch metrics | `aws cloudwatch list-metrics --namespace HeartDisease/Monitoring` | Check IAM permissions, verify region |
| Alarm not firing | `aws cloudwatch describe-alarms` | Check threshold, evaluation periods |
| Email not received | `aws sns list-subscriptions-by-topic` | Confirm subscription in email |
| Report empty | Check S3 object size | Re-run drift detection, check logs |

See [05-troubleshooting-monitoring.md](05-troubleshooting-monitoring.md) for detailed debugging.

---

## Next Phase: CI/CD (Phase 7)

With monitoring in place, we can now automate:

- **Lint + Test** on every PR (GitHub Actions)
- **Build + Push** Docker image to ECR on merge
- **Deploy** to EC2 automatically
- **Trigger** pipeline runs from GitHub
- **Notify** on drift via Slack/email

**Coming next:** `docs/learning/phase7/`

---

## Summary

| Metric | Value |
|--------|-------|
| Lines of Code (monitoring/) | ~300 |
| Terraform Resources | 6 (dashboard, 2 alarms, 2 filters, 1 topic) |
| Drift Threshold | 0.3 (30%) |
| Features Monitored | 13 (all inputs) |
| Report Retention | Unlimited (S3) |
| Metric Retention | 15 months (CloudWatch) |
| Cost | $0 (free tier) |

**Phase 6 Complete** ✅ — Your MLOps pipeline now has production-grade monitoring.
