# 06 — AWS Free Tier: What's Actually Free

## What We Used

| Service | Free Allowance | Our Usage | Headroom |
|---------|---------------|-----------|----------|
| EC2 t2.micro | 750 hrs/month | ~744 hrs (1 instance 24/7) | 6 hrs |
| RDS db.t3.micro | 750 hrs/month | ~744 hrs (1 instance 24/7) | 6 hrs |
| S3 Storage | 5 GB | ~1 GB | 4 GB |
| S3 Requests | 2K PUT / 20K GET | ~500 / ~5K | Plenty |
| ECR Storage | 500 MB | ~300 MB | 200 MB |
| CloudWatch Logs | 5 GB ingestion | ~500 MB | 4.5 GB |
| CloudWatch Metrics | 10 custom | ~3 | 7 |
| CloudWatch Dashboards | 3 | 1 | 2 |
| CloudWatch Alarms | 10 | 1 | 9 |
| GitHub Actions | 2,000 min/month | ~200 min | 1.8K min |
| Prefect Cloud | 10,000 runs/month | ~4-8 runs | 9.9K runs |

**Total cost within free tier: $0/month**

## The Catch: What's NOT Free

### Elastic IP (Public IPv4)

| Scenario | Cost |
|----------|------|
| EIP attached to running instance | **$0.005/hr (~$3.60/month)** |
| EIP attached to stopped instance | $0.005/hr |
| EIP allocated but unattached | $0.005/hr |

AWS introduced this charge in 2024. Public IPv4 addresses cost $0.005/hr regardless of whether the instance is running. This is **not covered by the free tier**.

**Your actual monthly cost: ~$3.60 for the EIP.**

### EC2 Public IP (Before EIP Attachment)

When an EC2 instance launches, it gets a temporary public IP (free). When you attach an EIP, the temporary IP is released. The EIP then costs $0.005/hr. There's no way around this — you need a static IP for MLflow/Prefect to have a stable endpoint.

### Data Transfer

| Direction | Cost |
|-----------|------|
| Inbound to EC2 | Free |
| Outbound from EC2 to internet | First 100 GB/month free, then $0.09/GB |
| EC2 to S3 (same region) | Free |
| EC2 to RDS (same VPC) | Free |
| EC2 to ECR (same region) | Free |

Our traffic is mostly EC2 ↔ S3/RDS/ECR (all same region = free). Outbound internet traffic is minimal (Prefect Cloud API calls, package downloads). You won't exceed 100 GB.

### RDS Storage

RDS includes 20 GB gp2 storage free. Our usage will be well under 1 GB (MLflow metadata is tiny). No extra cost.

## Theory: Free Tier Types

### "12-Month Free Tier" vs "Always Free"

| Type | Duration | Our Services |
|------|----------|-------------|
| 12-month free | First 12 months after account creation | EC2, RDS, S3, ECR, CloudWatch (generous limits) |
| Always free | Forever | CloudWatch (10 metrics, 3 dashboards), Lambda, DynamoDB (25 GB) |

**Critical**: After 12 months, your EC2 + RDS will cost ~$15.50/month. Set a calendar reminder.

### The 750-Hour Trap

Free tier gives you 750 hours/month for EC2 and 750 hours/month for RDS. A month has ~744 hours.

- **1 instance running 24/7** = 744 hours → within the 750 limit ✓
- **2 instances running 24/7** = 1,488 hours → **exceeds the limit** ✗
- **1 instance + 1 stopped for 6 hours** = 744 + 6 = 750 → barely fits

The limit is **per service, not combined**. You get 750 EC2 hours AND 750 RDS hours independently.

### How AWS Calculates Hours

- A running instance counts as 1 hour per clock hour, even if you run it for 5 minutes
- A stopped instance doesn't count (but EIP still charges)
- RDS auto-stopped instances don't count hours while stopped

## How to Track Spending

### Set Up AWS Budgets Alert (Do This Now)

1. AWS Console → Billing → AWS Budgets
2. Create budget → "Zero Spend" or "$1 monthly"
3. Set alert threshold at $1
4. Add your email

This sends an email if you accidentally exceed free tier.

### CLI Check

```bash
# Current month's charges
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-05-31 \
  --granularity MONTHLY \
  --metrics BlendedCost

# By service
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-05-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

### Free Tier Usage Check

```bash
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,State.Name,LaunchTime]' --output table
aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceClass,DBInstanceStatus]' --output table
```

## Money-Saving Tips

### Stop EC2 When Not Developing

```bash
# Stop (EIP still charges $0.005/hr = ~$3.60/month)
aws ec2 stop-instances --instance-ids i-0bda8692493c15a77

# Start when needed (takes ~30 seconds)
aws ec2 start-instances --instance-ids i-0bda8692493c15a77
```

### Stop RDS When Not Training

```bash
# Stop RDS (saves 744 hrs/month of free tier hours)
aws rds stop-db-instance --db-instance-identifier heart-disease-mlops-db

# Note: RDS auto-starts after 7 days of no connections
# Note: RDS auto-starts if you modify the instance
```

### Use Spot Instances (Not for Free Tier)

If you're past the free tier, t2/t3 spot instances cost ~70% less. But they can be interrupted, so they're only good for training, not for long-running services.

### Clean Up Unused Resources

```bash
# Old ECR images
aws ecr list-images --repository-name heart-disease-mlops-api --output table

# Old S3 objects
aws s3 ls s3://heart-disease-mlops-695074562426/ --recursive --human-readable
```

The ECR lifecycle policy (keep last 5 images) and S3 lifecycle rule (delete monitoring reports after 90 days) handle this automatically.

## What Happens When Free Tier Expires

| Service | Monthly Cost After Free Tier |
|---------|------------------------------|
| EC2 t2.micro 24/7 | ~$8.50 |
| RDS db.t3.micro 24/7 | ~$7.00 |
| S3 (1 GB) | ~$0.25 |
| ECR (300 MB) | ~$0.04 |
| CloudWatch | ~$0.50 |
| EIP | ~$3.60 |
| **Total** | **~$20/month** |

This is still very cheap for a full MLOps stack. Compare with SageMaker MLflow alone at $72/month.
