# 01 — Containerizing for Production

## What We Did

Replaced the single-stage `api/Dockerfile` with a **root-level multi-stage build** that produces smaller, production-ready images.

### Before (Single-Stage)

```dockerfile
FROM python:3.12-slim
RUN pip install -U pip
WORKDIR /app
COPY ["api/requirements.txt", "api/main.py", "api/schema.py", "./"]
RUN pip install --no-cache-dir -r requirements.txt
COPY ["../models/pipeline.pkl", "./"]
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Problems:**
- Compiled dependencies (numpy, scikit-learn) built in final image
- Build tools (gcc, build-essential) remained in final image
- Local pickle file copied in (tight coupling)
- Image size: ~1.07 GB

### After (Multi-Stage)

```dockerfile
FROM python:3.11-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY api/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r /build/requirements.txt

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    MLFLOW_TRACKING_URI="" \
    MODEL_NAME="heart-disease-model" \
    AWS_REGION=""
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY api /app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Improvements:**
- Build tools isolated to `builder` stage
- Only compiled Python packages copied to `runtime` stage
- Default env vars set (overridden at runtime)
- `--workers 1` for memory-constrained t2.micro

## Why Multi-Stage Builds Matter

### The Problem

When you install Python packages with C extensions (numpy, pandas, scikit-learn), they need to be **compiled** from source. This requires:
- gcc (C compiler)
- build-essential (make, headers)
- python3-dev (Python headers)

These tools are **100+ MB** but only needed during install, not at runtime.

### The Solution

Multi-stage builds use Docker's layer caching to:
1. **Build stage**: Install everything needed to compile
2. **Runtime stage**: Copy only the result, discard the build tools

```
┌─────────────────────────────────────┐
│  Stage 1: builder                   │
│  - gcc, build-essential             │
│  - compile numpy, sklearn           │
│  - create virtualenv                  │
│  - result: /opt/venv (compiled libs) │
└────────────┬────────────────────────┘
             │ COPY --from=builder
             ▼
┌─────────────────────────────────────┐
│  Stage 2: runtime                   │
│  - only ca-certificates             │
│  - copied venv with compiled libs   │
│  - your app code                    │
│  - result: small production image   │
└─────────────────────────────────────┘
```

### Real Numbers

| Metric | Single-Stage | Multi-Stage | Improvement |
|--------|--------------|-------------|-------------|
| Image Size | 1.07 GB | 613 MB | 43% smaller |
| Build Time | 4-5 min | 3-4 min | Similar |
| Attack Surface | gcc + dev libs | ca-certificates only | Much smaller |
| Memory at Runtime | Higher | Lower | Better for t2.micro |

## Build Commands

```bash
# Build from repo root (where Dockerfile is)
docker build -t heart-disease-api .

# Tag for ECR
docker tag heart-disease-api:latest \
  695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest

# Push to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  695074562426.dkr.ecr.us-east-1.amazonaws.com
docker push 695074562426.dkr.ecr.us-east-1.amazonaws.com/heart-disease-mlops-api:latest
```

## Common Mistakes

### ❌ Wrong: Building from api/ directory

```bash
cd api && docker build -t api .  # Wrong! Dockerfile expects COPY api/
```

The multi-stage Dockerfile is at **repo root** so it can copy the `api/` directory into the image. Build from root:

```bash
docker build -t heart-disease-api .  # Correct!
```

### ❌ Wrong: Forgetting --from=builder

```dockerfile
# This copies the requirements.txt, not the installed packages
COPY --from=builder /build/requirements.txt /app/

# This copies the compiled virtualenv (correct)
COPY --from=builder /opt/venv /opt/venv
```

### ❌ Wrong: Using COPY without build context

```dockerfile
# This tries to copy from your local machine (wrong)
COPY /opt/venv /opt/venv

# This copies from the builder stage (correct)
COPY --from=builder /opt/venv /opt/venv
```

## Why This Matters for AWS Free Tier

**ECR Free Tier:** 500 MB storage
- 613 MB image fits within limit
- 1.07 GB image would exceed it

**EC2 t2.micro:** 1 GB RAM
- Smaller images use less disk cache
- More RAM available for the running container
- Faster pull/deploy times

## Key Takeaways

1. **Multi-stage builds** separate compilation from runtime
2. **Build from repo root** when Dockerfile copies subdirectories
3. **Use virtualenv in containers** to isolate Python dependencies
4. **Set production env vars** in Dockerfile (can be overridden)
5. **Image size directly impacts** storage costs and deploy speed

## Debugging Tips

```bash
# Inspect image layers (see what's taking space)
docker history heart-disease-api

# Check image size
docker images heart-disease-api

# Run container interactively to debug
docker run -it --rm heart-disease-api /bin/bash

# Test locally with env vars
docker run -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 \
  -e MODEL_NAME=heart-disease-classifier \
  heart-disease-api
```

## Next Steps

- [02 — Loading Models from MLflow](02-loading-models-from-mlflow.md)
