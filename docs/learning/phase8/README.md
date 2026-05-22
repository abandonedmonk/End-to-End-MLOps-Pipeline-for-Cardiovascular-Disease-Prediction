# Phase 8 — Comprehensive Testing with pytest

Complete test suite replacing placeholder tests with real, comprehensive coverage for ML pipelines.

---

## What Was Implemented

Phase 8 transformed testing from a single `assert False` placeholder into a comprehensive test suite covering:

| Test File | Purpose | Coverage |
|-----------|---------|----------|
| `tests/conftest.py` | Shared fixtures, mocks, and utilities | Base infrastructure |
| `tests/test_data.py` | Data loading, preprocessing, S3 handling | Data pipeline |
| `tests/test_train.py` | Model training, metrics logging, best model selection | Training logic |
| `tests/test_register.py` | MLflow model registration and alias management | Registry |
| `tests/test_load_model.py` | Loading champion/production models from MLflow | Model serving |
| `tests/test_api.py` | FastAPI endpoints without running server | API layer |
| `tests/test_prefect_flow.py` | Prefect flow composition and orchestration | Pipeline orchestration |
| `tests/test_monitoring.py` | Drift detection, CloudWatch metrics, S3 reports | Monitoring |

**Total:** ~400+ lines of test code, 80%+ coverage target, zero external AWS dependencies.

---

## Key Features

### 1. **No Live Services Required**

All tests run locally without:
- Running MLflow server
- AWS credentials
- S3 buckets
- RDS database
- Docker containers
- Running FastAPI server

**How:** Comprehensive mocking with `moto` (AWS), `monkeypatch` (functions), and temporary SQLite (MLflow).

### 2. **Shared Fixtures in conftest.py**

```python
@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    """Provide safe environment variables so tests never target live services."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    # ... all env vars set to test-safe values
```

**Why `autouse=True`:** Every test gets fresh, isolated environment automatically.

### 3. **Deterministic Mock Data**

```python
@pytest.fixture
def sample_dataframe(full_dataframe):
    """Return a deterministic, cleaned sample with realistic heart-disease columns."""
    df = full_dataframe.loc[
        (full_dataframe["ca"] != "?") & (full_dataframe["thal"] != "?")
    ].head(50)
    return df.copy()
```

**Why:** Tests use real Cleveland dataset schema, not random numbers.

### 4. **Dummy sklearn Models**

```python
class DummyHeartModel(BaseEstimator, ClassifierMixin):
    """Small sklearn-compatible classifier used by API and registry tests."""
    classes_ = np.array([0, 1])
    
    def predict(self, X):
        return np.ones(len(X), dtype=int)
    
    def predict_proba(self, X):
        return np.tile(np.array([[0.2, 0.8]]), (len(X), 1))
```

**Why:** Fast, deterministic, no training time needed.

---

## Quick Start

```bash
# Run all tests
pytest tests/

# Run with coverage (CI command)
pytest --cov=heart_disease_prediction --cov=monitoring --cov=api \
  --cov-report=term-missing --cov-fail-under=80 tests/

# Run specific test file
pytest tests/test_data.py -v

# Run specific test
pytest tests/test_api.py::test_health_endpoint_reports_loaded_model -v

# Run with warnings visible
pytest tests/ -W always
```

---

## Documentation Guide

| File | Topic |
|------|-------|
| [Phase 8 Overview](phase8-overview.md) | High-level summary, test philosophy |
| [01 — pytest Fundamentals](01-pytest-fundamentals.md) | Fixtures, conftest.py, tmp_path, monkeypatch |
| [02 — Mocking AWS Services](02-mocking-aws-services.md) | moto for S3, mocking MLflow, boto3 patching |
| [03 — Testing Data Pipelines](03-testing-data-pipelines.md) | Data loading, preprocessing, train/test split |
| [04 — Testing ML Training](04-testing-ml-training.md) | Model training, metrics, cross-validation |
| [05 — Testing API with TestClient](05-testing-api-with-testclient.md) | FastAPI testing without running server |
| [06 — Testing Prefect Flows](06-testing-prefect-flows.md) | Flow composition, task mocking, orchestration |
| [07 — Testing Monitoring](07-testing-monitoring.md) | Evidently drift, CloudWatch metrics, S3 uploads |
| [08 — Troubleshooting Tests](08-troubleshooting-tests.md) | Common test failures and fixes |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Test Suite                               │
├─────────────────────────────────────────────────────────────────┤
│  conftest.py (fixtures)                                          │
│  ├── test_environment (autouse=True)  → Safe env vars         │
│  ├── mock_mlflow                       → SQLite backend         │
│  ├── sample_dataframe                  → Cleveland dataset      │
│  ├── dummy_model                       → Sklearn pipeline       │
│  └── import_fresh                      → Clean module import    │
├─────────────────────────────────────────────────────────────────┤
│  Test Files                                                      │
│  ├── test_data.py                      → Data pipeline          │
│  ├── test_train.py                     → Model training         │
│  ├── test_register.py                  → MLflow registry        │
│  ├── test_load_model.py                → Model loading          │
│  ├── test_api.py                       → FastAPI endpoints      │
│  ├── test_prefect_flow.py              → Orchestration          │
│  └── test_monitoring.py                → Drift & metrics        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Test Principles

### 1. **Unit Tests > Integration Tests**

Test functions in isolation, mock external services:

```python
# Good: Mock MLflow
@mock_aws
def test_s3_data_loading():
    # S3 is mocked, no real AWS calls
    pass

# Bad: Hits real services
def test_bad_hits_production():
    response = requests.get("http://32.196.26.238:8000/predict")  # DON'T DO THIS
```

### 2. **Deterministic Tests**

```python
# Good: Fixed random state
RandomForestClassifier(n_estimators=10, random_state=42)

# Bad: Non-deterministic
RandomForestClassifier()  # Different results each run
```

### 3. **Fast Tests**

Target: <1 second per test, <30 seconds for full suite.

```python
# Good: Dummy model, no training
@pytest.fixture
def dummy_model():
    return Pipeline([("classifier", DummyHeartModel())])

# Bad: Trains real model (slow)
def test_bad_slow():
    model = RandomForestClassifier(n_estimators=1000)  # Too slow!
    model.fit(X_train, y_train)
```

### 4. **Isolated Tests**

Each test gets fresh state:

```python
# Good: Uses tmp_path (fresh per test)
def test_model_saves(tmp_path):
    path = tmp_path / "model.pkl"
    save_model(path)
    assert path.exists()

# Bad: Shares state between tests
MODEL_PATH = "/tmp/model.pkl"  # Tests interfere with each other!
```

---

## CI Integration

The CI workflow now runs the full test suite:

```yaml
- name: Run test suite
  run: |
    pytest --cov=heart_disease_prediction --cov=monitoring --cov=api \
      --cov-report=term-missing --cov-fail-under=80 tests/
```

**Coverage Requirements:**
- Minimum 80% coverage
- Missing lines reported in CI logs
- PR blocked if tests fail

---

## Dependencies Added

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",      # Coverage reporting
    "pytest-asyncio>=0.23.0", # Async test support
    "httpx>=0.27.0",          # For FastAPI TestClient
    "moto>=5.0.0",            # Mock AWS services
]
```

---

## Verification

After Phase 8, verify with:

```bash
# Run tests
pytest tests/ -v

# Check coverage
pytest --cov=heart_disease_prediction --cov=monitoring --cov=api tests/

# Verify no placeholder tests
grep -r "assert False" tests/  # Should return nothing
grep -r "pass  # TODO" tests/  # Should return nothing

# Verify all test files exist
ls tests/*.py
# Should show: conftest.py, test_api.py, test_data.py, test_load_model.py,
#              test_monitoring.py, test_prefect_flow.py, test_register.py, test_train.py
```

---

## What Changed in Production Code

To make code testable, some production functions were updated:

| File | Change | Why |
|------|--------|-----|
| `data.py` | `get_data()` preserves all 303 rows, binarizes `hd` | Consistent with test expectations |
| `train.py` | Returns actual best pipeline | Testable selection logic |
| `register.py` | Sets champion alias, raises clear errors | Testable success/failure paths |
| `load_model.py` | `load_champion_model()` with Production fallback | Testable alias resolution |
| `api/main.py` | Stable health endpoint, probability in response | Testable endpoint behavior |
| `cloudwatch_metrics.py` | Model-name dimension | Testable metric structure |

---

## Next Steps

- ✅ Phase 8: Testing (you are here)
- ⏭️ Phase 9: Security hardening (purge .env from git, rotate keys)

---

## Key Takeaway

**Comprehensive testing doesn't require live infrastructure.** With proper mocking:

- Test AWS S3 without credentials (moto)
- Test MLflow without a server (SQLite backend)
- Test FastAPI without running it (TestClient)
- Test the full pipeline without EC2/RDS

This makes tests fast, reliable, and runnable in CI without complex infrastructure.

---

## Quick Reference

| Task | Command |
|------|---------|
| Run all tests | `pytest tests/` |
| Run with coverage | `pytest --cov-fail-under=80 tests/` |
| Run one file | `pytest tests/test_api.py -v` |
| Run one test | `pytest tests/test_api.py::test_health -v` |
| Debug failing test | `pytest tests/test_api.py::test_health -v --tb=long` |
| See print statements | `pytest tests/ -v -s` |
| Warnings as errors | `pytest tests/ -W error` |

---

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [moto - Mock AWS](https://docs.getmoto.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [scikit-learn Testing](https://scikit-learn.org/stable/developers/develop.html#testing)
