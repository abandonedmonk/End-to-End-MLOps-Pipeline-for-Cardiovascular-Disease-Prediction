import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FEATURE_COLUMNS = [
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
]

NUMERICAL_COLUMNS = [
    "age",
    "sex",
    "trestbps",
    "chol",
    "fbs",
    "thalach",
    "exang",
    "oldpeak",
]

CATEGORICAL_COLUMNS = ["restecg", "slope", "thal", "ca", "cp"]


@dataclass(frozen=True)
class MonitoringConfig:
    s3_bucket: str
    aws_region: str
    drift_threshold: float
    reference_data_key: str
    current_data_key: str
    reports_prefix: str
    metrics_key: str
    fallback_data_path: str
    fastapi_log_group: str
    cloudwatch_namespace: str

    @property
    def reference_data_uri(self) -> str:
        return f"s3://{self.s3_bucket}/{self.reference_data_key}"

    @property
    def current_data_uri(self) -> str:
        return f"s3://{self.s3_bucket}/{self.current_data_key}"

    @property
    def metrics_uri(self) -> str:
        return f"s3://{self.s3_bucket}/{self.metrics_key}"


def get_config() -> MonitoringConfig:
    bucket = os.getenv("S3_BUCKET") or os.getenv("MLFLOW_S3_BUCKET")
    if not bucket:
        bucket = "heart-disease-mlops-695074562426"

    return MonitoringConfig(
        s3_bucket=bucket,
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        drift_threshold=float(os.getenv("DRIFT_THRESHOLD", "0.3")),
        reference_data_key=os.getenv(
            "REFERENCE_DATA_S3_KEY", "data/reference/reference_data.parquet"
        ),
        current_data_key=os.getenv(
            "CURRENT_DATA_S3_KEY", "monitoring/current/current_data.parquet"
        ),
        reports_prefix=os.getenv("MONITORING_REPORTS_PREFIX", "monitoring/reports"),
        metrics_key=os.getenv("DRIFT_METRICS_S3_KEY", "monitoring/metrics/drift_scores.jsonl"),
        fallback_data_path=os.getenv(
            "DATA_PATH",
            "s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data",
        ),
        fastapi_log_group=os.getenv("FASTAPI_LOG_GROUP", "/heart-disease-mlops/fastapi"),
        cloudwatch_namespace=os.getenv(
            "CLOUDWATCH_NAMESPACE", "HeartDisease/Monitoring"
        ),
    )
