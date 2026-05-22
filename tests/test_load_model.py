import mlflow
import numpy as np
import pandas as pd
import pytest
from mlflow.tracking import MlflowClient
from sklearn.pipeline import Pipeline

from heart_disease_prediction.load_model import load_champion_model


def _register_model_version(mock_mlflow, dummy_model, model_name):
    mlflow.set_tracking_uri(mock_mlflow["tracking_uri"])
    mlflow.set_experiment("pytest-load-model")
    with mlflow.start_run() as run:
        mlflow.sklearn.log_model(dummy_model, "model")
    result = mlflow.register_model(f"runs:/{run.info.run_id}/model", model_name)
    return result


def test_load_champion_model_by_alias(mock_mlflow, dummy_model):
    """Validate champion alias loading returns a model with predict support."""
    model_name = "pytest-load-champion"
    result = _register_model_version(mock_mlflow, dummy_model, model_name)
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    client.set_registered_model_alias(model_name, "champion", result.version)

    loaded = load_champion_model(
        {"mlflow_tracking_uri": mock_mlflow["tracking_uri"], "model_name": model_name}
    )

    assert isinstance(loaded, Pipeline)
    assert hasattr(loaded, "predict")


def test_load_champion_model_falls_back_to_production(mock_mlflow, dummy_model):
    """Validate Production stage is used when no champion alias exists."""
    model_name = "pytest-load-production"
    result = _register_model_version(mock_mlflow, dummy_model, model_name)
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    client.transition_model_version_stage(model_name, result.version, "Production")

    loaded = load_champion_model(
        {"mlflow_tracking_uri": mock_mlflow["tracking_uri"], "model_name": model_name}
    )

    assert hasattr(loaded, "predict")


def test_load_champion_model_raises_when_missing(mock_mlflow):
    """Validate a missing champion and Production model raises a clear error."""
    with pytest.raises(ValueError, match="No champion or Production model found"):
        load_champion_model(
            {
                "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
                "model_name": "pytest-missing-model",
            }
        )


def test_loaded_model_can_predict_binary_values(mock_mlflow, dummy_model):
    """Validate loaded registry model predicts 0/1 values for sample rows."""
    model_name = "pytest-load-predict"
    result = _register_model_version(mock_mlflow, dummy_model, model_name)
    MlflowClient(tracking_uri=mock_mlflow["tracking_uri"]).set_registered_model_alias(
        model_name, "champion", result.version
    )
    loaded = load_champion_model(
        {"mlflow_tracking_uri": mock_mlflow["tracking_uri"], "model_name": model_name}
    )
    features = pd.DataFrame({"age": [54, 61]})

    predictions = loaded.predict(features)

    assert isinstance(predictions, np.ndarray)
    assert set(predictions).issubset({0, 1})
