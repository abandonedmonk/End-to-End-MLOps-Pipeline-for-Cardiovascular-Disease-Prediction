# 05 — Testing API with TestClient

Testing FastAPI endpoints without running a server using TestClient.

---

## Table of Contents

1. [Why TestClient?](#why-testclient)
2. [Setting Up TestClient](#setting-up-testclient)
3. [Testing the Health Endpoint](#testing-the-health-endpoint)
4. [Testing the Predict Endpoint](#testing-the-predict-endpoint)
5. [Testing Error Handling](#testing-error-handling)
6. [Mocking Model Loading](#mocking-model-loading)
7. [Common Patterns](#common-patterns)
8. [Troubleshooting](#troubleshooting)

---

## Why TestClient?

### Traditional API Testing

```python
# Bad: Requires running server
import requests
import subprocess
import time

# Start server (slow!)
server = subprocess.Popen(["uvicorn", "api.main:app"])
time.sleep(5)  # Wait for startup

# Make request
response = requests.get("http://localhost:8000/health")
assert response.status_code == 200

# Cleanup
server.terminate()
```

**Problems:**
- Slow (server startup/shutdown)
- Complex orchestration
- Port conflicts
- Requires dependencies installed
- Brittle (server might fail to start)

---

### TestClient Approach

```python
# Good: In-process, no server needed
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

# Make request
response = client.get("/health")
assert response.status_code == 200

# Instant, no cleanup needed
```

**Benefits:**
- Fast (no server startup)
- Simple (no subprocesses)
- No port conflicts
- Easy mocking
- Runs in CI easily

---

## Setting Up TestClient

### Basic Setup

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from api.main import app

# Create client once
client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
```

**How it works:**
- TestClient wraps the FastAPI app
- Makes "requests" in-process (no HTTP)
- Runs all FastAPI middleware, dependencies
- Returns standard `requests` Response objects

---

### Our Setup with Mocking

```python
# tests/test_api.py
def _client_with_model(monkeypatch, import_fresh, model):
    """Create TestClient with mocked model loading."""
    # Mock mlflow.pyfunc.load_model to return our dummy
    monkeypatch.setattr(mlflow.pyfunc, "load_model", lambda uri: model)
    
    # Import fresh to pick up the mock
    module = import_fresh("api.main")
    
    return TestClient(module.app)
```

**Why mocking?** The API tries to load from MLflow at startup. We mock it to avoid needing real MLflow.

---

### import_fresh Fixture

```python
# conftest.py
@pytest.fixture
def import_fresh():
    """Import a module after removing any cached copy."""
    
    def _import(module_name: str):
        # Clear import cache
        importlib.invalidate_caches()
        
        # Remove cached module
        for cached in list(os.sys.modules):
            if cached == module_name or cached.startswith(f"{module_name}."):
                os.sys.modules.pop(cached)
        
        # Import fresh
        return importlib.import_module(module_name)
    
    return _import
```

**Why needed?** Python caches imports. If we import `api.main` before mocking, the real MLflow.load_model is already loaded.

---

## Testing the Health Endpoint

### Test: Healthy When Model Loaded

```python
def test_health_endpoint_reports_loaded_model(monkeypatch, import_fresh, dummy_model):
    """Validate /health returns ok and model_loaded=true when MLflow load succeeds."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_loaded": True,
    }
```

**What it validates:**
- Endpoint returns 200
- JSON response has expected keys
- `model_loaded` is true when model available

---

### Test: Healthy Even When Model Fails

```python
def test_health_endpoint_reports_unloaded_model(monkeypatch, import_fresh):
    """Validate /health stays available when MLflow load fails."""
    
    def fail_load(*args, **kwargs):
        raise RuntimeError("no registry")
    
    # Mock to simulate MLflow failure
    monkeypatch.setattr(mlflow.pyfunc, "load_model", fail_load)
    
    module = import_fresh("api.main")
    client = TestClient(module.app)
    
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_loaded": False,
    }
```

**What it validates:**
- Health endpoint works even if model fails to load
- System stays up for monitoring/load balancers
- Clear indication that predictions will fail

**Why important:** In production, model loading might fail (network, permissions), but we still want to know the API is running.

---

## Testing the Predict Endpoint

### Test: Valid Prediction Request

```python
def test_predict_endpoint_returns_prediction_and_probability(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate /predict returns a binary prediction and probability for valid input."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    response = client.post("/predict", json=patient_payload)
    
    assert response.status_code == 200
    data = response.json()
    
    # Prediction is binary
    assert data["prediction"] in {0, 1}
    
    # Probability is 0-1
    assert 0 <= data["probability"] <= 1
```

**What it validates:**
- Valid input returns 200
- Response has prediction (0 or 1)
- Response has probability (0.0-1.0)

---

### Test: Patient Payload Fixture

```python
# conftest.py
@pytest.fixture
def patient_payload():
    """Return a valid API payload for one heart-disease prediction."""
    return {
        "age": 54,
        "sex": 1,
        "cp": 1,
        "trestbps": 140,
        "chol": 239,
        "fbs": 0,
        "restecg": 1,
        "thalach": 160,
        "exang": 0,
        "oldpeak": 1.2,
        "slope": 1,
        "ca": 2,
        "thal": 3,
    }
```

**Why fixture?** Reusable across multiple tests.

---

### Test: Batch Predictions

```python
def test_predict_endpoint_handles_batch_input(
    monkeypatch, import_fresh, dummy_model
):
    """Validate /predict can handle multiple patients in one request."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    batch_payload = [
        {"age": 54, "sex": 1, "cp": 1, /* ... */},
        {"age": 61, "sex": 0, "cp": 2, /* ... */},
    ]
    
    response = client.post("/predict", json=batch_payload)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return list of predictions
    assert isinstance(data, list)
    assert len(data) == 2
    
    # Each prediction has expected fields
    for pred in data:
        assert pred["prediction"] in {0, 1}
        assert 0 <= pred["probability"] <= 1
```

---

## Testing Error Handling

### Test: Missing Required Fields

```python
def test_predict_endpoint_rejects_missing_fields(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate /predict returns 422 when required fields are missing."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    # Remove required field
    patient_payload.pop("age")
    
    response = client.post("/predict", json=patient_payload)
    
    assert response.status_code == 422
    
    # Error mentions missing field
    error_data = response.json()
    assert "age" in str(error_data) or "field required" in str(error_data).lower()
```

**What it validates:**
- Pydantic validation catches missing fields
- Returns 422 (Unprocessable Entity)
- Error message is descriptive

---

### Test: Wrong Data Types

```python
def test_predict_endpoint_rejects_wrong_types(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate Pydantic rejects non-numeric values for numeric patient fields."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    # Set invalid type
    patient_payload["age"] = "not-a-number"
    
    response = client.post("/predict", json=patient_payload)
    
    assert response.status_code == 422
    
    # Error mentions type issue
    error_data = response.json()
    assert "age" in str(error_data) or "int" in str(error_data).lower()
```

**What it validates:**
- Pydantic type validation works
- Strings rejected for numeric fields
- Clear error message

---

### Test: Out of Range Values

```python
def test_predict_endpoint_accepts_out_of_range_values(
    monkeypatch, import_fresh, dummy_model, patient_payload
):
    """Validate API accepts values outside training range (model responsibility)."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    # Age 150 is unrealistic but API accepts it
    patient_payload["age"] = 150
    
    response = client.post("/predict", json=patient_payload)
    
    # API accepts it (model may predict weirdly, but that's not API's job)
    assert response.status_code == 200
```

**Design decision:** API validates types/structure, not value ranges. Model handles ranges.

---

## Mocking Model Loading

### Why Mock?

The API loads a model at startup:

```python
# api/main.py
@app.on_event("startup")
async def load_model():
    global model
    try:
        model = mlflow.pyfunc.load_model(f"models:/{model_name}@champion")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
```

**Problems for testing:**
- Requires running MLflow server
- Requires model to exist in registry
- Slow network call
- Brittle test

---

### How We Mock

```python
def _client_with_model(monkeypatch, import_fresh, model):
    """Create TestClient with model loading mocked."""
    # Replace mlflow.pyfunc.load_model with simple lambda
    monkeypatch.setattr(mlflow.pyfunc, "load_model", lambda uri: model)
    
    # Import API module fresh (so it picks up the mock)
    module = import_fresh("api.main")
    
    # Create client with mocked app
    return TestClient(module.app)
```

**What happens:**
1. monkeypatch replaces `mlflow.pyfunc.load_model`
2. `import_fresh` re-imports `api.main` with our mock active
3. App startup calls our lambda instead of real MLflow
4. `dummy_model` loaded instantly
5. Tests run against mocked app

---

### Dummy Model Fixture

```python
# conftest.py
class DummyHeartModel(BaseEstimator, ClassifierMixin):
    """Small sklearn-compatible classifier for API tests."""
    
    classes_ = np.array([0, 1])
    
    def fit(self, X, y=None):
        return self
    
    def predict(self, X):
        # Always predict 1 (disease present)
        return np.ones(len(X), dtype=int)
    
    def predict_proba(self, X):
        # 80% confident in prediction 1
        return np.tile(np.array([[0.2, 0.8]]), (len(X), 1))


@pytest.fixture
def dummy_model():
    """Return a deterministic sklearn Pipeline-compatible model."""
    return Pipeline([("classifier", DummyHeartModel())])
```

**Characteristics:**
- sklearn-compatible (has `predict`, `predict_proba`)
- Deterministic (always same output)
- Fast (no training)
- Returns valid predictions (0/1) and probabilities

---

## Common Patterns

### Pattern: Testing with Different Model Responses

```python
def test_prediction_changes_with_different_model(monkeypatch, import_fresh):
    """Validate prediction reflects model output."""
    
    class AlwaysZeroModel(BaseEstimator, ClassifierMixin):
        def predict(self, X):
            return np.zeros(len(X), dtype=int)
        def predict_proba(self, X):
            return np.tile(np.array([[0.9, 0.1]]), (len(X), 1))
    
    zero_model = Pipeline([("clf", AlwaysZeroModel())])
    client = _client_with_model(monkeypatch, import_fresh, zero_model)
    
    response = client.post("/predict", json=patient_payload())
    data = response.json()
    
    assert data["prediction"] == 0  # Model predicts 0
    assert data["probability"] == 0.1  # Probability for class 0
```

---

### Pattern: Testing Startup Behavior

```python
def test_app_starts_even_if_model_missing(monkeypatch, import_fresh):
    """Validate app starts up (for health checks) even without model."""
    
    def raise_exception(*args, **kwargs):
        raise mlflow.exceptions.MlflowException("Model not found")
    
    monkeypatch.setattr(mlflow.pyfunc, "load_model", raise_exception)
    
    # Should not raise
    module = import_fresh("api.main")
    client = TestClient(module.app)
    
    # Health endpoint works
    response = client.get("/health")
    assert response.status_code == 200
    
    # But predict fails gracefully
    response = client.post("/predict", json=patient_payload())
    assert response.status_code == 503  # Service Unavailable
```

---

### Pattern: Testing Endpoint Response Time

```python
import time

def test_prediction_is_fast(monkeypatch, import_fresh, dummy_model):
    """Validate prediction responds quickly (not training on each request)."""
    client = _client_with_model(monkeypatch, import_fresh, dummy_model)
    
    start = time.time()
    response = client.post("/predict", json=patient_payload())
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 0.1  # Should be instant
```

---

## Troubleshooting

### Problem: "No module named 'api.main'"

**Cause:** Import path issue.

**Fix:** Ensure `api/` is in Python path or use absolute import.

```python
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
```

---

### Problem: Mock not applied

**Cause:** Module cached before mock.

**Fix:** Use `import_fresh` or clear cache.

```python
# Bad: Cached import
from api.main import app  # Uses real mlflow!

# Good: Fresh import
def test_with_mock(monkeypatch, import_fresh, dummy_model):
    monkeypatch.setattr(mlflow.pyfunc, "load_model", lambda uri: dummy_model)
    module = import_fresh("api.main")
    client = TestClient(module.app)
```

---

### Problem: Response is bytes, not JSON

**Cause:** Not using `response.json()`.

```python
# Bad
data = response.content  # b'{"prediction": 1}' - bytes!
assert data["prediction"]  # TypeError

# Good
data = response.json()  # {"prediction": 1} - dict!
assert data["prediction"] == 1
```

---

### Problem: Pydantic validation errors not raised

**Cause:** TestClient catches exceptions and returns 422.

**Check:** Look at `response.status_code` and `response.json()`.

```python
response = client.post("/predict", json={"invalid": "data"})
print(response.status_code)  # 422
print(response.json())  # Detail about validation error
```

---

## Key Takeaways

1. **TestClient is fast** — No server startup needed
2. **Mock model loading** — Avoid MLflow dependency
3. **Test health endpoint** — Critical for load balancers
4. **Test happy path** — Valid input → 200 + prediction
5. **Test error paths** — Invalid input → 422 with details
6. **Use import_fresh** — Clear module cache for mocking
7. **Test model failure** — App stays up even without model
8. **Dummy models are fine** — We're testing API, not model accuracy

---

## Next

- [06 — Testing Prefect Flows](06-testing-prefect-flows.md) — Pipeline orchestration testing
