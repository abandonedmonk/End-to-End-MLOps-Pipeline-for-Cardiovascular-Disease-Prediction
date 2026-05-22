from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import boto3
import pandas as pd
from botocore.exceptions import ClientError
from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset, DataQualityPreset
from evidently.report import Report

from monitoring.config import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERICAL_COLUMNS,
    get_config,
)
from monitoring.reference_data import build_reference_dataframe, save_reference_data


def _s3_client():
    config = get_config()
    return boto3.client("s3", region_name=config.aws_region)


def _read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    obj = _s3_client().get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def _object_exists(bucket: str, key: str) -> bool:
    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return False
        raise
    return True


def _load_feature_frame(uri: str) -> pd.DataFrame:
    if uri.startswith("s3://"):
        parsed = urlparse(uri)
        df = _read_parquet_from_s3(parsed.netloc, parsed.path.lstrip("/"))
    else:
        df = pd.read_parquet(uri)

    missing = sorted(set(FEATURE_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(f"Current data is missing feature columns: {missing}")

    return df[FEATURE_COLUMNS].copy()


def _load_reference_data() -> pd.DataFrame:
    config = get_config()
    if not _object_exists(config.s3_bucket, config.reference_data_key):
        save_reference_data(config.fallback_data_path)

    return _read_parquet_from_s3(config.s3_bucket, config.reference_data_key)[
        FEATURE_COLUMNS
    ].copy()


def _load_current_data() -> pd.DataFrame:
    config = get_config()
    if _object_exists(config.s3_bucket, config.current_data_key):
        return _load_feature_frame(config.current_data_uri)

    return build_reference_dataframe(config.fallback_data_path)


def _normalize_feature_types(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df[FEATURE_COLUMNS].copy()
    for column in CATEGORICAL_COLUMNS:
        normalized[column] = normalized[column].astype(str)
    for column in NUMERICAL_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized


def _extract_drift_score(report_dict: dict) -> tuple[float, bool]:
    for metric in report_dict.get("metrics", []):
        result = metric.get("result", {})
        if "share_of_drifted_columns" in result:
            score = float(result["share_of_drifted_columns"])
            return score, score > get_config().drift_threshold
        if "dataset_drift" in result and "number_of_columns" in result:
            drifted = float(result.get("number_of_drifted_columns", 0))
            total = float(result.get("number_of_columns", 1))
            score = drifted / total if total else 0.0
            return score, bool(result["dataset_drift"])

    return 0.0, False


def _append_metrics_history(record: dict) -> None:
    config = get_config()
    client = _s3_client()
    existing = ""

    if _object_exists(config.s3_bucket, config.metrics_key):
        existing = (
            client.get_object(Bucket=config.s3_bucket, Key=config.metrics_key)["Body"]
            .read()
            .decode("utf-8")
        )

    body = f"{existing}{json.dumps(record, sort_keys=True)}\n"
    client.put_object(
        Bucket=config.s3_bucket,
        Key=config.metrics_key,
        Body=body.encode("utf-8"),
        ContentType="application/jsonlines",
    )


def generate_drift_report() -> dict:
    config = get_config()
    reference_df = _normalize_feature_types(_load_reference_data())
    current_df = _normalize_feature_types(_load_current_data())

    column_mapping = ColumnMapping(
        numerical_features=NUMERICAL_COLUMNS,
        categorical_features=CATEGORICAL_COLUMNS,
    )
    report = Report(metrics=[DataDriftPreset(), DataQualityPreset()])
    report.run(
        reference_data=reference_df,
        current_data=current_df,
        column_mapping=column_mapping,
    )

    report_dict = report.as_dict()
    drift_score, drift_detected = _extract_drift_score(report_dict)

    report_date = date.today().isoformat()
    report_key = f"{config.reports_prefix}/{report_date}/drift_report.html"
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "drift_report.html"
        report.save_html(str(report_path))
        _s3_client().upload_file(
            str(report_path),
            config.s3_bucket,
            report_key,
            ExtraArgs={"ContentType": "text/html"},
        )

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "drift_score": drift_score,
        "drift_detected": drift_detected,
        "threshold": config.drift_threshold,
        "report_uri": f"s3://{config.s3_bucket}/{report_key}",
        "reference_rows": len(reference_df),
        "current_rows": len(current_df),
    }
    _append_metrics_history(record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Evidently drift report.")
    parser.parse_args()

    result = generate_drift_report()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
