# 03 — Systemd Service & Log Management

Advanced configuration for MLflow systemd service, including logging, auto-restart, and resource limits.

## Overview

Once MLflow is running manually and works, we optimize the systemd service for:
- **Auto-restart** on failure or EC2 reboot
- **Journald logging** for centralized log access
- **Resource limits** to prevent OOM (out of memory)
- **Health checks** via `systemctl status`

## Service File Reference

The systemd service created in Phase 2 / Step 8:

```ini
[Unit]
Description=MLflow Tracking Server
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/home/ubuntu
EnvironmentFile=/home/ubuntu/mlflow-env.sh
ExecStart=/home/ubuntu/mlflow-venv/bin/mlflow server \
  --backend-store-uri postgresql://mlflow_user:MySecurePass123!@DB_HOST:5432/mlflow \
  --default-artifact-root s3://S3_BUCKET/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Key Directives Explained

| Directive | Value | Purpose |
|-----------|-------|---------|
| `After=network.target` | — | Start only after network is up |
| `Type=notify` | — | Gunicorn supports systemd notifications |
| `User=ubuntu` | — | Run as unprivileged user (not root) |
| `EnvironmentFile=` | Path to `.sh` | Load environment variables from file |
| `ExecStart=` | Command | MLflow server command to run |
| `Restart=always` | — | Restart if process exits (any code) |
| `RestartSec=10` | 10 seconds | Wait 10 sec before restart attempt |
| `StandardOutput=journal` | — | Log to systemd journald (not file) |
| `StandardError=journal` | — | Log errors to journald |

## Service Commands

```bash
# Check status
sudo systemctl status mlflow

# View recent logs (last 50 lines)
sudo journalctl -u mlflow -n 50 --no-pager

# Follow logs in real-time (like tail -f)
sudo journalctl -u mlflow -f

# Filter logs by priority (errors only)
sudo journalctl -u mlflow -p err

# View logs since last boot
sudo journalctl -u mlflow -b

# View logs from the last hour
sudo journalctl -u mlflow --since "1 hour ago"

# Restart the service
sudo systemctl restart mlflow

# Stop the service
sudo systemctl stop mlflow

# Disable auto-start (manual start required)
sudo systemctl disable mlflow

# Enable auto-start on boot
sudo systemctl enable mlflow
```

## Monitoring Service Health

### Check if MLflow is responding:

```bash
# From EC2
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health

# Should return: 200
```

### Create a health check script:

Save as `/home/ubuntu/check-mlflow-health.sh`:

```bash
#!/bin/bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000)
if [ "$STATUS" = "200" ]; then
  echo "✓ MLflow healthy"
  exit 0
else
  echo "✗ MLflow unhealthy (status: $STATUS)"
  exit 1
fi
```

```bash
chmod +x /home/ubuntu/check-mlflow-health.sh
./check-mlflow-health.sh
```

### View systemd service events:

```bash
# List all service state changes
sudo systemctl show mlflow --all

# Check restart count
sudo systemctl show mlflow -p NRestarts

# If NRestarts > 0, service has been restarted (possible crashes)
```

## Resource Limits (Optional)

To prevent runaway processes:

```bash
# On EC2, edit service:
sudo systemctl edit mlflow
```

Add under `[Service]` section:

```ini
# Memory limit: 512 MB
MemoryLimit=512M

# CPU shares (relative weight)
CPUShares=512

# File descriptor limit
LimitNOFILE=65536
```

Save and apply:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mlflow
```

## Log Rotation

Journald automatically manages logs. To view disk usage:

```bash
# Check systemd-journald disk usage
sudo journalctl --disk-usage

# Clean old logs (keep only 1 month)
sudo journalctl --vacuum-time 30d
```

## Troubleshooting Common Issues

### Service stuck in "activating"

```bash
# Check logs
sudo journalctl -u mlflow -n 100

# Manually test the ExecStart command
/home/ubuntu/mlflow-venv/bin/mlflow server \
  --backend-store-uri postgresql://mlflow_user:PASSWORD@DB_HOST:5432/mlflow \
  --default-artifact-root s3://BUCKET/artifacts/ \
  --host 0.0.0.0 \
  --port 5000
```

If manual start fails, review database connection and S3 credentials.

### Service crashes after a few seconds

```bash
# View full logs with timestamps
sudo journalctl -u mlflow --output short-precise

# Common causes:
# 1. Port 5000 already in use: lsof -i :5000
# 2. Database connection failed: test psql connection manually
# 3. S3 credentials expired: verify IAM role on EC2
```

### High memory usage

```bash
# Check process memory
ps aux | grep mlflow | grep -v grep

# If > 500 MB, check for memory leak or long-running requests
sudo journalctl -u mlflow -f
```

## Systemd Best Practices

1. **Always test manually first:**
   ```bash
   /home/ubuntu/mlflow-venv/bin/mlflow server ...
   # Verify it works, then stop (Ctrl+C)
   ```

2. **Use environment files for secrets:**
   - Don't embed passwords in service file
   - Use `EnvironmentFile=/home/ubuntu/mlflow-env.sh`
   - Restrict permissions: `chmod 600 /home/ubuntu/mlflow-env.sh`

3. **Monitor logs regularly:**
   ```bash
   sudo journalctl -u mlflow -f
   # Watch for connection errors, out-of-memory, or warnings
   ```

4. **Test restart behavior:**
   ```bash
   sudo systemctl restart mlflow
   # Verify it comes back up and logs successfully
   ```

5. **Document your configuration:**
   Save a copy of the service file:
   ```bash
   cp /etc/systemd/system/mlflow.service ~/mlflow-service-backup.ini
   ```

## Verify Service on EC2 Reboot

Once systemd is configured, test a reboot:

```bash
# On EC2
sudo reboot

# Wait 1–2 minutes, then SSH back in
ssh -i key.pem ubuntu@EC2_PUBLIC_IP

# Check status
sudo systemctl status mlflow
# Should show: active (running)

# Test MLflow UI
curl -s http://localhost:5000 | head -5
```

---

**Next:** Proceed to [04-verification-and-troubleshooting.md](04-verification-and-troubleshooting.md) for end-to-end testing.
