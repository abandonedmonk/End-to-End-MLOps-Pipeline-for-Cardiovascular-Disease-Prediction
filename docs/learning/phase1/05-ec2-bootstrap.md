# 05 — EC2 Bootstrap (user_data, systemd, uv)

## What We Did

When Terraform creates the EC2 instance, a bash script (`user_data.sh.tftpl`) runs automatically on first boot. This script:

1. Adds 1GB swap space (t2.micro has only 1GB RAM)
2. Installs system packages (Docker, Python, git)
3. Installs `uv` for fast Python package management
4. Creates a Python virtual environment with MLflow, Prefect, scikit-learn, etc.
5. Creates systemd services for MLflow and Prefect agent
6. Waits for RDS to be reachable, then starts MLflow
7. Installs CloudWatch Agent for logs and metrics

## Theory: EC2 User Data

### What Is User Data?

User data is a script that runs **once** when an EC2 instance first launches. It runs as `root` and is the standard way to bootstrap instances.

```
EC2 Launch → cloud-init reads user_data → executes as root → instance is ready
```

### The `templatefile()` Pattern

Our user data is a **template**, not a plain bash script. Terraform's `templatefile()` injects variables at plan time:

```hcl
locals {
  user_data_rendered = templatefile(
    "${path.module}/user_data.sh.tftpl",
    {
      rds_endpoint   = module.rds.endpoint  # Terraform output
      rds_password   = var.rds_password      # From tfvars
      s3_bucket_name = module.s3.bucket_name # Terraform output
    }
  )
}
```

In the template, `${rds_endpoint}` is replaced with the actual RDS endpoint. For literal bash variables, use `$$`:

```bash
IMAGE_TAG=$${2:-latest}  # Terraform renders this as: IMAGE_TAG=${2:-latest}
```

### User Data Limitations

| Limitation | Detail |
|------------|--------|
| Runs once | Only on first boot (unless `user_data_replace_on_change = true`) |
| No interactive prompts | Script must be fully non-interactive |
| Size limit | 16 KB (base64 encoded) |
| No output to terminal | All output goes to `/var/log/user-data.log` |
| Fails silently | If script exits with error, EC2 still shows "running" |
| Sensitive values | RDS password is visible in user data (fix in Phase 9) |

### Why `set -euo pipefail` at the Top

```bash
#!/bin/bash
set -euo pipefail
```

| Flag | What It Does | Why |
|------|-------------|-----|
| `-e` | Exit on any command failure | Stops at first error instead of continuing blindly |
| `-u` | Treat unset variables as error | Catches typos in variable names |
| `-o pipefail` | Pipeline fails if any command fails | `curl | grep` fails if curl fails |

Without these, a failing `apt-get install` would silently continue and you'd spend hours debugging why a package is missing.

### Logging with `exec > >(tee ...)`

```bash
exec > >(tee /var/log/user-data.log) 2>&1
```

This sends all script output to both the terminal and a log file. You can then SSH in and check progress:

```bash
tail -f /var/log/user-data.log
```

## Theory: systemd Services

### Why systemd (Not Docker or Screen)

| Method | Pros | Cons |
|--------|------|------|
| **systemd** | Auto-restart, start on boot, logs via journalctl, standard | Requires .service file |
| Docker | Isolated, portable | Overhead on t2.micro, MLflow doesn't need isolation |
| screen/tmux | Simple | No auto-restart, no boot start, no log management |
| Supervisor | Python-native | Extra dependency, less standard than systemd |

**Our choice**: systemd — it's the standard Linux service manager, handles crashes, and integrates with `journalctl` for logs.

### The MLflow Service File

```ini
[Unit]
Description=MLflow Tracking Server
After=network.target          # Wait for network before starting

[Service]
User=ubuntu                    # Run as ubuntu, not root
Group=ubuntu
Environment=MLFLOW_TRACKING_URI=http://localhost:5000
Environment=AWS_REGION=us-east-1
ExecStart=/opt/mlflow-venv/bin/mlflow server \
  --backend-store-uri postgresql://user:pass@host/db \
  --default-artifact-root s3://bucket/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
Restart=on-failure             # Auto-restart if process crashes
RestartSec=10                  # Wait 10 seconds before restart

[Install]
WantedBy=multi-user.target    # Start on boot
```

### Key systemd Commands

```bash
sudo systemctl start mlflow      # Start now
sudo systemctl stop mlflow       # Stop now
sudo systemctl restart mlflow    # Restart (after config changes)
sudo systemctl status mlflow     # Check status + recent logs
sudo systemctl enable mlflow     # Start on boot
sudo journalctl -u mlflow -f    # Follow logs in real-time
sudo journalctl -u mlflow -n 50 # Last 50 log lines
```

### Service States

| State | Meaning |
|-------|---------|
| `active` | Running normally |
| `activating` | Starting up (or restarting after failure) |
| `failed` | Crashed and waiting for RestartSec before retry |
| `inactive` | Stopped (not running) |

If you see `activating` for more than 30 seconds, it's probably crash-looping. Check `journalctl`.

## Theory: Why Swap Space on t2.micro

t2.micro has 1 GB RAM. Our services use ~750 MB at idle:

| Service | RAM |
|---------|-----|
| MLflow (gunicorn, 5 workers) | ~200 MB |
| Docker daemon | ~50 MB |
| CloudWatch Agent | ~30 MB |
| Prefect agent | ~100 MB |
| System (kernel, SSH, etc.) | ~200 MB |
| **Total** | **~580 MB idle** |

During training or Evidently report generation, usage spikes to 900+ MB. Without swap, the OOM killer terminates processes randomly.

1GB swap gives a safety buffer:

```bash
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Swap is slower than RAM (disk vs memory), but it prevents crashes. On t2.micro, it's essential.

## How to Debug

### User Data Didn't Run or Failed

```bash
# Check if user data ran at all
ls -la /var/log/user-data.log

# Read the full log
cat /var/log/user-data.log

# Check cloud-init status
cloud-init status --long

# If cloud-init is still running, wait
cloud-init status --wait
```

### Service Is Crash-Looping

```bash
# Check status
sudo systemctl status mlflow

# Read the crash error
sudo journalctl -u mlflow --no-pager -n 30

# If it's a Python import error → missing package
# If it's a connection error → RDS/S3 not reachable
# If it's a permission error → check User= in service file
```

### Packages Missing After Bootstrap

User data might have failed partway through. Fix manually:

```bash
# Install missing package
sudo /opt/uv/uv pip install --python /opt/mlflow-venv/bin/python <package>

# Restart the service
sudo systemctl restart mlflow
```

### Checking If uv Is Working

```bash
/opt/uv/uv --version
/opt/mlflow-venv/bin/python -c "import mlflow; print(mlflow.__version__)"
```

## Practical Tips

### Reduce MLflow Worker Count to Save RAM

Default gunicorn workers = 4. Each uses ~40 MB. On t2.micro, reduce to 2:

```bash
# In the systemd service ExecStart, add --gunicorn-opts "--workers 2"
mlflow server --gunicorn-opts "--workers 2" ...
```

This saves ~80 MB at the cost of handling fewer concurrent requests (fine for our use case).

### Monitoring RAM Usage

```bash
# Quick check
free -h

# Detailed per-process
ps aux --sort=-%mem | head -10

# Watch continuously
watch -n 5 free -h
```

### If OOM Killer Strikes

```bash
# Check if OOM killed anything
dmesg | grep -i "out of memory"
sudo journalctl -k | grep -i "oom"

# The killed process will show in systemd as 'failed'
# Restart it:
sudo systemctl restart mlflow
```

### Terraform User Data Change Didn't Take Effect

Terraform's default behavior is to update user_data in-place, but AWS **does not re-run user_data on existing instances**. You must recreate:

```bash
terraform taint module.ec2.aws_instance.main
terraform apply
```

Or add this to the EC2 resource:
```hcl
user_data_replace_on_change = true  # Force recreation on user_data change
```
