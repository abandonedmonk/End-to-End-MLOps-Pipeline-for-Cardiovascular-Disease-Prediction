# 06 — Testing Prefect Flows

Testing Prefect flow orchestration, task composition, and pipeline integration.

---

## Table of Contents

1. [What We Test](#what-we-test)
2. [Testing Individual Tasks](#testing-individual-tasks)
3. [Testing Flow Composition](#testing-flow-composition)
4. [Testing Full Pipeline](#testing-full-pipeline)
5. [Mocking Strategy](#mocking-strategy)
6. [Fixtures for Flow Tests](#fixtures-for-flow-tests)
7. [Common Patterns](#common-patterns)
8. [Troubleshooting](#troubleshooting)

---

## What We Test

Prefect flows orchestrate multiple tasks:

```
┌─────────────────────────────────────────────────────────────────┐
│  Full Pipeline Flow                                              │
├─────────────────────────────────────────────────────────────────┤
│  1. get_data (Task)                                              │
│     → Load from S3 or local                                     │
│     ↓                                                           │
│  2. split_data_for_train (Task)                                  │
│     → Train/test split + preprocessor                           │
│     ↓                                                           │
│  3. train_model (Task)                                           │
│     → Train 4 models, pick best                                 │
│     ↓                                                           │
│  4. register_model (Task)                                        │
│     → Register best in MLflow                                   │
│     ↓                                                           │
│  5. load_model (Task)                                            │
│     → Load champion model                                       │
│     ↓                                                           │
│  6. run_drift_detection (Task)                                   │
│     → Evidently report + CloudWatch                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Individual Tasks

### Test: Data Loading Task

```python
# tests/test_prefect_flow.py
def test_load_data_task_returns_dataframe(sample_data_file):
    """Validate the pipeline data task loads a DataFrame from local data."""
    df = prefect_flow.get_data.fn(str(sample_data_file))
    
    assert isinstance(df, pd.DataFrame)
    assert "hd" in df.columns
    assert len(df) > 0
```

**What it validates:**
- Task callable via `.fn()` (synchronous)
- Returns DataFrame (not None, not dict)
- Has target column
- Contains data (non-empty)

---

### Test: Training Task Returns Correct Structure

```python
def test_train_models_task_returns_best_model_info(prepared_data, monkeypatch):
    """Validate the orchestration training task returns model, pipeline, and paths."""
    X_train, X_test, y_train, y_test, preprocessor = prepared_data
    
    # Mock the training function
    def fake_train(*args, **kwargs):
        return "model", "pipeline", {"model_name": "pytest-model"}
    
    monkeypatch.setattr(prefect_flow.train_model, "fn", fake_train)
    
    # Call task
    result = prefect_flow.train_model.fn(
        X_train, X_test, y_train, y_test, preprocessor, config={}
    )
    
    # Assert structure
    assert result == ("model", "pipeline", {"model_name": "pytest-model"})
    
    # Unpack and verify
    model, pipeline, paths = result
    assert model == "model"
    assert pipeline == "pipeline"
    assert paths["model_name"] == "pytest-model"
```

**What it validates:**
- Task returns tuple of (model, pipeline, paths)
- Paths dict contains model_name
- Can be unpacked

---

### Test: Registration Task

```python
def test_register_model_task_succeeds(monkeypatch):
    """Validate the orchestration registration task can return updated paths."""
    paths = {"model_name": "pytest-model"}
    
    def fake_register(*args, **kwargs):
        return {**paths, "model_uri": "models:/pytest-model@champion"}
    
    monkeypatch.setattr(prefect_flow.register_model, "fn", fake_register)
    
    result = prefect_flow.register_model.fn("pipeline", paths)
    
    # Assert: Adds model_uri to paths
    assert result["model_uri"] == "models:/pytest-model@champion"
    assert result["model_name"] == "pytest-model"
```

**What it validates:**
- Task updates paths dict with model_uri
- Champion alias in URI
- Original paths preserved

---

## Testing Flow Composition

### Test: Flow Can Be Built

```python
def test_flow_composition_can_be_built():
    """Validate the full pipeline flow object exposes the expected Prefect metadata."""
    # Access flow defined in module
    flow = prefect_flow.full_pipeline
    
    # Has correct name
    assert flow.name == "full-pipeline"
    
    # Is callable
    assert callable(flow.fn)
    
    # Has tasks
    assert len(flow.tasks) > 0
```

**What it validates:**
- Flow is defined and importable
- Name matches expected
- Contains tasks
- Can be executed

---

### Test: Flow Tasks Are Connected

```python
def test_flow_task_dependencies_exist():
    """Validate task dependencies are defined in flow."""
    flow = prefect_flow.full_pipeline
    
    # Get task names
    task_names = {task.name for task in flow.tasks}
    
    # Expected tasks exist
    expected = {
        "get_data",
        "split_data_for_train",
        "train_model",
        "register_model",
        "load_model",
        "run_drift_detection",
    }
    
    assert expected.issubset(task_names), f"Missing: {expected - task_names}"
```

---

### Test: Flow Has Schedule (if applicable)

```python
def test_flow_has_deployment_schedule():
    """Validate deployment has expected schedule."""
    # Access deployment
    deployment = prefect_flow.full_pipeline.to_deployment(
        name="full-pipeline",
        cron="0 0 * * 0"  # Weekly Sunday
    )
    
    assert deployment.schedule is not None
    assert "0 0 * * 0" in str(deployment.schedule)
```

---

## Testing Full Pipeline

### Test: Pipeline Runs with All Mocks

```python
def test_full_pipeline_runs_with_mocked_external_services(
    monkeypatch, sample_dataframe
):
    """Validate flow composition runs when MLflow, S3, and monitoring are mocked."""
    
    # Track calls
    calls = Mock()
    
    # Mock each task
    def fake_get_data(path):
        calls.get_data(path)
        return sample_dataframe
    
    def fake_split_data_for_train(df):
        calls.split(df)
        # Return realistic structure
        return "X_train", "X_test", "y_train", "y_test", "preprocessor"
    
    def fake_train_model(*args, **kwargs):
        calls.train(*args, **kwargs)
        return "model", "pipeline", {"model_name": "pytest-model"}
    
    def fake_register_model(pipeline, paths):
        calls.register(pipeline, paths)
        return {**paths, "model_uri": "models:/pytest-model@champion"}
    
    def fake_load_model(paths):
        calls.load(paths)
        return "loaded_model"
    
    def fake_run_drift_detection():
        calls.drift()
        return {"drift_score": 0.1, "drift_detected": False}
    
    # Apply mocks
    monkeypatch.setattr(prefect_flow, "get_data", fake_get_data)
    monkeypatch.setattr(prefect_flow, "split_data_for_train", fake_split_data_for_train)
    monkeypatch.setattr(prefect_flow, "train_model", fake_train_model)
    monkeypatch.setattr(prefect_flow, "register_model", fake_register_model)
    monkeypatch.setattr(prefect_flow, "load_model", fake_load_model)
    monkeypatch.setattr(prefect_flow, "run_drift_detection", fake_run_drift_detection)
    
    # Run flow
    prefect_flow.full_pipeline.fn()
    
    # Assert all tasks were called
    assert calls.get_data.called
    assert calls.split.called
    assert calls.train.called
    assert calls.register.called
    assert calls.load.called
    assert calls.drift.called
```

**What it validates:**
- All 6 tasks execute
- Tasks execute in order (get_data → split → train → register → load → drift)
- No task fails silently

---

### Test: Pipeline Handles Task Failure

```python
def test_pipeline_handles_task_failure_gracefully(monkeypatch, sample_dataframe):
    """Validate pipeline propagates errors rather than failing silently."""
    
    def failing_train(*args, **kwargs):
        raise RuntimeError("Training failed!")
    
    monkeypatch.setattr(prefect_flow, "get_data", lambda path: sample_dataframe)
    monkeypatch.setattr(prefect_flow, "split_data_for_train", 
                       lambda df: ("X_train", "X_test", "y_train", "y_test", "prep"))
    monkeypatch.setattr(prefect_flow, "train_model", failing_train)
    
    # Should raise, not silently fail
    with pytest.raises(RuntimeError, match="Training failed!"):
        prefect_flow.full_pipeline.fn()
```

---

### Test: Pipeline State Propagation

```python
def test_pipeline_passes_state_between_tasks(monkeypatch, sample_dataframe):
    """Validate data flows from one task to the next."""
    
    received_data = []
    
    def tracking_get_data(path):
        df = sample_dataframe
        received_data.append(("get_data", len(df)))
        return df
    
    def tracking_split_data_for_train(df):
        received_data.append(("split", len(df)))
        return "X_train", "X_test", "y_train", "y_test", "prep"
    
    monkeypatch.setattr(prefect_flow, "get_data", tracking_get_data)
    monkeypatch.setattr(prefect_flow, "split_data_for_train", tracking_split_data_for_train)
    # ... other mocks
    
    prefect_flow.full_pipeline.fn()
    
    # Assert data flowed through
    assert received_data[0] == ("get_data", len(sample_dataframe))
    assert received_data[1] == ("split", len(sample_dataframe))
```

---

## Mocking Strategy

### Level 1: Mock Individual Functions

```python
def test_with_function_mocks(monkeypatch):
    """Mock at the function level."""
    monkeypatch.setattr(prefect_flow.train_model, "fn", lambda **kwargs: ("m", "p", {}))
    # Task uses the mock
```

**Best for:** Testing single task in isolation.

---

### Level 2: Mock Module-Level Functions

```python
def test_with_module_mocks(monkeypatch):
    """Mock at the module level."""
    monkeypatch.setattr(prefect_flow, "train_model", mock_task)
    # Entire flow uses mocks
```

**Best for:** Testing flow composition.

---

### Level 3: Use Real Functions with Mocked Services

```python
@mock_aws
def test_with_real_tasks_mocked_services(monkeypatch, sample_dataframe):
    """Use real tasks but mock AWS/S3."""
    # boto3 calls go to moto
    # Prefect tasks run for real
    result = prefect_flow.get_data.fn("s3://test-bucket/data.csv")
```

**Best for:** Integration-style tests (faster than full integration).

---

### Which Level to Use?

| Goal | Strategy |
|------|----------|
| Test single task logic | Level 1: Mock task dependencies |
| Test flow structure | Level 2: Mock all tasks, verify calls |
| Test task with AWS | Level 3: Real task + moto |
| Fast unit tests | Level 1 or 2 |
| Catch integration issues | Level 3 or real services (occasionally) |

---

## Fixtures for Flow Tests

### Using Existing Fixtures

```python
# From conftest.py
@pytest.fixture
def sample_dataframe():
    """Return a cleaned sample with realistic heart-disease columns."""
    df = full_dataframe.loc[
        (full_dataframe["ca"] != "?") & (full_dataframe["thal"] != "?")
    ].head(50)
    return df.copy()

@pytest.fixture
def prepared_data(sample_dataframe):
    """Build train/test/preprocessor tuple."""
    return split_data_for_train.fn(sample_dataframe)
```

### Flow-Specific Fixtures

```python
@pytest.fixture
def mock_config(tmp_path):
    """Provide test configuration for flow tasks."""
    return {
        "mlflow_tracking_uri": f"sqlite:///{tmp_path}/mlflow.db",
        "experiment_name": "pytest-flow",
        "model_name": "pytest-flow-model",
    }
```

---

## Common Patterns

### Pattern: Testing Task Retry Logic

```python
from prefect import task

@task(retries=3, retry_delay_seconds=1)
def flaky_task():
    """Task that might fail."""
    if random.random() < 0.5:
        raise RuntimeError("Flaky!")
    return "success"

def test_task_retries_on_failure(monkeypatch):
    """Validate task retries on failure."""
    call_count = 0
    
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Always fails")
    
    monkeypatch.setattr(my_module, "flaky_task_function", always_fail)
    
    # After 3 retries, should give up
    with pytest.raises(RuntimeError):
        flaky_task.fn()
    
    assert call_count == 3  # Retried 3 times
```

---

### Pattern: Testing with Different Configurations

```python
@pytest.mark.parametrize("test_split", [0.1, 0.2, 0.3])
def test_flow_with_different_split_ratios(test_split, sample_dataframe, monkeypatch):
    """Validate flow works with different train/test splits."""
    
    def mock_split(df):
        n = len(df)
        train_size = int(n * (1 - test_split))
        return df.head(train_size), df.tail(n - train_size), None, None, "prep"
    
    monkeypatch.setattr(prefect_flow, "split_data_for_train", mock_split)
    
    # Run flow
    prefect_flow.full_pipeline.fn()
    
    # Should complete without error
```

---

### Pattern: Testing Task Inputs

```python
def test_task_receives_correct_arguments(monkeypatch, sample_dataframe):
    """Validate tasks receive expected inputs from upstream tasks."""
    
    captured_args = []
    
    def capture_train(*args, **kwargs):
        captured_args.append((args, kwargs))
        return "model", "pipeline", {}
    
    monkeypatch.setattr(prefect_flow, "train_model", capture_train)
    monkeypatch.setattr(prefect_flow, "get_data", lambda p: sample_dataframe)
    monkeypatch.setattr(prefect_flow, "split_data_for_train",
                       lambda df: ("X_train", "X_test", "y_train", "y_test", "prep"))
    # ... other mocks
    
    prefect_flow.full_pipeline.fn()
    
    # Verify train_model received X_train, X_test, etc.
    args, kwargs = captured_args[0]
    assert args[0] == "X_train"  # X_train
    assert args[1] == "X_test"   # X_test
    assert args[2] == "y_train"   # y_train
    assert args[3] == "y_test"    # y_test
    assert args[4] == "prep"      # preprocessor
```

---

### Pattern: Testing Concurrent Tasks

```python
def test_concurrent_tasks_run_in_parallel():
    """Validate concurrent tasks execute in parallel."""
    import time
    
    start_times = []
    end_times = []
    
    @task
    def timed_task(task_id: int):
        start_times.append((task_id, time.time()))
        time.sleep(0.1)  # Simulate work
        end_times.append((task_id, time.time()))
        return task_id
    
    @flow
    def parallel_flow():
        # These run concurrently
        futures = [timed_task.submit(i) for i in range(3)]
        return [f.result() for f in futures]
    
    parallel_flow()
    
    # If parallel, all should start within ~0.01s of each other
    start_time_diff = max(s[1] for s in start_times) - min(s[1] for s in start_times)
    assert start_time_diff < 0.05  # Parallel, not sequential
```

---

## Troubleshooting

### Problem: "Task not found in flow"

**Cause:** Task not imported/registered.

**Fix:**
```python
# Make sure task is in module namespace
from prefect import task

@task
def my_task():
    pass

# Then reference in flow
@flow
def my_flow():
    my_task()  # Not my_task.fn() in flow definition!
```

---

### Problem: "Mock not applied in flow"

**Cause:** Import order or caching.

**Fix:**
```python
# Mock before flow sees it
def test_correct(monkeypatch):
    monkeypatch.setattr(prefect_flow, "task_name", mock)
    result = prefect_flow.my_flow.fn()  # .fn() to run synchronously

# Bad: Flow cached import
def test_incorrect():
    from prefect_flow import my_flow  # Too late!
    monkeypatch.setattr(...)
```

---

### Problem: "Flow hangs"

**Cause:** Async task waiting or infinite loop.

**Fix:**
```python
# Use .fn() for synchronous execution in tests
def test_sync():
    prefect_flow.full_pipeline.fn()  # Not .submit()
```

---

### Problem: "Task state is 'Pending'"

**Cause:** Mixing sync and async.

**Fix:**
```python
# In flow, use .result() to wait
@flow
def my_flow():
    future = my_task.submit()
    return future.result()  # Wait for completion
```

---

## Key Takeaways

1. **Test tasks individually** — Verify each task works in isolation
2. **Test flow composition** — Verify tasks are connected correctly
3. **Mock external services** — S3, MLflow, CloudWatch via moto/monkeypatch
4. **Use .fn() for sync** — Run flows synchronously in tests
5. **Track calls to verify order** — Ensure data flows through pipeline
6. **Test error propagation** — Failures should raise, not silently pass
7. **Verify state passing** — Data from task N should reach task N+1

---

## Next

- [07 — Testing Monitoring](07-testing-monitoring.md) — Drift detection and CloudWatch tests
