# 02 — Loading Models from MLflow

## What We Did

Replaced local pickle file loading with **MLflow model registry loading at startup**. The API now:
- Connects to MLflow tracking server via env var
- Loads the "champion" model (or falls back to "Production")
- Exposes `/health` endpoint showing model load status
- Fails gracefully if model can't be loaded

### Before (Local Pickle)

```python
# main.py - OLD
with open("pipeline.pkl", "rb") as f:
    pipeline = pickle.load(f)

@app.post("/predict")
def predict_endpoint(data: PatientData):
    prediction = pipeline.predict(df)
    return {"prediction": int(prediction[0])}
```

**Problems:**
- Tight coupling: API and model must be built together
- Model updates require rebuilding Docker image
- No versioning or model lineage tracking
- Pickle security risks (arbitrary code execution)

### After (MLflow Registry)

```python
# main.py - NEW
import os
import mlflow
import mlflow.pyfunc
from dotenv import load_dotenv

load_dotenv()

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")
AWS_REGION = os.getenv("AWS_REGION")

if MLFLOW_TRACKING_URI:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

if AWS_REGION:
    boto3.setup_default_session(region_name=AWS_REGION)

def _load_pipeline():
    model_uris = [
        f"models:/{MODEL_NAME}@champion",           # Try champion alias first
        f"models:/{MODEL_NAME}/Production",        # Fallback to Production stage
    ]
    
    for model_uri in model_uris:
        try:
            return mlflow.pyfunc.load_model(model_uri), model_uri
        except Exception as exc:
            print(f"Failed to load {model_uri}: {exc}")
    
    return None, None

pipeline, loaded_model_uri = _load_pipeline()

@app.get("/health")
def health():
    return {
        "status": "ok" if pipeline is not None else "degraded",
        "model_loaded": pipeline is not None,
        "model_name": MODEL_NAME,
        "loaded_from": loaded_model_uri,
    }

@app.post("/predict")
def predict_endpoint(data: PatientData):
    if pipeline is None:
        return {"error": "Model not loaded from MLflow"}
    prediction = pipeline.predict(df)
    return {"prediction": int(prediction[0])}
```

## Why MLflow Registry Loading is Better

### The Problem with Pickles

1. **Tight Coupling**: Model file must exist at build/deploy time
2. **Version Blindness**: Can't tell which model version is running
3. **Update Pain**: New model = new Docker build + push + deploy
4. **Security Risk**: `pickle.load()` executes arbitrary Python code

### The Solution: MLflow Model Registry

**Model Registry** is MLflow's centralized model store:

```
┌─────────────────────────────────────┐
│  MLflow Tracking Server             │
│  ┌───────────────────────────────┐  │
│  │  Model: heart-disease-classifier │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │  Version 1              │  │  │
│  │  │  Stage: Archived        │  │  │
│  │  └─────────────────────────┘  │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │  Version 2              │  │  │
│  │  │  Stage: Production ←────┼──┼──┼──┐ API loads this
│  │  │  Alias: champion   ←────┼──┼──┼──┘ or this
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**Aliases vs Stages:**
- **Aliases** (new in MLflow 2.x): Named pointers (`@champion`, `@candidate`)
- **Stages** (legacy): Fixed stages (None, Staging, Production, Archived)
- We try `@champion` first, fall back to `Production` for compatibility

## How It Works

### 1. Environment Configuration

```bash
# On EC2, set in /etc/default/fastapi
MLFLOW_TRACKING_URI=http://localhost:5000
MODEL_NAME=heart-disease-classifier
AWS_REGION=us-east-1
```

### 2. Startup Loading

```python
# When container starts
pipeline, loaded_model_uri = _load_pipeline()
# This happens ONCE at import time (FastAPI startup)
```

### 3. Model Resolution

MLflow resolves the alias/stage to an actual artifact path:
```
models:/heart-disease-classifier@champion
    ↓
s3://heart-disease-mlops-artifacts/artifacts/2/...
    ↓
Downloaded to local cache → loaded into memory
```

### 4. Health Check

```bash
curl http://32.196.26.238:8000/health

{
  "status": "ok",
  "model_loaded": true,
  "model_name": "heart-disease-classifier",
  "loaded_from": "models:/heart-disease-classifier@champion",
  "tracking_uri_set": true
}
```

If model fails to load:
```json
{
  "status": "degraded",
  "model_loaded": false,
  "model_name": "heart-disease-classifier",
  "tracking_uri_set": true
}
```

## The Fallback Strategy

```python
model_uris = [
    f"models:/{MODEL_NAME}@champion",        # New way (MLflow 2.x)
    f"models:/{MODEL_NAME}/Production",      # Old way (stages)
]

for model_uri in model_uris:
    try:
        return mlflow.pyfunc.load_model(model_uri), model_uri
    except Exception as exc:
        print(f"Failed to load {model_uri}: {exc}")
        # Continue to next option
```

**Why two options?**
1. `@champion` alias: Modern, explicit, can point to any version
2. `Production` stage: Legacy support, used by older MLflow versions

This makes the API resilient to different registry configurations.

## Why Load at Startup vs On-Demand

### Startup Loading (What We Did)

**Pros:**
- Fast response times (no MLflow call during request)
- Fail fast (container won't start if model unavailable)
- Clear error messages in logs

**Cons:**
- Slower container startup
- Model updates require container restart

### On-Demand Loading (Alternative)

**Pros:**
- Fast startup
- Could reload model without restart

**Cons:**
- Slow first request (cold start)
- Complex caching logic needed
- Error handling in every request

**For production APIs, startup loading is preferred.**

## Security Considerations

### No More Pickle

```python
# OLD - Dangerous
with open("pipeline.pkl", "rb") as f:
    pipeline = pickle.load(f)  # Executes arbitrary code!

# NEW - Safe
pipeline = mlflow.pyfunc.load_model(model_uri)  # MLflow validates artifacts
```

### MLflow Artifact Validation

MLflow's `pyfunc` flavor:
- Validates model signature (input/output types)
- Loads via safe serialization (cloudpickle with restrictions)
- Tracks exact artifact version used

## Common Errors

### ❌ "Model not found"

```
Failed to load models:/my-model@champion: Not found
```

**Fix:** Check model name and alias exist:
```bash
mlflow models list --model-name my-model
mlflow models set-alias --model-name my-model --alias champion --version 2
```

### ❌ "Connection refused" to MLflow

```
Failed to connect to MLflow server at http://localhost:5000
```

**Fix:** Verify MLflow server is running and accessible:
```bash
# On EC2
sudo systemctl status mlflow
curl http://localhost:5000
```

### ❌ "Access denied" to S3

```
botocore.exceptions.ClientError: An error occurred (403)...
```

**Fix:** Check IAM role has S3 permissions:
```bash
aws sts get-caller-identity
aws s3 ls s3://heart-disease-mlops-artifacts/
```

## Deployment on EC2

### 1. Create Environment File

```bash
sudo tee /etc/default/fastapi << 'EOF'
MLFLOW_TRACKING_URI=http://localhost:5000
MODEL_NAME=heart-disease-classifier
AWS_REGION=us-east-1
EOF
```

### 2. Run Container with Env File

```bash
docker run -d \
  --name fastapi \
  --network=host \
  --env-file /etc/default/fastapi \
  -p 8000:8000 \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest
```

### 3. Test Health Endpoint

```bash
curl http://localhost:8000/health
```

### 4. Test Prediction

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 63, "sex": 1, "cp": 1, "trestbps": 145,
    "chol": 233, "fbs": 1, "restecg": 2, "thalach": 150,
    "exang": 0, "oldpeak": 2.3, "slope": 3, "ca": "0", "thal": "6"
  }'
```

## Key Takeaways

1. **MLflow registry** decouples API from model artifacts
2. **Aliases** (`@champion`) are preferred over **stages** (`/Production`)
3. **Load at startup** for fast, predictable responses
4. **Health endpoint** shows model status for monitoring
5. **Fallback strategy** makes API resilient to registry variations
6. **Graceful degradation** when model unavailable (returns 500 with clear error)

## Next Steps

- [03 — Sizing and Optimization](03-sizing-and-optimization.md)
