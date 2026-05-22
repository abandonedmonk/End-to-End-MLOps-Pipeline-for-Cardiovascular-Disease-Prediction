# 02 — Mocking AWS Services

How to test AWS-dependent code without hitting real services using moto, monkeypatch, and local backends.

---

## Table of Contents

1. [Why Mock AWS?](#why-mock-aws)
2. [moto — AWS Service Mocking](#moto--aws-service-mocking)
3. [Mocking S3](#mocking-s3)
4. [Mocking CloudWatch](#mocking-cloudwatch)
5. [Mocking MLflow (SQLite Backend)](#mocking-mlflow-sqlite-backend)
6. [monkeypatch for boto3](#monkeypatch-for-boto3)
7. [Advanced Patterns](#advanced-patterns)
8. [Troubleshooting Mocks](#troubleshooting-mocks)

---

## Why Mock AWS?

### Problems with Real AWS in Tests

| Problem | Impact |
|---------|--------|
| **Requires credentials** | Tests fail without AWS access |
| **Network calls** | Slow, flaky tests |
| **Costs money** | S3 requests, CloudWatch logs |
| **Shared state** | Tests interfere with each other |
| **Cleanup required** | Leftover resources in AWS |
| **Can't run offline** | No testing on airplanes |
| **Security risk** | Accidental prod data exposure |

### Benefits of Mocking

| Benefit | How |
|---------|-----|
| **Fast** | Local in-memory operations |
| **Deterministic** | Same results every time |
| **Isolated** | Each test gets fresh state |
| **No credentials** | Works without AWS access |
| **Free** | Zero AWS costs |
| **Offline** | Test anywhere |
| **Safe** | No prod data risk |

---

## moto — AWS Service Mocking

**moto** = Python library that mocks AWS services.

### Installation

```bash
pip install moto>=5.0.0
```

### Basic Usage

```python
from moto import mock_aws
import boto3

@mock_aws
def test_s3_operations():
    """All boto3 calls are mocked within this decorator."""
    # Create S3 client
    s3 = boto3.client("s3", region_name="us-east-1")
    
    # Create bucket
    s3.create_bucket(Bucket="test-bucket")
    
    # Upload object
    s3.put_object(Bucket="test-bucket", Key="data.txt", Body=b"Hello")
    
    # Download object
    obj = s3.get_object(Bucket="test-bucket", Key="data.txt")
    assert obj["Body"].read() == b"Hello"
    
# No real AWS calls were made!
```

---

## Mocking S3

### Our Use Case: Data Loading

Production code (`data.py`):
```python
def _resolve_data_path(path: str) -> str:
    if path.startswith("s3://"):
        return _download_s3_file(path)
    return path  # Local path

def _download_s3_file(s3_uri: str) -> str:
    bucket, key = parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    local_path = f"{LOCAL_DATA_CACHE}/{key.replace('/', '_')}"
    s3.download_file(bucket, key, local_path)
    return local_path
```

Test with moto:
```python
from moto import mock_aws
import boto3
import pandas as pd
from heart_disease_prediction import data

@mock_aws
def test_s3_data_loading_downloads_to_cache(sample_data_file, monkeypatch, tmp_path):
    """Validate s3:// paths trigger a boto3 download into the local cache."""
    # Setup: Create mock S3 bucket
    bucket = "test-heart-disease-bucket"
    key = "data/raw/heart.csv"
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.create_bucket(Bucket=bucket)
    
    # Setup: Upload test file to mock S3
    s3_client.upload_file(str(sample_data_file), bucket, key)
    
    # Setup: Set cache directory
    monkeypatch.setattr(data, "LOCAL_DATA_CACHE", tmp_path / "cache")
    
    # Action: Call the function with s3:// URL
    resolved = data._resolve_data_path(f"s3://{bucket}/{key}")
    
    # Assert: File was downloaded
    assert Path(resolved).exists()
    assert Path(resolved).parent == tmp_path / "cache"
    
    # Assert: File content is correct
    downloaded_df = pd.read_csv(resolved, header=None)
    assert len(downloaded_df) > 0
```

---

### Pattern: Testing S3 Uploads

Production code:
```python
def save_to_s3(local_path: str, s3_uri: str) -> str:
    """Upload local file to S3."""
    bucket, key = parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    s3.upload_file(local_path, bucket, key)
    return s3_uri
```

Test:
```python
@mock_aws
def test_save_to_s3_uploads_file(tmp_path):
    """Validate file uploads to S3 correctly."""
    # Setup: Create local file
    local_file = tmp_path / "model.pkl"
    local_file.write_bytes(b"fake model")
    
    # Setup: Create mock bucket
    bucket = "models-bucket"
    key = "models/v1/model.pkl"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=bucket)
    
    # Action: Upload
    result = save_to_s3(str(local_file), f"s3://{bucket}/{key}")
    
    # Assert: File in S3
    obj = s3.get_object(Bucket=bucket, Key=key)
    assert obj["Body"].read() == b"fake model"
    assert result == f"s3://{bucket}/{key}"
```

---

### Pattern: Testing Parquet in S3

```python
@mock_aws
def test_save_reference_data_creates_parquet(sample_dataframe):
    """Validate reference data saved as parquet to S3."""
    bucket = "monitoring-bucket"
    key = "data/reference/reference_data.parquet"
    
    # Create bucket
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=bucket)
    
    # Save DataFrame
    from io import BytesIO
    buffer = BytesIO()
    sample_dataframe.to_parquet(buffer, index=False)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue()
    )
    
    # Read back
    obj = s3.get_object(Bucket=bucket, Key=key)
    read_df = pd.read_parquet(BytesIO(obj["Body"].read()))
    
    assert len(read_df) == len(sample_dataframe)
    assert list(read_df.columns) == list(sample_dataframe.columns)
```

---

## Mocking CloudWatch

### Use Case: Metrics Publishing

Production code (`monitoring/cloudwatch_metrics.py`):
```python
def push_monitoring_metrics(
    drift_score: float,
    prediction_count: int,
    error_5xx_count: int
) -> None:
    """Push metrics to CloudWatch."""
    client = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION"))
    client.put_metric_data(
        Namespace="HeartDisease/MLOps",
        MetricData=[
            {
                "MetricName": "DataDriftScore",
                "Value": drift_score,
                "Dimensions": [{"Name": "ModelName", "Value": os.getenv("MODEL_NAME")}]
            },
            # ... more metrics
        ]
    )
```

Test with mocked client:
```python
from unittest.mock import Mock

def test_cloudwatch_metrics_include_namespace_and_model_dimension(monkeypatch):
    """Validate CloudWatch metrics are emitted with namespace and model dimension."""
    # Setup: Mock the CloudWatch client
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
    
    # Assert: Client was called
    assert put_metric_data.called
    
    # Assert: Correct namespace
    call_kwargs = put_metric_data.call_args.kwargs
    assert call_kwargs["Namespace"] == "HeartDisease/Test"  # From env
    
    # Assert: Correct metric names
    metric_names = {m["MetricName"] for m in call_kwargs["MetricData"]}
    assert metric_names == {"DataDriftScore", "FastAPIRequestCount", "FastAPI5xxErrorCount"}
    
    # Assert: Model name dimension
    for metric in call_kwargs["MetricData"]:
        assert metric["Dimensions"] == [{"Name": "ModelName", "Value": "pytest-heart-model"}]
```

---

### Pattern: Testing Log Queries

```python
def test_fastapi_log_counts_returns_zero_when_log_group_missing(monkeypatch):
    """Validate missing CloudWatch log groups are handled gracefully."""
    
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
    
    # Assert: Returns zeros, no exception
    assert request_count == 0
    assert error_count == 0
```

---

## Mocking MLflow (SQLite Backend)

MLflow uses HTTP API or file store. For testing, use SQLite backend.

### Fixture Pattern

```python
@pytest.fixture
def mock_mlflow(tmp_path):
    """Create an isolated local MLflow tracking store."""
    # SQLite database file
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    
    # Local artifact directory
    artifact_root = tmp_path / "mlartifacts"
    artifact_root.mkdir()
    
    # Configure MLflow
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("pytest-heart-disease")
    
    yield {
        "tracking_uri": tracking_uri,
        "artifact_root": f"file://{artifact_root}"
    }
    
    # Cleanup: End any active run
    mlflow.end_run()
```

---

### Test: Logging to MLflow

```python
def test_train_model_logs_metrics_and_artifacts(prepared_data, mock_mlflow):
    """Validate training logs accuracy, precision, recall, f1, and model artifacts."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    # Setup: Config with mock MLflow
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "mlflow_artifact_root": mock_mlflow["artifact_root"],
        "experiment_name": "pytest-heart-disease",
        "model_name": "pytest-heart-disease-model",
    }
    
    # Action: Train models
    best_model, best_pipeline, paths = train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config=config
    )
    
    # Assert: Query local MLflow
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-heart-disease")
    runs = client.search_runs([experiment.experiment_id])
    
    # Check runs were created
    assert len(runs) == 4  # 4 models
    
    # Check metrics
    for run in runs:
        assert 0 <= run.data.metrics["accuracy"] <= 1
        assert {"precision", "recall", "f1_score"}.issubset(run.data.metrics)
        assert client.list_artifacts(run.info.run_id, "model")
```

---

### Test: Model Registration

```python
def test_register_model_finds_best_run_and_sets_champion(mock_mlflow, dummy_model):
    """Validate registration picks the highest accuracy run and assigns champion alias."""
    experiment_name = "pytest-register-best"
    model_name = "pytest-registered-model"
    
    # Setup: Log two runs with different accuracies
    mlflow.set_experiment(experiment_name)
    
    with mlflow.start_run():
        mlflow.log_metric("accuracy", 0.55)
        mlflow.sklearn.log_model(dummy_model, "model")
    
    with mlflow.start_run() as run:
        mlflow.log_metric("accuracy", 0.91)
        mlflow.sklearn.log_model(dummy_model, "model")
        best_run_id = run.info.run_id
    
    # Action: Register best model
    result = register_model.fn(
        dummy_model,
        {
            "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
            "experiment_name": experiment_name,
            "model_name": model_name,
        },
    )
    
    # Assert: Model registered
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    champion = client.get_model_version_by_alias(model_name, "champion")
    
    assert result["model_uri"] == f"models:/{model_name}@champion"
    assert champion.run_id == best_run_id  # Correct run selected
```

---

### Test: Loading from Registry

```python
def _register_model_version(mock_mlflow, dummy_model, model_name):
    """Helper to register a model and return version info."""
    mlflow.set_tracking_uri(mock_mlflow["tracking_uri"])
    mlflow.set_experiment("pytest-load-model")
    
    with mlflow.start_run() as run:
        mlflow.sklearn.log_model(dummy_model, "model")
    
    return mlflow.register_model(
        f"runs:/{run.info.run_id}/model",
        model_name
    )

def test_load_champion_model_by_alias(mock_mlflow, dummy_model):
    """Validate champion alias loading returns a model with predict support."""
    model_name = "pytest-load-champion"
    
    # Setup: Register and alias
    result = _register_model_version(mock_mlflow, dummy_model, model_name)
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    client.set_registered_model_alias(model_name, "champion", result.version)
    
    # Action: Load champion
    loaded = load_champion_model({
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "model_name": model_name
    })
    
    # Assert: Loaded correctly
    assert isinstance(loaded, Pipeline)
    assert hasattr(loaded, "predict")
```

---

## monkeypatch for boto3

### Pattern: Replace boto3.client()

```python
def test_without_any_aws_calls(monkeypatch):
    """Completely bypass boto3."""
    
    # Track calls
    calls = []
    
    def mock_client(service, **kwargs):
        calls.append(service)
        return Mock()  # Fake client
    
    monkeypatch.setattr("boto3.client", mock_client)
    
    # Now any boto3.client() call uses our mock
    from heart_disease_prediction import data
    data._download_s3_file("s3://bucket/key")  # Uses mock_client
    
    assert "s3" in calls
```

---

### Pattern: Prevent AWS Calls

```python
def test_local_data_loading_bypasses_s3(sample_data_file, monkeypatch):
    """Validate local paths are returned directly without calling boto3."""
    called = False
    
    def fail_client(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("boto3 should not be called for local files")
    
    monkeypatch.setattr(data.boto3, "client", fail_client)
    
    # Action: Local path (should not trigger boto3)
    result = data._resolve_data_path(str(sample_data_file))
    
    # Assert: boto3 was NOT called
    assert called is False
    assert result == str(sample_data_file)
```

---

## Advanced Patterns

### Pattern: Context Manager for Multiple Services

```python
from contextlib import contextmanager

@contextmanager
def mock_all_aws():
    """Mock multiple AWS services at once."""
    with mock_aws():
        # Setup all mock resources
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        
        cw = boto3.client("cloudwatch", region_name="us-east-1")
        
        yield {
            "s3": s3,
            "cloudwatch": cw
        }

def test_full_pipeline_with_aws(mock_mlflow):
    with mock_all_aws() as aws:
        # Run full pipeline
        # All AWS calls use mocks
        pass
```

---

### Pattern: Moto with pytest Fixtures

```python
@pytest.fixture
def mock_s3_bucket():
    """Provide a pre-configured mock S3 bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-bucket"
        s3.create_bucket(Bucket=bucket_name)
        yield s3, bucket_name
        # Cleanup automatic when context exits

def test_with_mock_bucket(mock_s3_bucket):
    s3, bucket = mock_s3_bucket
    
    s3.put_object(Bucket=bucket, Key="test.txt", Body=b"data")
    obj = s3.get_object(Bucket=bucket, Key="test.txt")
    assert obj["Body"].read() == b"data"
```

---

### Pattern: Conditional Mocking

```python
def test_uses_real_aws_in_ci_but_mock_locally():
    """Rare, but possible."""
    import os
    
    if os.getenv("CI"):
        # Use real AWS (careful!)
        pass
    else:
        # Use mocks
        with mock_aws():
            pass
```

**Note:** Generally avoid real AWS in tests. Use mocks always.

---

## Troubleshooting Mocks

### Problem: Mock not working

```python
# Common mistake: Import module before patching
import boto3  # Too late!

@mock_aws
def test_s3():
    s3 = boto3.client("s3")  # This boto3 is already imported, might not be mocked
```

**Fix:** Import inside test or after mock setup.

```python
@mock_aws
def test_s3():
    import boto3  # Import here
    s3 = boto3.client("s3")
```

---

### Problem: Moto version incompatibility

```python
# Error: AttributeError: 'NoneType' has no attribute 'put_object'
```

**Fix:** Use `mock_aws` (moto 5.x) not `mock_s3` (moto 4.x).

```python
from moto import mock_aws  # Correct for moto 5.x

@mock_aws
def test():
    pass
```

---

### Problem: Tests pass individually but fail together

**Cause:** Shared state between tests.

**Fix:** Use `tmp_path` for all file paths.

```python
# Bad: Shared file path
TEST_FILE = "/tmp/test_data.csv"

# Good: Unique path per test
def test_something(tmp_path):
    test_file = tmp_path / "data.csv"
```

---

### Problem: MLflow state leaks between tests

**Fix:** Use fresh SQLite DB per test.

```python
@pytest.fixture
def fresh_mlflow(tmp_path):
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(tracking_uri)
    yield tracking_uri
    mlflow.end_run()  # Cleanup
```

---

## Key Takeaways

1. **moto mocks AWS services** — S3, CloudWatch, and many others
2. **Use `@mock_aws` decorator** — Wraps test in mock context
3. **SQLite for MLflow** — Local backend, no server needed
4. **monkeypatch for fine control** — Replace specific functions
5. **tmp_path for isolation** — Fresh temp directory per test
6. **No real AWS calls in tests** — Fast, free, reliable
7. **Assert on mock behavior** — Verify calls were made correctly

---

## Next

- [03 — Testing Data Pipelines](03-testing-data-pipelines.md) — Data loading, preprocessing, train/test split
