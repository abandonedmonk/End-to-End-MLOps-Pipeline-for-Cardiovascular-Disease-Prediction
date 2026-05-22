from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

import boto3

from monitoring.config import get_config


def _cloudwatch_client():
    config = get_config()
    return boto3.client("cloudwatch", region_name=config.aws_region)


def _logs_client():
    config = get_config()
    return boto3.client("logs", region_name=config.aws_region)


def push_monitoring_metrics(
    drift_score: float,
    prediction_count: int = 0,
    error_5xx_count: int = 0,
) -> None:
    config = get_config()
    now = datetime.now(timezone.utc)
    dimensions = [{"Name": "ModelName", "Value": os.getenv("MODEL_NAME", "heart-disease")}]

    _cloudwatch_client().put_metric_data(
        Namespace=config.cloudwatch_namespace,
        MetricData=[
            {
                "MetricName": "DataDriftScore",
                "Value": drift_score,
                "Unit": "None",
                "Timestamp": now,
                "Dimensions": dimensions,
            },
            {
                "MetricName": "FastAPIRequestCount",
                "Value": prediction_count,
                "Unit": "Count",
                "Timestamp": now,
                "Dimensions": dimensions,
            },
            {
                "MetricName": "FastAPI5xxErrorCount",
                "Value": error_5xx_count,
                "Unit": "Count",
                "Timestamp": now,
                "Dimensions": dimensions,
            },
        ],
    )


def get_fastapi_log_counts(lookback_minutes: int = 60) -> tuple[int, int]:
    config = get_config()
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=lookback_minutes)
    logs = _logs_client()

    try:
        request_response = logs.filter_log_events(
            logGroupName=config.fastapi_log_group,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='"POST /predict"',
        )
        error_response = logs.filter_log_events(
            logGroupName=config.fastapi_log_group,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='?500 ?501 ?502 ?503 ?504 ?505',
        )
    except logs.exceptions.ResourceNotFoundException:
        return 0, 0

    return len(request_response.get("events", [])), len(error_response.get("events", []))
