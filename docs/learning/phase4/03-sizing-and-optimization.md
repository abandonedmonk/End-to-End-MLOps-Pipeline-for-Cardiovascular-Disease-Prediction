# 03 — Sizing and Optimization

## What We Did

Reduced Docker image size from **1.07 GB to 613 MB** (43% reduction) using:
- Multi-stage builds (already covered)
- `.dockerignore` file
- `mlflow-skinny` instead of full `mlflow`
- Python 3.11 (vs 3.12, better package support)

## The .dockerignore File

```
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
.mypy_cache
.ruff_cache
.git
.gitignore
.venv
venv
env
data
mlruns
models
notebooks
infra/terraform.tfstate
infra/terraform.tfstate.backup
infra/.terraform
```

### Why This Matters

**Without .dockerignore:**
```
Sending build context to Docker daemon  2.5GB
```

**With .dockerignore:**
```
Sending build context to Docker daemon  45MB
```

The build context is everything in your repo root. Docker sends ALL of it to the daemon before building. Common bloat:

| Directory | Typical Size | Should Ignore? |
|-----------|--------------|----------------|
| `.git/` | 50-200 MB | ✅ Yes |
| `data/` | 100 MB-1 GB | ✅ Yes |
| `mlruns/` | 500 MB-5 GB | ✅ Yes |
| `models/` | 100-500 MB | ✅ Yes |
| `notebooks/` | 10-50 MB | ✅ Yes |
| `venv/` `.venv/` | 500 MB-2 GB | ✅ Yes |
| `__pycache__/` | 10-100 MB | ✅ Yes |
| `infra/.terraform/` | 500 MB-2 GB | ✅ Yes |

### Build Context Impact

**Large context = slower everything:**
1. `docker build` sends context to daemon
2. Larger context = longer send time
3. Larger context = more data to cache
4. CI/CD pipelines suffer most (fresh context each run)

### Pattern Matching

```dockerignore
# Ignore all .pyc files anywhere
*.pyc

# Ignore directories named __pycache__ anywhere
__pycache__

# Ignore specific path
infra/terraform.tfstate

# Ignore all .log files
*.log
```

## mlflow-skinny vs mlflow

### The Problem

Full MLflow package includes:
```
mlflow==2.13.0
├─ Flask (web UI)
├─ SQLAlchemy (database)
├─ alembic (migrations)
├─ gunicorn (WSGI server)
├─ querystring_parser
├─ databricks-cli
├─ ... (many more)
└─ 150+ MB of dependencies
```

Most of this is for **running MLflow server**, not **using MLflow client**.

### The Solution: mlflow-skinny

```
mlflow-skinny==2.13.0
├─ mlflow.tracking (experiment logging)
├─ mlflow.models (model loading/saving)
├─ mlflow.pyfunc (Python function flavor)
├─ Required dependencies only
└─ ~50 MB of dependencies
```

**Use `mlflow-skinny` when:**
- Loading models from registry (our use case)
- Logging experiments to remote server
- **Not** running MLflow tracking server

**Use full `mlflow` when:**
- Running `mlflow server` locally
- Need MLflow UI dependencies
- Self-hosted MLflow setup

### In Our requirements.txt

```
# Before (full MLflow)
mlflow==2.13.0

# After (skinny)
mlflow-skinny==2.13.0
```

**Impact:** ~100 MB reduction in final image

## Python Version Choice

### Why Python 3.11?

```dockerfile
FROM python:3.11-slim  # Not 3.12
```

**Reasons:**
1. **Package compatibility**: Many ML packages (torch, tensorflow) lag behind latest Python
2. **Binary wheels**: More packages have pre-built wheels for 3.11 (faster install)
3. **Stability**: 3.11 is mature, 3.12 is newer (potential edge cases)
4. **Size**: 3.11-slim and 3.12-slim are similar, but ecosystem favors 3.11

### Pre-built Wheels vs Compiling

**Pre-built wheel (fast):**
```
numpy-1.26.4-cp311-cp311-manylinux_2_17_x86_64.whl
→ Download (10s) → Install (2s)
```

**Source distribution (slow):**
```
numpy-1.26.4.tar.gz
→ Download (5s) → Compile (3-5 min) → Install
```

Python 3.11 has more pre-built wheels available.

## Why We Stopped at 613 MB

### What's Still Large

Even with all optimizations, our stack requires:

| Package | Size | Why |
|---------|------|-----|
| scikit-learn | ~150 MB | Compiled C++ extensions |
| scipy | ~100 MB | BLAS/LAPACK, Fortran |
| numpy | ~80 MB | Optimized math kernels |
| pandas | ~50 MB | C extensions, data handling |
| mlflow-skinny + deps | ~50 MB | Tracking, model loading |
| Python runtime | ~50 MB | Standard library |
| System libraries | ~130 MB | glibc, OpenSSL, etc. |

**Total: ~610 MB** (theoretical minimum)

### Further Optimization Options

If we needed <500 MB:

**Option 1: Distroless Base**
```dockerfile
FROM gcr.io/distroless/python3-debian12
# Removes shell, package manager, most system libs
# Risk: Harder to debug, limited compatibility
```

**Option 2: Alpine Linux**
```dockerfile
FROM python:3.11-alpine
# Smaller base but musl libc instead of glibc
# Risk: Many packages don't have musl wheels (compile from source)
```

**Option 3: Exclude Heavy Dependencies**
- Use ONNX instead of scikit-learn (much smaller)
- Requires retraining and exporting model

**Decision:** 613 MB is acceptable for:
- ECR 500 MB free tier (we pay $0.11/GB/month for the 113 MB overage)
- t2.micro memory constraints
- Debugging ease (we kept bash for troubleshooting)

## ECR Free Tier Math

**ECR Pricing:**
- Storage: $0.10 per GB-month
- Data transfer: Free within same region

**Our Image:**
- Size: 613 MB = 0.613 GB
- Free tier: 500 MB = 0.5 GB
- Overage: 0.113 GB
- Cost: 0.113 GB × $0.10 = **$0.0113/month** (~1 cent)

**Before optimization (1.07 GB):**
- Cost: 0.57 GB × $0.10 = **$0.057/month** (~6 cents)

**Savings:** 5 cents/month (not much, but every bit helps at scale)

## Validation Checklist

Before pushing to ECR, verify locally:

```bash
# 1. Build succeeds
docker build -t heart-disease-api .

# 2. Image size is reasonable
docker images heart-disease-api
# REPOSITORY          TAG       SIZE
# heart-disease-api   latest    613MB

# 3. Container starts
docker run -d --name test-api \
  -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 \
  -e MODEL_NAME=test \
  -p 8000:8000 \
  heart-disease-api

# 4. Health endpoint works (model load will fail without real MLflow, that's OK)
curl http://localhost:8000/health
# {"status":"degraded","model_loaded":false,...}

# 5. Clean up
docker stop test-api && docker rm test-api
```

## Key Takeaways

1. **`.dockerignore`** is critical — prevents sending GB of data to daemon
2. **`mlflow-skinny`** vs `mlflow` saves ~100 MB when only using client features
3. **Python 3.11** offers better package compatibility than 3.12
4. **scikit-learn + scipy** are inherently large — optimization has limits
5. **613 MB is production-ready** — fits ECR with minimal overage cost
6. **Optimize until good enough** — don't chase perfection, ship working code

## Quick Reference

```bash
# Check what's in your image
docker run --rm heart-disease-api du -sh /opt/venv

# See layer sizes
docker history --no-trunc heart-disease-api | head -20

# Export to check size breakdown
docker save heart-disease-api > /tmp/image.tar
ls -lh /tmp/image.tar
tar -tf /tmp/image.tar | head -20
```

## Next Steps

- Phase 5: Prefect Agent on EC2
- Deploy container to EC2 with systemd
- Set up monitoring and health checks
