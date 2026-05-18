# 04 — Local Dev with uv

## What We Did

Created a local Python virtual environment using `uv` (instead of `pip`/`venv`) and installed all project dependencies:

```bash
uv venv .venv --python 3.12
uv pip install -r requirements.txt
```

Result: 131 packages installed in ~24 seconds (vs ~5 minutes with pip).

## Why uv (Not pip or pipenv)

| Aspect | pip + venv | pipenv | uv |
|--------|-----------|--------|-----|
| Install speed | ~5 min (149 packages) | ~6 min | ~14 seconds |
| venv creation | `python -m venv .venv` | `pipenv install` | `uv venv .venv` |
| Lock file | requirements.txt | Pipfile.lock | uv.lock |
| Dependency resolver | Can get stuck in loops | Slow, complex | Rust-based, fast |
| Global cache | No | No | Yes (shared across venvs) |
| Python version mgmt | pyenv | pyenv | Built-in (`uv python install`) |

**Our choice**: uv — dramatically faster, especially on t2.micro where CPU time is scarce. Same tool on both EC2 and local machine.

## Theory: Python Virtual Environments

### The Problem Without venv

```
/usr/bin/python3    → Python 3.13 (system)
                     ├── numpy 2.0 (system package)
                     ├── mlflow 1.x (system package)
                     └── ... 200 other packages
```

If you `pip install mlflow==2.13.0`, it upgrades numpy globally, breaking other programs. Virtual environments solve this by isolating each project's packages.

### How venv Works

```
.venv/                          ← Virtual environment directory
├── bin/
│   ├── python3 → ../lib/...    ← Symlink to the real Python binary
│   ├── pip                     ← pip that only sees .venv packages
│   └── uvicorn                 ← Installed scripts
├── lib/
│   └── python3.12/
│       └── site-packages/
│           ├── mlflow/         ← Project-specific packages
│           ├── sklearn/
│           └── ...
└── pyvenv.cfg                  ← Config: which Python, whether system packages are visible
```

When activated (`source .venv/bin/activate`):
- `python` → `.venv/bin/python` (not `/usr/bin/python3`)
- `pip install X` → installs into `.venv/lib/` (not system)
- `import mlflow` → finds it in `.venv/lib/` first

### Why Python 3.12

| Python | Status | MLflow 2.13 support | Note |
|--------|--------|---------------------|------|
| 3.9 | EOL (Oct 2025) | Yes | Too old |
| 3.10 | Security fixes | Yes | Fine but aging |
| 3.11 | Active | Yes | Good choice |
| **3.12** | **Active** | **Yes** | **Our choice** — latest stable, good perf |
| 3.13 | Active | Experimental | Risk of breakage |

MLflow 2.13.0 officially supports Python 3.8-3.12. Python 3.13 works but is not officially supported yet.

## The setuptools Problem (Same Fix, Local Too)

### Symptom

```
ModuleNotFoundError: No module named 'pkg_resources'
```

### Why It Happens Locally Too

1. `uv venv .venv --python 3.12` creates a lean venv (no setuptools bundled)
2. `uv pip install mlflow==2.13.0` pulls in `setuptools>=82` (latest)
3. `setuptools>=71` removed the `pkg_resources` module
4. `mlflow` imports `pkg_resources` → crash

### Fix

```bash
uv pip install "setuptools<71"
```

Or add to `requirements.txt`:

```
setuptools<71
mlflow==2.13.0
...
```

This pins setuptools to a version that still includes `pkg_resources`. The `<71` constraint means "any version from 0.0.0 up to 70.99.99" — uv resolves it to `70.3.0` (the latest 70.x).

### Why Not Upgrade MLflow Instead?

MLflow 2.14+ may have fixed the `pkg_resources` import, but:
- Our pipeline was tested with 2.13.0
- Upgrading mid-project risks breaking other things
- `setuptools<71` is a safe, minimal fix
- We can upgrade MLflow in a future sprint

## The pyproject.toml Fix

### Symptom

```
warning: Failed to parse `pyproject.toml` during environment creation:
  TOML parse error at line 2, column 8
    |
  2 | name = "heart disease prediction"
    |        ^^^^^^^^^^^^^^^^^^^^^^^^^^
  Not a valid package or extra name
```

### Why

PEP 508 requires package names to contain only letters, digits, hyphens, underscores, and dots. Spaces are not allowed.

### Fix

```toml
# Before (broken)
name = "heart disease prediction"

# After (valid)
name = "heart-disease-prediction"
```

## Setup Steps (Reproduce on a New Machine)

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Create venv
uv venv .venv --python 3.12

# 3. Activate it
source .venv/bin/activate

# 4. Install dependencies
uv pip install -r requirements.txt

# 5. Verify key imports
python -c "import mlflow; import boto3; import prefect; import dotenv; import uvicorn; print('All OK')"
```

## How to Debug

### "Failed to parse pyproject.toml"

Check the `name` field — no spaces, must start with a letter/digit:
```toml
name = "valid-name-123"      # OK
name = "also_valid_name"     # OK
name = "not valid name"      # BROKEN
name = "123-starts-with-num" # OK but unusual
```

### "Command not found: uv"

```bash
# Check if uv is installed
which uv
# If empty, install it:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Restart your shell or:
source ~/.bashrc
```

### "No module named 'pkg_resources'"

```bash
# Check setuptools version
python -c "import setuptools; print(setuptools.__version__)"
# If >= 71, downgrade:
uv pip install "setuptools<71"
```

### "No matching distribution for X"

```bash
# Check Python version in venv
python --version
# Must be 3.9-3.12 for mlflow 2.13.0

# Recreate with correct Python
uv venv .venv --python 3.12
```

## Practical Tips

### Add/Remove a Package

```bash
# Add
uv pip install new-package
# Then update requirements.txt

# Remove
uv pip uninstall new-package
# Then remove from requirements.txt
```

### Freeze Exact Versions

```bash
uv pip freeze > requirements-lock.txt
```

This creates a lock file with exact versions and hashes — useful for reproducible deployments.

### Use uv for Running Scripts

```bash
# Run a script without activating the venv
uv run --python 3.12 train.py

# Run with specific packages (uv handles the venv automatically)
uv run --with matplotlib script.py
```

### The .venv in .gitignore

`.venv/` is already in `.gitignore`. Never commit a virtual environment — it's machine-specific (compiled C extensions differ between macOS/Linux/Windows).

### requirements.txt vs pyproject.toml

We maintain both:

| File | Purpose | Format |
|------|---------|--------|
| `requirements.txt` | Pip-compatible, used by `uv pip install -r` | One package per line |
| `pyproject.toml` | Python project metadata, used by build tools | TOML format |

Keep them in sync. When adding a package, add to both.

### Verifying the Local Pipeline Works

```bash
source .venv/bin/activate
cd heart_disease_prediction
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
print('MLFLOW_TRACKING_URI:', os.getenv('MLFLOW_TRACKING_URI'))
print('DATA_PATH:', os.getenv('DATA_PATH'))
"
```

This confirms your `.env` is loaded and values are correct before running the full pipeline.
