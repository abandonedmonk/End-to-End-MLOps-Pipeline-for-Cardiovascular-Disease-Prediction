import importlib
import os
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "processed.cleveland.data"
RAW_COLUMNS = [
    "age",
    "sex",
    "cp",
    "trestbps",
    "chol",
    "fbs",
    "restecg",
    "thalach",
    "exang",
    "oldpeak",
    "slope",
    "ca",
    "thal",
    "hd",
]


@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    """Provide safe environment variables so tests never target live services."""
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET", "test-heart-disease-bucket")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", f"file://{tmp_path / 'artifacts'}")
    monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", "pytest-heart-disease")
    monkeypatch.setenv("MODEL_NAME", "pytest-heart-disease-model")
    monkeypatch.setenv("DATA_PATH", str(DATA_PATH))
    monkeypatch.setenv("LOCAL_DATA_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("REFERENCE_DATA_S3_KEY", "data/reference/reference_data.parquet")
    monkeypatch.setenv("CURRENT_DATA_S3_KEY", "monitoring/current/current_data.parquet")
    monkeypatch.setenv("MONITORING_REPORTS_PREFIX", "monitoring/reports")
    monkeypatch.setenv("DRIFT_METRICS_S3_KEY", "monitoring/metrics/drift_scores.jsonl")
    monkeypatch.setenv("CLOUDWATCH_NAMESPACE", "HeartDisease/Test")
    yield


@pytest.fixture
def mock_mlflow(tmp_path):
    """Create an isolated local MLflow tracking store for a test."""
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artifact_root = tmp_path / "mlartifacts"
    artifact_root.mkdir()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("pytest-heart-disease")
    yield {"tracking_uri": tracking_uri, "artifact_root": f"file://{artifact_root}"}
    mlflow.end_run()


@pytest.fixture
def raw_data_path():
    """Return the checked-in Cleveland raw data file."""
    return DATA_PATH


@pytest.fixture
def full_dataframe():
    """Load the full raw dataset with the production schema."""
    df = pd.read_csv(DATA_PATH, header=None)
    df.columns = RAW_COLUMNS
    return df


@pytest.fixture
def sample_dataframe(full_dataframe):
    """Return a deterministic, cleaned sample with realistic heart-disease columns."""
    df = full_dataframe.loc[
        (full_dataframe["ca"] != "?") & (full_dataframe["thal"] != "?")
    ].head(50)
    return df.copy()


@pytest.fixture
def sample_data_file(sample_dataframe, tmp_path):
    """Write a small headerless Cleveland-shaped dataset to disk."""
    path = tmp_path / "heart.csv"
    sample_dataframe.to_csv(path, header=False, index=False)
    return path


@pytest.fixture
def prepared_data(sample_dataframe):
    """Build the same train/test/preprocessor tuple used by training."""
    from heart_disease_prediction.data import split_data_for_train

    return split_data_for_train.fn(sample_dataframe)


@pytest.fixture
def patient_payload():
    """Return a valid API payload for one heart-disease prediction."""
    return {
        "age": 54,
        "sex": 1,
        "cp": 1,
        "trestbps": 140,
        "chol": 239,
        "fbs": 0,
        "restecg": 1,
        "thalach": 160,
        "exang": 0,
        "oldpeak": 1.2,
        "slope": 1,
        "ca": 2,
        "thal": 3,
    }


class DummyHeartModel(BaseEstimator, ClassifierMixin):
    """Small sklearn-compatible classifier used by API and registry tests."""

    classes_ = np.array([0, 1])

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        return np.ones(len(X), dtype=int)

    def predict_proba(self, X):
        return np.tile(np.array([[0.2, 0.8]]), (len(X), 1))


@pytest.fixture
def dummy_model():
    """Return a deterministic sklearn Pipeline-compatible model."""
    return Pipeline([("classifier", DummyHeartModel())])


@pytest.fixture
def import_fresh():
    """Import a module after removing any cached copy."""

    def _import(module_name: str):
        importlib.invalidate_caches()
        for cached in list(os.sys.modules):
            if cached == module_name or cached.startswith(f"{module_name}."):
                os.sys.modules.pop(cached)
        return importlib.import_module(module_name)

    return _import
