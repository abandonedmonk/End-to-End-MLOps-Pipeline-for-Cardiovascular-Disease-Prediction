# Phase 6 Implementation Summary

## What Was Built

- `monitoring/config.py`: central monitoring configuration for S3 paths, AWS region, drift threshold, feature columns, and CloudWatch namespace.
- `monitoring/reference_data.py`: builds the training-data baseline and writes `data/reference/reference_data.parquet` to S3.
- `monitoring/generate_report.py`: loads reference/current feature data, runs Evidently data drift and data quality reports, uploads HTML reports to S3, and appends drift history to `monitoring/metrics/drift_scores.jsonl`.
- `monitoring/cloudwatch_metrics.py`: publishes `DataDriftScore`, `FastAPIRequestCount`, and `FastAPI5xxErrorCount` to CloudWatch.
- `heart_disease_prediction/prefect_flow.py`: adds a final `drift_detection` task after successful model registration and model alias promotion.
- `infra/modules/monitoring/`: creates a CloudWatch dashboard, CPU alarm, drift alarm, and SNS topic for manual email subscription.
- `requirements.txt` and `pyproject.toml`: add `evidently==0.4.0` and `pyarrow`.

## How It Works

The weekly Prefect flow trains models, registers the best model, promotes it to the `champion` alias, and then runs drift detection. The drift task compares the S3 reference snapshot against the current feature snapshot at `s3://heart-disease-mlops-695074562426/monitoring/current/current_data.parquet`.

If the current snapshot is not present yet, the job falls back to the configured raw data path so the first scheduled run can still produce a report. Reports are written to `s3://heart-disease-mlops-695074562426/monitoring/reports/<date>/drift_report.html`, and historical drift scores are appended to `s3://heart-disease-mlops-695074562426/monitoring/metrics/drift_scores.jsonl`.

CloudWatch receives the drift score, recent FastAPI prediction count, and recent FastAPI 5xx count under the `HeartDisease/Monitoring` namespace. Terraform adds dashboard widgets for EC2 CPU, EC2 memory, drift score, and FastAPI request/error counts.

## Key Design Decisions

- Drift threshold is `0.3`, meaning alerts fire when more than 30% of monitored features drift.
- Drift detection uses all 13 model input features: `age`, `sex`, `cp`, `trestbps`, `chol`, `fbs`, `restecg`, `thalach`, `exang`, `oldpeak`, `slope`, `ca`, and `thal`.
- Monitoring compares input features, not predictions, because feature drift is available before labels arrive and is easier to operationalize weekly.
- The Prefect task logs drift warnings now; SNS alarm delivery is provisioned for manual email subscription and future alert routing.
- The S3 bucket remains private. Use AWS CLI download or a presigned URL to view HTML reports instead of making the bucket public.

## Bugs Encountered & Fixes

- The existing API does not yet persist prediction feature snapshots. The drift job now supports `CURRENT_DATA_S3_KEY` and uses a raw-data fallback until prediction logging is added.
- `ca` and `thal` arrive as categorical values in training data but may be numeric in API payloads. Monitoring normalizes categorical columns to strings before report generation.
- Model registration previously returned `None` on failure while the flow continued. The flow now raises an error before promotion and drift detection if registration fails.
- The EC2 role had CloudWatch agent permissions, but the application task also needs `cloudwatch:PutMetricData` and `logs:FilterLogEvents`; these are now added in IAM.

## Debugging Tips

- If the report is missing, check that `S3_BUCKET`, `AWS_REGION`, and `DATA_PATH` are set on the EC2/Prefect environment.
- If current data is missing, upload a parquet file with the 13 feature columns to `monitoring/current/current_data.parquet`.
- If CloudWatch metrics are missing, verify the EC2 instance profile includes the updated monitoring policy.
- If FastAPI request counts are always zero, verify `FASTAPI_LOG_GROUP` matches the log group where API logs are shipped.
- If Evidently errors on columns, compare the parquet schema with the feature list in `monitoring/config.py`.

## Verification Commands

```bash
# Create or refresh reference data
python -m monitoring.reference_data

# Generate a drift report manually
python -m monitoring.generate_report

# Check drift report in S3
aws s3 ls s3://heart-disease-mlops-695074562426/monitoring/reports/

# Download the latest HTML report
aws s3 cp s3://heart-disease-mlops-695074562426/monitoring/reports/$(date +%F)/drift_report.html /tmp/drift_report.html

# View CloudWatch metrics
aws cloudwatch list-metrics --namespace HeartDisease/Monitoring

# Check alarm status
aws cloudwatch describe-alarms --alarm-names high-cpu high-drift

# Apply monitoring infrastructure
terraform -chdir=infra plan
terraform -chdir=infra apply
```
