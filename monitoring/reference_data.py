from __future__ import annotations

import argparse
from io import BytesIO
from urllib.parse import urlparse

import boto3
import pandas as pd

from monitoring.config import FEATURE_COLUMNS, get_config

RAW_COLUMNS = [*FEATURE_COLUMNS, "hd"]


def _read_raw_data(path: str) -> pd.DataFrame:
    if path.startswith("s3://"):
        parsed = urlparse(path)
        body = boto3.client("s3").get_object(
            Bucket=parsed.netloc,
            Key=parsed.path.lstrip("/"),
        )["Body"].read()
        df = pd.read_csv(BytesIO(body), header=None)
    else:
        df = pd.read_csv(path, header=None)

    df.columns = RAW_COLUMNS
    return df.loc[(df["ca"] != "?") & (df["thal"] != "?")].copy()


def build_reference_dataframe(data_path: str) -> pd.DataFrame:
    df = _read_raw_data(data_path)
    reference_df = df[FEATURE_COLUMNS].copy()

    for column in ["ca", "thal"]:
        reference_df[column] = reference_df[column].astype(str)

    return reference_df


def save_reference_data(data_path: str | None = None) -> str:
    config = get_config()
    data_path = data_path or config.fallback_data_path
    reference_df = build_reference_dataframe(data_path)

    buffer = BytesIO()
    reference_df.to_parquet(buffer, index=False)
    buffer.seek(0)

    boto3.client("s3", region_name=config.aws_region).put_object(
        Bucket=config.s3_bucket,
        Key=config.reference_data_key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )

    return config.reference_data_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Evidently reference data to S3.")
    parser.add_argument("--data-path", default=None, help="Local path or s3:// URI for raw data.")
    args = parser.parse_args()

    uri = save_reference_data(args.data_path)
    print(f"Saved reference data to {uri}")


if __name__ == "__main__":
    main()
