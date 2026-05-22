import mlflow
import pytest
from mlflow.tracking import MlflowClient
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from heart_disease_prediction.train import train_model


def test_all_configured_models_train_without_error(prepared_data):
    """Validate the four production classifier types can fit the prepared data."""
    X_train, _, y_train, _, preprocessor = prepared_data
    models = [
        LogisticRegression(max_iter=1000),
        RandomForestClassifier(n_estimators=10, random_state=42),
        HistGradientBoostingClassifier(random_state=42),
        DecisionTreeClassifier(ccp_alpha=0.0135, random_state=42),
    ]

    for model in models:
        pipeline = Pipeline([("preprocessor", preprocessor), ("classifier", model)])
        pipeline.fit(X_train, y_train)
        assert hasattr(pipeline, "predict")


def test_train_model_logs_metrics_and_artifacts(prepared_data, mock_mlflow):
    """Validate training logs accuracy, precision, recall, f1, and model artifacts."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "mlflow_artifact_root": mock_mlflow["artifact_root"],
        "experiment_name": "pytest-heart-disease",
        "model_name": "pytest-heart-disease-model",
    }

    best_model, best_pipeline, paths = train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config=config
    )

    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-heart-disease")
    runs = client.search_runs([experiment.experiment_id])

    assert best_model is not None
    assert hasattr(best_pipeline, "predict")
    assert paths["experiment_name"] == "pytest-heart-disease"
    assert len(runs) == 4
    for run in runs:
        assert 0 <= run.data.metrics["accuracy"] <= 1
        assert {"precision", "recall", "f1_score"}.issubset(run.data.metrics)
        assert client.list_artifacts(run.info.run_id, "model")


def test_best_model_selection_matches_highest_accuracy(prepared_data, mock_mlflow):
    """Validate the returned model corresponds to the highest logged accuracy run."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "mlflow_artifact_root": mock_mlflow["artifact_root"],
        "experiment_name": "pytest-best-model",
    }

    best_model, _, _ = train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config=config
    )

    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-best-model")
    best_run = client.search_runs(
        [experiment.experiment_id], order_by=["metrics.accuracy DESC"], max_results=1
    )[0]

    class_to_logged_name = {
        "LogisticRegression": "LogisticRegression",
        "RandomForestClassifier": "RandomForest",
        "HistGradientBoostingClassifier": "HistGradientBoosting",
        "DecisionTreeClassifier": "DecisionTree",
    }
    assert class_to_logged_name[best_model.__class__.__name__] == best_run.data.params["model"]


def test_cross_validation_scores_are_reasonable(prepared_data):
    """Validate cross-validation computes stable scores above a minimal baseline."""
    X_train, _, y_train, _, preprocessor = prepared_data
    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=1000)),
        ]
    )

    scores = cross_val_score(pipeline, X_train, y_train, cv=3, scoring="accuracy")

    assert len(scores) == 3
    assert scores.mean() > 0.5
