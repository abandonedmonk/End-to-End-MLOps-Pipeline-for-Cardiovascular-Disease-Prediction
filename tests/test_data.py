from pathlib import Path

import boto3
import pandas as pd
import pytest
from moto import mock_aws
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

from heart_disease_prediction import data


EXPECTED_COLUMNS = [
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


def test_load_data_returns_expected_schema(raw_data_path):
    """Validate raw Cleveland data loads with the expected 303x14 schema."""
    df = data.get_data.fn(str(raw_data_path))

    assert df.shape == (303, 14)
    assert list(df.columns) == EXPECTED_COLUMNS
    assert set(df["hd"].astype(int).unique()).issubset({0, 1})


def test_prepare_data_splits_and_binarizes_target(sample_dataframe):
    """Validate train/test split sizes, binary targets, and preprocessor type."""
    X_train, X_test, y_train, y_test, preprocessor = data.split_data_for_train.fn(
        sample_dataframe
    )

    assert len(X_train) == 40
    assert len(X_test) == 10
    assert set(y_train.unique()).issubset({0, 1})
    assert set(y_test.unique()).issubset({0, 1})
    assert isinstance(preprocessor, ColumnTransformer)


def test_preprocessor_handles_numeric_and_categorical_columns(prepared_data):
    """Validate the preprocessor has numeric passthrough and categorical encoder steps."""
    X_train, _, _, _, preprocessor = prepared_data
    transformed = preprocessor.fit_transform(X_train)
    transformers = dict((name, transformer) for name, transformer, _ in preprocessor.transformers)

    assert transformers["num"] == "passthrough"
    assert isinstance(transformers["cat"], OneHotEncoder)
    assert transformed.shape[0] == len(X_train)
    assert transformed.shape[1] > X_train.shape[1]


@mock_aws
def test_s3_data_loading_downloads_to_cache(sample_data_file, monkeypatch, tmp_path):
    """Validate s3:// paths trigger a boto3 download into the local cache."""
    bucket = "test-heart-disease-bucket"
    key = "data/raw/heart.csv"
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
    boto3.client("s3", region_name="us-east-1").upload_file(
        str(sample_data_file), bucket, key
    )
    monkeypatch.setattr(data, "LOCAL_DATA_CACHE", tmp_path / "cache")

    resolved = data._resolve_data_path(f"s3://{bucket}/{key}")

    assert Path(resolved).exists()
    assert Path(resolved).parent == tmp_path / "cache"


def test_local_data_loading_bypasses_s3(sample_data_file, monkeypatch):
    """Validate local paths are returned directly without calling boto3."""
    called = False

    def fail_client(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("boto3 should not be called for local files")

    monkeypatch.setattr(data.boto3, "client", fail_client)

    assert data._resolve_data_path(str(sample_data_file)) == str(sample_data_file)
    assert called is False


def test_missing_local_file_raises_clear_error(tmp_path):
    """Validate missing local files surface as FileNotFoundError."""
    missing = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        data.get_data.fn(str(missing))
