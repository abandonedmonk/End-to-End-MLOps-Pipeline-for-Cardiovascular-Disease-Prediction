import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
from typing import Tuple
from sklearn.metrics import accuracy_score, precision_score, f1_score, recall_score
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.base import ClassifierMixin
from sklearn.compose import ColumnTransformer
from typing import Dict
from prefect import task, get_run_logger
import os
from pathlib import Path
from dotenv import load_dotenv

import yaml
from mlflow.tracking import MlflowClient
import logging

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT}/mlruns/mlflow.db")
MLFLOW_ARTIFACT_ROOT = os.getenv("MLFLOW_ARTIFACT_ROOT", f"file://{PROJECT_ROOT}/mlruns/")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "heart-disease-experiment-pipeline")

def get_or_create_experiment_id(name: str, artifact_root: str) -> str:
    """
    Fully controlled MLflow experiment setup with safe artifact path and meta.yaml recovery.
    """
    client = MlflowClient()
    experiment = client.get_experiment_by_name(name)

    if experiment:
        print(f"🔍 Checking experiment: {name} at {experiment.artifact_location}")
        return experiment.experiment_id

    print(f"🚀 Creating new experiment at {artifact_root}")
    os.makedirs(artifact_root.replace("file://", ""), exist_ok=True)
    return client.create_experiment(name=name, artifact_location=artifact_root)

@task
def train_model(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: pd.Series,
    y_test: pd.Series,
    preprocessor: ColumnTransformer,
    config: Dict | None = None,
) -> Tuple[ClassifierMixin, Pipeline, Dict]:
    """
    Train multiple models, log experiments with MLflow, return best model
    """

    try:
        logger = get_run_logger()
    except RuntimeError:
        logger = logging.getLogger(__name__)

    config = config or {}

    # Set up MLflow
    # Path for each file
    if '__file__' in globals():
        project_root = Path(__file__).resolve().parents[1]
    else:
        project_root = Path(os.getcwd()).parent  # fallback for Jupyter

    paths = {
        "mlflow_tracking_uri": config.get("mlflow_tracking_uri", MLFLOW_TRACKING_URI),
        "mlflow_artifact_root": config.get("mlflow_artifact_root", MLFLOW_ARTIFACT_ROOT),
        "experiment_name": config.get("experiment_name", EXPERIMENT_NAME),
        "model_name": config.get("model_name"),
        "data_path": config.get("data_path"),
        "final_save_dir": f"{project_root}/models/",
    }

    paths["mlflow_db_path"] = paths["mlflow_tracking_uri"]
    paths["artifact_loc"] = paths["mlflow_artifact_root"]

    mlflow.set_tracking_uri(paths["mlflow_tracking_uri"])
    experiment_id = get_or_create_experiment_id(name=paths["experiment_name"], artifact_root=paths["mlflow_artifact_root"])

    mlflow.set_experiment(experiment_name=paths["experiment_name"])
    print(f"Experiment ID: {experiment_id}")

    # Define models to train
    models = {
        "LogisticRegression": LogisticRegression(max_iter=1000),
        "RandomForest": RandomForestClassifier(n_estimators=100, random_state=42),
        "HistGradientBoosting": HistGradientBoostingClassifier(random_state=42),
        "DecisionTree": DecisionTreeClassifier(ccp_alpha=0.0135, random_state=42) # CCP Alpha found from notebook experiment
    }

    best_model = None
    best_pipeline = None
    best_score = -1

    for name, model in models.items():
        with mlflow.start_run(run_name=name):

            # Create a pipeline with preprocessor and model so the datatype doesn't change while inferencing
            pipeline = Pipeline(steps=[
                ('preprocessor', preprocessor),
                ('classifier', model)
            ])
            pipeline.fit(X_train, y_train)
            y_pred = pipeline.predict(X_test)
            acc = accuracy_score(y_test, y_pred)

            # Log with MLflow
            mlflow.log_param("model", name)

            # Calculate and log metrics
            metrics = {
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred, average="weighted"),
                "recall": recall_score(y_test, y_pred, average="weighted"),
                "f1_score": f1_score(y_test, y_pred, average="weighted"),
            }
            mlflow.log_metrics(metrics)

            # Log Model
            mlflow.sklearn.log_model(
                sk_model=pipeline,
                artifact_path="model"
            )

            logger.info(f"{name} accuracy: {acc:.4f}")

            if acc > best_score:
                best_score = acc
                best_model = model
                best_pipeline = pipeline

    logger.info(f"✅ Best model selected with accuracy {best_score:.4f}")
    return best_model, best_pipeline, paths
