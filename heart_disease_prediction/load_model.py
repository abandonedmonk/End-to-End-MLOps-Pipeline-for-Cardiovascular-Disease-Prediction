import os
import pickle
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from typing import Tuple, Dict
from datetime import date
from pathlib import Path

def load_model(
    paths: Dict,
    # save_dir: str = "../models/"
) -> Tuple[str, str]:
    assert isinstance(paths["model_name"], str), "model_name must be a string"
    assert isinstance(paths["experiment_name"], str), "experiment_name must be a string"

    # Ensure tracking URI is set
    mlflow.set_tracking_uri(paths["mlflow_db_path"])
    client = MlflowClient()

    # Get the latest version(s) (filtering by model name only)
    results = client.search_model_versions(
        f"name='{paths['model_name']}'")

    # Optionally filter out only those without any alias set (like stage=None)
    versions = [v for v in results if not v.aliases]

    # Sort by version number (as string)
    versions = sorted(versions, key=lambda v: int(v.version), reverse=True)

    # Take the latest one (optional)
    latest_version = versions[0] if versions else None

        # Transition to Production
    client.set_registered_model_alias(
            name=paths["model_name"],
            alias="champion",
            version=latest_version.version,
        )

    print(f"✅ Model {paths["model_name"]} v{latest_version.version} moved to Production.")

if __name__ == "__main__":
    if '__file__' in globals():
        project_root = Path(__file__).resolve().parents[1]
    paths = {
        "model_name": "best_model_2025-07-30",
        "mlflow_db_path": f"sqlite:///{project_root}/mlruns/mlflow.db",
        "artifact_loc": f"file://{project_root}/mlruns/artifacts/",
        "experiment_name": "heart-disease-experiment-pipeline",
        "final_save_dir": f"{project_root}/models/"
    }
    load_model(paths)