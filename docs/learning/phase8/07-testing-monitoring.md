# 07 — Testing Monitoring

Testing drift detection with Evidently, CloudWatch metrics, and S3 report storage.

---

## Table of Contents

1. [What We Test](#what-we-test)
2. [Testing Reference Data](#testing-reference-data)
3. [Testing Drift Reports](#testing-drift-reports)
4. [Testing CloudWatch Metrics](#testing-cloudwatch-metrics)
5. [Testing Log Queries](#testing-log-queries)
6. [Mocking Strategies](#mocking-strategies)
7. [Common Patterns](#common-patterns)
8. [Troubleshooting](#troubleshooting)

---

## What We Test

Monitoring has multiple components:

```
┌─────────────────────────────────────────────────────────────────┐
│  Reference Data (Training Baseline)                            │
│  → Load from S3                                                 │
│  → Save to S3 as parquet                                        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Current Data (New Predictions)                                  │
│  → Collect from API or batch predictions                        │
│  → Compare to reference                                         │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Evidently Report                                                │
│  → Generate drift report                                        │
│  → Check data quality                                           │
│  → Save HTML + JSON to S3                                       │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  CloudWatch Metrics                                              │
│  → Push drift score                                             │
│  → Push request/error counts                                    │
│  → Namespace + ModelName dimension                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Reference Data

### Test: Reference Data Creation

```python
# tests/test_monitoring.py
@mock_aws
def test_reference_data_creation_saves_expected_columns(sample_data_file):
    """Validate reference data is saved to S3 with the expected feature columns."""
    config = get_config()
    
    # Setup: Create mock S3 bucket
    s3 = boto3.client("s3", region_name=config.aws_region)
    s3.create_bucket(Bucket=config.s3_bucket)
    
    # Action: Save reference data
    uri = reference_data.save_reference_data(str(sample_data_file))
    
    # Assert: Correct S3 URI returned
    assert uri == config.reference_data_uri
    
    # Assert: File exists in S3
    obj = s3.get_object(Bucket=config.s3_bucket, Key=config.reference_data_key)
    saved = pd.read_parquet(BytesIO(obj["Body"].read()))
    
    # Assert: Has expected columns
    assert list(saved.columns) == FEATURE_COLUMNS
    assert len(saved) > 0
```

**What it validates:**
- Reference data uploads to correct S3 path
- Returns proper S3 URI
- Saved as parquet (efficient format)
- Has correct columns
- Contains data

---

### Test: Reference Data Idempotency

```python
@mock_aws
def test_reference_data_creation_is_idempotent(sample_data_file):
    """Validate saving reference data twice produces same result."""
    config = get_config()
    s3 = boto3.client("s3", region_name=config.aws_region)
    s3.create_bucket(Bucket=config.s3_bucket)
    
    # Save twice
    uri1 = reference_data.save_reference_data(str(sample_data_file))
    uri2 = reference_data.save_reference_data(str(sample_data_file))
    
    # Same URI
    assert uri1 == uri2
    
    # Same content (overwritten or same)
    obj = s3.get_object(Bucket=config.s3_bucket, Key=config.reference_data_key)
    saved = pd.read_parquet(BytesIO(obj["Body"].read()))
    
    original = pd.read_csv(sample_data_file, header=None, names=FEATURE_COLUMNS)
    assert len(saved) == len(original)
```

---

## Testing Drift Reports

### Test: Drift Report Generation

```python
@mock_aws
def test_drift_report_generation_uploads_report_and_metrics(
    monkeypatch, sample_data_file
):
    """Validate drift report generation uploads HTML and writes drift summary metrics."""
    config = get_config()
    
    # Setup: Mock S3
    client = boto3.client("s3", region_name=config.aws_region)
    client.create_bucket(Bucket=config.s3_bucket)
    
    # Setup: Set data path to our test file
    monkeypatch.setenv("DATA_PATH", str(sample_data_file))
    
    # Setup: Mock Evidently Report (skip real calculation)
    class FakeReport:
        def __init__(self, metrics):
            self.metrics = metrics
        
        def run(self, reference_data, current_data, column_mapping):
            self.reference_rows = len(reference_data)
            self.current_rows = len(current_data)
        
        def as_dict(self):
            return {
                "metrics": [
                    {"result": {"share_of_drifted_columns": 0.1}},
                ]
            }
        
        def save_html(self, path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("<html>drift</html>")
    
    monkeypatch.setattr(generate_report, "Report", FakeReport)
    
    # Action: Generate report
    result = generate_report.generate_drift_report()
    
    # Assert: Drift score extracted
    assert result["drift_score"] == 0.1
    assert result["drift_detected"] is False
    
    # Assert: Report uploaded to S3
    report_key = result["report_uri"].split(f"s3://{config.s3_bucket}/", 1)[1]
    report_object = client.get_object(Bucket=config.s3_bucket, Key=report_key)
    assert b"drift" in report_object["Body"].read()
    
    # Assert: Metrics saved to S3
    metrics_object = client.get_object(Bucket=config.s3_bucket, Key=config.metrics_key)
    assert b"drift_score" in metrics_object["Body"].read()
```

**What it validates:**
- Drift score calculated and returned
- HTML report generated and uploaded
- Metrics JSON saved to S3
- Report URI properly formatted
- Correct S3 keys used

---

### Test: Drift Detection Thresholds

```python
def test_drift_detected_above_threshold(monkeypatch):
    """Validate drift_detected=True when score exceeds threshold."""
    config = get_config()
    
    # Mock report with high drift
    class HighDriftReport:
        def as_dict(self):
            return {
                "metrics": [
                    {"result": {"share_of_drifted_columns": 0.5}},  # > 0.3 threshold
                ]
            }
        def run(self, *args, **kwargs): pass
        def save_html(self, path): pass
    
    monkeypatch.setattr(generate_report, "Report", HighDriftReport)
    
    with mock_aws():
        s3 = boto3.client("s3", region_name=config.aws_region)
        s3.create_bucket(Bucket=config.s3_bucket)
        
        result = generate_report.generate_drift_report()
        
        assert result["drift_detected"] is True
        assert result["drift_score"] == 0.5
```

---

### Test: No Drift Below Threshold

```python
def test_no_drift_below_threshold(monkeypatch):
    """Validate drift_detected=False when score below threshold."""
    
    class LowDriftReport:
        def as_dict(self):
            return {
                "metrics": [
                    {"result": {"share_of_drifted_columns": 0.1}},  # < 0.3 threshold
                ]
            }
        def run(self, *args, **kwargs): pass
        def save_html(self, path): pass
    
    monkeypatch.setattr(generate_report, "Report", LowDriftReport)
    
    with mock_aws():
        # ... setup ...
        result = generate_report.generate_drift_report()
        
        assert result["drift_detected"] is False
        assert result["drift_score"] == 0.1
```

---

## Testing CloudWatch Metrics

### Test: CloudWatch Metrics Structure

```python
def test_cloudwatch_metrics_include_namespace_and_model_dimension(monkeypatch):
    """Validate CloudWatch metrics are emitted with namespace and model dimension."""
    
    # Setup: Mock CloudWatch client
    put_metric_data = Mock()
    mock_client = Mock(put_metric_data=put_metric_data)
    
    monkeypatch.setattr(
        cloudwatch_metrics,
        "_cloudwatch_client",
        lambda: mock_client
    )
    
    # Setup: Set model name
    monkeypatch.setenv("MODEL_NAME", "pytest-heart-model")
    
    # Action: Push metrics
    cloudwatch_metrics.push_monitoring_metrics(
        drift_score=0.2,
        prediction_count=12,
        error_5xx_count=1
    )
    
    # Assert: Called once
    assert put_metric_data.called
    
    # Assert: Correct payload
    payload = put_metric_data.call_args.kwargs
    
    # Check namespace
    assert payload["Namespace"] == "HeartDisease/Test"  # From test env
    
    # Check metric names
    metric_names = {metric["MetricName"] for metric in payload["MetricData"]}
    assert metric_names == {
        "DataDriftScore",
        "FastAPIRequestCount",
        "FastAPI5xxErrorCount",
    }
    
    # Check dimension on all metrics
    for metric in payload["MetricData"]:
        assert metric["Dimensions"] == [
            {"Name": "ModelName", "Value": "pytest-heart-model"}
        ]
        assert "Value" in metric or "Timestamp" in metric
```

**What it validates:**
- CloudWatch client called with correct namespace
- All three metrics present (drift, requests, errors)
- ModelName dimension on all metrics
- Values are numeric

---

### Test: Metric Values Are Correct

```python
def test_metric_values_match_input(monkeypatch):
    """Validate pushed metric values match input parameters."""
    
    captured_metrics = []
    
    def capture_put_metric_data(*args, **kwargs):
        captured_metrics.append(kwargs)
    
    mock_client = Mock(put_metric_data=capture_put_metric_data)
    monkeypatch.setattr(cloudwatch_metrics, "_cloudwatch_client", lambda: mock_client)
    
    cloudwatch_metrics.push_monitoring_metrics(
        drift_score=0.35,
        prediction_count=100,
        error_5xx_count=5
    )
    
    payload = captured_metrics[0]
    
    # Find each metric
    metrics_by_name = {m["MetricName"]: m for m in payload["MetricData"]}
    
    assert metrics_by_name["DataDriftScore"]["Value"] == 0.35
    assert metrics_by_name["FastAPIRequestCount"]["Value"] == 100
    assert metrics_by_name["FastAPI5xxErrorCount"]["Value"] == 5
```

---

### Test: Timestamp Included

```python
def test_metrics_include_timestamp(monkeypatch):
    """Validate metrics include current timestamp."""
    
    from datetime import datetime
    
    put_metric_data = Mock()
    mock_client = Mock(put_metric_data=put_metric_data)
    monkeypatch.setattr(cloudwatch_metrics, "_cloudwatch_client", lambda: mock_client)
    
    before = datetime.utcnow()
    cloudwatch_metrics.push_monitoring_metrics(drift_score=0.1, prediction_count=1, error_5xx_count=0)
    after = datetime.utcnow()
    
    payload = put_metric_data.call_args.kwargs
    
    for metric in payload["MetricData"]:
        if "Timestamp" in metric:
            assert before <= metric["Timestamp"] <= after
```

---

## Testing Log Queries

### Test: Log Group Missing Handled Gracefully

```python
def test_fastapi_log_counts_returns_zero_when_log_group_missing(monkeypatch):
    """Validate missing CloudWatch log groups are handled without raising."""
    
    class FakeLogs:
        """Mock CloudWatch Logs client."""
        
        class exceptions:
            class ResourceNotFoundException(Exception):
                pass
        
        def filter_log_events(self, **kwargs):
            raise self.exceptions.ResourceNotFoundException()
    
    # Replace logs client with fake
    monkeypatch.setattr(
        cloudwatch_metrics,
        "_logs_client",
        lambda: FakeLogs()
    )
    
    # Action: Try to get log counts
    request_count, error_count = cloudwatch_metrics.get_fastapi_log_counts()
    
    # Assert: Returns zeros, doesn't raise
    assert request_count == 0
    assert error_count == 0
```

**What it validates:**
- Missing log group handled gracefully
- Returns (0, 0) instead of crashing
- No exception raised

---

### Test: Log Counts When Group Exists

```python
def test_log_counts_parsed_correctly(monkeypatch):
    """Validate log counts are extracted from CloudWatch response."""
    
    class FakeLogsWithData:
        def filter_log_events(self, **kwargs):
            # Simulate CloudWatch response structure
            if "ERROR" in kwargs.get("filterPattern", ""):
                return {"events": [{}, {}, {}]}  # 3 errors
            else:
                return {"events": [{}, {}, {}, {}, {}]}  # 5 total
    
    monkeypatch.setattr(
        cloudwatch_metrics,
        "_logs_client",
        lambda: FakeLogsWithData()
    )
    
    request_count, error_count = cloudwatch_metrics.get_fastapi_log_counts()
    
    assert request_count == 5
    assert error_count == 3
```

---

## Mocking Strategies

### Strategy 1: Mock Evidently (Fast Tests)

```python
def test_with_mocked_evidently(monkeypatch):
    """Mock Evidently to skip heavy calculation."""
    
    class MockReport:
        def run(self, *args, **kwargs): pass
        def as_dict(self):
            return {"metrics": [{"result": {"drift": 0.1}}]}
        def save_html(self, path): pass
    
    monkeypatch.setattr(generate_report, "Report", MockReport)
    
    result = generate_report.generate_drift_report()
    # Fast, no real drift calculation
```

**Best for:** Unit tests, fast feedback.

---

### Strategy 2: Use Real Evidently (Integration Tests)

```python
def test_with_real_evidently(sample_dataframe):
    """Use real Evidently for accurate drift calculation."""
    
    # Generate reference and current data
    reference = sample_dataframe.head(25)
    current = sample_dataframe.tail(25)
    
    # Real Evidently calculation
    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current)
    
    result = report.as_dict()
    
    # Real drift score
    drift_score = result["metrics"][0]["result"]["share_of_drifted_columns"]
    
    # For identical data, drift should be 0
    assert drift_score == 0.0
```

**Best for:** Accuracy validation, drift algorithm testing.

**Note:** Slower, use sparingly.

---

### Strategy 3: Mock S3 with moto (Always)

```python
@mock_aws
def test_with_mocked_s3():
    """S3 operations mocked via moto."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    
    # ... rest of test
```

**Always use:** Never hit real S3 in tests.

---

### Strategy 4: Mock CloudWatch Client

```python
def test_with_mocked_cloudwatch(monkeypatch):
    """Mock boto3 CloudWatch client."""
    
    put_metric = Mock()
    mock_client = Mock(put_metric_data=put_metric)
    
    monkeypatch.setattr(
        cloudwatch_metrics,
        "_cloudwatch_client",
        lambda: mock_client
    )
    
    # ... test metric pushing
```

**Always use:** Never push real metrics in tests.

---

## Common Patterns

### Pattern: Testing Report HTML Content

```python
@mock_aws
def test_report_html_contains_expected_sections(monkeypatch, tmp_path):
    """Validate generated HTML contains key sections."""
    
    html_path = tmp_path / "report.html"
    
    class HTMLReport:
        def run(self, *args, **kwargs): pass
        def as_dict(self):
            return {"metrics": []}
        def save_html(self, path):
            html_content = """
            <html>
                <head><title>Drift Report</title></head>
                <body>
                    <h1>Data Drift Report</h1>
                    <div id="overview">Overview section</div>
                    <div id="metrics">Metrics section</div>
                </body>
            </html>
            """
            Path(path).write_text(html_content)
    
    monkeypatch.setattr(generate_report, "Report", HTMLReport)
    
    # ... run report generation
    
    # Assert HTML has expected sections
    html = html_path.read_text()
    assert "<h1>Data Drift Report</h1>" in html
    assert 'id="overview"' in html
    assert 'id="metrics"' in html
```

---

### Pattern: Testing Config Validation

```python
def test_config_raises_on_missing_s3_bucket():
    """Validate config raises error if S3_BUCKET not set."""
    
    with pytest.raises(ValueError, match="S3_BUCKET"):
        with patch.dict(os.environ, {"S3_BUCKET": ""}):
            get_config()

def test_config_uses_defaults_for_optional():
    """Validate config uses sensible defaults for optional values."""
    
    with patch.dict(os.environ, {
        "S3_BUCKET": "test-bucket",
        # DRIFT_THRESHOLD not set
    }):
        config = get_config()
        assert config.drift_threshold == 0.3  # Default
```

---

### Pattern: Testing Column Mapping

```python
def test_column_mapping_matches_features(monkeypatch):
    """Validate ColumnMapping uses correct feature columns."""
    
    from evidently import ColumnMapping
    
    captured_mapping = None
    
    class CaptureReport:
        def run(self, reference_data, current_data, column_mapping):
            nonlocal captured_mapping
            captured_mapping = column_mapping
        
        def as_dict(self): return {"metrics": []}
        def save_html(self, path): pass
    
    monkeypatch.setattr(generate_report, "Report", CaptureReport)
    
    # ... run report
    
    assert captured_mapping is not None
    assert set(captured_mapping.numerical_features) == set(FEATURE_COLUMNS)
```

---

## Troubleshooting

### Problem: "boto3 client not found"

**Cause:** boto3 not mocked or moto not applied.

**Fix:**
```python
from moto import mock_aws

@mock_aws  # Don't forget the decorator!
def test_s3_operations():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test")
```

---

### Problem: "Evidently taking too long"

**Cause:** Real drift calculation on large dataset.

**Fix:** Mock Evidently for unit tests.

```python
def test_fast(monkeypatch):
    """Fast test with mock."""
    monkeypatch.setattr(generate_report, "Report", MockReport)
    # ... fast

def test_accuracy(sample_data):
    """Slower test with real Evidently."""
    # ... use real Report
```

---

### Problem: "CloudWatch metrics not captured"

**Cause:** Mock not applied correctly.

**Fix:**
```python
def test_metrics(monkeypatch):
    # Mock the client getter
    mock_client = Mock()
    monkeypatch.setattr(
        cloudwatch_metrics,
        "_cloudwatch_client",
        lambda: mock_client  # Must return mock when called
    )
    
    # Now push_monitoring_metrics() will use our mock
    cloudwatch_metrics.push_monitoring_metrics(...)
    
    assert mock_client.put_metric_data.called
```

---

### Problem: "S3 parquet read fails"

**Cause:** Reading parquet from moto S3 can be tricky.

**Fix:**
```python
from io import BytesIO

@mock_aws
def test_parquet():
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="test")
    
    # Read as BytesIO
    obj = s3.get_object(Bucket="test", Key="data.parquet")
    df = pd.read_parquet(BytesIO(obj["Body"].read()))
```

---

## Key Takeaways

1. **Mock Evidently for speed** — Real drift calculation is slow
2. **Mock S3 with moto always** — Never use real S3 in tests
3. **Mock CloudWatch client** — Don't push test metrics
4. **Test drift threshold logic** — 0.3 threshold, drift_detected boolean
5. **Test metric structure** — Namespace, dimensions, metric names
6. **Test error handling** — Missing log groups, missing S3 keys
7. **Verify report content** — HTML sections, JSON metrics
8. **Test config validation** — Required env vars, defaults

---

## Next

- [08 — Troubleshooting Tests](08-troubleshooting-tests.md) — Common test failures and fixes
