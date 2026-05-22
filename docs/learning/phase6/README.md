# Phase 6 — Monitoring with Evidently + CloudWatch

Practical guide to implementing ML monitoring in production: data drift detection with Evidently AI and infrastructure observability with AWS CloudWatch.

---

## What This Phase Covers

| Component | Purpose | Tool |
|-----------|---------|------|
| **Data Drift** | Detect when production data differs from training baseline | Evidently AI |
| **Data Quality** | Monitor missing values, type changes, range violations | Evidently AI |
| **Concept Drift** | Track prediction quality degradation (when labels available) | Evidently AI |
| **Infrastructure** | EC2 health, CPU, memory, API errors | CloudWatch |
| **Alerts** | Notify on issues via SNS | CloudWatch Alarms |
| **Reporting** | HTML drift reports saved to S3 | S3 + Evidently |

---

## Documentation Index

| File | What You'll Learn |
|------|-------------------|
| [Phase 6 Overview](phase6-overview.md) | Architecture, current state, what's been built |
| [01 — Evidently Drift Detection](01-evidently-drift-detection.md) | Setting up Evidently, reference data, drift reports, S3 storage |
| [02 — CloudWatch Metrics](02-cloudwatch-metrics.md) | Custom metrics, namespace design, metric pushing from Python |
| [03 — Infrastructure Monitoring](03-infrastructure-monitoring.md) | Dashboards, alarms, SNS notifications via Terraform |
| [04 — Pipeline Integration](04-pipeline-integration.md) | Adding monitoring to Prefect flows, task design, error handling |
| [05 — Troubleshooting Monitoring](05-troubleshooting-monitoring.md) | Common errors, debugging metrics, verifying reports |

---

## Quick Start

```bash
# 1. Install Evidently
pip install evidently==0.4.0 pyarrow

# 2. Create reference data (run once)
python -m monitoring.reference_data

# 3. Generate drift report
python -m monitoring.generate_report

# 4. Check S3 for report
aws s3 ls s3://$S3_BUCKET/monitoring/reports/

# 5. View CloudWatch metrics
aws cloudwatch list-metrics --namespace HeartDisease/Monitoring
```

---

## Key URLs

| Service | URL |
|---------|-----|
| MLflow UI | http://32.196.26.238:5000 |
| FastAPI Health | http://32.196.26.238:8000/health |
| AWS Console | https://console.aws.amazon.com |
| CloudWatch Dashboard | AWS Console → CloudWatch → Dashboards → heart-disease-mlops |

---

## Architecture

```
Prefect Flow
    │
    ├──► Train Model ──► Register Model ──► Set Champion Alias
    │                                           │
    │                                           ▼
    │                                    Drift Detection Task
    │                                           │
    │       ┌───────────────────────────────────┘
    │       │
    │       ▼
    │   Load Reference Data (S3)
    │       │
    │       ▼
    │   Load Current Data (S3)
    │       │
    │       ▼
    │   Evidently Report (data drift + quality)
    │       │
    │       ├──► Save HTML to S3
    │       │
    │       ├──► Append score to drift_scores.jsonl
    │       │
    │       └──► Push to CloudWatch Metrics
    │               │
    │               ▼
    │       CloudWatch Dashboard
    │               │
    │               ▼
    │       Alarm (if drift > 0.3)
    │               │
    │               ▼
    │           SNS Topic
    │               │
    │               ▼
    │           Email Alert
    │
    └──► Continue pipeline (or halt if critical)
```

---

## Files Created

```
monitoring/
├── __init__.py
├── config.py              # Central config: thresholds, paths, features
├── reference_data.py      # Save training baseline to S3
├── generate_report.py     # Evidently drift + quality reports
├── cloudwatch_metrics.py  # Push metrics to CloudWatch
└── utils.py               # S3 helpers, data loading

infra/modules/monitoring/
├── main.tf                # Dashboard, alarms, SNS
├── variables.tf           # Inputs: thresholds, email, log groups
└── outputs.tf             # SNS topic ARN, dashboard URL

heart_disease_prediction/
└── prefect_flow.py        # Modified: added drift_detection task
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Drift Threshold | 0.3 (30%) | Balanced sensitivity — catches real drift without noise |
| Monitored Features | All 13 inputs | Simple, comprehensive; no feature selection complexity |
| What to Monitor | Input features | Available immediately, no label delay |
| Report Storage | S3 private bucket | Secure, versioned, accessible via presigned URLs |
| Score History | JSON Lines format | Append-friendly, easy to parse, compact |
| Alert Method | CloudWatch → SNS | Native AWS integration, email ready |
| Integration Point | After model registration | Ensures champion model is set before comparison |

---

## Free Tier Impact

| Resource | Usage | Allowance | Headroom |
|----------|-------|-----------|----------|
| CloudWatch Custom Metrics | 3 metrics | 10 free | 7 |
| CloudWatch Dashboards | 1 dashboard | 3 free | 2 |
| CloudWatch Alarms | 2 alarms | 10 free | 8 |
| S3 Reports | ~10 MB/week | 5 GB total | ~4.5 GB |
| SNS Notifications | Email only | 1M publishes free | ~1M |

**Total additional monthly cost: $0**

---

## Verification Checklist

- [ ] Reference data uploaded to S3 (`data/reference/reference_data.parquet`)
- [ ] Drift report generates without errors
- [ ] HTML report accessible in S3
- [ ] CloudWatch metrics appear under `HeartDisease/Monitoring`
- [ ] Dashboard shows 4+ widgets (CPU, memory, drift, requests)
- [ ] Alarms created (high-cpu, high-drift)
- [ ] Prefect task integrated and runs successfully
- [ ] Drift score > 0.3 triggers warning in logs

---

## Next Phase

**Phase 7: CI/CD with GitHub Actions**
- Automated linting, testing, building
- Docker image push to ECR
- Automated EC2 deployment
- OIDC authentication (no stored AWS keys)

See `docs/learning/phase7/` (coming next).
