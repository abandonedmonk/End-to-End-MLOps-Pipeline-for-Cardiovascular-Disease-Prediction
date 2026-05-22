from unittest.mock import Mock

import pandas as pd

from heart_disease_prediction import prefect_flow


def test_load_data_task_returns_dataframe(sample_data_file):
    """Validate the pipeline data task loads a DataFrame from local data."""
    df = prefect_flow.get_data.fn(str(sample_data_file))

    assert isinstance(df, pd.DataFrame)
    assert "hd" in df.columns


def test_train_models_task_returns_best_model_info(prepared_data, monkeypatch):
    """Validate the orchestration training task returns model, pipeline, and paths."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data

    def fake_train(*args, **kwargs):
        return "model", "pipeline", {"model_name": "pytest-model"}

    monkeypatch.setattr(prefect_flow.train_model, "fn", fake_train)
    result = prefect_flow.train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config={}
    )

    assert result == ("model", "pipeline", {"model_name": "pytest-model"})


def test_register_model_task_succeeds(monkeypatch):
    """Validate the orchestration registration task can return updated paths."""
    paths = {"model_name": "pytest-model"}

    def fake_register(*args, **kwargs):
        return {**paths, "model_uri": "models:/pytest-model@champion"}

    monkeypatch.setattr(prefect_flow.register_model, "fn", fake_register)

    assert prefect_flow.register_model.fn("pipeline", paths)["model_uri"].endswith(
        "@champion"
    )


def test_flow_composition_can_be_built():
    """Validate the full pipeline flow object exposes the expected Prefect metadata."""
    assert prefect_flow.full_pipeline.name == "full-pipeline"
    assert callable(prefect_flow.full_pipeline.fn)


def test_full_pipeline_runs_with_mocked_external_services(monkeypatch, sample_dataframe):
    """Validate flow composition runs when MLflow, S3, and monitoring are mocked."""
    calls = Mock()

    def fake_get_data(path):
        calls.get_data(path)
        return sample_dataframe

    def fake_split_data_for_train(df):
        calls.split(df)
        return "X_train", "X_test", "y_train", "y_test", "preprocessor"

    def fake_train_model(*args, **kwargs):
        calls.train(*args, **kwargs)
        return "model", "pipeline", {"model_name": "pytest-model"}

    def fake_register_model(pipeline, paths):
        calls.register(pipeline, paths)
        return {**paths, "model_uri": "models:/pytest-model@champion"}

    monkeypatch.setattr(prefect_flow, "get_data", fake_get_data)
    monkeypatch.setattr(prefect_flow, "split_data_for_train", fake_split_data_for_train)
    monkeypatch.setattr(prefect_flow, "train_model", fake_train_model)
    monkeypatch.setattr(prefect_flow, "register_model", fake_register_model)
    monkeypatch.setattr(prefect_flow, "load_model", lambda paths: calls.load(paths))
    monkeypatch.setattr(prefect_flow, "run_drift_detection", lambda: calls.drift())

    prefect_flow.full_pipeline.fn()

    assert calls.get_data.called
    assert calls.train.called
    assert calls.register.called
    assert calls.load.called
    assert calls.drift.called
