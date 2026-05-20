# Prefect Agent Setup on EC2

Step-by-step guide to installing and configuring the Prefect agent as a systemd service.

---

## Overview

The Prefect agent (called "worker" in Prefect 3.x) is a process that:
- Connects to Prefect Cloud or a Prefect server
- Listens for scheduled or manually-triggered flow runs
- Executes your pipeline code on the EC2 instance
- Reports status, logs, and artifacts back to Prefect

---

## Installation

The Prefect worker is installed via pip (already done in user_data.sh during EC2 setup):

```bash
# In user_data.sh.tftpl (already done)
sudo /opt/uv/uv pip install prefect==3.4.10
```

This creates:
- Binary: `/opt/mlflow-venv/bin/prefect`
- Version: Prefect 3.x (uses `worker` command, not `agent`)

---

## The Critical Fix: `agent` → `worker`

### The Problem

Prefect 2.x used `prefect agent start`. Prefect 3.x changed this to `prefect worker start`.

**Error you'll see:**
```bash
$ prefect agent start --pool default

╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Unknown command "agent". Did you mean "event"? Available commands: deploy,   │
│ init, flow, flows, flow-run, flow-runs, deployment, deployments, ...         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

This error repeated thousands of times in our logs because systemd kept restarting the failed service.

### The Fix

**Old (broken) service file:**
```ini
[Service]
ExecStart=/opt/mlflow-venv/bin/prefect agent start --pool heart-disease
```

**New (working) service file:**
```ini
[Service]
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
```

**Key changes:**
- `agent start` → `worker start`
- `--pool heart-disease` → `--pool default` (must match deployment)
- Added `--work-queue default` (explicit queue name)

---

## Creating the Systemd Service

### Complete Service File

Create `/etc/systemd/system/prefect-agent.service`:

```ini
[Unit]
Description=Prefect Agent
After=network.target mlflow.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu

# Critical: Set PATH so prefect can find Python
Environment="PATH=/opt/mlflow-venv/bin:/usr/local/bin:/usr/bin:/bin"

# Prefect configuration
Environment="PREFECT_HOME=/home/ubuntu/.prefect"

# For Prefect Cloud (add these when connecting to Cloud):
# Environment="PREFECT_API_URL=https://api.prefect.cloud/api/accounts/XXX/workspaces/YYY"
# Environment="PREFECT_API_KEY=pnu_xxxxxxxxxxxxxxxx"

# MLflow and AWS settings (pipeline needs these)
Environment="MLFLOW_TRACKING_URI=http://10.0.0.186:5000"
Environment="AWS_REGION=us-east-1"
Environment="S3_BUCKET=heart-disease-mlops-695074562426"

# The actual command
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default

# Auto-restart on failure
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Installation Commands

```bash
# SSH to EC2
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238

# Stop any old service
sudo systemctl stop prefect-agent 2>/dev/null
sudo systemctl disable prefect-agent 2>/dev/null

# Create service file
sudo tee /etc/systemd/system/prefect-agent.service > /dev/null << 'EOF'
[Unit]
Description=Prefect Agent
After=network.target mlflow.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu
Environment="PATH=/opt/mlflow-venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PREFECT_HOME=/home/ubuntu/.prefect"
Environment="MLFLOW_TRACKING_URI=http://10.0.0.186:5000"
Environment="AWS_REGION=us-east-1"
Environment="S3_BUCKET=heart-disease-mlops-695074562426"
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable (start on boot)
sudo systemctl enable prefect-agent

# Start now
sudo systemctl start prefect-agent

# Verify
sudo systemctl status prefect-agent
```

---

## Environment Variables Explained

| Variable | Purpose | Example |
|----------|---------|---------|
| `PATH` | Find Python/prefect binary | `/opt/mlflow-venv/bin:...` |
| `PREFECT_HOME` | Prefect config/cache directory | `/home/ubuntu/.prefect` |
| `PREFECT_API_URL` | Where to connect (Cloud or local) | `https://api.prefect.cloud/...` |
| `PREFECT_API_KEY` | Authentication for Cloud | `pnu_xxxxxxxxxxxxxxxx` |
| `MLFLOW_TRACKING_URI` | Where to log experiments | `http://10.0.0.186:5000` |
| `AWS_REGION` | AWS SDK region | `us-east-1` |
| `S3_BUCKET` | Default S3 bucket name | `heart-disease-mlops-...` |

---

## Verifying the Agent

### Check Service Status

```bash
sudo systemctl status prefect-agent --no-pager
```

**Good output:**
```
● prefect-agent.service - Prefect Agent
     Loaded: loaded (/etc/systemd/system/prefect-agent.service; enabled)
     Active: active (running) since Wed 2026-05-20 19:34:50 UTC
   Main PID: 31633 (prefect)
      Tasks: 1
     Memory: 32.7M
        CPU: 4.451s
   CGroup: ...
           └─31633 /opt/mlflow-venv/bin/python ... prefect worker start
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u prefect-agent -f

# Last 100 lines
sudo journalctl -u prefect-agent --no-pager | tail -100

# Since last boot
sudo journalctl -u prefect-agent --since today --no-pager
```

**What to look for:**
- ✅ `Starting temporary server on http://127.0.0.1:8992` (means no PREFECT_API_URL set)
- ✅ `Worker started` (successfully connected)
- ❌ `Unknown command "agent"` (wrong command, needs fix)
- ❌ `Connection refused` (can't reach PREFECT_API_URL)
- ❌ `Authentication failed` (wrong PREFECT_API_KEY)

### Check Process

```bash
# Is prefect running?
ps aux | grep prefect

# Expected output:
ubuntu   31633  ...  /opt/mlflow-venv/bin/python /opt/mlflow-venv/bin/prefect worker start
```

---

## Troubleshooting

### Agent Won't Start

```bash
# Check for syntax errors in service file
sudo systemd-analyze verify /etc/systemd/system/prefect-agent.service

# Test the command manually (without systemd)
sudo -u ubuntu bash -c '
  export PATH=/opt/mlflow-venv/bin:$PATH
  export MLFLOW_TRACKING_URI=http://10.0.0.186:5000
  /opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
'
# ^ This shows errors immediately instead of in logs
```

### High Restart Count

```bash
# Check restart count
sudo systemctl show prefect-agent --property=NRestarts
# NRestarts=5883  ← This is bad! Should be 0-5

# Fix: Check logs for error, fix service file
sudo journalctl -u prefect-agent --no-pager | tail -50
```

### Agent Running But Not Picking Up Work

**Symptom:** Agent shows "active" but flows stay in "Scheduled" state.

**Likely causes:**
1. **Wrong pool name** — Deployment uses pool "default", agent started with "--pool production"
2. **Wrong work queue** — Deployment targets "default", agent listening on "high-priority"
3. **Not connected to same server** — Local server vs Cloud vs temporary server

**Debug:**
```bash
# Check what pool/queue agent is using
sudo journalctl -u prefect-agent | grep -i "pool\|queue"

# Should show: "Worker '...' started in pool 'default' work queue 'default'"
```

---

## Integration with Terraform

For new EC2 instances, add to `user_data.sh.tftpl`:

```bash
# Create Prefect agent service
cat > /etc/systemd/system/prefect-agent.service << 'EOF'
[Unit]
Description=Prefect Agent
After=network.target mlflow.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu
Environment="PATH=/opt/mlflow-venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PREFECT_HOME=/home/ubuntu/.prefect"
%{ if prefect_api_url != "" }
Environment="PREFECT_API_URL=${prefect_api_url}"
%{ endif }
%{ if prefect_api_key != "" }
Environment="PREFECT_API_KEY=${prefect_api_key}"
%{ endif }
Environment="MLFLOW_TRACKING_URI=http://$(hostname -I | awk '{print $1}'):5000"
Environment="AWS_REGION=${aws_region}"
Environment="S3_BUCKET=${s3_bucket}"
ExecStart=/opt/mlflow-venv/bin/prefect worker start --pool default --work-queue default
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable prefect-agent
systemctl start prefect-agent
```

This ensures new instances automatically have the correct service.

---

## Summary

Key points for Prefect agent setup:

1. **Use `worker` not `agent`** — Prefect 3.x changed the command name
2. **Set PATH explicitly** — Otherwise systemd won't find Python
3. **Match pool names** — Deployment pool must equal agent `--pool` argument
4. **Environment variables** — MLflow URI and AWS creds needed for pipeline
5. **Auto-restart** — `Restart=always` handles transient failures
6. **Logs via journalctl** — `journalctl -u prefect-agent -f` for real-time debugging
