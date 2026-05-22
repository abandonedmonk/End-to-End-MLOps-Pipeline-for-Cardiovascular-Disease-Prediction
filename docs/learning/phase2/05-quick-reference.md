# Quick Reference — Phase 2 Commands

Fast lookup for common operations during and after Phase 2 deployment.

## AWS CLI Queries

```bash
# Load config
source ~/.mlflow-aws-config

# Check EC2 status
aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].[State.Name, PublicIpAddress, InstanceType]' --output text

# Check RDS status
aws rds describe-db-instances --db-instance-identifier $DB_IDENTIFIER --query 'DBInstances[0].[DBInstanceStatus, Endpoint.Address]' --output text

# Check S3 contents
aws s3 ls s3://$S3_BUCKET/ --recursive --human-readable --summarize

# Check security group rules
aws ec2 describe-security-groups --group-ids $SG_ID --query 'SecurityGroups[0].IpPermissions[].{Protocol:IpProtocol, Port:FromPort, CIDR:IpRanges[0].CidrIp}' --output table

# Check IAM role
aws iam get-role --role-name $IAM_ROLE_NAME

# Get all resources tagged (optional, if you tag them)
aws ec2 describe-instances --filters "Name=tag:Phase,Values=2" --output table
```

## SSH & EC2 Operations

```bash
# SSH into EC2
ssh -i "${EC2_KEY_NAME}.pem" ubuntu@"${EC2_PUBLIC_IP}"

# Copy file to EC2
scp -i "${EC2_KEY_NAME}.pem" ./local-file.txt ubuntu@"${EC2_PUBLIC_IP}":~/

# Copy file from EC2
scp -i "${EC2_KEY_NAME}.pem" ubuntu@"${EC2_PUBLIC_IP}":~/remote-file.txt ./

# Execute command on EC2 without SSH shell
ssh -i "${EC2_KEY_NAME}.pem" ubuntu@"${EC2_PUBLIC_IP}" "command here"
```

## Systemd Service Management (on EC2)

```bash
# Check status
sudo systemctl status mlflow

# View logs (real-time)
sudo journalctl -u mlflow -f

# View logs (last 100 lines)
sudo journalctl -u mlflow -n 100 --no-pager

# Restart service
sudo systemctl restart mlflow

# Stop service
sudo systemctl stop mlflow

# Start service
sudo systemctl start mlflow

# Check if enabled on boot
sudo systemctl is-enabled mlflow
```

## MLflow UI Access

```bash
# From laptop
open "http://${EC2_PUBLIC_IP}:5000"

# Or via curl
curl -s http://${EC2_PUBLIC_IP}:5000 | head -20

# Check health endpoint
curl -I http://${EC2_PUBLIC_IP}:5000/health
```

## RDS & PostgreSQL

```bash
# Connect to RDS from laptop
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME"

# Common queries
SELECT * FROM experiments;
SELECT * FROM runs ORDER BY start_time DESC LIMIT 10;
SELECT COUNT(*) FROM metrics;
\dt                    # List all tables
\du                    # List users
\q                     # Quit

# From EC2 (if psql installed)
sudo apt install -y postgresql-client
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM runs;"
```

## MLflow Tracking (from laptop)

```bash
# Set env vars
export MLFLOW_TRACKING_URI=http://${EC2_PUBLIC_IP}:5000

# Log an experiment in Python
python3 <<'EOF'
import mlflow

with mlflow.start_run():
    mlflow.log_param("test", 1)
    mlflow.log_metric("acc", 0.9)
    mlflow.log_artifact("./file.txt")
print("✓ Logged")
EOF

# List experiments
mlflow experiments list

# Get run details
mlflow runs list --experiment-id 0
```

## S3 Operations

```bash
# List bucket contents
aws s3 ls s3://$S3_BUCKET/

# Download entire folder
aws s3 sync s3://$S3_BUCKET/artifacts/ ./local-artifacts/

# Upload file
aws s3 cp ./model.pkl s3://$S3_BUCKET/models/

# Remove file
aws s3 rm s3://$S3_BUCKET/temp/file.txt

# Sync with delete
aws s3 sync s3://$S3_BUCKET/old/ s3://$S3_BUCKET/new/ --delete

# Check size
aws s3 ls s3://$S3_BUCKET/ --recursive --human-readable --summarize
```

## Troubleshooting Commands

```bash
# On EC2: Check if port 5000 is listening
sudo lsof -i :5000

# On EC2: Check process memory/CPU
ps aux | grep mlflow

# On EC2: Check disk space
df -h

# On EC2: Check network connectivity
ping 8.8.8.8
curl -s https://checkip.amazonaws.com

# On laptop: Test network path to EC2
traceroute $EC2_PUBLIC_IP
mtr $EC2_PUBLIC_IP

# Check Python environment
which python3
python3 -m pip list | grep mlflow
```

## Cleanup & Teardown

```bash
# Stop MLflow service (on EC2)
sudo systemctl stop mlflow

# Delete EC2 instance
aws ec2 terminate-instances --instance-ids $INSTANCE_ID

# Delete RDS instance (requires confirmation)
aws rds delete-db-instance \
  --db-instance-identifier $DB_IDENTIFIER \
  --skip-final-snapshot

# Delete S3 bucket (must be empty first)
aws s3 rm s3://$S3_BUCKET --recursive
aws s3api delete-bucket --bucket $S3_BUCKET

# Delete IAM role
aws iam remove-role-from-instance-profile \
  --instance-profile-name $INSTANCE_PROFILE_NAME \
  --role-name $IAM_ROLE_NAME
aws iam detach-role-policy \
  --role-name $IAM_ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam delete-role --role-name $IAM_ROLE_NAME

# Delete security group
aws ec2 delete-security-group --group-id $SG_ID

# Delete key pair
aws ec2 delete-key-pair --key-name $EC2_KEY_NAME
rm -f "${EC2_KEY_NAME}.pem"
```

## Environment Variables to Set (on laptop)

```bash
# Add to ~/.bashrc or ~/.zshrc
export AWS_REGION=us-east-1
export MLFLOW_TRACKING_URI=http://<EC2-IP>:5000
export MLFLOW_ARTIFACT_ROOT=s3://your-bucket-name/artifacts/

# Then source:
source ~/.bashrc
```

## Useful Aliases (optional)

```bash
# Add to ~/.bashrc
alias mlflow-ui="open http://${EC2_PUBLIC_IP}:5000"
alias mlflow-ssh="ssh -i ${EC2_KEY_NAME}.pem ubuntu@${EC2_PUBLIC_IP}"
alias mlflow-logs="ssh -i ${EC2_KEY_NAME}.pem ubuntu@${EC2_PUBLIC_IP} 'sudo journalctl -u mlflow -f'"
alias mlflow-status="ssh -i ${EC2_KEY_NAME}.pem ubuntu@${EC2_PUBLIC_IP} 'sudo systemctl status mlflow'"
```

## Useful Links

- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [AWS Free Tier](https://aws.amazon.com/free/)
- [AWS RDS Limits](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Limits.html)
- [Systemd Manual](https://man7.org/linux/man-pages/man1/systemd.1.html)

---

**Got stuck?** Check [04-verification-and-troubleshooting.md](04-verification-and-troubleshooting.md) for detailed debugging.
