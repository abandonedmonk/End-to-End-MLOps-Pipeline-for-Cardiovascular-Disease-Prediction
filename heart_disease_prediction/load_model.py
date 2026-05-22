import os
import pickle
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from typing import Tuple, Dict
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT}/mlruns/mlflow.db")
MODEL_NAME = os.getenv("MODEL_NAME", f"best_model_{date.today().isoformat()}")

def load_model(
    paths: Dict | None = None,
    # save_dir: str = "../models/"
) -> Tuple[str, str]:
    paths = paths or {}
    model_name = paths.get("model_name", MODEL_NAME)
    experiment_name = paths.get("experiment_name", os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline"))

    assert isinstance(model_name, str), "model_name must be a string"
    assert isinstance(experiment_name, str), "experiment_name must be a string"

    # Ensure tracking URI is set
    mlflow.set_tracking_uri(paths.get("mlflow_tracking_uri", MLFLOW_TRACKING_URI))
    client = MlflowClient()

    # Get the latest version(s) (filtering by model name only)
    results = client.search_model_versions(
        f"name='{model_name}'")

    # Optionally filter out only those without any alias set (like stage=None)
    versions = [v for v in results if not v.aliases]

    # Sort by version number (as string)
    versions = sorted(versions, key=lambda v: int(v.version), reverse=True)

    # Take the latest one (optional)
    latest_version = versions[0] if versions else None

    if latest_version is None:
        raise ValueError(f"No registered versions found for model {model_name}")

    # Transition to Production
    client.set_registered_model_alias(
        name=model_name,
        alias="champion",
        version=latest_version.version,
    )

    print(f"✅ Model {model_name} v{latest_version.version} moved to Production.")
    return model_name, latest_version.version


def load_champion_model(paths: Dict | None = None):
    """Load the registered champion model, falling back to Production stage."""
    paths = paths or {}
    model_name = paths.get("model_name", MODEL_NAME)
    tracking_uri = paths.get("mlflow_tracking_uri", MLFLOW_TRACKING_URI)

    mlflow.set_tracking_uri(tracking_uri)
    errors = []
    for model_uri in (f"models:/{model_name}@champion", f"models:/{model_name}/Production"):
        try:
            return mlflow.sklearn.load_model(model_uri)
        except Exception as exc:
            errors.append(f"{model_uri}: {exc}")

    raise ValueError(
        f"No champion or Production model found for {model_name}. "
        f"Attempts: {'; '.join(errors)}"
    )

if __name__ == "__main__":
    if '__file__' in globals():
        project_root = Path(__file__).resolve().parents[1]
    paths = {
        "model_name": MODEL_NAME,
        "mlflow_tracking_uri": MLFLOW_TRACKING_URI,
        "artifact_loc": f"file://{project_root}/mlruns/artifacts/",
        "experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline"),
        "final_save_dir": f"{project_root}/models/"
    }
    load_model(paths)
