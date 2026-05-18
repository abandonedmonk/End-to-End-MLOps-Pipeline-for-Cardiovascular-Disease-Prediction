FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

COPY api/requirements.txt /wheels/requirements.txt
RUN pip --disable-pip-version-check wheel --wheel-dir /wheels/wheels -r /wheels/requirements.txt

FROM python:3.11-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy built wheels from builder and install
COPY --from=builder /wheels/wheels /wheels
RUN pip --no-cache-dir install /wheels/*

# Copy application
COPY api /app

ENV PYTHONUNBUFFERED=1
ENV MLFLOW_TRACKING_URI=""
ENV MODEL_NAME="heart-disease-model"
ENV AWS_REGION=""

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
# Use official Python image
FROM python:3.12-slim

RUN pip install -U pip

# Set working directory inside the container
WORKDIR /app

# Copy all files to container
COPY ["api/requirements.txt", "api/main.py", "api/schema.py", "./"]

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY [ "../models/pipeline.pkl", "./" ]

# Expose FastAPI default port
EXPOSE 8000

# Run the FastAPI app using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
