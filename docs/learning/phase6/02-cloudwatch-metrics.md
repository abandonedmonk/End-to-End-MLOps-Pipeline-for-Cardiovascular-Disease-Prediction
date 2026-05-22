# 02 — CloudWatch Metrics

Pushing custom metrics from Python to AWS CloudWatch for monitoring and alerting.

---

## Why CloudWatch Metrics?

**Problem:** Evidently generates beautiful reports, but you need programmatic access to drift scores for:
- Dashboards (visualization)
- Alarms (automated alerts)
- Historical tracking (trends over time)

**Solution:** CloudWatch custom metrics
- Native AWS integration
- Free tier: 10 custom metrics
- Automatic aggregation (min, max, avg, sum, count)
- Retention: 15 months

---

## Metric Design

### Namespaces
Organize metrics hierarchically:
```
HeartDisease/Monitoring/    # Our namespace
├── DataDriftScore          # Overall drift (0-1)
├── DriftedFeatureCount     # Number of features that drifted
├── FastAPIRequestCount     # Total predictions
├── FastAPI5xxErrorCount    # Server errors
└── FastAPILatency          # Response time (p50, p99)
```

### Dimensions (Tags)
Use dimensions sparingly — each unique combination counts as a separate metric!

**Good:** No dimensions (just the metric value)  
**Bad:** High cardinality (user_id, request_id)

```python
# Simple metric (1 metric)
cloudwatch.put_metric_data(
    Namespace='HeartDisease/Monitoring',
    MetricData=[{
        'MetricName': 'DataDriftScore',
        'Value': 0.35,
        'Unit': 'None'
    }]
)

# With dimensions (still 1 metric if values are static)
cloudwatch.put_metric_data(
    Namespace='HeartDisease/Monitoring',
    MetricData=[{
        'MetricName': 'DataDriftScore',
        'Value': 0.35,
        'Unit': 'None',
        'Dimensions': [
            {'Name': 'Environment', 'Value': 'production'}
        ]
    }]
)
```

---

## Implementation

### CloudWatch Metrics Module (`monitoring/cloudwatch_metrics.py`)

```python
"""
Push custom metrics to AWS CloudWatch.
"""
import boto3
from datetime import datetime
from monitoring.config import AWS_REGION, CLOUDWATCH_NAMESPACE


def get_cloudwatch_client():
    """Get CloudWatch client with region."""
    return boto3.client('cloudwatch', region_name=AWS_REGION)


def push_drift_metrics(drift_score: float, drift_detected: bool):
    """
    Push drift metrics to CloudWatch.
    
    Args:
        drift_score: Overall drift score (0-1)
        drift_detected: Whether drift exceeded threshold
    """
    cloudwatch = get_cloudwatch_client()
    
    timestamp = datetime.utcnow()
    
    metrics = [
        {
            'MetricName': 'DataDriftScore',
            'Value': drift_score,
            'Unit': 'None',
            'Timestamp': timestamp
        },
        {
            'MetricName': 'DriftDetected',
            'Value': 1.0 if drift_detected else 0.0,
            'Unit': 'Count',
            'Timestamp': timestamp
        }
    ]
    
    cloudwatch.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=metrics
    )
    
    print(f"✓ CloudWatch metrics pushed: drift_score={drift_score:.3f}")


def push_fastapi_metrics(
    request_count: int,
    error_5xx_count: int,
    latency_p99: float = None
):
    """
    Push FastAPI application metrics.
    
    These would typically come from log parsing or middleware.
    """
    cloudwatch = get_cloudwatch_client()
    
    timestamp = datetime.utcnow()
    
    metrics = [
        {
            'MetricName': 'FastAPIRequestCount',
            'Value': float(request_count),
            'Unit': 'Count',
            'Timestamp': timestamp
        },
        {
            'MetricName': 'FastAPI5xxErrorCount',
            'Value': float(error_5xx_count),
            'Unit': 'Count',
            'Timestamp': timestamp
        }
    ]
    
    if latency_p99:
        metrics.append({
            'MetricName': 'FastAPILatencyP99',
            'Value': latency_p99,
            'Unit': 'Milliseconds',
            'Timestamp': timestamp
        })
    
    cloudwatch.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=metrics
    )


def get_metric_statistics(
    metric_name: str,
    start_time: datetime,
    end_time: datetime,
    statistics: list = ['Average', 'Maximum'],
    period: int = 3600  # 1 hour
):
    """
    Query metric statistics from CloudWatch.
    Useful for trend analysis.
    """
    cloudwatch = get_cloudwatch_client()
    
    response = cloudwatch.get_metric_statistics(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricName=metric_name,
        StartTime=start_time,
        EndTime=end_time,
        Period=period,
        Statistics=statistics
    )
    
    return response['Datapoints']
```

### IAM Permissions Required

Add to EC2 instance profile policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cloudwatch:PutMetricData",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics"
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "cloudwatch:namespace": "HeartDisease/Monitoring"
                }
            }
        }
    ]
}
```

**Note:** The `cloudwatch:namespace` condition ensures you can only write to your specific namespace.

---

## Integration with Drift Detection

Update `monitoring/generate_report.py` to push metrics:

```python
# At the end of generate_drift_report()
from monitoring.cloudwatch_metrics import push_drift_metrics

def generate_drift_report(reference_df, current_df):
    # ... existing code ...
    
    # After saving report to S3
    push_drift_metrics(drift_score, drift_detected)
    
    return html_path, drift_score, drift_detected
```

---

## Viewing Metrics

### AWS CLI

```bash
# List all metrics in namespace
aws cloudwatch list-metrics --namespace HeartDisease/Monitoring

# Get recent drift scores
aws cloudwatch get-metric-statistics \
    --namespace HeartDisease/Monitoring \
    --metric-name DataDriftScore \
    --start-time 2025-08-01T00:00:00Z \
    --end-time 2025-08-08T00:00:00Z \
    --period 86400 \
    --statistics Average Maximum

# Get metric widget image (for sharing)
aws cloudwatch get-metric-widget-image \
    --metric-widget '{
        "metrics": [["HeartDisease/Monitoring", "DataDriftScore"]],
        "period": 86400,
        "start": "-P7D",
        "end": "PT0H"
    }'
```

### AWS Console

1. Navigate to **CloudWatch → Metrics**
2. Select **HeartDisease/Monitoring** namespace
3. Click on metric name to view graph
4. Click **Create Alarm** to set up alerts

### Python (Programmatic)

```python
from monitoring.cloudwatch_metrics import get_metric_statistics
from datetime import datetime, timedelta

# Get drift scores for last 7 days
end_time = datetime.utcnow()
start_time = end_time - timedelta(days=7)

stats = get_metric_statistics(
    metric_name='DataDriftScore',
    start_time=start_time,
    end_time=end_time,
    period=86400  # Daily aggregation
)

for point in sorted(stats, key=lambda x: x['Timestamp']):
    print(f"{point['Timestamp']}: {point['Average']:.3f}")
```

---

## Best Practices

### 1. Batch Metrics
Don't push one metric at a time — batch them:

```python
# Good: One API call
cloudwatch.put_metric_data(
    Namespace='MyNamespace',
    MetricData=[metric1, metric2, metric3, ...]
)

# Bad: Multiple API calls
cloudwatch.put_metric_data(Namespace='...', MetricData=[metric1])
cloudwatch.put_metric_data(Namespace='...', MetricData=[metric2])
```

### 2. Handle Throttling
CloudWatch limits: 150 TPS per region per account. Implement backoff:

```python
from botocore.exceptions import ClientError
import time

def push_with_retry(metrics, max_retries=3):
    for attempt in range(max_retries):
        try:
            cloudwatch.put_metric_data(...)
            break
        except ClientError as e:
            if e.response['Error']['Code'] == 'Throttling':
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

### 3. Set Timestamps
Always set explicit timestamps to ensure ordering:

```python
'Timestamp': datetime.utcnow()  # Don't rely on server time
```

### 4. Use Appropriate Units
- Counts: `'Unit': 'Count'`
- Percentages/Ratios: `'Unit': 'None'` (or 'Percent' for 0-100)
- Latency: `'Unit': 'Milliseconds'`
- Size: `'Unit': 'Bytes'`

---

## Debugging

### Metric Not Appearing?

```bash
# Check if namespace exists
aws cloudwatch list-metrics --namespace HeartDisease/Monitoring

# Check recent data (may take a few minutes to appear)
aws cloudwatch get-metric-statistics \
    --namespace HeartDisease/Monitoring \
    --metric-name DataDriftScore \
    --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 60 \
    --statistics Average
```

### Permission Denied?

```bash
# Check EC2 instance profile
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Test with explicit credentials
AWS_REGION=us-east-1 python -c "
import boto3
cloudwatch = boto3.client('cloudwatch')
cloudwatch.put_metric_data(
    Namespace='TestNamespace',
    MetricData=[{'MetricName': 'Test', 'Value': 1, 'Unit': 'Count'}]
)
print('Success!')
"
```

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `AccessDenied` | Missing IAM policy | Add `cloudwatch:PutMetricData` |
| `InvalidParameterValue` | Value out of range | Ensure drift_score is 0-1 |
| `ThrottlingException` | Too many requests | Batch metrics, add backoff |
| `Timestamp too old` | Clock skew | Use `datetime.utcnow()` |
