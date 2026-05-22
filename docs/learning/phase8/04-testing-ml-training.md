# 04 — Testing ML Training

Testing model training, metrics logging, best model selection, and cross-validation.

---

## Table of Contents

1. [What We Test](#what-we-test)
2. [Testing Model Training](#testing-model-training)
3. [Testing Metrics Logging](#testing-metrics-logging)
4. [Testing Best Model Selection](#testing-best-model-selection)
5. [Testing Cross-Validation](#testing-cross-validation)
6. [Fixtures for Training Tests](#fixtures-for-training-tests)
7. [MLflow Mocking](#mlflow-mocking)
8. [Common Patterns](#common-patterns)

---

## What We Test

The training module has several responsibilities:

```
┌─────────────────────────────────────────────────────────┐
│  Input: X_train, X_test, y_train, y_test, preprocessor  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  1. Train Multiple Models                               │
│     - Logistic Regression                              │
│     - Random Forest                                    │
│     - Gradient Boosting                                │
│     - Decision Tree                                    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  2. Evaluate on Test Set                                │
│     - accuracy, precision, recall, f1                  │
│     - Log to MLflow                                    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  3. Select Best Model                                   │
│     - Highest accuracy                                 │
│     - Return: model, pipeline, paths                   │
└─────────────────────────────────────────────────────────┘
```

---

## Testing Model Training

### Test: All Models Train Without Error

```python
# tests/test_train.py
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

def test_all_configured_models_train_without_error(prepared_data):
    """Validate the four production classifier types can fit the prepared data."""
    X_train, _, y_train, _, preprocessor = prepared_data
    
    models = [
        LogisticRegression(max_iter=1000),
        RandomForestClassifier(n_estimators=10, random_state=42),
        HistGradientBoostingClassifier(random_state=42),
        DecisionTreeClassifier(ccp_alpha=0.0135, random_state=42),
    ]
    
    for model in models:
        pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", model)
        ])
        pipeline.fit(X_train, y_train)
        
        # Assert pipeline can predict
        assert hasattr(pipeline, "predict")
        
        # Assert predictions are binary
        preds = pipeline.predict(X_train[:5])
        assert all(p in [0, 1] for p in preds)
```

**What it validates:**
- All 4 model types work with our data
- Pipeline + model combination is valid
- Predictions are binary (classification task)

**Note:** We use `n_estimators=10` (not 100) for speed.

---

### Test: Model with Preprocessor Pipeline

```python
def test_pipeline_structure(prepared_data):
    """Validate the pipeline has preprocessor + classifier stages."""
    X_train, _, y_train, _, preprocessor = prepared_data
    
    model = LogisticRegression(max_iter=1000)
    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", model)
    ])
    
    # Pipeline has 2 steps
    assert len(pipeline.steps) == 2
    assert pipeline.steps[0][0] == "preprocessor"
    assert pipeline.steps[1][0] == "classifier"
    
    # Can fit end-to-end
    pipeline.fit(X_train, y_train)
    
    # Can predict
    preds = pipeline.predict(X_train[:3])
    assert len(preds) == 3
```

---

## Testing Metrics Logging

### Test: Training Logs All Expected Metrics

```python
def test_train_model_logs_metrics_and_artifacts(prepared_data, mock_mlflow):
    """Validate training logs accuracy, precision, recall, f1, and model artifacts."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    # Setup: Config with mock MLflow
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "mlflow_artifact_root": mock_mlflow["artifact_root"],
        "experiment_name": "pytest-heart-disease",
        "model_name": "pytest-heart-disease-model",
    }
    
    # Action: Train models
    best_model, best_pipeline, paths = train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config=config
    )
    
    # Assert: Returns valid objects
    assert best_model is not None
    assert hasattr(best_pipeline, "predict")
    assert paths["experiment_name"] == "pytest-heart-disease"
    
    # Assert: Query MLflow for logged runs
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-heart-disease")
    runs = client.search_runs([experiment.experiment_id])
    
    # 4 models trained = 4 runs
    assert len(runs) == 4
    
    # Each run has expected metrics
    for run in runs:
        # Metrics in valid range
        assert 0 <= run.data.metrics["accuracy"] <= 1
        assert 0 <= run.data.metrics["precision"] <= 1
        assert 0 <= run.data.metrics["recall"] <= 1
        assert 0 <= run.data.metrics["f1_score"] <= 1
        
        # Model artifact exists
        artifacts = client.list_artifacts(run.info.run_id, "model")
        assert len(artifacts) > 0
```

**What it validates:**
- All 4 models are trained and logged
- Each run has 4 metrics (accuracy, precision, recall, f1)
- Metrics are valid (0-1 range)
- Model artifacts are saved
- Config flows through correctly

---

### Test: Metrics Have Model Names

```python
def test_logged_metrics_include_model_name(prepared_data, mock_mlflow):
    """Validate each run is tagged with the model type."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "experiment_name": "pytest-model-names",
    }
    
    train_model.fn(X_train, X_test, y_train, y_test, preprocessor, config=config)
    
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-model-names")
    runs = client.search_runs([experiment.experiment_id])
    
    # Collect model names from params
    model_names = {run.data.params.get("model") for run in runs}
    
    expected_models = {
        "LogisticRegression",
        "RandomForest",
        "HistGradientBoosting",
        "DecisionTree"
    }
    
    assert model_names == expected_models
```

---

## Testing Best Model Selection

### Test: Best Model Has Highest Accuracy

```python
def test_best_model_selection_matches_highest_accuracy(prepared_data, mock_mlflow):
    """Validate the returned model corresponds to the highest logged accuracy run."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "mlflow_artifact_root": mock_mlflow["artifact_root"],
        "experiment_name": "pytest-best-model",
    }
    
    best_model, _, _ = train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config=config
    )
    
    # Query runs sorted by accuracy descending
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-best-model")
    best_run = client.search_runs(
        [experiment.experiment_id],
        order_by=["metrics.accuracy DESC"],
        max_results=1
    )[0]
    
    # Map class names to logged names
    class_to_logged_name = {
        "LogisticRegression": "LogisticRegression",
        "RandomForestClassifier": "RandomForest",
        "HistGradientBoostingClassifier": "HistGradientBoosting",
        "DecisionTreeClassifier": "DecisionTree",
    }
    
    # Assert: Returned model matches highest accuracy run
    expected_name = class_to_logged_name[best_model.__class__.__name__]
    logged_name = best_run.data.params["model"]
    
    assert expected_name == logged_name
```

**What it validates:**
- Selection logic picks highest accuracy model
- Returned model matches MLflow's best run
- No off-by-one or sorting errors

---

### Test: Best Model Is Usable

```python
def test_best_model_can_predict(prepared_data, mock_mlflow):
    """Validate the returned best model can make predictions."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "experiment_name": "pytest-usable-model",
    }
    
    best_model, best_pipeline, _ = train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config=config
    )
    
    # Can predict on test set
    predictions = best_pipeline.predict(X_test)
    
    assert len(predictions) == len(y_test)
    assert all(p in [0, 1] for p in predictions)
    
    # Can predict on single row
    single_row = X_test.head(1)
    single_pred = best_pipeline.predict(single_row)
    
    assert len(single_pred) == 1
    assert single_pred[0] in [0, 1]
```

---

## Testing Cross-Validation

### Test: Cross-Validation Produces Stable Scores

```python
from sklearn.model_selection import cross_val_score

def test_cross_validation_scores_are_reasonable(prepared_data):
    """Validate cross-validation computes stable scores above a minimal baseline."""
    X_train, _, y_train, _, preprocessor = prepared_data
    
    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", LogisticRegression(max_iter=1000))
    ])
    
    # 3-fold cross-validation
    scores = cross_val_score(
        pipeline, X_train, y_train,
        cv=3,
        scoring="accuracy"
    )
    
    # Assert: Got 3 scores (one per fold)
    assert len(scores) == 3
    
    # Assert: All scores are reasonable (> 0.5 for this dataset)
    # (Random guessing would be ~0.5 for balanced binary)
    assert scores.mean() > 0.5, f"CV mean {scores.mean()} <= 0.5 baseline"
    
    # Assert: Scores are not all identical (variation expected)
    assert scores.std() > 0, "No variation in CV scores (suspicious)"
    
    # Assert: Scores are within reasonable range
    assert all(0 <= s <= 1 for s in scores)
```

**What it validates:**
- CV produces expected number of scores
- Model performs better than random (0.5)
- Some variation exists (not suspiciously identical)
- Scores are valid (0-1 range)

---

### Test: CV Scores Logged to MLflow

```python
def test_cross_validation_scores_logged(prepared_data, mock_mlflow):
    """Validate CV scores are logged with mean and std."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "experiment_name": "pytest-cv-logging",
    }
    
    train_model.fn(X_train, X_test, y_train, y_test, preprocessor, config=config)
    
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-cv-logging")
    runs = client.search_runs([experiment.experiment_id])
    
    # Check a run has CV metrics
    run = runs[0]
    
    # If CV is logged, we expect these metrics
    assert "cv_mean_accuracy" in run.data.metrics or \
           "cv_scores" in run.data.params
```

---

## Fixtures for Training Tests

### prepared_data fixture

```python
# conftest.py
@pytest.fixture
def prepared_data(sample_dataframe):
    """Build the same train/test/preprocessor tuple used by training."""
    from heart_disease_prediction.data import split_data_for_train
    return split_data_for_train.fn(sample_dataframe)
```

**Provides:**
- `X_train`: Training features (40 rows for 50-row sample)
- `X_test`: Test features (10 rows)
- `y_train`: Training targets
- `y_test`: Test targets
- `preprocessor`: Fitted ColumnTransformer

---

### mock_mlflow fixture

```python
# conftest.py
@pytest.fixture
def mock_mlflow(tmp_path):
    """Create an isolated local MLflow tracking store."""
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artifact_root = tmp_path / "mlartifacts"
    artifact_root.mkdir()
    
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("pytest-heart-disease")
    
    yield {
        "tracking_uri": tracking_uri,
        "artifact_root": f"file://{artifact_root}"
    }
    
    mlflow.end_run()
```

**Provides:**
- SQLite tracking URI (local file)
- Artifact directory
- Pre-configured experiment
- Automatic cleanup

---

## MLflow Mocking

### Why SQLite Backend?

| Aspect | Production | Test |
|--------|-----------|------|
| **Backend** | RDS PostgreSQL | SQLite |
| **Artifacts** | S3 | Local filesystem |
| **URI** | `http://32.196.26.238:5000` | `sqlite:///tmp/mlflow.db` |
| **Speed** | Network calls | In-memory (mostly) |
| **Cleanup** | Delete runs manually | Delete temp file |

**Benefits:**
- Same API (`mlflow.log_metric()` works identically)
- No network calls
- No server startup needed
- Automatic cleanup
- Deterministic

---

### Test: MLflow Experiment Creation

```python
def test_training_creates_experiment(mock_mlflow):
    """Validate training creates MLflow experiment if not exists."""
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "experiment_name": "brand-new-experiment",
    }
    
    # Before: experiment doesn't exist
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    assert client.get_experiment_by_name("brand-new-experiment") is None
    
    # Action: Train (should create experiment)
    train_model.fn(X_train, X_test, y_train, y_test, preprocessor, config=config)
    
    # After: experiment exists
    experiment = client.get_experiment_by_name("brand-new-experiment")
    assert experiment is not None
```

---

### Test: MLflow Run Structure

```python
def test_mlflow_run_has_correct_structure(prepared_data, mock_mlflow):
    """Validate each run has params, metrics, and tags."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "experiment_name": "pytest-run-structure",
    }
    
    train_model.fn(X_train, X_test, y_train, y_test, preprocessor, config=config)
    
    client = MlflowClient(tracking_uri=mock_mlflow["tracking_uri"])
    experiment = client.get_experiment_by_name("pytest-run-structure")
    runs = client.search_runs([experiment.experiment_id])
    
    for run in runs:
        # Has params
        assert "model" in run.data.params
        
        # Has metrics
        assert "accuracy" in run.data.metrics
        
        # Has status
        assert run.info.status == "FINISHED"
        
        # Has timestamps
        assert run.info.start_time < run.info.end_time
```

---

## Common Patterns

### Pattern: Speed vs. Realism Trade-off

```python
# Very fast (for unit tests)
def test_fast_with_tiny_data():
    X = np.random.rand(10, 5)
    y = [0, 1] * 5
    model = LogisticRegression(max_iter=100)
    model.fit(X, y)
    assert model.coef_.shape == (1, 5)

# Slower but realistic (for integration)
def test_realistic_with_sample(prepared_data):
    X_train, _, y_train, _, _ = prepared_data
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)
    assert model.score(X_train, y_train) > 0.5
```

**Recommendation:** Use sample data (50-100 rows) for balance.

---

### Pattern: Deterministic Training

```python
# Good: Fixed random_state
def test_deterministic(prepared_data):
    X_train, _, y_train, _, preprocessor = prepared_data
    
    model = RandomForestClassifier(
        n_estimators=10,
        random_state=42  # Fixed!
    )
    pipeline = Pipeline([("prep", preprocessor), ("clf", model)])
    pipeline.fit(X_train, y_train)
    
    score1 = pipeline.score(X_train, y_train)
    
    # Re-fit with same seed
    model2 = RandomForestClassifier(n_estimators=10, random_state=42)
    pipeline2 = Pipeline([("prep", preprocessor), ("clf", model2)])
    pipeline2.fit(X_train, y_train)
    score2 = pipeline2.score(X_train, y_train)
    
    assert score1 == score2  # Deterministic!

# Bad: Non-deterministic
def test_nondeterministic(prepared_data):
    model = RandomForestClassifier(n_estimators=10)  # No random_state!
    # Results vary between runs
```

---

### Pattern: Testing Error Handling

```python
def test_training_handles_empty_data(mock_mlflow):
    """Validate training fails gracefully with empty data."""
    X_empty = pd.DataFrame()
    y_empty = pd.Series()
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "experiment_name": "pytest-error",
    }
    
    with pytest.raises(ValueError) as exc_info:
        train_model.fn(X_empty, X_empty, y_empty, y_empty, None, config=config)
    
    assert "empty" in str(exc_info.value).lower()
```

---

### Pattern: Verifying Side Effects

```python
def test_training_creates_artifacts(prepared_data, mock_mlflow):
    """Validate model artifacts are saved to artifact store."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    config = {
        "mlflow_tracking_uri": mock_mlflow["tracking_uri"],
        "mlflow_artifact_root": mock_mlflow["artifact_root"],
        "experiment_name": "pytest-artifacts",
    }
    
    _, _, _ = train_model.fn(X_train, X_test, y_train, y_test, preprocessor, config=config)
    
    # Verify artifacts on filesystem
    artifact_path = Path(mock_mlflow["artifact_root"].replace("file://", ""))
    
    # Should have experiment directories
    assert any(artifact_path.iterdir())
    
    # Should have model subdirectories
    model_dirs = list(artifact_path.rglob("model*"))
    assert len(model_dirs) > 0
```

---

## Key Takeaways

1. **Test all model types** — Ensure they work with our data
2. **Test metrics logging** — Verify MLflow integration
3. **Test selection logic** — Best model is actually best
4. **Use SQLite for MLflow** — Fast, isolated, no server
5. **Set random_state** — Deterministic tests
6. **Keep data small** — 50-100 rows is enough
7. **Test pipeline structure** — preprocessor + classifier
8. **Verify predictions** — Binary, valid range

---

## Next

- [05 — Testing API with TestClient](05-testing-api-with-testclient.md) — FastAPI testing without server
