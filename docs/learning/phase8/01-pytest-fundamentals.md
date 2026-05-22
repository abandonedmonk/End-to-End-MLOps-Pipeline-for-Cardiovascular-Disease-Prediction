# 01 — pytest Fundamentals

pytest basics: fixtures, conftest.py, tmp_path, monkeypatch, and test organization.

---

## Table of Contents

1. [Why pytest?](#why-pytest)
2. [Test Organization](#test-organization)
3. [Fixtures](#fixtures)
4. [conftest.py](#conftestpy)
5. [tmp_path](#tmp_path)
6. [monkeypatch](#monkeypatch)
7. [Test Discovery](#test-discovery)
8. [Running Tests](#running-tests)
9. [Common Patterns](#common-patterns)
10. [Best Practices](#best-practices)

---

## Why pytest?

pytest is Python's most popular testing framework because it:

- **Minimal boilerplate** — No classes needed, just `def test_*():`
- **Powerful fixtures** — Reusable setup/teardown
- **Auto-discovery** — Finds tests automatically
- **Rich plugins** — Coverage, mocking, async support
- **Great error messages** — Clear diffs and tracebacks

**vs unittest:**
```python
# unittest (verbose)
import unittest
class TestData(unittest.TestCase):
    def test_load(self):
        df = load_data()
        self.assertEqual(df.shape, (303, 14))

# pytest (clean)
def test_load_data_returns_expected_shape():
    df = load_data()
    assert df.shape == (303, 14)
```

---

## Test Organization

### File Structure

```
tests/
├── __init__.py              # Makes tests a package (optional)
├── conftest.py              # Shared fixtures (auto-imported)
├── test_data.py             # Tests for data module
├── test_train.py            # Tests for training module
├── test_api.py              # Tests for API
└── ...
```

**Naming convention:**
- Test files: `test_*.py` or `*_test.py`
- Test functions: `test_*`
- Test classes: `Test*` (optional)

---

## Fixtures

Fixtures provide reusable setup/teardown. They're pytest's superpower.

### Basic Fixture

```python
import pytest

@pytest.fixture
def sample_data():
    """Provide a small DataFrame for tests."""
    df = pd.DataFrame({
        "age": [54, 61],
        "sex": [1, 0],
        "hd": [1, 0]
    })
    return df

def test_data_has_target_column(sample_data):
    """Use the fixture by naming it as a parameter."""
    assert "hd" in sample_data.columns
```

**How it works:**
1. pytest sees `sample_data` parameter
2. Finds fixture with that name
3. Calls fixture function
4. Passes return value to test

---

### Fixture with Cleanup

```python
@pytest.fixture
def temp_database():
    """Create database, yield it, then cleanup."""
    db = create_database()
    db.connect()
    yield db  # Test runs here
    # Cleanup after test
    db.disconnect()
    db.delete()

def test_query(temp_database):
    result = temp_database.query("SELECT * FROM users")
    assert len(result) > 0
# After test: cleanup runs automatically
```

---

### Fixture Scope

Control how often fixtures run:

| Scope | When Created | Use Case |
|-------|--------------|----------|
| `function` (default) | Every test | Fresh state per test |
| `class` | Once per class | Shared class setup |
| `module` | Once per module | Expensive module-level setup |
| `package` | Once per package | Package-level resources |
| `session` | Once per test run | Database, external services |

```python
@pytest.fixture(scope="module")
def expensive_setup():
    """Run once for all tests in this module."""
    result = slow_operation()
    yield result
    cleanup(result)
```

**Phase 8 uses:** `function` scope (default) for isolation.

---

### autouse Fixtures

Run automatically for every test:

```python
@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment before every test."""
    os.environ.clear()
    os.environ.update(DEFAULT_ENV)
    yield

def test_something():  # No parameter needed!
    # Environment is already reset
    pass
```

**Phase 8 usage (`conftest.py`):**
```python
@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    """Every test gets safe env vars automatically."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    # ... all tests have safe defaults
```

---

## conftest.py

**conftest.py = shared fixtures**

- Placed in `tests/` or subdirectories
- Auto-imported by all tests in that directory
- Defines fixtures used by multiple test files

### Our conftest.py Structure

```python
# tests/conftest.py

# 1. Imports
import pytest
import pandas as pd
from sklearn.pipeline import Pipeline

# 2. Constants
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "processed.cleveland.data"

# 3. autouse fixture (safety)
@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    """Safe env vars for every test."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    # ... other safe defaults

# 4. Data fixtures
@pytest.fixture
def sample_dataframe():
    """Load small sample dataset."""
    return pd.read_csv(DATA_PATH).head(50)

# 5. Model fixtures
class DummyHeartModel(BaseEstimator, ClassifierMixin):
    def predict(self, X):
        return np.ones(len(X), dtype=int)

@pytest.fixture
def dummy_model():
    return Pipeline([("classifier", DummyHeartModel())])

# 6. Utility fixtures
@pytest.fixture
def import_fresh():
    """Import module after clearing cache."""
    def _import(name):
        # ... import logic
    return _import
```

**Benefits:**
- No repeated setup code
- Consistent test data
- Automatic cleanup
- Single place to change defaults

---

## tmp_path

Built-in fixture: temporary directory unique to each test.

```python
def test_save_file(tmp_path):
    """tmp_path is a pathlib.Path to a temp directory."""
    file_path = tmp_path / "test.txt"
    
    # Write file
    file_path.write_text("Hello, World!")
    
    # Read and verify
    assert file_path.read_text() == "Hello, World!"
    
    # After test: directory is automatically cleaned up!
```

**Phase 8 usage:**
```python
@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    """Use tmp_path for temporary MLflow database."""
    monkeypatch.setenv(
        "MLFLOW_TRACKING_URI", 
        f"sqlite:///{tmp_path / 'mlflow.db'}"  # Fresh DB per test!
    )
```

---

## monkeypatch

Built-in fixture: temporarily modify objects, functions, or environment.

### Environment Variables

```python
def test_with_custom_env(monkeypatch):
    """Temporarily set env var."""
    monkeypatch.setenv("MODEL_NAME", "test-model")
    
    # Code under test sees the new value
    assert os.getenv("MODEL_NAME") == "test-model"
    
# After test: original value restored automatically
```

### Mocking Functions

```python
def test_with_mocked_function(monkeypatch):
    """Replace a function temporarily."""
    def fake_train(*args, **kwargs):
        return "fake_model", "fake_pipeline", {}
    
    monkeypatch.setattr(
        "heart_disease_prediction.prefect_flow.train_model",
        type("Mock", (), {"fn": fake_train})
    )
    
    # Now train_model.fn() returns our fake
    result = prefect_flow.train_model.fn()
    assert result == ("fake_model", "fake_pipeline", {})
```

### Mocking Attributes

```python
def test_with_mocked_attr(monkeypatch):
    """Replace object attributes."""
    class FakeClient:
        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(b"fake data")}
    
    monkeypatch.setattr(
        "boto3.client",
        lambda service, **kwargs: FakeClient()
    )
    
    # boto3.client("s3") now returns FakeClient
```

**Phase 8 usage:**
```python
def test_api_with_mock_model(monkeypatch, import_fresh):
    """Mock mlflow.pyfunc.load_model to avoid real MLflow calls."""
    monkeypatch.setattr(
        mlflow.pyfunc, 
        "load_model", 
        lambda uri: dummy_model
    )
    # API thinks it loaded from MLflow, but got our dummy
```

---

## Test Discovery

pytest finds tests automatically:

```bash
# Discover all tests
pytest --collect-only

# Discover in specific directory
pytest tests/ --collect-only

# Discover specific file
pytest tests/test_data.py --collect-only

# Output:
# <Module test_data.py>
#   <Function test_load_data_returns_expected_schema>
#   <Function test_prepare_data_splits_and_binarizes_target>
```

**Rules:**
1. Look in `testpaths` (default: current directory)
2. Recurse into directories
3. Collect files matching `test_*.py` or `*_test.py`
4. Collect functions/classes named `test_*` or `Test*`

---

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run specific file
pytest tests/test_data.py

# Run specific test
pytest tests/test_data.py::test_load_data_returns_expected_schema

# Run matching pattern
pytest -k "test_load"

# Run tests not matching pattern
pytest -k "not slow"
```

### Useful Options

```bash
# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Full traceback
pytest --tb=long

# Show warnings
pytest -W always

# Measure execution time
pytest --durations=10

# Run last failed first
pytest --ff

# Only run last failed
pytest --lf
```

### Coverage

```bash
# Run with coverage
pytest --cov=heart_disease_prediction tests/

# Show missing lines
pytest --cov=heart_disease_prediction --cov-report=term-missing tests/

# Generate HTML report
pytest --cov=heart_disease_prediction --cov-report=html tests/

# Fail if coverage < 80%
pytest --cov-fail-under=80 tests/
```

---

## Common Patterns

### Pattern 1: Setup → Action → Assertion

```python
def test_load_data():
    # Setup
    path = "data/raw/heart.csv"
    
    # Action
    df = load_data(path)
    
    # Assertion
    assert df.shape == (303, 14)
    assert "hd" in df.columns
```

---

### Pattern 2: Arrange → Act → Assert (AAA)

```python
def test_training_logs_metrics(mock_mlflow):
    # Arrange
    X_train, y_train = make_classification(n_samples=100)
    config = {"experiment_name": "test"}
    
    # Act
    model, pipeline, paths = train_model(X_train, ..., config=config)
    
    # Assert
    runs = mlflow.search_runs()
    assert len(runs) == 4
    assert runs[0].data.metrics["accuracy"] > 0
```

---

### Pattern 3: Parametrized Tests

Run same test with different inputs:

```python
@pytest.mark.parametrize("model_class", [
    LogisticRegression,
    RandomForestClassifier,
    GradientBoostingClassifier,
])
def test_all_models_can_fit(model_class, prepared_data):
    """Test each model class with same data."""
    X_train, _, y_train, _, preprocessor = prepared_data
    model = model_class()
    pipeline = Pipeline([("prep", preprocessor), ("clf", model)])
    pipeline.fit(X_train, y_train)
    assert hasattr(pipeline, "predict")
```

**Output:**
```
test_train.py::test_all_models_can_fit[LogisticRegression] PASSED
test_train.py::test_all_models_can_fit[RandomForestClassifier] PASSED
test_train.py::test_all_models_can_fit[GradientBoostingClassifier] PASSED
```

---

### Pattern 4: Exception Testing

```python
def test_missing_file_raises_error():
    with pytest.raises(FileNotFoundError):
        load_data("/nonexistent/file.csv")

def test_specific_error_message():
    with pytest.raises(ValueError, match="No runs found"):
        register_model(empty_experiment)
```

---

### Pattern 5: Fixture Dependencies

```python
@pytest.fixture
def raw_data():
    return load_raw_data()

@pytest_fixture
def processed_data(raw_data):  # Depends on raw_data fixture
    return preprocess(raw_data)

@pytest.fixture
def trained_model(processed_data):  # Depends on processed_data
    return train(processed_data)

def test_model_predicts(trained_model):  # Gets trained model
    predictions = trained_model.predict(X_test)
    assert len(predictions) > 0
```

---

## Best Practices

### 1. Descriptive Test Names

```python
# Bad
 def test1():
    pass

# Good
def test_load_data_returns_dataframe_with_expected_columns():
    pass
```

**Pattern:** `test_<action>_<result>_<context>`

---

### 2. One Assertion per Test (Flexible)

```python
# Good: Related assertions
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_loaded"] is True

# Bad: Unrelated assertions
def test_everything():
    # Data loading
    assert load_data().shape == (303, 14)
    
    # Training
    model = train_model()
    assert model is not None
    
    # API
    assert client.get("/health").status_code == 200
```

---

### 3. Fast Tests

```python
# Bad: Slow test
def test_real_training():
    model = RandomForestClassifier(n_estimators=10000)
    model.fit(X_train, y_train)  # Minutes!

# Good: Fast test
def test_training_logs_metrics():
    # Use small data, few estimators
    model = RandomForestClassifier(n_estimators=10)
    model.fit(X_train_small, y_train_small)
    # Or use mocked model
```

---

### 4. Independent Tests

```python
# Bad: Depends on state from other test
TEST_COUNTER = 0

def test_a():
    global TEST_COUNTER
    TEST_COUNTER += 1

def test_b():
    global TEST_COUNTER
    assert TEST_COUNTER == 1  # Depends on test_a running first!

# Good: Each test is self-contained
def test_a():
    counter = 0
    counter += 1
    assert counter == 1

def test_b():
    counter = 0
    counter += 1
    assert counter == 1
```

---

### 5. Fixtures for Common Setup

```python
# Bad: Repeated setup
def test_a():
    df = pd.read_csv("data.csv").head(50)
    # ... test a

def test_b():
    df = pd.read_csv("data.csv").head(50)
    # ... test b

# Good: Use fixture
@pytest.fixture
def sample_data():
    return pd.read_csv("data.csv").head(50)

def test_a(sample_data):
    # ... test a

def test_b(sample_data):
    # ... test b
```

---

## Key Takeaways

1. **Fixtures are powerful** — Reusable setup with automatic cleanup
2. **conftest.py for sharing** — Common fixtures in one place
3. **tmp_path for temp files** — Automatic cleanup, no side effects
4. **monkeypatch for mocking** — Temporary modifications
5. **autouse for safety** — Run setup for every test automatically
6. **Descriptive names** — Tests document expected behavior
7. **Keep tests fast** — Use small data, mock expensive operations
8. **Tests should be independent** — No shared state between tests

---

## Next

- [02 — Mocking AWS Services](02-mocking-aws-services.md) — moto, boto3 mocking, MLflow mocking
