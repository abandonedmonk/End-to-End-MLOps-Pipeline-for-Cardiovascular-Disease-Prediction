import os
import sys
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from prefect import flow, task, get_run_logger
try:
    from .data import get_data, split_data_for_train
    from .register import register_model
    from .train import train_model
    from .load_model import load_model
except ImportError:
    from data import get_data, split_data_for_train
    from register import register_model
    from train import train_model
    from load_model import load_model

load_dotenv()

PIPELINE_CONFIG = {
    "data_path": os.getenv("DATA_PATH", "../data/raw/processed.cleveland.data"),
    "mlflow_tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db"),
    "mlflow_artifact_root": os.getenv("MLFLOW_ARTIFACT_ROOT", "file://mlruns/"),
    "experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline"),
    "model_name": os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}"),
}

@task(name="drift_detection", retries=2)
def run_drift_detection() -> bool:
    """Generate an Evidently report and publish drift metrics to CloudWatch."""
    logger = get_run_logger()

    try:
        from monitoring.cloudwatch_metrics import (
            get_fastapi_log_counts,
            push_monitoring_metrics,
        )
        from monitoring.config import get_config
        from monitoring.generate_report import generate_drift_report
    except ImportError:
        project_root = Path(__file__).resolve().parents[1]
        if str(project_root) not in sys.path:
            sys.path.append(str(project_root))

        from monitoring.cloudwatch_metrics import (
            get_fastapi_log_counts,
            push_monitoring_metrics,
        )
        from monitoring.config import get_config
        from monitoring.generate_report import generate_drift_report

    config = get_config()
    result = generate_drift_report()
    prediction_count, error_5xx_count = get_fastapi_log_counts()
    push_monitoring_metrics(
        drift_score=result["drift_score"],
        prediction_count=prediction_count,
        error_5xx_count=error_5xx_count,
    )

    logger.info(
        "Drift report saved to %s with score %.4f",
        result["report_uri"],
        result["drift_score"],
    )

    if result["drift_score"] > config.drift_threshold:
        logger.warning(
            "DRIFT DETECTED! score=%.4f threshold=%.4f. Retraining recommended.",
            result["drift_score"],
            config.drift_threshold,
        )
        return True

    logger.info("No drift detected.")
    return False

@flow
def full_pipeline():
    df = get_data(path=PIPELINE_CONFIG["data_path"])
    X_train, X_test, y_train, y_test, preprocessor = split_data_for_train(df)
    _, pipeline, paths = train_model(X_train, X_test, y_train, y_test, preprocessor, config=PIPELINE_CONFIG)
    paths = {**PIPELINE_CONFIG, **paths}
    paths = register_model(pipeline, paths)
    if not paths:
        raise RuntimeError("Model registration failed; skipping model promotion and drift detection.")
    load_model(paths)
    run_drift_detection()

if __name__ == "__main__":
    full_pipeline()

# prefect deploy prefect_flow.py:full_pipeline --name heart-disease --work-queue default --cron "0 0 * * 0"
