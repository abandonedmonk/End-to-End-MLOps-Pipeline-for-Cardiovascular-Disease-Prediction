import mlflow
import pytest
from mlflow.tracking import MlflowClient

from heart_disease_prediction.register import register_model


def _log_candidate_model(experiment_name, model, accuracy):
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run() as run:
        mlflow.log_metric("accuracy", accuracy)
        mlflow.sklearn.log_model(model, "model")
        return run.info.run_id


def test_register_model_finds_best_run_and_sets_champion(mock_mlflow, dummy_model):
    """Validate registration picks the highest accuracy run and assigns champion alias."""
    experiment_name = "pytest-register-best"
    model_name = "pytest-registered-model"
    _log_candidate_model(experiment_name, dummy_model, 0.55)
    best_run_id = _log_candidate_model(experiment_name, dummy_model, 0.91)

    result = register_model.fn(
        dummy_model,
        {
            "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
            "experiment_name": experiment_name,
            "model_name": model_name,
        },
    )

    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    champion = client.get_model_version_by_alias(model_name, "champion")

    assert result["model_uri"] == f"models:/{model_name}@champion"
    assert champion.run_id == best_run_id


def test_register_model_raises_when_no_runs_found(mock_mlflow, dummy_model):
    """Validate registration fails clearly when an experiment has no candidate runs."""
    mlflow.set_experiment("pytest-empty-register")

    with pytest.raises(ValueError, match="No MLflow runs found"):
        register_model.fn(
            dummy_model,
            {
                "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
                "experiment_name": "pytest-empty-register",
                "model_name": "pytest-empty-model",
            },
        )


def test_register_model_propagates_mlflow_connection_failure(monkeypatch, dummy_model):
    """Validate MLflow client failures are not swallowed by registration."""

    def fail_set_tracking_uri(*args, **kwargs):
        raise RuntimeError("tracking backend unavailable")

    monkeypatch.setattr(mlflow, "set_tracking_uri", fail_set_tracking_uri)

    with pytest.raises(RuntimeError, match="tracking backend unavailable"):
        register_model.fn(
            dummy_model,
            {
                "mlflow_tracking_uri": "sqlite:///unreachable.db",
                "experiment_name": "pytest-failure",
                "model_name": "pytest-failure-model",
            },
        )
