# 05 — Troubleshooting Monitoring

Common errors, debugging techniques, and fixes for Evidently + CloudWatch monitoring.

---

## Quick Diagnostic Commands

```bash
# 1. Check S3 for reports
aws s3 ls s3://heart-disease-mlops-695074562426/monitoring/reports/ --recursive

# 2. Check drift history
aws s3 cp s3://heart-disease-mlops-695074562426/monitoring/metrics/drift_scores.jsonl - | tail -5

# 3. List CloudWatch metrics
aws cloudwatch list-metrics --namespace HeartDisease/Monitoring

# 4. Get recent drift scores
aws cloudwatch get-metric-statistics \
    --namespace HeartDisease/Monitoring \
    --metric-name DataDriftScore \
    --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 86400 \
    --statistics Average Maximum

# 5. Check CloudWatch alarms
aws cloudwatch describe-alarms --alarm-names heart-disease-mlops-high-drift

# 6. Test drift detection locally
python -m monitoring.generate_report
```

---

## Evidently Errors

### Error: `NoSuchKey` — Reference Data Not Found

**Symptom:**
```
botocore.errorfactory.NoSuchKey: An error occurred (NoSuchKey) 
when calling the GetObject operation: The specified key does not exist.
```

**Cause:** Reference data hasn't been created yet.

**Fix:**
```bash
# Create reference data
python -m monitoring.reference_data

# Verify it exists
aws s3 ls s3://heart-disease-mlops-695074562426/data/reference/
```

### Error: `KeyError: 'dataset_drift'`

**Symptom:**
```
KeyError: 'dataset_drift'
```

**Cause:** Evidently report structure changed or metrics not found.

**Fix:** Update metric extraction:
```python
# Debug: print report structure
report_dict = report.as_dict()
print(json.dumps(report_dict, indent=2))

# Then find correct path to drift score
# Usually: report_dict['metrics'][0]['result']['dataset_drift']
```

### Error: `ValueError: could not convert string to float`

**Symptom:**
```
ValueError: could not convert string to float: '?'
```

**Cause:** Missing values (`?`) in Cleveland dataset not handled.

**Fix:** Already handled in `reference_data.py`:
```python
# Ensure categorical columns are strings
for col in CATEGORICAL_COLUMNS:
    if col in reference_df.columns:
        reference_df[col] = reference_df[col].astype(str)
```

### Error: `Different columns in reference and current`

**Symptom:**
```
ValueError: Columns in reference and current datasets are different
```

**Cause:** Feature columns don't match between datasets.

**Fix:** Ensure both datasets have same columns:
```python
# In generate_report.py
assert set(reference_df.columns) == set(current_df.columns), \
    f"Column mismatch: {set(reference_df.columns) ^ set(current_df.columns)}"

# Or subset to common columns
common_cols = list(set(reference_df.columns) & set(current_df.columns))
reference_df = reference_df[common_cols]
current_df = current_df[common_cols]
```

### Error: Report generates but HTML is empty

**Symptom:** HTML file is 0 bytes or missing content.

**Cause:** Report didn't run successfully.

**Fix:** Check for exceptions before save:
```python
try:
    report.run(reference_data=ref, current_data=cur)
    html = report.get_html()
    if not html or len(html) < 1000:
        raise ValueError("Report HTML is empty")
    s3.put_object(..., Body=html.encode('utf-8'))
except Exception as e:
    logger.error(f"Report generation failed: {e}")
    raise
```

---

## CloudWatch Errors

### Error: `AccessDenied` — Permission Denied

**Symptom:**
```
botocore.exceptions.ClientError: An error occurred (AccessDenied) 
when calling the PutMetricData operation
```

**Cause:** EC2 instance lacks CloudWatch permissions.

**Fix:**
```bash
# Check current IAM role
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Verify policy includes cloudwatch:PutMetricData
aws iam get-role-policy \
    --role-name heart-disease-mlops-ec2-role \
    --policy-name CloudWatchMetricsPolicy
```

Add to `infra/modules/iam/main.tf`:
```json
{
    "Effect": "Allow",
    "Action": [
        "cloudwatch:PutMetricData",
        "cloudwatch:GetMetricStatistics"
    ],
    "Resource": "*",
    "Condition": {
        "StringEquals": {
            "cloudwatch:namespace": "HeartDisease/Monitoring"
        }
    }
}
```

Then:
```bash
terraform -chdir=infra apply
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/  # refresh
```

### Error: `InvalidParameterValue` — Invalid Metric Value

**Symptom:**
```
Parameter validation failed: Invalid parameter: Value
```

**Cause:** Metric value out of valid range.

**Fix:** Validate before sending:
```python
def push_drift_metrics(score, detected):
    # Ensure score is valid
    if not isinstance(score, (int, float)):
        score = float(score)
    
    if score < 0 or score > 1:
        logger.warning(f"Clamping drift score {score} to [0,1]")
        score = max(0, min(1, score))
    
    cloudwatch.put_metric_data(...)
```

### Error: `ThrottlingException` — Too Many Requests

**Symptom:**
```
botocore.exceptions.ClientError: An error occurred (ThrottlingException) 
when calling the PutMetricData operation: Rate exceeded
```

**Cause:** Exceeding 150 TPS CloudWatch limit.

**Fix:** Add exponential backoff:
```python
from botocore.exceptions import ClientError
import time

def push_with_retry(metrics, max_retries=3):
    cloudwatch = boto3.client('cloudwatch')
    
    for attempt in range(max_retries):
        try:
            cloudwatch.put_metric_data(
                Namespace='HeartDisease/Monitoring',
                MetricData=metrics
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'Throttling':
                wait = 2 ** attempt
                logger.warning(f"Throttled, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    
    raise Exception("Max retries exceeded")
```

### Error: Metrics Not Appearing in Console

**Symptom:** `put_metric_data` succeeds but metrics don't show.

**Possible Causes:**

1. **Wrong region**
   ```python
   # Ensure region matches your deployment
   cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
   ```

2. **Delay** — CloudWatch metrics take 2-3 minutes to appear
   ```bash
   # Wait, then check
   sleep 180
   aws cloudwatch list-metrics --namespace HeartDisease/Monitoring
   ```

3. **Wrong namespace** — Check for typos
   ```bash
   # List all namespaces
   aws cloudwatch list-metrics | jq '.Metrics[].Namespace' | sort | uniq
   ```

4. **Wrong timestamp** — Metrics in the future won't show
   ```python
   # Always use UTC
   from datetime import datetime
   timestamp = datetime.utcnow()
   ```

---

## S3 Errors

### Error: `NoSuchBucket`

**Symptom:**
```
botocore.errorfactory.NoSuchBucket: The specified bucket does not exist
```

**Cause:** S3_BUCKET env var wrong or bucket doesn't exist.

**Fix:**
```bash
# Check bucket exists
aws s3 ls s3://heart-disease-mlops-695074562426

# Verify env var
echo $S3_BUCKET  # Should be: heart-disease-mlops-695074562426

# Set if missing
export S3_BUCKET=heart-disease-mlops-695074562426
```

### Error: `AccessDenied` — S3 Permission

**Symptom:**
```
botocore.exceptions.ClientError: An error occurred (AccessDenied) 
when calling the PutObject operation
```

**Cause:** EC2 role lacks S3 permissions.

**Fix:** Verify IAM policy includes:
```json
{
    "Effect": "Allow",
    "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
    ],
    "Resource": [
        "arn:aws:s3:::heart-disease-mlops-695074562426",
        "arn:aws:s3:::heart-disease-mlops-695074562426/*"
    ]
}
```

---

## Pipeline Integration Errors

### Error: Drift Task Not Running

**Symptom:** Pipeline completes but no drift detection output.

**Cause:** Task not called or failed silently.

**Fix:** Add explicit error raising:
```python
@task(name="drift_detection")
def run_drift_detection():
    logger = get_run_logger()
    
    try:
        result = generate_report_with_fallback()
        return result
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        raise  # Don't swallow errors
```

### Error: `ModuleNotFoundError: No module named 'monitoring'`

**Symptom:**
```
ModuleNotFoundError: No module named 'monitoring'
```

**Cause:** Monitoring package not installed on EC2.

**Fix:**
```bash
# SSH to EC2
ssh -i ~/.ssh/id_ed25519 ubuntu@32.196.26.238

# Install dependencies
sudo /opt/mlflow-venv/bin/pip install evidently==0.4.0 pyarrow

# Verify
sudo /opt/mlflow-venv/bin/python -c "import monitoring; print('OK')"
```

### Error: Drift Detection Slow / Timeout

**Symptom:** Task times out after 60 seconds.

**Cause:** Large datasets or slow S3 reads.

**Fix:** Add task timeout and optimize:
```python
@task(name="drift_detection", timeout_seconds=300)  # 5 minutes
def run_drift_detection():
    # Sample large datasets
    if len(current_df) > 10000:
        current_df = current_df.sample(10000, random_state=42)
    
    # Run report
    report.run(...)
```

---

## CloudWatch Dashboard Issues

### Widget Shows "No Data"

**Symptom:** Dashboard widget is empty.

**Troubleshooting:**

1. **Check metric exists:**
   ```bash
   aws cloudwatch list-metrics \
       --namespace HeartDisease/Monitoring \
       --metric-name DataDriftScore
   ```

2. **Check time range:**
   - Metric might be outside dashboard window
   - Adjust time picker to "Last 7 days"

3. **Check period alignment:**
   - Dashboard period (e.g., 86400 for daily)
   - Must align with when metrics were pushed

4. **Refresh credentials:**
   ```bash
   aws sts get-caller-identity  # Verify you're in right account
   ```

### Alarm Not Triggering

**Symptom:** Metric exceeds threshold but alarm stays OK.

**Possible Causes:**

1. **Evaluation periods** — Alarm needs 2 consecutive periods
   ```bash
   # Check alarm state
   aws cloudwatch describe-alarms \
       --alarm-names heart-disease-mlops-high-drift \
       --query 'MetricAlarms[0].StateValue'
   ```

2. **Missing data** — Alarm treats missing as "not breaching"
   ```bash
   # Configure alarm to treat missing as breaching
   aws cloudwatch put-metric-alarm \
       --alarm-name heart-disease-mlops-high-drift \
       --treat-missing-data breaching
   ```

3. **Wrong statistic** — Using Average instead of Maximum
   ```hcl
   # In Terraform: use Maximum for drift score
   statistic = "Maximum"
   ```

---

## Debugging Techniques

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
boto3.set_stream_logger('', logging.DEBUG)
```

### Print Report Structure

```python
def debug_report_structure():
    report = Report(metrics=[DatasetDriftMetric()])
    report.run(reference_data=ref, current_data=cur)
    
    # Print full structure
    import json
    print(json.dumps(report.as_dict(), indent=2))
    
    # Find drift score path
    for i, metric in enumerate(report.as_dict()['metrics']):
        print(f"\nMetric {i}: {metric.get('metric')}")
        print(f"Result: {metric.get('result', {}).keys()}")
```

### Test CloudWatch Locally

```python
# test_cloudwatch.py
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

# Test push
try:
    cloudwatch.put_metric_data(
        Namespace='TestNamespace',
        MetricData=[{
            'MetricName': 'TestMetric',
            'Value': 42.0,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }]
    )
    print("✓ Metric pushed successfully")
except Exception as e:
    print(f"✗ Error: {e}")

# Verify
response = cloudwatch.list_metrics(Namespace='TestNamespace')
print(f"Metrics: {response['Metrics']}")
```

### Check S3 Object Metadata

```bash
# Verify report was uploaded correctly
aws s3api head-object \
    --bucket heart-disease-mlops-695074562426 \
    --key monitoring/reports/2025-08-01/drift_report.html

# Should show Content-Type: text/html and Content-Length > 0
```

---

## Common Mistakes

| Mistake | Impact | Solution |
|---------|--------|----------|
| Forgetting `datetime.utcnow()` | Metrics appear in wrong time window | Always use UTC |
| Wrong AWS region | Metrics sent to wrong region | Explicit `region_name` in client |
| Not handling categorical columns | Evidently type errors | Convert to string before comparison |
| Ignoring monitoring task failures | Silent data quality issues | Log errors but don't necessarily fail pipeline |
| Using wrong feature columns | Drift on irrelevant features | Use same columns as model training |
| Not saving reports | Can't debug historical drift | Always save HTML to S3 |
| Missing IAM permissions | Monitoring silently fails | Test permissions before production |
| Hardcoding paths | Breaks when bucket changes | Use env vars for all paths |

---

## Getting Help

### Evidently Resources
- Docs: https://docs.evidentlyai.com/
- GitHub: https://github.com/evidentlyai/evidently
- Examples: https://github.com/evidentlyai/evidently/tree/main/examples

### CloudWatch Resources
- Docs: https://docs.aws.amazon.com/cloudwatch/
- Limits: https://docs.aws.amazon.com/cloudwatch/latest/monitoring/cloudwatch_limits.html
- Pricing: https://aws.amazon.com/cloudwatch/pricing/

### Debugging Workflow

1. **Local first** — Run `python -m monitoring.generate_report` locally
2. **Check S3** — Verify reports exist with `aws s3 ls`
3. **Test CloudWatch** — Run test script to verify permissions
4. **Check logs** — SSH to EC2 and check `journalctl -u prefect-agent`
5. **Simplify** — Comment out parts of the flow to isolate the issue

---

## Verification Script

Save as `verify_monitoring.py`:

```python
#!/usr/bin/env python3
"""Verify monitoring setup is working."""
import boto3
import os
from datetime import datetime, timedelta

BUCKET = os.getenv('S3_BUCKET', 'heart-disease-mlops-695074562426')
REGION = os.getenv('AWS_REGION', 'us-east-1')

def check_s3():
    """Verify S3 paths exist."""
    s3 = boto3.client('s3', region_name=REGION)
    
    checks = [
        'data/reference/reference_data.parquet',
        'monitoring/metrics/drift_scores.jsonl'
    ]
    
    for key in checks:
        try:
            s3.head_object(Bucket=BUCKET, Key=key)
            print(f"✓ S3: {key}")
        except s3.exceptions.ClientError:
            print(f"✗ S3: {key} (missing)")

def check_cloudwatch():
    """Verify CloudWatch metrics."""
    cloudwatch = boto3.client('cloudwatch', region_name=REGION)
    
    try:
        response = cloudwatch.list_metrics(Namespace='HeartDisease/Monitoring')
        metrics = [m['MetricName'] for m in response['Metrics']]
        
        if metrics:
            print(f"✓ CloudWatch: {len(metrics)} metrics found")
            for m in set(metrics):
                print(f"  - {m}")
        else:
            print("✗ CloudWatch: No metrics found")
    except Exception as e:
        print(f"✗ CloudWatch: {e}")

def check_alarms():
    """Verify alarms exist."""
    cloudwatch = boto3.client('cloudwatch', region_name=REGION)
    
    try:
        response = cloudwatch.describe_alarms(
            AlarmNames=['heart-disease-mlops-high-cpu', 'heart-disease-mlops-high-drift']
        )
        
        for alarm in response['MetricAlarms']:
            print(f"✓ Alarm: {alarm['AlarmName']} ({alarm['StateValue']})")
    except Exception as e:
        print(f"✗ Alarms: {e}")

if __name__ == "__main__":
    print("Monitoring Verification")
    print("=" * 50)
    check_s3()
    check_cloudwatch()
    check_alarms()
    print("=" * 50)
```

Run:
```bash
python verify_monitoring.py
```
