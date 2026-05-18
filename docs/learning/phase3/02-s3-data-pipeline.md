# 02 — S3 Data Pipeline

## What We Did

Modified `data.py` to download data from S3 when `DATA_PATH` points to an `s3://` URI, caching it locally. This lets the pipeline read training data from S3 without any code changes — just set `DATA_PATH=s3://bucket/data/file.csv` in the environment.

Also uploaded the raw dataset to S3:
```bash
aws s3 cp data/raw/processed.cleveland.data s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data
```

## Why S3 for Data (Not EC2 Local Disk)

| Aspect | EC2 Local Disk | S3 |
|--------|---------------|-----|
| Durability | 99.9% (lost if instance dies) | 99.999999999% (11 nines) |
| Sharing | Only on one instance | Any EC2, any Lambda, any service |
| Versioning | None | Built-in (recover accidental overwrites) |
| Cost | Free (included in EC2) | $0.023/GB/month (practically free for <1GB) |
| Size limit | 30GB (EBS volume) | 5TB per object |
| Access from CI/CD | Need SSH to EC2 | Direct via IAM role |

**Our choice**: S3 for the single source of truth. The pipeline downloads data to `/tmp` for processing, but the canonical copy lives in S3.

## Theory: How S3 Paths Work

### S3 URI Format

```
s3://bucket-name/path/to/file.ext
│    │            │
│    │            └── Key (the "file path" inside the bucket)
│    └── Bucket name (globally unique across all AWS accounts)
└── Protocol prefix
```

There are **no folders** in S3. The path `data/raw/processed.cleveland.data` is just a string key. The `/` characters have no special meaning to S3 — they're just part of the key name. But the AWS CLI and console render them as folders for convenience.

### S3 Operations We Use

| Operation | CLI Command | boto3 Equivalent |
|-----------|------------|------------------|
| Upload a file | `aws s3 cp local.txt s3://bucket/dir/` | `s3.upload_file("local.txt", "bucket", "dir/local.txt")` |
| Download a file | `aws s3 cp s3://bucket/dir/file.txt .` | `s3.download_file("bucket", "dir/file.txt", "local.txt")` |
| List objects | `aws s3 ls s3://bucket/dir/` | `s3.list_objects_v2(Bucket="bucket", Prefix="dir/")` |
| Sync directory | `aws s3 sync data/ s3://bucket/data/` | No direct equivalent (iterate + upload) |
| Delete a file | `aws s3 rm s3://bucket/dir/file.txt` | `s3.delete_object(Bucket="bucket", Key="dir/file.txt")` |

### The `_resolve_data_path()` Function

This is the core abstraction that makes S3 transparent to the rest of the pipeline:

```python
from urllib.parse import urlparse
from pathlib import Path

DATA_PATH = os.getenv("DATA_PATH", "../data/raw/processed.cleveland.data")
LOCAL_DATA_CACHE = Path(os.getenv("LOCAL_DATA_CACHE", "/tmp/heart_disease_prediction"))

def _resolve_data_path(path: str) -> str:
    if not path.startswith("s3://"):
        return path

    parsed = urlparse(path)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    LOCAL_DATA_CACHE.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_DATA_CACHE / Path(key).name
    boto3.client("s3").download_file(bucket, key, str(local_path))
    return str(local_path)
```

Flow diagram:

```
DATA_PATH = "../data/raw/processed.cleveland.data"
    │
    └── _resolve_data_path() sees no "s3://" prefix
        └── Returns path as-is → pd.read_csv("../data/raw/...")

DATA_PATH = "s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data"
    │
    └── _resolve_data_path() sees "s3://" prefix
        ├── Parse: bucket="heart-disease-mlops-695074562426", key="data/raw/processed.cleveland.data"
        ├── Local cache: /tmp/heart_disease_prediction/processed.cleveland.data
        ├── Download: boto3 S3 → local cache
        └── Returns: "/tmp/heart_disease_prediction/processed.cleveland.data"
            └── pd.read_csv("/tmp/heart_disease_prediction/processed.cleveland.data")
```

### Why Cache to `/tmp` Instead of Reading Directly from S3

pandas `read_csv` can read from S3 directly if you have `s3fs` installed:

```python
pd.read_csv("s3://bucket/data/file.csv")  # Works with s3fs
```

But we chose the download-then-read approach because:

| Aspect | Direct S3 read | Download + read |
|--------|---------------|-----------------|
| Dependencies | Requires `s3fs` + `botocore` | Only `boto3` (already installed) |
| Performance | Network latency on every read | Fast local disk after first download |
| Offline dev | Fails without internet | Works after first download |
| Multiple reads | Each read = network request | One download, many reads |
| Error messages | Cryptic S3 errors | Standard file errors |

The download approach is simpler, fewer dependencies, and more predictable.

## How AWS Authentication Works for S3

When `boto3.client("s3")` is called, it searches for credentials in this order:

1. **Environment variables**: `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`
2. **Shared credentials file**: `~/.aws/credentials`
3. **EC2 instance profile**: IAM role attached via Terraform (our primary method)
4. **ECS task role**: If running in ECS (not our setup)
5. **Web identity**: OIDC token (GitHub Actions, Phase 7)

On EC2, we use the **instance profile** — no keys in code, no keys in `.env`. The EC2 assumes the `heart-disease-mlops-ec2-role` automatically, which has S3 read/write permissions.

Locally, you use `aws configure` (which creates `~/.aws/credentials`).

### Verifying Your Auth

```bash
# Check who you're authenticated as
aws sts get-caller-identity

# On EC2, you should see:
# "Arn": "arn:aws:sts::695074562426:assumed-role/heart-disease-mlops-ec2-role/..."

# Locally, you should see:
# "Arn": "arn:aws:iam::695074562426:user/firstuser"
```

## The Makefile S3 Sync Commands

We fixed the Makefile and added S3 sync targets:

```makefile
S3_BUCKET_NAME ?= heart-disease-mlops-695074562426

sync_data_up:
	aws s3 sync data/ s3://$(S3_BUCKET_NAME)/data

sync_data_down:
	aws s3 sync s3://$(S3_BUCKET_NAME)/data/ data/
```

### The Double-Prefix Bug We Fixed

**Before** (broken):
```makefile
sync_data_up:
	aws s3 sync data/ s3://s3://$(S3_BUCKET_NAME)/data
```

This would try to upload to `s3://s3://bucket/data` — an invalid URI. The bug came from copy-pasting an S3 URI and wrapping it in `s3://` again.

**After** (correct):
```makefile
sync_data_up:
	aws s3 sync data/ s3://$(S3_BUCKET_NAME)/data
```

### `?=` vs `:=` in Makefiles

```makefile
S3_BUCKET_NAME ?= heart-disease-mlops-695074562426   # Set only if not already set
S3_BUCKET_NAME := heart-disease-mlops-695074562426   # Always set (override)
```

We use `?=` so you can override the bucket name without editing the Makefile:

```bash
S3_BUCKET_NAME=my-other-bucket make sync_data_up
```

## How to Debug

### S3 Download Fails in Pipeline

```bash
# Test S3 access manually
aws s3 ls s3://heart-disease-mlops-695074562426/data/raw/
# Should show: 2025-XX-XX XX:XX:XX    18461 processed.cleveland.data

# Test download manually
aws s3 cp s3://heart-disease-mlops-695074562426/data/raw/processed.cleveland.data /tmp/test_data.csv
```

### "Access Denied" on S3

```bash
# Check your identity
aws sts get-caller-identity

# If running on EC2 with instance profile, check the role
aws iam list-attached-role-policies --role-name heart-disease-mlops-ec2-role

# Simulate a specific permission
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::695074562426:role/heart-disease-mlops-ec2-role \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::heart-disease-mlops-695074562426/data/raw/processed.cleveland.data
```

### "NoSuchKey" Error

```bash
# The file might not be uploaded yet. Check bucket contents:
aws s3 ls s3://heart-disease-mlops-695074562426/ --recursive

# Upload if missing:
aws s3 cp data/raw/processed.cleveland.data s3://heart-disease-mlops-695074562426/data/raw/
```

### boto3 Client vs Resource

boto3 has two APIs for S3:

```python
# Client — low-level, returns raw dicts
s3 = boto3.client("s3")
s3.download_file("bucket", "key", "/tmp/file")

# Resource — high-level, object-oriented
s3 = boto3.resource("s3")
s3.Object("bucket", "key").download_file("/tmp/file")
```

We use the **client** API because it's simpler for single-file operations. The resource API is better for listing and iterating.

## Practical Tips

### Upload All Raw Data to S3

```bash
make sync_data_up
# or manually:
aws s3 sync data/raw/ s3://heart-disease-mlops-695074562426/data/raw/
```

### Verify Data Integrity After Download

```python
import hashlib

def verify_s3_file(bucket, key, expected_md5=None):
    local = f"/tmp/{key.split('/')[-1]}"
    boto3.client("s3").download_file(bucket, key, local)

    if expected_md5:
        with open(local, "rb") as f:
            actual = hashlib.md5(f.read()).hexdigest()
        assert actual == expected_md5, f"MD5 mismatch: {actual} != {expected_md5}"
    return local
```

### Cost of S3 for This Project

| Item | Size | Monthly cost |
|------|------|-------------|
| Raw data (18KB) | ~0.02 GB | $0.0005 |
| Model artifacts (~5MB each, ~50 models) | ~0.25 GB | $0.006 |
| Monitoring reports (~1MB each, 90 days) | ~0.09 GB | $0.002 |
| **Total** | | **< $0.01/month** |

S3 is essentially free for ML workloads at this scale.

### The LOCAL_DATA_CACHE Env Var

The default `/tmp/heart_disease_prediction` is fine on EC2, but on your local machine you might want:

```
LOCAL_DATA_CACHE=/home/yourname/.cache/heart_disease_prediction
```

This keeps S3-cached data separate from your project directory, and survives project rebuilds.
