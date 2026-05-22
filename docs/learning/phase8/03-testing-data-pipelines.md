# 03 — Testing Data Pipelines

Testing data loading, preprocessing, train/test splitting, and S3 handling.

---

## Table of Contents

1. [What We Test](#what-we-test)
2. [Testing Data Loading](#testing-data-loading)
3. [Testing Preprocessing](#testing-preprocessing)
4. [Testing Train/Test Split](#testing-traintest-split)
5. [Testing S3 Data Loading](#testing-s3-data-loading)
6. [Testing Error Handling](#testing-error-handling)
7. [Fixtures for Data Tests](#fixtures-for-data-tests)
8. [Common Patterns](#common-patterns)

---

## What We Test

The data pipeline has three layers:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Data Loading                                   │
│  - Local file (.csv)                                    │
│  - S3 file (s3://bucket/key)                           │
│  - Cleveland dataset (303 rows, 14 columns)            │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Preprocessing                                  │
│  - Column naming (age, sex, ..., hd)                    │
│  - Handle missing values ("?")                          │
│  - Target binarization (0-4 → 0, others → 1)            │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Train/Test Split + Preprocessor                │
│  - 80/20 split (configurable)                          │
│  - ColumnTransformer (numeric + categorical)           │
│  - Returns: X_train, X_test, y_train, y_test, prep     │
└─────────────────────────────────────────────────────────┘
```

---

## Testing Data Loading

### Test: Loading Raw Cleveland Data

```python
# tests/test_data.py
EXPECTED_COLUMNS = [
    "age", "sex", "cp", "trestbps", "chol", "fbs",
    "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal", "hd"
]

def test_load_data_returns_expected_schema(raw_data_path):
    """Validate raw Cleveland data loads with the expected 303x14 schema."""
    df = data.get_data.fn(str(raw_data_path))
    
    assert df.shape == (303, 14), f"Expected (303, 14), got {df.shape}"
    assert list(df.columns) == EXPECTED_COLUMNS
    assert set(df["hd"].astype(int).unique()).issubset({0, 1})
```

**What it validates:**
- Shape matches known Cleveland dataset (303 rows, 14 features + target)
- Column names match expected schema
- Target column is binary (0 or 1)

**Why:**
- Dataset schema is well-known (UCI ML Repository)
- If shape changes, something broke in loading/parsing
- Binary classification is our task assumption

---

### Test: Target Binarization

The Cleveland dataset has target values 0-4 (0 = no disease, 1-4 = disease severity).
We binarize: 0 → 0 (no disease), 1-4 → 1 (disease).

```python
def test_target_is_binary_after_loading(raw_data_path):
    """Validate target values are 0 or 1 after binarization."""
    df = data.get_data.fn(str(raw_data_path))
    
    unique_targets = set(df["hd"].unique())
    assert unique_targets == {0, 1}, f"Expected {{0, 1}}, got {unique_targets}"
    assert df["hd"].isna().sum() == 0, "No missing targets allowed"
```

**Production code:**
```python
def get_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, header=None, names=COLUMNS)
    # Binarize target: 0 stays 0, 1-4 become 1
    df["hd"] = (df["hd"] > 0).astype(int)
    return df
```

---

### Test: Handling Missing Values

The Cleveland dataset uses "?" for missing values in `ca` and `thal` columns.

```python
def test_missing_values_handled(sample_dataframe):
    """Validate missing values (?) are handled appropriately."""
    # Count ? before preprocessing
    ca_missing = (sample_dataframe["ca"] == "?").sum()
    thal_missing = (sample_dataframe["thal"] == "?").sum()
    
    # After split_data_for_train, these should be handled
    X_train, X_test, y_train, y_test, preprocessor = data.split_data_for_train.fn(
        sample_dataframe
    )
    
    # Verify no ? remain in features (either filtered or imputed)
    assert "?" not in X_train.values, "Missing markers not handled in X_train"
    assert "?" not in X_test.values, "Missing markers not handled in X_test"
```

---

## Testing Preprocessing

### Test: Preprocessor Structure

The preprocessor is a `ColumnTransformer` with:
- Numeric columns: passed through (or scaled)
- Categorical columns: one-hot encoded

```python
def test_preprocessor_handles_numeric_and_categorical_columns(prepared_data):
    """Validate the preprocessor has numeric passthrough and categorical encoder steps."""
    X_train, _, _, _, preprocessor = prepared_data
    
    # Transform a sample
    transformed = preprocessor.fit_transform(X_train)
    
    # Get transformer names
    transformers = dict(
        (name, transformer) for name, transformer, _ in preprocessor.transformers
    )
    
    # Assert numeric passthrough
    assert transformers["num"] == "passthrough"
    
    # Assert categorical one-hot
    assert isinstance(transformers["cat"], OneHotEncoder)
    
    # Verify transformed shape
    assert transformed.shape[0] == len(X_train)  # Same rows
    assert transformed.shape[1] > X_train.shape[1]  # More columns (one-hot expanded)
```

**What it validates:**
- Preprocessor has both numeric and categorical branches
- Numeric: `passthrough` (or StandardScaler)
- Categorical: OneHotEncoder
- One-hot encoding increases column count

---

### Test: Preprocessor Fit/Transform

```python
def test_preprocessor_fit_then_transform(prepared_data):
    """Validate preprocessor can be fit on train and transform both train/test."""
    X_train, X_test, _, _, preprocessor = prepared_data
    
    # Fit on train
    preprocessor.fit(X_train)
    
    # Transform train
    X_train_transformed = preprocessor.transform(X_train)
    assert X_train_transformed.shape[0] == len(X_train)
    
    # Transform test (fit should not change)
    X_test_transformed = preprocessor.transform(X_test)
    assert X_test_transformed.shape[0] == len(X_test)
    
    # Same number of columns
    assert X_train_transformed.shape[1] == X_test_transformed.shape[1]
```

**Why:** Preprocessor must be fit **only** on training data to avoid data leakage.

---

## Testing Train/Test Split

### Test: Split Sizes

```python
def test_prepare_data_splits_and_binarizes_target(sample_dataframe):
    """Validate train/test split sizes, binary targets, and preprocessor type."""
    X_train, X_test, y_train, y_test, preprocessor = data.split_data_for_train.fn(
        sample_dataframe
    )
    
    # On 50-row sample with 0.8/0.2 split: 40 train, 10 test
    assert len(X_train) == 40, f"Expected 40 train rows, got {len(X_train)}"
    assert len(X_test) == 10, f"Expected 10 test rows, got {len(X_test)}"
    
    # Target is binary
    assert set(y_train.unique()).issubset({0, 1})
    assert set(y_test.unique()).issubset({0, 1})
    
    # Returns ColumnTransformer
    assert isinstance(preprocessor, ColumnTransformer)
```

**Why explicit numbers (40/10):**
- Sample fixture returns 50 rows
- 80% train = 40, 20% test = 10
- Explicit > formula (easier to debug)

---

### Test: Split is Deterministic

```python
def test_split_is_detinistic_with_random_state(sample_dataframe):
    """Validate same split on repeated calls with same random_state."""
    X_train_1, X_test_1, _, _, _ = data.split_data_for_train.fn(
        sample_dataframe, random_state=42
    )
    X_train_2, X_test_2, _, _, _ = data.split_data_for_train.fn(
        sample_dataframe, random_state=42
    )
    
    # Same rows in train
    assert X_train_1.equals(X_train_2)
    
    # Same rows in test
    assert X_test_1.equals(X_test_2)
```

**Why:** Deterministic splits make debugging and reproduction possible.

---

## Testing S3 Data Loading

### Test: S3 Path Triggers Download

```python
@mock_aws
def test_s3_data_loading_downloads_to_cache(sample_data_file, monkeypatch, tmp_path):
    """Validate s3:// paths trigger a boto3 download into the local cache."""
    # Setup: Create mock S3 bucket
    bucket = "test-heart-disease-bucket"
    key = "data/raw/heart.csv"
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.create_bucket(Bucket=bucket)
    
    # Setup: Upload test file
    s3_client.upload_file(str(sample_data_file), bucket, key)
    
    # Setup: Set cache directory
    monkeypatch.setattr(data, "LOCAL_DATA_CACHE", tmp_path / "cache")
    
    # Action: Resolve s3:// path
    resolved = data._resolve_data_path(f"s3://{bucket}/{key}")
    
    # Assert: File downloaded to cache
    assert Path(resolved).exists()
    assert Path(resolved).parent == tmp_path / "cache"
    
    # Assert: Content matches
    downloaded = pd.read_csv(resolved, header=None)
    original = pd.read_csv(sample_data_file, header=None)
    assert downloaded.equals(original)
```

**What it validates:**
- `s3://` prefix triggers S3 download logic
- File lands in local cache directory
- Content unchanged during download

---

### Test: Local Path Bypasses S3

```python
def test_local_data_loading_bypasses_s3(sample_data_file, monkeypatch):
    """Validate local paths are returned directly without calling boto3."""
    called = False
    
    def fail_client(*args, **kwargs):
        """If called, fail the test."""
        nonlocal called
        called = True
        raise AssertionError("boto3 should not be called for local files")
    
    # Replace boto3.client with failing version
    monkeypatch.setattr(data.boto3, "client", fail_client)
    
    # Action: Resolve local path
    result = data._resolve_data_path(str(sample_data_file))
    
    # Assert: boto3 was never called
    assert called is False
    
    # Assert: Path returned as-is
    assert result == str(sample_data_file)
```

**What it validates:**
- Local file paths skip S3 logic entirely
- No unnecessary AWS calls (faster, no credentials needed)

---

### Test: S3 Download Failure

```python
@mock_aws
def test_s3_download_failure_raises_clear_error(monkeypatch, tmp_path):
    """Validate S3 download failures raise descriptive errors."""
    bucket = "test-bucket"
    key = "nonexistent/data.csv"
    
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.create_bucket(Bucket=bucket)
    # Note: NOT uploading the file
    
    monkeypatch.setattr(data, "LOCAL_DATA_CACHE", tmp_path / "cache")
    
    with pytest.raises(Exception) as exc_info:
        data._resolve_data_path(f"s3://{bucket}/{key}")
    
    assert "not found" in str(exc_info.value).lower() or \
           "404" in str(exc_info.value)
```

---

## Testing Error Handling

### Test: Missing Local File

```python
def test_missing_local_file_raises_clear_error(tmp_path):
    """Validate missing local files surface as FileNotFoundError."""
    missing = tmp_path / "missing.csv"
    
    with pytest.raises(FileNotFoundError) as exc_info:
        data.get_data.fn(str(missing))
    
    assert str(missing) in str(exc_info.value)
```

**What it validates:**
- Clear error for missing files
- Error includes the file path
- Caller can catch specific exception type

---

### Test: Malformed Data

```python
def test_malformed_csv_raises_parse_error(tmp_path):
    """Validate malformed CSV raises appropriate pandas error."""
    bad_file = tmp_path / "bad.csv"
    bad_file.write_text("not,a,valid,csv\n1,2")  # Mismatched columns
    
    with pytest.raises(pd.errors.ParserError):
        data.get_data.fn(str(bad_file))
```

---

## Fixtures for Data Tests

### conftest.py fixtures used

```python
@pytest.fixture
def raw_data_path():
    """Return the checked-in Cleveland raw data file."""
    return DATA_PATH  # data/raw/processed.cleveland.data

@pytest.fixture
def full_dataframe():
    """Load the full raw dataset with the production schema."""
    df = pd.read_csv(DATA_PATH, header=None)
    df.columns = RAW_COLUMNS
    return df

@pytest.fixture
def sample_dataframe(full_dataframe):
    """Return a deterministic, cleaned sample with realistic columns."""
    # Remove rows with missing values for cleaner tests
    df = full_dataframe.loc[
        (full_dataframe["ca"] != "?") & (full_dataframe["thal"] != "?")
    ].head(50)
    return df.copy()

@pytest.fixture
def sample_data_file(sample_dataframe, tmp_path):
    """Write a small headerless Cleveland-shaped dataset to disk."""
    path = tmp_path / "heart.csv"
    sample_dataframe.to_csv(path, header=False, index=False)
    return path

@pytest.fixture
def prepared_data(sample_dataframe):
    """Build the same train/test/preprocessor tuple used by training."""
    from heart_disease_prediction.data import split_data_for_train
    return split_data_for_train.fn(sample_dataframe)
```

---

## Common Patterns

### Pattern: Testing with Real Data File

```python
def test_with_real_data(raw_data_path):
    """Use the actual data file from repo."""
    df = data.get_data.fn(str(raw_data_path))
    
    # Tests against real schema/shape
    assert df.shape == (303, 14)
```

**Pros:**
- Tests real production data
- Catches data drift

**Cons:**
- Slower (file I/O)
- Requires data file in repo

---

### Pattern: Testing with Synthetic Data

```python
def test_with_synthetic_data():
    """Use small synthetic dataset."""
    df = pd.DataFrame({
        "age": [50, 60, 70],
        "sex": [1, 0, 1],
        # ... other columns
        "hd": [0, 1, 1]
    })
    
    result = preprocess(df)
    assert result.shape[0] == 3
```

**Pros:**
- Very fast
- No file dependencies
- Controlled edge cases

**Cons:**
- May not catch real data issues

---

### Pattern: Combined Approach (What We Use)

```python
@pytest.fixture
def sample_dataframe(full_dataframe):
    """Sample from real data (best of both worlds)."""
    return full_dataframe.head(50)  # Real data, but small/fast

def test_both_real_and_fast(sample_dataframe):
    """Fast test with real data characteristics."""
    pass
```

---

## Key Takeaways

1. **Test data schema first** — Shape, columns, types
2. **Test transformations** — Binarization, missing value handling
3. **Test split ratios** — Explicit numbers are clearer
4. **Test S3 path detection** — s3:// vs local triggers different logic
5. **Mock S3 with moto** — No real AWS calls
6. **Use real data samples** — Catches production data drift
7. **Test error paths** — Missing files, bad formats
8. **Keep data tests fast** — Small samples, not full 303 rows unless needed

---

## Next

- [04 — Testing ML Training](04-testing-ml-training.md) — Model training, metrics, selection
