# 04 — Pipeline Integration

Integrating drift detection into your Prefect flow as a final validation step.

---

## Why Add Monitoring to the Pipeline?

**Problem:** Drift detection runs as a separate process
- Easy to forget
- Manual execution
- Not tied to model lifecycle

**Solution:** Integrate into Prefect flow
- Automatic after every training run
- Tied to model registration
- Centralized logging
- Alerts via CloudWatch/SNS

---

## Design Principles

### 1. Fail-Fast for Critical Drift
If drift is catastrophic (>0.8), stop the pipeline:
```python
if drift_score > 0.8:
    raise ValueError("Catastrophic drift detected! Model unreliable.")
```

### 2. Warn for Moderate Drift
If drift is concerning (>0.3), log warning but continue:
```python
if drift_score > 0.3:
    logger.warning("Drift detected. Consider retraining soon.")
```

### 3. Always Generate Report
Even if no drift, save the report for historical tracking:
```python
# Always run, always save
report_path, score, detected = generate_drift_report(...)
```

### 4. Only After Model Registration
Don't monitor if model failed to register:
```python
alias_result = promote_champion_model(best_model_name)
if alias_result is None:
    logger.error("Model promotion failed, skipping drift detection")
    return None
```

---

## Implementation

### Updated Prefect Flow (`heart_disease_prediction/prefect_flow.py`)

```python
"""
Full training pipeline with drift detection.
"""
import os
import mlflow
from prefect import flow, task, get_run_logger
from prefect.artifacts import create_link_artifact

# Existing imports
from heart_disease_prediction.data import load_data, preprocess_data
from heart_disease_prediction.train import train_all_models, select_best_model
from heart_disease_prediction.register import register_best_model

# New monitoring imports
from monitoring.generate_report import generate_report_with_fallback
from monitoring.cloudwatch_metrics import push_drift_metrics
from monitoring.config import DRIFT_THRESHOLD


@task(name="load_and_validate_data", retries=2)
def load_and_validate_data(data_path: str):
    """Load data and validate schema."""
    logger = get_run_logger()
    logger.info(f"Loading data from {data_path}")
    
    df = load_data(data_path)
    
    # Basic validation
    required_columns = [
        'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs',
        'restecg', 'thalach', 'exang', 'oldpeak',
        'slope', 'ca', 'thal', 'target'
    ]
    
    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    
    logger.info(f"✓ Loaded {len(df)} rows with {len(df.columns)} columns")
    return df


@task(name="preprocess", retries=1)
def preprocess(df):
    """Preprocess data for training."""
    logger = get_run_logger()
    logger.info("Preprocessing data...")
    
    X_train, X_test, y_train, y_test, preprocessor = preprocess_data(df)
    
    logger.info(f"✓ Train: {X_train.shape}, Test: {X_test.shape}")
    return X_train, X_test, y_train, y_test, preprocessor


@task(name="train_models")
def train_models(X_train, X_test, y_train, y_test, preprocessor):
    """Train all models and select best."""
    logger = get_run_logger()
    logger.info("Training models...")
    
    mlflow.set_experiment("heart-disease-training")
    
    with mlflow.start_run():
        results = train_all_models(
            X_train, X_test, y_train, y_test, preprocessor
        )
        best_model_name, best_model_info = select_best_model(results)
        
        logger.info(f"✓ Best model: {best_model_name}")
        logger.info(f"  Accuracy: {best_model_info['accuracy']:.3f}")
        
        return best_model_name, best_model_info, results


@task(name="register_model", retries=1)
def register_model(best_model_name: str, best_model_info: dict):
    """Register best model and set champion alias."""
    logger = get_run_logger()
    logger.info(f"Registering model: {best_model_name}")
    
    # This should now return the registered model name or raise
    registered_name = register_best_model(
        model_name=best_model_name,
        accuracy=best_model_info['accuracy']
    )
    
    if registered_name is None:
        raise ValueError("Model registration failed")
    
    logger.info(f"✓ Model registered: {registered_name}")
    return registered_name


@task(name="promote_champion", retries=1)
def promote_champion_model(model_name: str):
    """Set the 'champion' alias on the registered model."""
    logger = get_run_logger()
    logger.info(f"Setting champion alias for {model_name}")
    
    try:
        client = mlflow.tracking.MlflowClient()
        
        # Get latest version
        latest_versions = client.get_latest_versions(model_name)
        if not latest_versions:
            raise ValueError(f"No versions found for {model_name}")
        
        latest_version = latest_versions[0].version
        
        # Set champion alias
        client.set_registered_model_alias(
            name=model_name,
            alias="champion",
            version=latest_version
        )
        
        logger.info(f"✓ Champion alias set: {model_name} v{latest_version}")
        return model_name
        
    except Exception as e:
        logger.error(f"Failed to promote champion: {e}")
        raise


@task(name="drift_detection")
def run_drift_detection():
    """
    Generate drift report and push metrics to CloudWatch.
    
    This task:
    1. Loads reference data (training baseline)
    2. Loads current data (production features)
    3. Generates Evidently drift + quality reports
    4. Uploads HTML report to S3
    5. Appends drift score to history
    6. Pushes metrics to CloudWatch
    7. Returns drift status for flow control
    """
    logger = get_run_logger()
    logger.info("Starting drift detection...")
    
    try:
        # Generate report (handles fallback to raw data if needed)
        report_path, drift_score, drift_detected = generate_report_with_fallback()
        
        # Push to CloudWatch
        push_drift_metrics(drift_score, drift_detected)
        logger.info(f"✓ CloudWatch metrics pushed: score={drift_score:.3f}")
        
        # Create artifact link to report
        bucket = os.getenv("S3_BUCKET", "heart-disease-mlops-695074562426")
        report_url = f"s3://{bucket}/{report_path}"
        
        create_link_artifact(
            key="drift-report",
            link=report_url,
            description=f"Evidently drift report (score: {drift_score:.3f})"
        )
        
        # Alert on drift
        if drift_detected:
            logger.warning(
                f"🚨 DRIFT DETECTED! Score {drift_score:.3f} > threshold {DRIFT_THRESHOLD}\n"
                f"   Report: {report_url}\n"
                f"   Consider retraining the model."
            )
            
            # Optional: fail flow for catastrophic drift
            if drift_score > 0.8:
                raise ValueError(f"Catastrophic drift detected: {drift_score:.3f}")
        else:
            logger.info(f"✓ No drift detected (score: {drift_score:.3f})")
        
        return {
            "drift_score": drift_score,
            "drift_detected": drift_detected,
            "report_path": report_path,
            "report_url": report_url
        }
        
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        # Don't fail the entire flow for monitoring issues
        # but do log the error
        return {
            "drift_score": None,
            "drift_detected": None,
            "error": str(e)
        }


@flow(name="full-pipeline")
def full_pipeline(config: dict = None):
    """
    Full MLOps pipeline: train → register → monitor.
    
    Args:
        config: Pipeline configuration dict (optional, loads from env if not provided)
    """
    logger = get_run_logger()
    logger.info("=" * 50)
    logger.info("Starting Heart Disease Prediction Pipeline")
    logger.info("=" * 50)
    
    # Load config from env if not provided
    if config is None:
        config = {
            "data_path": os.getenv("DATA_PATH", "data/raw/processed.cleveland.data"),
            "mlflow_uri": os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
            "s3_bucket": os.getenv("S3_BUCKET"),
            "aws_region": os.getenv("AWS_REGION", "us-east-1")
        }
    
    # Set MLflow tracking
    mlflow.set_tracking_uri(config["mlflow_uri"])
    logger.info(f"MLflow URI: {config['mlflow_uri']}")
    
    # Step 1: Load data
    df = load_and_validate_data(config["data_path"])
    
    # Step 2: Preprocess
    X_train, X_test, y_train, y_test, preprocessor = preprocess(df)
    
    # Step 3: Train models
    best_model_name, best_model_info, all_results = train_models(
        X_train, X_test, y_train, y_test, preprocessor
    )
    
    # Step 4: Register model
    registered_name = register_model(best_model_name, best_model_info)
    
    # Step 5: Promote to champion (API will load this)
    champion_name = promote_champion_model(registered_name)
    
    # Step 6: Drift detection (only after successful registration)
    logger.info("-" * 50)
    logger.info("Running drift detection...")
    drift_result = run_drift_detection()
    
    # Summary
    logger.info("=" * 50)
    logger.info("Pipeline Complete!")
    logger.info(f"  Model: {champion_name}")
    logger.info(f"  Accuracy: {best_model_info['accuracy']:.3f}")
    if drift_result.get("drift_score") is not None:
        logger.info(f"  Drift Score: {drift_result['drift_score']:.3f}")
        logger.info(f"  Drift Detected: {drift_result['drift_detected']}")
    logger.info("=" * 50)
    
    return {
        "model_name": champion_name,
        "accuracy": best_model_info['accuracy'],
        "drift": drift_result
    }


if __name__ == "__main__":
    # Run locally for testing
    result = full_pipeline()
    print(f"\nPipeline result: {result}")
```

---

## Flow Visualization

```
┌────────────────────────────────────────────────────────────────┐
│                    FULL PIPELINE FLOW                           │
└────────────────────────────────────────────────────────────────┘

load_and_validate_data
        │
        ▼
    preprocess
        │
        ▼
    train_models ──► MLflow experiments logged
        │
        ▼
    register_model ──► Model registered in MLflow
        │
        ▼
    promote_champion_model ──► "champion" alias set
        │
        ▼
    run_drift_detection
        │
        ├──► Load reference data (S3)
        │
        ├──► Load current data (S3 or fallback)
        │
        ├──► Generate Evidently report
        │       │
        │       ├──► Data drift metrics
        │       └──► Data quality metrics
        │
        ├──► Save HTML to S3
        │
        ├──► Append score to drift_scores.jsonl
        │
        ├──► Push to CloudWatch
        │
        ├──► Create Prefect artifact (link to report)
        │
        └──► Alert if drift > threshold
                │
                ├──► Log warning (0.3 < drift < 0.8)
                │
                └──► Raise exception (drift > 0.8)
```

---

## Deployment Update

### Update `prefect.yaml`

Add environment variables for monitoring:

```yaml
# prefect.yaml
name: heart-disease-pipeline

build: null

push: null

pull:
  - prefect.deployments.steps.git_clone:
      repository: https://github.com/abandonedmonk/MLOps-Zoomcamp-Project.git
      branch: aws_migration

deployments:
  - name: heart-disease-pipeline
    entrypoint: heart_disease_prediction/prefect_flow.py:full_pipeline
    work_pool:
      name: default
    schedule:
      cron: "0 0 * * 0"  # Weekly on Sunday midnight
    parameters: {}
    enforce_parameter_schema: false
    
    # Environment variables for monitoring
    job_variables:
      env:
        MLFLOW_TRACKING_URI: "http://10.0.0.186:5000"
        AWS_REGION: "us-east-1"
        S3_BUCKET: "heart-disease-mlops-695074562426"
        DATA_PATH: "s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data"
        # Optional: current data for drift detection
        CURRENT_DATA_S3_KEY: "monitoring/current/current_data.parquet"
```

### Update EC2 User Data

Ensure monitoring dependencies are installed on EC2:

```bash
# In infra/user_data.sh.tftpl

# Install Python dependencies including Evidently
sudo /opt/mlflow-venv/bin/pip install \
    evidently==0.4.0 \
    pyarrow \
    boto3

# Verify installation
sudo /opt/mlflow-venv/bin/python -c "import evidently; print(f'Evidently {evidently.__version__}')"
```

---

## Testing the Integrated Flow

### Local Test

```bash
# Run locally first (Prefect server mode)
python -m heart_disease_prediction.prefect_flow

# You should see:
# 1. Model training
# 2. Model registration
# 3. Champion alias set
# 4. Drift detection
# 5. CloudWatch metrics pushed
# 6. Report saved to S3
```

### Deploy to Prefect

```bash
# Deploy with monitoring
prefect deploy prefect_flow.py:full_pipeline \
    --name heart-disease-pipeline \
    --pool default \
    --cron "0 0 * * 0"
```

### Trigger Manual Run

```bash
# Trigger from CLI
prefect deployment run full-pipeline/heart-disease-pipeline

# Or trigger from Prefect Cloud UI
```

---

## Verification Checklist

- [ ] Pipeline runs end-to-end without errors
- [ ] Model registered in MLflow
- [ ] Champion alias set successfully
- [ ] Drift report generated and saved to S3
- [ ] CloudWatch metrics pushed (verify in console)
- [ ] Prefect artifact created with S3 link
- [ ] Drift warning logged if score > 0.3
- [ ] Pipeline continues even if drift detection fails (graceful degradation)

---

## Monitoring Failures Gracefully

### Why Not Fail on Monitoring Errors?

Monitoring is **observability**, not **functionality**. The model can still work even if monitoring breaks:

```python
@task(name="drift_detection")
def run_drift_detection():
    try:
        # ... generate report ...
        return drift_result
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        # Return error info but don't stop pipeline
        return {"error": str(e), "drift_score": None}
```

### When to Fail

Only fail the pipeline for **catastrophic drift** (>0.8), not monitoring errors:

```python
if drift_score > 0.8:
    raise ValueError("Model unreliable due to catastrophic drift")
```

---

## Next Steps

Once drift detection is working:

1. **Automate retraining** — Phase 7 CI/CD will trigger new runs
2. **Feature store** — Store engineered features for drift comparison
3. **A/B testing** — Compare champion vs. challenger models
4. **Anomaly detection** — Use Isolation Forest for outlier detection

See Phase 7 (CI/CD) for automated pipeline triggers.
