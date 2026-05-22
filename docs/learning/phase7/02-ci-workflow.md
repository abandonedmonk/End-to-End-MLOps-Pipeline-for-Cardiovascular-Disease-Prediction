# 02 — CI Workflow: Linting & Code Quality

## What is Continuous Integration (CI)?

**CI** automatically checks code quality on every Pull Request. It catches issues before they reach production.

**Our CI Steps:**
1. `flake8` — Style guide enforcement
2. `black --check` — Format verification
3. `isort --check` — Import sorting
4. Placeholder tests (Phase 8 adds real ones)

---

## Why Linting Matters

### Without Linting

```python
# messy_code.py
def predict( data):
  x=data.drop(['target'],axis=1)
  y=data['target']
  model=train(x,y)
  return model

import numpy as np
import pandas as pd
import sklearn
```

**Problems:**
- Inconsistent spacing
- Imports scattered
- Hard to review
- Easy to miss bugs

---

### With Linting

```python
# clean_code.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier


def predict(data):
    """Train model on data."""
    x = data.drop(['target'], axis=1)
    y = data['target']
    model = train(x, y)
    return model
```

**Benefits:**
- ✅ Consistent style
- ✅ Imports organized
- ✅ Easy to review
- ✅ Catches syntax errors

---

## The Tools

| Tool | Purpose | Example Fix |
|------|---------|-------------|
| **flake8** | Style guide (PEP 8) | `x=1` → `x = 1` |
| **black** | Auto-formatter | Makes everything consistent |
| **isort** | Import sorting | Groups stdlib, 3rd party, local |

---

## Tool Details

### flake8

**What it does:**
- Checks PEP 8 style guide
- Detects syntax errors
- Finds unused imports

**Configuration:**

```bash
# .flake8 or setup.cfg
[flake8]
max-line-length = 88
extend-ignore = E203  # Black handles this
exclude = 
    .git,
    __pycache__,
    .venv,
    infra/.terraform
```

**Running:**

```bash
# Check style
flake8 heart_disease_prediction/

# Strict mode (fail on any error)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Normal mode (report but don't fail)
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
```

---

### black

**What it does:**
- Auto-formats code
- Enforces consistent style
- No configuration needed ("opinionated")

**Configuration:**

```bash
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py312']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.direnv
  | \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | build
  | dist
)/
'''
```

**Running:**

```bash
# Check if code is formatted (CI mode)
black --check heart_disease_prediction/

# Auto-format (local development)
black heart_disease_prediction/

# Format and show what changed
black heart_disease_prediction/ --diff
```

---

### isort

**What it does:**
- Sorts imports alphabetically
- Groups by type (stdlib, 3rd party, local)
- Configurable style

**Configuration:**

```bash
# pyproject.toml
[tool.isort]
profile = "black"  # Compatible with black
line_length = 88
known_first_party = ["heart_disease_prediction", "api", "monitoring"]
```

**Running:**

```bash
# Check order (CI mode)
isort --check-only heart_disease_prediction/ --profile black

# Auto-sort (local development)
isort heart_disease_prediction/ --profile black
```

**Example Output:**

```python
# Before isort
import numpy as np
import os
from heart_disease_prediction.train import train_model
import pandas as pd
import sys

# After isort
import os
import sys

import numpy as np
import pandas as pd

from heart_disease_prediction.train import train_model
```

---

## Our CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main, aws_migration]

jobs:
  lint:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install linting tools
        run: |
          pip install flake8 black isort

      - name: Run flake8
        run: |
          # Strict check for syntax errors
          flake8 heart_disease_prediction/ api/ monitoring/ \
            --count --select=E9,F63,F7,F82 --show-source --statistics
          # Full check (report but don't fail on style)
          flake8 heart_disease_prediction/ api/ monitoring/ \
            --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

      - name: Run black check
        run: |
          black --check heart_disease_prediction/ api/ monitoring/ || true

      - name: Run isort check
        run: |
          isort --check-only heart_disease_prediction/ api/ monitoring/ \
            --profile black || true

      - name: Placeholder test
        run: |
          echo "Phase 8 will add real tests. For now, this passes."
          exit 0
```

---

## Understanding the `|| true` Pattern

You might notice:

```yaml
- name: Run black check
  run: |
    black --check ... || true
```

**What `|| true` does:**
- If command fails → continue anyway
- Prevents workflow from failing

**Why we use it:**

| Tool | Strict? | Why |
|------|---------|-----|
| flake8 (syntax) | ✅ Yes | Syntax errors MUST be fixed |
| flake8 (style) | ❌ No | Style issues logged but don't block |
| black | ❌ No | Format issues logged but don't block (for now) |
| isort | ❌ No | Import order logged but don't block (for now) |

**Gradual Adoption:**
1. **Now:** Only syntax errors block PR
2. **Soon:** Add black formatting requirement
3. **Later:** Add isort requirement
4. **Phase 8:** Real tests block PR

---

## Local Development Setup

### Install Dev Dependencies

```bash
# Using pip
pip install flake8 black isort pytest

# Or with your package manager
uv pip install flake8 black isort pytest
```

### Configure IDE Integration

**VS Code:**
```json
// settings.json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "ms-python.black-formatter",
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.sortImports.args": ["--profile", "black"]
}
```

**PyCharm:**
- Settings → Tools → Black → Enable
- Settings → Editor → Inspections → Enable flake8

### Pre-Commit Hook (Optional)

```bash
# Install pre-commit
pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
  
  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ["--profile", "black"]
  
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
EOF

# Install hooks
pre-commit install

# Now runs automatically on every commit!
```

---

## Makefile Integration

Add to your `Makefile`:

```makefile
.PHONY: lint format check test

# Check code style (CI mode)
lint:
	flake8 heart_disease_prediction/ api/ monitoring/ --count --statistics

# Auto-format code (local development)
format:
	black heart_disease_prediction/ api/ monitoring/
	isort heart_disease_prediction/ api/ monitoring/ --profile black

# Check formatting (CI mode)
check:
	black --check heart_disease_prediction/ api/ monitoring/
	isort --check-only heart_disease_prediction/ api/ monitoring/ --profile black

# Run tests (Phase 8)
test:
	pytest tests/

# Full quality check
quality: lint check test
```

Usage:
```bash
make format   # Fix everything
make lint     # Check everything
make quality  # Full check
```

---

## Phase 8: Real Testing

Current placeholder:

```python
# tests/test_placeholder.py
def test_placeholder():
    """This test always passes until Phase 8."""
    assert True
```

Future tests (Phase 8):

```python
# tests/test_model.py
import pytest
from heart_disease_prediction.train import train_model

def test_model_training():
    """Test that model trains without errors."""
    model = train_model("s3://bucket/data.csv")
    assert model is not None
    assert hasattr(model, 'predict')

def test_model_accuracy():
    """Test model meets accuracy threshold."""
    model = train_model("s3://bucket/data.csv")
    accuracy = evaluate_model(model, "s3://bucket/test.csv")
    assert accuracy > 0.85

# tests/test_api.py
import requests

def test_api_health():
    """Test API health endpoint."""
    response = requests.get("http://32.196.26.238:8000/health")
    assert response.status_code == 200
    assert response.json()["model_loaded"] is True
```

---

## Common Linting Issues

### Issue 1: Line Too Long

```python
# ❌ Bad (127+ characters)
result = some_function_with_very_long_name(first_parameter, second_parameter, third_parameter)

# ✅ Good
result = some_function_with_very_long_name(
    first_parameter,
    second_parameter,
    third_parameter
)
```

### Issue 2: Unused Imports

```python
# ❌ Bad
import pandas as pd
import numpy as np  # Never used!

data = pd.read_csv("file.csv")

# ✅ Good
import pandas as pd

data = pd.read_csv("file.csv")
```

### Issue 3: Trailing Whitespace

```bash
# ❌ flake8 error
W291 trailing whitespace

# ✅ Remove trailing spaces at end of lines
```

### Issue 4: Missing Docstrings

```python
# ❌ Bad
def train(x, y):
    return model.fit(x, y)

# ✅ Good
def train(x, y):
    """Train model on features and target.
    
    Args:
        x: Feature matrix
        y: Target vector
    
    Returns:
        Trained model
    """
    return model.fit(x, y)
```

---

## CI Workflow Flow

```
Developer creates PR
        │
        ▼
┌───────────────────┐
│ GitHub Actions    │
│ triggers CI       │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Checkout code     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌───────────────────┐
│ flake8 syntax     │───>│ ❌ FAIL → Block PR│
│ (E9,F63,F7,F82)   │     └───────────────────┘
└─────────┬─────────┘
          │ Pass
          ▼
┌───────────────────┐     ┌───────────────────┐
│ flake8 style      │───>│ ⚠️ Log but pass   │
│ (other codes)     │     └───────────────────┘
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌───────────────────┐
│ black check       │───>│ ⚠️ Log but pass   │
│                   │     └───────────────────┘
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌───────────────────┐
│ isort check       │───>│ ⚠️ Log but pass   │
│                   │     └───────────────────┘
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ placeholder test  │
│ (always passes)   │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ ✅ PASS → Allow   │
│ merge             │
└───────────────────┘
```

---

## Verification

### Test CI Locally

```bash
# 1. Create test branch
git checkout -b test-ci
echo "# test" >> README.md
git add . && git commit -m "Test CI"
git push origin test-ci

# 2. Open PR on GitHub
# CI should run automatically

# 3. Check status
gh pr checks test-ci

# 4. View logs
gh run list --workflow=CI
gh run view <run-id>
```

### Debug CI Failures

```bash
# Check specific step
gh run view <run-id> --job=lint

# Re-run failed jobs
gh run rerun <run-id>

# Watch live
gh run watch <run-id>
```

---

## Key Takeaways

1. **Linting prevents bugs** — Syntax errors caught before merge
2. **Consistent style** — Code reviews focus on logic, not formatting
3. **Automated enforcement** — No manual checking required
4. **Gradual adoption** — Start strict on syntax, relax on style initially
5. **IDE integration** — Catch issues before commit

---

## Next Steps

- ✅ Read [03 — CD Workflow](03-cd-workflow.md) for deployment automation
- ✅ Set up local linting in your IDE
- ✅ Run `make format` on your code
- ✅ Create test PR to verify CI runs
