# Phase 8 Overview — Comprehensive Testing

Replacing placeholder tests with a production-quality test suite.

---

## The Problem We Solved

**Before Phase 8:**
```python
# tests/test_placeholder.py
def test_placeholder():
    assert False  # TODO: implement real tests
```

**Problems with placeholder tests:**
1. CI/CD pipeline doesn't validate code correctness
2. Bugs reach production undetected
3. Refactoring is risky (no safety net)
4. Code review relies on manual inspection
5. No documentation of expected behavior

**After Phase 8:**
- 8 test files, 400+ lines of test code
- 80%+ code coverage
- All external services mocked
- Tests run in ~30 seconds
- CI blocks PRs on test failures

---

## What We Built

### Test File Organization

```
tests/
├── __init__.py                    # Package marker
├── conftest.py                    # Shared fixtures (auto-imported)
├── test_data.py                   # Data loading & preprocessing (6 tests)
├── test_train.py                  # Model training (4 tests)
├── test_register.py               # MLflow registration (3 tests)
├── test_load_model.py             # Model loading (4 tests)
├── test_api.py                    # FastAPI endpoints (5 tests)
├── test_prefect_flow.py           # Pipeline orchestration (5 tests)
└── test_monitoring.py             # Drift detection (4 tests)
```

**Total: 31 test functions covering all critical paths.**

---

## Core Testing Philosophy

### 1. **Mock External Services**

Never hit real infrastructure in tests:

| Service | Production | Test |
|---------|-----------|------|
| MLflow | `http://32.196.26.238:5000` | `sqlite:///tmp/mlflow.db` |
| S3 | `s3://heart-disease-mlops-*` | moto mock |
| RDS | PostgreSQL | SQLite (via MLflow) |
| FastAPI | Running on EC2 | TestClient (in-memory) |
| Prefect | Prefect Cloud | Local flow run |

**Benefits:**
- Tests run offline
- No AWS credentials needed
- No infrastructure costs
- Deterministic results
- Fast execution (< 1s per test)

---

### 2. **Test Real Behavior, Not Implementation**

```python
# Good: Tests behavior (what it does)
def test_load_data_returns_expected_schema():
    df = data.get_data.fn(str(raw_data_path))
    assert df.shape == (303, 14)
    assert list(df.columns) == EXPECTED_COLUMNS

# Bad: Tests implementation (how it does it)
def test_bad_uses_pandas_read_csv(monkeypatch):
    read_csv_called = False
    def track_read(*args, **kwargs):
        nonlocal read_csv_called
        read_csv_called = True
        return pd.DataFrame()
    monkeypatch.setattr(pd, "read_csv", track_read)
    data.get_data.fn("/path")
    assert read_csv_called  # Brittle! Implementation can change
```

---

### 3. **Use Fixtures for Reusable Setup**

```python
# conftest.py
@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    """Every test gets fresh, safe environment."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    # ... all other env vars
```

**Why `autouse=True`:** No test can accidentally use production endpoints.

---

## Key Fixtures

### Mock MLflow (SQLite Backend)

```python
@pytest.fixture
def mock_mlflow(tmp_path):
    """Create an isolated local MLflow tracking store."""
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("pytest-heart-disease")
    yield {"tracking_uri": tracking_uri, "artifact_root": f"file://{artifact_root}"}
    mlflow.end_run()
```

**Usage:**
```python
def test_train_logs_metrics(mock_mlflow):
    # All MLflow calls go to local SQLite, not production server
    train_model(...)
    runs = mlflow.search_runs()
    assert len(runs) > 0
```

---

### Sample Data (Cleveland Dataset)

```python
@pytest.fixture
def sample_dataframe(full_dataframe):
    """Return a deterministic, cleaned sample."""
    df = full_dataframe.loc[
        (full_dataframe["ca"] != "?") & (full_dataframe["thal"] != "?")
    ].head(50)
    return df.copy()
```

**Why real data:** Tests validate actual schema, not random columns.

---

### Dummy Model (No Training)

```python
class DummyHeartModel(BaseEstimator, ClassifierMixin):
    """Fast, deterministic classifier for API/registry tests."""
    classes_ = np.array([0, 1])
    
    def predict(self, X):
        return np.ones(len(X), dtype=int)
    
    def predict_proba(self, X):
        return np.tile(np.array([[0.2, 0.8]]), (len(X), 1))

@pytest.fixture
def dummy_model():
    return Pipeline([("classifier", DummyHeartModel())])
```

**Why:** Tests model serving logic without 30-second training time.

---

## Testing Patterns by Component

### Data Pipeline (`test_data.py`)

| Test | Validates |
|------|-----------|
| `test_load_data_returns_expected_schema` | Shape (303, 14), columns, binary target |
| `test_prepare_data_splits_and_binarizes_target` | 80/20 split, train=40/test=10 on sample |
| `test_preprocessor_handles_numeric_and_categorical` | ColumnTransformer with passthrough + OneHot |
| `test_s3_data_loading_downloads_to_cache` | moto S3 mock, download logic |
| `test_local_data_loading_bypasses_s3` | No boto3 calls for local paths |
| `test_missing_local_file_raises_clear_error` | FileNotFoundError with clear message |

---

### ML Training (`test_train.py`)

| Test | Validates |
|------|-----------|
| `test_all_configured_models_train_without_error` | LR, RF, GradientBoosting, DecisionTree all fit |
| `test_train_model_logs_metrics_and_artifacts` | accuracy, precision, recall, f1 in MLflow |
| `test_best_model_selection_matches_highest_accuracy` | Highest accuracy run returned |
| `test_cross_validation_scores_are_reasonable` | CV scores > 0.5 baseline |

---

### Model Registration (`test_register.py`)

| Test | Validates |
|------|-----------|
| `test_register_model_finds_best_run_and_sets_champion` | Highest accuracy registered, champion alias set |
| `test_register_model_raises_when_no_runs_found` | Clear error for empty experiment |
| `test_register_model_propagates_mlflow_connection_failure` | MLflow errors bubble up |

---

### Model Loading (`test_load_model.py`)

| Test | Validates |
|------|-----------|
| `test_load_champion_model_by_alias` | Loads @champion, returns Pipeline |
| `test_load_champion_model_falls_back_to_production` | Fallback to Production stage |
| `test_load_champion_model_raises_when_missing` | Clear error if no model found |
| `test_loaded_model_can_predict_binary_values` | Predictions are 0/1 values |

---

### FastAPI (`test_api.py`)

**Key technique:** `TestClient` from FastAPI, no server needed.

| Test | Validates |
|------|-----------|
| `test_health_endpoint_reports_loaded_model` | `/health` returns ok + model_loaded=true |
| `test_health_endpoint_reports_unloaded_model` | Still works when MLflow fails |
| `test_predict_endpoint_returns_prediction_and_probability` | Binary prediction + 0-1 probability |
| `test_predict_endpoint_rejects_missing_fields` | 422 error for incomplete payload |
| `test_predict_endpoint_rejects_wrong_types` | 422 error for non-numeric values |

---

### Prefect Flows (`test_prefect_flow.py`)

| Test | Validates |
|------|-----------|
| `test_load_data_task_returns_dataframe` | Task returns DataFrame with hd column |
| `test_train_models_task_returns_best_model_info` | Returns model, pipeline, paths dict |
| `test_register_model_task_succeeds` | Returns paths with model_uri |
| `test_flow_composition_can_be_built` | Flow has correct name and is callable |
| `test_full_pipeline_runs_with_mocked_external_services` | Full flow runs with all mocks |

---

### Monitoring (`test_monitoring.py`)

| Test | Validates |
|------|-----------|
| `test_reference_data_creation_saves_expected_columns` | Reference parquet saved to S3 with right columns |
| `test_drift_report_generation_uploads_report_and_metrics` | HTML report + JSON metrics uploaded |
| `test_cloudwatch_metrics_include_namespace_and_model_dimension` | Metrics have right namespace + ModelName dimension |
| `test_fastapi_log_counts_returns_zero_when_log_group_missing` | Missing log group handled gracefully |

---

## CI/CD Integration

### Updated `.github/workflows/ci.yml`

```yaml
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      # ... linting steps ...
      
      - name: Install test dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest-cov pytest-asyncio httpx moto
      
      - name: Run test suite
        run: |
          pytest --cov=heart_disease_prediction \
                 --cov=monitoring \
                 --cov=api \
                 --cov-report=term-missing \
                 --cov-fail-under=80 \
                 tests/
```

**Key changes:**
1. Added `pytest-cov` for coverage
2. Added `moto` for AWS mocking
3. Added `httpx` for TestClient
4. Coverage fails build if < 80%

---

## Coverage Strategy

### What's Covered (Target: 80%+)

| Module | Coverage Focus |
|--------|---------------|
| `heart_disease_prediction/data.py` | Data loading, preprocessing, S3 handling |
| `heart_disease_prediction/train.py` | Model training, metrics, selection |
| `heart_disease_prediction/register.py` | MLflow registration |
| `heart_disease_prediction/load_model.py` | Model loading from registry |
| `heart_disease_prediction/prefect_flow.py` | Flow composition, task orchestration |
| `api/main.py` | Endpoints, health, prediction |
| `monitoring/` | Drift detection, CloudWatch metrics |

### What's Not Covered (Acceptable)

| Excluded | Reason |
|----------|--------|
| `notebooks/` | Exploration code, not production |
| `infra/` | Terraform, tested by `terraform validate` |
| `docs/` | Documentation, not code |
| `.github/workflows/` | CI config, validated by GitHub |
| UI code | Swagger UI is auto-generated |

---

## Mocking Techniques

### 1. **pytest monkeypatch**

Replace functions/attributes temporarily:

```python
def test_with_monkeypatch(monkeypatch):
    # Replace a function
    def fake_train(*args, **kwargs):
        return "model", "pipeline", {}
    
    monkeypatch.setattr(prefect_flow.train_model, "fn", fake_train)
    
    # Now prefect_flow.train_model.fn() returns our fake
    result = prefect_flow.train_model.fn()
    assert result == ("model", "pipeline", {})
```

---

### 2. **moto (AWS Mocking)**

Mock S3, CloudWatch, etc.:

```python
from moto import mock_aws

@mock_aws
def test_s3_operations():
    # Create mock S3 bucket
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    
    # Upload file
    client.upload_file("/tmp/data.csv", "test-bucket", "data.csv")
    
    # Download file
    obj = client.get_object(Bucket="test-bucket", Key="data.csv")
    assert obj["Body"].read()
```

**Benefits:**
- No AWS credentials needed
- No network calls
- Deterministic behavior
- Tests run offline

---

### 3. **Temporary SQLite for MLflow**

```python
@pytest.fixture
def mock_mlflow(tmp_path):
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(tracking_uri)
    yield tracking_uri
    mlflow.end_run()

def test_mlflow_logging(mock_mlflow):
    with mlflow.start_run():
        mlflow.log_metric("accuracy", 0.95)
    
    # Query local SQLite
    client = MlflowClient(tracking_uri=mock_mlflow)
    runs = client.search_runs(["0"])
    assert runs[0].data.metrics["accuracy"] == 0.95
```

---

### 4. **FastAPI TestClient**

```python
from fastapi.testclient import TestClient

def test_api_without_server(monkeypatch, dummy_model):
    # Mock model loading
    monkeypatch.setattr(mlflow.pyfunc, "load_model", lambda uri: dummy_model)
    
    # Import fresh (to pick up monkeypatch)
    from api.main import app
    client = TestClient(app)
    
    # Test endpoints
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model_loaded"] is True
```

**Key:** `TestClient` runs FastAPI in-process, no server needed.

---

## Production Code Changes

To make code testable, some production changes were needed:

### 1. **Injectable Configuration**

```python
# Before (hard to test)
def train_model(X_train, X_test, y_train, y_test, preprocessor):
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))  # Global env

# After (testable)
def train_model(X_train, X_test, y_train, y_test, preprocessor, config=None):
    config = config or {}  # Allow injection
    mlflow.set_tracking_uri(config.get("mlflow_tracking_uri") or os.getenv(...))
```

---

### 2. **Clear Error Messages**

```python
# Before (vague)
def register_model(model, config):
    runs = client.search_runs(...)
    if not runs:
        raise Exception("Failed")  # What failed?

# After (clear)
def register_model(model, config):
    runs = client.search_runs(...)
    if not runs:
        raise ValueError(f"No MLflow runs found in experiment '{experiment_name}'")
```

---

### 3. **Return Values for Verification**

```python
# Before (side effects only)
def train_model(...):
    # Trains and logs, returns nothing
    pass

# After (returns data for tests)
def train_model(...):
    # ... training logic ...
    return best_model, best_pipeline, paths  # Testable!
```

---

## Common Testing Mistakes

### ❌ Mistake 1: Testing Implementation Details

```python
# Bad: Tests that pandas was called
def test_uses_pandas(monkeypatch):
    called = False
    def track(*args, **kwargs):
        nonlocal called
        called = True
        return pd.DataFrame()
    monkeypatch.setattr(pd, "read_csv", track)
    load_data()
    assert called  # Breaks if we switch to polars!
```

**Fix:** Test behavior (output), not implementation (library calls).

---

### ❌ Mistake 2: Shared State Between Tests

```python
# Bad: Global state
MLFLOW_URI = "sqlite:///test.db"  # Shared!

def test_a():
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.log_metric("x", 1)  # Affects test_b!

def test_b():
    runs = mlflow.search_runs()  # Sees test_a's runs!
```

**Fix:** Use `tmp_path` fixture (fresh per test).

---

### ❌ Mistake 3: Slow Tests

```python
# Bad: 30 seconds per test
def test_real_training():
    model = RandomForestClassifier(n_estimators=1000)
    model.fit(X_train, y_train)  # Slow!
```

**Fix:** Use dummy models for serving tests, small datasets for training tests.

---

### ❌ Mistake 4: Non-Deterministic Tests

```python
# Bad: Random results
model = RandomForestClassifier()  # Random state not set!
predictions = model.predict(X_test)
assert predictions[0] == 1  # Might be 0!
```

**Fix:** Set `random_state=42` everywhere.

---

### ❌ Mistake 5: Tests That Hit Production

```python
# Bad: Hits real EC2!
def test_api():
    response = requests.get("http://32.196.26.238:8000/health")
    assert response.status_code == 200
```

**Fix:** Use mocks and TestClient.

---

## Test Debugging Tips

### See print statements:
```bash
pytest tests/test_api.py -v -s
```

### Stop on first failure:
```bash
pytest tests/ -x
```

### Run specific test:
```bash
pytest tests/test_data.py::test_load_data_returns_expected_schema -v
```

### Debug with pdb:
```python
def test_something():
    import pdb; pdb.set_trace()  # Breakpoint
    assert value == expected
```

Run with:
```bash
pytest tests/test_something.py --pdb
```

### Full traceback:
```bash
pytest tests/ --tb=long
```

---

## Verification Checklist

After Phase 8, verify:

- [ ] `pytest tests/` passes (0 failures)
- [ ] `pytest --cov-fail-under=80` passes
- [ ] `grep -r "assert False" tests/` returns nothing
- [ ] All 8 test files exist
- [ ] Tests run without AWS credentials
- [ ] Tests run without MLflow server
- [ ] Tests run without Docker
- [ ] CI workflow passes

---

## Documentation Files

| File | Content |
|------|---------|
| [01 — pytest Fundamentals](01-pytest-fundamentals.md) | Fixtures, conftest.py, tmp_path |
| [02 — Mocking AWS Services](02-mocking-aws-services.md) | moto, boto3, MLflow mocking |
| [03 — Testing Data Pipelines](03-testing-data-pipelines.md) | Data loading, preprocessing |
| [04 — Testing ML Training](04-testing-ml-training.md) | Model training, metrics, selection |
| [05 — Testing API with TestClient](05-testing-api-with-testclient.md) | FastAPI testing |
| [06 — Testing Prefect Flows](06-testing-prefect-flows.md) | Flow composition, orchestration |
| [07 — Testing Monitoring](07-testing-monitoring.md) | Drift detection, CloudWatch |
| [08 — Troubleshooting Tests](08-troubleshooting-tests.md) | Common issues and fixes |

---

## Next Phase

- **Phase 9:** Security hardening
  - Purge `.env` from git history
  - Rotate AWS access keys
  - Set up pre-commit hooks for secrets

---

## Key Takeaways

1. **Mock external services** — No live AWS/MLflow in tests
2. **Use fixtures** — Reusable setup, automatic cleanup
3. **Test behavior, not implementation** — Resilient to refactoring
4. **Keep tests fast** — <1s each, full suite <30s
5. **Deterministic tests** — Fixed random seeds
6. **Coverage target 80%+** — Critical paths covered
7. **CI integration** — Block PRs on test failures

Testing doesn't guarantee bug-free code, but it catches regressions, documents expected behavior, and enables confident refactoring.
