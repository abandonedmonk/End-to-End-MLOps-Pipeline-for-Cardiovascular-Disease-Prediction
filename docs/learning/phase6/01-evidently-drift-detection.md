# 01 — Evidently Drift Detection

Setting up Evidently AI to detect when your production data starts diverging from your training baseline.

---

## What is Data Drift?

**Data drift** occurs when the statistical properties of your input features change over time. This is a silent killer in ML systems — your model keeps making predictions, but they're increasingly wrong because the world changed.

**Common causes:**
- Seasonal effects (heart disease risk factors vary by season)
- Policy changes (new hospital admission criteria)
- Population shifts (different demographics using the system)
- Data pipeline bugs (new ETL code changes value distributions)

---

## Why Evidently?

| Alternative | Pros | Cons |
|-------------|------|------|
| **Evidently** | Open source, beautiful HTML reports, easy Python API, S3 integration | Manual setup, no hosted UI |
| **WhyLabs** | Hosted, automated | Paid for production scale |
| **Great Expectations** | Data quality focus, comprehensive | Steep learning curve |
| **Custom scripts** | Full control | Time consuming, error prone |

**Evidently wins for:**
- Free tier compatibility (open source)
- Quick implementation (2 hours to production)
- Rich HTML reports (shareable, actionable)
- Works with S3 (no additional infrastructure)

---

## Core Concepts

### Reference Data (Baseline)
Your training data — what the model learned from. This is your "ground truth" snapshot.

### Current Data (Production)
New data coming through your pipeline — what you want to check for drift.

### Drift Score
0 = identical distributions  
1 = completely different  
0.3 = 30% of features have drifted (our alert threshold)

### Statistical Tests
Evidently uses:
- **Kolmogorov-Smirnov** for numerical features
- **Chi-square** for categorical features
- **Jensen-Shannon distance** for distribution comparison

---

## Implementation

### Step 1: Install Evidently

```bash
# Add to requirements.txt
evidently==0.4.0
pyarrow  # For parquet support

# Or install directly
pip install evidently==0.4.0 pyarrow
```

### Step 2: Configuration (`monitoring/config.py`)

```python
import os
from typing import List

# S3 Paths
S3_BUCKET = os.getenv("S3_BUCKET", "heart-disease-mlops-695074562426")
S3_PREFIX = "monitoring"
REFERENCE_DATA_KEY = "data/reference/reference_data.parquet"
CURRENT_DATA_KEY = "data/current/current_data.parquet"  # Fallback

# Drift Detection
DRIFT_THRESHOLD = 0.3  # 30% of features drifted = alert
FEATURE_COLUMNS = [
    "age", "sex", "cp", "trestbps", "chol", "fbs",
    "restecg", "thalach", "exang", "oldpeak", 
    "slope", "ca", "thal"
]
TARGET_COLUMN = "target"  # For reference data only

# AWS
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CLOUDWATCH_NAMESPACE = "HeartDisease/Monitoring"

# Categorical columns that need special handling
CATEGORICAL_COLUMNS = ["sex", "cp", "fbs", "restecg", "exang", "slope", "ca", "thal"]
```

### Step 3: Save Reference Data (`monitoring/reference_data.py`)

```python
"""
Save training data as reference baseline to S3.
Run once after training, before drift detection starts.
"""
import os
import boto3
import pandas as pd
from io import BytesIO

from monitoring.config import (
    S3_BUCKET, REFERENCE_DATA_KEY, 
    FEATURE_COLUMNS, TARGET_COLUMN, AWS_REGION
)

def create_reference_data():
    """Load training data and save to S3 as parquet."""
    # Load from local or S3 depending on your setup
    data_path = os.getenv("DATA_PATH", "data/raw/processed.cleveland.data")
    
    # Load data (your existing data.py logic)
    df = load_data(data_path)  # Your existing function
    
    # Keep only features + target
    reference_df = df[FEATURE_COLUMNS + [TARGET_COLUMN]]
    
    # Ensure categorical columns are strings
    for col in CATEGORICAL_COLUMNS:
        if col in reference_df.columns:
            reference_df[col] = reference_df[col].astype(str)
    
    # Save to S3
    s3 = boto3.client("s3", region_name=AWS_REGION)
    buffer = BytesIO()
    reference_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=REFERENCE_DATA_KEY,
        Body=buffer.getvalue()
    )
    
    print(f"✓ Reference data saved to s3://{S3_BUCKET}/{REFERENCE_DATA_KEY}")
    print(f"  Shape: {reference_df.shape}")
    print(f"  Columns: {list(reference_df.columns)}")
    
    return reference_df

if __name__ == "__main__":
    create_reference_data()
```

### Step 4: Generate Drift Report (`monitoring/generate_report.py`)

```python
"""
Generate Evidently drift and quality reports.
Uploads HTML to S3, appends score to drift history.
"""
import os
import json
import boto3
import pandas as pd
from datetime import datetime
from io import BytesIO, StringIO
from typing import Tuple, Optional

from evidently import ColumnMapping
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, DataQualityPreset
from evidently.metrics import DatasetDriftMetric

from monitoring.config import (
    S3_BUCKET, REFERENCE_DATA_KEY, CURRENT_DATA_KEY,
    FEATURE_COLUMNS, DRIFT_THRESHOLD, CATEGORICAL_COLUMNS,
    AWS_REGION
)
from monitoring.cloudwatch_metrics import push_drift_metrics


def load_data_from_s3(s3_key: str) -> pd.DataFrame:
    """Load parquet data from S3."""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        return pd.read_parquet(BytesIO(response['Body'].read()))
    except s3.exceptions.NoSuchKey:
        return None


def normalize_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure categorical columns are strings for comparison."""
    df = df.copy()
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


def generate_drift_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    report_date: str = None
) -> Tuple[str, float, bool]:
    """
    Generate Evidently drift report.
    
    Returns:
        report_path: S3 key where HTML is saved
        drift_score: 0-1 score
        drift_detected: True if score > threshold
    """
    report_date = report_date or datetime.now().strftime("%Y-%m-%d")
    
    # Normalize categorical columns
    reference_df = normalize_categoricals(reference_df)
    current_df = normalize_categoricals(current_df)
    
    # Create report with drift and quality metrics
    report = Report(metrics=[
        DatasetDriftMetric(),  # Overall drift score
        DataDriftPreset(),     # Per-feature drift
        DataQualityPreset()    # Missing values, ranges
    ])
    
    # Run the report
    report.run(
        reference_data=reference_df,
        current_data=current_df,
        column_mapping=ColumnMapping()
    )
    
    # Extract drift score
    report_dict = report.as_dict()
    drift_score = report_dict['metrics'][0]['result']['dataset_drift']
    drift_detected = drift_score > DRIFT_THRESHOLD
    
    # Save HTML to S3
    html_path = f"monitoring/reports/{report_date}/drift_report.html"
    html_content = report.get_html()
    
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=html_path,
        Body=html_content.encode('utf-8'),
        ContentType='text/html'
    )
    
    # Append drift score to history (JSON Lines)
    history_key = "monitoring/metrics/drift_scores.jsonl"
    history_entry = {
        "date": report_date,
        "drift_score": drift_score,
        "drift_detected": drift_detected,
        "threshold": DRIFT_THRESHOLD,
        "reference_shape": list(reference_df.shape),
        "current_shape": list(current_df.shape)
    }
    
    try:
        # Try to append to existing file
        existing = s3.get_object(Bucket=S3_BUCKET, Key=history_key)
        existing_lines = existing['Body'].read().decode('utf-8')
        new_content = existing_lines + "\n" + json.dumps(history_entry)
    except s3.exceptions.NoSuchKey:
        # Create new file
        new_content = json.dumps(history_entry)
    
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=history_key,
        Body=new_content.encode('utf-8')
    )
    
    print(f"✓ Drift report saved to s3://{S3_BUCKET}/{html_path}")
    print(f"  Drift score: {drift_score:.3f} (threshold: {DRIFT_THRESHOLD})")
    print(f"  Drift detected: {drift_detected}")
    
    return html_path, drift_score, drift_detected


def generate_report_with_fallback() -> Tuple[Optional[str], float, bool]:
    """
    Generate report with fallback to raw data if current data not available.
    """
    # Load reference data
    reference_df = load_data_from_s3(REFERENCE_DATA_KEY)
    if reference_df is None:
        raise ValueError(f"Reference data not found at s3://{S3_BUCKET}/{REFERENCE_DATA_KEY}")
    
    # Try to load current data
    current_df = load_data_from_s3(CURRENT_DATA_KEY)
    
    if current_df is None:
        # Fallback: use raw data path for first runs
        print("⚠ Current data snapshot not found, falling back to raw data")
        data_path = os.getenv("DATA_PATH", "data/raw/processed.cleveland.data")
        from heart_disease_prediction.data import load_data
        current_df = load_data(data_path)
        # Keep only feature columns
        current_df = current_df[FEATURE_COLUMNS]
    
    return generate_drift_report(reference_df, current_df)


if __name__ == "__main__":
    report_path, score, detected = generate_report_with_fallback()
    
    # Push to CloudWatch
    push_drift_metrics(score, detected)
    
    if detected:
        print(f"\n🚨 DRIFT DETECTED! Score {score:.3f} > threshold {DRIFT_THRESHOLD}")
        print("   Consider retraining the model.")
