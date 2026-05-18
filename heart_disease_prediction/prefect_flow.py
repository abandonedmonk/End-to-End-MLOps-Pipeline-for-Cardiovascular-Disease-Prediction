import os
from datetime import date
from dotenv import load_dotenv
from prefect import flow, task
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

@flow
def full_pipeline():
    df = get_data(path=PIPELINE_CONFIG["data_path"])
    X_train, X_test, y_train, y_test, preprocessor = split_data_for_train(df)
    _, pipeline, paths = train_model(X_train, X_test, y_train, y_test, preprocessor, config=PIPELINE_CONFIG)
    paths = {**PIPELINE_CONFIG, **paths}
    paths = register_model(pipeline, paths)
    load_model(paths)

if __name__ == "__main__":
    full_pipeline()

# prefect deploy prefect_flow.py:full_pipeline --name heart-disease --work-queue default --cron "0 0 * * 0"