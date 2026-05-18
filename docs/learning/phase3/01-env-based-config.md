# 01 — Environment-Based Configuration

## What We Did

Converted every hardcoded path and URI in the pipeline to use `os.getenv()` with local fallback defaults. This lets the **same code** run locally (with SQLite and file paths) or on AWS (with RDS, S3, and the EC2 MLflow server) — the only difference is environment variables.

Changed files:

| File | What changed |
|------|-------------|
| `train.py` | `MLFLOW_TRACKING_URI`, `MLFLOW_ARTIFACT_ROOT`, `MLFLOW_EXPERIMENT_NAME` from env |
| `register.py` | `MLFLOW_TRACKING_URI`, `MODEL_NAME` from env, `@task` decorator added |
| `load_model.py` | `MLFLOW_TRACKING_URI`, `MODEL_NAME` from env, dynamic model name (no more hardcoded date) |
| `prefect_flow.py` | `PIPELINE_CONFIG` dict from env vars, relative imports with fallback |
| `data.py` | `DATA_PATH` from env, S3 download via boto3 when path starts with `s3://` |
| `.env.example` | Created with EC2-targeted placeholder values |

## Why Environment Variables (Not Config Files or CLI Args)

| Approach | Pros | Cons |
|----------|------|------|
| **Env vars** | 12-factor app standard, no code change between environments, secrets stay out of code, Docker-friendly | Need `.env` file locally, `export` commands |
| Config YAML/JSON | Structured, supports nested config | Must load/parse file, version control risk for secrets |
| CLI arguments | Explicit, no hidden state | Can't use with Prefect/CI, verbose for many params |
| Hardcoded paths | Simplest to write | Can't change without editing code, breaks across environments |

**Our choice**: Environment variables with `python-dotenv` — the industry standard for 12-factor apps. Works everywhere: local dev, Docker, EC2, CI/CD.

## Theory: The 12-Factor App Methodology

The [12-factor app](https://12factor.net/) is a set of best practices for building software-as-a-service apps. Factor III states:

> **Store config in the environment** — strictly separate config from code. Code remains the same across all deploys; config varies.

### What Counts as "Config"?

| Config (changes between deploys) | Not Config (same across deploys) |
|----------------------------------|----------------------------------|
| `MLFLOW_TRACKING_URI` | `max_iter=1000` in LogisticRegression |
| `DATA_PATH` | Column names in the dataset |
| `S3_BUCKET` | Train/test split ratio (0.2) |
| `AWS_REGION` | Feature engineering logic |
| Database passwords | Model hyperparameter names |

Anything that could change between your laptop and AWS must come from the environment.

## The `os.getenv()` Pattern

### Basic Usage

```python
import os
from dotenv import load_dotenv

load_dotenv()

#                    env var name         fallback if not set
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db")
```

How this works in each environment:

| Environment | `MLFLOW_TRACKING_URI` value | Source |
|-------------|---------------------------|--------|
| Local dev (no `.env`) | `sqlite:///mlruns/mlflow.db` | Fallback default |
| Local dev (with `.env`) | `http://localhost:5000` | `.env` file |
| EC2 | `http://localhost:5000` | systemd service `Environment=` |
| Your machine (remote) | `http://32.196.26.238:5000` | `.env` file |

### The `python-dotenv` Flow

```
python train.py
    │
    ├── load_dotenv() reads .env file
    │   └── Sets environment variables in os.environ
    │
    ├── os.getenv("MLFLOW_TRACKING_URI")
    │   ├── If .env has MLFLOW_TRACKING_URI=http://32.196.26.238:5000
    │   │   → returns "http://32.196.26.238:5000"
    │   └── If .env doesn't have it
    │       → returns fallback "sqlite:///mlruns/mlflow.db"
    │
    └── mlflow.set_tracking_uri(result)
```

### Why `.env.example` Instead of `.env` in Git

| File | Purpose | Commit to Git? |
|------|---------|---------------|
| `.env.example` | Template with placeholder values | Yes |
| `.env` | Real values (may contain secrets) | **Never** |
| `.gitignore` | Must include `.env` | Yes |

The `.env.example` tells new developers what variables they need to set. The actual `.env` with real passwords and keys is **never committed**.

## The Pattern We Used in Each File

### `train.py` — MLflow Connection Config

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT}/mlruns/mlflow.db")
MLFLOW_ARTIFACT_ROOT = os.getenv("MLFLOW_ARTIFACT_ROOT", f"file://{PROJECT_ROOT}/mlruns/")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline")
```

Key insight: The fallback uses `PROJECT_ROOT` to compute an absolute path. SQLite requires an absolute path — `sqlite:///mlruns/mlflow.db` would be relative to wherever you run the script from, which is unreliable.

### `register.py` — Dynamic Model Name

```python
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")
```

Before: `best_model_2025-07-30` was hardcoded — the model name would never change even on different days. Now: if `MODEL_NAME` isn't set, it dynamically uses today's date.

### `load_model.py` — Finding the Right Model

```python
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")
```

Same pattern. The load function searches MLflow for the registered model by name. If you always use the same `MODEL_NAME` across train/register/load, it finds the right model.

### `prefect_flow.py` — Central Config Dict

```python
PIPELINE_CONFIG = {
    "data_path": os.getenv("DATA_PATH", "../data/raw/processed.cleveland.data"),
    "mlflow_tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db"),
    "mlflow_artifact_root": os.getenv("MLFLOW_ARTIFACT_ROOT", "file://mlruns/"),
    "experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline"),
    "model_name": os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}"),
}
```

This dict is passed through the entire pipeline. Each task reads from it or falls back to its own env var. This way:
- You can override a single value for one run by setting an env var
- The pipeline config is visible in one place
- Prefect can log the config as part of the flow run

## The `@task` Decorator Fix

`register.py` was missing the `@task` decorator, which meant Prefect couldn't track it as a separate unit of work.

### Before (broken)
```python
def register_model(preprocessor, paths):
    ...
```

### After (correct)
```python
@task
def register_model(preprocessor, paths):
    ...
```

Without `@task`:
- Prefect treats the function as a regular Python call
- No retry on failure (Prefect retries tasks automatically)
- No timeout enforcement
- No separate logging in the Prefect UI
- The task doesn't appear in the flow graph

## How to Debug

### "MLflow can't connect" After Config Migration

```bash
# Check what MLflow URI your code is using
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
print('MLFLOW_TRACKING_URI:', os.getenv('MLFLOW_TRACKING_URI', 'NOT SET'))
"
```

If it prints `NOT SET` or the wrong URI:
1. Check `.env` file exists in the project root
2. Check the variable name matches exactly (case-sensitive)
3. Check no trailing whitespace in `.env`

### "No module named 'dotenv'"

```bash
pip install python-dotenv
# or with uv:
uv pip install python-dotenv
```

### "Model not found" in load_model.py

The model name must match between `register.py` and `load_model.py`. Check:

```python
# In register.py, the model is registered as:
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")

# In load_model.py, it searches for:
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")
```

If `MODEL_NAME` is set in `.env`, both use the same value. If not set, both use today's date — but if you train on Monday and load on Tuesday, the dates won't match! That's why setting `MODEL_NAME` in `.env` is important for production.

## Practical Tips

### Test Config Resolution Without Running the Pipeline

```python
from dotenv import load_dotenv
import os
load_dotenv()

for var in ["MLFLOW_TRACKING_URI", "MLFLOW_ARTIFACT_ROOT", "DATA_PATH", "MODEL_NAME", "S3_BUCKET"]:
    print(f"{var} = {os.getenv(var, '<using fallback>')}")
```

### Override a Single Variable for One Run

```bash
MLFLOW_TRACKING_URI=http://localhost:5000 python heart_disease_prediction/prefect_flow.py
```

Shell-level env vars override `.env` file values (dotenv only fills in what's not already set).

### Docker Environment Variables

When running in Docker (Phase 4), you pass env vars differently:

```bash
docker run -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 ...
```

Or with `--env-file`:

```bash
docker run --env-file .env ...
```

Inside Docker, `localhost` refers to the container, not the EC2 host. Use `host.docker.internal` or the EC2's private IP to reach MLflow.

### The `.env.example` Template

Our `.env.example`:

```
AWS_REGION=us-east-1
DATA_PATH=s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data
LOCAL_DATA_CACHE=/tmp/heart_disease_prediction
MLFLOW_TRACKING_URI=http://32.196.26.238:5000
MLFLOW_ARTIFACT_ROOT=s3://heart-disease-mlops-695074562426/artifacts/
MLFLOW_EXPERIMENT_NAME=heart-disease-experiment-pipeline
MODEL_NAME=best_model_YYYY-MM-DD
S3_BUCKET=heart-disease-mlops-695074562426
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/<account-id>/workspaces/<workspace-id>
PREFECT_API_KEY=<prefect-api-key>
```

To use it: `cp .env.example .env` then fill in real values for `MODEL_NAME`, `PREFECT_API_URL`, `PREFECT_API_KEY`.
