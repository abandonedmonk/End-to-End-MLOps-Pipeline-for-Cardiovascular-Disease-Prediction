# 08 — Troubleshooting Tests

Common test failures, debugging techniques, and fixes.

---

## Table of Contents

1. [Test Discovery Issues](#test-discovery-issues)
2. [Fixture Problems](#fixture-problems)
3. [Mocking Issues](#mocking-issues)
4. [Import Problems](#import-problems)
5. [Assertion Failures](#assertion-failures)
6. [Coverage Issues](#coverage-issues)
7. [Performance Problems](#performance-problems)
8. [CI/CD Test Failures](#cicd-test-failures)
9. [Debugging Techniques](#debugging-techniques)
10. [Test Maintenance](#test-maintenance)

---

## Test Discovery Issues

### Problem: "No tests found"

**Symptom:**
```bash
$ pytest tests/
========================= no tests ran =========================
```

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Wrong file naming | Rename to `test_*.py` or `*_test.py` |
| Wrong function naming | Rename to `test_*` |
| Tests in subdirectories without `__init__.py` | Add empty `__init__.py` files |
| pytest not finding directory | Run with `pytest tests/` explicit path |
| `pytest.ini` excludes tests | Check `norecursedirs` setting |

**Check naming:**
```bash
# Should work:
tests/
├── test_data.py           # File: test_ prefix
├── test_train.py
└── conftest.py            # Fixture file (no test_ prefix!)

# Inside test_data.py:
def test_load_data():      # Function: test_ prefix
    pass
```

---

### Problem: "Test file not collected"

**Check collection:**
```bash
pytest --collect-only tests/test_data.py
```

**Fix `conftest.py` location:**
```bash
# conftest.py should be in tests/ directory, not test files
tests/
├── conftest.py          # Here!
├── test_data.py         # Not here
└── test_train.py
```

---

## Fixture Problems

### Problem: "Fixture not found"

**Symptom:**
```
E       fixture 'sample_dataframe' not found
```

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Fixture in wrong file | Move to `conftest.py` or same file |
| Typo in name | Check spelling |
| Fixture not returned | Ensure `return` statement exists |
| Fixture scope too narrow | Change to `scope="session"` or broader |

**Example:**
```python
# conftest.py - Available to all tests in directory
@pytest.fixture
def sample_dataframe():
    return pd.DataFrame(...)  # Don't forget return!
```

---

### Problem: "Fixture yields None"

**Bad (missing return/yield):**
```python
@pytest.fixture
def bad_fixture():
    df = pd.DataFrame(...)  # Created but not returned!
    # No return statement

def test_uses_it(bad_fixture):
    assert bad_fixture is None  # Fails!
```

**Good:**
```python
@pytest.fixture
def good_fixture():
    df = pd.DataFrame(...)
    return df  # Or: yield df for cleanup

def test_uses_it(good_fixture):
    assert len(good_fixture) > 0  # Works!
```

---

### Problem: "Fixture scope mismatch"

**Symptom:**
```
ScopeMismatch: You tried to access the 'function' scoped fixture 
'mock_mlflow' with a 'session' scoped fixture.
```

**Fix:** Match scopes or adjust structure:
```python
# Option 1: Make both function scope (default)
@pytest.fixture  # function scope
def mock_mlflow(tmp_path):
    ...

# Option 2: Make both session scope
@pytest.fixture(scope="session")
def mock_mlflow():
    ...

# Option 3: Don't mix - use tmp_path_factory for session
@pytest.fixture(scope="session")
def session_temp(tmp_path_factory):
    return tmp_path_factory.mktemp("data")
```

---

### Problem: "Fixture runs too often" (slow tests)

**Fix:** Use broader scope:
```python
@pytest.fixture(scope="module")  # Once per module, not per test
def expensive_setup():
    """Setup that can be shared across tests."""
    result = slow_operation()
    yield result
    cleanup(result)
```

**Scopes:**
- `function`: Every test (default)
- `class`: Once per test class
- `module`: Once per module
- `package`: Once per package
- `session`: Once per test run

---

## Mocking Issues

### Problem: "Mock not applied"

**Symptom:** Real function called instead of mock.

**Common cause - import order:**
```python
# Bad: Import before mock
from heart_disease_prediction import data  # Real import cached!

def test_bad(monkeypatch):
    monkeypatch.setattr(data, "function", mock)  # Too late!
    data.function()  # Still calls real function

# Good: Import after mock or reimport
def test_good(monkeypatch):
    monkeypatch.setattr(data, "function", mock)
    import importlib
    importlib.reload(data)  # Force reimport
    data.function()  # Uses mock
```

**Or use `import_fresh` fixture:**
```python
def test_with_fresh_import(monkeypatch, import_fresh):
    monkeypatch.setattr(mlflow.pyfunc, "load_model", mock)
    module = import_fresh("api.main")  # Fresh with mock
```

---

### Problem: "moto not intercepting boto3"

**Symptom:** Real AWS calls made, credentials errors.

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| boto3 imported outside @mock_aws | Move import inside test or reload |
| Wrong moto version | Use `@mock_aws` (moto 5.x), not `@mock_s3` (4.x) |
| Regional client mismatch | Match region in boto3.client() and moto |
| Multiple AWS services | Use `@mock_aws` not specific decorators |

**Correct pattern:**
```python
from moto import mock_aws

@mock_aws
def test_s3():
    import boto3  # Import inside decorated function
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test")  # Works!
```

---

### Problem: "monkeypatch not affecting imported module"

**Example:**
```python
# conftest.py or test file
import os

def test_env(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "test")
    
    # Module imported at top level
    from api import main  # Sees original env!
    
    assert main.model_name == "test"  # Fails!
```

**Fix - defer import or reload:**
```python
def test_env(monkeypatch, import_fresh):
    monkeypatch.setenv("MODEL_NAME", "test")
    
    main = import_fresh("api.main")  # Fresh import with new env
    
    assert main.model_name == "test"  # Works!
```

---

## Import Problems

### Problem: "ModuleNotFoundError: No module named 'api'"

**Causes:**
1. Running pytest from wrong directory
2. Missing `__init__.py`
3. PYTHONPATH not set

**Fixes:**

```bash
# 1. Run from project root
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project
pytest tests/

# 2. Add __init__.py files
touch api/__init__.py
touch heart_disease_prediction/__init__.py
touch tests/__init__.py

# 3. Install package in editable mode
pip install -e .

# 4. Use python -m pytest
python -m pytest tests/  # Adds current directory to path
```

---

### Problem: "ImportError: cannot import name 'X'"

**Check:**
```bash
# Verify module has the name
python -c "from heart_disease_prediction import X"

# Check for circular imports
python -c "import heart_disease_prediction.train"
```

**Common fix - absolute imports:**
```python
# Bad: Relative import that might fail
from . import data

# Good: Absolute import
from heart_disease_prediction import data
```

---

## Assertion Failures

### Problem: "AssertionError: expected X got Y"

**Add context to assertion:**
```python
# Bad: No context
assert result == expected

# Good: Descriptive message
assert result == expected, f"Expected {expected}, got {result}. Input was {input_data}"

# Better: Use pytest helper
from pytest import approx
assert result == approx(expected, abs=0.001), f"Values differ by {abs(result - expected)}"
```

---

### Problem: "Flaky test - sometimes passes, sometimes fails"

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Random state not fixed | Add `random_state=42` to all models |
| Test order dependency | Make tests independent, no shared state |
| Time-based assertions | Mock time or use approx ranges |
| External service calls | Mock S3/MLflow/CloudWatch |
| File system state | Use `tmp_path`, clean up in fixtures |

**Fix randomness:**
```python
# Bad: Non-deterministic
def test_model():
    model = RandomForestClassifier()  # Random!
    model.fit(X, y)
    score = model.score(X, y)
    assert score > 0.8  # Might fail!

# Good: Deterministic
def test_model():
    model = RandomForestClassifier(random_state=42)  # Fixed!
    model.fit(X, y)
    score = model.score(X, y)
    assert score == 0.853  # Exact match expected
```

---

### Problem: "DataFrame equals assertion fails"

**Use pandas testing helpers:**
```python
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

def test_dataframe():
    result = process_data(input_df)
    expected = pd.DataFrame({"col": [1, 2, 3]})
    
    # Bad: Might fail on dtype differences
    assert result == expected
    
    # Good: Pandas-aware comparison
    assert_frame_equal(result, expected)
    
    # With tolerance for floats
    assert_frame_equal(result, expected, check_dtype=False, atol=0.001)
```

---

## Coverage Issues

### Problem: "Coverage below 80%"

**Check what's missing:**
```bash
# Generate HTML report
pytest --cov=heart_disease_prediction --cov-report=html tests/
# Open htmlcov/index.html in browser

# Show missing lines
pytest --cov=heart_disease_prediction --cov-report=term-missing tests/
```

**Common uncovered code:**

| Code | Test Strategy |
|------|---------------|
| `if __name__ == "__main__":` | Move to function, or skip with `# pragma: no cover` |
| Error handling branches | Add tests for error conditions |
| Debug/logging code | Mock logger, assert called |
| Type checking code | Parametrize with different types |
| Platform-specific code | Test on each platform in CI |

**Exclude from coverage (pyproject.toml):**
```toml
[tool.coverage.run]
omit = [
    "*/tests/*",
    "*/conftest.py",
    "*/__init__.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

---

### Problem: "Coverage report shows 0%"

**Check:**
```bash
# Is pytest-cov installed?
pip list | grep pytest-cov

# Is the module installed?
pip install -e .  # Editable install

# Run with explicit path
pytest --cov=heart_disease_prediction tests/
```

---

## Performance Problems

### Problem: "Tests take too long"

**Profile tests:**
```bash
# Find slowest tests
pytest --durations=10 tests/

# Run with verbose timing
pytest --durations=0 -v tests/
```

**Optimization strategies:**

| Strategy | Implementation |
|----------|----------------|
| Smaller test data | Use 50 rows instead of 300 |
| Mock heavy operations | Mock Evidently, S3, MLflow |
| Reduce model complexity | `n_estimators=10` not 1000 |
| Wider fixture scope | `scope="module"` for expensive setup |
| Parallel test execution | `pytest-xdist` plugin |

**Install pytest-xdist for parallel execution:**
```bash
pip install pytest-xdist
pytest -n auto tests/  # Run in parallel
```

---

### Problem: "Memory usage growing"

**Check for:**
- Large fixtures not cleaned up
- MLflow runs accumulating
- DataFrames in global scope

**Fix with explicit cleanup:**
```python
@pytest.fixture
def large_data():
    df = pd.DataFrame(np.random.rand(100000, 100))
    yield df
    # Cleanup after test
    del df
    import gc
    gc.collect()
```

---

## CI/CD Test Failures

### Problem: "Tests pass locally, fail in CI"

**Check:**

| Check | CI Fix |
|-------|--------|
| Python version | Pin version in CI (e.g., 3.12) |
| Dependencies | Lock requirements.txt, use pip freeze |
| Environment variables | Set all env vars in CI workflow |
| File paths | Use `tmp_path`, not hardcoded paths |
| Timezones | Set `TZ=UTC` or mock datetime |
| Secrets | Use GitHub Secrets, don't hardcode |

**Common CI fixes:**

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"  # Pin version!
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Set test environment
        run: |
          echo "MODEL_NAME=test-model" >> $GITHUB_ENV
          echo "AWS_REGION=us-east-1" >> $GITHUB_ENV
      
      - name: Run tests
        run: pytest tests/
```

---

### Problem: "Coverage fails in CI only"

**Cause:** Module installed differently in CI.

**Fix:**
```yaml
- name: Install package in editable mode
  run: pip install -e .

- name: Run coverage
  run: pytest --cov=heart_disease_prediction tests/
```

Or use source flag:
```bash
pytest --cov=heart_disease_prediction --cov-report=xml tests/
```

---

## Debugging Techniques

### Technique 1: pytest --pdb

```bash
# Drop into debugger on failure
pytest tests/test_data.py::test_load_data --pdb

# Inside pdb:
# (Pdb) p df.shape
# (Pdb) p df.columns.tolist()
# (Pdb) c  # Continue
```

---

### Technique 2: Print Debugging

```python
def test_with_debug():
    result = process_data()
    print(f"DEBUG: result = {result}")  # Shows with -s flag
    assert result == expected
```

Run with:
```bash
pytest tests/ -s  # Show print statements
```

---

### Technique 3: pytest --tb=long

```bash
# Full traceback
pytest tests/ --tb=long

# Or shorter
pytest tests/ --tb=short
pytest tests/ --tb=line
```

---

### Technique 4: Last Failed Tests

```bash
# Run only last failed tests
pytest --lf

# Run last failed first, then others
pytest --ff
```

---

### Technique 5: Test with Warnings

```bash
# Show all warnings
pytest tests/ -W always

# Warnings as errors
pytest tests/ -W error
```

---

### Technique 6: Fixture Debugging

```python
@pytest.fixture
def debug_fixture():
    print("\nFIXTURE SETUP")
    data = load_data()
    print(f"Loaded {len(data)} rows")
    yield data
    print("\nFIXTURE TEARDOWN")
    cleanup(data)
```

---

### Technique 7: Mock Inspection

```python
from unittest.mock import Mock, patch

def test_with_mock():
    mock_func = Mock(return_value="mocked")
    
    with patch("module.function", mock_func):
        result = call_function()
        
        # Inspect mock
        print(f"Called: {mock_func.called}")
        print(f"Call count: {mock_func.call_count}")
        print(f"Call args: {mock_func.call_args}")
        
        assert result == "mocked"
```

---

## Test Maintenance

### Regular Maintenance Tasks

| Task | Frequency | Command |
|------|-----------|---------|
| Update dependencies | Monthly | `pip list --outdated` |
| Remove dead code | Quarterly | `vulture` or `coverage` analysis |
| Speed up slow tests | Quarterly | `pytest --durations=10` |
| Review skipped tests | Monthly | `pytest -v` (look for s) |
| Update test data | As needed | Keep sample data realistic |

---

### Handling Deprecation Warnings

```bash
# See all warnings
pytest tests/ -W always

# Fix in code:
import warnings

def test_with_expected_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = legacy_function()
    
    assert result is not None
```

---

### Test Documentation

```python
def test_load_data_with_missing_file(tmp_path):
    """
    Test that loading non-existent file raises FileNotFoundError.
    
    Regression test for: https://github.com/org/repo/issues/123
    
    Given:
        - Path to non-existent file
    When:
        - get_data() is called
    Then:
        - Raises FileNotFoundError with path in message
    """
    missing = tmp_path / "missing.csv"
    
    with pytest.raises(FileNotFoundError) as exc_info:
        get_data(str(missing))
    
    assert str(missing) in str(exc_info.value)
```

---

## Key Takeaways

1. **Naming matters** — `test_` prefix on files and functions
2. **Fixtures need `return` or `yield`** — Or they yield None
3. **Mock before import** — Or use `import_fresh` to reload
4. **Use `tmp_path`** — Not hardcoded paths
5. **Set `random_state`** — For deterministic tests
6. **Check coverage with HTML report** — See uncovered lines visually
7. **Use pandas testing helpers** — `assert_frame_equal` not `==`
8. **Print debugging with `-s`** — Quick and effective
9. **Run `--pdb` on failures** — Interactive debugging
10. **Keep tests fast** — Mock external services, use small data

---

## Quick Reference Card

| Problem | Quick Fix |
|---------|-----------|
| No tests found | Check `test_` prefix on files/functions |
| Fixture not found | Move to `conftest.py` or check spelling |
| Mock not working | Import after mock or use `import_fresh` |
| Moto failing | Use `@mock_aws`, import boto3 inside decorator |
| Test too slow | Mock external calls, reduce data size |
| Coverage low | Check `htmlcov/index.html` for gaps |
| Flaky test | Fix random_state, remove shared state |
| CI different | Pin Python version, check env vars |
| Can't debug | Use `--pdb` or add `print()` with `-s` |

---

## Next

- Phase 8 is complete! 
- Move to Phase 9: Security hardening
