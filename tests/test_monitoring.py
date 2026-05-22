from io import BytesIO
from unittest.mock import Mock

import boto3
import pandas as pd
from moto import mock_aws

from monitoring import cloudwatch_metrics, generate_report, reference_data
from monitoring.config import FEATURE_COLUMNS, get_config


@mock_aws
def test_reference_data_creation_saves_expected_columns(sample_data_file):
    """Validate reference data is saved to S3 with the expected feature columns."""
    config = get_config()
    boto3.client("s3", region_name=config.aws_region).create_bucket(Bucket=config.s3_bucket)

    uri = reference_data.save_reference_data(str(sample_data_file))
    obj = boto3.client("s3", region_name=config.aws_region).get_object(
        Bucket=config.s3_bucket, Key=config.reference_data_key
    )
    saved = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert uri == config.reference_data_uri
    assert list(saved.columns) == FEATURE_COLUMNS
    assert len(saved) > 0


@mock_aws
def test_drift_report_generation_uploads_report_and_metrics(
    monkeypatch, sample_data_file
):
    """Validate drift report generation uploads HTML and writes drift summary metrics."""
    config = get_config()
    client = boto3.client("s3", region_name=config.aws_region)
    client.create_bucket(Bucket=config.s3_bucket)
    monkeypatch.setenv("DATA_PATH", str(sample_data_file))

    class FakeReport:
        def __init__(self, metrics):
            self.metrics = metrics

        def run(self, reference_data, current_data, column_mapping):
            self.reference_rows = len(reference_data)
            self.current_rows = len(current_data)

        def as_dict(self):
            return {
                "metrics": [
                    {"result": {"share_of_drifted_columns": 0.1}},
                ]
            }

        def save_html(self, path):
            with open(path, "w", encoding="utf-8") as report_file:
                report_file.write("<html>drift</html>")

    monkeypatch.setattr(generate_report, "Report", FakeReport)

    result = generate_report.generate_drift_report()
    report_key = result["report_uri"].split(f"s3://{config.s3_bucket}/", 1)[1]
    report_object = client.get_object(Bucket=config.s3_bucket, Key=report_key)
    metrics_object = client.get_object(Bucket=config.s3_bucket, Key=config.metrics_key)

    assert result["drift_score"] == 0.1
    assert result["drift_detected"] is False
    assert b"drift" in report_object["Body"].read()
    assert b"drift_score" in metrics_object["Body"].read()


def test_cloudwatch_metrics_include_namespace_and_model_dimension(monkeypatch):
    """Validate CloudWatch metrics are emitted with namespace and model dimension."""
    put_metric_data = Mock()
    monkeypatch.setenv("MODEL_NAME", "pytest-heart-model")
    monkeypatch.setattr(
        cloudwatch_metrics,
        "_cloudwatch_client",
        lambda: Mock(put_metric_data=put_metric_data),
    )

    cloudwatch_metrics.push_monitoring_metrics(
        drift_score=0.2, prediction_count=12, error_5xx_count=1
    )

    payload = put_metric_data.call_args.kwargs
    assert payload["Namespace"] == "HeartDisease/Test"
    assert {metric["MetricName"] for metric in payload["MetricData"]} == {
        "DataDriftScore",
        "FastAPIRequestCount",
        "FastAPI5xxErrorCount",
    }
    for metric in payload["MetricData"]:
        assert metric["Dimensions"] == [
            {"Name": "ModelName", "Value": "pytest-heart-model"}
        ]


def test_fastapi_log_counts_returns_zero_when_log_group_missing(monkeypatch):
    """Validate missing CloudWatch log groups are handled without raising."""

    class FakeLogs:
        class exceptions:
            class ResourceNotFoundException(Exception):
                pass

        def filter_log_events(self, **kwargs):
            raise self.exceptions.ResourceNotFoundException()

    monkeypatch.setattr(cloudwatch_metrics, "_logs_client", lambda: FakeLogs())

    assert cloudwatch_metrics.get_fastapi_log_counts() == (0, 0)
